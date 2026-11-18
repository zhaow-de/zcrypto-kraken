"""Which hours are ready to reconcile, and the losses no witness can heal (spec 00050).

`reconcile.py` answers "what did the primary miss that the secondary saw?" — a question that needs a
LIVE secondary to answer it. This module answers the two questions it structurally cannot, because
its witness is dark too:

  * **`both_streams_silent`** — every book stream silent, on BOTH hosts, across ONE window.
  * **`total_loss`** — an hour that exists on neither mirror.

Both detectors are **unconditional**: they require no secondary activity, which is exactly why they
are the only ones that can see a correlated outage (spec 00050 constraint 4 — a correlated event hits
every host at the same exchange event, so redundancy buys nothing against it). Neither is ever
spliced: there is no witness. They are ledgered, booked into `residual_gap_seconds_total`, and paged,
but for a venue halt `classify_halt` proves the book carried through, which books to its own counter.

No I/O policy and no Typer here — the tree scan is filename-only (it never opens a parquet), and
`command.py` owns the reading, the minting and the exporter.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from cli.capture.errors import CaptureError

# An hour is finalized at H+1h and carried to the NAS by the pull cycle that follows; H+2h gives both
# a full cycle to land, so a settled hour is complete on both mirrors or genuinely missing from them.
SETTLE_HOURS = 2

# Past this, a complete secondary hour is minted even with the primary's still absent: an hour that
# has not arrived 6 h late is not in flight, and nothing arriving later can add coverage the secondary
# does not already have. Before it, a full-secondary mint would shadow primary data still on its way.
LATE_MINT_HOURS = 6

# `<HH>.parquet` and NOTHING else. The T0038 trap: a bare `*.parquet` glob also matches the live
# hour's `<HH>.part####.parquet` and, on the NAS mirror, thousands of already-merged stale part files
# rsync never deleted — so an hour would read as present, and complete, when it is neither.
FINAL_NAME = re.compile(r"^(\d{2})\.parquet$")


def settled_hours(*, now: datetime, window_hours: int) -> list[datetime]:
    """The trailing window of hours old enough to be complete on both mirrors, OLDEST first.

    Re-scanned every cycle: a residual hour may be healable in the next, and the LEDGER — not this list —
    stops a decided hour being re-decided. Every hour inherits `now`'s offset, so a non-UTC `now` is refused here.
    """
    if now.tzinfo is None:
        raise CaptureError(f"refusing to settle hours from {now!r}: a naive `now`, with no offset to check against UTC")
    if now.utcoffset() != timedelta(0):
        raise CaptureError(f"refusing to settle hours from {now!r}: a `now` at UTC offset {now.isoformat()[-6:]}, not at UTC")
    newest = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=SETTLE_HOURS)
    return [newest - timedelta(hours=i) for i in reversed(range(window_hours))]


def is_late(hour: datetime, *, now: datetime) -> bool:
    """At or past the late deadline (see `LATE_MINT_HOURS`)."""
    return now - hour >= timedelta(hours=LATE_MINT_HOURS)


def hour_path(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    """This hour's final under `root` — the pair spans two directory levels."""
    base, quote = pair.split("/")
    return root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"


def scan_hours(root: Path, kind: str) -> dict[str, set[datetime]]:
    """`{pair: {hour, ...}}` for every COMMITTED final of `kind` under `root`.

    Filenames only — nothing is opened. This is the whole availability picture the reconciler needs
    (which hours exist, which are missing, which mirror is freshest), and it must stay cheap: the raw
    mirrors are retained indefinitely (D7) and the loop budget assumes reconcile is not a third hash
    sweep of the archive on top of the two the pull step already does.
    """
    found: dict[str, set[datetime]] = {}
    for path in root.glob(f"*/*/{kind}/*/*/*/*.parquet"):
        match = FINAL_NAME.match(path.name)
        if match is None:
            continue
        parts = path.parts
        try:
            hour = datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(match.group(1)), tzinfo=UTC)
        except ValueError, OverflowError:  # a hand-made directory that is not a date — not ours, ignore it
            continue
        found.setdefault(f"{parts[-7]}/{parts[-6]}", set()).add(hour)
    return found


