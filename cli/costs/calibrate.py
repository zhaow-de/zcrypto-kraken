"""The captured-spread calibration query, committed as runnable code (T0014, spec 00085 D5).

Was prose at `docs/reference/captured-spread-calibration.md`; this module is now the provenance of
record. `tests/test_costs_calibrate.py::test_the_committed_script_reproduces_the_table_it_replaces`
runs it over the SUPERSEDED window and requires it to reproduce the SUPERSEDED table, both held
there as literals. It deliberately does NOT read `cli/costs/spread.py`'s constants: those now carry
the current window, so importing them would make the control follow the very restamp it exists to
check. That test is the standing instrument for attributing a restamp's move to the window rather
than to this code.

The statistic, matching the query of record: the mean of `(fill_bps_bid_<size> +
fill_bps_ask_<size>) / 2` per pair per rung. `hours` means hourly panel files PER PAIR, not summed
pair-hours -- where pairs differ, the minimum is reported and `max_rows - min_rows` exposes the
spread (a partial NAS pull of one leg must be visible, not averaged away).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from cli.costs.errors import CostModelError

_SIZES: tuple[tuple[int, str], ...] = ((100, "100"), (1_000, "1k"), (10_000, "10k"))


@dataclass(frozen=True)
class CalibrationResult:
    """`calibrate()`'s output: the re-keyed table plus the provenance figures Task 7 restamps
    `cli/costs/spread.py`'s constants from."""

    table: dict[str, dict[int, float]]
    hours: int
    min_rows: int
    max_rows: int
    btc_eur_reference: float


def _discover_pairs(panel_root: Path) -> list[str]:
    # Mirrors `cli/panel/command.py`'s glob-and-slice convention for the same tree layout
    # (`<BASE>/<QUOTE>/panel-1s/<YYYY>/<MM>/<DD>/<HH>.parquet`).
    return sorted({f"{p.parts[-7]}/{p.parts[-6]}" for p in panel_root.glob("*/*/panel-1s/*/*/*/*.parquet")})


def _hourly_files_in_window(panel_dir: Path, window_start: datetime, window_end: datetime) -> list[Path]:
    # A file's hour interval is [HH:00:00, HH+1:00:00); keep files that OVERLAP the window rather
    # than start inside it, since `window_start`/`window_end` need not land on an hour boundary
    # -- reproduced against the real tree BOTH ways: 353 files/pair for the superseded, non-aligned
    # 2026-07-08T13:47:33Z..2026-07-23T05:59:59Z window, and 365 files/pair for the current,
    # hour-aligned 2026-07-23T14:00:00Z..2026-08-07T19:00:00Z one. Note the count is files that
    # OVERLAP, so it equals span/3600 only when the window is hour-aligned: the superseded window
    # spans 352.21 h yet correctly yields 353 files.
    files = []
    for p in panel_dir.glob("*/*/*/*.parquet"):
        # Hardcoded UTC, not `window_start.tzinfo`: panel paths are UTC by the tree's own
        # convention, independent of what tzinfo the caller's window happens to carry. Deriving it
        # from the caller would select the wrong FILES for an equivalent-instant, non-UTC window
        # while the polars filter below stayed correct -- a silently partial window.
        hour_start = datetime(
            int(p.parent.parent.parent.name), int(p.parent.parent.name), int(p.parent.name), int(p.stem), tzinfo=timezone.utc
        )
        if hour_start < window_end and hour_start + timedelta(hours=1) > window_start:
            files.append(p)
    return sorted(files)


def calibrate(panel_root: Path, window_start: datetime, window_end: datetime) -> CalibrationResult:
    """Scan every `<BASE>/<QUOTE>/panel-1s/**` pair under `panel_root` and compute the mean
    effective-spread table over `[window_start, window_end]`, plus its provenance.

    `window_start`/`window_end` must be timezone-aware (panel `ts` is `Datetime("us", "UTC")`; a
    naive literal compared against it raises `SchemaError`).
    """
    table: dict[str, dict[int, float]] = {}
    hours_per_pair: dict[str, int] = {}
    rows_per_pair: dict[str, int] = {}

    for symbol in _discover_pairs(panel_root):
        base, quote = symbol.split("/")
        panel_dir = panel_root / base / quote / "panel-1s"
        files = _hourly_files_in_window(panel_dir, window_start, window_end)
        if not files:
            continue
        hours_per_pair[symbol] = len(files)

        lf = pl.scan_parquet(files).filter(pl.col("ts").is_between(window_start, window_end, closed="both"))
        stats = lf.select(
            pl.len().alias("_rows"),
            *(
                (((pl.col(f"fill_bps_bid_{suffix}") + pl.col(f"fill_bps_ask_{suffix}")) / 2).mean()).alias(str(size))
                for size, suffix in _SIZES
            ),
        ).collect()

        rows_per_pair[symbol] = stats["_rows"].item()
        table[symbol] = {size: stats[str(size)].item() for size, _ in _SIZES}

    # Guard on rows actually landing IN the window, not on key presence: a BTC/EUR file whose hour
    # merely OVERLAPS the window (see `_hourly_files_in_window`) puts "BTC/EUR" in `table` even when
    # every row inside it falls in an archive gap the window happens to land in -- `rows_per_pair`
    # is then 0 (or the key never gets set at all, for the "no file at all" case both cover).
    if not rows_per_pair.get("BTC/EUR"):
        raise CostModelError(f"no BTC/EUR panel data in the window [{window_start}, {window_end}]; refusing an unpinned table")

    btc_eur_reference = (
        pl.scan_parquet(_hourly_files_in_window(panel_root / "BTC" / "EUR" / "panel-1s", window_start, window_end))
        .filter(pl.col("ts").is_between(window_start, window_end, closed="both"))
        .select(pl.col("mid").mean())
        .collect()
        .item()
    )

    return CalibrationResult(
        table=table,
        hours=min(hours_per_pair.values()),
        min_rows=min(rows_per_pair.values()),
        max_rows=max(rows_per_pair.values()),
        btc_eur_reference=btc_eur_reference,
    )
