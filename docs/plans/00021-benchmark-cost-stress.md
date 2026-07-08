# Benchmark Cost-Stress Panel (§9.6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `docs/benchmark-b0-b1-report.md` with the **§9.6 cost-stress panel** — re-run the four BTC strategies (B0, gated-B0, B1, gated-B1) through the backtester at the confirmed Tier-1 Kraken fees (0 / 0.40% maker base / 0.60% = 1.5× / 0.80% = 2× = taker) — answering the master plan's §9.6 deployment gate ("a strategy that dies at 1.5× costs is not deployable"), and recording the honest, non-trivial finding the stress surfaces.

**Architecture:** No new code — a reproducible real-data run (scratchpad script) composing the existing `sma_gate`/`vol_target`/`buy_and_hold`/`returns_from_prices`/`run_backtest` with the `fee_rate` parameter, and an update to the committed report. The fee tiers come from `cli.costs.spot_fee_rates(0.0)` (Tier-1 maker 0.40% / taker 0.80%). Light doc iteration (no spec).

**Tech Stack:** Python 3.14, stdlib + polars (`cli.ohlc.dataset.read_parquet`). Ruff/markdown hygiene via pre-commit.

## Global Constraints

- **No code change** — the run uses existing components. The run script is a THROWAWAY scratchpad (not committed); the committed artifact is the updated report. `docs/benchmark-b0-b1-report.md` is NOT on the mdformat allowlist — write clean markdown by hand. No CLI/README change.
- **The fitted base cost is the Tier-1 maker fee, 0.40%** (`spot_fee_rates(0.0)["maker"]` = 0.0040). §9.6 stress multiples are **1.5× → 0.60%** and **2× → 0.80%** (which coincides with the Tier-1 taker fee 0.80%). Present zero-fee as the idealized reference column.
- **Report the honest finding, not a headline.** The stress surfaces a Sharpe crossover (below) — the report must state it, per the distrust-the-instrument discipline. Do NOT claim gated-B1 is unconditionally best after costs.

---

### Task 1: Run + add the cost-stress section to the report

**Files:** Modify `docs/benchmark-b0-b1-report.md`.

- [ ] **Step 1: Write + run** a scratchpad script (e.g. under the session scratchpad dir, NOT committed) that loads `data/ohlc-full/BTC/EUR/1440.parquet`, builds the four strategies exactly as in the existing report —
  - **B0** = `buy_and_hold(len(rets))`
  - **gated-B0** = `sma_gate(prices, window=200)`
  - **B1** = `vol_target(rets, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`
  - **gated-B1** = elementwise `sma_gate(prices, window=200) × B1`

  — then for each strategy runs `run_backtest(rets, pos, fee_rate=fr, periods_per_year=365)` at **fr ∈ {0.0, 0.0040, 0.0060, 0.0080}** (get 0.0040 from `spot_fee_rates(0.0)["maker"]`; 0.0060 = 1.5×; 0.0080 = 2× = `spot_fee_rates(0.0)["taker"]`). Record Sharpe, annualized return, total return, and max drawdown at each fee level.

  **Expected values (verify — if any diverges materially, STOP and report):**

  Sharpe by fee level:

  | Strategy | @0 | @0.40% (maker, base) | @0.60% (1.5×) | @0.80% (2×=taker) |
  |---|---:|---:|---:|---:|
  | B0 — buy-and-hold | 1.075 | 1.075 | 1.074 | 1.074 |
  | gated-B0 — 200d gate | 1.102 | 1.040 | 1.009 | 0.978 |
  | B1 — vol-target | 1.111 | 1.029 | 0.988 | 0.948 |
  | gated-B1 — gate × vol-target | 1.247 | 1.117 | 1.052 | 0.986 |

  gated-B1 supporting metrics (annualized / maxDD) across the same fee levels: annualized **11.12% → 9.85% → 9.22% → 8.59%**; maxDD **12.3% → 15.2% → 16.6% → 18.0%**. B0 is fee-immune (annualized ~66.6% at all levels, maxDD 82.5% flat) because it barely trades.

