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
    """Hold an exclusive lock on `data_dir` for as long as this process is writing segments.

    `SegmentWriter` derives the next part sequence by globbing the hour directory and names the part
    deterministically, so two processes pick the SAME sequence and write the SAME file: they clobber
    each other's parts and shred the hour (measured: 70 of 120 rows destroyed). Within one process
    the 24 writers are safe — disjoint `pair/kind` roots — but nothing stopped a SECOND process: an
    overlapping restart, or a human running `zcrypto capture` beside the service. These rows are
    unbackfillable, so refuse to start rather than race.

    `flock` because the kernel releases it when the process dies, however it dies — a SIGKILL, an OOM
    kill or a power loss leaves no stale lockfile for a human to reason about at 3am. It is held on
    the data dir itself, so it spans the container boundary too (the compose file bind-mounts the
    host path straight through).

    Only CONTENTION refuses the start. Failing to create or lock the file at all does not: on a
    read-only remount — the aftermath of the very ENOSPC condition `DiskWatermark` exists for — the
    `mkdir`/`open` raises, and refusing to start there would crash-loop the daemon under
    `restart: always` on exactly the failure we most need it to survive and report (the same trap as
    `_recover`'s tmp cleanup). An unwritable disk has nothing to corrupt, so we log and run on.
    """
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
            # A read-only filesystem, a mount without flock support (ENOLCK / EOPNOTSUPP). Not
            # evidence of a second writer, and not worth the daemon.
            logger.exception("could not take the single-instance lock — running UNLOCKED path=%s", path)
        yield
    finally:
        if fd is not None:
            os.close(fd)  # releases the lock


def resolve_universe_path(data_root: Path) -> Path:
    """The newest COMPLETE stamped universe set's artifact.

    Publication is additive (`rsync --ignore-existing`, never `--delete`), so a fixed filename can
    never be updated on the hub -- the artifact is a SERIES of immutable sets instead. Only exact
    `universe-<%Y%m%d>` names are candidates: fixed-width digits, so lexicographic order is
    chronological, and a stray hand copy (`universe-backup`) never outranks a date. A stamped dir
    lacking the artifact is skipped LOUDLY -- an ERROR names it, because silently degrading to an
    older universe is the same defect class the source guard refuses -- but skipped, not fatal:
    during an in-flight fetch a directory legitimately exists for seconds before its file lands.

    The legacy unstamped `universe/` set was the fallback here until the first stamped set was
    published (2026-08-13, `universe-20260813`). It is no longer consulted: that directory is frozen
    at its 2026-07-07 content and cannot be updated through the additive transport, so a fallback to
    it would present a six-week-old basket as the current one -- a resolution bug wearing the costume
    of a successful read. Absence is therefore FATAL rather than silently satisfied. The directory
    itself stays on disk and on the hub: `universe` remains in the config's `authored_sets`, and
    `push_hot` raises when a named set is missing, so removing it would break every future push.
    """
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
    pairs = [symbol for symbol in selected if symbol.endswith("/EUR")]
    # T0092: the universe selects BTC-quoted legs too, and this fallback drops them. The deploy
    # path passes --pairs explicitly (capture_pairs), so production is unaffected -- but a run
    # without --pairs would silently capture fewer streams than the universe selects, and
    # unbackfillable non-collection looks exactly like success.
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
    # Kraken stamps UTC. Should it ever drop the trailing `Z`, the result is naive — and every
    # comparison the writer makes against it (`_implausible`, the late-event floor) would raise
    # TypeError out of `append()`, i.e. out of the single consumer task: capture dies for all 10
    # pairs and both kinds, on one missing character.
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


