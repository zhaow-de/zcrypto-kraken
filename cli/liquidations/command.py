from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from pathlib import Path
from typing import Optional

import typer

from cli.capture.command import single_instance_lock
from cli.capture.gap_monitor import DiskWatermark, ping_healthcheck
from cli.liquidations.recorder import LiquidationRecorder, run_recorder
from cli.liquidations.ws_client import DEFAULT_URI, BinanceLiquidationClient
from cli.logging import get_logger

logger = get_logger("liquidations.command")

DEFAULT_DATA_DIR = Path("/var/lib/zcrypto-ops/liquidations")
DATA_DIR_ENV_VAR = "ZCRYPTO_LIQUIDATIONS_DATA_DIR"
HEALTHCHECK_ENV_VAR = "LIQUIDATIONS_HEALTHCHECK_URL"
HEALTHCHECK_INTERVAL_SECONDS = 60
DISK_WATERMARK_INTERVAL_SECONDS = 30


async def _healthcheck_loop(url: str | None, client: BinanceLiquidationClient, interval: int, watermark: DiskWatermark) -> None:
    while True:
        await asyncio.sleep(interval)
        # Dead-man's-switch, reduced from capture's gate: a liquidations feed has no book/checksum
        # gap concept, so the `monitor.is_healthy` term is dropped — the only "gap" is a reconnect
        # window, already covered by `client.connected`. `not watermark.breached` (writes stop on a
        # breach) and `watermark.measurable` (a failing disk probe is not "healthy") are load-bearing
        # exactly as in capture (T0032): both must hold or the ping is withheld and the breach pages.
        if client.connected and not watermark.breached and watermark.measurable:
            ping_healthcheck(url)


async def _disk_watermark_loop(watermark: DiskWatermark, interval: int) -> None:
    while True:
        try:
            watermark.check()
        except Exception:
            # check() reads the filesystem (a flaky mount raises OSError); this task is awaited by
            # nothing until shutdown, so an escaping exception would silently freeze `breached` and
            # let the dead-man ping green through a later real breach. Log and keep polling.
            logger.exception("disk watermark check failed — retrying in %ss", interval)
        await asyncio.sleep(interval)


async def _run(data_dir: Path, duration: int | None, healthcheck_url: str | None, uri: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)  # disk_usage() (DiskWatermark) requires the path to exist
    recorder = LiquidationRecorder(data_dir)
    watermark = DiskWatermark(data_dir)
    client = BinanceLiquidationClient(uri)

    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()
    if main_task is not None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, main_task.cancel)

    consumer = asyncio.create_task(run_recorder(client, recorder, watermark))
    health = asyncio.create_task(_healthcheck_loop(healthcheck_url, client, HEALTHCHECK_INTERVAL_SECONDS, watermark))
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
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                # A task that DIED earlier re-raises its corpse's exception here (already surfaced,
                # or about to be, by the try block's re-raise). Letting it escape would skip
                # recorder.close() below, losing every writer's buffered rows on top of the failure.
                logger.exception("background task failed during shutdown")
        recorder.close()


def liquidations(
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
    """Stream Binance USD-M futures forceOrder (liquidation) events to hourly zstd-Parquet segments.

    NOT DEPLOYED: Binance geo-fences its futures WebSocket from our network egresses, so this
    cannot reach the feed from the fleet. The deployed liquidations source is `liquidations-poll`.
    Kept tested and portable in case a served egress appears.
    """
    resolved_data_dir = data_dir or Path(os.environ.get(DATA_DIR_ENV_VAR, str(DEFAULT_DATA_DIR)))
    healthcheck_url = os.environ.get(HEALTHCHECK_ENV_VAR)

    logger.info("starting liquidations recorder data_dir=%s duration=%s", resolved_data_dir, duration)
    # Same reason as capture (T0023): two writers racing the same SegmentWriter part sequence
    # silently clobber each other's parts and shred unbackfillable rows.
    with single_instance_lock(resolved_data_dir):
        asyncio.run(_run(resolved_data_dir, duration, healthcheck_url, DEFAULT_URI))
