from __future__ import annotations

from pathlib import Path

import polars as pl

from cli.ohlc.dataset import read_parquet

_OHLC_COLUMNS = ["open", "high", "low", "close"]


def reconcile_series(backfill: pl.DataFrame, rest: pl.DataFrame) -> dict:
    """OHLC and volume share REST's Kraken source and should match; `vwap` is a reconstruction proxy, so it is only reported."""
    joined = backfill.join(rest, on="ts", how="inner", suffix="_rest")
    overlap_rows = joined.height
    if overlap_rows == 0:
        return {
            "overlap_rows": 0,
            "ohlc_exact_match_rows": 0,
            # None for all three, though their success values differ -- 1.0 for the rate, 0.0 for the
            # two deviation measures. Nothing was compared, so neither a perfect rate nor a zero
            # deviation is a reading anyone may act on.
            "ohlc_match_rate": None,
            "volume_rel_diff_max": None,
            "vwap_mean_abs_rel_diff": None,
        }

    match = joined.select(pl.all_horizontal([pl.col(c) == pl.col(f"{c}_rest") for c in _OHLC_COLUMNS]).alias("match"))
    ohlc_exact_match_rows = int(match["match"].sum())

    def _rel_diff(col: str) -> pl.Series:
        expr = (pl.col(col) - pl.col(f"{col}_rest")).abs() / pl.col(f"{col}_rest").abs().clip(lower_bound=1e-12)
        return joined.select(expr).to_series()

    return {
        "overlap_rows": overlap_rows,
        "ohlc_exact_match_rows": ohlc_exact_match_rows,
        "ohlc_match_rate": ohlc_exact_match_rows / overlap_rows,
        "volume_rel_diff_max": float(_rel_diff("volume").max()),
        "vwap_mean_abs_rel_diff": float(_rel_diff("vwap").mean()),
    }


def reconcile_dataset(backfill_root: Path, rest_root: Path, intervals: dict[str, int]) -> dict:
    """`intervals` supplies the labels to look for (e.g. `cli.ohlc.qa.INTERVAL_SECONDS`)."""
    entries = sorted(
        (str(path.parent.relative_to(backfill_root)), label, path)
        for label in intervals
        for path in backfill_root.rglob(f"{label}.parquet")
    )

    series = {}
    for symbol, label, bf_path in entries:
        rest_path = rest_root / symbol / f"{label}.parquet"
        if not rest_path.exists():
            continue
        series[f"{symbol}/{label}"] = reconcile_series(read_parquet(bf_path), read_parquet(rest_path))

    match_rates = [s["ohlc_match_rate"] for s in series.values() if s["ohlc_match_rate"] is not None]
    summary = {
        "series_count": len(series),
        "total_overlap_rows": sum(s["overlap_rows"] for s in series.values()),
        # None, not 1.0: a minimum over no measured series has no value, and the success value here
        # would report every series matching exactly.
        "min_ohlc_match_rate": min(match_rates) if match_rates else None,
    }
    return {"series": series, "summary": summary}


def render_markdown(report: dict) -> str:
    lines = ["# OHLCVT Backfill Reconciliation Report", ""]
    lines += [
        "| Series | Overlap rows | OHLC match rate | OHLC exact matches | Volume rel diff max | Vwap mean abs rel diff |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in report["series"].items():
        match_rate = f"{s['ohlc_match_rate']:.4f}" if s["ohlc_match_rate"] is not None else "n/a"
        volume_diff = f"{s['volume_rel_diff_max']:.6f}" if s["volume_rel_diff_max"] is not None else "n/a"
        vwap_diff = f"{s['vwap_mean_abs_rel_diff']:.6f}" if s["vwap_mean_abs_rel_diff"] is not None else "n/a"
        lines.append(
            f"| {name} | {s['overlap_rows']} | {match_rate} | {s['ohlc_exact_match_rows']} | {volume_diff} | {vwap_diff} |"
        )

    summary = report["summary"]
    min_match_rate = f"{summary['min_ohlc_match_rate']:.4f}" if summary["min_ohlc_match_rate"] is not None else "n/a"
    lines += [
        "",
        "## Summary",
        "",
        f"- Series count: {summary['series_count']}",
        f"- Total overlap rows: {summary['total_overlap_rows']}",
        f"- Min OHLC match rate: {min_match_rate}",
    ]
    return "\n".join(lines) + "\n"
