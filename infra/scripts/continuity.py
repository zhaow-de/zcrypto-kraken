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
import datetime as dt
import re
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments

FINAL = re.compile(r"^\d{2}$")


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
    out: dict[str, list[tuple[dt.datetime, Path]]] = {}
    for pair, hour, p in canonical_segments(root, overlay_root, kind=kind):
        out.setdefault(pair, []).append((hour, p))
    return out


def report(
    streams: dict[str, list[tuple[dt.datetime, Path]]], *, since: dt.datetime, quiet: bool, show_exit_bar: bool = True
) -> int:
    """Print the per-pair continuity table + summary. Returns 0, or 1 if `streams` is empty.

    `show_exit_bar` gates ONLY the `EXIT BAR (<0.1% gap time): PASS/FAIL` verdict line: the raw
    report (the default call) always gets it; the `--overlay` canonical report never does, so an
    overlay run can never bank a T0003 exit-bar PASS (spec 00050, exit-bar isolation).
    """
    if not streams:
        print("no segments found")
        return 1

    HOUR = dt.timedelta(hours=1)
    worst = 0.0
    print(f"{'pair':<10} {'hours':>6} {'missing':>8} {'trunc':>6} {'gap_s':>10} {'covered_s':>11} {'gap%':>8}")
    print("-" * 66)
    totals = []
    for pair, segs in sorted(streams.items()):
        segs = [(h, p) for h, p in segs if h >= since]
        if not segs:
            continue
        segs.sort()
        first_hour, last_hour = segs[0][0], segs[-1][0]
        have = {h for h, _ in segs}

        # 1. missing hours across the observed span
        span_hours = int((last_hour - first_hour) / HOUR) + 1
        missing = span_hours - len(have)
        gap = missing * 3600.0

        # 2. head/tail truncation, and 3. intra-hour silence
        trunc = 0
        all_diffs = []
        per_hour = []
        for h, p in segs:
            ts = pl.read_parquet(p, columns=["ts"])["ts"]
            lo, hi = ts.min(), ts.max()
            head = (lo - h).total_seconds()
            tail = (h + HOUR - hi).total_seconds()
            if head > 5:
                trunc += 1
            gap += max(head, 0.0) + max(tail - 1.0, 0.0)  # tail: allow the final second
            d = ts.diff().drop_nulls()
            per_hour.append(d)
            all_diffs.append(d)

        # threshold from the data, not guessed: p99.99 of inter-row spacing, floored at 5 s
        if all_diffs:
            diffs = pl.concat(all_diffs)
            secs = diffs.dt.total_microseconds() / 1e6
            thresh = max(float(secs.quantile(0.9999) or 0) * 10, 5.0)
            silence = float(secs.filter(secs > thresh).sum() or 0.0)
            gap += silence

        covered = span_hours * 3600.0
        pct = 100.0 * gap / covered if covered else 0.0
        worst = max(worst, pct)
        totals.append((pair, span_hours, missing, trunc, gap, covered, pct))
        if not quiet:
            print(f"{pair:<10} {span_hours:>6} {missing:>8} {trunc:>6} {gap:>10.1f} {covered:>11.0f} {pct:>7.4f}%")

    print("-" * 66)
    tg = sum(t[4] for t in totals)
    tc = sum(t[5] for t in totals)
    tt = sum(t[3] for t in totals)
    tm = sum(t[2] for t in totals)
    print(f"{'TOTAL':<10} {'':>6} {tm:>8} {tt:>6} {tg:>10.1f} {tc:>11.0f} {100.0 * tg / tc:>7.4f}%")
    print()
    print(f"  worst single stream : {worst:.4f}%")
    if show_exit_bar:
        print("  EXIT BAR (<0.1% gap time): " + ("PASS" if worst < 0.1 else "*** FAIL ***"))
    print(f"  truncated hours (T0036 signature): {tt}  -- MUST be 0 after the fix")
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
        "informational only, never the T0003 exit-bar instrument (exit-bar isolation, spec 00050)",
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    add_args(ap)
    return ap


def main() -> int:
    a = build_parser().parse_args()

    since = dt.datetime.fromisoformat(a.since).replace(tzinfo=dt.UTC) if a.since else dt.datetime.min.replace(tzinfo=dt.UTC)
    streams = segments(a.root, a.kind)
    rc = report(streams, since=since, quiet=a.quiet)
    if rc != 0:
        return rc

    if a.overlay is not None:
        print()
        print(
            f"=== CANONICAL VIEW (reconciled-first, healed from {a.overlay}) "
            f"-- informational only, NOT the T0003 exit-bar instrument ==="
        )
        canonical = _canonical_streams(a.root, a.overlay, a.kind)
        report(canonical, since=since, quiet=a.quiet, show_exit_bar=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
