# Inverse-Vol Majors Basket (B2 generator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `inverse_vol_basket(prices_by_asset, *, lookback)` to `cli/benchmark/strategies.py` — a pure, look-ahead-free generator that turns a set of pre-aligned equal-length price series into the inverse-vol-weighted basket's daily net portfolio return series (B2 in the §9 benchmark family).

**Architecture:** One stdlib function appended to the existing `cli/benchmark/strategies.py`, exported from `cli/benchmark/__init__.py`, reusing the module's `returns_from_prices` and `BenchmarkError`. TDD on synthetic prices. The caller (a later real-data report iteration) supplies pre-aligned series; this function does no I/O.

**Tech Stack:** Python 3.14, stdlib only (`statistics.stdev`). Ruff line-length 132, double quotes. Spec: `docs/specs/00022-inverse-vol-basket-design.md`.

## Global Constraints

- **Look-ahead-free (correctness-critical):** `weight_i[t]` uses `returns_i[t-lookback:t]` (strictly `< t`) and is applied to `returns_i[t]`. A test asserts a future price cannot change any earlier portfolio return.
- **Never-NaN / loud failure:** degenerate input raises `BenchmarkError`, never returns NaN/inf. Zero-vol assets are *excluded* from a day's weighting (they'd take infinite inverse-vol weight), not allowed to poison it.
- **Reuse, don't reinvent:** compute per-asset returns via the existing `returns_from_prices` (which already raises `BenchmarkError` on non-finite/non-positive/too-short prices); use stdlib `statistics.stdev` (sample stdev) for the realized-vol window, matching `vol_target`.
- **No I/O, no CLI, no README change, no new deps.** Data loading + calendar alignment are the caller's job (a later iteration).
- Guard int params against `bool` (`bool` is a subclass of `int`): `isinstance(lookback, int) and not isinstance(lookback, bool)`.

---

### Task 1: `inverse_vol_basket` generator (TDD)

**Files:**
- Modify: `cli/benchmark/strategies.py` (append the function)
- Modify: `cli/benchmark/__init__.py` (export `inverse_vol_basket`)
- Test: `tests/test_benchmark_strategies.py` (append)

**Interfaces:**
- Consumes: `returns_from_prices(prices: list[float]) -> list[float]` and `BenchmarkError` from the same package; `buy_and_hold`, `run_backtest` for the integration test.
- Produces: `inverse_vol_basket(prices_by_asset: dict[str, list[float]], *, lookback: int) -> list[float]` — net portfolio return series of length `L-1` (`L` = common price-series length), aligned with `returns_from_prices`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_benchmark_strategies.py`:

```python
def test_inverse_vol_basket_value_two_assets():
    # A has 1/3 the trailing vol of B at t=2 -> weights 0.75 / 0.25.
    # returns_A[:2]=[0.02,-0.02] (stdev s), returns_B[:2]=[0.06,-0.06] (stdev 3s).
    # portfolio[2] = 0.75*returns_A[2] + 0.25*returns_B[2] = 0.75*0.10 + 0.25*(-0.20) = 0.025.
    a = [100, 102, 99.96, 109.956]
    b = [100, 106, 99.64, 79.712]
    out = inverse_vol_basket({"A": a, "B": b}, lookback=2)
    assert out[0] == 0.0 and out[1] == 0.0
    assert abs(out[2] - 0.025) < 1e-9


def test_inverse_vol_basket_equal_vol_equal_weight():
    # C and D share the same trailing window -> equal vol -> 0.5/0.5.
    # portfolio[2] = 0.5*(0.10 + 0.04) = 0.07.
    c = [100, 102, 99.96, 109.956]
    d = [100, 102, 99.96, 103.9584]
    out = inverse_vol_basket({"C": c, "D": d}, lookback=2)
    assert abs(out[2] - 0.07) < 1e-9


def test_inverse_vol_basket_length_and_warmup():
    prices = {"A": [100, 101, 102, 103, 104, 105], "B": [100, 99, 101, 98, 102, 97]}
    out = inverse_vol_basket(prices, lookback=2)
    assert len(out) == 6 - 1  # L - 1
    assert out[0] == 0.0 and out[1] == 0.0  # first `lookback` are warm-up


