# Benchmark Basket Gate + Short (B3/B4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `docs/benchmark-b2-basket-report.md` with **B3 (200-day gate on the basket) and B4 (short)** — completing the B0–B4 benchmark family on the multi-asset side — recording the honest findings: the gate rescues the raw basket from a loss but doesn't lift it, the gate *hurts* the already-vol-targeted basket, and **adding the short (B4) is disastrous** (negative Sharpe — the lagging gate shorts into violent bear-market rallies).

**Architecture:** No new code — a throwaway scratchpad run composing the already-reviewed `inverse_vol_basket`, `sma_gate`, and `vol_target` on the same common window, and a new section appended to the existing report. Light doc iteration (no spec).

**Tech Stack:** Python 3.14, stdlib + polars. The report is NOT on the mdformat allowlist — hand-write clean markdown.

## Global Constraints

- **No code change.** Throwaway scratchpad script (session scratchpad dir, not committed); the committed artifact is the extended `docs/benchmark-b2-basket-report.md`. No CLI/README change.
- **Same common window** as the existing report: 10 EUR majors intersected on `ts` → 2021-12-21 → 2026-03-31 (1562 closes → 1561 returns), lookback=30, zero-fee.
- **Gate design (document it):** the 200-day gate is applied to the **basket's own equity index** (cumulative product of the B2 return series, seeded at 1.0) — a self-referential regime gate: long/flat/short by the basket's *own* trend, not a market proxy. Build the equity index as `eq=[1.0]; for r in b2: eq.append(eq[-1]*(1+r))` (length `len(b2)+1`), then `gate = sma_gate(eq, window=200)` (length `len(b2)`, aligned with the basket returns).
- **B4 long/short construction:** `sma_gate` returns `0.0` for BOTH warm-up (`k < 199`) and below-SMA. B4 shorts only after warm-up: `longshort[k] = 0.0 if k < 199 else (1.0 if gate[k] == 1.0 else -1.0)`.
- **Report the honest finding, not a headline.** Every result here is weak-to-terrible; do NOT spin any as a win. B4's negative Sharpe is the point.

---

### Task 1: Run + extend the report

**Files:** Modify `docs/benchmark-b2-basket-report.md`.

- [ ] **Step 1: Write + run** a scratchpad script (session scratchpad dir, NOT committed) reproducing the existing report's basket setup (load 10 majors, intersect `ts`, `b2 = inverse_vol_basket(prices_by_asset, lookback=30)`), then compute:
  - `eq` = basket equity index (as above); `gate = sma_gate(eq, window=200)` — this is **B3** (gated-B2, long/flat).
  - `b2vt = vol_target(b2, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`; `gated_b2vt = [g*v for g, v in zip(gate, b2vt)]`.
  - `longshort` = the B4 position vector (as above).
  - Run each through `run_backtest(b2, positions, fee_rate=0.0, periods_per_year=365)`; also compute the gate's long fraction `sum(gate)/len(gate)` and B4's short fraction.

  **Expected values (verify — if any diverges materially, STOP and report):**

  | Strategy | Total | Annualized | Sharpe | Max DD |
  |---|---:|---:|---:|---:|
  | B2 — raw basket (reference) | 0.68× | −8.57% | 0.194 | 69.4% |
  | B3 — gated-B2 (200d, long/flat) | 1.06× | 1.36% | 0.237 | 48.4% |
  | gated-B2 + vol-target | 1.08× | 1.73% | 0.270 | 14.8% |
  | B4 — basket long/short | 0.34× | −22.43% | **−0.136** | 83.0% |

  Gate long fraction ≈ **41.8%**; B4 short fraction ≈ **45.5%**.