def newest_hour(*scans: dict[str, set[datetime]]) -> datetime | None:
    """The newest final across every scan — the mirror's own freshness, for `source_lag`."""
    hours = [hour for scan in scans for pair_hours in scan.values() for hour in pair_hours]
    return max(hours) if hours else None


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def us_from_dt(moment: datetime) -> int:
    """Exact microseconds since epoch — integer path only, no float rounding."""
    delta = moment - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def dt_from_us(us: int) -> datetime:
    """Exact inverse of `us_from_dt`."""
    return _EPOCH + timedelta(microseconds=int(us))


def us_array(stamps: Iterable[datetime] | np.ndarray) -> np.ndarray:
    """int64-μs view of `stamps`; an int64-μs ndarray passes through, datetimes convert exactly.

    An ndarray must ALREADY hold microseconds since epoch; any other dtype is refused rather than
    cast — the same two-scale trap `_message_ts` refuses on the sibling path. `astype(np.int64)` on a
    `datetime64[ns]` array yields NANOSECONDS, and those then sit in one `edges` array beside hour
    bounds that are always microseconds: measured there, the `ns` direction overflows `dt_from_us`
    while the `ms` direction shrinks a real 3300 s outage to 3.3 s and books a fabricated gap anchored
    in 1970 — silently, into a counter that can never be walked back. The exact conversion is the
    caller's (`Series.to_numpy().view(np.int64)` on a `Datetime(us)` column), so guessing it here is
    how the two scales meet.

    No defensive copy: an int64 array is returned as given. Every caller builds a fresh one.
    """
    if isinstance(stamps, np.ndarray):
        if stamps.dtype != np.int64:
            raise CaptureError(f"stamps ndarray is {stamps.dtype}, not int64 microseconds since epoch")
        return stamps
    return np.fromiter((us_from_dt(s) for s in stamps), dtype=np.int64)


def us_view(stamps: pl.Series) -> np.ndarray:
    """int64-μs view of a book segment's `ts` column, refusing any unit but microseconds.

    `.view(np.int64)` reads the column's OWN unit, so `us_array` cannot catch a wrong one — by then
    the array is already int64. Nothing downstream catches it either, because the caller books the
    fleet-dark residual BEFORE the heal path hands the same frame to `_message_ts`.

    The failure shape here is NOT `_message_ts`'s shrunken-gap one: `fleet_dark_windows` CLAMPS to
    the hour bounds, and a `ms` integer is 1000× too small for a microsecond bound, so every stamp
    falls BELOW `hour_start` and is discarded — measured, 0 of 360. The hour then reads as wholly
    dark rather than as a shortened gap, and a healthy, dense hour on three streams books 10800.0 s
    (3600 s × 3) of fabricated permanent loss into a counter that can never be walked back. This
    check is the only thing standing between a non-µs column and that booking.
    """
    if stamps.dtype != pl.Datetime("us", "UTC"):
        raise CaptureError(f"book `ts` column is {stamps.dtype}, not Datetime('us', 'UTC') — refusing to reconcile")
    if stamps.null_count():
        # A null becomes iNaT in the int64 view — the most negative int64 — fabricating a window that
        # spans the whole epoch and clamps every real message out of the timeline.
        raise CaptureError("null ts in a book segment — refusing to reconcile")
    return stamps.to_numpy().view(np.int64)


@dataclass(frozen=True)
class DarkWindow:
    """A window in which the whole fleet, on both hosts, recorded nothing at all."""

    start: datetime
    end: datetime
    seconds: float


