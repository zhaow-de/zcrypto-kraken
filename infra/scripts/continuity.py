"""Exit-bar gap measurement from SEGMENT-TIMESTAMP CONTINUITY.
T0003's bar is a consecutive-day run under a gap-time fraction. The daemon's own GapMonitor cannot
measure it: it is in-process, so it resets on restart, and it counts WebSocket downtime rather
than lost data, which is why it scored a crash at seconds when the hour it clobbered had lost
minutes (T0036). The bar is therefore derived from the archive itself.
Measured per BOOK stream only: books update continuously, so a silence IS downtime, while trades
legitimately go quiet and cannot measure uptime. A missing hour books the whole hour; a boundary
silence -- the interval from the last row of one hour to the first of the next -- is judged by the
same derived threshold as any other interval, and is the restart-clobber signature `trunc` counts.
A stream with too few intervals is reported UNMEASURED and FAILS the bar, because below that bound
the derived threshold degenerates (see MIN_POOL). A stream that clears the bound but whose tail
steepens too fast per decade is refused the same way: the same degeneracy arriving from repeat
outages rather than a small sample (see TAIL_RATIO_CUT).
Usage:  uv run python infra/scripts/continuity.py <segments-root> [--since YYYY-MM-DD]
            [--kind book] [--overlay <reconciled-root>]
Run it against a PULLED copy, never the live dir the daemon is writing. `--overlay` adds a
separate, clearly labelled canonical report beside the raw one. Exit-bar isolation (spec 00050):
the raw report is the ONLY gate instrument and the canonical one never prints the verdict line,
because an overlay heals gaps by design and would otherwise let a raw-capture regression bank a
clean run -- the defect class the bar exists to catch.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import re
from pathlib import Path

import polars as pl

FINAL = re.compile(r"^\d{2}$")

# D6: below this many pooled intervals `quantile(0.9999)` IS the maximum, so a derived threshold
# would be ten times the worst outage and the instrument blind by construction. Such a stream is
# reported UNMEASURED rather than scored. tests/test_infra_continuity.py pins the bound by measuring
# polars rather than trusting this comment.
MIN_POOL = 5002

# MIN_POOL tolerates only ONE outage-scale interval. From two similar outages upward the pool clears
# the bound while p99.99 lands ON an outage, so the derived threshold inflates and the instrument
# books zero over genuinely missing data -- the false GREEN this script exists to prevent. A
# contaminated tail is refused rather than trusted, judged by how steeply the pool's tail rises per
# decade of quantiles.
#
# The cut is the per-decade quantile ratio of a Pareto tail at alpha = 1, the infinite-mean boundary
# no physical spacing distribution crosses; contamination from same-scale repeat outages measures
# well above it.
TAIL_RATIO_CUT = 10.0
# The ratios' denominator floor, and not a new magic number: it is 5.0 / 10, the spacing scale below
# which the threshold floor above already declares steepness irrelevant. Needed because an
# ultra-bursty pool legitimately has p99.9 = 0 (same-millisecond bursts), which would otherwise
# refuse a healthy stream.
RATIO_FLOOR_S = 0.5

HOUR = dt.timedelta(hours=1)


def tail_steepness(pool: pl.Series) -> tuple[float, float]:
    """(p99.99/p99.9, p99.9/p99), each denominator floored at RATIO_FLOOR_S.
    Nearest interpolation, the same basis as the threshold itself. Two chained decades because one
    does not cover the range: the first ratio catches p99.99 landing on an outage, but once the
    outage count grows p99.9 is contaminated too and reads about 1, and from there only the second
    still spans the cliff.
    """
    q99 = float(pool.quantile(0.99) or 0.0)
    q999 = float(pool.quantile(0.999) or 0.0)
    q9999 = float(pool.quantile(0.9999) or 0.0)
    return q9999 / max(q999, RATIO_FLOOR_S), q999 / max(q99, RATIO_FLOOR_S)


def tail_depth(pool: pl.Series) -> int:
    """How many pooled intervals reach p99.99 -- how many data points the threshold rests on.
    00079/D5: TRANSPARENCY ONLY, never a gate. Depth is provably not a contamination detector --
    the count at or above p99.99 is a deterministic function of n rather than of contamination,
    and tests/test_infra_continuity.py pins that equality, so promoting depth into a gate means
    deleting the test that disproves it. What it IS good for is saying out loud how few intervals
    set a stream's threshold.
    """
    return int((pool >= pool.quantile(0.9999)).sum())


@dataclasses.dataclass(frozen=True)
class StreamTimeline:
    """A stream's hours read as ONE timeline (D1), not as independent files.
    `pool` is the threshold sample: intra-row diffs plus the crossings between contiguous hours,
    so a boundary is judged by the same measured density as any other interval. `intra` books
    silence; `boundaries` books and counts truncations. A crossing appears in `pool` for the
    statistic and in `boundaries` for booking but never in `intra` -- that separation is what
    keeps it from being booked twice.
    """

    pool: pl.Series
    intra: pl.Series
    boundaries: list[tuple[float, str]]
    missing_hours: int
    span_hours: int
    genesis_skipped: bool


def stream_timeline(segs: list[tuple[dt.datetime, Path]], *, genesis_hour: dt.datetime) -> StreamTimeline:
    """Build the interval model for one stream's (already `--since`-filtered, sorted) segments."""
    intra_parts: list[pl.Series] = []
    crossings: list[float] = []
    boundaries: list[tuple[float, str]] = []
    missing_hours = 0
    prev_hi: dt.datetime | None = None
    prev_hour: dt.datetime | None = None

    for h, p in segs:
        ts = pl.read_parquet(p, columns=["ts"])["ts"]
        lo, hi = ts.min(), ts.max()
        intra_parts.append(ts.diff().drop_nulls().dt.total_microseconds() / 1e6)
        if prev_hour is None:
            # D5: the genesis hour begins mid-hour by construction, so its head measures the
            # stream's birth, not a gap. Any other first-in-window hour IS measurable (D10).
            if h != genesis_hour:
                boundaries.append(((lo - h).total_seconds(), "edge_head"))
        else:
            missing = int((h - prev_hour) / HOUR) - 1
            crossing = (lo - prev_hi).total_seconds()
            if missing == 0:
                crossings.append(crossing)
                boundaries.append((crossing, "crossing"))
            else:
                # D4: the whole hours are booked at 3600 each; only the excess -- the real tail+head
                # silence bracketing the hole -- is a measurement, and it never joins the sample.
                missing_hours += missing
                boundaries.append((crossing - 3600.0 * missing, "excess"))
        prev_hi, prev_hour = hi, h

    if prev_hour is not None:
        boundaries.append(((prev_hour + HOUR - prev_hi).total_seconds(), "edge_tail"))

    intra = pl.concat(intra_parts) if intra_parts else pl.Series([], dtype=pl.Float64)
    pool = pl.concat([intra, pl.Series(crossings, dtype=pl.Float64)]) if crossings else intra
    span_hours = int((prev_hour - segs[0][0]) / HOUR) + 1 if segs else 0
    return StreamTimeline(
        pool=pool,
        intra=intra,
        boundaries=boundaries,
        missing_hours=missing_hours,
        span_hours=span_hours,
        genesis_skipped=bool(segs) and segs[0][0] == genesis_hour,
    )