- [ ] **Step 2: Add a `## B3 and B4: gating and shorting the basket` section** to `docs/benchmark-b2-basket-report.md`, placed **after `## Interpretation (honest)`** and **before `## Distrust-the-instrument note`**. It must contain:
  - A one-line design note: the gate is the 200-day long/flat rule applied to the **basket's own equity index** (self-referential regime); B4 replaces "flat" with "short" below the SMA. Both over the same common window, zero-fee.
  - The four-row table above (real numbers from your run).
  - The honest interpretation:
    - **B3 (gate) rescues the raw basket from a loss but doesn't lift it.** Long only ~41.8% of the time, the gate turns the −8.6%/yr raw basket into a slight +1.4%/yr gain (0.68× → 1.06×) and roughly halves the drawdown (69.4% → 48.4%) by sitting out much of the alt bear — but Sharpe (0.237) stays far below the vol-targeted basket's 0.453.
    - **The gate HURTS the vol-targeted basket.** gated-B2 + vol-target (Sharpe 0.270) is *worse* than plain B2 + vol-target (0.453): once vol-targeting controls the risk, the gate only subtracts participation. On the basket the gate and vol-target are **substitutes, not complements** — the *opposite* of single-asset BTC, where `gate × vol-target` (gated-B1) was the **best** result in the whole family (Sharpe 1.247, `docs/benchmark-b0-b1-report.md`).
    - **B4 (short) is disastrous.** Adding the short takes Sharpe *negative* (**−0.136**) and the drawdown to **83.0%** — worse than every other line. The 200-day gate is a *lagging* signal: it flips to short only *after* price is already below the trailing SMA, so B4 shorts into the violent 2022–2023 bear-market counter-rallies and gets whipsawed. Shorting a lagging-trend basket over this window destroyed capital.
    - **Family conclusion:** no overlay lifts the basket to the single-asset BTC bar. Vol-targeting is the only overlay that helps; gating rescues-but-doesn't-lift and is redundant with vol-targeting; shorting backfires. The deployable target remains **gated-B1** (vol-targeted BTC with the regime gate) from the single-asset panel.
  - A short caveat: B4 is an **idealized long/short** (zero-cost, always-shortable). Real short-borrow costs and per-alt shortability constraints on Kraken spot-margin would make B4 *even worse* — and it is already the worst line in the panel.

- [ ] **Step 3: Update the report's final `## Caveats`** — change the last bullet (currently "**B3** (gate × basket), **B4** (short), and the DSR/PBO/SPA … are deferred") to drop B3/B4 (now delivered in this section) and keep only the DSR/PBO/SPA significance comparison + the basket-turnover cost model as deferred.

- [ ] **Step 4: Full gate** — `git add docs/benchmark-b2-basket-report.md` (report only; NOT the scratchpad); `uv run pre-commit run -a` clean; `uv run pytest -q` green (no code change ⇒ unchanged **469 passed**).

- [ ] **Step 5: Commit** — `docs(benchmark): complete the basket family — B3 gate + B4 short`.

---

### Task 2: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1:** Append `## 2026-07-08 — iter-032: basket gate + short (B3/B4), Phase 3` with bullets covering: extended `docs/benchmark-b2-basket-report.md` with B3 (200d gate on the basket's own equity index) + B4 (short) over the common window, completing the B0–B4 family on the multi-asset side; **B3 rescues the raw basket from a loss** (0.68× → 1.06×, maxDD 69.4% → 48.4%, long ~41.8% of the time) **but stays weak** (Sharpe 0.237); **the gate HURTS the vol-targeted basket** (0.453 → 0.270 — substitute, not complement, the opposite of BTC's gated-B1); **B4 (short) is disastrous** (Sharpe **−0.136**, maxDD 83.0%) — the lagging gate shorts into the 2022–23 bear rallies and gets whipsawed; family conclusion — no overlay lifts the basket to the BTC-based bar, deployable target stays gated-B1. No new code (composes `inverse_vol_basket`/`sma_gate`/`vol_target`). Plan `00024`. Ninth Phase-3 component; the B0–B4 benchmark family (single-asset + basket) is now complete pending the DSR/PBO/SPA significance layer. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-032 closeout — basket gate + short (B3/B4)`.
