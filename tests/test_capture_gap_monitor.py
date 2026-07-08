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


def test_end_gap_before_start_raises():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(10))
    with pytest.raises(CaptureError):
        monitor.end_gap("BTC/EUR", at=_at(5))


def test_gap_seconds_includes_still_open_window_when_at_given():
    monitor = GapMonitor()
    monitor.start_gap("BTC/EUR", "reconnect", at=_at(0))
    assert monitor.gap_seconds("BTC/EUR", at=_at(20)) == 20.0
    # Without `at`, only closed gap time counts.
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
