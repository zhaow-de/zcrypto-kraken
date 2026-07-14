"""Which hours are ready to reconcile, and the losses no witness can heal (spec 00050).

`reconcile.py` answers "what did the primary miss that the secondary saw?" — a question that needs a
LIVE secondary to answer it. This module answers the two questions it structurally cannot, because
its witness is dark too:

  * **`both_streams_silent`** — every book stream silent, on BOTH hosts, across ONE window.
  * **`total_loss`** — an hour that exists on neither mirror.

Both detectors are **unconditional**: they require no secondary activity, which is exactly why they
are the only ones that can see a correlated outage (spec 00050 constraint 4 — a correlated event hits
every host at the same exchange event, so redundancy buys nothing against it). Neither is ever
spliced: the data is gone. They are ledgered, booked into `residual_gap_seconds_total`, and paged.

No I/O policy and no Typer here — the tree scan is filename-only (it never opens a parquet), and
`command.py` owns the reading, the minting and the exporter.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

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

    Re-scanned every cycle: an hour that was residual last cycle may be healable this one (a late
    pull), and the ledger — not this list — is what stops an already-decided hour being re-decided.
    """
    newest = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=SETTLE_HOURS)
    return [newest - timedelta(hours=i) for i in reversed(range(window_hours))]


def is_late(hour: datetime, *, now: datetime) -> bool:
    """Past the late deadline (see `LATE_MINT_HOURS`)."""
    return now - hour >= timedelta(hours=LATE_MINT_HOURS)


def hour_path(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    """`<root>/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` — the pair spans two levels."""
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
        except ValueError:  # a hand-made directory that is not a date — not ours, ignore it
            continue
        found.setdefault(f"{parts[-7]}/{parts[-6]}", set()).add(hour)
    return found


def newest_hour(*scans: dict[str, set[datetime]]) -> datetime | None:
    """The newest final across every scan — the mirror's own freshness, for `source_lag`."""
    hours = [hour for scan in scans for pair_hours in scan.values() for hour in pair_hours]
    return max(hours) if hours else None


@dataclass(frozen=True)
class DarkWindow:
    """A window in which the whole fleet, on both hosts, recorded nothing at all."""

    start: datetime
    end: datetime
    seconds: float


def fleet_dark_windows(
    stamps: Iterable[datetime], *, hour_start: datetime, hour_end: datetime, min_seconds: float
) -> list[DarkWindow]:
    """Windows in which NOTHING was recorded — no pair, on either host.

    `stamps` is every book message timestamp of every pair from BOTH mirrors in this hour, merged.
    A window between two consecutive stamps is therefore one in which the whole fleet, on both hosts,
    was silent *simultaneously* — the INTERSECTION of the per-pair dual-silences, never their union.

    That distinction is the detector. Ten pairs each going quiet for 40 s at ten *different* moments
    of the hour is an ordinary thin market. Ten pairs going quiet for 40 s at the *same* moment, on
    two independent hosts holding two independent WS connections, is not a market — at depth 100 it
    has no benign explanation, and it is loss. A per-pair silence *count* carries no window and cannot
    tell the two apart, so it would page on the benign one.

    The hour's own bounds are edges, for the same reason `find_book_gaps` requires them: a fleet that
    dies at :10 has no "next message" to pair with, and that crash shape is the whole point. Stamps
    outside the bounds (a late event that leaked in from an adjacent hour) are clamped away rather
    than allowed to fabricate a negative-length window.
    """
    inside = sorted({stamp for stamp in stamps if hour_start <= stamp <= hour_end})
    edges = [hour_start, *inside, hour_end]
    windows = [
        DarkWindow(start=a, end=b, seconds=(b - a).total_seconds())
        for a, b in zip(edges, edges[1:], strict=False)
        if (b - a).total_seconds() >= min_seconds
    ]
    return windows


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
