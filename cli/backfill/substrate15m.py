from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from cli.backfill.backfill import backfill_basket
from cli.ohlc.dataset import read_parquet
from cli.ohlc.qa import INTERVAL_SECONDS, detect_gaps
from cli.tick.aggregate import ticks_to_bars
from cli.tick.read import read_trades_csv
from cli.tick.reconcile import reconcile

_SECS_15M = INTERVAL_SECONDS["15"]
_SECS_1H = INTERVAL_SECONDS["60"]
# The tick-reconciliation acceptance band ratified in T0004 (resolved): a bar matches when every O/H/L/C relative
# difference is within 1 %, so `reconcile`'s `pct_within_tol` at this band is the acceptance rate.
_ACCEPTANCE_TOL = 1e-2
# Seam price tolerance: re-bucketing moves O/H/L/C by copy/max/min, never arithmetic, so this is slack around values
# that should be bit-identical.
_SEAM_PRICE_TOL = 1e-9
# Seam volume tolerance — exact up to float summation order: re-bucketing reorders the minute-volume sum, so volume is
# matched within 2 ULP, while the order-immune Int64 `count` sum is compared exactly and is what proves per-hour
# minute-set identity.
_SEAM_VOLUME_TOL = 5e-16
_PRICE_COLUMNS = ["open", "high", "low", "close"]


def build_15m_substrate(source_dir: Path, symbols: list[str], out_root: Path, *, fetched_at: str) -> dict:
    """Build the full-history 15m substrate — `backfill_basket` at the `"15"` interval, verbatim."""
    return backfill_basket(source_dir, symbols, ["15"], out_root, fetched_at)


def _pair_parquet(root: Path, symbol: str, label: str) -> pl.DataFrame:
    base, quote = symbol.split("/")
    return read_parquet(root / base / quote / f"{label}.parquet")


def qa_15m(out_root: Path, symbols: list[str]) -> dict:
    """Gap/density QA over each pair's written `15.parquet`, a pure read that modifies nothing; `density_by_year` clips the
    first and last year's ideal-grid denominator to the series span, so a mid-year start does not dilute its year."""
    report: dict = {}
    for symbol in symbols:
        frame = _pair_parquet(out_root, symbol, "15")
        gaps = detect_gaps(frame, _SECS_15M)
        first_ts, last_ts = frame["ts"].min(), frame["ts"].max()
        first_epoch, last_epoch = int(first_ts.timestamp()), int(last_ts.timestamp())

        rows_by_year = dict(frame.group_by(pl.col("ts").dt.year().alias("year")).len().iter_rows())
        density_by_year: dict[int, float] = {}
        for year in range(first_ts.year, last_ts.year + 1):
            year_start = int(datetime(year, 1, 1, tzinfo=UTC).timestamp())
            year_end = int(datetime(year + 1, 1, 1, tzinfo=UTC).timestamp())
            lo = max(first_epoch, year_start)
            hi = min(last_epoch, year_end - _SECS_15M)
            ideal = (hi - lo) // _SECS_15M + 1
            density_by_year[year] = 100.0 * rows_by_year.get(year, 0) / ideal

        report[symbol] = {
            "rows": frame.height,
            "first_ts": first_ts,
            "last_ts": last_ts,
            "gap_count": len(gaps),
            "largest_gap_missing": max((gap["missing"] for gap in gaps), default=0),
            "density_by_year": density_by_year,
        }
    return report


