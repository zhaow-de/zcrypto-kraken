# A1 — vol-targeted long/flat/short trend book (Bucket-A alpha family) — Design

**Iteration:** iter-044 (spec only — execution is the next iteration) · **Phase:** 4 (Alpha Research Sprints, Bucket A) · **Status:** design approved (unattended loop); **not yet executed**
**Refs:** `docs/research/05.phase4-orientation.md` (the A1 kickoff + the four Phase-3 findings that shape it), master-plan §5 (ranked queue), §9 (validation protocol / deployment rule), §12 (Phase-4 kill bar + Decision Register). Consumes `cli/features/` (iter-040/041), `cli/benchmark/strategies.py` (`vol_target`, `sma_gate`, `returns_from_prices`, `run_backtest`), `cli/validation/` (CPCV/DSR/PBO/bootstrap/SPA), `cli/registry/` (trials), `cli/costs/` (Kraken cost model).

## Problem & context

Phase 3 froze the deployment bar at **gated-B1** (vol-targeted BTC × 200-day long/flat gate; full-history Sharpe 1.247, maxDD 12.3 %, ~1.12 after fees, worst year −5.5 %). A1 is the first Bucket-A alpha: extend that survivor into a **vol-targeted long/flat/short trend book over the majors**, and test — under the §12 kill bar — whether it beats gated-B1 net of stressed costs at its registered trial count. Per §9's deployment rule the deployed system is the best of {benchmarks ∪ validated survivors}, so A1 earns its place only by beating the bar on DSR/SPA, not on a point estimate.

**The four Phase-3 findings are binding on the design** (orientation memo): (1) the majors basket *underperformed* single-asset BTC — the basket base is not a free win and must be A/B'd, not assumed; (2) naive lagging-gate *shorting* was disastrous (B4 Sharpe −0.136) — the short state must be the §5 confirmed-bear design, not a gate flip; (3) on the basket the regime gate was *redundant* with vol-targeting — an ensemble must beat the single gate to justify itself; (4) estimation uncertainty is large — beating the point estimate is not enough, the edge must survive DSR + SPA + 1.5× cost stress + the worst walk-forward slice.

## Goals

New `cli/alpha/` package (`a1.py`, `errors.py`, `__init__.py`), pure-Python/list-based like `cli/benchmark/`, consuming the reviewed causal features. It builds a **per-asset → aggregated book net-return series** (strictly look-ahead-free, `sma_gate` alignment: every position for return-period `k` is decided from prices/features at `≤ k`), parameterized by four toggles — **each toggle combination is one registered trial**:

1. **base** ∈ {`btc_only`, `equal_risk_basket`} — a BTC-anchored book vs an inverse-vol majors basket (finding 1). Uses `inverse_vol_basket` for the basket leg.
2. **regime** ∈ {`single_gate`, `ensemble`} — the 200-day BTC `sma_gate` alone, vs an ensemble (`sma_gate` **and** per-asset `trend_agreement > 0`) (finding 3).
3. **short** ∈ {`off`, `confirmed_bear`} — long/flat, vs adding a short state entered only on *confirmed* bear (price < SMA − band **and** `trend_agreement < 0`) at **≤ 0.5×** exposure (finding 2). Never a gate flip.
4. **vol_target** — the book scaled to 10–12 %/yr via `vol_target` (fixed; a small {10,12} check at most, not a sweep).

**Feature inputs (all built + leak-tested, iter-040/041):** `momentum` (multi-horizon), `channel_position`, `realized_vol` (the book vol-target input), `trend_agreement` (the ensemble/short signal), `drawdown_state`, plus `sma_gate` (BTC regime). No new features expected; if one is, it ships leak-tested.

## Verdict protocol (§12 Phase-4 kill bar)

For **every** toggle combination, register a trial (`cli/registry/` — the registry's first real records) and evaluate net of costs: CPCV + walk-forward, stressed at **1.5×** the confirmed Kraken fee/margin rates (`cli/costs/`). A variant is **archived** unless **all** hold: DSR > 0 at its trial count, **SPA beats gated-B1**, it survives 1.5× cost stress, and its worst walk-forward regime slice is not disqualifying. The short leg additionally gets a **whipsaw kill test** in isolation (turnover, hit-rate, drawdown of the short leg alone — finding 2). Prove the treatment engaged before reading any result (arms must differ; the gate/short must change exposure somewhere — the "distrust the instrument" gate).

## Non-goals / boundaries

- **The honest base A/B (finding 1) needs the full-history dynamic-composition basket (T0007, parked).** A1 uses the **available** aligned majors data (as iter-036's common-window proxy) with that caveat explicit; if the basket can't clear BTC even here, that is a strong (if window-limited) refutation and A1 collapses toward `btc_only`. The definitive full-history basket remains T0007.
- **No holdout touch** (look budget = 1, spent in Phase 5 with the human), **no new data spend**, **no A2** (the per-asset TSMOM ensemble is a separate A/B within Bucket A — its own spec). No live/paper trading (Phase 6).
- **Escalate to the human only** for the §12 triggers: new data spend, abandoning Bucket A early, trial-budget expansion (A = 40), any holdout temptation.

## Testing / done

TDD (`tests/test_alpha_a1_*.py`), synthetic fixtures first:

- **The book assembler is leak-tested** — a planted change to `prices[k+1:]` cannot alter any position at `≤ k` (the same look-ahead regression guard the features carry, at the book level).
- **Engagement evidence** — toggles demonstrably change the series (arms differ; the gate/short changes exposure on a constructed regime; the ensemble differs from the single gate on a constructed split).
- **Planted-signal recovery through the harness** — a synthetic trending series is scored positive; a null scores ≈ 0 (the harness proves itself on known answers before its verdicts count).
- **Registry invariants** — each variant produces a valid trial record (finite DSR, monotonic trial count, hash chain intact).
- Then the **real-data kill-bar run** per variant → an A/B verdict (adopt/reject/park) recorded in `.tmp/decisions.md` + the trial registry, and an iterations-history entry.

## Closeout (planned, at execution)

The execution iteration writes: the per-variant kill-bar verdicts (registry + decision log), the iterations-history entry, and — if a variant clears the bar — a Phase-4 A1 result note under `docs/research/`. If **none** clears gated-B1, that is a **success** (an honest kill / "benchmark wins"), recorded as such. This spec iteration logs only the design decision in `.tmp/decisions.md` (`[iter-044]`).
