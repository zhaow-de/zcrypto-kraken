"""Coinalyze REST liquidation-history poller (`zcrypto liquidations-poll`, spec 00051 OPS-2): the
T0023 fallback for the shelved Binance forceOrder WS recorder (`cli.liquidations.recorder`), which
Binance geo-fences from every egress we own. Polls the documented `/v1/liquidation-history` endpoint
every `COINALYZE_POLL_SECONDS` for the funding basket's 10 USDT perps, ingesting only 1-min buckets
Coinalyze has PROVEN closed (see `poll_cycle`), and writes them through the same `SegmentWriter` the
recorder uses -- one writer per coin, `kind="liquidations-1m"` -- so the existing NAS replication
channel and dead-man wiring (same data dir) carry over unchanged.

Overlap-safety invariant (do not "optimize" away): each cycle still re-fetches the whole 30 h
catch-up window, and THREE mechanisms keep the overlap safe. First, a per-coin bucket watermark
(primed from the on-disk segment tree at startup, advanced in memory on each submit) filters
re-submissions at source, before they ever reach a writer. Second and third, the writer's own
defenses remain intact behind it: SegmentWriter's dedup (`_seen`) covers the currently-OPEN hour,
and re-submissions into already-FINALIZED hours are dropped by the writer's late-event floor
(`_current_hour`/`_floor` in `cli/capture/segment_writer.py`). Narrowing the window or touching
the floor logic must preserve all of this -- and a `dropping replayed event` warning that still
fires is now a genuine anomaly, not steady-state noise.
"""

from __future__ import annotations

import json
import os
import re
import signal
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import polars as pl
import typer

from cli.capture.command import single_instance_lock
from cli.capture.gap_monitor import DiskWatermark, ping_healthcheck
from cli.capture.segment_writer import LIQ_AGG_SCHEMA, SegmentWriter
from cli.liquidations.errors import LiquidationsError
from cli.logging import get_logger

logger = get_logger("liquidations.coinalyze")

# The funding-basket's 10 Binance USDT perps (spec 00051 OPS-2 decision, 2026-07-15) -- the coins
# the poller's writer set covers, one `SegmentWriter` each.
COINS = ["BTC", "ETH", "SOL", "ADA", "XRP", "LTC", "LINK", "DOT", "AVAX", "DOGE"]

_BASE_URL = "https://api.coinalyze.net/v1/liquidation-history"
_TIMEOUT_SECONDS = 15

_BUCKET_SECONDS = 60  # Coinalyze's fixed bucket width (interval=1min)
# Load-bearing (verified live 2026-07-15, stable over 150s): SegmentWriter's dedup keeps the FIRST
# row per event_id, so ingesting a bucket before Coinalyze has finished aggregating it would
# permanently lock in a possibly-incomplete l/s pair -- this poller's overlapping 24h re-poll would
# never revisit it once dedup has seen the key. A bucket is proven closed once
# `t + _BUCKET_SECONDS <= now - _CLOSE_MARGIN_SECONDS`.
_CLOSE_MARGIN_SECONDS = 120
# Each cycle re-requests the last 30h regardless of when it last succeeded: Coinalyze's own history
# purges to ~25-33h, so anything older is unreachable anyway. The per-coin bucket watermark IS
# deliberate cross-cycle in-memory state (spec 00055): it filters re-submissions at source, but it
# is advisory (fail-open) and never durable -- losing it only costs one window of re-submissions,
# absorbed by SegmentWriter's dedup/floor.
# Coinalyze retains 1500-2000 one-minute bars (~25-33 h); requesting a window wider than what it
# still holds is harmless (it returns what exists), so 30 h maximizes post-outage catch-up without
# ever asking for provably-purged data.
_CATCHUP_WINDOW_SECONDS = 30 * 3600

