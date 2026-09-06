from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from cli.capture.errors import CaptureError
from cli.capture.gap_monitor import DiskWatermark, GapMonitor, ping_healthcheck

T0 = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)


def _at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_gap_open_then_close_accumulates_duration():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    duration = monitor.end_gap("BTC/EUR", at=_at(30))
    assert duration == 30.0
    assert monitor.gap_seconds("BTC/EUR") == 30.0
    assert monitor.is_open("BTC/EUR") is False


def test_gap_accumulates_across_multiple_windows():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    monitor.end_gap("BTC/EUR", at=_at(10))
    monitor.start_gap("BTC/EUR", "checksum_resync", at=_at(100))
    monitor.end_gap("BTC/EUR", at=_at(115))
    assert monitor.gap_seconds("BTC/EUR") == 25.0


def test_start_gap_is_idempotent_earliest_start_wins():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(5))  # ignored - already open
    duration = monitor.end_gap("BTC/EUR", at=_at(10))
    assert duration == 10.0


def test_end_gap_with_no_open_gap_returns_zero():
    monitor = GapMonitor()
    assert monitor.end_gap("BTC/EUR", at=_at(0)) == 0.0


def test_end_gap_clamps_a_backward_stepped_clock():
    # T0032 mirror for the per-pair windows: `at` is the wall clock, so an end before the start is a
    # backward clock step (chrony makestep), not a caller bug — and an escaping error here kills the
    # consumer task and with it the daemon.
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(120))
    assert monitor.end_gap("BTC/EUR", at=_at(0)) == 0.0  # clamped, not raised
    assert monitor.is_open("BTC/EUR") is False  # the window really closed ...
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(200))  # ... so the NEXT gap books normally
    assert monitor.end_gap("BTC/EUR", at=_at(230)) == 30.0
    assert monitor.gap_seconds("BTC/EUR") == 30.0


def test_gap_seconds_clamps_open_pair_window_under_backward_clock():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    monitor.end_gap("BTC/EUR", at=_at(30))  # 30 s legitimately booked
    monitor.start_gap("BTC/EUR", "checksum_resync", at=_at(120))
    assert monitor.gap_seconds("BTC/EUR", at=_at(0)) == 30.0  # open window contributes 0, not -120
    assert monitor.gap_ratio("BTC/EUR", window_seconds=60.0, at=_at(0)) == pytest.approx(0.5)


def test_gap_seconds_clamps_open_watermark_window_under_backward_clock():
    monitor = GapMonitor()
    monitor.start_watermark_gap(at=_at(120))
    assert monitor.gap_seconds("BTC/EUR", at=_at(0)) == 0.0  # not -120


def test_gap_seconds_includes_still_open_window_when_at_given():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    assert monitor.gap_seconds("BTC/EUR", at=_at(20)) == 20.0
    assert monitor.gap_seconds("BTC/EUR") == 0.0


def test_gap_ratio_divides_by_window_seconds():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    monitor.end_gap("BTC/EUR", at=_at(60))
    assert monitor.gap_ratio("BTC/EUR", window_seconds=60_000) == pytest.approx(0.001)


def test_gap_ratio_rejects_non_positive_window():
    monitor = GapMonitor()
    with pytest.raises(CaptureError):
        monitor.gap_ratio("BTC/EUR", window_seconds=0)


def test_summary_reports_per_pair():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    monitor.end_gap("BTC/EUR", at=_at(10))
    monitor.start_gap("ETH/EUR", "checksum_resync", at=_at(5))
    summary = monitor.summary(["BTC/EUR", "ETH/EUR"], window_seconds=100, at=_at(15))
    assert summary["BTC/EUR"] == {"gap_seconds": 10.0, "gap_ratio": 0.1, "open": False}
    assert summary["ETH/EUR"] == {"gap_seconds": 10.0, "gap_ratio": 0.1, "open": True}


def test_is_healthy_false_while_any_pair_has_open_gap():
    monitor = GapMonitor()
    assert monitor.is_healthy(["BTC/EUR", "ETH/EUR"]) is True
    monitor.start_gap("ETH/EUR", "reconnect", at=_at(0))
    assert monitor.is_healthy(["BTC/EUR", "ETH/EUR"]) is False
    monitor.end_gap("ETH/EUR", at=_at(1))
    assert monitor.is_healthy(["BTC/EUR", "ETH/EUR"]) is True


