# A1 causal feature primitives — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build `cli/features/` — three strictly-causal, leak-tested feature primitives (`momentum`, `channel_position`, `realized_vol`) that A1/A2 consume.

**Architecture:** Pure stdlib (`math`, `statistics`), `list[float]` in/out, mirroring `cli/benchmark/strategies.py`. A `FeatureError` for validation. All three share `sma_gate`'s causal alignment (return length `len(prices)-1`; `feature[k]` uses only `prices[≤k]`; warm-up `0.0`).

**Tech Stack:** Python 3.14, uv, pytest, ruff (line 132, double quotes).

## Global Constraints

- Study `cli/benchmark/strategies.py` (`sma_gate`, `vol_target`, `returns_from_prices`, `inverse_vol_basket`) and **match its style exactly**: input validation with clear messages raising a package `*Error`, `list[float]` I/O, no NaN/inf ever emitted.
- **Causal alignment (identical to `sma_gate`):** over `prices` length `L`, return length `L-1`; element `k` = the move `prices[k]→prices[k+1]`; `feature[k]` computed from only `prices[≤k]`; warm-up → `0.0`.
- Validation on every function: `prices` a `list` of `≥2` finite positive numbers (else `FeatureError`); `lookback`/`window` `int ≥ 2`, reject `bool` (`isinstance(x, bool)` is `True` for ints — guard it), else `FeatureError`.
- Loggers (if any) named `get_logger("features.<module>")` — but these are pure functions, so none expected.
- Commit gate: `uv run pre-commit run -a` (per CLAUDE.md), not individual tools.

---

### Task 1: package skeleton + `FeatureError` + `momentum`

**Files:**
- Create: `cli/features/__init__.py`, `cli/features/errors.py`, `cli/features/momentum.py`
- Test: `tests/test_features_momentum.py`

**Interfaces:**
- Produces: `FeatureError(Exception)`; `momentum(prices: list[float], *, lookback: int) -> list[float]`.