# --- Drill knob (spec 00072 D7) -----------------------------------------------------------------
# T0008's whole history is a fix nobody could prove ran in production. The ladder is only closable
# if a drill walks every rung against the real venue -- and that drill is only meaningful if the
# validated binary IS the deployed binary, which is why this ships in the image rather than in a
# test-only build.
#
# Inert unless ZCRYPTO_DRILL_DESYNC_SECONDS is set, which is set NOWHERE in the fleet: not in the
# compose templates, not in any role, not in any env file. Read once at import, so a running daemon
# cannot be pushed into it by a later environment change.
#
# The UNIT is a duration, not a snapshot count, and two failed drill runs are why. Counting
# snapshots does not express "stuck": the first attempt faked only the return value, leaving the
# book reporting healthy so the transition guard re-fired rung 1 in a storm; the second also set
# `desynced`, but on a book whose data was genuinely valid -- so the next update recomputed a good
# CRC and healed it in milliseconds, before the 20 s grace could elapse. A pair is stuck for a
# LENGTH OF TIME, so that is what the knob takes.
_DRILL_DESYNC_SECONDS = float(os.environ.get("ZCRYPTO_DRILL_DESYNC_SECONDS", "0") or 0)
_drill_started_at: dict[str, datetime] = {}


def _drill_maybe_fail(pair: str, category: str, in_sync: bool, book: OrderBook | None, now: datetime) -> bool:
    """Hold `pair` desynced for the drill window, then let it heal naturally.

    Reproduces the ONE failure mode no external action can induce: a book that stays out of sync
    while Kraken is perfectly happy, so no error frame is ever emitted and only "still desynced N
    seconds later" can see it. Holding both the return value and `book.desynced` is required --
    either alone simulates a different fault (see the note above).
    """
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

        # BEFORE every early return below (T0101). A watermark breach makes this loop `continue`
        # past the writers while the socket stays connected; if it also stopped `last_seen` moving,
        # the watchdog would book a phantom silence on top of a real, different silent loss.
        last_seen[pair] = datetime.now(UTC)

        was_desynced = book.desynced
        in_sync = book.ingest_snapshot(entry) if category == "book_snapshot" else book.ingest_update(entry)
        now = datetime.now(UTC)
        in_sync = _drill_maybe_fail(pair, category, in_sync, book, now)
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
                # Rung 1 has fired. The ladder now owns what happens if it does not take -- see
                # _desync_recovery_loop. Nothing else here re-fires: the transition guard above is
                # what keeps a desync from becoming a resubscribe storm.
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
            # T0102: route every reply back to the resubscribe that asked for it. Correlation is
            # what releases the deferred `subscribe` (and what makes a rejection countable); a
            # reply carrying no req_id of ours is a no-op inside `note_reply`.
            client.note_reply(msg)
            if category == "subscribe_error":
                logger.error("subscribe error: %s", msg)
            elif category == "unsubscribe_error":
                # the resubscribe recovery's unsubscribe leg was rejected — surface it, since a
                # silently rejected request is exactly what made the desync incident undiagnosable
                logger.error("unsubscribe error: %s", msg)
        elif category == "status":
            # RECORDED, not acted on (spec 00073 D1). Kraken pushes this on connect and on every
            # engine-state change, and its planned-downtime form carries an `effectiveTime`. Until
            # one is actually observed in production there is nothing to build a reaction against --
            # and this log line is what makes "was the outage announced?" answerable at all.
            for item in msg.get("data", []) or []:
                system = item.get("system")
                # `effectiveTime` is the lead time a planned-downtime notice carries -- the one
                # number the pre-drain decision waited on (T0105 -- settled 2026-08-06: zero lead
                # observed, pre-drain dropped). Capturing `system`
                # and dropping it would answer only the easy half.
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
        # Dead-man's-switch: ping only while the WS is actually connected AND books are healthy, so
        # a connectivity loss (stuck in reconnect/backoff, no book updates flowing) stops the ping
        # and healthchecks.io alerts — not just checksum desyncs.
        #
        # `not watermark.breached` is load-bearing (T0032): on a breach the message handlers return
        # early and the daemon writes NOTHING, yet the WS stays connected and no gap opens — so
        # without this term the dead-man would keep reporting GREEN while the unbackfillable L2
        # stream is silently lost. Withholding the ping is what turns a silent death into a page.
        #
        # `watermark.measurable` closes the T0032(c) blind spot: while the disk probe itself is failing,
        # `breached` freezes at its last (green) value, so a disk that fills DURING the probe outage
        # would keep the ping green. "Cannot measure" is not "healthy" — withhold the ping so a
        # sustained probe failure pages (the healthcheck grace absorbs a transient blip).
        if client.connected and monitor.is_healthy(pairs) and not watermark.breached and watermark.measurable:
            ping_healthcheck(url)