def fleet_dark_windows(
    stamps: Iterable[datetime] | np.ndarray, *, hour_start: datetime, hour_end: datetime, min_seconds: float
) -> list[DarkWindow]:
    """Windows in which NOTHING was recorded — no pair, on either host.

    `stamps` is every book message timestamp of every pair from BOTH mirrors in this hour, merged.
    A window between two consecutive stamps is therefore one in which the whole fleet, on both hosts,
    was silent *simultaneously* — the INTERSECTION of the per-pair dual-silences, never their union.

    That distinction is the detector. Ten pairs each going quiet for 40 s at ten *different* moments
    of the hour is an ordinary thin market. Ten pairs going quiet for 40 s at the *same* moment, on
    two independent hosts holding two independent WS connections, is not a market — at depth 100 it
    is loss or the venue halting its books, which `classify_halt` tells apart. A per-pair silence *count*
    carries no window and cannot tell the two apart, so it would page on the benign one.

    The hour's own bounds are edges, for the same reason `find_book_gaps` requires them: a fleet that
    dies at :10 has no "next message" to pair with, and that crash shape is the whole point. Stamps
    outside the bounds (a late event that leaked in from an adjacent hour) are clamped away rather
    than allowed to fabricate a negative-length window.
    """
    arr = us_array(stamps)
    lo, hi = us_from_dt(hour_start), us_from_dt(hour_end)
    inside = np.unique(arr[(arr >= lo) & (arr <= hi)])  # sorted + deduped == sorted(set(...)), bounds inclusive as before
    edges = np.concatenate(([lo], inside, [hi]))
    # `/ 1e6`, never `* 1e-6`: the reciprocal is not exactly representable, so the product differs
    # from this quotient in ~30% of microsecond widths — and `timedelta.total_seconds()`, which this
    # must stay byte-identical to, is an integer division by 10**6.
    seconds = np.diff(edges).astype(np.float64) / 1e6
    # STRICTLY greater, matching `find_book_gaps`: a window of exactly the threshold is not a
    # gap on the way in, so booking it as residual here would be loss that was never healable.
    idx = np.nonzero(seconds > min_seconds)[0]
    return [DarkWindow(start=dt_from_us(edges[i]), end=dt_from_us(edges[i + 1]), seconds=float(seconds[i])) for i in idx]


