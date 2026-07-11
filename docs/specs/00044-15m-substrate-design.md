# The 15m bar substrate for Bucket B (design)

**Iteration:** iter-085 (unattended research loop; decisions log `[iter-085]`). **Goal:** the B1 intraday family's data substrate — full-history **15-minute bars for the 12-pair universe**, derived from the Kraken 1-minute OHLCVT dumps by the existing, tested backfill machinery, QA'd (gap/density per pair) and **instrument-proved by an independent tick-derived reconciliation** — resolving T0012's storage decision (15m Parquet derivation; the tick catalog explicitly dropped for now).

## Why this shape (decisions `[iter-085]`)

- **Source = the 1-minute dumps via `cli/backfill`** — the same provenance and code path that built the canonical 1h/4h/1d (`aggregate_minutes` is already interval-parametric; iter-008 verified it bit-identical against REST). Adding `"15": 900` to `cli/ohlc/qa.py::INTERVAL_SECONDS` makes the whole pipeline (backfill, gap QA) 15m-capable. The dumps' native 15m files are redundant with this (and any disagreement would surface in the reconciliation cross-check); tick-primary aggregation is the expensive path better spent as the independent check.
- **Tick catalog dropped for now** — no current consumer (B1 consumes 15m bars; C2/C1 re-open the question under their own family topics). The raw zips stay on the NAS untouched.

## The derived dataset

- **Path:** `data/ohlc-15m/{BASE}/{QUOTE}/15.parquet` — a **new derived root**, never touching `data/ohlc-full` (immutable canonical). Same schema as canonical (via `cli.ohlc.ingest.to_frame`).
- **Provenance + hashes:** the backfill's existing manifest convention (`manifest.json`: per pair `rows`, `first_ts`, `last_ts`, `sha256`; plus `basket_sha256`) — the registry-referenceable dataset hash for every future B1 trial.
- **Source:** the NAS OHLCVT archive (`/home/zhaow/Projects/zcrypto-kraken-data/kraken-ohlcvt-updates/` — the full-history `Kraken_OHLCVT.zip` + quarterly incrementals), **read-only**; the merge across full+quarterly dumps follows whatever `cli/backfill`'s existing source-dir handling did for the canonical build (base-authoritative merge, iter-008) — consumed as-is, not redesigned.
- **Universe:** the 12 canonical pairs (the same basket file the canonical backfill used).

## QA + the instrument proof (before any B1 trial may consume this)

1. **Gap/density characterization per pair at 15m** (the iter-009 pattern via `detect_gaps` at 900 s): per-pair gap count/extent, empty-interval (omitted-candle) density by year — written into the iteration report. Expected: dense recent years, sparse early-illiquid alt history (the known T0004 residual); no NEW anomaly classes vs the 1h characterization.
2. **Tick-derived reconciliation** (the T0004 machinery at a new interval): `cli.tick.read` + `ticks_to_bars(interval_minutes=15)` on sampled windows per pair (one dense recent quarter per pair minimum, from the NAS tick zips), `cli.tick.reconcile.reconcile` against the dump-derived 15m — **acceptance: coverage and within-1% match rates consistent with T0004's 1h results (≥ 99.4% within 1% on dense windows; early-illiquid residuals disclosed, not hidden)**. A material miss is an instrument finding that stops the substrate from shipping, not a tolerance to loosen.
3. **Seam check:** the 15m frame's aggregation to 1h must reproduce the canonical 1h bars on overlapping stamps for sampled windows (internal consistency of the derivation chain).

## Code deltas (all small, TDD)

1. `cli/ohlc/qa.py::INTERVAL_SECONDS` gains `"15": 900` (typed test: backfill_pair emits a 15m frame with 900 s buckets; detect_gaps at 900 s).
2. A thin driver (script-level or a `cli/backfill` function reuse — NOT a new CLI subcommand; nothing user-facing) that runs `run_backfill(..., intervals=["15"], out_root=data/ohlc-15m)` for the basket and prints the manifest summary. If `run_backfill` already covers it verbatim, no new code beyond the interval key.
3. The reconciliation/QA driver as a tested function (sampling windows, calling the existing tick + reconcile machinery), with the report numbers emitted as its return value — no new frameworks.

## Out of scope

B1 trials themselves (next iteration, against this substrate's dataset hash); the tick catalog; any change to `data/ohlc-full`, the engine, or capture; REST-based 15m top-up (the dumps end at the last quarterly — B1 backtests on dump history; freshness top-up is a B1-iteration concern if it needs it).

## Closeout

T0012 resolved (storage decision made + substrate delivered + catalog explicitly dropped with the re-open note) → archive per lifecycle; iterations-history entry; the report's next-step = B1 family opening (its own topic/spec per T0016's split rule).
