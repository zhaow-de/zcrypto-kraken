from __future__ import annotations

from pathlib import Path

import polars as pl

from cli.ohlc.dataset import read_parquet

# 1d / 4h / 1h (matching `cli.ohlc.DEFAULT_INTERVALS`) plus 15m, keyed by the on-disk interval label.
INTERVAL_SECONDS = {"1440": 86400, "240": 14400, "60": 3600, "15": 900}


def detect_gaps(frame: pl.DataFrame, interval_secs: int) -> list[dict]:
    """Find gaps in `frame`'s `ts` column exceeding `interval_secs`; `frame` is assumed sorted (`to_frame` guarantees it).

    Each gap is `{after_ts, before_ts, missing}`, `missing` counting the grid candles absent between the two timestamps.
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
    """Return bar-over-bar close moves beyond `max_ratio`x or below `1 / max_ratio` — candidate corporate actions or data errors.

    Genuine crypto moves trip it too, so classify each `{ts, prev_close, close, ratio}` hit against known events.
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
    """Compute the per-series QA summary for `frame` on the `interval_secs` grid.

    `coverage_pct` is rows as a percentage of the candles that grid holds between `first_ts` and `last_ts`.
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

    `symbol` is the parquet's directory relative to `root`; each series is keyed `"{symbol}/{label}"`, e.g. `"BTC/EUR/1440"`.
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
