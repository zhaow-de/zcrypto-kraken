from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import re
import signal
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import typer
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric

from cli.capture.book import OrderBook
from cli.capture.desync_recovery import Action, DesyncRecovery
from cli.capture.errors import CaptureError
from cli.capture.gap_monitor import DiskWatermark, GapMonitor, ping_healthcheck
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA, HourOracle, SegmentWriter
from cli.capture.ws_client import ALLOWED_DEPTHS, CaptureClient, classify
from cli.config import load_config
from cli.logging import get_logger
from cli.obs.metrics import build_registry, metrics_port_from_env, start_metrics_server

logger = get_logger("capture.command")

DEFAULT_DEPTH = 100
DEFAULT_DATA_DIR = Path("/var/lib/zcrypto-capture/segments")
DATA_DIR_ENV_VAR = "ZCRYPTO_CAPTURE_DATA_DIR"
HEALTHCHECK_ENV_VAR = "HEALTHCHECK_URL"
HEALTHCHECK_INTERVAL_SECONDS = 60
DISK_WATERMARK_INTERVAL_SECONDS = 30
UNIVERSE_FILENAME = "point-in-time-universe.json"
_STAMPED_UNIVERSE = re.compile(r"universe-\d{8}")
LOCKFILE_NAME = ".capture.lock"


@contextlib.contextmanager
def single_instance_lock(data_dir: Path) -> Iterator[None]:
    """Hold an exclusive lock on `data_dir` for as long as this process writes segments: two processes glob the same
    hour directory, derive the SAME part sequence and clobber each other's unbackfillable rows, so CONTENTION refuses
    the start. `flock` on the data dir itself -- the kernel releases it however the process dies, leaving no stale
    lockfile, and the lock spans the container boundary the compose bind-mount crosses."""
    fd = None
    path = data_dir / LOCKFILE_NAME
    try:
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            # The ONLY thing that means "someone else holds it". Anything else does not.
            raise CaptureError(
                f"another capture process is already writing {data_dir} (lock: {path}) — refusing to "
                "start. Two writers overwrite each other's part files and destroy rows. Stop the "
                "running one first (`systemctl stop zcrypto-capture`)."
            ) from exc
        except OSError:
            # Not evidence of a second writer (a read-only filesystem, a mount without flock support: ENOLCK /
            # EOPNOTSUPP), and an unwritable disk has nothing to corrupt -- refusing here would crash-loop the daemon
            # under its `restart: unless-stopped` policy on the very failure it most needs to survive and report.
            logger.exception("could not take the single-instance lock — running UNLOCKED path=%s", path)
        yield
    finally:
        if fd is not None:
            os.close(fd)  # releases the lock