# How often the recovery ladder is evaluated. Well under the 20 s grace, so a retry fires close to
# when it is due rather than up to a tick late.
DESYNC_RECOVERY_INTERVAL_SECONDS = 5

# A book stream silent this long is booked as gap (T0101, spec 00073 D5). Derived, not guessed:
# the worst NATURAL intra-hour book spacing measured across the fleet is 12.196 s (ETH/BTC, the
# thinnest leg on 2026-07-24), and across ETH/BTC's 104 hourly segments the largest natural hourly
# maximum is 12.299 s -- so 30 s is ~2.4x the binding pair's worst natural gap. It
# deliberately equals the reconciler's --min-gap-seconds, so the two producers finally measure the
# same thing instead of merely adjacent things.
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
    """Book gap for any book stream that is subscribed, connected, and receiving nothing (T0101).

    This is the fault class the daemon could not represent: on 2026-07-27 all 12 pairs went silent
    for ~209 s on BOTH hosts while `client.connected` was True, the library keepalive completed >=11
    ping/pong round trips, and `gap_seconds_total` read 0.0 throughout.

    The window is stamped at `last_seen[pair]`, NOT at detection: the watchdog cannot notice until
    the threshold has elapsed, so stamping at `now` would discard 30 s from every outage -- an
    under-report, the same direction as the defect being fixed.

    A pair with no `last_seen` yet is skipped rather than booked: before the first snapshot arrives
    there is nothing to be stale relative to. `_run` seeds every pair at process start, so this
    guards only the theoretical case -- an unseeded pair would be skipped forever AND report a 0.0
    gauge, the healthiest value there is, which is the opposite of what a never-delivering stream
    should look like.

    KNOWN IMPRECISION, bounded and always in the same direction. The window closes at the pair's
    `last_seen` as of the *closing tick*, not at the first message after the silence, so it includes
    up to one `interval` of live traffic: last message t=0, data resumes t=209.01, tick at t=210
    reads `seen=209.98` and books 209.98 s for a 209.01 s silence. Over-reporting by <= `interval`
    (5 s, i.e. <= 2.4 % of a 209 s outage), never under. Left as-is deliberately: closing at the
    true resume instant needs the first post-silence message time, which is exactly the value
    `last_seen` has already overwritten by the time the tick runs, and an under-reporting gap
    counter is the failure mode this whole topic exists to remove.

    Never raises, and never lets one pair abort the sweep -- `pairs` is ordered, so a wrapping
    try/except would starve every pair after the raising one, deterministically and forever.
    """
    now_fn = now_fn or (lambda: datetime.now(UTC))
    while True:
        now = now_fn()
        for pair in pairs:
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
    """Drive the recovery ladder for pairs that are still desynced (spec 00072, T0008).

    TIME-driven, not message-driven, and deliberately so. A grace period keyed on incoming messages
    would depend on the stuck pair still receiving traffic, and would re-evaluate hundreds of times
    per second at depth-100 instead of once per tick.

    Live book state is authoritative: a pair that healed between ticks is dropped from the ladder
    here, so the ladder's own record can never outlive the fault it describes.

    Never raises. This runs as a bare task beside the consumer, so an escaping exception would take
    the daemon's recovery down silently and permanently -- the exact failure class T0008 exists to
    fix, reintroduced one level up.
    """
    now_fn = now_fn or (lambda: datetime.now(UTC))
    while True:
        now = now_fn()
        for pair, book in books.items():
            # PER-PAIR, never around the whole sweep: one pair's exception must not abort the tick.
            # `books` is insertion-ordered from `pairs`, so a wrapping try/except starves every pair
            # after the raising one -- deterministically the same pairs, forever. That is T0008's own
            # defect reintroduced for 11 pairs by 1.
            try:
                if not book.desynced:
                    recovery.note_recovered(pair, at=now)
                    continue
                action = recovery.due(pair, at=now)
                if action is Action.NONE:
                    continue
                # A rung spent against a client that is mid-reconnect reaches no socket:
                # `resubscribe_book`/`force_reconnect` both no-op when `_ws is None`. Counting it
                # would burn grace + 3 retries + the one escalation in 55 s against nothing, then go
                # terminal for an hour -- deaf exactly when the post-reconnect snapshot might fail.
                if not client.connected:
                    logger.debug("desync recovery: client reconnecting, holding pair=%s", pair)
                    continue
                # The ladder advances BEFORE the await. If the call raises, the attempt still
                # happened as far as the schedule is concerned -- otherwise `attempts` stays 0,
                # `since` keeps measuring from the desync, and the pair retries every tick forever
                # without ever reaching rung 3 (measured: 57 retries in 5 min, 0 escalations).
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
            # T0032: withholding the dead-man ping PAGES the operator, but the breach's lost time must
            # also be BOOKED into the exit-bar gap accounting, or the automated <0.1% gap-time bar reads
            # clean for a window that lost data. Bridge the breach state into GapMonitor's dedicated
            # watermark window here — both calls are idempotent, so the poll can drive them every tick.
            now = datetime.now(UTC)
            if healthy:
                monitor.end_watermark_gap(at=now)
            else:
                monitor.start_watermark_gap(at=now)
        except Exception:
            # check() reads the filesystem (a flaky mount raises OSError out of disk_usage), and this
            # task is awaited by NOTHING until shutdown: an escaping exception silently ENDS watermark
            # polling — `breached` freezes, and a later real breach goes undetected while the dead-man
            # pings green (the exact T0032 silent death). Log and keep polling.
            logger.exception("disk watermark check failed — retrying in %ss", interval)
        await asyncio.sleep(interval)


