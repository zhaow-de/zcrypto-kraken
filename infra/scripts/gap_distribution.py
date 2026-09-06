"""Pin `--min-gap-seconds` from real cross-host data (spec 00050 Task 12, T0039).
The deployed 30 s is validated by a soak this harness ran; the harness stays reusable
for re-pinning. Kraken coalesces book updates per WebSocket connection, so the two hosts record
different message sequences for the same pair and a coalescing artifact can make the primary
appear silent while the secondary shows activity inside that silence. A threshold below that
apparent-silence tail would let the reconciler splice a secondary block into an hour the primary
never lost -- an unaudited swap into an archive that cannot be backfilled -- so it must sit ABOVE
the measured tail.
Measured over the soaked RAW mirrors, never the overlay, with the reconciler's own
`find_book_gaps` at a 1 s probe floor: below the region that pins the threshold, so the whole
approach to the tail is visible, while excluding sub-second coalescing jitter that is irrelevant
and quadratic to enumerate.
    uv run python infra/scripts/gap_distribution.py <primary-root> <secondary-root>
        [--since YYYY-MM-DD] [--probe-seconds 1.0] [--review-ceiling 120] [--top 20]
Run it against PULLED copies, never the live dirs. The suggested threshold is decision-support:
the largest windows must be classified by hand first, because a real outage counted as quiescence
pushes the threshold too high and blinds the detector, and a coalescing artifact excluded pushes
it too low and licenses a phantom splice.
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

try:  # cli is an installed package in the deploy image; a repo checkout needs the root on the path
    from cli.archive.reconcile import find_book_gaps
    from cli.archive.settle import hour_path, scan_hours
except ModuleNotFoundError:  # running from infra/scripts/ in a checkout where cli is not installed
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from cli.archive.reconcile import find_book_gaps
    from cli.archive.settle import hour_path, scan_hours

GapObs = tuple[str, datetime, float]  # (pair, hour, primary-silence seconds the secondary witnessed)


def observe_gaps(
    primary_root: Path,
    secondary_root: Path,
    *,
    since: datetime | None = None,
    probe_seconds: float = 1.0,
) -> tuple[list[GapObs], list[tuple[str, datetime, str]]]:
    """Every primary book-silence window the secondary witnessed, across hours BOTH mirrors hold.
    Only the intersection of the two mirrors' hours is used: a pre-secondary hour would otherwise
    register as one hour-long primary-only gap and poison the distribution with data about
    coverage rather than coalescing.
    A per-hour failure is ISOLATED. `find_book_gaps` raises on a non-monotonic stream and a read
    can raise on a truncated final, so letting one anomalous hour abort would throw away the whole
    soak; each is recorded in `skipped` with its (pair, hour, error) and surfaced, because a
    silently dropped hour would read as clean.
    """
    pri_hours = scan_hours(primary_root, "book")
    sec_hours = scan_hours(secondary_root, "book")

    obs: list[GapObs] = []
    skipped: list[tuple[str, datetime, str]] = []
    for pair in sorted(set(pri_hours) & set(sec_hours)):
        for hour in sorted(pri_hours[pair] & sec_hours[pair]):
            if since is not None and hour < since:
                continue
            try:
                cols = ["ts", "type"]
                primary = pl.read_parquet(hour_path(primary_root, pair, "book", hour), columns=cols)
                secondary = pl.read_parquet(hour_path(secondary_root, pair, "book", hour), columns=cols)
                for gap in find_book_gaps(
                    primary,
                    secondary,
                    min_gap_seconds=probe_seconds,
                    hour_start=hour,
                    hour_end=hour + timedelta(hours=1),
                ):
                    obs.append((pair, hour, gap.seconds))
            except Exception as exc:  # noqa: BLE001 -- isolate a bad hour; the whole point is not to lose 48h to one
                skipped.append((pair, hour, f"{type(exc).__name__}: {exc}"))
    return obs, skipped


def _percentile(sorted_seconds: list[float], p: float) -> float:
    """Nearest-rank percentile of an already-sorted list (p in [0, 100])."""
    if not sorted_seconds:
        raise ValueError("no data")
    rank = math.ceil(p / 100.0 * len(sorted_seconds))
    return sorted_seconds[max(0, rank - 1)]


def summarize(seconds: list[float]) -> dict:
    """Distribution stats + a suggested `--min-gap-seconds`.
    The suggestion is `ceil(2 * max)`, the same 2x-margin rule that produced the current default,
    now from measured data. It is a STARTING point: the largest windows are flagged for manual
    classification first, because the risk T0039 exists for is that one of them is a coalescing
    artifact the threshold must cover rather than a real outage it must not be dragged up by.
    """
    if not seconds:
        return {
            "n": 0,
            "p50": None,
            "p90": None,
            "p99": None,
            "p99_9": None,
            "max": None,
            "suggested_min_gap_seconds": None,
        }
    s = sorted(seconds)
    return {
        "n": len(s),
        "p50": _percentile(s, 50),
        "p90": _percentile(s, 90),
        "p99": _percentile(s, 99),
        "p99_9": _percentile(s, 99.9),
        "max": s[-1],
        "suggested_min_gap_seconds": float(math.ceil(2 * s[-1])),
    }


def _report(
    obs: list[GapObs],
    *,
    review_ceiling: float,
    top: int,
    skipped: list[tuple[str, datetime, str]] | None = None,
) -> str:
    lines: list[str] = []
    skipped = skipped or []
    seconds = [g for _p, _h, g in obs]
    stats = summarize(seconds)

    # T0039: the derivation this report backs.
    lines.append("=== cross-host primary book-silence distribution ===")

    if skipped:
        # Loud, never a footnote: a skipped hour is unmeasured, not clean. If one of these was a real
        # primary outage the secondary could have witnessed, the distribution below is missing its
        # largest window and the suggestion is too low. Investigate before trusting the number.
        lines.append(f"  !! {len(skipped)} hour(s) SKIPPED (unreadable / non-monotonic) — the distribution is INCOMPLETE:")
        for pair, hour, err in skipped[:top]:
            lines.append(f"     {pair:<9} {hour:%Y-%m-%d %H}:00  {err[:70]}")
        if len(skipped) > top:
            lines.append(f"     ... and {len(skipped) - top} more")
        lines.append("")

    if stats["n"] == 0:
        lines.append("  no witnessed primary silences yet — the primary has not gapped during the overlap,")
        lines.append("  or the soak has too little overlapping data. Nothing to pin; let it soak.")
        return "\n".join(lines)

    lines.append(f"  windows observed : {stats['n']}")
    lines.append(f"  p50 / p90 / p99  : {stats['p50']:.2f} / {stats['p90']:.2f} / {stats['p99']:.2f} s")
    lines.append(f"  p99.9 / max      : {stats['p99_9']:.2f} / {stats['max']:.2f} s")
    lines.append(f"  single-host ref  : 14.78 s (max natural quiescence), current default 30 s")
    lines.append("")

    # ALWAYS surface the largest windows, regardless of review_ceiling. The suggestion is driven by
    # `max`, so the window that produced it must be visible and classifiable -- a report that hid it
    # (because it fell under the ceiling) while suggesting a number derived from it would contradict
    # itself. review_ceiling now only ANNOTATES which of these are outage-sized.
    largest = sorted(obs, key=lambda o: o[2], reverse=True)[:top]
    lines.append(f"  largest witnessed windows (classify EACH before trusting the number):")
    for pair, hour, sec in largest:
        tag = "  <- >= review ceiling" if sec >= review_ceiling else ""
        lines.append(f"    {sec:8.2f}s  {pair:<9} {hour:%Y-%m-%d %H}:00{tag}")
    lines.append("")
    lines.append(f"  SUGGESTED --min-gap-seconds : {stats['suggested_min_gap_seconds']:.0f}  (= ceil(2 x max))")
    lines.append("  Decision-support, NOT a verdict. The primary reboots ~21:25 UTC nightly (staggered 1h before")
    lines.append("  the secondary so the secondary witnesses it), so a benign ~80s reboot window will normally")
    lines.append("  sit at or near the top of this list -- a real primary-down window the secondary covered, NOT")
    lines.append("  a coalescing artifact. Exclude any such reboot/outage window and re-read the max below it;")
    lines.append("  a coalescing artifact, by contrast, must be COVERED by the threshold. Record the chosen value")
    lines.append("  + this derivation before flipping the reconciler to --mint.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # T0039: the soak these mirrors come from.
    ap = argparse.ArgumentParser(description="Pin --min-gap-seconds from the soaked cross-host mirrors.")
    ap.add_argument("primary_root", type=Path)
    ap.add_argument("secondary_root", type=Path)
    ap.add_argument("--since", type=lambda s: datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC))
    ap.add_argument(
        "--probe-seconds",
        type=float,
        default=1.0,
        help="Only count primary silences longer than this (default 1s). The region that pins the "
        "threshold is near/above the 14.78s single-host figure, so the sub-1s coalescing jitter is "
        "excluded by design -- and probing at 0 is quadratic on a busy pair (every inter-message "
        "window calls the secondary-witness check), which does not finish on real data.",
    )
    ap.add_argument("--review-ceiling", type=float, default=120.0, help="List windows at/above this for manual review.")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)

    obs, skipped = observe_gaps(args.primary_root, args.secondary_root, since=args.since, probe_seconds=args.probe_seconds)
    print(_report(obs, review_ceiling=args.review_ceiling, top=args.top, skipped=skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
