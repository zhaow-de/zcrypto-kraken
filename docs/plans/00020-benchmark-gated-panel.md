# Benchmark Gated-BTC Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `docs/benchmark-b0-b1-report.md` into the **BTC benchmark panel** — add the 200-day-gated variants (gated-B0 = the §5 prior survivor; gated-B1 = gate × vol-target) run on real BTC through the backtester — recording the master plan's §1/§5 thesis (a disciplined vol-targeted trend/regime rule is the realistic best case) validated on real data.

**Architecture:** No new code — a reproducible real-data run (scratchpad script) composing the existing `sma_gate`/`vol_target`/`buy_and_hold`/`returns_from_prices`/`run_backtest`, and an update to the committed report. Light doc iteration (no spec).

**Tech Stack:** Python 3.14, stdlib + polars (`cli.ohlc.dataset.read_parquet`). Ruff/markdown hygiene via pre-commit.

## Global Constraints

- No code change — the run uses existing components. The run script is a THROWAWAY scratchpad (not committed); the committed artifact is the updated report. `docs/benchmark-b0-b1-report.md` is NOT on the mdformat allowlist — write clean markdown. No CLI/README change.

---

### Task 1: Run + update the report

**Files:** Modify `docs/benchmark-b0-b1-report.md`.

- [ ] **Step 1: Write + run** a scratchpad script that loads `data/ohlc-full/BTC/EUR/1440.parquet`, and via `returns_from_prices` + `run_backtest(..., fee_rate=0.0, periods_per_year=365)` computes the four BTC strategies:
  - **B0** = `buy_and_hold(len(rets))`
  - **gated-B0** = `sma_gate(prices, window=200)` (the 200-day long/flat gate = the prior survivor)
  - **B1** = `vol_target(rets, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`
  - **gated-B1** = elementwise `sma_gate(prices, window=200) × B1`
  - Also report the gate's long fraction (`sum(gate)/len(gate)`).

  **Expected values (verify — if they diverge materially, STOP and report):**

  | Strategy | Total | Sharpe | maxDD | Annualized |
  |---|---:|---:|---:|---:|
  | B0 buy-and-hold | 606.9× | 1.075 | 82.5% | 66.7% |
  | gated-B0 (200d) | 188.9× | 1.102 | 62.8% | 51.9% |
  | B1 vol-target (10%/yr) | 3.76× | 1.111 | 22.0% | 13.2% |
  | gated-B1 (gate × vol-target) | 2.77× | 1.247 | 12.3% | 11.1% |

  Gate long fraction ≈ 56.0%.

- [ ] **Step 2: Update `docs/benchmark-b0-b1-report.md`** — retitle to reflect the BTC panel, and:
  - Update the intro to note it now covers the four single-asset BTC strategies (B0/B1 and their 200-day-gated variants), still zero-fee.
  - Replace the results table with the four-row table above (real numbers from your run).
  - Add an interpretation of the gate: the 200-day long/flat gate (the §5 prior survivor) cuts B0's drawdown 82.5% → 62.8% while *raising* Sharpe (1.075 → 1.102), and combined with vol-targeting gives the **best risk-adjusted result** — gated-B1: Sharpe **1.247**, maxDD **12.3%** — long only ~56% of the time. This validates the master plan's §1/§5 thesis (disciplined vol-targeted trend/regime rule = the realistic best case, the deployable target family).
  - Keep the distrust-the-instrument note and the caveats (single-asset; zero-fee — and note gated/vol-targeted strategies rebalance, so their *net* return is more fee-sensitive; the full B0–B4 panel with the basket + short + the DSR/PBO/SPA significance comparison is deferred).

- [ ] **Step 3: Full gate** — `git add -A` (report only; NOT the scratchpad), `uv run pre-commit run -a` clean; `uv run pytest -q` green (no code change ⇒ unchanged count 459).

- [ ] **Step 4: Commit** — `docs(benchmark): extend to the gated BTC panel (200-day regime gate)`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-028: gated-BTC benchmark panel (Phase 3)`: extended `docs/benchmark-b0-b1-report.md` to the four BTC strategies — the 200-day gate cuts B0's maxDD 82.5% → 62.8% while raising Sharpe (1.075 → 1.102); **gated-B1 (gate × vol-target) is the best risk-adjusted: Sharpe 1.247 / maxDD 12.3%** (vs buy-and-hold's 82.5%), long ~56% of the time. Validates the §1/§5 thesis (disciplined vol-targeted trend/regime rule = the realistic best case) on real data. No new code (composes `sma_gate`/`vol_target`/`run_backtest`). Plan `00020`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-028 closeout — gated BTC panel`.
