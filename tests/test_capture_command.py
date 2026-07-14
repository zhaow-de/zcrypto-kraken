import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.book import OrderBook
from cli.capture.command import _default_pairs, _parse_ts, single_instance_lock
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA, SegmentWriter, verify_manifest

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# The point-in-time universe JSON is a gitignored *generated* artifact (its canonical committed
# form is docs/universe/point-in-time-universe.md); it is absent in CI and fresh checkouts.
_REPO_UNIVERSE = Path("data/universe/point-in-time-universe.json")


def test_default_pairs_filters_to_eur_quoted(tmp_path):
    universe_path = tmp_path / "point-in-time-universe.json"
    universe_path.write_text(json.dumps({"selected": ["BTC/EUR", "ETH/EUR", "ETH/BTC", "SOL/BTC"]}))
    assert _default_pairs(universe_path) == ["BTC/EUR", "ETH/EUR"]


def test_default_pairs_raises_when_universe_file_missing(tmp_path):
    with pytest.raises(CaptureError):
        _default_pairs(tmp_path / "missing.json")


def test_default_pairs_raises_clear_error_on_malformed_universe_file(tmp_path):
    universe_path = tmp_path / "point-in-time-universe.json"
    universe_path.write_text('{"no_selected_key": []}')
    with pytest.raises(CaptureError):
        _default_pairs(universe_path)


@pytest.mark.skipif(not _REPO_UNIVERSE.exists(), reason="generated (gitignored) universe JSON absent — see docs/universe/*.md")
def test_default_pairs_from_local_universe_file():
    # A local sanity check on the real generated universe file when present: 12 selected symbols,
    # 10 of them EUR-quoted (the "EUR majors"). Skips in CI / fresh checkouts (the file is a
    # gitignored generated artifact); _default_pairs' logic itself is covered by the synthetic
    # test_default_pairs_filters_to_eur_quoted above.
    pairs = _default_pairs(_REPO_UNIVERSE)
    assert len(pairs) == 10
    assert all(p.endswith("/EUR") for p in pairs)
    assert "BTC/EUR" in pairs
    assert "ETH/BTC" not in pairs


def test_parse_ts_parses_kraken_rfc3339():
    ts = _parse_ts("2023-10-06T17:35:55.440295Z")
    assert ts.year == 2023
    assert ts.month == 10


def test_parse_ts_raises_capture_error_on_garbage():
    with pytest.raises(CaptureError):
        _parse_ts("not-a-timestamp")


def test_capture_help_lists_options():
    result = runner.invoke(app, ["capture", "--help"])
    assert result.exit_code == 0
    # Strip ANSI: when the terminal reports color (e.g. CI with FORCE_COLOR), rich styles option
    # names with escape codes *between* characters (`-`<esc>`-pairs`), so a raw substring check for
    # "--pairs" fails even though it renders. Normalize before asserting.
    output = _ANSI_RE.sub("", result.output)
    assert "--pairs" in output
    assert "--depth" in output
    assert "--data-dir" in output
    assert "--duration" in output


class _FakeClient:
    """Replaces `CaptureClient` in `cli.capture.command` for an end-to-end wiring test: yields one
    correctly-in-sync book snapshot + one trade, then hangs — forcing the `--duration` timeout path
    to be what stops the run, exercising the finalize-on-shutdown behavior."""

    last_instance = None

    def __init__(self, pairs, depth):
        self.pairs = pairs
        self.depth = depth
        self.resubscribed = []
        _FakeClient.last_instance = self

    async def stream(self):
        book = OrderBook("BTC/EUR", depth=100)
        book.bids = {Decimal("100.0"): Decimal("1.0")}
        book.asks = {Decimal("101.0"): Decimal("1.0")}
        checksum = book.checksum()
        yield {
            "channel": "book",
            "type": "snapshot",
            "data": [
                {
                    "symbol": "BTC/EUR",
                    "bids": [{"price": 100.0, "qty": 1.0}],
                    "asks": [{"price": 101.0, "qty": 1.0}],
                    "checksum": checksum,
                    "timestamp": "2026-07-08T14:00:00.000000Z",
                }
            ],
        }
        yield {
            "channel": "trade",
            "type": "update",
            "data": [
                {
                    "symbol": "BTC/EUR",
                    "side": "buy",
                    "price": 100.5,
                    "qty": 0.01,
                    "ord_type": "market",
                    "trade_id": 1,
                    "timestamp": "2026-07-08T14:00:01.000000Z",
                }
            ],
        }
        await asyncio.Event().wait()  # hang until cancelled by the --duration timeout

    async def resubscribe_book(self, pair):
        self.resubscribed.append(pair)


