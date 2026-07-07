---
status: open
---

# Full tick history ingestion + tick-derived bar reconciliation

## Context — what

Phase 1's autonomous loop (master-plan §12) lists *"pull full tick history for the candidate pairs; build 15m/1h/4h/1d bars from ticks and reconcile vs OHLCVT (tolerance test)"*, and the exit bar wants *"candle reconciliation within tolerance on ≥99.5% of intervals."* The completed Phase-1 work reconstructed canonical 1h/4h/1d bars from the **1-minute OHLCVT dumps** (iter-008) and reconciled them **bit-identically to the REST OHLC** (100% match) and **cross-checked vs Binance** (iter-012) — but it never ingested **trade-level (tick) data**, so the specific *tick-derived-bars-vs-OHLCVT* reconciliation and a **true** (tick-weighted) vwap are not yet done. The current vwap is the Σ(close·vol)/Σvol proxy (iter-008).

## Why this matters

Tick data is the substrate for two master-plan bets: **intraday microstructure features** (§1, §6 — trade-flow, realized-vol-from-ticks, seasonality) that Phase 4 mines, and a **true vwap** to replace the reconstruction proxy. The tick-vs-OHLCVT reconciliation is the exit-bar tolerance test that would independently corroborate the OHLCVT dumps at trade granularity. Absent it, the dataset is validated at 1-minute granularity (strong: 100% OHLC match vs REST + Binance cross-check) but not at tick granularity — acceptable for the 1h/4h/1d research of Phases 2–4, insufficient for tick-level feature work.

## Findings so far

- **The tick data is not on the NAS.** `../zcrypto-kraken-data/kraken-ohlcvt-updates/` holds only OHLCVT ZIPs (base + quarterlies) — no trade/tick dumps. So this is **blocked on data acquisition**, unlike the OHLCVT work which had its dumps in hand.
- **Two acquisition paths, both heavy.** (a) Kraken publishes downloadable **full time-and-sales (tick) CSVs per pair** (§2) — the clean path, mirroring how the OHLCVT dumps were **manually downloaded** to the NAS (a human/side action, then autonomous ingestion). (b) The public REST **Trades endpoint pages the complete history from `since=0`** (§2, keyless) — fully autonomous but a multi-GB, rate-limited, many-hour paged pull per pair (BTC/EUR alone is >10 years of trades), impractical inside a single unattended loop iteration.
- **Not on the Phase-2/3/4 critical path.** Those phases run on the existing 1h/4h/1d canonical dataset; tick data is a Phase-4-microstructure / true-vwap enhancement — hence deferred to a future phase, not a current-phase autonomous miss.
- The OHLCVT-derived reconstruction (`cli/backfill/`) already emits the 8-field row shape and reconciliation scaffolding (`cli/backfill/reconcile.py`), so a tick→bar aggregator can reuse the same canonical-schema + reconcile pattern (TDD on synthetic tick fixtures, as iter-008 did for OHLCVT).

## Suggested next steps

- **Prefer the manual-download path** (mirroring OHLCVT): fetch Kraken's per-pair full tick CSVs to the NAS, then build a `cli` tick-ingestion module (TDD on synthetic fixtures) → tick storage → 15m/1h/4h/1d bar builder (with **true** tick-weighted vwap) → reconcile vs the OHLCVT-derived bars (tolerance test) → catalog + hashes.
- If manual download is undesirable, scope a **bounded, resumable** REST Trades backfill (checkpointed by `since` cursor, rate-limit-aware) as its own multi-session job — do **not** attempt a full pull inside one loop iteration.
- Pick up when Phase 4 microstructure features or a true-vwap requirement makes the tick substrate load-bearing.
