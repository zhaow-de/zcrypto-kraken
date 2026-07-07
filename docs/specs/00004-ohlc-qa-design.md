# OHLC Dataset QA Report — Design (Phase 1)

**Iteration:** iter-006 · **Phase:** 1 (Data Foundation) · **Status:** design approved (unattended loop)
**Master plan refs:** §8 (data-QA policy — empty-interval detection, outlier/wick audit, exit criteria), §Phase 1 (data-QA report generator).

## Problem & context

The iter-004 OHLC dataset needs a QA layer that surfaces data-quality issues before it feeds any backtest: **gaps** on the interval grid (Kraken omits no-trade candles — §8), **wick/outlier** candles, and basic integrity. Read-only; it reports, it does not mutate the dataset (empty-interval *reconstruction* is a follow-up).

## Goals

- `cli/ohlc/qa.py` — pure functions computing a per-series and whole-dataset QA report over the canonical OHLC Parquet, TDD on synthetic frames (no live network). A committed QA report for the v0 dataset.

## Non-goals

- No empty-interval reconstruction (report gaps, don't fill — follow-up). No Binance-Vision cross-check (follow-up). No new deps (stdlib + polars). No dataset mutation.

## Design

**`cli/ohlc/qa.py` (pure, polars):**

- `detect_gaps(frame: pl.DataFrame, interval_secs: int) -> list[dict]`: on the sorted `ts`, find consecutive rows whose gap exceeds `interval_secs`; return `[{after_ts, before_ts, missing}]` where `missing = gap/interval_secs - 1`. (`to_frame` already guarantees sorted/deduped, so this is a clean diff.)
- `wick_outliers(frame: pl.DataFrame, *, rel_range: float = 0.20) -> list[dict]`: candles where `(high - low) / close > rel_range` (extreme intraday range) — return `[{ts, high, low, close, rel_range}]`. A configurable heuristic flag, not a hard failure.
- `qa_series(frame: pl.DataFrame, interval_secs: int) -> dict`: `{rows, first_ts, last_ts, gap_count, missing_candles, coverage_pct (actual/expected on the grid), wick_outlier_count, monotonic_ts (bool), nonneg_volume (bool)}`.
- `qa_dataset(root: Path, intervals: dict[str,int]) -> dict`: run `qa_series` over `root/{symbol}/{interval}.parquet` (reading via `cli.ohlc.read_parquet`); return `{as_of, series: {...}, summary: {series_count, total_gaps, min_coverage_pct}}`. (`intervals` maps the interval label used in the path to its seconds.)
- `render_markdown(report: dict) -> str`: a per-series table (rows, coverage%, gaps, wick outliers, integrity) + summary.

Interval seconds: 1440→86400, 240→14400, 60→3600 (a small constant map, exported).

## Testing

`tests/test_ohlc_qa.py` on synthetic polars frames (built inline; no live network):
- `detect_gaps`: a frame with one deleted mid-series candle yields one gap with `missing == 1`; a contiguous frame yields none.
- `wick_outliers`: a planted extreme-range candle is flagged; normal candles are not; the threshold is respected.
- `qa_series`: `coverage_pct` = actual/expected over the grid; `monotonic_ts`/`nonneg_volume` correct; counts right.
- `render_markdown`: contains the series rows + summary.

## Deferred / parked

Empty-interval reconstruction (fill no-trade candles), Binance-Vision cross-venue reconciliation, the symbol & corporate-action ledger → follow-up Phase-1 iterations. Full-history QA improves once T0001 backfill lands.

## Closeout (planned)

On merge: generate the QA report over the live v0 dataset → commit `docs/ohlc-qa-report.md`; append the `iter-006` iterations-history entry.
