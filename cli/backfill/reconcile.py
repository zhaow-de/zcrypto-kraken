from __future__ import annotations

from pathlib import Path

import polars as pl

from cli.ohlc.dataset import read_parquet

_OHLC_COLUMNS = ["open", "high", "low", "close"]


def reconcile_series(backfill: pl.DataFrame, rest: pl.DataFrame) -> dict:
    """Compare a backfill-reconstructed series against its v0 REST counterpart over the ts overlap.

    Inner-joins on `ts` (the overlap window). OHLC/volume are expected to match closely (same
    Kraken source, so reported and compared for exact equality); `vwap` is a reconstruction proxy
    and is expected to differ from REST's true vwap, so it's reported (mean abs relative diff) —
    not asserted or raised on. Returns `{overlap_rows, ohlc_exact_match_rows, ohlc_match_rate,
    volume_rel_diff_max, vwap_mean_abs_rel_diff}`.
    """
    joined = backfill.join(rest, on="ts", how="inner", suffix="_rest")
    overlap_rows = joined.height
    if overlap_rows == 0:
        return {
            "overlap_rows": 0,
            "ohlc_exact_match_rows": 0,
            "ohlc_match_rate": 1.0,
            "volume_rel_diff_max": 0.0,
            "vwap_mean_abs_rel_diff": 0.0,
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
    """Reconcile every `backfill_root/{symbol}/{label}.parquet` series against its v0 REST
    counterpart at `rest_root`, for each interval label in `intervals` (label -> interval_secs,
    e.g. `cli.ohlc.qa.INTERVAL_SECONDS`). Series without a `rest_root` counterpart are skipped.
    Returns `{series: {"{symbol}/{label}": reconcile_series-dict}, summary}`, where `summary` is
    `{series_count, total_overlap_rows, min_ohlc_match_rate}`.
    """
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

    match_rates = [s["ohlc_match_rate"] for s in series.values()]
    summary = {
        "series_count": len(series),
        "total_overlap_rows": sum(s["overlap_rows"] for s in series.values()),
        "min_ohlc_match_rate": min(match_rates) if match_rates else 1.0,
    }
    return {"series": series, "summary": summary}


def render_markdown(report: dict) -> str:
    """Render a reconcile `report` (as returned by `reconcile_dataset`) as a Markdown table + summary."""
    lines = ["# OHLCVT Backfill Reconciliation Report", ""]
    lines += [
        "| Series | Overlap rows | OHLC match rate | OHLC exact matches | Volume rel diff max | Vwap mean abs rel diff |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in report["series"].items():
        lines.append(
            f"| {name} | {s['overlap_rows']} | {s['ohlc_match_rate']:.4f} | {s['ohlc_exact_match_rows']} | "
            f"{s['volume_rel_diff_max']:.6f} | {s['vwap_mean_abs_rel_diff']:.6f} |"
        )

    summary = report["summary"]
    lines += [
        "",
        "## Summary",
        "",
        f"- Series count: {summary['series_count']}",
        f"- Total overlap rows: {summary['total_overlap_rows']}",
        f"- Min OHLC match rate: {summary['min_ohlc_match_rate']:.4f}",
    ]
    return "\n".join(lines) + "\n"
