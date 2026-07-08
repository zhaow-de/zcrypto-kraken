# Benchmark Bootstrap CIs (Phase-3 exit bar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stationary-block-bootstrap 95% confidence intervals for the annualized Sharpe of every benchmark strategy to both benchmark reports — delivering the §12 Phase-3 exit-bar requirement ("B3/B4 numbers with bootstrap CIs") and recording the honest meta-finding that the benchmark comparisons are dominated by estimation uncertainty (full-history BTC Sharpes are all significantly positive but mutually indistinguishable; the common-window family is entirely within noise).

**Architecture:** No new code — a throwaway scratchpad run applying the already-built `cli.validation.bootstrap_ci` (stationary block bootstrap, Politis-Romano) to each strategy's net-return series, and a new section added to each of the two committed reports. Light doc iteration (no spec).

**Tech Stack:** Python 3.14, stdlib + polars. Reports are NOT on the mdformat allowlist — hand-write clean markdown.

## Global Constraints

- **No code change.** Throwaway scratchpad (session scratchpad dir, not committed); committed artifacts are the two extended reports (`docs/benchmark-b0-b1-report.md`, `docs/benchmark-b2-basket-report.md`). No CLI/README change.
- **Reproducibility (pin everything):** `bootstrap_ci(net_series, statistic=annualized-Sharpe, mean_block=ℓ, n_resamples=2000, alpha=0.05, seed=42)`, where `statistic = lambda r: sharpe(r, periods_per_year=365)` and `net_series[t] = positions[t] * asset_returns[t]` (zero fee). Block length **ℓ ≈ n^(1/3)** (Politis-White rule of thumb): **ℓ=16** for the 4580-day BTC full history, **ℓ=12** for the 1561-day common window.
- **Honest framing (the point):** the CIs show the Sharpe *differences* are not significant. Do NOT present the CIs as confirming gated-B1's superiority on Sharpe — they don't. gated-B1's case rests on point estimate + highest/robustly-positive lower bound + drawdown control, explicitly acknowledging the overlap.

---

### Task 1: Run + add CI sections to both reports

**Files:** Modify `docs/benchmark-b0-b1-report.md` and `docs/benchmark-b2-basket-report.md`.

