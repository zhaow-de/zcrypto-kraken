import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from cli.capture.gap_monitor import DiskWatermark
from cli.capture.segment_writer import verify_manifest
from cli.liquidations.recorder import LiquidationRecorder, parse_force_order, run_recorder


@dataclass
class _FakeUsage:
    """Minimal stand-in for `shutil.disk_usage`'s return value — only `.free` is read."""

    free: int


def _envelope(*, symbol="BTCUSDT", side="SELL", price="9910", qty="0.014", avg="9910", status="FILLED", t_ms):
    """A real Binance combined-stream forceOrder envelope."""
    return json.dumps(
        {
            "stream": "!forceOrder@arr",
            "data": {
                "e": "forceOrder",
                "E": t_ms,
                "o": {
                    "s": symbol,
                    "S": side,
                    "o": "LIMIT",
                    "f": "IOC",
                    "q": qty,
                    "p": price,
                    "ap": avg,
                    "X": status,
                    "l": qty,
                    "z": qty,
                    "T": t_ms,
                },
            },
        }
    )


def test_parse_force_order_maps_envelope_to_row():
    t_ms = 1568014460893  # 2019-09-09T07:34:20.893Z
    row = parse_force_order(_envelope(t_ms=t_ms))
    assert row == {
        "ts": datetime(2019, 9, 9, 7, 34, 20, 893000, tzinfo=UTC),
        "symbol": "BTCUSDT",
        "side": "SELL",
        "price": 9910.0,
        "orig_qty": 0.014,
        "avg_price": 9910.0,
        "order_status": "FILLED",
        "event_id": "BTCUSDT-1568014460893-9910-0.014",
    }
    assert row["ts"].tzinfo is not None  # tz-aware UTC


def test_parse_force_order_tolerates_missing_avg_price_and_status():
    # `ap`/`S` and `X` are secondary fields; a forceOrder missing them still carries the required
    # identity fields (s/S/p/q/T), so it must still yield a row (with the secondary fields None)
    # rather than the whole non-backfillable liquidation being discarded.
    raw = json.dumps(
        {
            "stream": "!forceOrder@arr",
            "data": {
                "e": "forceOrder",
                "o": {"s": "BTCUSDT", "S": "SELL", "q": "0.014", "p": "9910", "T": 1568014460893},
            },
        }
    )
    row = parse_force_order(raw)
    assert row is not None
    assert row["avg_price"] is None
    assert row["order_status"] is None


def test_parse_force_order_returns_none_for_non_force_order():
    # A different event type on the same combined stream envelope.
    assert parse_force_order(json.dumps({"stream": "x", "data": {"e": "aggTrade", "o": {}}})) is None


def test_parse_force_order_returns_none_and_never_raises_on_garbage():
    for bad in [
        "not json",
        "",
        "null",
        "123",
        json.dumps({"data": {"e": "forceOrder"}}),
        json.dumps({"data": {"e": "forceOrder", "o": {"s": "BTCUSDT"}}}),
        # `T: Infinity` -- json.loads parses the `Infinity` literal to float('inf'); int(float('inf'))
        # raises OverflowError, which the old `except KeyError, TypeError, ValueError` did not catch.
        '{"stream":"x","data":{"e":"forceOrder","o":{"s":"BTCUSDT","S":"SELL","p":"1","q":"1","ap":"1","X":"FILLED","T":Infinity}}}',
        # A huge out-of-range integer `T` survives `int()` (Python bigints) but blows up
        # `datetime.fromtimestamp` with OverflowError/OSError depending on platform.
        json.dumps(
            {
                "data": {
                    "e": "forceOrder",
                    "o": {
                        "s": "BTCUSDT",
                        "S": "SELL",
                        "p": "1",
                        "q": "1",
                        "ap": "1",
                        "X": "FILLED",
                        "T": 99999999999999999999999,
                    },
                }
            }
        ),
    ]:
        assert parse_force_order(bad) is None


class _FakeStreamClient:
    """Yields a fixed list of already-parsed rows then completes (no reconnect loop)."""

    def __init__(self, rows):
        self._rows = rows
        self.connected = True

    async def stream(self):
        for row in self._rows:
            yield row


def test_recorder_writes_hour_finals_dedups_and_flushes_on_close(tmp_path):
    # Five events spanning three UTC hours (06/07/08) on 2019-09-09, with one redelivered 06 event.
    r1 = parse_force_order(_envelope(price="100", qty="1", t_ms=1568008800000))  # 06:00:00
    r2 = parse_force_order(_envelope(price="101", qty="2", t_ms=1568009400000))  # 06:10:00
    r3 = parse_force_order(_envelope(price="100", qty="1", t_ms=1568008800000))  # redeliver of r1
    r4 = parse_force_order(_envelope(price="102", qty="3", t_ms=1568012400000))  # 07:00:00
    r5 = parse_force_order(_envelope(price="103", qty="4", t_ms=1568016000000))  # 08:00:00
    assert r3["event_id"] == r1["event_id"]

    client = _FakeStreamClient([r1, r2, r3, r4, r5])
    recorder = LiquidationRecorder(tmp_path)
    watermark = DiskWatermark(tmp_path)  # never checked -> not breached

    asyncio.run(run_recorder(client, recorder, watermark))
    recorder.close()

    base = tmp_path / "BTCUSDT" / "liquidations" / "2019" / "09" / "09"
    final_06 = base / "06.parquet"
    final_07 = base / "07.parquet"

    # Hour 06 finalized when the 07:00 event crossed the boundary; hour 07 when 08:00 crossed.
    assert final_06.exists()
    assert final_07.exists()
    assert verify_manifest(final_06) is True
    assert verify_manifest(final_07) is True

    # Dedup: the redelivered 06 event (r3) was dropped, so hour 06 holds only r1 + r2.
    df06 = pl.read_parquet(final_06)
    assert df06.height == 2
    assert sorted(df06["event_id"].to_list()) == sorted([r1["event_id"], r2["event_id"]])

    # Shutdown flushed hour 08's buffered event to a part, but close() does NOT finalize the open hour.
    assert not (base / "08.parquet").exists()
    assert list(base.glob("08.part*.parquet"))


def test_run_recorder_skips_rows_while_disk_watermark_is_breached(tmp_path):
    row = parse_force_order(_envelope(price="100", qty="1", t_ms=1568008800000))
    client = _FakeStreamClient([row])
    recorder = LiquidationRecorder(tmp_path)

    watermark = DiskWatermark(tmp_path, min_free_bytes=1000, usage_fn=lambda p: _FakeUsage(free=0))
    watermark.check()  # forces a breach (0 free < 1000 min_free_bytes)
    assert watermark.breached is True

    asyncio.run(run_recorder(client, recorder, watermark))
    recorder.close()

    # The row was skipped by the write gate: no segment/part file for BTCUSDT anywhere under tmp_path.
    assert not list(tmp_path.rglob("*.parquet"))