def containing_dark_window(
    stamps: Iterable[datetime] | np.ndarray, window: DarkWindow, *, hour_start: datetime, hour_end: datetime
) -> DarkWindow | None:
    """ONE stream's own silence window containing `window` — the fleet-dark intersection.

    The intersection is the window in which EVERY stream was silent, so it is bounded by whichever
    stream went quiet last and whichever returned first. Booking it × stream count therefore books
    the binding stream's loss for all of them, and every other stream's surplus is booked nowhere —
    invisible, and invisible in the reassuring direction.

    Per-intersection-window, deliberately, rather than "every window this stream was dark for" —
    but this BOUNDS the thin-market false positive rather than excluding it, and the difference
    matters. The containing window is still the stream's own undecidable silence: a genuine fleet
    blip landing inside a thin stream's natural quiet drags that whole quiet window into a monotone
    counter driving the permanent-loss page. Constructed and measured: a real 31 s blip inside a
    600 s thin-pair quiet books 976.5 s against a truth of 372 s.

    What makes it safe TODAY is the universe, not the algorithm. Over all 24 hours of 2026-07-26,
    both mirrors, all 12 pairs: maximum natural silence 11.44 s, p99.9 ≤ 2.6 s, and ZERO windows
    above the 30 s threshold — so the containing window exceeds the intersection only by about twice
    the per-stream message spacing. The exposure grows if genuinely thin pairs enter the universe;
    re-measure that distribution before widening it.

    `stamps` is this stream's own timestamps across BOTH mirrors: a window the secondary witnessed
    is not this stream's silence, and booking it would double-count against the healed-gap path.

    Returns None when a stamp falls strictly inside `window` — impossible for a true intersection,
    since it is built from the union of every stream's stamps and such a stamp would have split it.
    Guarded rather than assumed: the caller must never book a window that does not exist.
    """
    # KNOWN LIMITATION -- accepted, do not 'fix' incidentally: `edges` starts at hour_start, so a
    # stream whose silence began in H-1 is measured from the boundary rather than its true start.
    # Measured at 0.045% of one event. NOT structurally bounded by min_gap_seconds -- H-1 books a
    # stream's tail only when the FLEET-dark window there clears the threshold, and that is bounded
    # above by the stream's own, so a thin pair can straddle far wider. What bounds it is the
    # measured silence distribution above. Closing it costs an H-1 segment read per pair on every
    # fleet-dark hour. Re-measure the share before changing this:
    # infra/runbooks/capture.md#cross-hour-straddle
    arr = us_array(stamps)
    lo, hi = us_from_dt(hour_start), us_from_dt(hour_end)
    inside = np.unique(arr[(arr >= lo) & (arr <= hi)])
    edges = np.concatenate(([lo], inside, [hi]))
    ws, we = us_from_dt(window.start), us_from_dt(window.end)
    # Consecutive edges partition the hour, so for a POSITIVE-width window only the interval
    # bracketing `window.start` can hold it: any earlier one ends at or before `ws`, any later one
    # starts after it. That interval's left edge is the LAST edge <= `ws`, which is what
    # `side="right"` picks — including when `ws` equals an interior stamp, where it lands on the
    # interval that STARTS there. Equivalent to the linear scan this replaced for every positive-width
    # window, measured over 25,358 constructions with zero divergences.
    #
    # Scoped deliberately: a ZERO-width or REVERSED window genuinely differs. On a zero-width one the
    # scan took the interval ENDING at that edge and this takes the one STARTING there; at `hour_end`
    # the scan returned a window where this returns None. Neither is reachable — `fleet_dark_windows`
    # emits only `seconds > min_seconds` — and the sole theoretical route is a negative
    # `--min-gap-seconds`, which nothing lower-bounds. Fix that bound, not this, if it ever matters.
    i = int(np.searchsorted(edges, ws, side="right")) - 1
    if i < 0 or i + 1 >= edges.size:
        return None
    a, b = int(edges[i]), int(edges[i + 1])
    if a <= ws and we <= b:
        return DarkWindow(start=dt_from_us(a), end=dt_from_us(b), seconds=(b - a) / 1e6)  # `/ 1e6`: see `fleet_dark_windows`
    return None


VENUE_SILENT = "venue_silent"
CAPTURE_DIVERGENT = "capture_divergent"
UNDETERMINED = "undetermined"

# An interior longer than this is not a sputtering venue -- it is healthy traffic separating two
# INDEPENDENT incidents, and treating it as evidence is bracket promotion (D2b). Measured, with the
# real event 3.0x inside it: 2026-08-20's interior is 98.497572 s. Re-measure before widening.
INTERIOR_MAX_SECONDS = 300.0


@dataclass(frozen=True)
class EpisodeVerdict:
    """Why the fleet went dark — TRIAGE, and an input to the booking only as a veto on a halt.

    `residual_gap_seconds_total` books ABSENCE of data; this says what the reconciler believes
    CAUSED the absence. Fusing the two would make a monotonic, unwalkbackable ledger depend on an
    inference, so the verdict reaches the log line and the record, and the booking reads it in the one
    direction that cannot lower that counter: `capture_divergent` keeps an hour's seconds as loss even
    where `classify_halt` proves a halt.
    """

    verdict: str
    interior_updates: int
    interior_snapshots: int
    interior_seconds: float
    pairs_agreeing: int
    pairs_skipped: int
    divergent_pairs: tuple[str, ...]