def segments(root: Path, kind: str) -> dict[str, list[tuple[dt.datetime, Path]]]:
    out: dict[str, list[tuple[dt.datetime, Path]]] = {}
    for p in sorted(root.glob(f"*/*/{kind}/*/*/*/*.parquet")):
        if not FINAL.match(p.stem):
            continue  # skip *.part*
        parts = p.parts
        pair = f"{parts[-7]}/{parts[-6]}"
        y, m, d = parts[-4], parts[-3], parts[-2]
        hour = dt.datetime(int(y), int(m), int(d), int(p.stem), tzinfo=dt.UTC)
        out.setdefault(pair, []).append((hour, p))
    return out


def _canonical_streams(root: Path, overlay_root: Path, kind: str) -> dict[str, list[tuple[dt.datetime, Path]]]:
    """The reconciled-first view of `root`, healed by `overlay_root` (see `cli.archive.reader`)."""
    # Imported here, not at module top: the default raw-only invocation is the T0003 exit-bar
    # instrument and must keep running on a host with only stdlib + polars — the cli package is
    # needed only when `--overlay` is passed.
    from cli.archive.reader import canonical_segments

    out: dict[str, list[tuple[dt.datetime, Path]]] = {}
    for pair, hour, p in canonical_segments(root, overlay_root, kind=kind):
        out.setdefault(pair, []).append((hour, p))
    return out