def resolve_universe_path(data_root: Path) -> Path:
    """The newest COMPLETE stamped universe set's artifact. Publication is additive, so the artifact is a SERIES of
    immutable `universe-<%Y%m%d>` sets rather than one mutable filename: fixed-width digits sort chronologically, and a
    stray hand copy never outranks a date. A stamped dir lacking the artifact is skipped LOUDLY, not fatally -- an
    in-flight fetch has one for seconds. The legacy unstamped set stays in `authored_sets`; `push_hot` raises without it."""
    stamped = sorted(
        (p for p in data_root.glob("universe-*") if p.is_dir() and _STAMPED_UNIVERSE.fullmatch(p.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    for candidate in stamped:
        artifact = candidate / UNIVERSE_FILENAME
        if artifact.exists():
            return artifact
        logger.error(
            "universe resolution: %s lacks %s -- skipping a NEWER stamped set in favor of an older universe",
            candidate.name,
            UNIVERSE_FILENAME,
        )
    raise FileNotFoundError(
        f"no stamped universe set under {data_root} carries {UNIVERSE_FILENAME} -- "
        f"run `zcrypto data fetch` to pull the published sets, or `zcrypto data rebuild universe` to mint one. "
        f"The legacy unstamped set is deliberately not a fallback: it is frozen at its 2026-07-07 content."
    )


def _default_pairs(universe_path: Path) -> list[str]:
    """The EUR-majors default: the EUR-quoted symbols of the point-in-time universe's `selected` list
    (master-plan §3 / T0003, resolved)."""
    if not universe_path.exists():
        raise CaptureError(
            f"no point-in-time universe file at {universe_path} to derive default pairs from — pass --pairs explicitly"
        )
    try:
        selected = json.loads(universe_path.read_text())["selected"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CaptureError(f"{universe_path} is not a valid point-in-time universe file: {exc}") from exc
    pairs = [symbol for symbol in selected if symbol.endswith("/EUR")]
    # T0092 (resolved: the deploy captures the BTC-quoted legs through explicit --pairs) -- this fallback still drops
    # them, so a hand-started run without --pairs under-collects, and unbackfillable non-collection looks like success.
    dropped = [symbol for symbol in selected if symbol not in pairs]
    if dropped:
        # ERROR, not WARNING: `alerts.yaml`'s "Capture · daemon ERROR logs" selects level=~"ERROR|CRITICAL",
        # and silent under-collection is exactly what must page -- it looks identical to success otherwise.
        logger.error(
            "default pairs dropped %d non-EUR-quoted universe symbol(s): %s -- pass --pairs to capture them",
            len(dropped),
            ", ".join(dropped),
        )
    return pairs


def _parse_ts(raw: str) -> datetime:
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CaptureError(f"unparseable timestamp from Kraken WS: {raw!r}") from exc
    # Kraken stamps UTC; a naive value would raise TypeError out of every writer comparison against it (`_implausible`,
    # the late-event floor) and so out of the single consumer task, killing capture for every pair on one missing `Z`.
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


# Drill knob (spec 00072 D7), shipped in the image rather than a test-only build: the ladder is only closable if a drill
# walks every rung against the real venue, and only if the validated binary IS the deployed one. Inert unless
# ZCRYPTO_DRILL_DESYNC_SECONDS is set, and read once at import, so a later environment change cannot push a running
# daemon into it. The UNIT is a duration, not a snapshot count, because a pair is stuck for a LENGTH OF TIME.
_DRILL_DESYNC_SECONDS = float(os.environ.get("ZCRYPTO_DRILL_DESYNC_SECONDS", "0") or 0)
_drill_started_at: dict[str, datetime] = {}


def _drill_maybe_fail(pair: str, category: str, in_sync: bool, book: OrderBook | None, now: datetime) -> bool:
    """Hold `pair` desynced for the drill window, then let it heal naturally: it reproduces the one failure mode no
    external action can induce, a book out of sync while Kraken is perfectly happy and emits no error frame. Both the
    return value and `book.desynced` must be held -- the return value alone re-fires rung 1 on every update, and
    `desynced` alone heals on the next good CRC."""
    if not _DRILL_DESYNC_SECONDS or not category.startswith("book"):
        return in_sync
    started = _drill_started_at.setdefault(pair, now)
    elapsed = (now - started).total_seconds()
    if elapsed > _DRILL_DESYNC_SECONDS:
        return in_sync
    if book is not None:
        book.desynced = True
    return False


async def _handle_book_message(
    msg: dict,
    category: str,
    client: CaptureClient,
    books: dict[str, OrderBook],
    book_writers: dict[str, SegmentWriter],
    monitor: GapMonitor,
    watermark: DiskWatermark,
    recovery: DesyncRecovery,
    last_seen: dict[str, datetime],
) -> None:
    for entry in msg.get("data", []):
        pair = entry["symbol"]
        book = books.get(pair)
        if book is None:
            continue  # a pair we didn't subscribe to; ignore defensively

        # BEFORE every early return below (T0101): a watermark breach makes this loop `continue` past the writers while
        # the socket stays connected, and a frozen `last_seen` would book a phantom silence on top of that real loss.
        last_seen[pair] = datetime.now(UTC)

        was_desynced = book.desynced
        in_sync = book.ingest_snapshot(entry) if category == "book_snapshot" else book.ingest_update(entry)
        now = datetime.now(UTC)
        in_sync = _drill_maybe_fail(pair, category, in_sync, book, now)
        if not in_sync:
            # Resubscribe ONCE, on the transition into desync, never on every subsequent out-of-sync update: at
            # depth-100 that is hundreds a second, which trips Kraken's subscribe rate limit ("Exceeded msg rate") and
            # the pair can then never resync. While desynced we simply wait for the resubscribe's fresh snapshot.
            if not was_desynced:
                monitor.start_gap(pair, "checksum_resync", at=now)
                logger.warning("checksum desync pair=%s - resubscribing", pair)
                await client.resubscribe_book(pair)
                # Rung 1 has fired; `_desync_recovery_loop` owns what happens if it does not take.
                recovery.note_desync(pair, at=now)
        elif was_desynced:
            monitor.end_gap(pair, at=now)
            recovery.note_recovered(pair, at=now)

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
    recovery: DesyncRecovery,
    last_seen: dict[str, datetime],
    venue_status: dict[str, int],
) -> None:
    async for msg in client.stream():
        category = classify(msg)
        if category in ("book_snapshot", "book_update"):
            await _handle_book_message(msg, category, client, books, book_writers, monitor, watermark, recovery, last_seen)
        elif category in ("trade_snapshot", "trade_update"):
            _handle_trade_message(msg, trade_writers, watermark)
        elif category in ("subscribe_ack", "unsubscribe_ack", "subscribe_error", "unsubscribe_error"):
            # T0102 (resolved): route every reply back to the resubscribe that asked for it -- correlation releases the deferred
            # `subscribe` and makes a rejection countable; a reply carrying no req_id of ours no-ops in `note_reply`.
            client.note_reply(msg)
            if category == "subscribe_error":
                logger.error("subscribe error: %s", msg)
            elif category == "unsubscribe_error":
                # a silently rejected request is what made the desync incident undiagnosable -- surface it
                logger.error("unsubscribe error: %s", msg)
        elif category == "status":
            # RECORDED, not acted on (spec 00073 D1): Kraken pushes this on connect and on every engine-state change,
            # and this log line is what makes "was the outage announced?" answerable at all.
            for item in msg.get("data", []) or []:
                system = item.get("system")
                # `effectiveTime` is the lead time a planned-downtime notice carries -- the number the pre-drain
                # decision waited on (T0105, resolved: the measured lead was zero, so the pre-drain was dropped).
                logger.info(
                    "venue status system=%s version=%s effective_time=%s",
                    system,
                    item.get("version"),
                    item.get("effectiveTime"),
                )
                if system is not None:
                    venue_status[system] = venue_status.get(system, 0) + 1
        # heartbeat / other -> nothing to do


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
        # Dead-man's-switch: ping only while the WS is connected AND books are healthy, so a connectivity loss stops the ping and
        # healthchecks.io alerts -- not just checksum desyncs. `not watermark.breached` is load-bearing (T0032): on a breach the
        # handlers return early and NOTHING is written while the WS stays connected and no gap opens. `watermark.measurable` holds
        # it while the probe fails -- "cannot measure" is not "healthy", and the healthchecks.io grace absorbs a transient blip.
        if client.connected and monitor.is_healthy(pairs) and not watermark.breached and watermark.measurable:
            ping_healthcheck(url)


# How often the recovery ladder is evaluated; well under its grace, so a retry fires close to when it is due.
DESYNC_RECOVERY_INTERVAL_SECONDS = 5

# A book stream silent this long is booked as a gap (T0101, spec 00073 D5). Set above the worst natural intra-hour book
# spacing over the fleet's captured hourly book segments, and deliberately equal to the reconciler's --min-gap-seconds, so
# the two producers measure the same thing rather than merely adjacent things.
BOOK_STALENESS_SECONDS = 30.0
STALENESS_CHECK_INTERVAL_SECONDS = 5


async def _staleness_loop(
    pairs: list[str],
    monitor: GapMonitor,
    last_seen: dict[str, datetime],
    *,
    interval: int = STALENESS_CHECK_INTERVAL_SECONDS,
    threshold: float = BOOK_STALENESS_SECONDS,
    now_fn=None,
    once: bool = False,
) -> None:
    """Book a gap for any subscribed, connected book stream receiving nothing (T0101); a pair with no `last_seen` is skipped, never
    booked -- nothing to be stale relative to; `_run` seeds every pair. The window is stamped at `last_seen[pair]`, never at
    detection -- that discards the threshold from every outage, an under-report in the defect's own direction -- and closes at the
    closing tick's `last_seen`, over-reporting by at most one `interval`, never under: the resume instant is already overwritten."""
    now_fn = now_fn or (lambda: datetime.now(UTC))
    while True:
        now = now_fn()
        for pair in pairs:
            # PER-PAIR, never around the sweep: `pairs` is ordered, so a wrapping guard would starve every pair after
            # the raising one, deterministically and forever.
            try:
                seen = last_seen.get(pair)
                if seen is None:
                    continue
                if (now - seen).total_seconds() > threshold:
                    monitor.start_silence(pair, at=seen)
                elif monitor.is_silent(pair):
                    monitor.end_silence(pair, at=seen)
            except Exception:
                logger.exception("staleness check failed for pair=%s -- continuing with the rest", pair)
        if once:
            return
        await asyncio.sleep(interval)


async def _desync_recovery_loop(
    client,
    books: dict[str, OrderBook],
    recovery: DesyncRecovery,
    *,
    interval: int = DESYNC_RECOVERY_INTERVAL_SECONDS,
    now_fn=None,
    once: bool = False,
) -> None:
    """Drive the recovery ladder for pairs still desynced (spec 00072, T0008, resolved). TIME-driven, not message-driven: a grace
    keyed on incoming messages would depend on the stuck pair still receiving traffic, and would re-evaluate hundreds of
    times a second at depth-100. Live book state is authoritative -- a pair that healed between ticks is dropped here,
    so the ladder's record cannot outlive the fault. Never raises: as a bare task, an escape kills recovery silently."""
    now_fn = now_fn or (lambda: datetime.now(UTC))
    while True:
        now = now_fn()
        for pair, book in books.items():
            # PER-PAIR, never around the whole sweep: `books` is insertion-ordered, so a wrapping try/except starves
            # every pair after the raising one -- deterministically the same pairs, forever, which is T0008's own defect (resolved).
            try:
                if not book.desynced:
                    recovery.note_recovered(pair, at=now)
                    continue
                action = recovery.due(pair, at=now)
                if action is Action.NONE:
                    continue
                # A rung spent against a client that is mid-reconnect reaches no socket -- `resubscribe_book` and
                # `force_reconnect` both no-op when `_ws is None` -- so it would burn the whole ladder against nothing
                # and go terminal for the cooldown, deaf exactly when the post-reconnect snapshot might fail.
                if not client.connected:
                    logger.debug("desync recovery: client reconnecting, holding pair=%s", pair)
                    continue
                # The ladder advances BEFORE the await: if the call raises, the attempt still happened as far as the
                # schedule is concerned. Otherwise `attempts` stays 0, `since` keeps measuring from the desync, and the
                # pair retries every tick forever without ever reaching the escalation rung.
                if action is Action.RETRY:
                    recovery.note_attempt(pair, at=now)
                    logger.warning("desync recovery: retrying resubscribe pair=%s", pair)
                    await client.resubscribe_book(pair)
                elif action is Action.RECONNECT:
                    # Escalation drops EVERY pair, not just this one -- bounded to once per pair
                    # per cooldown by the ladder, because a loop here is worse than the stuck pair.
                    recovery.note_escalated(pair, at=now)
                    logger.error(
                        "desync recovery: pair=%s still desynced after bounded retries -- forcing a full reconnect",
                        pair,
                    )
                    await client.force_reconnect()
            except Exception:
                logger.exception("desync recovery failed for pair=%s -- continuing with the rest", pair)
        if once:
            return
        await asyncio.sleep(interval)


async def _disk_watermark_loop(watermark: DiskWatermark, monitor: GapMonitor, interval: int) -> None:
    while True:
        try:
            healthy = watermark.check()
            # T0032: withholding the dead-man ping pages the operator, but the breach's lost time must also be BOOKED
            # into the gap accounting, or it reads clean for a window that lost data. Both calls are idempotent, so the
            # poll can drive them every tick.
            now = datetime.now(UTC)
            if healthy:
                monitor.end_watermark_gap(at=now)
            else:
                monitor.start_watermark_gap(at=now)
        except Exception:
            # check() reads the filesystem (a flaky mount raises OSError out of disk_usage) and NOTHING awaits this
            # task until shutdown: an escaping exception silently ENDS watermark polling -- `breached` freezes and a
            # later real breach goes undetected while the dead-man pings green (T0032). Log and keep polling.
            logger.exception("disk watermark check failed — retrying in %ss", interval)
        await asyncio.sleep(interval)


class CaptureCollector:
    """Expose capture's live objects as scrape-time series (spec 00069 D5), registered inside `_run()` once every object it reads
    exists. Every mutator runs on the SAME event-loop thread while a scrape only reads from prometheus_client's HTTP thread -- that
    single-writer-thread property, not an absence of concurrent mutation, is what makes reads good enough for `increase()` over
    these series, the intended consumption, even though `GapMonitor.end_watermark_gap` updates its two fields non-atomically."""

    def __init__(
        self,
        pairs: list[str],
        client: CaptureClient,
        books: dict[str, OrderBook],
        book_writers: dict[str, SegmentWriter],
        trade_writers: dict[str, SegmentWriter],
        monitor: GapMonitor,
        watermark: DiskWatermark,
        last_seen: dict[str, datetime] | None = None,
        venue_status: dict[str, int] | None = None,
    ) -> None:
        self._pairs = pairs
        self._last_seen = last_seen if last_seen is not None else {}
        self._venue_status = venue_status if venue_status is not None else {}
        self._client = client
        self._books = books
        self._book_writers = book_writers
        self._trade_writers = trade_writers
        self._monitor = monitor
        self._watermark = watermark

    def collect(self) -> Iterator[Metric]:
        writers = (*self._book_writers.values(), *self._trade_writers.values())
        yield CounterMetricFamily(
            "zcrypto_capture_reconnects_total", "WS reconnect attempts since process start.", value=self._client.reconnects_total
        )
        yield CounterMetricFamily(
            "zcrypto_capture_resubscribes_total",
            "Book resubscribes issued to recover from a checksum desync.",
            value=self._client.resubscribes_total,
        )
        yield CounterMetricFamily(
            "zcrypto_capture_resubscribe_errors_total",
            "Resubscribe frames the venue REJECTED (subscribe/unsubscribe error replies), correlated by req_id.",
            value=self._client.resubscribe_errors_total,
        )
        yield CounterMetricFamily(
            "zcrypto_capture_resubscribe_ack_timeouts_total",
            "Resubscribes whose unsubscribe ack never arrived in time; the subscribe was sent anyway.",
            value=self._client.resubscribe_ack_timeouts_total,
        )
        yield CounterMetricFamily(
            "zcrypto_capture_segments_written_total",
            "Hourly segments committed, summed across every pair and kind.",
            value=sum(w.segments_written for w in writers),
        )
        yield CounterMetricFamily(
            "zcrypto_capture_segment_bytes_total",
            "Bytes of committed segment files, summed across every pair and kind.",
            value=sum(w.segment_bytes for w in writers),
        )
        yield CounterMetricFamily(
            "zcrypto_capture_rows_held_total",
            # T0037: why held rows are parked rather than written in place.
            "Rows parked pending oracle hour confirmation, summed across every pair and kind.",
            value=sum(w.rows_held for w in writers),
        )
        yield CounterMetricFamily(
            "zcrypto_capture_rows_quarantined_total",
            "Held rows actually spilled to a .held quarantine file, summed across every pair and kind.",
            value=sum(w.rows_quarantined for w in writers),
        )
        yield CounterMetricFamily(
            "zcrypto_capture_hour_finalized_early_total",
            # Spec 00103 D1, T0037's residual (a). FINALIZED, not published -- `_count_if_early` runs ahead of the
            # merge, which declines in reachable cases, so a counted hour need not have reached disk.
            "Hours FINALIZED before the wall clock said they were over, summed across every pair and kind.",
            value=sum(w.hour_finalized_early for w in writers),
        )
        yield CounterMetricFamily(
            "zcrypto_capture_ts_past_dated_hour_total",
            # Spec 00109 D1: T0037's past-dated residual. Oracle-bearing writers only -- `_enter_hour`
            # gates the increment, so this counts fabrication rather than poll cadence.
            "First events that opened a stream's hour already behind the wall clock, where that hour held no captured parts.",
            value=sum(w.ts_past_dated_hour for w in writers),
        )

        now = datetime.now(UTC)
        gap = CounterMetricFamily(
            "zcrypto_capture_gap_seconds_total",
            "Cumulative gap seconds since process start, per pair -- use `increase()` (restart-safe).",
            labels=["pair"],
        )
        for pair in self._pairs:
            gap.add_metric([pair], self._monitor.gap_seconds(pair, at=now))
        yield gap

        # The proof-it-runs signal for the staleness watchdog (spec 00073 D4): fed by the SAME `last_seen` map the
        # watchdog reads, so a gauge that stays fresh proves the watchdog's input is live on every message -- without
        # injecting a fault into an unbackfillable pipeline.
        since = GaugeMetricFamily(
            "zcrypto_capture_seconds_since_last_book_message",
            "Seconds since this pair's last book message; grows without bound while upstream is silent.",
            labels=["pair"],
        )
        for pair in self._pairs:
            seen = self._last_seen.get(pair)
            since.add_metric([pair], (now - seen).total_seconds() if seen is not None else 0.0)
        yield since

        # Kraken's own engine state, counted by value (T0101/T0105). Series exist only for values
        # actually seen, so the presence of anything other than `online` is itself the signal.
        status = CounterMetricFamily(
            "zcrypto_capture_venue_status_total",
            "Venue status messages received, by reported system state.",
            labels=["system"],
        )
        for system, count in sorted(self._venue_status.items()):
            status.add_metric([system], count)
        yield status

        desynced = GaugeMetricFamily(
            "zcrypto_capture_book_desynced", "1 if the pair's book is currently checksum-desynced, else 0.", labels=["pair"]
        )
        for pair in self._pairs:
            desynced.add_metric([pair], 1.0 if self._books[pair].desynced else 0.0)
        yield desynced

        yield GaugeMetricFamily(
            "zcrypto_capture_disk_watermark_breached",
            "1 if the disk watermark is breached (every write stops while the WS stays connected), else 0.",
            value=1.0 if self._watermark.breached else 0.0,
        )


async def _run(pairs: list[str], depth: int, data_dir: Path, duration: int | None, healthcheck_url: str | None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)  # disk_usage() (DiskWatermark) requires the path to exist
    books = {pair: OrderBook(pair, depth) for pair in pairs}
    # One oracle shared by every writer (T0037): an hour boundary is acted on only once a second witness -- another
    # stream, or the handicapped wall clock -- has seen time reach it, so one bogus `timestamp` cannot truncate the hour.
    oracle = HourOracle()
    book_writers = {pair: SegmentWriter(data_dir, pair, "book", BOOK_SCHEMA, oracle=oracle) for pair in pairs}
    # `dedup_key`: on every (re)connect `ws_client` resubscribes with snapshot=True and Kraken REPLAYS recent trade
    # prints (T0026); `trade_id` is globally unique, so a replayed print already in the open hour is dropped.
    trade_writers = {
        pair: SegmentWriter(data_dir, pair, "trades", TRADE_SCHEMA, dedup_key="trade_id", oracle=oracle) for pair in pairs
    }
    monitor = GapMonitor()
    watermark = DiskWatermark(data_dir)
    client = CaptureClient(pairs, depth)

    # Per-pair last book message time, written by the handler and read by both the staleness watchdog and the collector's gauge.
    # SEEDED at process start -- an unseeded pair is skipped by the watchdog forever while its gauge reads 0.0, so a subscribed pair
    # that never delivers would be invisible to the instrument built to see silence. The seed costs no phantom gap:
    # subscribe-to-first-book-message, measured per pair, is an order of magnitude under the threshold.
    last_seen: dict[str, datetime] = dict.fromkeys(pairs, datetime.now(UTC))
    venue_status: dict[str, int] = {}

    # Opt-in exporter (spec 00069 D5): an unset ZCRYPTO_METRICS_PORT means no server, no thread, no collector. A
    # registration failure must leave capture running and the process metrics served -- `register()` runs a describe-less
    # collector's `collect()` synchronously, so this is where a live-object read can raise.
    port = metrics_port_from_env()
    if port is not None:
        registry = build_registry()
        try:
            registry.register(
                CaptureCollector(pairs, client, books, book_writers, trade_writers, monitor, watermark, last_seen, venue_status)
            )
        except Exception:
            logger.exception("capture metrics collector registration failed -- continuing with process metrics only")
        start_metrics_server(port, registry)

    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()
    if main_task is not None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, main_task.cancel)

    # One ladder per host, shared by every pair (spec 00072).
    recovery = DesyncRecovery()
    consumer = asyncio.create_task(
        _consume(client, books, book_writers, trade_writers, monitor, watermark, recovery, last_seen, venue_status)
    )
    health = asyncio.create_task(
        _healthcheck_loop(healthcheck_url, client, monitor, pairs, HEALTHCHECK_INTERVAL_SECONDS, watermark)
    )
    disk_check = asyncio.create_task(_disk_watermark_loop(watermark, monitor, DISK_WATERMARK_INTERVAL_SECONDS))
    desync_recovery = asyncio.create_task(_desync_recovery_loop(client, books, recovery))
    staleness = asyncio.create_task(_staleness_loop(pairs, monitor, last_seen))

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
        for task in (consumer, health, disk_check, desync_recovery, staleness):
            task.cancel()
        for task in (consumer, health, disk_check, desync_recovery, staleness):
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                # A task that DIED earlier re-raises its corpse's exception here, already surfaced (or about to be) by
                # the try block's own re-raise. Letting it escape would skip the writer.close() below and lose every
                # buffered row on top of the original failure.
                logger.exception("background task failed during shutdown")
        for writer in (*book_writers.values(), *trade_writers.values()):
            writer.close()


def capture(
    pairs: Optional[list[str]] = typer.Option(
        None,
        "--pairs",
        help="Pair(s) to capture, e.g. --pairs BTC/EUR --pairs ETH/EUR. Defaults to the EUR majors "
        "from the newest data/universe-<stamp>/point-in-time-universe.json; if no stamped set is "
        "present the command fails rather than reading the frozen unstamped one.",
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
    resolved_pairs = pairs or _default_pairs(resolve_universe_path(cfg.data_dir or Path("data")))
    resolved_data_dir = data_dir or Path(os.environ.get(DATA_DIR_ENV_VAR, str(DEFAULT_DATA_DIR)))
    healthcheck_url = os.environ.get(HEALTHCHECK_ENV_VAR)

    logger.info(
        "starting capture pairs=%s depth=%d data_dir=%s duration=%s",
        resolved_pairs,
        depth,
        resolved_data_dir,
        duration,
    )
    with single_instance_lock(resolved_data_dir):
        asyncio.run(_run(resolved_pairs, depth, resolved_data_dir, duration, healthcheck_url))
