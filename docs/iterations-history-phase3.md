# Iterations history — Phase 3 (Benchmarks & the Bar to Beat)

Per-iteration changelog for Phase 3. Appended at each iteration's close-out; see `.claude/rules/prose.md`.

## 2026-07-08 — iter-024: explicit-cost backtester engine (Phase 3)

- **`cli/backtest/`** scores a strategy end to end — target positions in, net-return series after explicit per-turnover fees out — reusing the Phase-2 metrics rather than reimplementing them.
- **Timing contract:** `positions[t]` is held during period `t` and earns that period's return, so a caller must set it from information no later than `t−1`; the engine cannot enforce it, the validation harness is what catches a leaky strategy.
- **A degenerate run refuses rather than returning NaN** — an undefined Sharpe or a wiped-out equity path raises `BacktestError`, so no caller ever scores a broken series.
- **Design and plan:** `docs/specs/00016-backtester-engine-design.md`, `docs/plans/00016-backtester-engine.md`.
## 2026-07-08 — iter-025: benchmark strategies B0 + B1 (Phase 3)

- **`cli/benchmark/`** holds the benchmark position generators fed to the backtester, opening with B0 buy-and-hold and B1 vol-target.
- **B1's realized-vol window excludes the period it sizes**, so a position never uses the return it earns and the composed strategy is look-ahead-free end to end.
- **Design and plan:** `docs/specs/00017-benchmark-b0-b1-design.md`, `docs/plans/00017-benchmark-b0-b1.md`.
## 2026-07-08 — iter-026: B0/B1 bar-to-beat report on real BTC (Phase 3)

- **`docs/research/04.phase3-benchmark-b0-b1-report.md`** records the first bar to beat — B0 and B1 on real BTC/EUR daily over the full history, zero-fee.
- **`returns_from_prices`** is where every later benchmark gets its close-to-close return series from the canonical daily dataset.
- **B1 is parameterized at the master plan's §9 target vol, never an arbitrary one** — a wrong B1 bar would mislead the Phase-4 comparison.
- **Verdict: vol-targeting scales the position linearly, so Sharpe is invariant to the target** — the §9 target band is a risk/return ray, not a Sharpe choice.
- **Plan:** `docs/plans/00018-benchmark-bar-to-beat.md`.
## 2026-07-08 — iter-027: regime gate (200-day SMA long/flat) (Phase 3)

- **`cli/benchmark/sma_gate`** adds the §5 prior survivor — a 200-day long/flat regime signal aligned to the return series — and composes multiplicatively with the other generators.
- **The gate decides at the start of a period from prices through that start**, so a gated strategy stays look-ahead-free under the backtester's timing contract.
- **Design and plan:** `docs/specs/00019-regime-gate-design.md`, `docs/plans/00019-regime-gate.md`, which also holds what the gate deliberately does not do.
## 2026-07-08 — iter-028: gated-BTC benchmark panel (Phase 3)

- **The B0/B1 report extends to the four-strategy BTC panel** — the 200-day-gated variants of B0 and B1, composed from the existing generators, no new code.
- **Verdict: the gate cuts buy-and-hold's drawdown while raising Sharpe, and gated-B1 is the panel's best risk-adjusted line** — supporting the plan's §1/§5 thesis that a vol-targeted regime rule, not raw buy-and-hold, is the deployable family.
- **The report says "supports", never "validates"** — one zero-fee run with no significance test cannot carry more.
- **Plan:** `docs/plans/00020-benchmark-gated-panel.md`.
## 2026-07-08 — iter-029: benchmark cost-stress panel (§9.6, Phase 3)

- **The B0/B1 report's `## Cost stress (§9.6)` section** runs the four BTC strategies through the backtester's per-turnover fee at the confirmed Kraken Tier-1 ladder, sourced from `cli.costs.spot_fee_rates`.
- **§9.6 verdict: gated-B1 does not die on the ladder** — its turnover is low enough that Sharpe erodes gently and still clears the deployment gate at 1.5× the base maker fee.
- **Verdict: buy-and-hold overtakes gated-B1 on Sharpe from 1.5× up**, because it pays no rebalancing fee — so the gated family's deployment case rests on its drawdown advantage, not on a fee-robust Sharpe edge.
- **Scope of the ladder: exchange fees only** — spread is not modelled and margin carry is not applicable to long/flat spot.
- **Plan:** `docs/plans/00021-benchmark-cost-stress.md`.
## 2026-07-08 — iter-030: inverse-vol majors basket generator (B2, Phase 3)

- **`inverse_vol_basket` in `cli/benchmark/strategies.py`** is the B2 generator: pre-aligned per-asset price series in, the inverse-vol-weighted basket's daily net return series out.
- **Weights come from a window strictly before the day they apply to**, zero-vol assets are excluded and the rest renormalized, and degenerate input raises `BenchmarkError` — a refusal, never a NaN.
- **Decision: the generator is the fixed-composition basket and the caller supplies aligned series**, keeping data loading and calendar alignment in the later real-data run; the dynamic 2→10-asset full-history variant was parked as `T0007` (resolved at iter-044).
- **Spec and plan:** `docs/specs/00022-inverse-vol-basket-design.md`, `docs/plans/00022-inverse-vol-basket.md`.
## 2026-07-08 — iter-031: B2 inverse-vol basket bar-to-beat (Phase 3)

