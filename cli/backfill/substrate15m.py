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
# The T0004-ratified acceptance band for tick reconciliation: match rate "within 1 %".
_ACCEPTANCE_TOL = 1e-2
# Seam price tolerance. O/H/L/C survive re-bucketing without arithmetic (copies, max, min),
# so this is slack for bit-identical values.
_SEAM_PRICE_TOL = 1e-9
# Seam volume tolerance — "exact up to float summation order" (ratified at review):
# re-bucketing reorders the minute-volume sum, shifting a fraction of hours by exactly 1 ULP
# (~2.2e-16 rel), so volume matches at rel <= 5e-16 (<= 2 ULP); the Int64 `count` sum is
# order-immune and is compared exactly, proving per-hour minute-set identity.
_SEAM_VOLUME_TOL = 5e-16
_PRICE_COLUMNS = ["open", "high", "low", "close"]


def build_15m_substrate(source_dir: Path, symbols: list[str], out_root: Path, *, fetched_at: str) -> dict:
    """Build the full-history 15m substrate: `backfill_basket` at the `"15"` interval, verbatim.

    Writes `out_root/{BASE}/{QUOTE}/15.parquet` per symbol plus `out_root/manifest.json`
    (per-series `rows`/`first_ts`/`last_ts`/`sha256` + `basket_sha256`) and returns the manifest.
    """
    return backfill_basket(source_dir, symbols, ["15"], out_root, fetched_at)


def _pair_parquet(root: Path, symbol: str, label: str) -> pl.DataFrame:
    base, quote = symbol.split("/")
    return read_parquet(root / base / quote / f"{label}.parquet")


def qa_15m(out_root: Path, symbols: list[str]) -> dict:
    """Gap/density QA over each pair's written `15.parquet` (a pure read; nothing is modified).

    Per symbol: `rows`, `first_ts`/`last_ts`, `gap_count` + `largest_gap_missing` (`detect_gaps`
    at 900 s), and `density_by_year` — actual bars per calendar year as a percentage of the ideal
    96-bars/day 900-s grid, with the first/last year's denominator clipped to the series span
    (so a mid-year start doesn't dilute its year). A calendar year inside the span with zero bars
    still appears, at density 0.0.
    """
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
    """Independent tick-derived check of the 15m substrate over `window` (`[start, end)`, tz-aware
    UTC, 900-s-aligned so tick buckets and bar stamps share the grid).

    Per symbol in `symbol_csvs` (canonical `"BASE/QUOTE"` -> CSV member name inside `tick_zip`):
    `read_trades_csv` on the zip member -> window filter -> `ticks_to_bars(interval_minutes=15)`
    -> `cli.tick.reconcile.reconcile` against the pair's written `15.parquet` rows in-window, at
    `tol=1e-2` — so `pct_within_tol` IS the T0004 "within 1 %" acceptance rate. Returns the
    reconcile dict per symbol, extended with `canonical_bars_in_window` and `coverage_pct`
    (compared bars over canonical bars in-window; the honest denominator, since `reconcile`
    inner-joins and would otherwise silently drop uncovered bars).
    """
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
    """Seam check: re-aggregating the 15m frame to 1h must reproduce the canonical 1h bars.

    `window` is `[start, end)`, tz-aware UTC, hour-aligned (a partial edge hour would produce a
    spurious bucket). The 15m rows in-window are bucketed by `floor(ts / 3600)` with an explicit
    polars group-by (open=first, high=max, low=min, close=last, volume=sum, count=sum — NOT
    `aggregate_minutes`, which assumes 1-minute inputs) and inner-joined on `ts` against the
    canonical `60.parquet` in-window. A joined hour matches (the ratified predicate) when every
    O/H/L/C relative difference is within 1e-9, volume is exact up to float summation order
    (rel <= 5e-16, i.e. <= 2 ULP — re-bucketing reorders the minute-volume sum, which shifts some
    hours by exactly 1 ULP), AND the summed trade `count` is exactly equal (Int64, order-immune —
    per-hour minute-set identity). Per symbol: bucket counts (`n_hours_15m`/`n_hours_canonical`/
    `n_joined`), `n_matched`, `n_price_mismatch` / `n_volume_mismatch` / `n_count_mismatch`,
    `n_volume_bitexact` (joined hours whose volume is bit-identical — transparency on how much
    the 2-ULP band absorbs), `max_price_rel_diff` / `max_volume_rel_diff` (0.0 when clean), and
    `all_match` (identical bucket sets and every joined hour matching).
    """
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
