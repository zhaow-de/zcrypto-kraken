from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer

from cli.capture.book import OrderBook
from cli.capture.errors import CaptureError
from cli.capture.gap_monitor import DiskWatermark, GapMonitor, ping_healthcheck
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA, SegmentWriter
from cli.capture.ws_client import ALLOWED_DEPTHS, CaptureClient, classify
from cli.config import load_config
from cli.logging import get_logger

logger = get_logger("capture.command")

DEFAULT_DEPTH = 100
DEFAULT_DATA_DIR = Path("/var/lib/zcrypto-capture/segments")
DATA_DIR_ENV_VAR = "ZCRYPTO_CAPTURE_DATA_DIR"
HEALTHCHECK_ENV_VAR = "HEALTHCHECK_URL"
HEALTHCHECK_INTERVAL_SECONDS = 60
DISK_WATERMARK_INTERVAL_SECONDS = 30
UNIVERSE_RELATIVE_PATH = Path("universe") / "point-in-time-universe.json"


def _default_pairs(universe_path: Path) -> list[str]:
    """The EUR-majors default: the EUR-quoted symbols from the point-in-time universe file's
    `selected` list (the ~10 EUR majors — master-plan §3 / T0003 design)."""
    if not universe_path.exists():
        raise CaptureError(
            f"no point-in-time universe file at {universe_path} to derive default pairs from — pass --pairs explicitly"
        )
    try:
        selected = json.loads(universe_path.read_text())["selected"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CaptureError(f"{universe_path} is not a valid point-in-time universe file: {exc}") from exc
    return [symbol for symbol in selected if symbol.endswith("/EUR")]


def _parse_ts(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CaptureError(f"unparseable timestamp from Kraken WS: {raw!r}") from exc


async def _handle_book_message(
    msg: dict,
    category: str,
    client: CaptureClient,
    books: dict[str, OrderBook],
    book_writers: dict[str, SegmentWriter],
    monitor: GapMonitor,
    watermark: DiskWatermark,
) -> None:
    for entry in msg.get("data", []):
        pair = entry["symbol"]
        book = books.get(pair)
        if book is None:
            continue  # a pair we didn't subscribe to; ignore defensively

        was_desynced = book.desynced
        in_sync = book.ingest_snapshot(entry) if category == "book_snapshot" else book.ingest_update(entry)
        now = datetime.now(UTC)
        if not in_sync:
            # Resubscribe (and open a gap) ONCE, on the transition into desync — NOT on every
            # subsequent out-of-sync update. Otherwise a single desync fires a resubscribe on
            # every following update (hundreds/sec at depth-100), which trips Kraken's subscribe
            # rate limit ("Exceeded msg rate") so the pair can never resync — a self-inflicted
            # cascade. While desynced, we simply wait for the resubscribe's fresh snapshot.
            if not was_desynced:
                monitor.start_gap(pair, "checksum_resync", at=now)
                logger.warning("checksum desync pair=%s - resubscribing", pair)
                await client.resubscribe_book(pair)
        elif was_desynced:
            monitor.end_gap(pair, at=now)

        if watermark.breached:
            continue
        writer = book_writers.get(pair)
        if writer is None:
            continue
        ts = _parse_ts(entry["timestamp"])
        row_type = "snapshot" if category == "book_snapshot" else "update"
        for side_name, levels in (("bid", entry.get("bids", [])), ("ask", entry.get("asks", []))):
            for level in levels:
                writer.append(
                    {
                        "ts": ts,
                        "symbol": pair,
                        "type": row_type,
                        "side": side_name,
                        "price": float(level["price"]),
                        "qty": float(level["qty"]),
                        "checksum": int(entry["checksum"]),
                    }
                )


def _handle_trade_message(msg: dict, trade_writers: dict[str, SegmentWriter], watermark: DiskWatermark) -> None:
    if watermark.breached:
        return
    for trade in msg.get("data", []):
        pair = trade["symbol"]
        writer = trade_writers.get(pair)
        if writer is None:
            continue
        writer.append(
            {
                "ts": _parse_ts(trade["timestamp"]),
                "symbol": pair,
                "side": trade["side"],
                "price": float(trade["price"]),
                "qty": float(trade["qty"]),
                "ord_type": trade["ord_type"],
                "trade_id": int(trade["trade_id"]),
            }
        )


async def _consume(
    client: CaptureClient,
    books: dict[str, OrderBook],
    book_writers: dict[str, SegmentWriter],
    trade_writers: dict[str, SegmentWriter],
    monitor: GapMonitor,
    watermark: DiskWatermark,
) -> None:
    async for msg in client.stream():
        category = classify(msg)
        if category in ("book_snapshot", "book_update"):
            await _handle_book_message(msg, category, client, books, book_writers, monitor, watermark)
        elif category in ("trade_snapshot", "trade_update"):
            _handle_trade_message(msg, trade_writers, watermark)
        elif category == "subscribe_error":
            logger.error("subscribe error: %s", msg)
        elif category == "unsubscribe_error":
            # the resubscribe recovery's unsubscribe leg was rejected — surface it, since a silently
            # rejected request is exactly what made the desync incident undiagnosable
            logger.error("unsubscribe error: %s", msg)
        # heartbeat / subscribe_ack / unsubscribe_ack / other -> nothing to do


async def _healthcheck_loop(
    url: str | None,
    client: CaptureClient,
    monitor: GapMonitor,
    pairs: list[str],
    interval: int,
    watermark: DiskWatermark,
) -> None:
    while True:
        await asyncio.sleep(interval)
        # Dead-man's-switch: ping only while the WS is actually connected AND books are healthy, so
        # a connectivity loss (stuck in reconnect/backoff, no book updates flowing) stops the ping
        # and healthchecks.io alerts — not just checksum desyncs.
        #
        # `not watermark.breached` is load-bearing (T0032): on a breach the message handlers return
        # early and the daemon writes NOTHING, yet the WS stays connected and no gap opens — so
        # without this term the dead-man would keep reporting GREEN while the unbackfillable L2
        # stream is silently lost. Withholding the ping is what turns a silent death into a page.
        if client.connected and monitor.is_healthy(pairs) and not watermark.breached:
            ping_healthcheck(url)


async def _disk_watermark_loop(watermark: DiskWatermark, interval: int) -> None:
    while True:
        watermark.check()
        await asyncio.sleep(interval)


async def _run(pairs: list[str], depth: int, data_dir: Path, duration: int | None, healthcheck_url: str | None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)  # disk_usage() (DiskWatermark) requires the path to exist
    books = {pair: OrderBook(pair) for pair in pairs}
    book_writers = {pair: SegmentWriter(data_dir, pair, "book", BOOK_SCHEMA) for pair in pairs}
    trade_writers = {pair: SegmentWriter(data_dir, pair, "trades", TRADE_SCHEMA) for pair in pairs}
    monitor = GapMonitor()
    watermark = DiskWatermark(data_dir)
    client = CaptureClient(pairs, depth)

    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()
    if main_task is not None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, main_task.cancel)

    consumer = asyncio.create_task(_consume(client, books, book_writers, trade_writers, monitor, watermark))
    health = asyncio.create_task(
        _healthcheck_loop(healthcheck_url, client, monitor, pairs, HEALTHCHECK_INTERVAL_SECONDS, watermark)
    )
    disk_check = asyncio.create_task(_disk_watermark_loop(watermark, DISK_WATERMARK_INTERVAL_SECONDS))

    try:
        if duration is not None:
            await asyncio.wait({consumer}, timeout=duration)
            if consumer.done():
                consumer.result()  # re-raise if the consumer crashed instead of just timing out
        else:
            await consumer
    except asyncio.CancelledError:
        pass
    finally:
        for task in (consumer, health, disk_check):
            task.cancel()
        for task in (consumer, health, disk_check):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for writer in (*book_writers.values(), *trade_writers.values()):
            writer.close()


def capture(
    pairs: Optional[list[str]] = typer.Option(
        None,
        "--pairs",
        help="Pair(s) to capture, e.g. --pairs BTC/EUR --pairs ETH/EUR. Defaults to the EUR majors "
        "from data/universe/point-in-time-universe.json.",
    ),
    depth: int = typer.Option(DEFAULT_DEPTH, "--depth", help=f"Order book depth. One of {ALLOWED_DEPTHS}."),
    data_dir: Optional[Path] = typer.Option(
        None,
        "--data-dir",
        help=f"Segment output base directory. Defaults to ${DATA_DIR_ENV_VAR} if set, else {DEFAULT_DATA_DIR}.",
    ),
    duration: Optional[int] = typer.Option(
        None,
        "--duration",
        help="Run for this many seconds then stop cleanly (for smoke-testing); omit to run until interrupted.",
    ),
) -> None:
    """Stream Kraken's public WS v2 book + trade feed for the universe pairs to hourly zstd-Parquet segments."""
    cfg = load_config()
    resolved_pairs = pairs or _default_pairs((cfg.data_dir or Path("data")) / UNIVERSE_RELATIVE_PATH)
    resolved_data_dir = data_dir or Path(os.environ.get(DATA_DIR_ENV_VAR, str(DEFAULT_DATA_DIR)))
    healthcheck_url = os.environ.get(HEALTHCHECK_ENV_VAR)

    logger.info(
        "starting capture pairs=%s depth=%d data_dir=%s duration=%s",
        resolved_pairs,
        depth,
        resolved_data_dir,
        duration,
    )
    asyncio.run(_run(resolved_pairs, depth, resolved_data_dir, duration, healthcheck_url))
