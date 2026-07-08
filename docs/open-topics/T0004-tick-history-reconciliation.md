---
status: partial
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
- **Sample reconciliation** (`docs/tick-reconciliation-report.md`): all 10 EUR majors, Q1-2026,
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
- **Full-history BTC/EUR reconciliation** (`docs/tick-reconciliation-report.md`): 102.4 M ticks
  (2013-09-10 → 2025-12-31) → 106,626 hourly bars, **100.0000 % coverage**. Match: **99.94 % within
  1 %, 97.23 % within 10 bp**, but only 77 % at 1e-6 — the strict miss is sub-10-bp cross-source
  storage-precision noise (median close reldiff 0.000 bps every year; same code gives 100 % on
  Q1-2026), with just **68 bars (0.064 %) genuinely diverging > 1 %**, isolated to 2013–2015
  early-illiquid history.

## Suggested next steps

Remainder (the full-**universe** batch + tick-level enhancements):
- **Full-universe full-history batch** — extend the BTC/EUR full-history run to the other 9 majors
  (each ~GB complete member, billions of ticks total) → then this topic can flip to `resolved`. The
  reader now handles the format; this is the deferred heavy batch job. Fold in the exit-bar tolerance
  question the BTC run surfaced (1 % band clears ≥99.5 %; 1e-6 is precision-noise-limited) and the
  0.064 % early-illiquid >1 % divergences (flag or accept).
- **15-minute bars + tick storage/catalog** — the aggregator is interval-parametric, so 15m is
  trivial once there is an OHLCVT 15m (or another) reference to reconcile against; a parse-on-demand
  model suffices for reconciliation, so a tick storage/catalog layer is only needed if Phase-4
  microstructure features want repeated tick access.
- Pick up the full-history batch + microstructure-feature substrate when Phase 4 needs it load-bearing.