def classify_dark_episode(
    windows: Sequence[DarkWindow],
    mirror_rows: Mapping[str, Mapping[str, list[tuple[datetime, str]] | None]],
) -> EpisodeVerdict:
    """Was this episode the VENUE going quiet, or the fleet failing to record?

    EVIDENCE-WEIGHTING, never proof — and the honest statement of what it weighs is narrow. The
    capture writer stores Kraken's OWN message timestamp (`cli/capture/command.py` sets
    `ts = _parse_ts(entry["timestamp"])`), never local receipt time, so two independent hosts that
    receive the same message record byte-identical `ts` by construction and a host that was not
    receiving cannot manufacture one. Identical interior rows therefore establish that both hosts
    were receiving AT THOSE INSTANTS.

    They do NOT establish anything about the dark windows themselves: every interior event is a
    BRACKET for the silence on either side of it. What carries the verdict is that the interior is
    BRIEF — a synchronised failure and recovery on two independent hosts, aligned to the microsecond
    across a short window, is implausible in a way that "both hosts were simply fine for the twenty
    minutes between two separate incidents" is not. Brevity is load-bearing, which is why
    `INTERIOR_MAX_SECONDS` exists and why widening it is a design change, not a tuning knob.

    EXACTLY TWO windows, deliberately. With three or more there is no way to tell which gaps are the
    episode's own sputtering and which are healthy traffic separating unrelated incidents, and three
    successive review rounds each constructed a different false `venue_silent` out of multi-gap
    reasoning. Refusing to classify is the honest answer and costs nothing measurable: a `both_streams_silent`
    record carries one window or two in practice.
    """
    if len(windows) != 2:
        return EpisodeVerdict(UNDETERMINED, 0, 0, 0.0, 0, 0, ())
    lo, hi = windows[0].end, windows[1].start
    if hi < lo:
        return EpisodeVerdict(UNDETERMINED, 0, 0, 0.0, 0, 0, ())  # overlapping: not a timeline
    interior_seconds = (hi - lo).total_seconds()
    dark_seconds = windows[0].seconds + windows[1].seconds

    def inside(rows):
        return sorted(row for row in rows if lo <= row[0] <= hi)

    updates = snapshots = agreeing = skipped = 0
    divergent: list[str] = []
    for pair in sorted(mirror_rows):
        mirrors = mirror_rows[pair]
        primary, secondary = mirrors.get("primary"), mirrors.get("secondary")
        if primary is None or secondary is None:
            # Not a divergence -- there is nothing to compare. But NOT free either: this record is
            # decided ONCE (`_decided`), and a mirror landing next cycle could have shown divergence
            # that can then never demote it. Counted, and it caps the verdict below.
            skipped += 1
            continue
        inside_p, inside_s = inside(primary), inside(secondary)
        if not inside_p and not inside_s:
            continue  # this pair simply had nothing to say in the interior
        if inside_p == inside_s:
            agreeing += 1
            updates += sum(1 for _, kind in inside_p if kind == "update")
            snapshots += sum(1 for _, kind in inside_p if kind != "update")
        else:
            divergent.append(pair)

    if divergent:
        verdict = CAPTURE_DIVERGENT  # a finding in its own right: never masked by others agreeing
    elif skipped or not agreeing or not updates or interior_seconds >= dark_seconds or interior_seconds > INTERIOR_MAX_SECONDS:
        # Every path to "cannot tell", fail-closed: a pair whose mirror has not landed; no agreement;
        # snapshot-only; or an interior that does not look like one episode's sputtering -- either
        # because the silence does not dominate it, or because it is simply too long to be one.
        verdict = UNDETERMINED
    else:
        verdict = VENUE_SILENT
    return EpisodeVerdict(verdict, updates, snapshots, interior_seconds, agreeing, skipped, tuple(divergent))


VENUE_HALT = "venue_halt"

# A resync's snapshot follows the update that tripped it within the desync ladder's span -- to its reconnect
# rung plus one recovery tick (`cli/capture/desync_recovery.py`) -- and that update can reach capture late.
# A stream that resumes later than this before the hour's end could carry its snapshot into the next hour,
# which no examination of this hour reads.
RESUME_MARGIN_SECONDS = 300.0

