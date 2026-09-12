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

## Resolution (iter-085, 2026-07-11)

The storage decision: **15m Parquet derivation** mirroring `data/ohlc-full` — built at `data/ohlc-15m/` (12 pairs, ~3.12M bars, `basket_sha256 0fed24a6…`) from the 1-minute OHLCVT dumps via the existing `cli/backfill` machinery (`"15": 900` interval key + `cli/backfill/substrate15m.py`; spec/plan `00044`). Instrument-proved before any B1 consumption: tick reconciliation 100.0000% coverage and 100% within 1% (in fact bit-exact) on Q1-2026 windows across all 12 pairs; seam 15m→1h ratified "exact up to float summation order" (volume ≤ 2 ULP + exact Int64 count leg proving per-hour minute-set identity, zero mismatches over 25,909 hours). **The tick-level Parquet catalog was explicitly dropped** — no current consumer; the question re-opens under C2/C1's own family topic when those become live (raw tick zips stay on the NAS untouched).

Both steps this topic listed are discharged by that work, and by it alone.

**The steps this topic carried at its close, kept verbatim with what answered each:**

- Decide storage: one-off 15m Parquet derivation per pair (mirroring `data/ohlc-full/`) vs a tick-level Parquet catalog; hash-version either as a derived dataset (never overwriting canonical paths). — **ANSWERED:** the derivation above was taken — `data/ohlc-15m/`, hash-versioned under its own `basket_sha256` and never over a canonical path — with the tick-level catalog, its stated alternative, consciously dropped for want of a consumer (`cli/backfill/substrate15m.py`, spec/plan `00044`).
- Build + QA (gap/density characterization per pair, as iter-009 did for 1h/1d) before any B-family consumes it. — **ANSWERED:** both instruments ran per pair before any B1 read the dataset, and they are two separate requirements of spec `00044` rather than one. The gap/density characterization "shows only known anomaly classes (2013 illiquidity, 2018-01-11 venue outage, thin AVAX/LINK/DOT recent years — B1 design input)"; the independent tick reconciliation is the 100.0000 % coverage / bit-exact leg recorded above (both in the iter-085 verdict, `docs/research/10.phase4-decisions.md`).
