# Iterations history — Phase 2 (Validation Harness & Cost Model)

Per-iteration changelog for Phase 2. Appended at each iteration's close-out; see `.claude/rules/prose.md`.

## 2026-07-08 — iter-013: CPCV splitter — validation harness opens (Phase 2)

- **`cli/validation/` opens with the CPCV splitter** — a strategy is scored through purged, embargoed combinatorial folds from here on, never a plain train/test split.
- **The caller owns the embargo width**: it must be at least the label horizon plus the feature lookback, and each contiguous test block is trimmed on both sides independently.
- **Design and plan**: `docs/specs/00006-cpcv-splitter-design.md`, `docs/plans/00006-cpcv-splitter.md`.
- **Deferred, and nothing else in the tree carries it**: the purge/embargo properties bound the windows as *sufficient*, never as *tight*, so leakage-safe over-trimming goes unasserted — a two-sided-bound assertion is owed.

## 2026-07-08 — iter-014: deflated & probabilistic Sharpe ratio (Phase 2)

- **`cli/validation/dsr.py` deflates a trial's Sharpe by the trial budget** — more trials raise the bar, so a headline Sharpe is read deflated, never raw.
- **Degenerate input raises instead of returning NaN** — the PoC minted a fake winner from a NaN deflated Sharpe, and the trial registry asserts that integrity on read.
- **Design and plan**: `docs/specs/00007-deflated-sharpe-design.md`, `docs/plans/00007-deflated-sharpe.md`.

## 2026-07-08 — iter-015: probability of backtest overfitting (Phase 2)

- **`cli/validation/pbo.py` reports the probability of backtest overfitting** — an in-sample-best configuration is now quoted with the chance it sits below the out-of-sample median.
- **Bounded by construction, so never NaN** — a degenerate performance matrix, split count or metric raises instead.
- **Design and plan**: `docs/specs/00008-pbo-design.md`, `docs/plans/00008-pbo.md`. With the deflated Sharpe this completes the overfitting-detection pair a trial is judged on.

## 2026-07-08 — iter-016: stationary block bootstrap CIs (Phase 2)

- **`cli/validation/bootstrap.py` puts a confidence interval on any statistic** — seeded and reproducible from the seed alone, with the RNG function-local so global state cannot move a result.
- **A degenerate series, block length, alpha, seed or statistic raises** rather than crashing or returning NaN.
- **`T0006` parked the non-numeric-type-guard gap** as one coherent harness-hardening pass rather than a piecemeal fix — none of those paths can return NaN, so it is consistency, not a validity hole.
- **Design and plan**: `docs/specs/00009-stationary-bootstrap-design.md`, `docs/plans/00009-stationary-bootstrap.md`.

## 2026-07-08 — iter-017: Kraken cost model — fees + margin (Phase 2)

- **`cli/costs/` costs a trade against the confirmed July-2026 Kraken ladder** — fee tier by 30-day volume plus per-base margin carry (an opening fee plus one rollover per completed 4h hold), transcribed from `docs/reference/kraken-fee-schedule.md`.
- **Base Tier 1 is 0.40 % maker / 0.80 % taker** per that fee schedule, superseding the master plan's older 0.25/0.40 snapshot — quote the reference, not §1/§4/§14.
- **Design and plan**: `docs/specs/00010-cost-model-design.md`, `docs/plans/00010-cost-model.md`, which record the explicit non-goals — the spread term (capture-gated), the combined total-trade-cost helper that needs it, and the AoP qualification path (moot at our size).

## 2026-07-08 — iter-018: performance statistics (Phase 2)

- **`cli/validation/metrics.py` holds the headline statistics** — Sharpe, volatility, annualized return and max drawdown; the bootstrap CIs and the acceptance suite consume these rather than hand-rolled arithmetic.
- **Zero-variance returns and any period return at or below −100 % raise** rather than silently producing NaN or a broken equity curve.
- **Design and plan**: `docs/specs/00011-perf-metrics-design.md`, `docs/plans/00011-perf-metrics.md`, which record sortino/Calmar, returns-from-prices and benchmark-relative deltas as YAGNI non-goals.

## 2026-07-08 — iter-019: trial-registry hash chain (Phase 2)

- **`cli/registry/` chains each trial record to its predecessor** — a tamper that recomputes the edited record's own hash now breaks the next record's link, which the self-hash alone never caught.
- **Schema version 2 rejects a version-1 record unconditionally.**
- **Design and plan**: `docs/specs/00012-registry-hash-chain-design.md`, `docs/plans/00012-registry-hash-chain.md`, which record the external-anchor non-goal; the corruption check is reused as an acceptance-suite member.