def test_ping_healthcheck_noop_when_url_missing(monkeypatch):
    called = False

    def fake_urlopen(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("cli.capture.gap_monitor.urllib.request.urlopen", fake_urlopen)
    ping_healthcheck(None)
    assert called is False


def test_ping_healthcheck_calls_urlopen_with_url(monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout

    monkeypatch.setattr("cli.capture.gap_monitor.urllib.request.urlopen", fake_urlopen)
    ping_healthcheck("https://hc-ping.com/abc", timeout=3)
    assert seen == {"url": "https://hc-ping.com/abc", "timeout": 3}


def test_ping_healthcheck_swallows_transport_errors(monkeypatch):
    import urllib.error

    def fake_urlopen(url, timeout):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("cli.capture.gap_monitor.urllib.request.urlopen", fake_urlopen)
    ping_healthcheck("https://hc-ping.com/abc")  # must not raise


# --- T0032: a disk-watermark breach must be BOOKED into the exit-bar gap accounting -------------
#
# A breach stops every write for every pair; unbooked into `gap_seconds`, it leaves the <0.1% gap-time
# exit bar reading CLEAN over a window that lost data. Hence a DEDICATED window, never `start_gap`.


def test_watermark_gap_accumulates_into_every_pair_gap_seconds():
    monitor = GapMonitor()
    monitor.start_watermark_gap(at=_at(0))
    duration = monitor.end_watermark_gap(at=_at(45))
    assert duration == 45.0
    assert monitor.gap_seconds("BTC/EUR") == 45.0
    assert monitor.gap_seconds("ETH/EUR") == 45.0


def test_watermark_gap_is_not_swallowed_by_a_concurrent_pair_gap():
    # Were the breach booked via `start_gap`, the checksum_resync gap already open on the pair would
    # swallow it (`start_gap` no-ops when open) and its `end_gap` would resume the ping while still
    # breached.
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "checksum_resync", at=_at(0))  # a per-pair gap is already open ...
    monitor.start_watermark_gap(at=_at(10))  # ... and a breach lands during it
    monitor.end_watermark_gap(at=_at(40))  # the breach clears -- the pair gap is untouched
    assert monitor.is_open("BTC/EUR") is True  # the checksum_resync gap is STILL open, not ended
    monitor.end_gap("BTC/EUR", at=_at(50))
    assert monitor.gap_seconds("BTC/EUR") == 50.0 + 30.0  # both counted, neither swallowed the other
    assert monitor.gap_seconds("ETH/EUR") == 30.0  # a pair with no gap of its own still sees the breach


def test_start_watermark_gap_is_idempotent_earliest_start_wins():
    monitor = GapMonitor()
    monitor.start_watermark_gap(at=_at(0))
    monitor.start_watermark_gap(at=_at(5))  # ignored -- already open, earliest breach time wins
    assert monitor.end_watermark_gap(at=_at(10)) == 10.0


def test_end_watermark_gap_with_none_open_returns_zero():
    monitor = GapMonitor()
    assert monitor.end_watermark_gap(at=_at(0)) == 0.0


def test_open_watermark_window_counts_as_of_at():
    monitor = GapMonitor()
    monitor.start_watermark_gap(at=_at(0))
    assert monitor.gap_seconds("BTC/EUR", at=_at(20)) == 20.0  # the still-open breach, as of `at`
    assert monitor.gap_seconds("BTC/EUR") == 0.0  # without `at`, only closed breach time counts


def test_end_watermark_gap_clamps_a_backward_stepped_clock():
    # A wall clock stepped BACKWARD (chrony makestep, a VM snapshot-restore) across an open breach
    # window is a clock step, not a caller bug, and `end_watermark_gap` runs inside
    # `_disk_watermark_loop`, which nothing awaits until shutdown — so it books zero, never raises.
    monitor = GapMonitor()
    monitor.start_watermark_gap(at=_at(120))
    assert monitor.end_watermark_gap(at=_at(0)) == 0.0  # the clock stepped back past the start: clamped
    monitor.start_watermark_gap(at=_at(200))  # the window really closed — the NEXT breach books normally
    assert monitor.end_watermark_gap(at=_at(230)) == 30.0
    assert monitor.gap_seconds("BTC/EUR") == 30.0


@dataclass
class _FakeUsage:
    free: int


def test_disk_watermark_healthy_when_free_space_above_threshold(tmp_path):
    watermark = DiskWatermark(tmp_path, min_free_bytes=100, usage_fn=lambda p: _FakeUsage(free=1000))
    assert watermark.check() is True
    assert watermark.breached is False


def test_disk_watermark_breached_when_free_space_below_threshold(tmp_path):
    watermark = DiskWatermark(tmp_path, min_free_bytes=1000, usage_fn=lambda p: _FakeUsage(free=100))
    assert watermark.check() is False
    assert watermark.breached is True


def test_disk_watermark_clears_after_space_frees_up(tmp_path):
    free = {"value": 100}
    watermark = DiskWatermark(tmp_path, min_free_bytes=1000, usage_fn=lambda p: _FakeUsage(free=free["value"]))
    assert watermark.check() is False
    free["value"] = 5000
    assert watermark.check() is True
    assert watermark.breached is False


# --- T0032(c): a probe that CANNOT MEASURE must not read as healthy ------------------------------
#
# The disk probe reads the filesystem; a flaky mount raises OSError. The loop catches it and keeps
# polling, but `breached` freezes at its last value -- so a disk that fills DURING a probe outage
# leaves the dead-man pinging GREEN. "Cannot measure" must be treated as "not healthy": `measurable`
# goes False on a probe failure and gates the ping alongside `breached`. A transient blip is absorbed
# by the healthcheck's grace; only a SUSTAINED failure withholds enough pings to page.


def _raises(_p):
    raise OSError("stale NFS handle")


def test_disk_watermark_is_measurable_before_any_check(tmp_path):
    watermark = DiskWatermark(tmp_path, min_free_bytes=100, usage_fn=lambda p: _FakeUsage(free=1000))
    assert watermark.measurable is True


def test_disk_watermark_becomes_unmeasurable_when_the_probe_raises(tmp_path):
    watermark = DiskWatermark(tmp_path, min_free_bytes=100, usage_fn=_raises)
    with pytest.raises(OSError):
        watermark.check()
    assert watermark.measurable is False, "a failed probe must not read as healthy"


def test_disk_watermark_measurable_recovers_when_the_probe_succeeds_again(tmp_path):
    usage = {"fn": _raises}
    watermark = DiskWatermark(tmp_path, min_free_bytes=100, usage_fn=lambda p: usage["fn"](p))
    with pytest.raises(OSError):
        watermark.check()
    assert watermark.measurable is False

    usage["fn"] = lambda p: _FakeUsage(free=1000)
    assert watermark.check() is True
    assert watermark.measurable is True