- [ ] **Step 1 — failing tests** (`tests/test_features_momentum.py`): known-answer (`prices=[10,11,12,13,14]`, `lookback=2` → length 4, `m=[0.0, 0.0, 12/10-1, 13/11-1]` i.e. `[0.0, 0.0, 0.2, 0.181818…]`; warm-up `k<lookback` is `0.0`); output length `== len(prices)-1`; **leak test** — `momentum(prices,lookback=2)[:k]` unchanged when `prices[k+1:]` are mutated (build two price lists identical through index `k`, differing after; assert the first `k+1` feature values are equal); guards — non-positive price, non-finite price, `lookback` as `bool`/`<2`/non-int → `FeatureError`.
- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_features_momentum.py -v`).
- [ ] **Step 3 — implement** `errors.py` (`class FeatureError(Exception): ...`) and `momentum.py`:
  ```python
  from __future__ import annotations
  import math
  from cli.features.errors import FeatureError

  def _validate_prices(prices: list[float]) -> None:
      if not isinstance(prices, list) or len(prices) < 2:
          raise FeatureError(f"prices must be a list of >= 2 values, got {prices!r}")
      for p in prices:
          if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p <= 0:
              raise FeatureError(f"prices must be finite positive numbers, got {p!r}")

  def _validate_window(name: str, value: int) -> None:
      if not isinstance(value, int) or isinstance(value, bool) or value < 2:
          raise FeatureError(f"{name} must be an int >= 2, got {value!r}")

  def momentum(prices: list[float], *, lookback: int) -> list[float]:
      """Causal past-return feature: m[k] = prices[k]/prices[k-lookback] - 1 for k >= lookback, else
      0.0. Length len(prices)-1, aligned to returns_from_prices (element k = the move prices[k] ->
      prices[k+1]); m[k] uses only prices[<= k] -> no look-ahead."""
      _validate_prices(prices)
      _validate_window("lookback", lookback)
      out: list[float] = []
      for k in range(len(prices) - 1):
          out.append(prices[k] / prices[k - lookback] - 1 if k >= lookback else 0.0)
      return out
  ```
  Put `_validate_prices`/`_validate_window` where Tasks 2–3 can reuse them (e.g. a small `cli/features/_validate.py`, or import from `momentum`); pick one and keep it DRY. Export `momentum` + `FeatureError` from `cli/features/__init__.py`.
- [ ] **Step 4 — run, verify green** (`uv run pytest tests/test_features_momentum.py -v`).
- [ ] **Step 5 — commit** (`feat(features): add causal multi-horizon momentum primitive`).

### Task 2: `channel_position` (Donchian)

**Files:**
- Create: `cli/features/channel.py`
- Test: `tests/test_features_channel.py`

**Interfaces:**
- Consumes: the shared `_validate_prices`/`_validate_window` from Task 1.
- Produces: `channel_position(prices: list[float], *, window: int) -> list[float]`.

- [ ] **Step 1 — failing tests:** known-answer — with `window=3` and prices rising to a fresh high, `channel_position[k] == +1.0` at a new high, `== -1.0` at a new low, `== 0.0` at the window midpoint (construct a small explicit series and hand-compute `2*(P-lo)/(hi-lo)-1`); flat window (`prices=[5,5,5,5]`, `window=3`) → all `0.0` (degenerate `hi==lo`); length `len(prices)-1`; warm-up (`k<window-1`) `0.0`; leak test (as Task 1); guards → `FeatureError`.
- [ ] **Step 2 — run, verify red.**
- [ ] **Step 3 — implement:**
  ```python
  def channel_position(prices: list[float], *, window: int) -> list[float]:
      """Donchian channel position in [-1, +1]: with hi/lo = max/min(prices[k-window+1:k+1]),
      pos[k] = 2*(prices[k]-lo)/(hi-lo) - 1 (+1 at the channel high, -1 at the low). Flat window
      (hi==lo) and warm-up (k<window-1) -> 0.0. Length len(prices)-1; uses only prices[<= k]."""
      _validate_prices(prices)
      _validate_window("window", window)
      out: list[float] = []
      for k in range(len(prices) - 1):
          if k < window - 1:
              out.append(0.0); continue
          w = prices[k - window + 1 : k + 1]
          hi, lo = max(w), min(w)
          out.append(2 * (prices[k] - lo) / (hi - lo) - 1 if hi > lo else 0.0)
      return out
  ```
  Export from `__init__.py`.
- [ ] **Step 4 — run, verify green.**
- [ ] **Step 5 — commit** (`feat(features): add causal Donchian channel-position primitive`).

### Task 3: `realized_vol`

**Files:**
- Create: `cli/features/volatility.py`
- Test: `tests/test_features_volatility.py`

**Interfaces:**
- Consumes: shared validators; `returns_from_prices` from `cli.benchmark.strategies`.
- Produces: `realized_vol(prices: list[float], *, lookback: int) -> list[float]`.

- [ ] **Step 1 — failing tests:** known-answer — `prices` with hand-computed returns, `realized_vol[k] == statistics.stdev(returns[k-lookback+1:k+1])` for `k >= lookback`; warm-up (`k<lookback`) `0.0`; a constant-price series (zero returns → zero-vol window) → `0.0`; length `len(prices)-1`; leak test; guards → `FeatureError`.
- [ ] **Step 2 — run, verify red.**
- [ ] **Step 3 — implement** (uses `returns_from_prices`; `returns` has length `len(prices)-1`, `returns[j]` = move `prices[j]→prices[j+1]`, so the `lookback` returns ending at the move into `k` are `returns[k-lookback:k]` for the price-index alignment — derive carefully so `realized_vol[k]` uses only `prices[≤k]`, and add a leak test that would fail if it peeked at `prices[k+1]`):
  ```python
  import statistics
  from cli.benchmark.strategies import returns_from_prices

  def realized_vol(prices: list[float], *, lookback: int) -> list[float]:
      """Realized-vol state: stdev of the trailing `lookback` returns ending at the move into k,
      using only prices[<= k]. Warm-up (k < lookback) and zero-vol windows -> 0.0. Length
      len(prices)-1; aligned to returns_from_prices."""
      _validate_prices(prices)
      _validate_window("lookback", lookback)
      returns = returns_from_prices(prices)  # length len(prices)-1
      out: list[float] = []
      for k in range(len(prices) - 1):
          if k < lookback:
              out.append(0.0); continue
          window = returns[k - lookback : k]  # returns[j] uses prices[j],prices[j+1]; j<=k-1 -> prices[<=k]
          rv = statistics.stdev(window)
          out.append(rv if rv > 0 else 0.0)
      return out
  ```
  **Verify the window bound by hand against the leak test** — the last return used must be `returns[k-1]` (move `prices[k-1]→prices[k]`), never `returns[k]` (which uses `prices[k+1]`). Export from `__init__.py`.
- [ ] **Step 4 — run, verify green** — plus run the full suite `uv run pytest -q` and `uv run ruff check` / `ruff format --check` on `cli/features/` and the new tests.
- [ ] **Step 5 — commit** (`feat(features): add causal realized-vol-state primitive`).

### Task 4: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1** — append a `## 2026-07-08 — iter-040: A1 causal feature primitives (Phase 4)` section: what landed (`cli/features/` — momentum / channel_position / realized_vol, all `sma_gate`-aligned + leak-tested), the causal convention, and that this is the A1/A2 substrate (no strategy verdict yet). Note the scoping decision is in `.tmp/decisions.md` `[iter-040]`.
- [ ] **Step 2** — `uv run pre-commit run -a`; stage everything it rewrites; commit (`docs: iter-040 closeout — A1 causal feature substrate`).
