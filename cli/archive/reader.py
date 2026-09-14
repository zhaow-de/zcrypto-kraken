"""The canonical read surface (spec 00050 D6).

Consumers must not glob `**/*.parquet` over the archive: it also matches the live hour's
`<HH>.part####.parquet`, and any part a mirror still holds beside its merged final (T0038), so those
rows are read twice. L2 rows carry absolute quantities, so a doubled delta stream reconstructs a
different book. `FINAL_NAME` is `settle.py`'s, not a second copy of it: one pattern for what counts
as a committed final, shared by the settlement scan and this reader.
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

    Sorted by `(pair, hour)`, a healed hour the primary lacks in sequence with the rest, never appended
    after later hours. The order is a contract: consumers concatenate hours in yield order and may
    never re-sort rows by `ts` (L2 rows carry absolute quantities), so an out-of-sequence hour would
    splice a different book.
    """
    merged = {(pair, hour): p for pair, hour, p in _hours(primary_root, kind)}
    if reconciled_root is not None and reconciled_root.exists():
        merged.update({(pair, hour): p for pair, hour, p in _hours(reconciled_root, kind)})
    for (pair, hour), p in sorted(merged.items()):
        yield pair, hour, p
