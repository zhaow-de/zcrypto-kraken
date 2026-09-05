from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cli.capture.gap_monitor import DiskWatermark
from cli.capture.segment_writer import LIQ_SCHEMA, SegmentWriter
from cli.logging import get_logger

if TYPE_CHECKING:
    # Imported lazily to avoid a cycle: `ws_client` imports `parse_force_order` from this module.
    from cli.liquidations.ws_client import BinanceLiquidationClient

logger = get_logger("liquidations.recorder")


def _epoch_ms_to_utc(ms: int) -> datetime:
    """Binance `o.T` (trade time; `E` is the event time) as the tz-aware UTC microsecond `datetime` `SegmentWriter` rotates on."""
    seconds, millis = divmod(ms, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=millis * 1000)


def parse_force_order(raw: str) -> dict | None:
    """Parse one Binance combined-stream frame — or a bare one with `e` at the top level — into a `LIQ_SCHEMA` row dict, or `None`.

    Never raises: a non-`forceOrder` frame or a malformed line yields `None`, which `BinanceLiquidationClient.stream` skips.
    `event_id` is built from the raw wire strings for price/qty, so a redelivery reproduces it exactly."""
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError, TypeError:
        return None
    if not isinstance(envelope, dict):
        return None
    data = envelope.get("data", envelope)
    if not isinstance(data, dict) or data.get("e") != "forceOrder":
        return None
    order = data.get("o")
    if not isinstance(order, dict):
        return None
    try:
        symbol = order["s"]
        price = order["p"]
        orig_qty = order["q"]
        trade_time_ms = order["T"]
        return {
            "ts": _epoch_ms_to_utc(int(trade_time_ms)),
            "symbol": str(symbol),
            "side": str(order["S"]),
            "price": float(price),
            "orig_qty": float(orig_qty),
            "avg_price": float(order["ap"]) if order.get("ap") is not None else None,
            # str() is load-bearing: a structured value would pass this parser untouched and then raise
            # in polars' Utf8 column at flush -- downstream of the "never raises" guarantee.
            "order_status": str(order["X"]) if order.get("X") is not None else None,
            "event_id": f"{symbol}-{trade_time_ms}-{price}-{orig_qty}",
        }
    except Exception:
        # Untrusted wire data: any conversion failure means "not a usable row", never a crash -- this parser
        # never raises. `except Exception` spares BaseException, so an interrupt still propagates as the stop signal.
        return None


class LiquidationRecorder:
    """Routes parsed forceOrder rows to a per-symbol `SegmentWriter`, created lazily.

    `!forceOrder@arr` carries every symbol, so no pair list exists up front; a single feed has no sibling stream to corroborate an
    hour boundary, so `oracle` stays unset and rotation trusts each event's own `ts`; `dedup_key="event_id"` drops redeliveries."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._writers: dict[str, SegmentWriter] = {}

    def append(self, row: dict) -> None:
        symbol = row["symbol"]
        writer = self._writers.get(symbol)
        if writer is None:
            writer = SegmentWriter(self._data_dir, symbol, "liquidations", LIQ_SCHEMA, dedup_key="event_id")
            self._writers[symbol] = writer
        writer.append(row)

    def close(self) -> None:
        """Flush every open writer (idempotent); like `SegmentWriter.close`, leaves the open hour unfinalized."""
        for writer in self._writers.values():
            writer.close()


async def run_recorder(client: "BinanceLiquidationClient", recorder: LiquidationRecorder, watermark: DiskWatermark) -> None:
    """Consume parsed forceOrder rows from `client.stream()` into `recorder`, until cancelled.

    A disk-watermark breach drops the row rather than write to a disk that may be about to error."""
    async for row in client.stream():
        if watermark.breached:
            continue
        recorder.append(row)