def test_inverse_vol_basket_no_look_ahead():
    # Perturbing an asset's LAST price changes only the last return; it must not
    # alter any earlier portfolio return (a future price cannot leak backward).
    a = [100, 101, 102, 101, 103, 104]
    b = [100, 99, 101, 100, 102, 101]
    base = inverse_vol_basket({"A": a, "B": b}, lookback=2)
    a2 = a.copy()
    a2[-1] = 130.0  # very different last price -> changes returns_A[-1] only
    perturbed = inverse_vol_basket({"A": a2, "B": b}, lookback=2)
    assert base[:-1] == perturbed[:-1]  # all earlier periods identical (no leak)
    assert base[-1] != perturbed[-1]    # the last period does use the last price


def test_inverse_vol_basket_window_is_real():
    # Perturbing the FIRST price moves returns[0], which is inside the vol window
    # of the first weighted period (t=lookback) -> its weight, hence its return, changes.
    a = [100, 101, 102, 101, 103, 104]
    b = [100, 99, 101, 100, 102, 101]
    base = inverse_vol_basket({"A": a, "B": b}, lookback=2)
    a2 = a.copy()
    a2[0] = 60.0  # changes returns_A[0] (in the window [0:2] of period t=2)
    perturbed = inverse_vol_basket({"A": a2, "B": b}, lookback=2)
    assert perturbed[0] == 0.0 and perturbed[1] == 0.0  # warm-up unchanged
    assert base[2] != perturbed[2]  # first weighted period's weight moved


def test_inverse_vol_basket_zero_vol_asset_excluded():
    # E is constant over the trailing window (vol 0) -> dropped at t=2;
    # F carries weight 1, so portfolio[2] == F's own return[2].
    e = [100, 100, 100, 110]
    f = [100, 102, 99.96, 105]
    out = inverse_vol_basket({"E": e, "F": f}, lookback=2)
    assert abs(out[2] - (105 / 99.96 - 1)) < 1e-9


def test_inverse_vol_basket_all_zero_vol_day_is_flat():
    # Both assets constant over the window -> nothing weightable -> 0.0.
    e = [100, 100, 100, 110]
    g = [50, 50, 50, 40]
    out = inverse_vol_basket({"E": e, "G": g}, lookback=2)
    assert out[2] == 0.0


def test_inverse_vol_basket_single_asset():
    # One asset -> weight 1 after warm-up -> basket return == that asset's returns.
    a = [100, 101, 102, 103, 104, 105]
    out = inverse_vol_basket({"A": a}, lookback=2)
    rets = returns_from_prices(a)
    assert len(out) == len(rets)
    for t in range(2):
        assert out[t] == 0.0
    for t in range(2, len(rets)):
        assert abs(out[t] - rets[t]) < 1e-12


def test_inverse_vol_basket_guards():
    good = [100, 101, 102, 103]
    import pytest
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({}, lookback=2)                       # empty dict
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": good, "B": [100, 101, 102]}, lookback=2)  # unequal lengths
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": [100, 101, 102]}, lookback=2)   # L=3 < lookback+2=4
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": [100, -1, 102, 103]}, lookback=2)  # non-positive price
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": [100, float("nan"), 102, 103]}, lookback=2)  # non-finite
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": good}, lookback=1)              # lookback < 2
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": good}, lookback=True)           # bool, not int


def test_inverse_vol_basket_integrates_with_backtester():
    a = [100, 101, 102, 101, 103, 104, 105, 106]
    b = [100, 99, 101, 100, 102, 101, 103, 102]
    pr = inverse_vol_basket({"A": a, "B": b}, lookback=3)
    result = run_backtest(pr, buy_and_hold(len(pr)), fee_rate=0.0, periods_per_year=365)
    assert math.isfinite(result["sharpe"])
    assert math.isfinite(result["max_drawdown"])