- **New report `docs/research/04.phase3-benchmark-b2-basket-report.md`** runs the basket on the ten EUR majors over their common window against single-asset BTC, zero-fee.
- **Verdict: the raw inverse-vol basket underperformed single-asset BTC and drew down deeper** — the window opens near the 2021 top and an inverse-vol basket keeps holding the losers at risk-normalized weights, so naive diversification bought nothing.
- **Verdict: vol-targeting, not asset selection, is the edge** — both vol-targeted variants beat either raw strategy on risk-adjusted terms.
- **B2 does not raise the bar** — the deployable target stays the vol-targeted/gated family, and any Phase-4 alpha clears that family, not the raw basket.
- **Window caveat:** the common window is BTC-unfavourable, so whether the underperformance is structural or window-specific is what `T0007`'s full-history dynamic basket would settle. **Plan:** `docs/plans/00023-benchmark-b2-basket-report.md`.
## 2026-07-08 — iter-032: basket gate + short (B3/B4), Phase 3

- **The basket report gains B3 (the basket's own 200-day equity gate) and B4 (short below it)**, completing the B0–B4 family on the multi-asset side; no new code.
- **Verdict: the gate rescues the raw basket from a loss but does not lift it** to the vol-targeted basket's risk-adjusted level.
- **Verdict: on the basket the gate and vol-targeting are substitutes, not complements** — once vol-targeting controls risk the gate only subtracts participation, the opposite of single-asset BTC where their product is the best line.
- **Verdict: the short backfires** — the 200-day gate lags, so B4 shorts after the crash and is whipsawed by the bear-market counter-rallies, even before real borrow cost.
- **No overlay lifts the basket to the single-asset BTC bar; the deployable target remains gated-B1.** **Plan:** `docs/plans/00024-benchmark-basket-gate-short.md`; the basket-turnover cost model this left open went to `T0010` (resolved at iter-055).
## 2026-07-08 — iter-033: benchmark bootstrap CIs (Phase-3 exit bar)

- **Both benchmark reports gain a `## Statistical significance (bootstrap CIs)` section** — stationary block-bootstrap 95% CIs on each strategy's annualized Sharpe via the Phase-2 harness (`cli.validation.bootstrap_ci`); no new code.
- **Verdict: the full-history BTC family's Sharpes are all significantly positive but their CIs overlap heavily** — a single ~12-year path cannot distinguish the strategies from each other.
- **Verdict: over the common window every CI straddles zero**, so the basket underperformance and the B4 result are directional point estimates, not significant ones — a power problem that reinforces the full-history basket (`T0007`).
- **Deployment bar FROZEN = gated-B1** — vol-targeted BTC (10%/yr target, 30-day window) × the 200-day long/flat regime gate — chosen on point estimate, robustly-positive lower bound and drawdown control, never on a significant Sharpe edge over B0/B1, which the CIs show does not exist; the frozen values and their basis are `docs/research/04.phase3-decisions.md` `[iter-033]`.
- **Plan:** `docs/plans/00025-benchmark-bootstrap-cis.md`, delivering the §12 exit-bar CI and frozen-bar requirements.
## 2026-07-08 — iter-034: benchmark regime slices (Phase-3 exit bar)

- **The B0/B1 report gains `## Regime slices (calendar-year)`** — annual net return of B0, B1 and gated-B1 across BTC's history, zero-fee; no new code.
- **Verdict: gated-B1 turns BTC's catastrophic bear years into near-flat ones** by going flat below the 200-day line, and the gate's marginal value over vol-targeting alone is concentrated in exactly those years.
- **Verdict: the cost is the bull-year cap** — gated-B1 gives up the explosive years and so underperforms buy-and-hold heavily in raw cumulative return; it trades return for the elimination of catastrophic years.
- **What is robust in the dossier is the year-by-year loss floor, not a significant Sharpe edge** — that floor is the source of gated-B1's drawdown control and why it is the frozen bar; on a single historical path it is descriptive, not guaranteed.
- **Plan:** `docs/plans/00026-benchmark-regime-slices.md`, completing the §12 exit-bar regime-slice dimension.
## 2026-07-08 — iter-035: Phase 3 close-out (benchmarks & the frozen bar)

- **`docs/research/04.phase3-benchmarks-closeout.md` closes Phase 3** — the §12 exit bar is met, the B0–B4 family is characterized across cost stress, bootstrap CIs and regime slices, and the frozen deployment bar is gated-B1.
- **The one carried-forward §12 handback — the human confirmation of B4 as the *fallback* deployable — is named in that report**; it gates Phase 5's fallback choice, not the Phase-4 kickoff.
- **`docs/research/04.phase3-decisions.md` is the committed home of the phase's decision log**, drained verbatim from the running log and kept off the mdformat allowlist so it stays verbatim.
- **Open topics swept at the phase boundary** — every one still open was human-gated or deferred to a later phase, none Phase-3-relevant.
