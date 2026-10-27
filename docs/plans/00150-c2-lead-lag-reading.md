# C2 reading 1 — the BTC→alt lead-lag surface on `ohlc-15m` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One reading subject, `c2-lead-lag-reading`, that reads the gross lead-lag surface of spec 00150's 176 cells on the frozen 15m set and lands as reading 7 on `docs/reference/reading-ledger.jsonl`, its potential criterion fixed before its hash.

**Architecture:** The pure functions — returns, scale, moves, signals, grid mapping, forward returns, a cell's reads, the rank correlation — live in a new `cli/alpha/c2.py`, each proven on a fixture with a known answer. The subject in `cli/research/subjects.py` is built in two halves: the inputs half (the leader's signals and each follower's coverage, no forward return) that the data-gated basis case runs before the hash, and the computes half (the cells and the context rows) that runs before the hash over synthetic inputs alone. The run, the ledger line, the decisions-log entries, T0016 and the retirement follow the shape of iter-190's reading (plan 00145).

**Tech Stack:** Python 3.14, polars (the reader's frames, `rolling_std`), `statistics.correlation(method="ranked")` for Spearman, `cli.validation.spa.reality_check_pvalue` for the bootstrap p, pytest.

**Spec:** `docs/specs/00150-c2-lead-lag-reading-design.md`

## Global Constraints

- The hash rule (spec D7): before the spec's sha256 is taken, no program reads or computes any follower's forward return conditioned on a signal, any cell's means or `p`, or the context rows over the real set; the leader's returns, scale, moves and signal counts, and each follower's stamps and coverage, are allowed. The computes half runs before the hash over synthetic inputs alone.
- No change to any existing function: `cli/alpha/*` beyond the new module, `cli/validation/*`, `cli/data/*`, `cli/engine/*`, any record, reading or adopted artifact (spec D6).
- The constants, verbatim: `cost_round_trip` 0.012, `sigma_window` 96, `mean_block` 30, `n_resamples` 2000, `seed` 42; lags `(1, 4)`, thresholds `(1, 2)`, horizons `(1, 4)`, sides `("up", "down")`; the followers, in this order: `ADA/EUR`, `AVAX/EUR`, `DOGE/EUR`, `DOT/EUR`, `ETH/EUR`, `LINK/EUR`, `LTC/EUR`, `SOL/EUR`, `XRP/EUR`, `ETH/BTC`, `SOL/BTC`; the leader `BTC/EUR`; the step 15 minutes.
- A cell's name: `f"{follower}|L{lag}|th{threshold}|H{horizon}|{side}"`, e.g. `ETH/EUR|L1|th2|H4|up`.
- Commits: Conventional Commits, one subject per change; the message says what changed and the result line of the test command it names, run over the commit's own tree, pasted; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every commit ends with the two trailer lines the dispatch names.
- A comment or docstring stays only where a reader would do something differently without it, and has to be correct; a spec citation names the D-section.
- `tests/test_research_c2_lead_lag_reading_basis.py` is data-gated (`pytestmark = pytest.mark.data`, the literal-rooted `_DATA_ROOT` form `tests/skip_gates.py` admits); every other new test is not and runs in CI.
- The worktree is `.claude/worktrees/iter195`; `data/ohlc-15m` is linked into it by the controller for the data-gated steps alone (`ln -sn`, unlinked after).

## Review Focus

1. A follower's bar at a stamp the leader lacks (the basis: 649 across the eleven) — dropped from the grid, counted in `off_grid`, never shifting a close onto a neighbouring stamp. Pinned in Task 1's `test_on_grid_drops_a_follower_bar_the_leader_lacks`.
2. A leader gap inside a forward window (the basis: 3,002 non-15m steps) — the forward return is `None`, never computed across the gap. Pinned in Task 1's `test_forward_return_is_none_across_a_leader_gap`.
3. A `None` return inside the 96-bar scale window — the scale is `None`, and every signal at that bar is none (no threshold against a `None` scale). Pinned in Task 1's `test_scale_is_none_while_a_gap_sits_inside_its_window`.
4. A cell with fewer than 2 trades — `p` is `null`, the means `null` at 0 trades, no `ValidationError` escapes. Pinned in Task 1's `test_cell_reads_with_no_trade_and_with_one_trade`.
5. The entry-at-close convention's look-ahead — the one-bar-delay bound: on a planted lead the delayed read is at most the undelayed. Pinned in Task 1's `test_a_one_bar_delay_reads_no_more_than_entry_at_close`.

---

### Task 1: the pure functions in `cli/alpha/c2.py`

**Files:**
- Create: `cli/alpha/c2.py`
- Test: `tests/test_alpha_c2.py`

**Interfaces:**
- Produces, all in `cli/alpha/c2.py`:
  - `STEP = timedelta(minutes=15)`; `LAGS = (1, 4)`; `THRESHOLDS = (1, 2)`; `HORIZONS = (1, 4)`; `SIDES = ("up", "down")`; `COST_ROUND_TRIP = 0.012`; `SIGMA_WINDOW = 96`; `LEADER = "BTC/EUR"`; `FOLLOWERS = ("ADA/EUR", "AVAX/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR", "ETH/BTC", "SOL/BTC")`.
  - `log_returns(ts: list[datetime], close: list[float]) -> list[float | None]` — `ln(close[i]/close[i-1])` where `ts[i] - ts[i-1] == STEP`, else `None`; index 0 `None`.
  - `trailing_std(values: list[float | None], *, window: int = SIGMA_WINDOW) -> list[float | None]` — the sample standard deviation over the trailing `window` values ending at each index, `None` until `window` values are present or when any of them is `None` (polars `rolling_std(window_size=window, min_samples=window)` over a Float64 series with nulls).
  - `moves(returns: list[float | None], *, lag: int) -> list[float | None]` — the sum of the last `lag` returns ending at each index, `None` if any is `None` or fewer than `lag` exist.
  - `signals(moves_l: list[float | None], sigma: list[float | None], *, lag: int, threshold: float) -> list[int]` — `+1` where `moves_l[t] > threshold * sigma[t] * sqrt(lag)`, `-1` where `< -threshold * sigma[t] * sqrt(lag)`, else `0`; `0` where either is `None`.
  - `on_grid(grid: list[datetime], ts: list[datetime], close: list[float]) -> tuple[list[float | None], int, int]` — the follower's closes placed on the grid by exact stamp (`None` where absent), and `(on_grid, off_grid)` counts; refuses with `AlphaError` on a duplicate stamp in `grid`.
  - `forward_returns(grid: list[datetime], close_on_grid: list[float | None], *, horizon: int) -> list[float | None]` — `ln(close[t+horizon]/close[t])` when both closes are present, every one of the `horizon` steps from `t` is exactly `STEP`, and every intermediate close is present; else `None`; the last `horizon` indices `None`.
  - `cell_reads(signal: list[int], side: str, forward: list[float | None], years: list[int], *, cost: float = COST_ROUND_TRIP, mean_block: float = 30, n_resamples: int = 2000, seed: int = 42) -> dict` — the trades are the indices with `signal == +1` for `"up"`, `== -1` for `"down"`, and `forward` not `None`; gross `forward` for `up`, `-forward` for `down`; returns `{"per_year": {year: {"n", "mean_gross", "mean_net"}} over every year in `years`, "n", "mean_gross", "mean_net", "p"}` with `mean_*` `None` at `n` 0, `p` `None` at `n` < 2, else `reality_check_pvalue([[g - cost] for g in gross_in_index_order], mean_block=mean_block, n_resamples=n_resamples, seed=seed)["p_value"]`.
  - `rank_ic(x: list[float | None], y: list[float | None]) -> float | None` — Spearman over the indices where both are present, `statistics.correlation(xs, ys, method="ranked")`; `None` at fewer than 2 pairs or when either has no variance (`StatisticsError` caught).
  - `per_year(values: list[float | None], years: list[int]) -> dict[int, list[float]]` — the present values grouped by year, every year in `years` keyed.
  - `cell_name(follower: str, lag: int, threshold: int, horizon: int, side: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_alpha_c2.py
import math
from datetime import UTC, datetime, timedelta
import pytest
from cli.alpha.c2 import (STEP, cell_name, cell_reads, forward_returns, log_returns, moves, on_grid, per_year, rank_ic, signals, trailing_std)
from cli.alpha.errors import AlphaError

def _grid(n, start=datetime(2024, 1, 1, tzinfo=UTC)):
    return [start + i * STEP for i in range(n)]

def test_log_returns_are_none_at_index_0_and_across_a_non_15m_step():
    ts = _grid(3) + [_grid(3)[-1] + 2 * STEP]
    r = log_returns(ts, [100.0, 110.0, 121.0, 133.1])
    assert r[0] is None and r[3] is None
    assert r[1] == pytest.approx(math.log(1.1)) and r[2] == pytest.approx(math.log(1.1))

def test_trailing_std_is_the_sample_std_and_none_until_the_window_fills():
    vals = [None, 1.0, 2.0, 4.0, 8.0]
    s = trailing_std(vals, window=3)
    assert s[:3] == [None, None, None]
    assert s[3] == pytest.approx(1.5275252316519468)  # sample std of 1, 2, 4
    assert s[4] == pytest.approx(3.055050463303893)   # sample std of 2, 4, 8

def test_scale_is_none_while_a_gap_sits_inside_its_window():
    vals = [1.0, 2.0, None, 4.0, 5.0, 6.0]
    assert trailing_std(vals, window=3)[4] is None and trailing_std(vals, window=3)[5] is not None

def test_moves_sum_the_last_lag_returns_and_are_none_over_a_gap():
    r = [None, 0.1, 0.2, None, 0.3, 0.4]
    assert moves(r, lag=1)[1:3] == [0.1, 0.2]
    assert moves(r, lag=2)[2] == pytest.approx(0.3) and moves(r, lag=2)[4] is None and moves(r, lag=2)[5] == pytest.approx(0.7)

def test_signals_fire_beyond_threshold_times_sigma_times_sqrt_lag_on_either_side():
    m = [0.05, -0.05, 0.01, None, 0.05]
    sig = [0.02, 0.02, 0.02, 0.02, None]
    assert signals(m, sig, lag=4, threshold=1.0) == [1, -1, 0, 0, 0]  # 0.02*2 = 0.04 < 0.05
    assert signals(m, sig, lag=4, threshold=2.0) == [0, 0, 0, 0, 0]   # 0.02*2*2 = 0.08 > 0.05

def test_on_grid_drops_a_follower_bar_the_leader_lacks():
    grid = _grid(4)
    ts = [grid[0], grid[1], grid[1] + timedelta(minutes=7), grid[3]]
    closes, on, off = on_grid(grid, ts, [1.0, 2.0, 9.0, 4.0])
    assert closes == [1.0, 2.0, None, 4.0] and (on, off) == (3, 1)

def test_on_grid_refuses_a_duplicate_leader_stamp():
    g = _grid(3)
    with pytest.raises(AlphaError, match="duplicate"):
        on_grid(g + [g[-1]], g, [1.0, 1.0, 1.0])

def test_forward_return_is_none_across_a_leader_gap():
    grid = _grid(3) + [_grid(3)[-1] + 2 * STEP, _grid(3)[-1] + 3 * STEP]
    fwd = forward_returns(grid, [1.0, 2.0, 4.0, 8.0, 16.0], horizon=1)
    assert fwd[0] == pytest.approx(math.log(2)) and fwd[2] is None and fwd[3] == pytest.approx(math.log(2)) and fwd[4] is None
    assert forward_returns(grid, [1.0, 2.0, None, 8.0, 16.0], horizon=2)[0] is None  # an absent intermediate close

def test_cell_reads_with_no_trade_and_with_one_trade():
    years = [2024, 2024, 2025]
    none = cell_reads([0, 0, 0], "up", [0.1, 0.1, 0.1], years)
    assert none["n"] == 0 and none["mean_gross"] is None and none["p"] is None
    assert none["per_year"] == {2024: {"n": 0, "mean_gross": None, "mean_net": None}, 2025: {"n": 0, "mean_gross": None, "mean_net": None}}
    one = cell_reads([1, 0, 0], "up", [0.03, 0.1, 0.1], years)
    assert one["n"] == 1 and one["mean_gross"] == pytest.approx(0.03) and one["mean_net"] == pytest.approx(0.018) and one["p"] is None

def test_cell_reads_take_the_down_side_short_and_skip_an_absent_forward():
    years = [2024] * 4
    c = cell_reads([-1, -1, 1, -1], "down", [-0.02, None, 0.5, -0.04], years, n_resamples=50)
    assert c["n"] == 2 and c["mean_gross"] == pytest.approx(0.03) and c["mean_net"] == pytest.approx(0.018)
    assert 0.0 < c["p"] <= 1.0

def test_a_planted_lead_is_recovered_and_a_null_reads_zero():
    # Leader moves +1 at even bars; the follower's next bar return equals the leader's move: gross 0.05 a trade, net 0.038.
    years = [2024] * 200
    sig = [1 if i % 2 == 0 else 0 for i in range(200)]
    fwd = [0.05 if i % 2 == 0 else -0.05 for i in range(200)]
    planted = cell_reads(sig, "up", fwd, years, n_resamples=200)
    assert planted["n"] == 100 and planted["mean_gross"] == pytest.approx(0.05) and planted["p"] < 0.05
    null = cell_reads(sig, "up", [0.0] * 200, years, n_resamples=200)
    assert null["mean_gross"] == pytest.approx(0.0) and null["p"] >= 0.99

def test_a_one_bar_delay_reads_no_more_than_entry_at_close():
    # The planted lead above, read one bar after the signal: the delayed forward is the next bar's, which carries none of it.
    years = [2024] * 200
    sig = [1 if i % 2 == 0 else 0 for i in range(200)]
    fwd = [0.05 if i % 2 == 0 else -0.05 for i in range(200)]
    delayed = [0] + sig[:-1]
    assert cell_reads(delayed, "up", fwd, years, n_resamples=50)["mean_gross"] <= cell_reads(sig, "up", fwd, years, n_resamples=50)["mean_gross"]

def test_rank_ic_is_spearman_and_none_without_two_pairs_or_variance():
    assert rank_ic([1.0, 2.0, 3.0, None], [10.0, 30.0, 20.0, 5.0]) == pytest.approx(0.5)
    assert rank_ic([1.0, None], [1.0, 2.0]) is None
    assert rank_ic([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None

def test_per_year_groups_present_values_and_keys_every_year():
    assert per_year([1.0, None, 3.0], [2023, 2023, 2024]) == {2023: [1.0], 2024: [3.0]}

def test_cell_name():
    assert cell_name("ETH/EUR", 1, 2, 4, "up") == "ETH/EUR|L1|th2|H4|up"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_alpha_c2.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError` on `cli.alpha.c2`.

- [ ] **Step 3: Implement `cli/alpha/c2.py`** with the signatures in Interfaces; `trailing_std` through `pl.Series(values, dtype=pl.Float64).rolling_std(window_size=window, min_samples=window)` with `None` propagating (a null inside the window gives null); `cell_reads` builds the `[[g - cost]]` matrix in index order; `rank_ic` wraps `statistics.correlation(..., method="ranked")` and returns `None` on `statistics.StatisticsError`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_alpha_c2.py -q -p no:cacheprovider`
Expected: `15 passed`.

- [ ] **Step 5: Probe the two guards** — `on_grid`'s duplicate refusal (mutation: the `raise` removed; control: the message changed) through `-k duplicate_leader_stamp`, and `forward_returns`' gap arm (mutation: the step check removed; control: `horizon` read as 0) through `-k across_a_leader_gap`, each `infra/scripts/mutate-probe.sh --file cli/alpha/c2.py --control … --mutation … -- uv run pytest tests/test_alpha_c2.py -q -p no:cacheprovider -k <case>`; both must print `KILLED (control proven, …)`.

- [ ] **Step 6: Commit** — `feat(alpha): c2's pure functions — the 15m leader's scale, moves and signals, a follower's grid and forward returns, a cell's reads` with the test line and the two probe lines.

---

### Task 2: the reading subject `c2-lead-lag-reading` in `cli/research/subjects.py`

**Files:**
- Modify: `cli/research/subjects.py` — one block before `SUBJECTS` (`_C2ReadingInputs`, `_c2_reads`, `_c2_reading_inputs`, `_c2_reading_metrics`, `_build_c2_lead_lag_reading`, `_C2_READING_KEYS`), one `SUBJECTS` entry, one import line from `cli.alpha.c2`
- Modify: `README.md:380` — the `--subject` row gains `c2-lead-lag-reading` (C2's lead-lag reading; the frozen 15m set, whole)
- Test: `tests/test_research_c2_lead_lag_reading.py`

**Interfaces:**
- Consumes: Task 1's functions and constants.
- Produces:
  - `class _C2ReadingInputs(NamedTuple)`: `grid: list[datetime]`, `years: list[int]`, `leader: dict` (`bars`, `first_stamp`, `last_stamp`, `non_15m_steps`, `sigma_warm_index`), `returns: list[float | None]`, `sigma: list[float | None]`, `signals: dict[str, list[int]]` keyed `f"L{lag}|th{threshold}"` (the signed signal, both sides in one list), `followers: dict[str, dict]` (`closes: list[float | None]`, `bars`, `first_stamp`, `on_grid`, `off_grid`).
  - `_c2_reads(reader: ObservedReader, subject: str) -> dict[str, tuple[list[datetime], list[float]]]` — the twelve files read whole through `reader.read_series("ohlc-15m", relpath)` (`BTC/EUR/15.parquet`, `<A>/EUR/15.parquet`, `ETH/BTC/15.parquet`, `SOL/BTC/15.parquet`), a `PolarsError` a `SubjectError(f"ohlc-15m/{relpath}: {exc}")`.
  - `_c2_reading_inputs(reads: dict, subject: str) -> _C2ReadingInputs` — the grid is the leader's stamps; `AlphaError` from `on_grid` becomes `SubjectError`; a follower with `on_grid` 0 refuses (`SubjectError(f"{subject}: {follower} has no stamp on the leader's grid")`); `sigma_warm_index` the first index whose scale is not `None`, `-1` if none; `non_15m_steps` counts consecutive stamps whose difference is not `STEP`.
  - `_c2_reading_metrics(inputs: _C2ReadingInputs) -> dict` — `cells` (176, `cell_reads` per cell, the `per_year` keys stringified years), `context` (`{follower: {f"L{lag}|H{horizon}": {"rank_ic_per_year": {...}, "drift_per_year": {...}}}}`, the rank IC per year over `moves` and the forward returns via `per_year`, the drift the mean forward return per year), `signals` (`{f"L{lag}|th{threshold}|{side}": {"per_year": {...}, "total": n}}`), `followers` (coverage, no closes), `leader`, and the constants.
  - `_build_c2_lead_lag_reading(reader, dataset, window, as_of=None, accept_holes=False) -> dict` — refuses `as_of` and `window` with the spec D6 messages verbatim, then `_c2_reading_metrics(_c2_reading_inputs(_c2_reads(reader, subject), subject))`.
  - `_C2_READING_KEYS = frozenset({"cells", "context", "signals", "followers", "leader", "cost_round_trip", "sigma_window", "mean_block", "n_resamples", "seed"})`.
  - The `SUBJECTS` entry: `"c2-lead-lag-reading": Subject("c2-lead-lag-reading", (15,), _ASSETS, _build_c2_lead_lag_reading, spec="docs/specs/00150-c2-lead-lag-reading-design.md", metric_keys=_C2_READING_KEYS, seeds=(42,))` — no `verdict`, `family` or `n_trials`.

- [ ] **Step 1: Write the failing tests** — a synthetic reader: a class with `read_series(dataset, relpath)` returning a polars frame `{"ts", "close"}` from a dict of twelve synthetic series on a 400-bar 15m grid from 2023-12-01, each follower's closes a planted function of the leader's lagged move (the EUR alts follow the leader's last move with a known coefficient, `ETH/BTC` is flat); the leader's grid carries one 30-minute step at bar 200 and `LTC/EUR` lacks bar 50.

```python
def test_the_build_returns_exactly_the_declared_keys_and_176_cells():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    assert set(out) == subjects._C2_READING_KEYS and len(out["cells"]) == 176
    assert set(out["cells"]) == {cell_name(f, L, th, H, s) for f in FOLLOWERS for L in LAGS for th in THRESHOLDS for H in HORIZONS for s in SIDES}

def test_the_inputs_half_reads_no_forward_return():
    inputs = subjects._c2_reading_inputs(subjects._c2_reads(_Reader(), "c2-lead-lag-reading"), "c2-lead-lag-reading")
    assert set(inputs._fields) == {"grid", "years", "leader", "returns", "sigma", "signals", "followers"}
    assert inputs.leader["non_15m_steps"] == 1 and inputs.followers["LTC/EUR"]["off_grid"] == 0 and inputs.followers["LTC/EUR"]["on_grid"] == 399

def test_the_signals_keys_carry_both_sides_and_the_basis_shape():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    assert set(out["signals"]) == {f"L{L}|th{th}|{s}" for L in LAGS for th in THRESHOLDS for s in SIDES}
    assert all(set(v) == {"per_year", "total"} for v in out["signals"].values())

def test_a_planted_follower_reads_potential_and_a_flat_cross_reads_none():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    planted = out["cells"]["ETH/EUR|L1|th1|H1|up"]
    assert planted["mean_gross"] > 0.012 and planted["p"] < 0.05
    assert out["cells"]["ETH/BTC|L1|th1|H1|up"]["mean_gross"] == pytest.approx(0.0, abs=1e-12)

def test_as_of_and_window_are_refused_before_any_read():
    with pytest.raises(subjects.SubjectError, match="drop --as-of"):
        subjects._build_c2_lead_lag_reading(_CountingReader(), "ohlc-15m", None, as_of="2026-01-01")
    with pytest.raises(subjects.SubjectError, match="drop --window"):
        subjects._build_c2_lead_lag_reading(_CountingReader(), "ohlc-15m", ("2024-01-01", "2024-02-01"))
    # _CountingReader.read_series raises if called: neither refusal read a file.

def test_an_unreadable_file_names_its_relpath():
    with pytest.raises(subjects.SubjectError, match="ohlc-15m/SOL/BTC/15.parquet"):
        subjects._build_c2_lead_lag_reading(_Reader(broken="SOL/BTC/15.parquet"), "ohlc-15m", None)

def test_the_subject_is_registered_as_a_reading():
    s = subjects.SUBJECTS["c2-lead-lag-reading"]
    assert s.verdict is None and s.family is None and s.n_trials is None and s.intervals == (15,) and s.seeds == (42,)
    assert s.spec == "docs/specs/00150-c2-lead-lag-reading-design.md" and s.metric_keys == subjects._C2_READING_KEYS
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_research_c2_lead_lag_reading.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'cli.research.subjects' has no attribute '_build_c2_lead_lag_reading'`.

- [ ] **Step 3: Implement the block and the `SUBJECTS` entry**, the README row, with the refusal messages verbatim from spec D6: `"c2-lead-lag-reading evaluates the frozen 15m set whole, never the rolling dataset as of a day: drop --as-of"` and `"c2-lead-lag-reading reads the frozen 15m set whole: the scale's trailing day reaches back past any window's first stamp; drop --window"`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_research_c2_lead_lag_reading.py tests/test_alpha_c2.py -q -p no:cacheprovider`
Expected: `22 passed`.

- [ ] **Step 5: Run the subject-table readers** — `uv run pytest tests/test_research_subjects.py tests/test_retired_subjects.py tests/test_readme_subjects.py -q -p no:cacheprovider` (the files that exist among these; `infra/scripts/consumers.sh --direct cli/research/subjects.py README.md` lists them) under `-m "not slow and not data"`.
Expected: all pass.

- [ ] **Step 6: Probe** the two refusals through `-k as_of_and_window` (mutation: the `window` check removed; control: the message changed) — `KILLED`.

- [ ] **Step 7: Commit** — `feat(research): the reading subject c2-lead-lag-reading — spec 00150's 176 cells on the frozen 15m set, no rule, no slot` with the test lines and the probe line.

---

### Task 3: the data-gated basis test and the decisions-log entries before the hash

**Files:**
- Create: `tests/test_research_c2_lead_lag_reading_basis.py`
- Modify: `docs/research/10.phase4-decisions.md` (append two entries)
- Test: the new file (data-gated), `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py`

**Interfaces:**
- Consumes: `subjects._c2_reads`, `subjects._c2_reading_inputs`; `ObservedReader(_DATA_ROOT)` as `tests/test_research_b3_btc_overlay_basis.py` builds it.

- [ ] **Step 1: Write the data-gated basis case**, `pytestmark = pytest.mark.data`, the literal-rooted `_DATA_ROOT`, the figures copied from spec 00150's measured basis, never from a run:

```python
def test_the_inputs_half_reads_the_specs_measured_basis():
    reader = ObservedReader(_DATA_ROOT)
    inputs = subjects._c2_reading_inputs(subjects._c2_reads(reader, "c2-lead-lag-reading"), "c2-lead-lag-reading")
    assert inputs.leader == {"bars": 430_560, "first_stamp": "2013-09-10T23:45:00+00:00", "last_stamp": "2026-03-31T23:45:00+00:00", "non_15m_steps": 3_002, "sigma_warm_index": 2_831}
    assert {f: (v["bars"], v["first_stamp"], v["on_grid"], v["off_grid"]) for f, v in inputs.followers.items()} == FOLLOWER_BASIS  # the eleven rows of the spec's basis
    sig = inputs.signals  # the computes half is never called here: it is past the hash rule
    def n(key, side): return sum(1 for s in sig[key] if s == (1 if side == "up" else -1))
    assert n("L1|th1", "up") == 43_196 and n("L1|th1", "down") == 42_015
    assert n("L1|th2", "up") == 9_275 and n("L1|th2", "down") == 9_963
    assert n("L4|th1", "up") == 41_203 and n("L4|th1", "down") == 39_583
    assert n("L4|th2", "up") == 9_302 and n("L4|th2", "down") == 10_077
    per_year_2015_L4_th2_up = sum(1 for s, y in zip(sig["L4|th2"], inputs.years) if s == 1 and y == 2015)
    assert per_year_2015_L4_th2_up == 267
```

  `FOLLOWER_BASIS` is the dict of the spec's eleven follower rows, `first_stamp` as the ISO string with `+00:00`.

- [ ] **Step 2: Run it without the data linked** — Expected: `1 skipped` with the skip gate's reason (not a failure); then, the controller having linked `data/ohlc-15m`, run it — Expected: `1 passed` in under 3 minutes. (The implementer runs the unlinked form only and reports; the linked run is the controller's at Task 4.)