# The shortest all-pairs quiet around a window that a halt must span. A halt stops every pair's matching for
# minutes; inside a shorter quiet, the market's own, a writer that dropped every pair's rows on both hosts leaves
# the same mirrors a halt does.
QUIET_SPAN_SECONDS = 240.0


@dataclass(frozen=True)
class HaltEvidence:
    """Whether a fleet-dark hour was the venue halting its books, and the counts that say why.

    The booking's evidence for a halt: it books the hour's seconds to the halt counter, and none to
    `residual_gap_seconds_total`, only when this holds.
    """

    streams: int
    streams_carried: int
    windows: int
    windows_bracketed: int
    trades_inside: int
    id_holes: int
    quiet_seconds: float

    @property
    def holds(self) -> bool:
        return (
            self.streams > 0
            and self.streams_carried == self.streams
            and self.windows_bracketed == self.windows
            and self.trades_inside == 0
            and self.id_holes == 0
            and self.quiet_seconds >= QUIET_SPAN_SECONDS
        )


def classify_halt(
    windows: Sequence[DarkWindow],
    stream_windows: Mapping[str, Sequence[DarkWindow]],
    book_rows: Mapping[str, Mapping[str, list[tuple[datetime, str]] | None]],
    trade_rows: Mapping[str, Mapping[str, list[tuple[datetime, int]] | None]],
    *,
    hour_end: datetime,
) -> HaltEvidence:
    """Did the venue halt its books across `windows`, losing nothing, or is the silence unproven?

    Three proofs, all from the mirrors alone, and all must hold:

      * **The book carried through.** Every booked stream is held by both mirrors, each resuming after each
        window on an update no later than `RESUME_MARGIN_SECONDS` before the hour's end, and on at least one
        of them no `snapshot` row lands from the stream's first window's start to that end. Capture checks
        every update's CRC against the book it carries and resubscribes on a mismatch, and a resubscribe or
        a reconnect writes a snapshot, so a resume with none after it is Kraken's own checksum accepting the
        book carried across the silence. That is the archive's standing ranks-1-10 attestation, no more: a
        change below rank 10 is outside it. The checksum vouches for what a host received, never for what it
        wrote, so the other host must come back on an update too: one that holds no file, never resumes, or
        comes back on a snapshot went dark by its own outage, and the window would be one host's dropped
        writes.
      * **Nothing traded.** No pair prints, on either mirror, inside its own booked silence
        (`stream_windows[pair]`, each containing a fleet window, or the fleet windows where it has none);
        every pair's trade ids step by exactly one across each fleet window they bracket, and some pair
        brackets every window. A writer that dropped rows while capture kept reading leaves the CRC
        whole, and this is what sees it wherever the venue matched across the drop.
      * **The market stood still.** Around each fleet window, the last print on any pair at or before its
        start and the first at or after its end, both in the hour's tapes, lie `QUIET_SPAN_SECONDS` or more
        apart: a writer that dropped every pair's rows on both hosts across a stretch no pair printed in
        passes the other two proofs, and only a quiet longer than the market's own tells a halt from it.

    A stream is `book_rows[pair]`'s two mirrors; `trade_rows[pair]`'s two tapes are unioned by trade id.
    """
    margin = timedelta(seconds=RESUME_MARGIN_SECONDS)

    def carried(mirrors: Mapping[str, list[tuple[datetime, str]] | None], own: Sequence[DarkWindow]) -> bool:
        both = [rows for rows in (mirrors.get("primary"), mirrors.get("secondary")) if rows is not None]
        if len(both) < 2 or not own:
            return False
        for rows in both:
            for w in own:
                at = min((ts for ts, _ in rows if ts >= w.end), default=None)
                if at is None or at > hour_end - margin:
                    return False
                if any(kind != "update" for ts, kind in rows if ts == at):
                    return False
        first = min(w.start for w in own)
        return any(all(kind == "update" for ts, kind in rows if ts >= first) for rows in both)

    carried_streams = sum(1 for pair, own in stream_windows.items() if carried(book_rows.get(pair) or {}, own))

    bracketed: set[int] = set()
    inside = holes = 0
    prints: list[datetime] = []
    for pair in sorted(trade_rows):
        first_seen: dict[int, datetime] = {}
        for rows in trade_rows[pair].values():
            for ts, trade_id in rows or ():
                first_seen.setdefault(trade_id, ts)
        tape = sorted((ts, trade_id) for trade_id, ts in first_seen.items())
        prints.extend(ts for ts, _ in tape)
        inside += sum(1 for ts, _ in tape for w in (stream_windows.get(pair) or windows) if w.start < ts < w.end)
        for i, w in enumerate(windows):
            before = [t for t in tape if t[0] <= w.start]
            after = [t for t in tape if t[0] >= w.end]
            if before and after:
                if after[0][1] - before[-1][1] == 1:
                    bracketed.add(i)
                else:
                    holes += 1

    def quiet(w: DarkWindow) -> float:
        last = max((ts for ts in prints if ts <= w.start), default=None)
        first = min((ts for ts in prints if ts >= w.end), default=None)
        return 0.0 if last is None or first is None else (first - last).total_seconds()

    return HaltEvidence(
        streams=len(stream_windows),
        streams_carried=carried_streams,
        windows=len(windows),
        windows_bracketed=len(bracketed),
        trades_inside=inside,
        id_holes=holes,
        quiet_seconds=min((quiet(w) for w in windows), default=0.0),
    )


