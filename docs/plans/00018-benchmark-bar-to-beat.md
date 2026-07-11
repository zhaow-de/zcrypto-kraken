# Benchmark Bar-to-Beat (B0/B1 on real BTC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `returns_from_prices` to `cli/benchmark/` and generate a committed **bar-to-beat report** — B0 buy-and-hold + B1 vol-target run on real BTC/EUR daily through the backtester — recording the first deployment floor Phase-4 alpha must beat, and validating the full stack (dataset → returns → strategy → backtester → metrics) on real data.

**Architecture:** Small reusable helper `returns_from_prices` in `cli/benchmark/strategies.py`; a reproducible run script (scratchpad) that loads `data/ohlc-full/BTC/EUR/1440.parquet`, runs B0/B1, and writes `docs/research/04.phase3-benchmark-b0-b1-report.md`. Light report iteration (design carried by this plan; no separate spec). TDD on the helper.

**Tech Stack:** Python 3.14, stdlib + polars (`cli.ohlc.dataset.read_parquet`), pytest. Ruff line-length 132, double quotes.

## Global Constraints

- The helper is stdlib-only (`math`); the run uses the existing `cli.ohlc.dataset.read_parquet` + `cli.benchmark` + `cli.backtest`. Guard raises `BenchmarkError`. The run is a scratchpad script (like the Phase-1 QA reports); the committed artifact is the **report**. No CLI/README change.

---

### Task 1: `returns_from_prices` helper + unit tests

**Files:** Modify `cli/benchmark/strategies.py`, `cli/benchmark/__init__.py`, `tests/test_benchmark_strategies.py`.

- [ ] **Step 1: Append failing tests** to `tests/test_benchmark_strategies.py`:

```python
def test_returns_from_prices():
    assert returns_from_prices([100.0, 110.0, 99.0]) == pytest.approx([0.10, -0.10])


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_returns_from_prices_guards(prices):
    with pytest.raises(BenchmarkError):
        returns_from_prices(prices)
```

(Add `returns_from_prices` to the existing `from cli.benchmark import ...` line.)

- [ ] **Step 2: Run, verify fail** → ImportError.

- [ ] **Step 3: Append to `cli/benchmark/strategies.py`:**
```python
def returns_from_prices(prices: list[float]) -> list[float]:
    """Close-to-close simple returns: r[t] = prices[t] / prices[t-1] - 1. Prices must be finite and positive."""
    if not isinstance(prices, list) or len(prices) < 2:
        raise BenchmarkError(f"prices must be a list of >= 2 values, got {prices!r}")
    for p in prices:
        if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
            raise BenchmarkError(f"prices must be finite positive numbers, got {p!r}")
    return [prices[t] / prices[t - 1] - 1 for t in range(1, len(prices))]
```

- [ ] **Step 4: Export** `returns_from_prices` in `cli/benchmark/__init__.py` (`__all__` alphabetized).
- [ ] **Step 5: Run unit tests, verify pass.** Then full gate: `uv run pre-commit run -a`, `uv run pytest -q` (was 441; +2 tests).

---

### Task 2: Generate the bar-to-beat report

**Files:** Create `docs/research/04.phase3-benchmark-b0-b1-report.md` (the committed artifact). Use a throwaway scratchpad script to produce it.

- [ ] **Step 1: Write + run** a scratchpad script that:
  - `read_parquet("data/ohlc-full/BTC/EUR/1440.parquet")`; `closes = f["close"].to_list()`; `rets = returns_from_prices(closes)`.
  - B0: `run_backtest(rets, buy_and_hold(len(rets)), fee_rate=0.0, periods_per_year=365)`.
  - B1: per-period target `tv = 0.10 / (365 ** 0.5)` (the master plan's specified B1 target — vol-targeted BTC at **10–12%/yr**, §9/§10; 10% is the primary); `pos = vol_target(rets, target_vol=tv, lookback=30, max_leverage=1.0)`; `run_backtest(rets, pos, fee_rate=0.0, periods_per_year=365)`.
  - Write `docs/research/04.phase3-benchmark-b0-b1-report.md` with the numbers.

  **Expected values (verify your run matches — if it diverges materially, STOP and report):** B0 total_return ≈ 606.9, sharpe ≈ 1.075, maxDD ≈ 0.825, annret ≈ 0.667. B1 (10%/yr) total_return ≈ 3.76, sharpe ≈ 1.111, maxDD ≈ 0.220, annret ≈ 0.132. Period: 2013-09-10 → 2026-03-31, 4580 daily returns.

- [ ] **Step 2: `docs/research/04.phase3-benchmark-b0-b1-report.md` content** — a short report:
  - Title + one-paragraph intro: the first bar-to-beat — B0 buy-and-hold BTC + B1 vol-targeted BTC on BTC/EUR daily (2013-09-10 → 2026-03-31, 4580 returns), zero-fee (a benchmark idealization; cost stress applied at evaluation per §9.6).
  - A results table: `Strategy | Total return | Annualized | Sharpe | Max DD` with the two rows.
  - Interpretation: BTC buy-and-hold is a high-return but brutal-drawdown (~82%) floor; vol-targeting at the master plan's 10%/yr target (§9, 30d) is the low-risk floor — maxDD ~22% (vs 82%) at a slightly higher Sharpe (~1.11, target-invariant), median exposure ~0.17×.
  - **Distrust-the-instrument note:** the whole stack (dataset → returns → strategy → backtester → metrics) runs on real data and the numbers are sane — BTC's ~82% max drawdown is a known historical fact (2018/2022 crashes), confirming the backtester + maxDD are correct.
  - Caveats: single-asset BTC only; zero transaction cost; the full B0–B4 panel + DSR/PBO/SPA comparison (the §9 deployment rule) is deferred to later iterations.

- [ ] **Step 3: Commit** — `docs(benchmark): B0/B1 bar-to-beat report on real BTC` (report + the Task-1 helper if not already committed). Full gate first.

---

### Task 3: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-026: B0/B1 bar-to-beat report (Phase 3)`: added `returns_from_prices` (close-to-close, reusable by B2–B4); ran B0 buy-and-hold + B1 vol-target on real BTC/EUR daily (2013–2026, 4580 returns) through the backtester → `docs/research/04.phase3-benchmark-b0-b1-report.md`: **B0 Sharpe 1.075 / maxDD 82.5% / 66.7% annualized / 607×**; **B1 (10%/yr per §9, 30d) Sharpe 1.111 / maxDD 22.0% / 13.2% annualized / 3.76×** (Sharpe target-invariant; 10–12% is a single risk/return ray). Validates the full stack on real data (the ~82% DD matches BTC's history — the engine is right); records the first deployment floor. Zero-fee idealization; single-asset; full B0–B4 panel deferred. Plan `00018`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-026 closeout — bar-to-beat report`.
