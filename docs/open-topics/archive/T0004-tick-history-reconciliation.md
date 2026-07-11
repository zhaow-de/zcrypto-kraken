---
status: resolved
---

# Full tick history ingestion + tick-derived bar reconciliation

## Context — what

Phase 1's autonomous loop (master-plan §12) lists *"pull full tick history for the candidate pairs; build 15m/1h/4h/1d bars from ticks and reconcile vs OHLCVT (tolerance test)"*, and the exit bar wants *"candle reconciliation within tolerance on ≥99.5% of intervals."* The completed Phase-1 work reconstructed canonical 1h/4h/1d bars from the **1-minute OHLCVT dumps** (iter-008) and reconciled them **bit-identically to the REST OHLC** (100% match) and **cross-checked vs Binance** (iter-012) — but it never ingested **trade-level (tick) data**, so the specific *tick-derived-bars-vs-OHLCVT* reconciliation and a **true** (tick-weighted) vwap are not yet done. The current vwap is the Σ(close·vol)/Σvol proxy (iter-008).

## Why this matters

Tick data is the substrate for two master-plan bets: **intraday microstructure features** (§1, §6 — trade-flow, realized-vol-from-ticks, seasonality) that Phase 4 mines, and a **true vwap** to replace the reconstruction proxy. The tick-vs-OHLCVT reconciliation is the exit-bar tolerance test that would independently corroborate the OHLCVT dumps at trade granularity. Absent it, the dataset is validated at 1-minute granularity (strong: 100% OHLC match vs REST + Binance cross-check) but not at tick granularity — acceptable for the 1h/4h/1d research of Phases 2–4, insufficient for tick-level feature work.

## Findings so far

- **The tick data has since been acquired** (iter-039): the manual-download path below was taken — Kraken's per-pair time-and-sales ZIPs now live at `../zcrypto-kraken-data/kraken-trades/` (`Kraken_Trading_History.zip` complete + quarterlies). (When this topic was opened the data was **not** on the NAS, which had blocked the work.)
- **Two acquisition paths, both heavy.** (a) Kraken publishes downloadable **full time-and-sales (tick) CSVs per pair** (§2) — the clean path, mirroring how the OHLCVT dumps were **manually downloaded** to the NAS (a human/side action, then autonomous ingestion). (b) The public REST **Trades endpoint pages the complete history from `since=0`** (§2, keyless) — fully autonomous but a multi-GB, rate-limited, many-hour paged pull per pair (BTC/EUR alone is >10 years of trades), impractical inside a single unattended loop iteration.
- **Not on the Phase-2/3/4 critical path.** Those phases run on the existing 1h/4h/1d canonical dataset; tick data is a Phase-4-microstructure / true-vwap enhancement — hence deferred to a future phase, not a current-phase autonomous miss.
- The OHLCVT-derived reconstruction (`cli/backfill/`) already emits the 8-field row shape and reconciliation scaffolding (`cli/backfill/reconcile.py`), so a tick→bar aggregator can reuse the same canonical-schema + reconcile pattern (TDD on synthetic tick fixtures, as iter-008 did for OHLCVT).

## Done so far

Iteration **iter-039** (spec `docs/specs/00028-tick-reconciliation-design.md`, plan
`docs/plans/00028-tick-reconciliation.md`) built the tick→bar machinery and **sample-validated it at
100 %**:

- **`cli/tick/`** — `read_trades_csv` (Kraken trades CSV, header + headerless auto-detect, from a path
  or a ZIP member), `ticks_to_bars` (left-closed epoch-aligned OHLCV bars + `count` + **true**
  tick-weighted `vwap` = Σpv/Σv), `reconcile` (per-interval O/H/L/C match vs the canonical OHLCVT,
  worst-mismatch surfacing), and the `XBT→BTC`/`XDG→DOGE` pair map. TDD, 25 synthetic-fixture tests.
- **Sample reconciliation** (`docs/research/02.phase1-tick-reconciliation-report.md`): all 10 EUR majors, Q1-2026,
  ~7.98 M ticks → **100.000 % O/H/L/C match within 1e-6 on all 30 pair×interval cells (1h/4h/1d), at
  100.0000 % coverage** — clears the ≥99.5 % exit-bar tolerance test for the sample. The true tick
  VWAP differs from the stored close-weighted proxy by ~1 bp (liquid) up to ~200 bps tails (illiquid).
- **Data-schema finding:** the quarterly ZIPs are 7-field-with-header; the **complete** dataset is
  headerless **3-field `Timestamp,Price,Volume`** (no side).

Iteration **iter-042** added the complete-dataset reader + a **full-history** BTC/EUR run:

- **`read_trades_csv` now auto-detects the complete 3-column layout** (a 3-field row whose first field
  is a plausible Unix timestamp `≥ 1e9` → `ts,price,volume` with null side; a small first field is
  still a malformed 4-field row and errors). TDD (2 new tests; the disambiguation keeps the existing
  malformed-row tests green).
- **Full-history BTC/EUR reconciliation** (`docs/research/02.phase1-tick-reconciliation-report.md`): 102.4 M ticks
  (2013-09-10 → 2025-12-31) → 106,626 hourly bars, **100.0000 % coverage**. Match: **99.94 % within
  1 %, 97.23 % within 10 bp**, but only 77 % at 1e-6 — the strict miss is sub-10-bp cross-source
  storage-precision noise (median close reldiff 0.000 bps every year; same code gives 100 % on
  Q1-2026), with just **68 bars (0.064 %) genuinely diverging > 1 %**, isolated to 2013–2015
  early-illiquid history.
- **iter-043 — full-**universe** full-history batch done:** all 10 majors, complete dataset →
  **660,343 hourly bars, 100.0000 % coverage**; **9 of 10 pairs match ≥ 99.7 % within 1 %**, total
  1088 bars (0.165 %) diverge > 1 %, all in each pair's early-illiquid history. Weakest is LTC/EUR
  (99.37 % within 1 %; 606 of its 611 outliers in 2013–2017, near-clean from 2018). Precision-noise-
  limited at 1e-6 (77–91 %). Table + per-year LTC breakdown in `docs/research/02.phase1-tick-reconciliation-report.md`.

## Resolution (2026-07-09, iter-044 open-topics sweep)

The human **confirmed the exit-bar tolerance is acceptable** (via `/research-loop`): the ≥99.5 %-of-intervals reconciliation is met at a **1 % band** (9/10 pairs ≥99.7 %; LTC 99.37 %, dragged only by 2013–2017 sparse data), with the residual a characterized, early-illiquid, cross-source precision property — not aggregation error. So the tick-vs-OHLCVT reconciliation is **complete and accepted**, closing the Phase-1 tick-granularity exit-bar item and delivering the true tick-weighted VWAP.

The one remaining item — **15-minute bars + a tick storage/catalog** — is **not a standalone follow-up**: `cli/tick.ticks_to_bars` is interval-parametric (15m is one argument), and a parse-on-demand model already suffices, so this is folded into the **Bucket-B intraday families** (§5: B1 trend/seasonality, B2 derivatives-positioning) — built there if/when a B-family needs repeated tick/15m access. Nothing autonomously-resolvable remains here.
