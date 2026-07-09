# A2 Donchian TSMOM book — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** A look-ahead-free `cli/alpha/a2.py` (`A2Config` + `a2_book_returns`) — a per-asset Donchian breakout ensemble, inverse-vol aggregated, vol-targeted — returning the same dict shape as `a1_book_returns` so iter-053's cost model + both verdict tools plug in unchanged.

**Architecture:** Maximal reuse of `cli/alpha/a1.py`. The ONLY new logic is the per-asset direction: a per-lookback Donchian **state machine** over `channel_position`, ensembled by mean. Weighting (`_inverse_vol_weights`), returns (`_asset_returns`), union-calendar mapping (`_map_to_union_index`), validation, `vol_target` → `run_backtest`, and `asset_positions` all mirror A1.

**Tech Stack:** Python 3.14, uv, pytest, ruff (line 132, double quotes). Pure-Python/list-based; no numpy.

## Global Constraints

- **Look-ahead-free is non-negotiable.** Every per-period value uses only `prices[<= k]` (and the prior signal). Ship the book-level leak test and **verify it fails on a deliberately-peeking implementation** before trusting it.
- Alignment convention: every per-period series has length `union_len - 1`; element `k` = the move into `k+1`, computed from data at `≤ k`. Same as `a1.py`.
- Do NOT modify `cli/alpha/a1.py`, `cli/alpha/killbar.py`, `cli/benchmark/`, or `cli/validation/`. Reuse A1's private helpers by importing them from `cli.alpha.a1` (they are module-private by underscore but importable) — do not copy-paste their bodies.
- Errors raise `AlphaError` (`cli/alpha/errors.py`).
- Commit gate: `uv run pre-commit run -a`.

---

### Task 1: `A2Config` + the Donchian state machine + per-asset directions

**Files:** Create `cli/alpha/a2.py`; create `tests/test_alpha_a2_directions.py`.

**Interfaces:**
- Produces: `A2Config` (frozen, kw-only): `lookbacks: tuple[int, ...]`, `short: str` ∈ {`"off"`,`"on"`}, `target_vol: float`, `band: float = 1.0`, `short_exposure: float = 0.5`, `vol_lookback: int = 30`, `basket_lookback: int = 30`, `max_leverage: float = 1.0`, `periods_per_year: int = 365`.
- Produces: `_donchian_signal(prices: list[float], *, window: int, band: float) -> list[float]` — length `len(prices)-1`.
- Produces: `_asset_directions_a2(prices_by_asset, union_ts, asset_ts, *, config) -> dict[str, list[float | None]]`.

- [ ] **Step 1 — failing tests** (`tests/test_alpha_a2_directions.py`):
  - **known-answer hold semantics**: a hand-built path that rises to a new `window`-high, then drifts sideways *below* the high, then breaks to a new `window`-low. Assert `_donchian_signal` is `0.0` through warm-up/pre-break, `+1.0` at the high **and held through the drift**, then `-1.0` from the low onward. (This is the whole point — it must HOLD, not go flat between breaks.)
  - **band**: with `band=1.0`, `+1` fires exactly when `channel_position == 1.0` (a new window max).
  - **ensemble**: two lookbacks whose signals differ at some `k` → `d_i[k] == mean(sig)`; e.g. `(+1, -1)` → `0.0`.
  - **short toggle**: `short="off"` → every direction `>= 0`; `short="on"` → a period whose ensemble is negative yields exactly `ensemble * short_exposure` (e.g. `-1.0 * 0.5 == -0.5`).
  - **no look-ahead**: mutate `prices[k+1:]`; `_donchian_signal(...)[:k]` bit-identical.
  - **union/None**: an asset absent (`None`) on a union day gets `None` direction there; a present-but-warming asset gets `0.0`.
  - guards: `lookbacks` empty / non-int / `< 2`; `band` not in `(0, 1]`; bad `short` enum; non-positive `target_vol` → `AlphaError`.
- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_alpha_a2_directions.py -v`).
- [ ] **Step 3 — implement** in `cli/alpha/a2.py`. Import from `cli.alpha.a1`: `_map_to_union_index`, `_asset_returns`, `_inverse_vol_weights`, `_validate_prices_by_asset`. Import `channel_position` from `cli.features`. The state machine:
  ```python
  def _donchian_signal(prices, *, window, band):
      cp = channel_position(prices, window=window)
      out, held = [], 0.0
      for k in range(len(cp)):
          if cp[k] >= band:
              held = 1.0
          elif cp[k] <= -band:
              held = -1.0
          out.append(held)   # hold between breaks; 0.0 until the first break
      return out
  ```
  Directions: compute `_donchian_signal` on each asset's **contiguous** (None-filtered) price series, map each to the union return index via `_map_to_union_index`, ensemble by mean over lookbacks (skip a union period where the mapping is `None` → direction `None`), then apply the short toggle.
- [ ] **Step 4 — run, verify green**; then `uv run pytest -q` (full suite) + `uv run ruff check` / `ruff format --check`.
- [ ] **Step 5 — commit** (`feat(alpha): add A2 Donchian signal + per-asset direction builder`).

### Task 2: `a2_book_returns`

**Files:** Modify `cli/alpha/a2.py`; create `tests/test_alpha_a2_book.py`; modify `cli/alpha/__init__.py` (export `A2Config`, `a2_book_returns`).

**Interfaces:**
- Consumes: Task 1's `_asset_directions_a2`; `_inverse_vol_weights`, `_asset_returns` (from `cli.alpha.a1`); `vol_target` (`cli.benchmark.strategies`); `run_backtest` (`cli.backtest`).
- Produces: `a2_book_returns(prices_by_asset: dict[str, list[float | None]], *, config: A2Config) -> dict` with keys `book_base_returns`, `vol_target_positions`, `net_returns`, `asset_positions`, `metrics` — **the same shape as `a1_book_returns`** (note: no `btc_prices` argument; A2 has no market gate).

- [ ] **Step 1 — failing tests** (`tests/test_alpha_a2_book.py`), on a synthetic 2–3 asset universe with a real trend leg, a chop leg, and a drawdown leg:
  - **book-level leak test**: two universes identical through union index `k_common`, differing after; assert `net_returns[:k_common]` **and** `asset_positions[a][:k_common]` bit-identical. (Use a divergent tail anchored near the boundary price so the book cannot blow up `run_backtest`'s degenerate-equity guard.)
  - **reconstruct identity**: `Σ_i asset_positions[i][k] * ret_i[k] == net_returns[k]` (abs < 1e-9) — the A1 identity, which validates the positions used by iter-053's cost model.
  - **engagement**: flipping `lookbacks`, `short`, and `target_vol` each changes `net_returns`; `short="on"` yields at least one negative `asset_positions` value; `short="off"` yields none.
  - **LOW-TURNOVER PREMISE** (the reason A2 exists): on the same universe, mean per-period turnover `Σ_i |Δ asset_positions_i|` for A2 (`short="off"`, `lookbacks=(20,)`) is **strictly less than** the same statistic for an `a1_book_returns` book (`base="equal_risk_basket", regime="single_gate", short="off"`, same `target_vol`). Assert `a2_turnover < a1_turnover`. If this fails, that is a **finding**, not a test to weaken — report it.
  - **planted trend**: a synthetic universe in a clean uptrend → `metrics["sharpe"] > 0`.
  - guards: non-`A2Config` config, empty/unequal-length `prices_by_asset`, non-positive/None-invalid prices → `AlphaError`.
- [ ] **Step 2 — run, verify red.**
- [ ] **Step 3 — implement** `a2_book_returns`: validate; build `union_ts = list(range(length))` and per-asset present-index lists; `directions = _asset_directions_a2(...)`; `returns = {a: _asset_returns(p)}`; `weights = _inverse_vol_weights(prices_by_asset, lookback=config.basket_lookback)`; `book_base_returns[k] = Σ weights[k].get(a,0.0) * (directions[a][k] or 0.0) * (returns[a][k] or 0.0)` (skip when either is `None`); `positions = vol_target(book_base_returns, target_vol=config.target_vol / sqrt(config.periods_per_year), lookback=config.vol_lookback, max_leverage=config.max_leverage)`; `backtest = run_backtest(book_base_returns, positions, fee_rate=0.0, periods_per_year=config.periods_per_year)`; `asset_positions[a][k] = weights[k].get(a,0.0) * (directions[a][k] or 0.0) * positions[k]`.
- [ ] **Step 4 — verify green**; full suite + ruff.
- [ ] **Step 5 — commit** (`feat(alpha): add a2_book_returns Donchian ensemble book`).

### Task 3: closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1** — append the `## 2026-07-09 — iter-052: …` entry: what landed (`cli/alpha/a2.py`, the Donchian hold-state machine, the ensemble, the low-turnover test result with its measured A2-vs-A1 turnover ratio), the leak test verified to bite, and that **no verdict** was recorded (iter-053 runs the 8-trial net-of-cost-first verdict). Note the decisions are in `.tmp/decisions.md` `[iter-052]`.
- [ ] **Step 2** — `uv run pre-commit run -a`; stage rewrites; commit (`docs: iter-052 closeout — A2 Donchian book`).
