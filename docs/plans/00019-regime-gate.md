# Regime Gate (200-day SMA) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `sma_gate` to `cli/benchmark/` per `docs/specs/00019-regime-gate-design.md` — a look-ahead-free long/flat regime signal (the prior survivor), aligned with the return series, composing with the backtester.

**Architecture:** Append `sma_gate` to `cli/benchmark/strategies.py`; export. TDD.

**Tech Stack:** Python 3.14, stdlib `math`, `statistics`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. **Alignment (fixed):** `sma_gate(prices, window)` returns length `len(prices)-1` (aligned with `returns_from_prices`); `signal[k]` uses `prices[k-window+1:k+1]` (through `prices[k]`, EXCLUDING `prices[k+1]`) — no look-ahead. Guards raise `BenchmarkError`. No CLI/README change.

---

### Task 1: `sma_gate` + tests

**Files:** Modify `cli/benchmark/strategies.py`, `cli/benchmark/__init__.py`, `tests/test_benchmark_strategies.py`.

- [ ] **Step 1: Append failing tests** to `tests/test_benchmark_strategies.py`:

```python
def test_sma_gate_value():
    assert sma_gate([10.0, 11.0, 12.0, 9.0, 8.0, 13.0], window=3) == [0.0, 0.0, 1.0, 0.0, 0.0]


def test_sma_gate_length_and_warmup():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    g = sma_gate(prices, window=3)
    assert len(g) == len(prices) - 1
    assert g[:2] == [0.0, 0.0]


def test_sma_gate_no_lookahead():
    prices = [10.0, 11.0, 12.0, 9.0, 8.0, 13.0, 14.0]
    window, k = 3, 2
    base = sma_gate(prices, window=window)
    perturbed = list(prices)
    perturbed[k + 1] = 100.0
    pert = sma_gate(perturbed, window=window)
    assert pert[k] == base[k]            # signal[k]'s window excludes prices[k+1]
    assert pert[k + 1] != base[k + 1]    # signal[k+1]'s window includes k+1 -> changes (window is real)


def test_sma_gate_declining_mostly_flat():
    g = sma_gate([100.0, 90.0, 80.0, 70.0, 60.0, 50.0], window=3)
    assert all(s == 0.0 for s in g)


def test_sma_gate_short_series_all_flat():
    assert sma_gate([10.0, 11.0], window=5) == [0.0]


@pytest.mark.parametrize(
    "prices,window",
    [([10.0], 3), ([10.0, float("nan")], 3), ([10.0, -5.0], 3), ([10.0, 11.0, 12.0], 1), ([10.0, 11.0, 12.0], 2.5)],
)
def test_sma_gate_guards(prices, window):
    with pytest.raises(BenchmarkError):
        sma_gate(prices, window=window)


def test_sma_gate_composes_with_backtester():
    prices = [100.0 * (1.003 ** i) * (1 + 0.02 * ((i % 5) - 2)) for i in range(300)]
    rets = returns_from_prices(prices)
    gate = sma_gate(prices, window=50)
    r0 = run_backtest(rets, gate, fee_rate=0.0, periods_per_year=252)  # gated buy-and-hold
    assert math.isfinite(r0["sharpe"]) and r0["n_periods"] == len(rets)
    gv = [g * v for g, v in zip(gate, vol_target(rets, target_vol=0.01, lookback=20, max_leverage=1.0))]
    r1 = run_backtest(rets, gv, fee_rate=0.0, periods_per_year=252)  # gated vol-target
    assert math.isfinite(r1["sharpe"])
```

(Add `sma_gate` to the existing `from cli.benchmark import ...` line; `math` is already imported in the test file.)

- [ ] **Step 2: Run, verify fail** → ImportError.

- [ ] **Step 3: Append to `cli/benchmark/strategies.py`:**
```python
def sma_gate(prices: list[float], *, window: int) -> list[float]:
    """Long/flat 200-day-style regime gate: signal[k] = 1.0 if prices[k] > SMA(prices[k-window+1:k+1]) else 0.0.

    Returns length len(prices)-1, aligned with returns_from_prices(prices) (element k = the move prices[k] ->
    prices[k+1]). signal[k] uses only prices[<= k] (through prices[k], the price at the start of return-period
    k) and never prices[k+1] -> no look-ahead. Warm-up (k < window-1) is 0.0.
    """
    if not isinstance(prices, list) or len(prices) < 2:
        raise BenchmarkError(f"prices must be a list of >= 2 values, got {prices!r}")
    for p in prices:
        if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
            raise BenchmarkError(f"prices must be finite positive numbers, got {p!r}")
    if not isinstance(window, int) or window < 2:
        raise BenchmarkError(f"window must be an int >= 2, got {window!r}")
    signal: list[float] = []
    for k in range(len(prices) - 1):
        if k < window - 1:
            signal.append(0.0)
            continue
        sma = statistics.mean(prices[k - window + 1 : k + 1])
        signal.append(1.0 if prices[k] > sma else 0.0)
    return signal
```

- [ ] **Step 4: Export** `sma_gate` in `cli/benchmark/__init__.py` (`__all__` alphabetized).
- [ ] **Step 5: Run tests, verify pass** — `uv run pytest tests/test_benchmark_strategies.py -q`.
- [ ] **Step 6: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.
- [ ] **Step 7: Commit** — `feat(benchmark): add sma_gate 200-day long/flat regime gate`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-027: regime gate (200-day SMA long/flat) (Phase 3)`: `cli/benchmark/sma_gate` — the prior survivor (§5): a long/flat signal (`prices[k] > SMA(prices[k-window+1:k+1])`) aligned with the return series (length `len(prices)-1`), look-ahead-free (signal[k] uses `prices[<= k]`, never `prices[k+1]`; a test asserts invariance to `prices[k+1]`). Composes multiplicatively — gated buy-and-hold = `sma_gate` itself, gated vol-target = `sma_gate × vol_target`. `BenchmarkError` guards. The B3 gate mechanism (B3-proper = gate × basket needs B2). Spec/plan `00019`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-027 closeout — regime gate`.