- [ ] **Step 3: Append the two decisions-log entries** to `docs/research/10.phase4-decisions.md`, the `[iter-195]` key, in the log's shape (question, 2–3 options with tradeoffs, `(Decision: N)`, the `Logged` line):
  1. `[iter-195] C2 opened on the owner's family pick — C2's first step, a no-slot reading of the gross lead-lag surface, the loop's pick under the owner's run instruction (Decision: 1)` — the three options of spec D1, verbatim in substance; the Logged line naming the owner's words of 2026-10-27 ("C2 — BTC→alt lead-lag on 15m (Recommended)"; "skip the questions, write the pre-registration. Ignore the wall clock time gate, but do not start a new task after 10:00Z") and spec 00150 D1.
  2. `[iter-195] C2's lead-lag reading's conventions, pinned by spec 00150 before its hash (Decision: 1)` — one option taken, the alternatives named: entry at the signal bar's close against a one-bar delay (D4); overlapping trades counted apart against a merged hold (D4); the √L scaling of the threshold (D3); the floor at 100 per complete year over 2015–2025 against every complete year (D5); Bonferroni over 176 against no correction (D5); gross against net in legs 1 and 2 (D5).

- [ ] **Step 4: Run the log's guards** — `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider`. Expected: all pass.

- [ ] **Step 5: Commit** — `docs(research): the two [iter-195] entries before spec 00150's hash, and C2's data-gated basis case` with both test lines (the basis case's `skipped` line named as the unlinked run).

---

### Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the run

- [ ] **Step 1: The gate** — the plan review closed (`zcrypto-plan-review`), the branch's reads closed with no open Critical or Important; `git status --porcelain` empty.
- [ ] **Step 2: The spec hash** — `sha256sum docs/specs/00150-c2-lead-lag-reading-design.md`, pasted; the spec never edited after.
- [ ] **Step 3: The develop check** — `git fetch origin develop && git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl; echo rc=$?` — `rc=0`, else STOP.
- [ ] **Step 4: Link the data and run the basis case** — `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-15m data/ohlc-15m`; `uv run pytest tests/test_research_c2_lead_lag_reading_basis.py -q -p no:cacheprovider` → `1 passed`.
- [ ] **Step 5: The notes, written before the run** (spec D7), to `.local/iter195/notes.txt`.
- [ ] **Step 6: The one run** — `uv run zcrypto research eval --subject c2-lead-lag-reading --dataset ohlc-15m --reading --iteration iter-195 --spec-hash <Step 2> --notes "$(cat .local/iter195/notes.txt)"`, backgrounded, its output to `.local/iter195/run.out`; no plain eval before or after.
- [ ] **Step 7: The ledger line's checks** — the last line of `docs/reference/reading-ledger.jsonl`: `reading_id` 7, `iteration` `iter-195`, `spec_hash` Step 2's, `attempt` `null`; `metrics.leader`, `metrics.followers` and `metrics.signals` equal to the basis's figures; 176 cells, every `p` `null` or in `(0, 1]`; its replay as the eval's `--replay` form the B4 reading used, if the command offers one, else the line's `record_hash` recomputed.
- [ ] **Step 8: Unlink the data** — `test -L data/ohlc-15m && unlink data/ohlc-15m`; the main checkout's `data/` listing read (13 entries).
- [ ] **Step 9: Read the criterion** (spec D5) off the line: the floor per cell over the complete years 2015–2025 the follower spans, then the three legs; the cells with potential, if any, named.
- [ ] **Step 10: Commit the line with its entry** — `docs/reference/reading-ledger.jsonl` and `docs/research/10.phase4-decisions.md`'s third entry, `[iter-195] BTC→alt lead-lag read on frozen ohlc-15m (reading 7)` in the `[iter-190]` reading entry's form: the subject, the set, the spec hash, the 176 cells' headline — how many cells the floor admits, how many clear each leg, the cells with potential (or none), the strongest cell's figures quoted unrounded — and `C2's next step after the lead-lag reading` as the fourth entry: a cell with potential → trial 1 pre-registered in a new spec; none → the family call is the owner's (hold or close), nothing started before their word. Message `docs(research): reading 7 — C2's lead-lag surface on ohlc-15m; [iter-195] its entry and C2's next step`.

---

### Task 5: T0016, the retirement and the index

**Files:**
- Modify: `docs/open-topics/T0016-bucket-b-c-alpha-families.md` — `ripe_when:`'s C2 clause ("a tick catalog exists") replaced by "the `[iter-NNN] C2's next step after the lead-lag reading` entry's step"; a `## Findings so far` bullet for reading 7 (its headline figures, from the ledger line); a `## Done so far` bullet "C2 opened (iter-195, spec/plan 00150) on the owner's pick of 2026-10-27 …: the module `cli/alpha/c2.py`, the subject `c2-lead-lag-reading`, the data-gated basis test …; reading 7 …; the subject retired."
- Modify: `tests/retired_subjects.py` — `"c2-lead-lag-reading"` added under a `# C2's reading.` comment.
- Modify: `docs/open-topics/README.md` — re-rendered by `uv run python infra/scripts/topics-index.py` (the `ripe_when` moved).

- [ ] **Step 1: Edit the three files** as above.
- [ ] **Step 2: Run** `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_retired_subjects.py -q -p no:cacheprovider`. Expected: all pass.
- [ ] **Step 3: Commit** — `docs(topics): T0016 carries C2's opening and reading 7; c2-lead-lag-reading retired; the index re-rendered`.

---

### Task 6 (the controller's): the change-index row, the reads and the PR

- [ ] **Step 1:** `open-pr` Steps 1, 2 and 4 — title `feat(research): iter-195 — C2's lead-lag surface read on ohlc-15m (reading 7)` (measured ≤ 72), the row `| #<n> | <date> | <title> | iter-195 | 00150 | T0016 |`, committed.
- [ ] **Step 2:** the reads — `pre-review` over `develop..HEAD`, folds by `fold-check`, `review`, `re-review` on a fix range — each on Opus, model named.
- [ ] **Step 3:** the push, the PR through `open-pr` (body: Summary; Spec / Plan naming 00150 and T0016; the read line; `## Changes`; `## Test plan` with every result line pasted; `## Reads`; the reading's headline and C2's next step under `## Changes`), the CI watch, `merge-pr` when green.
- [ ] **Step 4:** the memo's T0016 item and the coordination table; the reads archived to `.local/reads-archive/research/iter-195-c2-lead-lag/`; the worktree removed.
