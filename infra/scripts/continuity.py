"""Exit-bar gap measurement from SEGMENT-TIMESTAMP CONTINUITY.

T0003's bar is "capture daemon >=7 consecutive days with <0.1% gap time". The daemon's own
GapMonitor cannot measure this: it is in-process (resets on restart) and it counts WebSocket
downtime, so it scored the 2026-07-13 crash at ~5.5 s when the hour it clobbered actually lost
270 s -- a ~50x undercount (T0036). The bar therefore has to be derived from the archive itself.

Three kinds of gap, measured per BOOK stream (books update continuously, so a silence IS downtime;
trades legitimately go quiet, so they cannot measure uptime):

  1. MISSING hour   -- no segment at all              -> 3600 s
  2. HEAD/TAIL truncation -- first row late into its hour, or last row early
                              (this is exactly the T0036 restart-clobber signature)
  3. INTRA-hour silence   -- consecutive rows further apart than a threshold derived
                              from the data itself (not guessed)

Usage:  uv run python infra/scripts/continuity.py <segments-root> [--since YYYY-MM-DD] [--kind book]
                                                    [--overlay <reconciled-root>]

This is the T0003 exit-bar instrument (and the T0036 post-deploy check): run it against a
pulled copy of the capture tree, never against the live dir the daemon is writing.

`--overlay <reconciled-root>` adds a SEPARATE, clearly-labeled canonical (reconciled-first) report
alongside the raw one, for comparison. Exit-bar isolation (spec 00050): the raw report is the ONLY
T0003 gate instrument and always runs, unaffected; the canonical report never prints the EXIT BAR
verdict line, because an overlay heals gaps by design and would otherwise let a raw-capture
regression bank a "clean" run -- exactly the defect class the bar exists to catch.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import re
from pathlib import Path

import polars as pl

FINAL = re.compile(r"^\d{2}$")

# D6: with polars' default nearest interpolation, quantile(0.9999) returns the element at
# round(0.9999*(n-1)) -- which IS the maximum while n <= 5001, so the derived threshold would be
# 10x the worst outage and the instrument blind by construction. Below this many pooled intervals a
# stream is reported UNMEASURED rather than scored. The bound is pinned by
# tests/test_infra_continuity.py, which measures polars rather than trusting this comment.
MIN_POOL = 5002

HOUR = dt.timedelta(hours=1)


@dataclasses.dataclass(frozen=True)
class StreamTimeline:
    """A stream's hours read as ONE timeline (D1), not as independent files.

    `pool` is the threshold sample: intra-row diffs plus the crossings between contiguous hours, so
    a boundary is judged by the same measured density as any other interval. `intra` books silence;
    `boundaries` books and counts truncations. A crossing therefore appears in `pool` (for the
    statistic) and in `boundaries` (for booking) but never in `intra` -- that separation is what
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
    """Print the per-pair continuity table + summary. Returns 0, or 1 when there is nothing to measure -- `streams` empty, or `--since` excluding every hour of every stream.

    `show_exit_bar` gates ONLY the `EXIT BAR (<0.1% gap time): PASS/FAIL` verdict line: the raw
    report always gets it; the `--overlay` canonical report never does, so an overlay run can never
    bank a T0003 exit-bar PASS (spec 00050, exit-bar isolation). Required, with no default, so a
    future caller must SAY which report it is — a defaulted True would let a forgotten flag silently
    bank an exit bar.

    `genesis` maps each pair to its earliest hour in the UNFILTERED tree, so a `--since` window
    cannot promote a later hour into D5's free pass.
    """
    if not streams:
        print("no segments found")
        return 1

    worst = 0.0
    # `thresh_s` is printed because it is DERIVED per pair (see below), not configured: a 0.0000%
    # means "no silence" or "the threshold is wide enough that nothing counts as silence", and only
    # the number beside it tells an operator which.
    print(
        f"{'pair':<10} {'hours':>6} {'missing':>8} {'trunc':>6} {'n':>9} {'thresh_s':>12} {'gap_s':>10} {'covered_s':>11} {'gap%':>8}"
    )
    print("-" * 88)
    totals = []
    unmeasured: list[str] = []
    for pair, segs in sorted(streams.items()):
        segs = [(h, p) for h, p in segs if h >= since]
        if not segs:
            continue
        segs.sort()
        tl = stream_timeline(segs, genesis_hour=genesis[pair])

        gap = tl.missing_hours * 3600.0
        n = len(tl.pool)
        # D6: below the bound the p99.99 IS the maximum, so the threshold would be 10x the worst
        # outage. Report the stream as unmeasurable rather than score it against a blind number.
        measured = n >= MIN_POOL
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
            if not quiet:
                print(
                    f"{pair:<10} {tl.span_hours:>6} {tl.missing_hours:>8} {'-':>6} {n:>9} {'UNMEASURED':>12} {'':>10} {covered:>11.0f} {'':>8}"
                )
            continue

        pct = 100.0 * gap / covered if covered else 0.0
        worst = max(worst, pct)
        totals.append((pair, tl.span_hours, tl.missing_hours, trunc, gap, covered, pct))
        if not quiet:
            mark = " genesis" if tl.genesis_skipped else ""
            print(
                f"{pair:<10} {tl.span_hours:>6} {tl.missing_hours:>8} {trunc:>6} {n:>9} {thresh:>12.1f} {gap:>10.1f} {covered:>11.0f} {pct:>7.4f}%{mark}"
            )

    if not totals:
        # `--since` filters per stream at the top of the loop, long after the empty-tree guard, so a
        # window that excludes every hour reaches the TOTAL row with nothing to divide by. Answering
        # "nothing here" beats a ZeroDivisionError, which reads as a broken tool rather than an empty
        # window -- and it must not print an EXIT BAR, because nothing was measured.
        print("no segments in the requested window")
        return 1

    print("-" * 88)
    tg = sum(t[4] for t in totals)
    tc = sum(t[5] for t in totals)
    tt = sum(t[3] for t in totals)
    tm = sum(t[2] for t in totals)
    # No threshold on the TOTAL row: it is per pair, and averaging thresholds would invent a number.
    print(f"{'TOTAL':<10} {'':>6} {tm:>8} {tt:>6} {'':>9} {'':>12} {tg:>10.1f} {tc:>11.0f} {100.0 * tg / tc:>7.4f}%")
    print()
    print(f"  worst single stream : {worst:.4f}%")
    if show_exit_bar:
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