# T0046: most of the funding basket's symbols liquidate rarely, so `SegmentWriter`'s event-driven
# rotation (an hour closes only when the NEXT event for that symbol crosses its boundary) can leave
# an hour open -- unmanifested, sitting in RAM or as unmerged parts -- indefinitely. Each cycle
# below calls `SegmentWriter.finalize_completed_hours(now - _FINALIZE_LAG)` per writer to close
# The lag MUST exceed _CATCHUP_WINDOW_SECONDS: poll_cycle only ever requests [now-30h, now],
# so a 31h-old hour can never be re-fetched REGARDLESS of Coinalyze's ~25-33h retention --
# finalizing it forecloses nothing recoverable, and the >=1h margin stays monotone across cycles.
# ~25-33h retention): finalizing an hour any earlier would drop a post-outage re-fetch of it below
# the writer's late-event floor -- silently discarding data that was still recoverable. At 31h
# nothing recoverable remains, so finalization forecloses nothing; sparse-symbol manifests thus
# appear at most ~31h late instead of never.
_FINALIZE_LAG_SECONDS = 31 * 3600

DEFAULT_DATA_DIR = Path("/var/lib/zcrypto-ops/liquidations")
DATA_DIR_ENV_VAR = "ZCRYPTO_LIQUIDATIONS_DATA_DIR"
HEALTHCHECK_ENV_VAR = "LIQUIDATIONS_HEALTHCHECK_URL"
API_KEY_ENV_VAR = "COINALYZE_API_KEY"
POLL_SECONDS_ENV_VAR = "COINALYZE_POLL_SECONDS"
DEFAULT_POLL_SECONDS = 300

_sleep = time.sleep  # module-level so tests can stub the poll wait

# Matches exactly the files SegmentWriter persists rows in: hour finals and parts. Sidecars
# (.sha256), .merging, .tmp and .corrupt names do not end in ".parquet" so rglob skips them.
_SEGMENT_FILE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/(\d{2})\.(?:parquet|part\d{4}\.parquet)$")


def prime_bucket_watermarks(data_dir: Path, coins: list[str]) -> dict[str, int]:
    """Newest persisted bucket start (epoch s) per coin, read from the segment tree at startup.

    Fail-open per coin: a coin with no (readable) data is simply absent, so its whole catch-up
    window re-submits once and the writer's dedup/floor absorb it -- exactly the pre-watermark
    behavior, once.
    """
    marks: dict[str, int] = {}
    for coin in coins:
        by_hour: dict[tuple[str, ...], list[Path]] = {}
        for path in (data_dir / coin / "liquidations-1m").rglob("*.parquet"):
            m = _SEGMENT_FILE_RE.search(path.as_posix())
            if m is not None:
                by_hour.setdefault(m.groups(), []).append(path)
        if not by_hour:
            continue
        try:
            ts = pl.scan_parquet(by_hour[max(by_hour)]).select(pl.col("ts").max()).collect().item()
        except Exception:
            logger.warning("bucket-watermark priming failed for %s -- its full window will re-submit once", coin)
            continue
        if ts is not None:
            marks[coin] = int(ts.timestamp())
    return marks


def symbol_for(coin: str) -> str:
    """`"BTC"` -> `"BTCUSDT_PERP.A"` -- Coinalyze's symbol for the coin's Binance USDT perp."""
    return f"{coin}USDT_PERP.A"


