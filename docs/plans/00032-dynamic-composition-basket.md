# T0007 dynamic-composition basket — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** A look-ahead-free `dynamic_inverse_vol_basket` over the full-history union calendar (2→10 majors as they list), then the finding-1 verdict (does it beat single-asset BTC?).

**Architecture:** Pure-stdlib addition to `cli/benchmark/strategies.py`, generalizing `inverse_vol_basket` to a union calendar with per-asset presence (`None`) + per-asset warm-up. A scratchpad script drives the full-history run + report (mirroring the fixed-window B2 report).

**Tech Stack:** Python 3.14, uv, pytest, ruff (line 132, double quotes), polars (loading only).

## Global Constraints

- Match `cli/benchmark/strategies.py` style exactly: `list[float]` I/O (now `list[float | None]` in), validation raising `BenchmarkError`, look-ahead convention identical to `inverse_vol_basket` (weight at period `t` uses returns strictly before `t`, applied to return `t`).
- **Look-ahead-free is non-negotiable** — a period's weights must be invariant to that period's (and any later) realized return; ship the leak test that proves it, verified to fail on a peeking implementation.
- Reuse `returns_from_prices`, `vol_target`, `run_backtest`; do not reimplement metrics.
- Commit gate: `uv run pre-commit run -a`.

---

### Task 1: `dynamic_inverse_vol_basket` + TDD

**Files:** Modify `cli/benchmark/strategies.py`; create `tests/test_benchmark_dynamic_basket.py`.

**Interfaces:**
- Produces: `dynamic_inverse_vol_basket(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[float]` (length `L-1`, `L` = the common union length).

- [ ] **Step 1 — failing tests** (`tests/test_benchmark_dynamic_basket.py`):
  - **known-answer**: 2 assets, A present throughout, B `None` for the first few days then present; `lookback=2`; hand-compute the per-period qualifying set, `1/stdev` weights (renormalized), and `portfolio[t]`. Assert exact.
  - **entry warm-up**: an asset entering at union-index `E` (`None` before) contributes 0 weight until it has a full `lookback` of returns (i.e. from period `E+lookback` on), then joins.
  - **gap**: a single `None` mid-series disqualifies that asset until `lookback` clean returns re-accrue after the gap.
  - **renormalization**: for a period with ≥2 qualifying assets, the applied weights sum to 1.0 (within 1e-12).
  - **all-absent / all-warmup period** → `0.0`.
  - **look-ahead invariance**: build two `prices_by_asset` identical through union-index `t`, differing at `t+1:` (for one or more assets); assert `dynamic_inverse_vol_basket(...)[:t]` is bit-identical between them.
  - **reduces to fixed**: with no `None`s + equal-length series, output equals `inverse_vol_basket(same, lookback=…)` element-wise.
  - guards: non-int/`bool`/`<2` lookback, empty dict, unequal lengths → `BenchmarkError`.
- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_benchmark_dynamic_basket.py -v`).
- [ ] **Step 3 — implement** `dynamic_inverse_vol_basket` in `cli/benchmark/strategies.py`:
  - Validate `lookback` (int, not bool, ≥2), non-empty dict, all series equal length `L` (`BenchmarkError`). Each element must be `None` or a finite positive float.
  - Build per-asset `ret_i` (length `L-1`): `ret_i[t] = prices_i[t+1]/prices_i[t] - 1` iff both present+positive, else `None`.
  - For `t` in `range(L-1)`: qualifying `i` iff `ret_i[t] is not None` **and** all of `ret_i[t-lookback:t]` are non-`None` (need `t >= lookback`) **and** `stdev(that window) > 0`; weight `1/stdev`; renormalize over qualifiers; `portfolio.append(Σ w·ret_i[t])` or `0.0` if none.
  - (Factor the shared inverse-vol-from-window logic if it keeps `inverse_vol_basket` DRY, but do not change `inverse_vol_basket`'s behavior.)
- [ ] **Step 4 — run, verify green**; then `uv run pytest -q` (full suite) + `uv run ruff check`/`ruff format --check`.
- [ ] **Step 5 — commit** (`feat(benchmark): add look-ahead-free dynamic-composition inverse-vol basket`).

### Task 2: full-history run + report + finding-1 verdict

**Files:** Create `docs/research/04.phase3-benchmark-b2-dynamic-report.md` (+ a scratchpad script under the scratchpad dir; not committed).

- [ ] **Step 1** — scratchpad script: load the 10 majors' `data/ohlc-full/<BASE>/EUR/1440.parquet` via `cli.ohlc.dataset.read_parquet`; build the **union `ts` calendar** (sorted union of all `ts`); map each asset's close onto it (`None` where no bar); assert BTC spans 2013-09-10→2026-03-31 and composition grows (n present per period 2→10).
- [ ] **Step 2** — run `dynamic_inverse_vol_basket(union_prices, lookback=30)` (raw) and a vol-targeted version (`vol_target(basket_returns, target_vol=0.10/365**0.5, lookback=30)` applied — mirror the B2 report's method) through `run_backtest(..., periods_per_year=365, fee_rate=0.0)`; compute total return / annualized / Sharpe / maxDD. Do the same for BTC B0 (buy-hold) + B1 (vol-target) over the **matched full-history window** and over the **fixed AVAX-limited window** (apples-to-apples vs the existing B2 report).
- [ ] **Step 3** — plausibility gate: metrics finite, non-degenerate, composition grows as expected, dynamic-basket-over-fixed-window ≈ the committed B2 report's numbers (sanity cross-check). Only then write `docs/research/04.phase3-benchmark-b2-dynamic-report.md`: the results tables (full-history + fixed-window), the composition-growth summary, and the **finding-1 read** — does the full-history dynamic basket (raw and/or vol-targeted) beat single-asset BTC risk-adjusted, and is B2's Phase-3 weakness structural or a window artifact.
- [ ] **Step 4 — commit** (`docs(benchmark): full-history dynamic-composition basket report + finding-1 verdict`).

### Task 3: closeout

**Files:** Modify `docs/iterations-history.md`; `docs/open-topics/*` (resolve T0007).

- [ ] **Step 1** — append the `## 2026-07-09 — iter-044: …` iterations-history entry (what landed: the dynamic basket + leak test; the finding-1 verdict + numbers; that it's a benchmark, not a registry trial).
- [ ] **Step 2** — flip T0007 → `resolved`: add a resolution note, `git mv docs/open-topics/T0007-dynamic-composition-basket.md docs/open-topics/archive/`, sync `docs/open-topics/README.md` (R&D Open → Resolved).
- [ ] **Step 3** — `uv run pre-commit run -a`; stage rewrites; commit (`docs: iter-044 closeout — dynamic basket finding-1 + resolve T0007`).