- [ ] **Step 1: Write + run** a scratchpad script (session scratchpad dir, NOT committed) that:
  - **Full-history BTC family** (from `data/ohlc-full/BTC/EUR/1440.parquet`, full history): compute net-return series for B0 = `buy_and_hold`, gated-B0 = `sma_gate(prices, window=200)`, B1 = `vol_target(rets, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`, gated-B1 = `sma_gate × B1`; bootstrap CI each with **ℓ=16**.
  - **Common-window family** (10 majors intersected on `ts`, per the B2 report): B0/B1 on BTC over the window, B2 = `inverse_vol_basket(pba, lookback=30)`, B3 = gate on the basket equity index, B2+vt = `vol_target(b2, ...)`, B4 = long/short (`0.0 if k<199 else (1.0 if gate[k]==1.0 else -1.0)`); bootstrap CI each with **ℓ=12**.
  - Uses `from cli.validation import bootstrap_ci, sharpe`; `stat = lambda r: sharpe(r, periods_per_year=365)`; `net = lambda rets, pos: [p*r for p, r in zip(pos, rets)]`.

  **Expected values (verify — the CI bounds are seed/block-dependent; match the POINT to ≤0.005 and each bound to ≤0.03; if further off, STOP and report):**

  Full-history BTC (ℓ=16, 2000 resamples, seed=42), 95% CI on annualized Sharpe:

  | Strategy | Point | 95% CI |
  |---|---:|---:|
  | B0 — buy-and-hold | 1.075 | [0.47, 1.70] |
  | gated-B0 | 1.102 | [0.48, 1.70] |
  | B1 — vol-target | 1.111 | [0.43, 1.79] |
  | gated-B1 (the bar) | 1.247 | [0.61, 1.88] |

  Common window (ℓ=12, 2000 resamples, seed=42), 95% CI on annualized Sharpe:

  | Strategy | Point | 95% CI |
  |---|---:|---:|
  | B0 — BTC buy-and-hold | 0.397 | [−0.55, 1.38] |
  | B1 — BTC vol-target | 0.456 | [−0.59, 1.53] |
  | B2 — inverse-vol basket | 0.194 | [−0.74, 1.18] |
  | B3 — gated-B2 | 0.237 | [−0.68, 1.26] |
  | B2 + vol-target | 0.453 | [−0.57, 1.49] |
  | B4 — long/short | −0.136 | [−1.05, 0.80] |

  (Robustness — the qualitative conclusions hold across ℓ∈{8,16,24} and seed∈{1,42,99}: gated-B1's full-history lower bound stays in ~[0.53, 0.64] > 0; every common-window CI keeps straddling zero.)

- [ ] **Step 2: Add a `## Statistical significance (bootstrap CIs)` section to `docs/benchmark-b0-b1-report.md`** (placed after `## Interpretation` / the `### The 200-day regime gate` subsection, before `## Distrust-the-instrument note`):
  - Method one-liner: 95% percentile CI on the annualized Sharpe under the stationary block bootstrap (`cli.validation.bootstrap_ci`, Politis-Romano), ℓ=16≈n^(1/3), 2000 resamples, seed=42.
  - The full-history 4-row CI table above.
  - Finding: **all four Sharpes are significantly positive** (lower bounds ~0.43–0.61 > 0) **but their CIs overlap heavily — the differences are not statistically distinguishable** from a single ~12-year path. gated-B1 has both the highest point (1.247) and the highest, robustly-positive lower bound (~0.61, stable across block lengths/seeds). So the bar is chosen on point estimate + best lower bound + drawdown control (12.3% vs 82.5%), **not** on a significant Sharpe edge over B0/B1 — which does not exist.

- [ ] **Step 3: Add a `## Statistical significance (bootstrap CIs)` section to `docs/benchmark-b2-basket-report.md`** (placed after `## B3 and B4: gating and shorting the basket`, before `## Distrust-the-instrument note`):
  - Same method one-liner but ℓ=12 (the 1561-day common window).
  - The common-window 6-row CI table above.
  - Finding: **every CI straddles zero** — over this short ~4.3-year window, not one strategy has a significantly-positive Sharpe, and B4's −0.136 is not significantly negative ([−1.05, 0.80]). The basket's underperformance and B4's disaster are directional point estimates, not significant results. This is a power problem: 1561 daily returns through a single bull→bear→recovery cycle cannot distinguish these Sharpes — reinforcing the case for the full-history basket (open topic **T0007**), which would have the horizon the common window lacks.

- [ ] **Step 4: Full gate** — `git add` both reports (NOT the scratchpad); `uv run pre-commit run -a` clean; `uv run pytest -q` green (no code change ⇒ unchanged **469 passed**).

- [ ] **Step 5: Commit** — `docs(benchmark): add bootstrap-CI significance sections (Phase-3 exit bar)`.

---

### Task 2: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1:** Append `## 2026-07-08 — iter-033: benchmark bootstrap CIs (Phase-3 exit bar)` with bullets covering: added `## Statistical significance (bootstrap CIs)` sections to both benchmark reports via `cli.validation.bootstrap_ci` (stationary block bootstrap, ℓ≈n^(1/3), 2000 resamples, seed=42); **full-history BTC family** — all four Sharpes significantly positive (lower bounds ~0.43–0.61) but mutually indistinguishable (CIs overlap); gated-B1 has the highest point (1.247) and highest lower bound (~0.61, robust to block/seed); **common-window family** — every CI straddles zero (no significant Sharpe over 4.3 yr; a power problem reinforcing T0007); the honest meta-finding that the benchmark comparisons are dominated by estimation uncertainty and the bar (gated-B1) is chosen on point + lower-bound + drawdown, not a significant Sharpe edge. **Deployment bar frozen** (`.tmp/decisions.md` [iter-033]) = gated-B1. Delivers the §12 Phase-3 exit-bar "bootstrap CIs" + "bar frozen" requirements. No new code. Plan `00025`. Tenth Phase-3 component. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-033 closeout — benchmark bootstrap CIs`.