def fetch_liquidation_history(api_key: str, symbols: list[str], frm: int, to: int, *, opener=urllib.request.urlopen) -> list[dict]:
    """GET Coinalyze's `/v1/liquidation-history` for `symbols` (one batched call) over `[frm, to]`
    (unix seconds, inclusive on both ends). Returns the parsed `[{"symbol", "history": [...]}]`
    list. Raises `LiquidationsError` on a transport/HTTP failure, malformed JSON, or a non-list
    response body -- nothing is ever returned unless the whole fetch succeeds.

    The API key travels as the `api_key` header (never the URL, and never logged) via a `Request`
    object -- plain `urlopen(url, timeout=...)` has no way to attach headers. `urllib` capitalizes
    the header name it stores (`Api_key`); harmless, since HTTP header names are case-insensitive
    on the wire.
    """
    symbols_csv = ",".join(symbols)
    url = f"{_BASE_URL}?symbols={symbols_csv}&interval=1min&from={frm}&to={to}&convert_to_usd=true"
    request = urllib.request.Request(url, headers={"api_key": api_key})
    try:
        with opener(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError) as exc:
        raise LiquidationsError(f"transport error fetching Coinalyze liquidation-history: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LiquidationsError(f"invalid JSON from Coinalyze liquidation-history: {exc}") from exc
    if not isinstance(payload, list):
        raise LiquidationsError(f"malformed Coinalyze liquidation-history response (expected a list): {payload!r}")
    return payload


def poll_cycle(
    api_key: str,
    coins: list[str],
    writers: dict[str, SegmentWriter],
    *,
    watermarks: dict[str, int] | None = None,
    now: datetime | None = None,
    opener=urllib.request.urlopen,
) -> int:
    """One poll cycle: fetch `coins`' batched Coinalyze symbols over the last 30h and append every
    PROVEN-closed 1-min bucket to its coin's writer. Returns the number of rows submitted to a
    writer (SegmentWriter's own `dedup_key` -- not this count -- is what absorbs a re-polled
    overlapping window; see the module docstring).

    `watermarks` (coin -> newest submitted bucket start, epoch s) filters re-submissions at source:
    a proven-closed bucket at or below its coin's mark is skipped before the writer, and the dict is
    mutated in place -- a coin's mark advances only on a successful `writer.append`. `None` (the
    default) disables filtering entirely, reproducing the pre-watermark behavior.

    Raises `LiquidationsError` (propagated from `fetch_liquidation_history`) on any fetch failure,
    BEFORE a single row is appended -- a failed cycle writes nothing, and the caller's next cycle
    simply retries (the 30h re-fetch window covers the gap). A response entry naming a symbol with
    no corresponding writer is skipped defensively, never fatal.
    """
    now = now or datetime.now(UTC)
    now_s = int(now.timestamp())
    frm = now_s - _CATCHUP_WINDOW_SECONDS
    symbol_to_coin = {symbol_for(coin): coin for coin in coins}

    payload = fetch_liquidation_history(api_key, list(symbol_to_coin), frm, now_s, opener=opener)

    cutoff = now_s - _CLOSE_MARGIN_SECONDS
    written = 0
    skipped = 0
    for entry in payload:
        coin = symbol_to_coin.get(entry.get("symbol"))
        writer = writers.get(coin) if coin is not None else None
        if writer is None:
            continue
        symbol = entry["symbol"]
        # Sorted defensively: the finalization walk below ratchets SegmentWriter's hour forward, so a
        # non-ascending response would permanently drop earlier-hour buckets as "late events" on every
        # cycle. The live probe saw ascending order, but nothing in the docs promises it.
        for bucket in sorted(entry.get("history", []), key=lambda b: b["t"]):
            t = bucket["t"]
            if t + _BUCKET_SECONDS > cutoff:
                continue  # not yet proven closed -- a later cycle will pick it up
            if watermarks is not None and t <= watermarks.get(coin, -1):
                skipped += 1
                continue  # already persisted (or submitted this run) -- never reaches the writer
            writer.append(
                {
                    "ts": datetime.fromtimestamp(t, tz=UTC),
                    "symbol": symbol,
                    "long_usd": float(bucket["l"]),
                    "short_usd": float(bucket["s"]),
                    "event_id": f"{symbol}-{t}",
                }
            )
            written += 1
            if watermarks is not None:
                watermarks[coin] = max(t, watermarks.get(coin, -1))
    logger.info("poll cycle: submitted=%d skipped_at_watermark=%d closed bucket(s)", written, skipped)
    return written


def _poll_once(api_key: str, writers: dict[str, SegmentWriter], watermark: DiskWatermark) -> bool:
    """Run one cycle's watermark check + fetch/write; returns whether it fully succeeded (the
    dead-man ping's gate). A watermark probe that raises, a breach, or a `LiquidationsError` from
    `poll_cycle` are all treated the same way: log a warning, write nothing more, return False so
    the caller withholds the ping -- and the loop keeps going, retrying next cycle."""
    try:
        watermark.check()
    except Exception:
        logger.exception("disk watermark check failed -- treating this poll cycle as failed")
        return False
    if watermark.breached:
        logger.warning("disk watermark breached -- skipping poll cycle")
        return False
    try:
        poll_cycle(api_key, COINS, writers)
    except LiquidationsError as exc:
        logger.warning("Coinalyze poll cycle failed: %s", exc)
        return False
    except Exception:
        # A malformed bucket (null l/s, missing t, non-dict entry) raises TypeError/KeyError/
        # AttributeError -- not LiquidationsError. Uncaught, that escapes _run's loop and crash-loops
        # the container against the same bad response. The loop's contract is "a failed cycle is
        # retried next cycle", so ANY per-cycle failure is caught here (writers flush via close()'s
        # finally regardless; the fetch is all-or-nothing so no partial state was written).
        logger.exception("Coinalyze poll cycle failed on unexpected data -- retrying next cycle")
        return False
    # T0046: close any hour old enough that nothing recoverable can still arrive for it (see
    # _FINALIZE_LAG_SECONDS) -- the sparse-symbol writers that a genuine event never rotates.
    finalize_cutoff = datetime.now(UTC) - timedelta(seconds=_FINALIZE_LAG_SECONDS)
    for writer in writers.values():
        writer.finalize_completed_hours(finalize_cutoff)
    return True


def _run(data_dir: Path, api_key: str, poll_seconds: int, healthcheck_url: str | None, duration: int | None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)  # disk_usage() (DiskWatermark) requires the path to exist
    writers = {coin: SegmentWriter(data_dir, coin, "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id") for coin in COINS}
    watermark = DiskWatermark(data_dir)

    # SIGTERM is pointed at the same handler Python installs for SIGINT by default
    # (`signal.default_int_handler`, which raises KeyboardInterrupt). There is no asyncio event
    # loop here to hang `add_signal_handler` off of (this is a plain sync time.sleep loop, by
    # design -- no WS to await), so SIGINT's own well-tested "raise and unwind" behavior is reused
    # for SIGTERM too: per PEP 475, a syscall interrupted by a signal whose handler RAISED does not
    # auto-resume, so this interrupts a (default 300s) `time.sleep` immediately rather than waiting
    # it out. The previous handler is restored in `finally` -- this runs in-process under tests.
    previous_handler = signal.signal(signal.SIGTERM, signal.default_int_handler)
    started = time.monotonic()
    try:
        while True:
            ok = _poll_once(api_key, writers, watermark)
            if ok and not watermark.breached and watermark.measurable:
                ping_healthcheck(healthcheck_url)
            if duration is not None and time.monotonic() - started >= duration:
                break
            _sleep(poll_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        for writer in writers.values():
            writer.close()


def liquidations_poll(
    data_dir: Optional[Path] = typer.Option(
        None,
        "--data-dir",
        help=f"Segment output base directory. Defaults to ${DATA_DIR_ENV_VAR} if set, else {DEFAULT_DATA_DIR}.",
    ),
    duration: Optional[int] = typer.Option(
        None,
        "--duration",
        help="Run for this many seconds then stop cleanly (for smoke-testing; runs at least one "
        "poll cycle even with 0); omit to run until interrupted.",
    ),
) -> None:
    """Poll Coinalyze's `/v1/liquidation-history` REST endpoint every $COINALYZE_POLL_SECONDS
    (default 300s) for the funding basket's 10 USDT perps, writing closed 1-min liquidation buckets
    to per-coin zstd-Parquet segments. The T0023 fallback for the shelved Binance forceOrder WS
    recorder (`zcrypto liquidations`), which Binance geo-fences from every egress we own."""
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        logger.error("%s is required", API_KEY_ENV_VAR)
        raise typer.Exit(code=1)
    resolved_data_dir = data_dir or Path(os.environ.get(DATA_DIR_ENV_VAR, str(DEFAULT_DATA_DIR)))
    healthcheck_url = os.environ.get(HEALTHCHECK_ENV_VAR)
    poll_seconds = int(os.environ.get(POLL_SECONDS_ENV_VAR, DEFAULT_POLL_SECONDS))

    logger.info("starting liquidations-poll data_dir=%s poll_seconds=%d duration=%s", resolved_data_dir, poll_seconds, duration)
    with single_instance_lock(resolved_data_dir):
        _run(resolved_data_dir, api_key, poll_seconds, healthcheck_url, duration)