class _CrashingFakeClient:
    """A client whose `stream()` blows up mid-run — simulating a bug in message handling. The
    supervisor (systemd/Docker `restart: unless-stopped`, per the T0003 design) is what's supposed
    to bring capture back; that only works if the crash actually propagates instead of being
    silently swallowed by the `--duration` timeout path."""

    def __init__(self, pairs, depth):
        pass

    async def stream(self):
        yield {"channel": "heartbeat"}
        raise RuntimeError("boom")

    async def resubscribe_book(self, pair):
        pass


def test_capture_propagates_consumer_crash_even_with_duration_set(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.capture.command.CaptureClient", _CrashingFakeClient)
    result = runner.invoke(
        app,
        ["capture", "--pairs", "BTC/EUR", "--data-dir", str(tmp_path), "--duration", "5"],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


class _CrashAfterDataFakeClient:
    """Yields one trade (which lands in a writer's buffer) and then blows up."""

    def __init__(self, pairs, depth):
        pass

    async def stream(self):
        yield {
            "channel": "trade",
            "type": "update",
            "data": [
                {
                    "symbol": "BTC/EUR",
                    "side": "buy",
                    "price": 100.5,
                    "qty": 0.01,
                    "ord_type": "market",
                    "trade_id": 7,
                    "timestamp": "2026-07-08T14:00:01.000000Z",
                }
            ],
        }
        raise RuntimeError("boom")

    async def resubscribe_book(self, pair):
        pass


def test_a_consumer_crash_still_flushes_every_writer_at_shutdown(tmp_path, monkeypatch):
    # T0032 corollary: a task that died with a non-CancelledError re-raises its corpse's exception
    # at the shutdown `await task` — pre-fix that escaped `_run`'s finally BEFORE the writer-close
    # loop, so a crash lost up to flush_rows buffered rows per stream ON TOP of itself. The crash
    # must still propagate (the supervisor is what restarts capture), but every writer flushes first.
    monkeypatch.setattr("cli.capture.command.CaptureClient", _CrashAfterDataFakeClient)
    result = runner.invoke(
        app,
        ["capture", "--pairs", "BTC/EUR", "--data-dir", str(tmp_path), "--duration", "5"],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)  # the crash still propagates...
    parts = list((tmp_path / "BTC/EUR" / "trades" / "2026" / "07" / "08").glob("14.part*.parquet"))
    assert parts, "writer.close() must run at shutdown even when a task died with an exception"
    assert pl.concat([pl.read_parquet(p) for p in parts])["trade_id"].to_list() == [7]


def test_capture_end_to_end_writes_segments_with_fake_client(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.capture.command.CaptureClient", _FakeClient)
    # A not-yet-existing data dir (the realistic first-run case — nothing has provisioned
    # /var/lib/zcrypto-capture/segments yet) must not crash the disk-watermark check.
    data_dir = tmp_path / "does" / "not" / "exist" / "yet"
    result = runner.invoke(
        app,
        [
            "capture",
            "--pairs",
            "BTC/EUR",
            "--depth",
            "100",
            "--data-dir",
            str(data_dir),
            "--duration",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output

    book_path = data_dir / "BTC/EUR" / "book" / "2026" / "07" / "08" / "14.parquet"
    trade_path = data_dir / "BTC/EUR" / "trades" / "2026" / "07" / "08" / "14.parquet"
    # The run is stopped mid-hour, and a stop never publishes a partial hour as a segment (T0036):
    # the rows are on disk as parts, and the hour is finalized by the next process — on its first
    # event, whose ts is what says hour 14 is over (the writer holds no wall clock).
    assert not book_path.exists()
    assert list(book_path.parent.glob("14.part*.parquet"))
    next_hour = datetime(2026, 7, 8, 15, 0, tzinfo=timezone.utc)
    book_writer = SegmentWriter(data_dir, "BTC/EUR", "book", BOOK_SCHEMA)
    book_writer.append(
        {
            "ts": next_hour,
            "symbol": "BTC/EUR",
            "type": "update",
            "side": "bid",
            "price": 100.0,
            "qty": 1.0,
            "checksum": 1,
        }
    )
    trade_writer = SegmentWriter(data_dir, "BTC/EUR", "trades", TRADE_SCHEMA, dedup_key="trade_id")
    trade_writer.append(
        {
            "ts": next_hour,
            "symbol": "BTC/EUR",
            "side": "buy",
            "price": 100.0,
            "qty": 1.0,
            "ord_type": "market",
            "trade_id": 2,
        }
    )

    assert book_path.exists()
    assert trade_path.exists()
    assert verify_manifest(book_path) is True
    assert verify_manifest(trade_path) is True

    book_df = pl.read_parquet(book_path)
    assert book_df.height == 2  # one bid row + one ask row
    assert set(book_df["side"].to_list()) == {"bid", "ask"}

    trade_df = pl.read_parquet(trade_path)
    assert trade_df.height == 1
    assert trade_df["trade_id"].to_list() == [1]

    assert _FakeClient.last_instance.pairs == ["BTC/EUR"]
    assert _FakeClient.last_instance.depth == 100
    assert _FakeClient.last_instance.resubscribed == []  # checksum was correct - no desync


# --- T0032: a disk-watermark breach must STOP the dead-man ping ------------------------------
#
# On breach the daemon stops writing every row (_handle_book_message / _handle_trade_message
# return early) but the WS stays connected and no gap opens -- so without this guard the
# healthchecks.io dead-man keeps reporting GREEN while the unbackfillable L2 stream is lost.


class _StubClient:
    def __init__(self, connected=True):
        self.connected = connected


class _FakeUsage:
    def __init__(self, free):
        self.free = free


def _run_healthcheck_once(monkeypatch, *, free_bytes):
    """Drive _healthcheck_loop for a few iterations and report whether it pinged."""
    from cli.capture import command as cmd
    from cli.capture.gap_monitor import DiskWatermark, GapMonitor

    pings: list[str | None] = []
    monkeypatch.setattr(cmd, "ping_healthcheck", lambda url: pings.append(url))

    watermark = DiskWatermark(Path("/tmp"), min_free_bytes=1024, usage_fn=lambda p: _FakeUsage(free=free_bytes))
    watermark.check()  # establish the breach state, as _disk_watermark_loop does

    async def drive():
        task = asyncio.create_task(
            cmd._healthcheck_loop("https://hc-ping.com/x", _StubClient(), GapMonitor(), ["BTC/EUR"], 0.01, watermark)
        )
        await asyncio.sleep(0.06)
        task.cancel()

    asyncio.run(drive())
    return pings


def test_healthcheck_pings_while_disk_is_healthy(monkeypatch):
    pings = _run_healthcheck_once(monkeypatch, free_bytes=10_000)  # above the watermark
    assert pings, "a connected, in-sync capture with disk headroom must ping the dead-man"


def test_healthcheck_withheld_when_disk_watermark_breached(monkeypatch):
    # Breached: the daemon is writing NOTHING. The dead-man must fire, not report healthy.
    pings = _run_healthcheck_once(monkeypatch, free_bytes=10)  # below min_free_bytes
    assert pings == [], "a watermark breach stops all writes -- the dead-man must NOT keep pinging"


def test_disk_watermark_loop_books_the_breach_into_gap_accounting():
    # T0032: withholding the dead-man ping PAGES the operator, but the lost time must ALSO reach
    # GapMonitor's gap_seconds -- the exit-bar metric -- or the automated bar reads clean for a window
    # that actually lost data. The watermark loop opens the dedicated breach window on a breach and
    # closes it when the disk clears, independent of the ping-withholding.
    from cli.capture import command as cmd
    from cli.capture.gap_monitor import DiskWatermark, GapMonitor

    monitor = GapMonitor()
    free = {"v": 10}  # start breached
    watermark = DiskWatermark(Path("/tmp"), min_free_bytes=1024, usage_fn=lambda p: _FakeUsage(free=free["v"]))

    async def drive():
        task = asyncio.create_task(cmd._disk_watermark_loop(watermark, monitor, 0.01))
        await asyncio.sleep(0.05)  # let the breach window accumulate
        free["v"] = 10_000  # disk clears -> the loop closes the breach window
        await asyncio.sleep(0.03)
        task.cancel()

    asyncio.run(drive())
    # The breach was booked as gap time (a closed window, so it shows without an `at`), for every pair.
    assert monitor.gap_seconds("BTC/EUR") > 0
    assert monitor.gap_seconds("ETH/EUR") > 0


def test_disk_watermark_loop_survives_a_backward_clock_step_across_a_breach(monkeypatch):
    # T0032: a breach opens; chrony steps the wall clock BACK past the window's start; the disk
    # clears; then a SECOND real breach. Pre-fix, end_watermark_gap raised on the stepped clock and
    # the loop task died silently (nothing awaits it until shutdown): watermark.check() never ran
    # again, breached froze at False, and the dead-man kept pinging green while the second breach
    # dropped every write — the exact silent death this loop exists to prevent.
    from cli.capture import command as cmd
    from cli.capture.gap_monitor import DiskWatermark, GapMonitor

    t = {"now": datetime(2026, 7, 8, 10, 0, tzinfo=timezone.utc)}

    class _SteppedClock:
        @staticmethod
        def now(tz):
            return t["now"]

    monkeypatch.setattr(cmd, "datetime", _SteppedClock)
    monitor = GapMonitor()
    free = {"v": 10}  # breached from the first tick
    watermark = DiskWatermark(Path("/tmp"), min_free_bytes=1024, usage_fn=lambda p: _FakeUsage(free=free["v"]))

    async def drive():
        task = asyncio.create_task(cmd._disk_watermark_loop(watermark, monitor, 0.01))
        await asyncio.sleep(0.03)  # the breach window opens at 10:00
        t["now"] -= timedelta(minutes=2)  # chrony steps the clock back...
        free["v"] = 10_000  # ...and the disk clears: pre-fix this tick killed the task
        await asyncio.sleep(0.03)
        assert not task.done(), "the watermark loop must survive a backward-stepped clock"
        free["v"] = 10  # the SECOND, real breach
        await asyncio.sleep(0.03)
        assert watermark.breached is True  # detected: the dead-man gate withholds the ping (pages)
        t["now"] += timedelta(seconds=45)  # time passes on the breached disk
        assert monitor.gap_seconds("BTC/EUR", at=t["now"]) >= 45.0  # and BOOKED into gap accounting
        task.cancel()

    asyncio.run(drive())


def test_disk_watermark_loop_survives_a_failing_usage_probe(monkeypatch):
    # The same silent-death channel, via the other exit: check() reads the filesystem, and a flaky
    # mount raising OSError out of disk_usage would kill the loop task just as permanently. Any
    # exception from the loop body must be logged and survived — polling is the whole point.
    from cli.capture import command as cmd
    from cli.capture.gap_monitor import DiskWatermark, GapMonitor

    monitor = GapMonitor()
    state = {"mode": "raise", "free": 10_000}

    def usage(path):
        if state["mode"] == "raise":
            raise OSError("flaky mount")
        return _FakeUsage(free=state["free"])

    watermark = DiskWatermark(Path("/tmp"), min_free_bytes=1024, usage_fn=usage)

    async def drive():
        task = asyncio.create_task(cmd._disk_watermark_loop(watermark, monitor, 0.01))
        await asyncio.sleep(0.03)  # several ticks raise inside check()...
        assert not task.done(), "the watermark loop must survive an exception from check()"
        state.update(mode="ok", free=10)  # ...then a REAL breach
        await asyncio.sleep(0.03)
        assert watermark.breached is True  # still detected: polling never stopped
        task.cancel()

    asyncio.run(drive())


# --- T0036: exactly ONE process may write the segment tree ---------------------------------------
#
# `SegmentWriter._flush_buffer` derives the next part sequence from the hour directory and names the
# part deterministically, so two processes pick the SAME sequence and write the SAME file — shredding
# each other's rows (measured: 70 of 120 destroyed). Within one process the 20 writers are safe
# (disjoint pair/kind roots); nothing prevented a SECOND process — an overlapping restart, or a human
# running `zcrypto capture` beside the service.

_TAKE_THE_LOCK = """
import sys
from pathlib import Path
from cli.capture.command import single_instance_lock
from cli.capture.errors import CaptureError

try:
    with single_instance_lock(Path(sys.argv[1])):
        sys.exit(0)   # got it
except CaptureError:
    sys.exit(3)       # correctly refused
"""


def test_a_second_os_process_cannot_take_the_segment_tree_lock(tmp_path):
    # A real second interpreter, holding a real kernel lock — the shape production has (an
    # overlapping restart, a human at the console) rather than a same-process stand-in.
    with single_instance_lock(tmp_path):
        held = subprocess.run([sys.executable, "-c", _TAKE_THE_LOCK, str(tmp_path)], capture_output=True)
    assert held.returncode == 3, held.stderr.decode()

    # ... and the lock dies with the holder: nothing to clean up after a SIGKILL, no stale lockfile
    # to explain to a human at 3am.
    freed = subprocess.run([sys.executable, "-c", _TAKE_THE_LOCK, str(tmp_path)], capture_output=True)
    assert freed.returncode == 0, freed.stderr.decode()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the directory's write bit")
def test_an_unwritable_data_dir_does_not_crash_loop_the_daemon(tmp_path):
    # The lock must not re-create the crash loop the `.tmp` cleanup guard just removed. On a
    # read-only remount — the aftermath of the very ENOSPC condition DiskWatermark exists for — the
    # lockfile cannot be created; under `restart: always` a raise there loops the daemon forever on
    # exactly the failure we most need it to survive and REPORT. An unwritable disk has nothing to
    # corrupt, so the lock is skipped, loudly, and the daemon runs (its writes fail loudly too).
    tmp_path.chmod(0o500)
    try:
        with single_instance_lock(tmp_path):  # must not raise
            pass
    finally:
        tmp_path.chmod(0o700)


def test_a_lock_failure_that_is_not_contention_is_not_reported_as_contention(tmp_path, monkeypatch):
    # Only EWOULDBLOCK means "someone else holds it". Reporting ENOLCK / EOPNOTSUPP (a mount without
    # flock support) as "another capture process is already writing" would send a human hunting a
    # process that does not exist — and refuse to start over a filesystem quirk.
    def _no_locks(fd, op):
        raise OSError(37, "No locks available")  # ENOLCK

    monkeypatch.setattr("cli.capture.command.fcntl.flock", _no_locks)
    with single_instance_lock(tmp_path):  # must not raise, must not claim contention
        pass


def test_capture_refuses_to_start_beside_another_writer(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.capture.command.CaptureClient", _FakeClient)
    with single_instance_lock(tmp_path):
        result = runner.invoke(app, ["capture", "--pairs", "BTC/EUR", "--data-dir", str(tmp_path), "--duration", "1"])
    assert result.exit_code != 0
    assert isinstance(result.exception, CaptureError)
    assert "already writing" in str(result.exception)
    assert not list(tmp_path.rglob("*.parquet"))  # and it wrote nothing on its way out
