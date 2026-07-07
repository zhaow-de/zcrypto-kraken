from __future__ import annotations

from pathlib import Path

import polars as pl

from cli.ohlc.dataset import read_parquet

# 1d / 4h / 1h — matches `cli.ohlc.DEFAULT_INTERVALS`, keyed by the on-disk interval label.
INTERVAL_SECONDS = {"1440": 86400, "240": 14400, "60": 3600}


def detect_gaps(frame: pl.DataFrame, interval_secs: int) -> list[dict]:
    """Find gaps in `frame`'s sorted `ts` column that exceed `interval_secs`.

    Returns one dict per gap: `{after_ts, before_ts, missing}`, where `missing` is the count of
    candles absent from the regular grid between the two timestamps. `frame` is assumed sorted
    (as `to_frame` guarantees), so this is a clean consecutive-row diff.
    """
    diffs = frame.select(
        pl.col("ts").shift(1).alias("after_ts"),
        pl.col("ts").alias("before_ts"),
        (pl.col("ts") - pl.col("ts").shift(1)).dt.total_seconds().alias("delta"),
    ).filter(pl.col("delta") > interval_secs)

    return [
        {
            "after_ts": row["after_ts"],
            "before_ts": row["before_ts"],
            "missing": int(row["delta"]) // interval_secs - 1,
        }
        for row in diffs.iter_rows(named=True)
    ]


def wick_outliers(frame: pl.DataFrame, *, rel_range: float = 0.20) -> list[dict]:
    """Return candles whose intraday range `(high - low) / close` exceeds `rel_range`."""
    flagged = frame.select(
        "ts",
        "high",
        "low",
        "close",
        ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("rel_range"),
    ).filter(pl.col("rel_range") > rel_range)

    return flagged.to_dicts()


def price_discontinuities(frame: pl.DataFrame, *, max_ratio: float = 3.0) -> list[dict]:
    """Return bar-over-bar close moves beyond `max_ratio`x (or below `1 / max_ratio`) — candidate corporate
    actions (splits, redenominations) or data errors. A heuristic flag: genuine crypto moves (early-market
    chaos, mania pumps) also trip it, so classify each against known events. Returns
    `[{ts, prev_close, close, ratio}]`; fewer than 2 rows → `[]`.
    """
    if frame.height < 2:
        return []
    flagged = (
        frame.sort("ts")
        .with_columns(pl.col("close").shift(1).alias("prev_close"))
        .with_columns((pl.col("close") / pl.col("prev_close")).alias("ratio"))
        .filter((pl.col("ratio") > max_ratio) | (pl.col("ratio") < 1 / max_ratio))
        .select("ts", "prev_close", "close", "ratio")
    )
    return flagged.to_dicts()


def qa_series(frame: pl.DataFrame, interval_secs: int) -> dict:
    """Compute the per-series QA summary for `frame` at `interval_secs` cadence.

    `coverage_pct` is actual rows over the expected candle count on the regular grid spanning
    `first_ts..last_ts` (`rows + missing_candles`), as a percentage.
    """
    rows = frame.height
    gaps = detect_gaps(frame, interval_secs)
    missing_candles = sum(gap["missing"] for gap in gaps)
    expected = rows + missing_candles

    return {
        "rows": rows,
        "first_ts": frame["ts"].min(),
        "last_ts": frame["ts"].max(),
        "gap_count": len(gaps),
        "missing_candles": missing_candles,
        "coverage_pct": (rows / expected * 100) if expected else 0.0,
        "wick_outlier_count": len(wick_outliers(frame)),
        "monotonic_ts": bool(frame["ts"].is_sorted() and frame["ts"].n_unique() == rows),
        "nonneg_volume": bool((frame["volume"] >= 0).all()),
    }


def qa_dataset(root: Path, intervals: dict[str, int], *, as_of: str | None = None) -> dict:
    """Run `qa_series` over every `root/{symbol}/{label}.parquet` for `label` in `intervals`.

    `symbol` is discovered from the directory tree (the path relative to `root`, e.g. `"BTC/EUR"`),
    not passed in. Returns `{as_of?, series: {"{symbol}/{label}": qa_series-dict}, summary}`, where
    `summary` is `{series_count, total_gaps, min_coverage_pct}`. `as_of` is included only when given.
    """
    entries = sorted(
        (
            (str(path.parent.relative_to(root)), label, interval_secs, path)
            for label, interval_secs in intervals.items()
            for path in root.rglob(f"{label}.parquet")
        ),
        key=lambda entry: (entry[0], -entry[2]),
    )

    series = {f"{symbol}/{label}": qa_series(read_parquet(path), interval_secs) for symbol, label, interval_secs, path in entries}

    coverages = [s["coverage_pct"] for s in series.values()]
    summary = {
        "series_count": len(series),
        "total_gaps": sum(s["gap_count"] for s in series.values()),
        "min_coverage_pct": min(coverages) if coverages else 0.0,
    }

    report: dict = {}
    if as_of is not None:
        report["as_of"] = as_of
    report["series"] = series
    report["summary"] = summary
    return report


def render_markdown(report: dict) -> str:
    """Render a QA `report` (as returned by `qa_dataset`) as a Markdown table + summary."""
    lines = ["# OHLC Dataset QA Report", ""]
    if "as_of" in report:
        lines += [f"As of: {report['as_of']}", ""]

    lines += [
        "| Series | Rows | Coverage % | Gaps | Missing candles | Wick outliers | Monotonic ts | Nonneg volume |",
        "| --- | ---: | ---: | ---: | ---: | ---: | :---: | :---: |",
    ]
    for name, s in report["series"].items():
        lines.append(
            f"| {name} | {s['rows']} | {s['coverage_pct']:.2f} | {s['gap_count']} | {s['missing_candles']} | "
            f"{s['wick_outlier_count']} | {s['monotonic_ts']} | {s['nonneg_volume']} |"
        )

    summary = report["summary"]
    lines += [
        "",
        "## Summary",
        "",
        f"- Series count: {summary['series_count']}",
        f"- Total gaps: {summary['total_gaps']}",
        f"- Min coverage %: {summary['min_coverage_pct']:.2f}",
    ]
    return "\n".join(lines) + "\n"