class CaptureCollector:
    """Exposes capture's live objects as scrape-time series (spec 00069 D5, T3): registered once,
    inside `_run()`, after every object below already exists. These attributes have THREE mutators,
    not one -- `_consume`'s task, `_disk_watermark_loop`'s SEPARATE task (`watermark.check()`,
    `monitor.start_watermark_gap`/`end_watermark_gap`), and `writer.close()` on the main task at
    shutdown -- but every one of them runs on the SAME single event-loop thread, while a scrape
    runs on prometheus_client's own HTTP server thread and only ever reads. That single-writer-
    thread property is what makes a race here safe, not an absence of concurrent mutation: reads
    are consistent enough for counter semantics (`increase()` over these series, not a bare
    point-in-time read, is the intended consumption) even though `GapMonitor.end_watermark_gap`
    itself has a microsecond torn-read window across its own two fields -- do not restate "never a
    torn read"."""

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
            # Spec 00103 D1: T0037's residual (a). FINALIZED, not published -- `_count_if_early` runs
            # ahead of the merge, which declines in reachable cases, so a counted hour need not have
            # reached disk. A LEADING clock's truncation is NOT here (D1b): the skew alert sees that.
            "Hours FINALIZED before the wall clock said they were over, summed across every pair and kind.",
            value=sum(w.hour_finalized_early for w in writers),
        )
        yield CounterMetricFamily(
            "zcrypto_capture_ts_past_dated_hour_total",
            # Spec 00103 D5: T0037's past-dated residual. Oracle-bearing writers only -- `_enter_hour`
            # gates the increment, so this counts fabrication rather than poll cadence.
            "First events that opened a stream's hour already behind the wall clock.",
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

        # The proof-it-runs signal for the staleness watchdog (spec 00073 D4). Fed by the SAME
        # `last_seen` map the watchdog reads, so a gauge that stays fresh in production proves the
        # watchdog's input is live on every message -- without injecting a fault into an
        # unbackfillable pipeline, and without waiting for a real outage to find out.
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
            # T0032: the breach stops every write while the WS stays connected -- a silent-death shape.
            "1 if the disk watermark is breached (every write stops while the WS stays connected), else 0.",
            value=1.0 if self._watermark.breached else 0.0,
        )


