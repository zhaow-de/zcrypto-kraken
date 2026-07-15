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
    """Binance `o.T` (transaction/trade time, epoch milliseconds — `E` is the event time) -> a
    tz-aware UTC microsecond `datetime`, the form `SegmentWriter` requires for hour rotation."""
    seconds, millis = divmod(ms, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=millis * 1000)


def parse_force_order(raw: str) -> dict | None:
    """Parse one Binance combined-stream frame into a `LIQ_SCHEMA` row dict, or `None`.

    Returns `None` — never raises — for a non-`forceOrder` frame (heartbeat, other event types) or a
    malformed line, so the recorder loop can skip it. The combined-stream envelope is
    `{"stream": ..., "data": {"e": "forceOrder", "o": {...}}}`; a bare (uncombined) frame with `e`
    at the top level is tolerated too. `event_id` uses the raw wire strings for price/qty so it is
    exactly reproducible on a redelivery (`f"{o.s}-{o.T}-{o.p}-{o.q}"`)."""
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
            # str() coercion is load-bearing: a structured value (dict/list) would pass this parser
            # untouched and then blow up polars' Utf8 column at SegmentWriter flush -- downstream of
            # the "never raises" guarantee. str() stringifies anything harmlessly.
            "order_status": str(order["X"]) if order.get("X") is not None else None,
            "event_id": f"{symbol}-{trade_time_ms}-{price}-{orig_qty}",
        }
    except Exception:
        # Untrusted wire data: any conversion failure (missing/garbage core field, an out-of-range
        # `T` overflowing int()/datetime.fromtimestamp()) means "not a usable row", never a crash --
        # this is a "never raises" parser. `except Exception` deliberately excludes
        # KeyboardInterrupt/CancelledError (BaseException), so those still propagate as stop signals.
        return None


class LiquidationRecorder:
    """Routes parsed forceOrder rows to a per-symbol `SegmentWriter`, created lazily.

    The `!forceOrder@arr` combined stream carries every symbol, so unlike Kraken capture there is no
    fixed pair list up front — a writer is minted the first time a symbol is seen. `oracle=None`: a
    single Binance feed has no cross-stream sibling to corroborate an hour boundary, so rotation
    trusts each event's own `ts` (still protected by `SegmentWriter`'s implausible-ts guards).
    `dedup_key="event_id"` drops Binance's on-reconnect redeliveries.
    """

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
        """Flush every open writer (idempotent). Like `SegmentWriter.close`, does not finalize the
        open hour — the next process's sweep does, on its first event."""
        for writer in self._writers.values():
            writer.close()


async def run_recorder(client: "BinanceLiquidationClient", recorder: LiquidationRecorder, watermark: DiskWatermark) -> None:
    """Consume parsed forceOrder rows from `client.stream()` into `recorder`, until cancelled.

    On a disk-watermark breach we stop appending (matching capture): the row is dropped rather than
    written to a disk that may be about to error, and the dead-man gate withholds its ping so the
    breach pages."""
    async for row in client.stream():
        if watermark.breached:
            continue
        recorder.append(row)
