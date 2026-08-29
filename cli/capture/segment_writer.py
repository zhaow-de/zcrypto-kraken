from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.capture.errors import CaptureError
from cli.logging import get_logger

logger = get_logger("capture.segment_writer")

# One row per book-update price-level change (snapshot rows use type="snapshot").
BOOK_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "type": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "qty": pl.Float64,
    "checksum": pl.Int64,
}

# One row per trade print.
TRADE_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "qty": pl.Float64,
    "ord_type": pl.Utf8,
    "trade_id": pl.Int64,
}

# One row per Binance USD-M futures forceOrder (liquidation) event (spec 00051 OPS-2). `event_id` is
# synthesized (`f"{o.s}-{o.T}-{o.p}-{o.q}"`) because this stream carries no order id; it seeds the
# writer's `dedup_key` since Binance redelivers force-orders on reconnect.
LIQ_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "orig_qty": pl.Float64,
    "avg_price": pl.Float64,
    "order_status": pl.Utf8,
    "event_id": pl.Utf8,
}

# One row per Coinalyze closed 1-min liquidation bucket (spec 00051 OPS-2, T0023 fallback: Binance
# geo-fences the WS above from every egress we own, so the poller replaces it). `event_id` is
# synthesized (`f"{symbol}-{t}"`, `t` = the bucket's epoch-second start) since Coinalyze assigns no
# id to a bucket; it seeds the writer's `dedup_key` so the poller's overlapping 24h re-poll window
# never double-counts a bucket already ingested.
LIQ_AGG_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "long_usd": pl.Float64,
    "short_usd": pl.Float64,
    "event_id": pl.Utf8,
}

DEFAULT_FLUSH_ROWS = 5_000

# How far ahead a `ts` may be of BOTH our own clock AND the stream itself before it is garbage
# rather than data (see `_implausible`). Rotation follows the event's ts, so one far-future stamp
# would close the live hour early and then have the late-event guard drop every genuine row after it.
#
# The window is what a bad stamp gets away with: at +1h a stamp of `08:00` arriving at 07:05 passed
# BOTH witnesses (`>` is strict) and truncated the live hour to its first five minutes — published,
# manifest-verified, asserting "committed and complete". Five minutes bounds that to five minutes.
MAX_TS_AHEAD = timedelta(minutes=5)

# How many CONSECUTIVE timestamps the guard may refuse before it stands down (see `_implausible`).
#
# A DROPPED event never advances the guard's own reference, so a guard that is wrong about the stream
# stays wrong about it forever — every failure of this guard is therefore a PERMANENT blackout of the
# pair unless the run is capped. A run of refusals is the signature of a broken guard rather than a
# broken stream: real streams do not emit garbage back to back, but a wrong reference refuses
# everything. So the guard gets a bounded run, then stands down, and the first accepted event
# re-anchors it. This is what makes the guard's worst case a bounded, self-healing loss instead of a
# blackout: the stream ALWAYS makes progress, at worst losing this many timestamps per accepted one.
# (Executed: a clock lagging a constant 10 min on a pair printing every 10 min costs 3 rows once, at
# the cold start, and nothing thereafter. Only a clock that does not advance AT ALL — which no live
# host has — sustains the worst case, and even then a quarter of the prints get through.)
#
# DISTINCT timestamps, because one depth-100 book snapshot is ~200 rows that all share one ts: a
# single bad message must never exhaust the run and thereby let the rest of itself in (executed: a
# bogus 200-row far-future snapshot admits 0 of 200, and the hour is never opened in the future).
MAX_CONSECUTIVE_DROPS = 3

# The one bound that is NEVER stood down and needs no second witness (see `_implausible`).
#
# Two witnesses protect each other, but they share a blind spot: a stream that is COHERENTLY wrong.
# A systematic bad stamp — a `_parse_ts` unit bug, an exchange-side clock fault — advances normally,
# so the stream witness is perfectly satisfied by it, and an AND can then never drop it whatever the
# clock says. Executed against the pre-fix writer: a coherent far-future stream poisons the archive
# from its FIRST stamp (the hour opens in 2030, the late-event guard drops every genuine row behind
# it, and the startup sweep publishes the live hour truncated). The run cap narrows that to the 4th
# stamp, which is better and still not safe.
#
# So one bound answers to no witness at all: a `ts` a whole DAY ahead of our clock is not data under
# any reading. It is the one judgement the clock can be trusted to make alone, because a clock is
# wrong by minutes or hours — chrony's slew, an RTC read before the first step — and never by days,
# and because it can only ever fire on a ts that no plausible clock error could produce. It is
# deliberately far outside MAX_TS_AHEAD: this is a sanity floor, not a second guess at the window.
MAX_TS_ABSURD = timedelta(days=1)

# How many witnesses must vouch that an hour has BEGUN before any stream may act on the boundary —
# i.e. finalize the previous hour and open the new one (see `HourOracle`). Witnesses are the streams
# themselves (each one's newest accepted ts) plus the wall clock, which is deliberately handicapped:
# it vouches for an hour only once it believes the hour is CLOCK_WITNESS_MARGIN old.
#
# 2, because the asymmetry this exploits is already decisive at 2: a genuine boundary crosses every
# active stream within seconds, while a bogus stamp hits exactly ONE stream — so requiring any second
# witness (another stream, or the handicapped clock) is what a lone stamp can never produce. Higher
# would buy nothing against a single bad field and would starve a small `--pairs` run (one pair is
# only 2 streams), forcing every rotation to wait out the clock margin.
HOUR_QUORUM = 2

# The clock witness's handicap: it vouches for hour H only once it reads H's start plus this margin.
# The margin is what a LEADING clock would otherwise get away with: an unhandicapped clock witness
# plus one bogus stamp re-opens exactly the truncation this oracle exists to close. With the margin,
# that compound failure (a leading clock AND a bogus stamp, together) is bounded to lead-minus-margin
# minutes; either fault alone is harmless. A LAGGING clock never delays anything the streams can
# confirm themselves — the clock is one witness among many, never a veto (T0036's hard rule).
CLOCK_WITNESS_MARGIN = MAX_TS_AHEAD


