import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.book import OrderBook
from cli.capture.command import _default_pairs, _parse_ts
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
    # the rows are on disk as parts, and the hour is finalized by the next process to come up.
    assert not book_path.exists()
    assert list(book_path.parent.glob("14.part*.parquet"))
    SegmentWriter(data_dir, "BTC/EUR", "book", BOOK_SCHEMA)
    SegmentWriter(data_dir, "BTC/EUR", "trades", TRADE_SCHEMA)

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