def report(
    streams: dict[str, list[tuple[dt.datetime, Path]]],
    *,
    since: dt.datetime,
    quiet: bool,
    show_exit_bar: bool,
    genesis: dict[str, dt.datetime],
) -> int:
    """Print the per-pair continuity table and summary; returns 1 when there is nothing to measure.
    `show_exit_bar` gates ONLY the verdict line: the raw report always gets it and the canonical
    `--overlay` report never does, so an overlay run can never bank an exit-bar PASS (spec 00050).
    It is required with no default, so a caller must SAY which report it is -- a defaulted True
    would let a forgotten flag silently bank one.
    `genesis` maps each pair to its earliest hour in the UNFILTERED tree, so a `--since` window
    cannot promote a later hour into D5's free pass.
    """
    if not streams:
        print("no segments found")
        return 1

    worst = 0.0
    # `thresh_s` is printed because it is DERIVED per pair, not configured: a 0.0000% means either
    # "no silence" or "the threshold is wide enough that nothing counts as silence", and only the
    # number beside it tells an operator which. `tail` is how many pooled intervals the derived
    # threshold rests on -- diagnostic only; the gate is `tail_steepness`.
    print(
        f"{'pair':<10} {'hours':>6} {'missing':>8} {'trunc':>6} {'n':>9} {'tail':>6} {'thresh_s':>12} {'gap_s':>10} {'covered_s':>11} {'gap%':>8}"
    )
    print("-" * 95)
    totals = []
    unmeasured: list[str] = []
    steepened: list[str] = []
    for pair, segs in sorted(streams.items()):
        segs = [(h, p) for h, p in segs if h >= since]
        if not segs:
            continue
        segs.sort()
        tl = stream_timeline(segs, genesis_hour=genesis[pair])

        gap = tl.missing_hours * 3600.0
        n = len(tl.pool)
        # Below the bound the p99.99 IS the maximum, so the threshold would be ten times the worst
        # outage: report the stream unmeasurable rather than score it against a blind number. Above
        # the bound the same blindness returns from two similar outages, so a tail steepening more
        # than TAIL_RATIO_CUT per decade is refused too (00079/D1).
        #
        # Accepted residual (00079/D6), a conscious drop rather than a deferral: once enough of the
        # window is outage, p99 itself is contaminated, both ratios read about 1 and this gate goes
        # blind -- but that regime needs the window to be overwhelmingly outage by wall time, so the
        # `n` printed beside the span is the eyeball check. The truncated-hours count is explicitly
        # NOT a backstop: it tests against the same contaminated threshold.
        measured = n >= MIN_POOL and max(tail_steepness(tl.pool)) < TAIL_RATIO_CUT
        # Printed on UNMEASURED rows too -- a refused stream shows no threshold to judge, so the
        # depth is the only fragility signal left on that row. An empty pool has no quantile.
        depth: int | str = tail_depth(tl.pool) if n else ""
        thresh = max(float(tl.pool.quantile(0.9999) or 0) * 10, 5.0) if measured else 0.0
        trunc = 0
        if measured:
            gap += float(tl.intra.filter(tl.intra > thresh).sum() or 0.0)
            for secs, _kind in tl.boundaries:
                if secs > thresh:
                    gap += secs
                    trunc += 1

        covered = tl.span_hours * 3600.0
        if not measured:
            unmeasured.append(pair)
            if n >= MIN_POOL:
                steepened.append(pair)  # cleared the bound, refused by the tail-steepness gate
            if not quiet:
                print(
                    f"{pair:<10} {tl.span_hours:>6} {tl.missing_hours:>8} {'-':>6} {n:>9} {depth:>6} {'UNMEASURED':>12} {'':>10} {covered:>11.0f} {'':>8}"
                )
            continue

        pct = 100.0 * gap / covered if covered else 0.0
        worst = max(worst, pct)
        totals.append((pair, tl.span_hours, tl.missing_hours, trunc, gap, covered, pct))
        if not quiet:
            mark = " genesis" if tl.genesis_skipped else ""
            print(
                f"{pair:<10} {tl.span_hours:>6} {tl.missing_hours:>8} {trunc:>6} {n:>9} {depth:>6} {thresh:>12.1f} {gap:>10.1f} {covered:>11.0f} {pct:>7.4f}%{mark}"
            )

    # 00079/D4: two refusal reasons, named separately -- "too small to calibrate" and "calibrated on
    # a tail that is probably the outage" are different problems with different next actions.
    # Printed whenever ANY stream was refused, not only when nothing was measurable: in production a
    # contaminated stream almost always sits beside measured ones, and that is exactly where the
    # reason is least guessable.
    #
    # The prefix is `unmeasured: `, the same word the table prints in those rows' cell, so the note
    # maps onto its rows at a glance -- and NOT the plural form, which
    # tests/test_continuity_overlay.py asserts a canonical report never emits.
    if unmeasured:
        under = len(unmeasured) - len(steepened)
        if under:
            print(f"unmeasured: {under} stream(s) under the {MIN_POOL}-interval bound")
        if steepened:
            print(
                f"unmeasured: {len(steepened)} stream(s) whose spacing tail steepens more than "
                f"{TAIL_RATIO_CUT:.0f}x across a decade of quantiles -- the threshold sample is not trustworthy"
            )

    if not totals:
        # Nothing measurable. Two different situations, and only one of them may stay silent:
        # streams existed but none could be self-calibrated (D6 -- the reason is named above, and
        # FAIL), versus no segments at all (nothing was measured, so nothing may bank OR fail a
        # verdict).
        if unmeasured:
            if show_exit_bar:
                print(f"  EXIT BAR (<0.1% gap time): *** FAIL *** (unmeasured streams: {len(unmeasured)})")
            return 0
        # `--since` filters per stream at the top of the loop, long after the empty-tree guard, so a
        # window that excludes every hour reaches the TOTAL row with nothing to divide by. Answering
        # "nothing here" beats a ZeroDivisionError, which reads as a broken tool rather than an empty
        # window -- and it must not print an EXIT BAR, because nothing was measured.
        print("no segments in the requested window")
        return 1

    print("-" * 95)
    tg = sum(t[4] for t in totals)
    tc = sum(t[5] for t in totals)
    tt = sum(t[3] for t in totals)
    tm = sum(t[2] for t in totals)
    # No threshold and no tail depth on the TOTAL row: both are per pair, and summing or averaging
    # either would invent a number that describes no stream.
    print(f"{'TOTAL':<10} {'':>6} {tm:>8} {tt:>6} {'':>9} {'':>6} {'':>12} {tg:>10.1f} {tc:>11.0f} {100.0 * tg / tc:>7.4f}%")
    print()
    print(f"  worst single stream : {worst:.4f}%")
    if show_exit_bar:
        # D6: an unmeasurable stream must not be silently skipped -- a bar that ignores what it
        # could not measure is the same false-green the instrument exists to prevent.
        if unmeasured:
            print(f"  EXIT BAR (<0.1% gap time): *** FAIL *** (unmeasured streams: {len(unmeasured)})")
        else:
            print("  EXIT BAR (<0.1% gap time): " + ("PASS" if worst < 0.1 else "*** FAIL ***"))
    # T0036: the truncated-hour signature this counts.
    print(f"  truncated hours: {tt}  -- MUST be 0 after the fix")
    return 0


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("root", type=Path)
    ap.add_argument("--since", default=None, help="YYYY-MM-DD")
    ap.add_argument("--kind", default="book")
    ap.add_argument("--quiet", action="store_true", help="only the summary")
    ap.add_argument(
        "--overlay",
        type=Path,
        default=None,
        help="reconciled-root: also print a SEPARATE canonical (reconciled-first) report -- "
        # T0003 / spec 00050: the exit-bar isolation this flag preserves.
        "informational only, never the exit-bar instrument",
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    add_args(ap)
    return ap


def main() -> int:
    a = build_parser().parse_args()

    since = dt.datetime.fromisoformat(a.since).replace(tzinfo=dt.UTC) if a.since else dt.datetime.min.replace(tzinfo=dt.UTC)
    raw = segments(a.root, a.kind)
    # D5: genesis comes from the UNFILTERED tree -- a --since window must not promote a later hour
    # into the genesis free pass.
    genesis = {pair: min(h for h, _ in segs) for pair, segs in raw.items()}
    rc = report(raw, since=since, quiet=a.quiet, show_exit_bar=True, genesis=genesis)

    if a.overlay is not None:
        # Printed even when the raw report came up empty (rc 1): an empty raw mirror is exactly when
        # the overlay's healed hours matter most. The exit status stays the RAW report's — it is the
        # T0003 instrument; the canonical view is informational.
        print()
        print(
            f"=== CANONICAL VIEW (reconciled-first, healed from {a.overlay}) -- informational only, NOT the exit-bar instrument ==="
        )
        canonical = _canonical_streams(a.root, a.overlay, a.kind)
        report(
            canonical,
            since=since,
            quiet=a.quiet,
            show_exit_bar=False,
            genesis={pair: min(h for h, _ in segs) for pair, segs in canonical.items()},
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