async def _run(pairs: list[str], depth: int, data_dir: Path, duration: int | None, healthcheck_url: str | None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)  # disk_usage() (DiskWatermark) requires the path to exist
    books = {pair: OrderBook(pair, depth) for pair in pairs}
    # One oracle shared by all 24 writers (T0037): an hour boundary is acted on only once a second
    # witness — another stream, or the handicapped wall clock — has seen time reach it, so a single
    # bogus `timestamp` field can no longer finalize (and thereby permanently truncate) the live hour.
    oracle = HourOracle()
    book_writers = {pair: SegmentWriter(data_dir, pair, "book", BOOK_SCHEMA, oracle=oracle) for pair in pairs}
    # `dedup_key`: on every (re)connect `ws_client` resubscribes with snapshot=True and Kraken
    # REPLAYS its recent trade prints (T0026). `trade_id` is globally unique, so a replayed print
    # that is already in the open hour is recognized and dropped instead of stored twice.
    trade_writers = {
        pair: SegmentWriter(data_dir, pair, "trades", TRADE_SCHEMA, dedup_key="trade_id", oracle=oracle) for pair in pairs
    }
    monitor = GapMonitor()
    watermark = DiskWatermark(data_dir)
    client = CaptureClient(pairs, depth)

    # Opt-in exporter (spec 00069 D5): unset ZCRYPTO_METRICS_PORT means no server, no thread, no
    # collector -- registered here, late, because every object the collector reads must already
    # exist. A registration failure must not stop capture from running (or from serving at least
    # the process-self-metrics ProcessCollector already carries): log and still start the server.
    # The guard wraps `.register()` itself, not just `CaptureCollector(...)`'s construction
    # (cold-review M2): `CollectorRegistry.register()` calls the collector's OWN `.collect()`
    # synchronously, right here, whenever the collector has no `describe()` -- CaptureCollector
    # doesn't define one -- so capture evaluates these live objects at REGISTRATION time, not
    # lazily at the next scrape, and this is the one place that read can raise. (The engine's and
    # poller's own instruments are stock `Counter`/`Gauge`, which DO implement `describe()`, so
    # `.register()` never evaluates them eagerly the way it does here -- see the poller's own
    # comment for why its construction needs no equivalent guard.)
    # Per-pair last book message time: written by the handler, read by the staleness watchdog AND
    # by the collector's gauge. Declared here because the collector registers before the tasks start.
    # SEEDED at process start, not left empty. An unseeded pair has no `last_seen`, so the watchdog
    # skips it forever and the gauge reports 0.0 -- indistinguishable from "a message this instant",
    # the healthiest possible value. A pair that is subscribed and never delivers anything would
    # therefore be invisible to the very instrument built to see silence, and the deployed per-pair
    # stream-silent rule could never fire on it either. Seeding costs no phantom gap:
    # measured subscribe-to-first-book-message is 2.311 s (SOL/BTC) and 2.769 s (ETH/BTC), an order
    # of magnitude under the 30 s threshold.
    last_seen: dict[str, datetime] = dict.fromkeys(pairs, datetime.now(UTC))
    venue_status: dict[str, int] = {}

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

    # One ladder per host, shared by every pair (spec 00072). Defaults are unfitted -- see the
    # module docstring; the drill measures the first real heal latency this project has had since
    # the 2026-07-13 root-cause fix took desyncs to zero.
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
                # A task that DIED earlier re-raises its corpse's exception here — already surfaced
                # (or about to be, by the try block's own re-raise). Letting it escape this loop
                # would skip writer.close() below for all 24 writers, losing up to flush_rows
                # buffered rows per stream on top of the original failure.
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
