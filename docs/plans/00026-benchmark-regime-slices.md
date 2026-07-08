# Benchmark Regime Slices (Phase-3 exit bar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a calendar-year regime-slice section to `docs/benchmark-b0-b1-report.md` — the annual net return of B0 / B1 / gated-B1 for each year of BTC history — delivering the §12 Phase-3 exit-bar "regime slices" dimension and decomposing *where* the frozen bar (gated-B1) earns its edge: it turns catastrophic bear years into near-flat ones, at the cost of capping the explosive bull years.

**Architecture:** No new code — a throwaway scratchpad run bucketing the existing net-return series by the year each return is realized in, and a new section in the committed report. Light doc iteration (no spec).

**Tech Stack:** Python 3.14, stdlib + polars. The report is NOT on the mdformat allowlist — hand-write clean markdown.

## Global Constraints

- **No code change.** Throwaway scratchpad (session scratchpad dir, not committed); committed artifact is the extended `docs/benchmark-b0-b1-report.md`. No CLI/README change.
- **Year attribution:** a return `rets[k]` (from `returns_from_prices(prices)`) is realized at `ts[k+1]`, so it belongs to year `ts[k+1].year`. Annual return = `prod(1 + r for r in that year's net returns) - 1`.
- **Net series (zero fee):** `net[k] = positions[k] * rets[k]`, same strategies as the report's existing panel (B0 = `buy_and_hold`, B1 = `vol_target(rets, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`, gated-B1 = `sma_gate(prices, window=200) × B1`).
- **Honest framing:** gated-B1's bull-year cap is a genuine *cost* (it dramatically underperforms buy-and-hold in raw cumulative return); the section must show both sides. The "worst year −5.5%" is descriptive of 2013–2026, not a guarantee.

---

### Task 1: Run + add the regime-slice section

**Files:** Modify `docs/benchmark-b0-b1-report.md`.

- [ ] **Step 1: Write + run** a scratchpad script (session scratchpad dir, NOT committed) that loads `data/ohlc-full/BTC/EUR/1440.parquet`, builds `rets = returns_from_prices(prices)`, the year label per return (`ts[k+1].year`), the three net series (B0/B1/gated-B1), and for each year computes each strategy's compounded annual net return.

  **Expected values (verify — annual return %, if any full-year cell diverges >0.3pp, STOP and report):**

  | Year | B0 | B1 | gated-B1 |
  |---|---:|---:|---:|
  | 2013 (partial, 108 d) | 455.7 | 20.8 | 0.0 |
  | 2014 | −50.5 | −10.7 | −5.5 |
  | 2015 | 48.5 | 20.2 | 19.1 |
  | 2016 | 131.1 | 39.9 | 39.9 |
  | 2017 | 1211.3 | 46.9 | 46.9 |
  | 2018 | −73.0 | −17.9 | −5.2 |
  | 2019 | 97.7 | 25.2 | 8.9 |
  | 2020 | 269.6 | 33.6 | 27.5 |
  | 2021 | 71.9 | 9.6 | −0.6 |
  | 2022 | −62.1 | −17.1 | −0.5 |
  | 2023 | 149.0 | 27.0 | 11.4 |
  | 2024 | 134.6 | 23.8 | 17.2 |
  | 2025 | −17.3 | −4.1 | −4.6 |
  | 2026 (partial, 90 d) | −20.8 | −5.2 | 0.0 |

- [ ] **Step 2: Add a `## Regime slices (calendar-year)` section** to `docs/benchmark-b0-b1-report.md`, placed **after `## Statistical significance (bootstrap CIs)`** and **before `## Distrust-the-instrument note`**. It must contain:
  - A one-line note: each return is bucketed by the year it is realized in; annual figures are compounded net returns, zero fee; 2013 and 2026 are partial years (2013 = the gate's 200-day warm-up, so gated-B1 is flat; 2026 = 90 days).
  - The full table above (real numbers from your run).
  - The interpretation:
    - **gated-B1 turns catastrophic bear years into near-flat ones.** In the three big BTC bear years — 2014 (**−50.5%**), 2018 (**−73.0%**), 2022 (**−62.1%**) — gated-B1 lost only **−5.5%, −5.2%, −0.5%** by going flat below the 200-day line. Its **worst year in the whole 2013–2026 sample is −5.5%**; B0 has four double-digit-loss years.
    - **The gate's marginal value over vol-targeting is concentrated in the bear years.** Vol-targeting alone (B1) already softens them (2018 −17.9%, 2022 −17.1%), but the gate cuts them much further (2018 −5.2%, 2022 −0.5%). In calm uptrends (2016, 2017) the gate is long all year and gated-B1 ≡ B1.
    - **The cost is the bull-year cap.** gated-B1 gives up the explosive years — 2017 (**+46.9%** vs B0's **+1211%**), 2020 (+27.5% vs +269.6%) — so over the full history it dramatically underperforms buy-and-hold in *raw cumulative* return (the report's headline: 2.75× vs 607×). It trades return for the elimination of catastrophic years.
    - **This decomposes the whole dossier.** The bootstrap CIs showed gated-B1's Sharpe edge over B0/B1 is *not* statistically significant; the year-by-year view shows what *is* robust and economically real — not a higher average return, but **never losing more than ~6% in a year**. That bear-year elimination is the source of the low max drawdown (12.3% vs 82.5%) and is why gated-B1 is the frozen deployment bar.
  - A short caveat: this is a single historical path; "worst year −5.5%" describes 2013–2026, it is not a guaranteed floor.

- [ ] **Step 3: Full gate** — `git add docs/benchmark-b0-b1-report.md` (report only; NOT the scratchpad); `uv run pre-commit run -a` clean; `uv run pytest -q` green (no code change ⇒ unchanged **469 passed**).

- [ ] **Step 4: Commit** — `docs(benchmark): add calendar-year regime slices (Phase-3 exit bar)`.

---

### Task 2: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1:** Append `## 2026-07-08 — iter-034: benchmark regime slices (Phase-3 exit bar)` with bullets covering: added `## Regime slices (calendar-year)` to `docs/benchmark-b0-b1-report.md` — annual net return of B0/B1/gated-B1 per year, bucketing each return by the year it is realized; **gated-B1 turns the three catastrophic bear years (B0 2014 −50%, 2018 −73%, 2022 −62%) into near-flat (−5.5%, −5.2%, −0.5%)** by going flat, worst year in-sample −5.5% (B0 has four double-digit-loss years); **the gate's marginal value over vol-targeting is concentrated in the bear years** (2018 B1 −17.9% → gated-B1 −5.2%); **the cost is the bull-year cap** (2017 +46.9% vs B0's +1211%). Decomposes the whole dossier: the Sharpe edge is within noise (per the CIs), but bear-year *elimination* is the robust, economically-real differentiator and the source of the 12.3% max drawdown. Completes the §12 exit-bar "regime slices" dimension. No new code. Plan `00026`. Eleventh Phase-3 component. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-034 closeout — benchmark regime slices`.