def reconcile_15m_vs_ticks(out_root: Path, tick_zip: Path, symbol_csvs: dict[str, str], window: tuple[datetime, datetime]) -> dict:
    """Independent tick-derived check of the 15m substrate over `window` — half-open, tz-aware UTC and 900-s-aligned so tick
    buckets and bar stamps share the grid — for each canonical `"BASE/QUOTE"` in `symbol_csvs`, mapped to its CSV member
    inside `tick_zip`. Each symbol's `reconcile` dict gains `coverage_pct`, its joined `n_intervals` over the canonical bars
    in-window, because `reconcile` inner-joins and would otherwise silently drop the bars no tick bucket covered."""
    start, end = window
    report: dict = {}
    for symbol, member in symbol_csvs.items():
        ticks = read_trades_csv((tick_zip, member)).filter((pl.col("ts") >= start) & (pl.col("ts") < end))
        tick_bars = ticks_to_bars(ticks, interval_minutes=_SECS_15M // 60)
        canonical = _pair_parquet(out_root, symbol, "15").filter((pl.col("ts") >= start) & (pl.col("ts") < end))

        result = reconcile(tick_bars, canonical, tol=_ACCEPTANCE_TOL)
        result["canonical_bars_in_window"] = canonical.height
        result["coverage_pct"] = 100.0 * result["n_intervals"] / canonical.height if canonical.height else 100.0
        report[symbol] = result
    return report


def seam_15m_to_1h(out_root: Path, canonical_root: Path, symbols: list[str], window: tuple[datetime, datetime]) -> dict:
    """Seam check: re-aggregating the 15m frame to 1h must reproduce the canonical 1h bars over `window`, half-open, tz-aware
    UTC and hour-aligned, since a partial edge hour would produce a spurious bucket. The hourly roll-up is an explicit polars
    group-by rather than `aggregate_minutes`, which assumes 1-minute inputs. `n_volume_bitexact` reports how many joined
    hours needed no volume band at all."""
    start, end = window
    report: dict = {}
    for symbol in symbols:
        m15 = _pair_parquet(out_root, symbol, "15").filter((pl.col("ts") >= start) & (pl.col("ts") < end))
        hourly = (
            m15.sort("ts")
            .group_by((pl.col("ts").dt.epoch("s") // _SECS_1H * _SECS_1H).alias("hour_epoch"), maintain_order=True)
            .agg(
                pl.col("open").first(),
                pl.col("high").max(),
                pl.col("low").min(),
                pl.col("close").last(),
                pl.col("volume").sum(),
                pl.col("count").sum(),
            )
            .with_columns(pl.from_epoch(pl.col("hour_epoch"), time_unit="s").dt.replace_time_zone("UTC").alias("ts"))
            .drop("hour_epoch")
        )
        canonical = _pair_parquet(canonical_root, symbol, "60").filter((pl.col("ts") >= start) & (pl.col("ts") < end))

        joined = hourly.join(canonical, on="ts", how="inner", suffix="_canon")
        price_rel_diffs = [
            (pl.col(c) - pl.col(f"{c}_canon")).abs() / pl.col(f"{c}_canon").abs().clip(lower_bound=1e-12) for c in _PRICE_COLUMNS
        ]
        volume_rel_diff = (pl.col("volume") - pl.col("volume_canon")).abs() / pl.col("volume_canon").abs().clip(lower_bound=1e-12)
        flags = joined.select(
            pl.any_horizontal([diff > _SEAM_PRICE_TOL for diff in price_rel_diffs]).alias("price_mismatch"),
            (volume_rel_diff > _SEAM_VOLUME_TOL).alias("volume_mismatch"),
            (pl.col("volume") == pl.col("volume_canon")).alias("volume_bitexact"),
            (pl.col("count") != pl.col("count_canon")).alias("count_mismatch"),
            pl.max_horizontal(price_rel_diffs).alias("price_rel_diff"),
            volume_rel_diff.alias("volume_rel_diff"),
        )
        n_price_mismatch = int(flags["price_mismatch"].sum())
        n_volume_mismatch = int(flags["volume_mismatch"].sum())
        n_count_mismatch = int(flags["count_mismatch"].sum())
        n_matched = int((~(flags["price_mismatch"] | flags["volume_mismatch"] | flags["count_mismatch"])).sum())

        report[symbol] = {
            "n_hours_15m": hourly.height,
            "n_hours_canonical": canonical.height,
            "n_joined": joined.height,
            "n_matched": n_matched,
            "n_price_mismatch": n_price_mismatch,
            "n_volume_mismatch": n_volume_mismatch,
            "n_volume_bitexact": int(flags["volume_bitexact"].sum()),
            "n_count_mismatch": n_count_mismatch,
            "max_price_rel_diff": float(flags["price_rel_diff"].max()) if joined.height else 0.0,
            "max_volume_rel_diff": float(flags["volume_rel_diff"].max()) if joined.height else 0.0,
            "all_match": bool(hourly.height == canonical.height == joined.height and n_matched == joined.height),
        }
    return report
