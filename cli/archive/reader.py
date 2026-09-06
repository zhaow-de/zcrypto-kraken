"""The canonical read surface (spec 00050 D6).

Consumers must NOT glob `**/*.parquet` over the archive: that also matches `<HH>.part####.parquet`
(the live hour) and, on the NAS mirror, thousands of already-merged stale part files rsync never
deleted (T0038) — so the obvious glob silently reads a large fraction of the archive TWICE. For L2
book deltas that is not cosmetic: rows carry ABSOLUTE quantities, so a doubled delta stream
reconstructs a different book. This helper is the safe way in, and the strict final-name match makes
that whole class of bug structurally impossible.

`FINAL_NAME` is `settle.py`'s, not a second copy of it — one pattern for what counts as a committed
final, shared by the settlement scan and this reader.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from cli.archive.settle import FINAL_NAME


def _hours(root: Path, kind: str) -> Iterator[tuple[str, datetime, Path]]:
    for p in sorted(root.glob(f"*/*/{kind}/*/*/*/*.parquet")):
        match = FINAL_NAME.match(p.name)
        if match is None:
            continue
        parts = p.parts
        pair = f"{parts[-7]}/{parts[-6]}"
        try:
            hour = datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(match.group(1)), tzinfo=UTC)
        except ValueError, OverflowError:  # a hand-made directory that is not a date — not ours, ignore it
            continue
        yield pair, hour, p


def canonical_segments(
    primary_root: Path, reconciled_root: Path | None = None, *, kind: str = "book"
) -> Iterator[tuple[str, datetime, Path]]:
    """Yield `(pair, hour, path)` for every canonical hour: reconciled-first, primary otherwise.

    Yields are sorted by `(pair, hour)` — overlay-only hours (a wholly-missing primary hour, healed
    from the secondary) included, IN sequence, never appended after later raw hours. The order is a
    contract: consumers concatenate hours in yield order and may never re-sort rows by `ts` (L2 rows
    carry absolute quantities), so an out-of-sequence healed hour would splice a different book.
    """
    merged = {(pair, hour): p for pair, hour, p in _hours(primary_root, kind)}
    if reconciled_root is not None and reconciled_root.exists():
        merged.update({(pair, hour): p for pair, hour, p in _hours(reconciled_root, kind)})  # reconciled-first
    for (pair, hour), p in sorted(merged.items()):
        yield pair, hour, p