## 2026-07-08 — iter-020: acceptance suite — recovery + null (Phase 2)

- **`cli/validation/synthetic.py` and `tests/test_acceptance.py` compose the harness end-to-end on synthetic data** — planted signal recovered, pure noise rejected at about the nominal false-positive rate.
- **Read the scope precisely**: the run exercises fold structure, not purge/embargo leak prevention — the toy rule is not fit to data, so there is nothing to leak; the injected-leak check is its own iteration.
- **Design and plan**: `docs/specs/00013-acceptance-recovery-null-design.md`, `docs/plans/00013-acceptance-recovery-null.md`. A §12 exit-bar step; the cost model against captured spreads stays capture-gated.

## 2026-07-08 — iter-021: validation numeric-param type guards — T0006 (Phase 2)

- **`cli/validation/` refuses a non-numeric type on its float parameters with the harness's own error** instead of a bare `TypeError` — one never-crash discipline across the package.
- **Closed per `T0006`'s own defined scope, not "pattern eliminated everywhere"** — the deflated-Sharpe count parameters stay finiteness-checked only, because they feed arithmetic and can never yield NaN. `T0006` resolved and archived, index synced.
- **No committed spec or plan** — mechanical single-pattern hardening under the trivial-change carve-out; the topic itself was the design.

## 2026-07-08 — iter-022: acceptance suite — injected-leak detection (Phase 2)

- **`cli/validation/synthetic.py` and `tests/test_acceptance_leak.py` prove a planted look-ahead leak is removed** — and removed by purge and embargo together, since neither one-sided setting collapses it alone.
- **The §9 acceptance checks are complete on synthetic data** — recovery, null, injected leak, registry corruption; the one Phase-2 exit-bar row still open is the cost model against captured spreads, capture-gated.
- **Design and plan**: `docs/specs/00014-acceptance-leak-design.md`, `docs/plans/00014-acceptance-leak.md`.

## 2026-07-08 — iter-023: SPA / White reality check (Phase 2)

- **`cli/validation/spa.py` tests the best of a strategy family against the benchmark with a data-snooping correction** — reusing the stationary bootstrap rather than a second resampler.
- **The p-value is bounded away from zero and never NaN**, and a below-nominal null false-positive rate is the reality check's known conservativeness, not under-calibration — read it as such before concluding the test is broken.
- **The multiple-testing core is complete**; the benchmark family it runs against is fixed in Phase 3. Spec and plan `00015`.

______

**Continuation — post-close-out backlog.** Phase 2 closed 2026-07-08 with one exit-bar row carried forward: *"cost model validated against ≥2 weeks of captured spreads"*, T0003-gated. The entry below is that work.

______

## 2026-07-22 — iter-114: the cost model's captured-spread term, calibrated ([[T0014]], spec `00066`)

- **`cli/costs/spread.py` gives a trade its captured-spread leg and the combined round-trip helper the Phase-2 closeout deferred with it** — calibrated from our own `l2-panel` capture rather than a vendor quote; above the largest pinned notional it refuses instead of extrapolating a convex curve, and between pinned sizes it interpolates in log notional.
- **Quote a spread number from `docs/reference/captured-spread-calibration.md`**, which carries the two standing readings — never a *median* top-of-book spread for BTC/EUR (tick quantisation makes it swing; cite the mean or the effective spread at size), and no per-session dimension, rejected on **materiality** rather than absence.
- **Phase 2's "≥2 weeks" exit-bar row was NOT discharged here** — the panel window fell short of the literal clause — and archived [[T0091]] carries the restamp; the constants are a benign-regime estimate with day-level uncertainty, not a converged parameter.
- **The record's modeled `0.006/side` is a maker fee plus a headroom guess this calibration shows is far too large, and whether the model over- or under-charges turns on the unmade maker-vs-taker execution decision** — [[T0090]]; trial 44's registered verdict was never re-read at the realistic stack, and no new trial was registered here.
- **[[T0014]] resolved; `tests/test_costs_spread.py` pins table and provenance together**, so a recalibration without a new stamp fails rather than silently repricing history. Decisions route by subject matter — `03.phase2-decisions.md` here, the trial-44 re-read in `13.phase5-decisions.md`, the fee-tier finding in `14.phase6-decisions.md`.