def is_total_loss(
    hour: datetime,
    *,
    available: set[datetime],
    span: tuple[datetime, datetime] | None,
    alive_witness: set[datetime] | None = None,
) -> bool:
    """`total_loss`: the hour exists on NEITHER mirror, though the stream demonstrably ran both before
    and after it. `available` is the union of the hours both mirrors hold for this stream; `span` is
    its (earliest, latest), or None when the stream has no data at all.

    The "before" half is not in the spec's one-line rule ("absent from both mirrors while later hours
    exist") and it is load-bearing: without it, every hour of the window older than a pair's FIRST
    capture is "absent from both, and later hours exist" — so adding a pair to the universe would page
    a permanent-loss alarm for each of them and book them into a monotonic counter that can never be
    walked back. An absence is only a HOLE when real data brackets it on both sides; otherwise it is
    just a beginning.

    The trailing edge (both hosts dead and still dead) has no "after" and is deliberately not
    total_loss: an hour that has not arrived yet is indistinguishable from one that never will. That
    case belongs to `source_lag` and the two dead-men, which do not have to guess.

    `alive_witness` is the set of hours a CONTINUOUS sibling stream committed for the same pair — in
    practice the book hours, passed when judging `trades`. Bracketing alone is the right test for a
    continuous stream and the WRONG test for an event-driven one: book updates never stop, but trades
    are prints, and a quiet pair genuinely goes an hour without one. Caught in production on the first
    reconcile cycle (2026-07-14): LINK/EUR traded 8 times in hour 01 and 9 times in hour 04, had zero
    prints in hour 02, and was ledgered `total_loss` — permanent, unrecoverable loss — for an hour in
    which nothing happened. Its book final for that hour existed the whole time, which is exactly the
    proof that the connection was alive. So when the witness holds the hour, an absence here is not a
    hole; it is silence. When the witness is ALSO missing the hour, the stream really was dark, and it
    is a genuine hole. The book itself is the witness, so it is judged with `alive_witness=None`.
    """
    if span is None or hour in available:
        return False
    if alive_witness is not None and hour in alive_witness:
        return False
    return span[0] < hour < span[1]
