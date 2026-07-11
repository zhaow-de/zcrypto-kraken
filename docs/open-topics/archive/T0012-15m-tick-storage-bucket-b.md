---
status: resolved
---

# 15m bars + tick storage/catalog for the Bucket-B intraday families

## Context — what

Split out of **archived T0004**, whose resolution folded this into "the Bucket-B queue" — a live deferral buried in an archive file that is never reviewed (the second motivating example for the deferral-registration rule). `cli/tick.ticks_to_bars` is interval-parametric (15m is one argument); what's missing is a storage/catalog decision for repeated tick/15m access.

## Why this matters

Master-plan §5's B1 (intraday trend + seasonality, 1h/4h core with 15m scheduling relevance) and any microstructure feature need efficient repeated access to tick-derived bars; parse-on-demand from the ~GB per-pair CSVs is fine once, not per-iteration.

## Findings so far

The full-universe tick reconciliation (iters 042–043) proved the reader + `ticks_to_bars` at 1h against the canonical dataset (100 % coverage, ≥99.4 % within 1 %). No 15m bars have been built; no tick storage/catalog exists (raw zips on NAS).

## Suggested next steps

- Decide storage: one-off 15m Parquet derivation per pair (mirroring `data/ohlc-full/`) vs a tick-level Parquet catalog; hash-version either as a derived dataset (never overwriting canonical paths).
- Build + QA (gap/density characterization per pair, as iter-009 did for 1h/1d) before any B-family consumes it.

## Resolution (iter-085, 2026-07-11)

The storage decision: **15m Parquet derivation** mirroring `data/ohlc-full` — built at `data/ohlc-15m/` (12 pairs, ~3.12M bars, `basket_sha256 0fed24a6…`) from the 1-minute OHLCVT dumps via the existing `cli/backfill` machinery (`"15": 900` interval key + `cli/backfill/substrate15m.py`; spec/plan `00044`). Instrument-proved before any B1 consumption: tick reconciliation 100.0000% coverage and 100% within 1% (in fact bit-exact) on Q1-2026 windows across all 12 pairs; seam 15m→1h ratified "exact up to float summation order" (volume ≤ 2 ULP + exact Int64 count leg proving per-hour minute-set identity, zero mismatches over 25,909 hours). **The tick-level Parquet catalog was explicitly dropped** — no current consumer; the question re-opens under C2/C1's own family topic when those become live (raw tick zips stay on the NAS untouched).