```

Ensure the test module's imports cover `inverse_vol_basket`, `returns_from_prices`, `buy_and_hold`, `run_backtest`, `BenchmarkError`, and `math` (add any missing to the existing import block — do not duplicate).

- [ ] **Step 2: Run the tests, verify they fail** — `uv run pytest tests/test_benchmark_strategies.py -k inverse_vol_basket -q`. Expected: FAIL (`NameError`/`ImportError`: `inverse_vol_basket` not defined).

- [ ] **Step 3: Implement.** Append to `cli/benchmark/strategies.py` (ensure `import statistics` is present at the top — add if missing):

```python
def inverse_vol_basket(prices_by_asset: dict[str, list[float]], *, lookback: int) -> list[float]:
    """Inverse-vol-weighted basket net return series (B2), look-ahead-free.

    Each price series must be pre-aligned to the same length L. For return-period
    t >= lookback, weight asset i by 1 / stdev(returns_i[t-lookback:t]) (the window
    strictly before t), normalized over assets with positive trailing vol, and apply
    to returns_i[t]. Warm-up (t < lookback) and days with no positive-vol asset are 0.0.
    """
    if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 2:
        raise BenchmarkError(f"lookback must be an int >= 2, got {lookback!r}")
    if not isinstance(prices_by_asset, dict) or not prices_by_asset:
        raise BenchmarkError("prices_by_asset must be a non-empty dict of price series")

    returns_by_asset: dict[str, list[float]] = {}
    lengths: set[int] = set()
    for asset, prices in prices_by_asset.items():
        returns_by_asset[asset] = returns_from_prices(prices)  # validates finite/positive/len>=2
        lengths.add(len(prices))
    if len(lengths) != 1:
        raise BenchmarkError(f"all price series must have equal length, got {sorted(lengths)}")
    length = lengths.pop()
    if length < lookback + 2:
        raise BenchmarkError(f"price series length {length} too short for lookback {lookback} (need >= {lookback + 2})")

    n_returns = length - 1
    portfolio: list[float] = []
    for t in range(n_returns):
        if t < lookback:
            portfolio.append(0.0)
            continue
        inv_weights: dict[str, float] = {}
        for asset, rets in returns_by_asset.items():
            vol = statistics.stdev(rets[t - lookback:t])
            if vol > 0.0:
                inv_weights[asset] = 1.0 / vol
        if not inv_weights:
            portfolio.append(0.0)
            continue
        total = sum(inv_weights.values())
        portfolio.append(sum((inv / total) * returns_by_asset[asset][t] for asset, inv in inv_weights.items()))
    return portfolio
```

Then export it in `cli/benchmark/__init__.py` (add `inverse_vol_basket` to the existing import-from-`.strategies` and `__all__`).

- [ ] **Step 4: Run the tests, verify they pass** — `uv run pytest tests/test_benchmark_strategies.py -k inverse_vol_basket -q`. Expected: PASS (10 tests).

- [ ] **Step 5: Full gate** — `git add -A`; `uv run pre-commit run -a` clean; `uv run pytest -q` green (prior 459 + 10 new = **469 passed**).

- [ ] **Step 6: Commit** — `feat(benchmark): add inverse_vol_basket generator (B2, look-ahead-free)`.

---

### Task 2: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1:** Append `## 2026-07-08 — iter-030: inverse-vol majors basket generator (B2, Phase 3)` with bullets covering: added `inverse_vol_basket(prices_by_asset, *, lookback)` to `cli/benchmark/strategies.py` — the B2 generator producing the inverse-vol-weighted basket's daily net return series from pre-aligned equal-length price series; look-ahead-free (`weight_i[t]` from `returns_i[t-lookback:t]`, excludes `t`), zero-vol assets excluded and the rest renormalized, warm-up + all-excluded days flat; raises `BenchmarkError` on empty/unequal-length/too-short/non-finite/non-positive/bad-lookback input; reuses `returns_from_prices` + `statistics.stdev`. **Composition decision:** fixed 10-asset intersection basket (the pure generator; the dynamic-composition full-history variant is parked as **T0007**). 10 TDD tests (value, equal-vol, warm-up/length, no-look-ahead, window-is-real, zero-vol exclusion, all-flat, single-asset, guards, backtester integration). No real-data run yet — the B2 bar-to-beat vs BTC over the common window follows. Spec `00022`, plan `00022`. Seventh Phase-3 component. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-030 closeout — inverse-vol basket generator`.