- [ ] **Step 2: Add a `## Cost stress (§9.6)` section** to `docs/benchmark-b0-b1-report.md`, placed **after `## Interpretation`** and **before `## Distrust-the-instrument note`**. It must contain:
  - A one-line framing: §9.6 requires every headline result re-run at 1.5× and 2× the fitted cost model; the fitted base is the **Tier-1 Kraken maker fee 0.40%** (`cli.costs.spot_fee_rates`), so the stress ladder is 0.40% → 0.60% (1.5×) → 0.80% (2× = Tier-1 taker). The rule: a strategy that dies at 1.5× is not deployable.
  - The **Sharpe-by-fee-level table** above (real numbers from your run).
  - The interpretation, stated honestly:
    - **B0 is fee-immune** (turnover ≈ 0.0002/day — it only ever buys once), so its Sharpe ~1.075 is unchanged across the ladder.
    - The **gated / vol-targeted strategies rebalance** (gated-B1 turnover ≈ 0.008/day — the vol-target position resizes daily and the gate flips), so their net Sharpe erodes with the fee: gated-B1 **1.247 → 1.117 → 1.052 → 0.986**.
    - **§9.6 verdict: gated-B1 does not die at 1.5×** — Sharpe 1.052 (still > 1.0), so it clears the deployment gate; the erosion is gentle because turnover is low.
    - **The honest crossover (distrust-the-instrument).** At the realistic base maker fee (0.40%), gated-B1 (1.117) is still the panel's best Sharpe, above B0 (1.075). But because B0 is fee-immune while gated-B1 pays to rebalance, **B0 overtakes gated-B1 on Sharpe at 1.5×+ stress** (1.074 vs 1.052 at 0.60%; 1.074 vs 0.986 at 0.80%). So gated-B1's *Sharpe edge over buy-and-hold* is fee-sensitive and does not survive the stress ladder — its **drawdown** advantage does: gated-B1's maxDD stays **15–18%** across the ladder versus B0's **82.5%**, ~4–5× smaller. The deployment case for the gated/vol-targeted family rests on **risk (drawdown) control**, not a fee-proof return edge.
    - The subtle correct effect worth naming: **fees slightly raise the gated strategies' max drawdown** (12.3% → 18.0% for gated-B1) — the fee drag deepens/extends drawdown troughs; it is not a bug.

- [ ] **Step 3: Update the report's intro + caveats** to reflect that cost stress is now applied (not "deferred"):
  - In the intro paragraph, soften the "cost stress is applied later, at evaluation time" clause to note the cost-stress panel is now **in this report** (the `## Cost stress (§9.6)` section), while the headline `## Results` table stays zero-fee as the idealized reference.
  - In `## Caveats`, change the "Zero transaction cost — a benchmark idealization…" bullet: keep the zero-fee headline table as the idealization, but note the **§9.6 cost stress is now applied** in its own section (remove/adjust the "the fee model folds in with the full-panel run" clause, since it now folds in here). Leave the "full B0–B4 panel + DSR/PBO/SPA significance" deferral bullet as-is.

- [ ] **Step 4: Full gate** — `git add -A` (report only; NOT the scratchpad), `uv run pre-commit run -a` clean; `uv run pytest -q` green (no code change ⇒ unchanged count **459**).

- [ ] **Step 5: Commit** — `docs(benchmark): add the §9.6 cost-stress panel (Tier-1 fee ladder)`.

---

### Task 2: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1:** Append `## 2026-07-08 — iter-029: benchmark cost-stress panel (§9.6, Phase 3)` with bullets covering: added the `## Cost stress (§9.6)` section re-running the four BTC strategies at the Tier-1 fee ladder (0 / 0.40% maker / 0.60% = 1.5× / 0.80% = 2× = taker) via the backtester's `fee_rate`; the **§9.6 verdict — gated-B1 does not die at 1.5×** (Sharpe 1.247 → 1.117 → 1.052 → 0.986; clears the gate); the **honest crossover** the stress surfaces (B0 is fee-immune and overtakes gated-B1 on Sharpe at 1.5×+, so the gated family's deployment case rests on its robust **drawdown** advantage — maxDD 15–18% vs B0's 82.5% — not a fee-proof Sharpe edge); the subtle fee-raises-drawdown effect; no new code (composes existing components + `cli.costs` fees). Plan `00021`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-029 closeout — §9.6 cost-stress panel`.