class HourOracle:
    """Cross-stream corroboration that an hour has genuinely begun (T0037).

    Rotation trusts the event's own `ts` — a field Kraken sends — so one bogus stamp inside the
    plausibility window used to finalize the live hour early, permanently truncating it (the T0036
    invariant correctly refuses to reopen a committed final). The one signal no single bad field can
    forge is AGREEMENT: 24 writers share this process, a genuine hour boundary crosses all of them
    within seconds, and a bogus stamp hits exactly one. So a writer may act on a boundary only once
    `HOUR_QUORUM` witnesses have seen time reach it.

    Witnesses are each stream's newest plausible ts (reported by `observe`, clamped at the wall
    clock + MAX_TS_AHEAD — see `observe` for why an unclamped witness re-opens the truncation) plus
    the wall clock, handicapped by CLOCK_WITNESS_MARGIN so a leading clock cannot second a bogus
    stamp until the stamp's hour is genuinely near. The clock can only ever help CONFIRM a boundary — it has no veto,
    so a wrong clock can never darken a stream (the T0036 rule); at worst it delays a rotation that
    no second stream is around to confirm, and a delayed rotation loses nothing (`SegmentWriter`
    holds the new hour's rows and keeps the old hour open for appends).

    `confirmed_hour()` is monotone: once an hour is confirmed it stays confirmed, so a clock stepping
    backwards (chrony) can never un-confirm a boundary a writer already acted on.

    Shared mutable state across the 24 writers — safe because the daemon appends from ONE consumer
    task; there is no concurrency here by construction. The coupling is read-only at the decision
    point: a writer never waits ON another writer, it only reads how far time has provably got, so a
    quiet market cannot deadlock anything (no events -> no rotation attempted -> nothing is waiting).
    """

    def __init__(self) -> None:
        self._witnessed: dict[tuple[str, str], datetime] = {}  # (pair, kind) -> newest accepted ts
        self._confirmed: datetime | None = None

    def observe(self, stream: tuple[str, str], ts: datetime) -> None:
        """Record that `stream` saw a plausible event stamped `ts` (its guard already ran).

        The witness is CLAMPED at `now + MAX_TS_AHEAD`: a stream may vouch that time has reached T
        only once the wall clock is itself within MAX_TS_AHEAD of T. Unclamped, an UNCONFIRMED
        stamp corroborated: a garbage burst that stood the guard down (or an in-band walk of
        stamps each within the window of the last) parked one stream's witness hours ahead —
        forever, witnesses never expire — after which a single lone in-window stamp on any OTHER
        stream met quorum and truncated its live hour: the exact loss this oracle exists to close,
        rebuilt out of its own state. With the clamp every witness (the handicapped clock
        included) is <= now + MAX_TS_AHEAD, so no quorum, however poisoned, can confirm an hour
        more than MAX_TS_AHEAD before the wall clock reaches it — restoring the documented bound:
        an early publish now takes TWO streams stamped bogus inside the same closing window, and
        costs at most the window. A clock LAGGING by more than the window merely delays
        confirmation (rows are held and spilled, drained the moment the wall catches up — never
        dropped): the clock gains no veto over data, only over earliness.
        """
        ts = min(ts, _utcnow() + MAX_TS_AHEAD)
        prev = self._witnessed.get(stream)
        if prev is None or ts > prev:
            self._witnessed[stream] = ts

    def confirmed_hour(self) -> datetime | None:
        """The newest hour whose beginning HOUR_QUORUM witnesses have seen; None until any is."""
        witnesses = sorted([*self._witnessed.values(), _utcnow() - CLOCK_WITNESS_MARGIN], reverse=True)
        if len(witnesses) >= HOUR_QUORUM:
            candidate = _hour_start(witnesses[HOUR_QUORUM - 1])
            if self._confirmed is None or candidate > self._confirmed:
                self._confirmed = candidate
        return self._confirmed


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hour_start(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _read_failure(path: Path) -> Exception | None:
    """`None` if every row of `path` can be read, else the exception the read failed with.

    Decodes all data pages — aggregating rather than materializing, so memory stays bounded. A
    Parquet file's footer can be perfectly intact while its body is not (bit-rot, a half-written
    page), and `collect_schema()`, which reads only the footer, passes such a file happily.
    """
    try:
        pl.scan_parquet(path).select(pl.all().null_count()).collect(engine="streaming")
    except Exception as exc:
        return exc
    return None


def _replace_durably(tmp_path: Path, dest: Path) -> None:
    """`os.replace` into `dest`, fsyncing the data and then the directory entry.

    `replace` is atomic but not durable: on a machine power loss (as opposed to a process kill) the
    rename can reach the disk while the blocks it points at have not, leaving a torn file where an
    atomic one was promised. This dataset is unbackfillable, so take the durability.
    """
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    tmp_path.replace(dest)
    dir_fd = os.open(dest.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _part_index(path: Path, *, marker: str = ".part") -> int | None:
    """`"<HH>.part0007.parquet"` -> `7`; `None` if the name is not one of ours.

    Numeric, so part9999 sorts before part10000. Never raises: it runs on the `append()` path, and a
    `<HH>.part0000-copy.parquet` (a human's backup, an rsync artefact) would otherwise take down
    capture for every pair and both kinds, on every restart.

    `marker` distinguishes the two file families this writer sequences: ordinary parts (`.part`,
    merged into the hour's final) and held-spills (`.held`, quarantined rows the oracle never
    confirmed — see `_hold` / `_redeem_held`).
    """
    try:
        return int(path.name.split(marker)[1].split(".")[0])
    except IndexError, ValueError:
        return None


def _hour_of(hour_dir: Path, hh: str) -> datetime | None:
    """`.../<YYYY>/<MM>/<DD>` + `"07"` -> that UTC hour; `None` if the path is not one of ours.

    Nothing this writer creates fails to parse, but construction and the rotation path both walk the
    tree, and a raise from either stops capture for every pair and both kinds — so a stray file is
    skipped, never fatal.
    """
    day, month, year = hour_dir.name, hour_dir.parent.name, hour_dir.parent.parent.name
    try:
        return datetime(int(year), int(month), int(day), int(hh), tzinfo=UTC)
    except ValueError:
        return None


class SegmentWriter:
    """Buffers `(pair, kind)` capture events and streams them to hourly zstd-Parquet segments.

    Events are appended to a small in-memory buffer and flushed to a numbered "part" file once the
    buffer reaches `flush_rows` — the writer never holds more than that many rows in RAM at once,
    regardless of how much traffic an hour sees. When an event's `ts` crosses into a new hour, the
    closing hour's parts are streamed (`scan_parquet` -> `sink_parquet`, never loaded whole) into
    `<HH>.parquet`, alongside a sidecar `<file>.sha256` manifest.

    One invariant makes crash recovery mechanical, with nothing left to guess (T0036):

        **`<HH>.parquet` on disk is ALWAYS a committed, complete final.**

    It holds because `close()` flushes but never finalizes (a stop mid-hour leaves parts, never a
    part-hour published as a whole one), and because the final is the LAST thing a merge writes —
    the merged bytes go to `<HH>.parquet.merging` first, atomically, and are renamed into place only
    once the manifest is written and the consumed parts are gone. So:

    * a `<HH>.parquet.merging` on disk is a complete merge that was interrupted before it was
      published: it is authoritative, and committing it is all recovery has to do;
    * a part beside a `<HH>.parquet` is a state nothing this writer does can reach. It is a
      pre-T0036 leftover, and it is genuinely AMBIGUOUS (see `_merge_hour`) — so it is left exactly
      as it is, for a human. Nothing is guessed, nothing is unlinked, nothing is re-blessed.

    From the same invariant the writer needs **no wall clock**: "hour HH is closed" is exactly
    "`<HH>.parquet` exists", read off disk at construction. A clock leading for one instant (a boot
    before chrony's first step) would otherwise seed that state wrong and silently drop the entire
    live stream for up to 59:59. Which hours are over is likewise read from the event stream — the
    exchange's clock — not ours: the startup sweep runs on the first event, and finalizes every hour
    that still holds parts and is strictly before it. The clock is never allowed to declare an hour
    closed; it is allowed only to refuse to believe one that is dated in the FUTURE, which is
    nonsense no reading of the invariant produces (`_recover`).

    Nothing unreadable is ever deleted: it is quarantined to `<name>.corrupt` (never clobbering an
    earlier one) and kept as evidence.

    Segment layout: `<base_dir>/<pair>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet`.
    """

    def __init__(
        self,
        base_dir: Path,
        pair: str,
        kind: str,
        schema: dict[str, pl.DataType],
        *,
        flush_rows: int = DEFAULT_FLUSH_ROWS,
        dedup_key: str | None = None,
        oracle: HourOracle | None = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._pair = pair
        self._kind = kind
        self._schema = schema
        self._flush_rows = flush_rows
        self._dedup_key = dedup_key
        self._oracle = oracle
        self._held: dict[datetime, list[dict]] = {}  # rows for hours the oracle has not yet confirmed
        self._held_seen: dict[datetime, set] = {}  # per held hour: dedup keys, seeded from disk (see _hold)
        self._buffer: list[dict] = []
        self._current_hour: datetime | None = None  # the open hour; None until the first event
        self._max_ts: datetime | None = None  # the newest ts accepted...
        self._max_at: datetime = _utcnow()  # ... and our clock when we accepted it (see `_implausible`)
        self._seen: set = set()
        self._floor: datetime | None = None  # oldest hour still open, per the segments on disk
        self._drops = 0  # consecutive timestamps the plausibility guard has refused
        self._last_drop_ts: datetime | None = None
        # Additive, state-only counters (spec 00069 D5/T3): no behavioral change, plain ints a
        # metrics collector reads at scrape time. `rows_held` counts every row this writer has ever
        # parked pending oracle confirmation (see `_hold`); `rows_quarantined` counts the subset of
        # those rows actually spilled to a `.held` file rather than redeemed while still in RAM.
        self.segments_written = 0
        self.segment_bytes = 0
        self.rows_held = 0
        self.rows_quarantined = 0
        self.hour_finalized_early = 0  # hours FINALIZED before our clock said they were over (`_count_if_early`)
        self.ts_past_dated_hour = 0  # oracle-bearing first stamps that opened an hour behind the clock (`_enter_hour`)
        self._recover()

    def append(self, event: dict) -> None:
        """Append one event dict (keys matching `schema`). Rotates the previous hour's segment first
        if `event["ts"]` has crossed into a new hour."""
        ts = event["ts"]
        if self._implausible(ts):
            if ts != self._last_drop_ts:  # one bad message is one bad ts, however many rows it carries
                self._last_drop_ts = ts
                self._drops += 1
            logger.warning("dropping implausible event ts pair=%s kind=%s ts=%s", self._pair, self._kind, ts)
            return
        self._drops = 0  # the guard accepted a ts, so its references are good: re-arm the run cap
        self._last_drop_ts = None
        hour = _hour_start(ts)
        floor = self._current_hour or self._floor
        if floor is not None and hour < floor:
            # An hour that is already closed — a `<HH>.parquet` for it is on disk. A reconnect's
            # trade snapshot replays prints from before the boundary (T0026); writing them beside a
            # committed final would either duplicate rows it already holds or strand them.
            logger.warning("dropping late event pair=%s kind=%s ts=%s floor=%s", self._pair, self._kind, ts, floor)
            return
        if self._oracle is not None:
            # T0037: acting on a boundary — finalizing the live hour because one ts says a new hour
            # has begun — needs corroboration, because the ts is a field Kraken sends and one bad one
            # used to truncate the hour permanently. A row for an UNCONFIRMED hour is held, never
            # dropped: the live hour stays open (so no genuine row behind the stamp is ever refused),
            # and the held row is written the moment its hour is corroborated — by a second stream
            # crossing it, or by the handicapped clock. Held hours are drained in ascending order and
            # only up to this event's own hour, so every row still lands in the hour its ts names.
            self._oracle.observe((self._pair, self._kind), ts)
            confirmed = self._oracle.confirmed_hour()
            for held_hour in sorted(h for h in self._held if h <= hour and confirmed is not None and h <= confirmed):
                rows = self._held.pop(held_hour)
                self._held_seen.pop(held_hour, None)
                self._enter_hour(held_hour)
                for row in rows:
                    self._admit(row)
            if confirmed is None or hour > confirmed:
                self._hold(hour, event)
                return
        self._enter_hour(hour)
        self._admit(event)

    def close(self) -> None:
        """Flush the buffer — and any held rows — to disk (idempotent). Deliberately does **not**
        finalize the open hour: `<HH>.parquet` means "committed and complete", and publishing a
        stop's half-hour under that name is what made crash recovery ambiguous. The hour is
        finalized by whoever crosses its boundary — this process, or the next one's sweep. Held rows
        (an hour the oracle never confirmed) spill as HELD-SPILL files (`<HH>.held####.parquet`) of
        the hour their ts names — never as parts: a part is merged by the sweep, and a bogus stamp
        spilled at a stop used to become the SOLE, manifest-certified content of an hour that was
        never genuinely captured. A held-spill commits nothing and is invisible to the sweep; it is
        redeemed into parts only when a live, quorum-confirmed stream opens its hour
        (`_redeem_held`) — until then it is quarantine, kept and never deleted."""
        self._flush_buffer()
        for hour, rows in self._held.items():
            if rows:
                self._write_part(rows, hour, marker=".held")
                self.rows_quarantined += len(rows)
        self._held = {}
        self._held_seen = {}

    def finalize_completed_hours(self, cutoff: datetime) -> int:
        """INTENDED FOR NON-ORACLE WRITERS ONLY (review 2f08379-I1): this method ignores held
        spills entirely -- on an oracle-bearing writer, finalizing an hour with held rows would
        floor-lock the hour and strand its quarantine forever (never merged, never redeemed). The
        only sanctioned caller (the Coinalyze poller) builds writers without an oracle; the guard
        below makes any future oracle-bearing caller fail fast instead of silently foreclosing rows.

        Finalize every hour STRICTLY OLDER than `cutoff` that currently holds a row — the open
        hour (if any) plus any crash-leftover part-hours the event stream itself has not yet swept.
        Returns the count of hours this call actually finalized (0 is the correct, idempotent
        answer once there is nothing left to do). Hours `>= cutoff` are NEVER touched.

        T0046: rotation is event-driven — an hour closes only when the NEXT event for this same
        (pair, kind) crosses its boundary (`_enter_hour`) — which fits a continuously-emitting
        stream but stalls indefinitely for a sparse one (a symbol quiet for hours never produces
        the "next" event that would close it). This is the wall-clock escape hatch: the CALLER
        decides `cutoff` (see `cli/liquidations/coinalyze.py` for the margin that makes it safe),
        and this method finalizes anything provably older than it, via the exact same
        `_finalize_hour`/`_merge_hour` path an ordinary rotation uses. A pair that keeps emitting
        normally never has an hour cross `cutoff` while still open, so calling this on the live
        capture daemon's writers would be a no-op in practice — nothing here changes what an
        ordinary rotation does; it is purely additive.

        Two independent things can be older than `cutoff`:

        1. The open hour (`self._current_hour`) — flushed and merged, then the writer is left with
           NO open hour (`None`), so the next event re-derives its own hour from scratch exactly
           like a fresh writer's first event does (`_enter_hour`'s `is None` branch: sweep, open).
        2. Any OTHER part-hours already on disk — crash leftovers from a previous process that
           never got swept, because sweeping is deferred to this writer's first event and one may
           never come for a symbol this sparse.

        Setting `_current_hour` to `None` is new for this class — the ordinary rotation path only
        ever advances it forward via `_open_hour`, which re-anchors the late-event floor for free
        as a side effect. With no such call here, this method re-anchors `self._floor` itself for
        every hour it actually finalizes (a merge this class declines — e.g. the AMBIGUOUS
        parts-beside-a-final case — does not count, and does not raise the floor). Skipping this
        would let a late replay for an hour finalized here — arriving while `_current_hour` is
        still `None` — silently reopen it, and its eventual re-rotation would then read as "parts
        beside a readable final": the class's own ambiguous, human-only state.
        """
        if self._oracle is not None:
            raise CaptureError(
                "finalize_completed_hours is not supported on oracle-bearing writers (held spills would be stranded)"
            )
        finalized = 0
        newest_hour: datetime | None = None

        if self._current_hour is not None and self._current_hour < cutoff:
            hour = self._current_hour
            final_path = self._hour_dir(hour) / f"{hour:%H}.parquet"
            already_final = final_path.exists()
            self._finalize_hour(hour)
            self._current_hour = None
            if not already_final and final_path.exists():
                finalized += 1
                newest_hour = hour

        root = self._base_dir / self._pair / self._kind
        for hour_dir in sorted({path.parent for path in root.rglob("*.part*.parquet")}):
            for hh in sorted({path.name.split(".part")[0] for path in hour_dir.glob("*.part*.parquet")}):
                hour = _hour_of(hour_dir, hh)
                if hour is None or hour >= cutoff:
                    continue
                final_path = hour_dir / f"{hh}.parquet"
                already_final = final_path.exists()
                self._merge_hour(hour_dir, hh)
                if not already_final and final_path.exists():
                    finalized += 1
                    newest_hour = hour if newest_hour is None else max(newest_hour, hour)

        if newest_hour is not None:
            floor = newest_hour + timedelta(hours=1)
            self._floor = floor if self._floor is None else max(self._floor, floor)
        return finalized

    def _enter_hour(self, hour: datetime) -> None:
        """Make `hour` the open hour: sweep (first event) or finalize the previous hour, then open.
        A no-op when `hour` is already open. Callers guarantee `hour` never goes backwards."""
        if self._current_hour is None:
            # Spec 00103 D5, T0037's past-dated residual. On an ORACLE-BEARING writer the first event
            # is the only one that can open an hour behind the wall clock -- from here on `floor` is
            # `_current_hour`, so the late-event guard refuses a past-dated stamp before it reaches
            # us -- and such an hour can commit a final for an hour that was never captured.
            #
            # Gated on the oracle because that premise is FALSE without one: `finalize_completed_hours`
            # nulls `_current_hour` every poll cycle, so an oracle-less poller re-enters this branch
            # constantly and a re-awakening sparse symbol opens a prior hour BY DESIGN.
            if self._oracle is not None and hour < _hour_start(_utcnow()):
                self.ts_past_dated_hour += 1
                logger.warning("first stamp opened a past hour pair=%s kind=%s hour=%s", self._pair, self._kind, hour)
            self._sweep(hour)
            self._open_hour(hour)
        elif hour > self._current_hour:
            self._finalize_hour(self._current_hour)
            self._open_hour(hour)

    def _admit(self, event: dict) -> None:
        """The write path proper: de-dup, advance the stream witness, buffer, flush. The event's
        hour is already open."""
        if self._dedup_key is not None:
            key = event[self._dedup_key]
            if key in self._seen:
                logger.warning("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
            self._seen.add(key)
        ts = event["ts"]
        if self._max_ts is None or ts > self._max_ts:
            self._max_ts = ts
            self._max_at = _utcnow()  # anchored together: the witness is the PAIR, not either half
        self._buffer.append(event)
        if len(self._buffer) >= self._flush_rows:
            self._flush_buffer()

    def _hold(self, hour: datetime, event: dict) -> None:
        """Park a row whose hour the oracle has not confirmed. It still advances the stream witness
        (it passed the plausibility guard, and a witness that ignores it would re-fire on its
        successors), and RAM stays bounded: a held hour that reaches `flush_rows` is spilled to that
        hour's HELD-SPILL files (`.held`, quarantine the sweep never merges — see `_redeem_held`),
        so an hour that never confirms in this process is redeemed when it genuinely arrives.

        Held rows pass the SAME de-dup as stored ones. `_admit`'s `_seen` covers only the open
        hour, so a T0026 reconnect replay landing in a hold window used to be held blind — and a
        stop before confirmation spilled BOTH copies, which the next process merged into the
        committed final: duplicated prints, as permanent as lost ones. The held set is seeded from
        the hour's on-disk parts AND held-spills (the originals a previous process — or an earlier
        spill of this one — already wrote), then tracks what this hold window has taken.
        """
        if self._dedup_key is not None:
            seen = self._held_seen.get(hour)
            if seen is None:
                hour_dir = self._hour_dir(hour)
                hh = f"{hour:%H}"
                files = [*self._parts_for(hour_dir, hh), *self._parts_for(hour_dir, hh, marker=".held")]
                seen = self._held_seen[hour] = self._disk_keys(files)
            key = event[self._dedup_key]
            if key in seen:
                logger.warning("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
            seen.add(key)
        rows = self._held.setdefault(hour, [])
        rows.append(event)
        self.rows_held += 1
        ts = event["ts"]
        if self._max_ts is None or ts > self._max_ts:
            self._max_ts = ts
            self._max_at = _utcnow()
        if len(rows) >= self._flush_rows:
            self._write_part(rows, hour, marker=".held")
            self.rows_quarantined += len(rows)
            self._held[hour] = []

    def _implausible(self, ts: datetime) -> bool:
        """True only if `ts` is far ahead of BOTH where the stream should have got to by now AND our
        own clock — and only while the guard has not already refused MAX_CONSECUTIVE_DROPS in a row.

        Two witnesses must agree before a row is thrown away, because either one alone has a failure
        mode that costs the whole stream for as long as it lasts:

        * the clock alone — a local clock lagging by more than MAX_TS_AHEAD rejects every live event
          (and chrony only *slews* an offset that appears after startup, so it can last hours);
        * the stream alone — a pair can genuinely go hours without a print (the thin EUR alts do,
          overnight), and the next real trade would then be rejected against a reference that can
          never advance again, since a DROPPED event does not advance it.

        The stream witness is the last ACCEPTED ts carried forward by the time that has passed since
        we accepted it — not the bare `_max_ts`. That distinction is the whole guard. Bare `_max_ts`
        made the two witnesses' blind spots OVERLAP: a pair quiet for longer than the window makes it
        fire, and a lagging clock makes the clock witness fire, so both fire on the same genuine live
        print and the pair goes dark (a 10-minute lag on a pair printing every 10 minutes: 12 of 12
        dropped, and it never recovers). Carrying it forward measures the stream against the clock's
        RATE instead of its VALUE, so a constant offset — which is what a wrong clock is — cancels
        out entirely, and a quiet pair under a lagging clock loses nothing. It is also sharper on the
        real target: after a 4-hour silence the reference is *now*, so a far-future stamp is still
        caught, where bare `_max_ts` would have let anything through for the next 4 hours.

        The run cap is the backstop for what is left: a clock that STEPS (chrony's first correction)
        breaks the rate assumption for exactly one interval, and a run of refusals is the signature
        of a broken guard rather than a broken stream — real streams do not emit garbage back to
        back, but a wrong reference refuses everything. So the guard stands down, and the first
        accepted event re-anchors it.

        That cap is also what lets the clock judge the FIRST event alone. It must be allowed to:
        before this process has accepted anything there is no stream witness, and returning False
        unconditionally meant one garbage far-future stamp — arriving as the first event after ANY
        restart — opened the hour in the future and had the late-event guard drop every genuine row
        after it, for the life of the process. A lagging clock now costs the first few rows; it can
        no longer cost the stream. (Seeding the stream witness from the newest segment on disk
        instead is worse than useless: an outage longer than MAX_TS_AHEAD leaves it stale by exactly
        the length of the outage, so it fires on the first genuine event of the recovery — which is
        the reboot this whole fix exists for.)

        MAX_TS_ABSURD is checked FIRST and answers to none of that — not to the second witness, not
        to the cap. Both witnesses share one blind spot, a stream that is COHERENTLY wrong, and the
        cap is a way IN to that blind spot: a systematic bad stamp satisfies the stream witness by
        construction, and a run of them stands the guard down and is then accepted. Nothing below can
        reach a `ts` a day ahead of our clock, so the blind spot is closed at its only entrance.
        """
        now = _utcnow()
        if ts > now + MAX_TS_ABSURD:
            return True  # not data under any reading of any clock — and never stood down
        if self._drops >= MAX_CONSECUTIVE_DROPS:
            return False
        if self._max_ts is None:
            return ts > now + MAX_TS_AHEAD
        # Clamped: a clock stepped BACKWARD must only ever make the guard laxer, never tighter.
        elapsed = max(now - self._max_at, timedelta(0))
        return ts > self._max_ts + elapsed + MAX_TS_AHEAD and ts > now + MAX_TS_AHEAD

    def _hour_dir(self, hour: datetime) -> Path:
        return self._base_dir / self._pair / self._kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"

    def _parts_for(self, hour_dir: Path, hh: str, *, marker: str = ".part") -> list[Path]:
        """Every `marker` file on disk for `<HH>`, in ascending sequence order. A name whose sequence
        does not parse is not one of ours: it is skipped, never guessed at and never fatal."""
        indexed = [
            (seq, path) for path in hour_dir.glob(f"{hh}{marker}*.parquet") if (seq := _part_index(path, marker=marker)) is not None
        ]
        return [path for _, path in sorted(indexed)]

    def _open_hour(self, hour: datetime) -> None:
        self._current_hour = hour
        self._redeem_held(hour)
        self._seen = set()
        if self._dedup_key is None:
            return
        # Seed the de-dup set from the parts a previous process already wrote for this hour. On a
        # mid-hour restart `ws_client` resubscribes with snapshot=True and Kraken REPLAYS its recent
        # prints (T0026); they are already on disk, so an in-memory-only de-dup would not recognize
        # them and the hour's segment would hold each replayed print twice. Duplicated rows corrupt a
        # reconstructed book exactly as badly as lost ones.
        parts = self._parts_for(self._hour_dir(hour), f"{hour:%H}")
        if parts:
            self._seen = self._disk_keys(parts)

    def _redeem_held(self, hour: datetime) -> None:
        """Redeem `hour`'s held-spill files (`<HH>.held####.parquet`) into ordinary parts.

        A held-spill holds rows the oracle could not corroborate when they hit disk (spilled at
        `flush_rows`, or by `close()`). Under its own name it is quarantine — the sweep and the
        merge ignore it — so an uncorroborated stamp can never fabricate a committed final for an
        hour that was never genuinely captured. Opening the hour IS the missing corroboration:
        quorum has confirmed it and a live event stream is entering it, so the quarantined rows
        become parts, sequenced ahead of anything this process writes (they are older). The rename
        is atomic and this never raises (it runs on the rotation path): a rename that fails just
        leaves the row where it was — quarantined, never lost, never duplicated.
        """
        hour_dir = self._hour_dir(hour)
        hh = f"{hour:%H}"
        for held in self._parts_for(hour_dir, hh, marker=".held"):
            parts = self._parts_for(hour_dir, hh)
            seq = (_part_index(parts[-1]) or 0) + 1 if parts else 0
            try:
                held.rename(hour_dir / f"{hh}.part{seq:04d}.parquet")
            except OSError:
                logger.exception("could not redeem a held spill pair=%s kind=%s path=%s", self._pair, self._kind, held)

    def _disk_keys(self, files: list[Path]) -> set:
        """The de-dup keys held by `files`, tolerating unreadable inputs. One unreadable file must
        not silently empty the whole set — that is how a replay gets written a second time. Take
        the keys of every file that CAN be read; one that cannot is quarantined at the merge, so
        its rows never reach the segment and a replay of them is a recovery, not a duplicate."""
        try:
            return set(self._keys_of(files)) if files else set()
        except Exception:
            keys: set = set()
            for file in files:
                try:
                    keys |= set(self._keys_of([file]))
                except Exception:
                    logger.exception("could not read de-dup keys pair=%s kind=%s path=%s", self._pair, self._kind, file)
            return keys

    def _keys_of(self, parts: list[Path]) -> pl.Series:
        return pl.scan_parquet(parts).select(self._dedup_key).collect()[self._dedup_key]

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        self._write_part(self._buffer, self._current_hour)
        self._buffer = []

    def _write_part(self, rows: list[dict], hour: datetime, *, marker: str = ".part") -> None:
        hour_dir = self._hour_dir(hour)
        hh = f"{hour:%H}"
        try:
            hour_dir.mkdir(parents=True, exist_ok=True)
            # The next sequence number is read from disk, so a writer resuming a half-written hour
            # starts *past* the highest part already there and can never overwrite it.
            parts = self._parts_for(hour_dir, hh, marker=marker)
            seq = (_part_index(parts[-1], marker=marker) or 0) + 1 if parts else 0
            part_path = hour_dir / f"{hh}{marker}{seq:04d}.parquet"
            tmp_path = part_path.with_name(part_path.name + ".tmp")
            df = pl.DataFrame(rows, schema=self._schema)
            df.write_parquet(tmp_path, compression="zstd")
            _replace_durably(tmp_path, part_path)  # atomic + durable: a kill can never leave a torn part
        except Exception:
            # The hottest write in the daemon (every `flush_rows` rows), and it is one `OSError`
            # (EIO, ENOSPC despite DiskWatermark) away from taking down the single consumer task —
            # i.e. capture for all 12 pairs and both kinds. This buffer is lost either way; the other
            # 19 streams need not be. The dead-man's switch goes red on the watermark breach that
            # normally causes this, and the traceback names the pair.
            logger.exception("flush failed — buffer dropped pair=%s kind=%s hour=%s", self._pair, self._kind, hh)

    def _count_if_early(self, hour: datetime) -> None:
        """Count an hour finalized before our own clock said it was over (spec 00103 D1/D2) — the
        visible signature of T0037's residual (a).

        It does NOT see a LEADING clock's truncation: that measurement is taken with the same wrong
        clock, which subtracts its own lead back out (D1b). A genuinely past hour yields a negative
        earliness, so the sweep's ordinary republishing is excluded by the arithmetic rather than by
        a special case.
        """
        earliness = (hour + timedelta(hours=1)) - _utcnow()
        if earliness > timedelta(0):
            self.hour_finalized_early += 1
            logger.warning(
                "hour finalized early pair=%s kind=%s hour=%s early_s=%.1f",
                self._pair,
                self._kind,
                hour,
                earliness.total_seconds(),
            )

    def _finalize_hour(self, hour: datetime) -> None:
        self._count_if_early(hour)
        self._flush_buffer()
        self._merge_hour(self._hour_dir(hour), f"{hour:%H}")

    def _merge_hour(self, hour_dir: Path, hh: str) -> None:
        """Merge the hour's parts into a committed `<HH>.parquet`. Never raises.

        This runs on `append()`'s rotation path, and nothing between here and `_run` catches: a raise
        would kill capture for every pair and both kinds. Every step below leaves the hour fully
        recoverable — a part is unlinked only once the merged bytes that contain it are durable — so
        on any failure the right move is to log and carry on, and let the next boundary (or the next
        process's sweep) retry the hour. No row is ever destroyed by giving up here.
        """
        final_path = hour_dir / f"{hh}.parquet"
        merging_path = hour_dir / f"{hh}.parquet.merging"
        parts = self._parts_for(hour_dir, hh)
        if not parts:
            return  # already committed, or the hour was never captured: nothing to merge
        try:
            if merging_path.exists():
                # A merge that `_recover` could not finish (its commit hit an IO error). Those bytes
                # may be the hour's ONLY copy — the parts they came from are already unlinked — so
                # they are never sunk over. Only `_recover` promotes them; leave it to the next start.
                logger.error("an uncommitted merge is in the way pair=%s kind=%s path=%s", self._pair, self._kind, merging_path)
                return
            if final_path.exists():
                failure = _read_failure(final_path)
                if failure is None:
                    # AMBIGUOUS, and unresolvable from here — the pre-T0036 writer produced BOTH
                    # readings of this state: `close()` published the open hour, so the parts hold
                    # rows the final does NOT have (merging is right); and its finalize unlinked the
                    # parts only AFTER sinking the final, so a kill there leaves parts the final
                    # ALREADY holds (merging would duplicate the whole hour). Guessing either way
                    # destroys the data — round 3 unlinked them, and it deleted real rows. Every byte
                    # is on disk and nothing here is on fire, so touch nothing and let a human look.
                    logger.error(
                        "parts beside a readable final — ambiguous, left untouched pair=%s kind=%s path=%s parts=%d",
                        self._pair,
                        self._kind,
                        final_path,
                        len(parts),
                    )
                    return
                # An unreadable final holds no rows anyone can recover, so it cannot be the truth and
                # cannot be an input: quarantine it (never delete) and rebuild the hour from the parts.
                self._quarantine(final_path, failure)
            if self._write_merging(parts, merging_path):
                self._commit(merging_path, final_path)
                logger.info("segment written pair=%s kind=%s path=%s", self._pair, self._kind, final_path)
                try:
                    # Isolation invariant (spec 00069 D5): the commit above already succeeded and
                    # `final_path` is durably on disk -- a metrics update must never look like the
                    # merge itself failing. `stat()` is the one call here that can still raise (an
                    # unreadable/vanished file, e.g. a racing external `rm`), so it gets its own
                    # try/except rather than sharing the outer "merge failed" one.
                    self.segments_written += 1
                    self.segment_bytes += final_path.stat().st_size
                except Exception:
                    logger.exception(
                        "segment committed but its metrics update failed pair=%s kind=%s path=%s",
                        self._pair,
                        self._kind,
                        final_path,
                    )
        except Exception:
            logger.exception("merge failed pair=%s kind=%s dir=%s hour=%s", self._pair, self._kind, hour_dir, hh)

    def _write_merging(self, inputs: list[Path], merging_path: Path) -> bool:
        """Stream `inputs` into `<HH>.parquet.merging`, atomically. False if nothing could be read.

        Rows are concatenated in input order and are **never sorted**: L2 book deltas carry ABSOLUTE
        quantities, so re-ordering rows that share a `ts` silently corrupts the rebuilt book.

        The happy path decodes each input exactly ONCE — the read IS the validation. Only if it
        actually fails is every input decoded on its own, to quarantine the unreadable one and merge
        the rest: pre-validating every part on every rotation cost a 27s event-loop stall at each
        hour boundary across the 20 streams, starving the healthcheck and disk-watermark loops.
        """
        tmp_path = merging_path.with_name(merging_path.name + ".tmp")
        try:
            try:
                pl.scan_parquet(inputs).sink_parquet(tmp_path, compression="zstd")
            except Exception:
                inputs = [path for path in inputs if self._readable(path)]
                if not inputs:
                    return False
                pl.scan_parquet(inputs).sink_parquet(tmp_path, compression="zstd")
            _replace_durably(tmp_path, merging_path)
            return True
        finally:
            # A no-op once the replace has consumed it. On a failure it is a half-sunk full-hour file
            # on the very disk DiskWatermark guards, and it is re-derivable from the untouched parts.
            tmp_path.unlink(missing_ok=True)

    def _commit(self, merging_path: Path, final_path: Path) -> None:
        """Publish an interrupted-or-fresh `<HH>.parquet.merging` as the hour's committed final.

        The merging file was written atomically, so it is whole — it, never the parts and never a
        half-written final, is the authority. The order is what makes recovery mechanical:

        1. the manifest, from the merging file's bytes (which ARE the final's bytes, so the digest is
           right before the file it certifies exists) — a final can never be published unmanifested;
        2. the parts, which are now provably inside durable merged bytes — and only now;
        3. the rename, atomic and last.

        A kill anywhere in here leaves a `<HH>.parquet.merging` behind, and the next construction
        simply re-runs these three steps. Nothing has to be inferred from what is or is not on disk.
        """
        self._write_manifest(merging_path, final_path)
        for part in self._parts_for(final_path.parent, final_path.name.split(".")[0]):
            part.unlink(missing_ok=True)
        _replace_durably(merging_path, final_path)

    def _readable(self, path: Path) -> bool:
        """True if every row of `path` decodes; else quarantine it and return False.

        One unreadable input must never abort the merge: it runs on the rotation path and, on a
        restart, over every hour a previous process left behind — so a raise here stops capture for
        every pair and both kinds until a human intervenes. That is unbounded loss, far worse than
        the one file.
        """
        failure = _read_failure(path)
        if failure is None:
            return True
        self._quarantine(path, failure)
        return False

    def _quarantine(self, path: Path, failure: Exception) -> None:
        """Rename an unreadable file aside, **never delete it**: it is evidence, and rows may still
        be salvageable from it by hand. The target is never clobbered — a rename would silently
        overwrite an earlier quarantine's bytes, and the same name does recur (the part sequence
        globs `<HH>.part*.parquet`, which `.corrupt` files do not match, so once every part of an
        hour has been quarantined the numbering restarts at 0000)."""
        dest = path.with_name(path.name + ".corrupt")
        seq = 0
        while dest.exists():
            seq += 1
            dest = path.with_name(f"{path.name}.corrupt.{seq}")
        path.rename(dest)
        logger.error(
            "quarantined unreadable file pair=%s kind=%s path=%s dest=%s error=%s",
            self._pair,
            self._kind,
            path,
            dest,
            failure,
        )

    def _recover(self) -> None:
        """Finish what a previous process left mid-merge, and read off disk which hours are closed.

        Runs at construction and must not raise: the daemon builds one writer per (pair, kind) before
        it connects, so anything escaping here stops capture entirely, on every restart. It merges
        nothing — that needs to know which hour is still in progress, which only the event stream can
        say (`_sweep`).
        """
        root = self._base_dir / self._pair / self._kind
        for tmp in root.rglob("*.tmp"):
            # Re-derivable: a merge tmp from the parts (still on disk), a part tmp from rows that
            # never reached a part file (the same loss as an unflushed buffer).
            if tmp.is_file():
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    # The one operation in `__init__` that could raise — and a read-only remount (the
                    # aftermath of the very ENOSPC condition DiskWatermark exists for) makes it do so
                    # for all 20 streams, on every restart: a crash loop, the worst outcome there is.
                    # A leftover tmp is re-derivable garbage. It is not worth the daemon.
                    logger.exception("could not remove a stale tmp pair=%s kind=%s path=%s", self._pair, self._kind, tmp)
        for merging_path in sorted(root.rglob("*.parquet.merging")):
            final_path = merging_path.with_name(merging_path.name.removesuffix(".merging"))
            try:
                if final_path.exists():
                    # Unreachable from any kill: the rename that publishes a final is atomic and is
                    # what consumes the merging file. So this is a hand-edit or a restored backup —
                    # and committing would overwrite a COMMITTED final and re-bless its sidecar. The
                    # one thing recovery must never do is overwrite what the invariant calls whole.
                    logger.error(
                        "an interrupted merge beside a committed final — left untouched pair=%s kind=%s path=%s",
                        self._pair,
                        self._kind,
                        merging_path,
                    )
                    continue
                failure = _read_failure(merging_path)
                if failure is not None:
                    # `_commit` hashes these bytes, unlinks the parts they came from and renames them
                    # onto the final — decoding nothing. So bit-rot (or a lying fsync, or a partial
                    # restore) here published an unreadable `<HH>.parquet` whose sha256 was minted
                    # FROM the rot: verify_manifest() returned True over it, the one corruption
                    # detector this dataset has certifying the corruption — while the parts that
                    # still held every row were deleted. Quarantine it (never delete) and fall
                    # through: the parts are untouched, so `_sweep` rebuilds the hour losslessly.
                    self._quarantine(merging_path, failure)
                    continue
                self._commit(merging_path, final_path)
                logger.warning("committed an interrupted merge pair=%s kind=%s path=%s", self._pair, self._kind, final_path)
            except Exception:
                logger.exception(
                    "could not commit an interrupted merge pair=%s kind=%s path=%s", self._pair, self._kind, final_path
                )
        # Which hours are closed. A `<HH>.parquet` is one, by the invariant. So is a `.merging` file
        # that would not commit above: its bytes may be the hour's only copy (the parts are already
        # unlinked), and an hour left open here could be re-opened by the live stream and its merge
        # would then sink straight over them. A held-spill (`.held`) closes nothing: it is
        # quarantine, and letting it seed the floor would drop every genuine row of the very hour
        # it names, on every restart.
        hours = []
        for path in (*root.rglob("*.parquet"), *root.rglob("*.parquet.merging")):
            if ".part" in path.name or ".held" in path.name:
                continue
            if (hour := _hour_of(path.parent, path.name.split(".")[0])) is None:
                continue
            if hour > _utcnow() + MAX_TS_AHEAD:
                # An hour that has not happened cannot have been committed: a future-dated segment is
                # nonsense, and it is what a single accepted garbage stamp leaves behind. Seeding the
                # floor from it drops EVERY genuine event, on EVERY restart, forever — the pair is
                # bricked until a human finds the file. So it is ignored, loudly, and never deleted.
                # (Under a lagging clock this merely ignores a real recent final, which is fail-safe:
                # the hour is re-opened, the new part lands beside the final, and `_merge_hour`'s
                # "ambiguous — left untouched" branch then preserves every byte of both.)
                logger.error("ignoring a future-dated segment pair=%s kind=%s path=%s", self._pair, self._kind, path)
                continue
            hours.append(hour)
        self._floor = max(hours) + timedelta(hours=1) if hours else None

    def _sweep(self, before: datetime) -> None:
        """Finalize every hour that still holds parts and is strictly before `before` — the hour of
        the first event this writer accepts, i.e. Kraken's own clock. Whatever a previous process
        left unfinished (the hour it died in, or hours it slept through) is closed here."""
        root = self._base_dir / self._pair / self._kind
        for hour_dir in sorted({path.parent for path in root.rglob("*.part*.parquet")}):
            for hh in sorted({path.name.split(".part")[0] for path in hour_dir.glob("*.part*.parquet")}):
                hour = _hour_of(hour_dir, hh)
                if hour is not None and hour < before:
                    # A restart-window early confirmation reaches `_merge_hour` from HERE, never
                    # through `_finalize_hour`, so it takes the same count (spec 00103 D2).
                    self._count_if_early(hour)
                    self._merge_hour(hour_dir, hh)

    def _write_manifest(self, source: Path, final_path: Path) -> None:
        """Write `<HH>.parquet.sha256` from `source`'s bytes — atomically and durably, so a kill can
        never leave a torn or empty sidecar that nothing would rewrite.

        Only ever called for a final this writer is itself publishing (`source` is the merging file
        whose bytes it is about to become). The sidecar of any other final is never touched: a digest
        that no longer matches its file is real corruption, and re-blessing it would destroy the only
        bit-rot detector this unbackfillable dataset has.
        """
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_path = final_path.with_name(final_path.name + ".sha256")
        tmp_path = manifest_path.with_name(manifest_path.name + ".tmp")
        tmp_path.write_text(f"{digest}  {final_path.name}\n")
        _replace_durably(tmp_path, manifest_path)

    def __enter__(self) -> SegmentWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def verify_manifest(path: Path) -> bool:
    """Recompute `path`'s sha256 and compare it against its `<path>.sha256` sidecar."""
    manifest_path = path.with_name(path.name + ".sha256")
    recorded = manifest_path.read_text().split() if manifest_path.exists() else []
    if not recorded:
        # An EMPTY or unparseable sidecar is a MISSING one, not a mismatch — a pre-T0036 process
        # killed inside its non-atomic `write_text` left a 0-byte file, and `split()[0]` then raised
        # IndexError out of the archive's verify_tree instead of reporting the hour.
        raise CaptureError(f"no manifest for {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest() == recorded[0]
