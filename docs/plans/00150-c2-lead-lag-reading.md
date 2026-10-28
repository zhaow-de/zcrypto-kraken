# C2 reading 1 — the BTC→alt lead-lag surface on `ohlc-15m` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One reading subject, `c2-lead-lag-reading`, that reads the gross lead-lag surface of spec 00150's 176 cells on the frozen 15m set and lands as reading 7 on `docs/reference/reading-ledger.jsonl`, its potential criterion fixed before its hash.

**Architecture:** The pure functions — returns, scale, moves, signals, grid mapping, forward returns, a cell's reads, the rank correlation — live in a new `cli/alpha/c2.py`, each proven on a fixture with a known answer. The subject in `cli/research/subjects.py` is built in two halves: the inputs half (the leader's signals and each follower's coverage, no forward return) that the data-gated basis case runs before the hash, and the computes half (the cells and the context rows) that runs before the hash over synthetic inputs alone. The run, the ledger line, the decisions-log entries, T0016 and the retirement follow the shape of iter-190's reading (plan 00145).

**Tech Stack:** Python 3.14, polars (the reader's frames, `rolling_std`), `statistics.correlation(method="ranked")` for Spearman, `cli.validation.spa.reality_check_pvalue` for the bootstrap p, pytest.

**Spec:** `docs/specs/00150-c2-lead-lag-reading-design.md`

## Global Constraints

- The hash rule (spec D7): before the spec's sha256 is taken, no program reads or computes any follower's forward return conditioned on a signal, any cell's means or `p`, or the context rows over the real set; the leader's returns, scale, moves and signal counts, and each follower's stamps and coverage, are allowed. The computes half runs before the hash over synthetic inputs alone.
- No change to any existing function: `cli/alpha/*` beyond the new module, `cli/validation/*`, `cli/data/*`, `cli/engine/*`, any record, reading or adopted artifact (spec D6).
- The constants, verbatim: `cost_round_trip` 0.012, `sigma_window` 96, `mean_block` 30, `n_resamples` 4000, `seed` 42; lags `(1, 4)`, thresholds `(1, 2)`, horizons `(1, 4)`, sides `("up", "down")`; the followers, in this order: `ADA/EUR`, `AVAX/EUR`, `DOGE/EUR`, `DOT/EUR`, `ETH/EUR`, `LINK/EUR`, `LTC/EUR`, `SOL/EUR`, `XRP/EUR`, `ETH/BTC`, `SOL/BTC`; the leader `BTC/EUR`; the step 15 minutes.
- A cell's name: `f"{follower}|L{lag}|th{threshold}|H{horizon}|{side}"`, e.g. `ETH/EUR|L1|th2|H4|up`.
- Commits: Conventional Commits, one subject per change; the message says what changed and the result line of the test command it names, run over the commit's own tree, pasted; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every commit ends with the two trailer lines the dispatch names.
- A comment or docstring stays only where a reader would do something differently without it, and has to be correct; a spec citation names the D-section.
- `tests/test_research_c2_lead_lag_reading_basis.py` is data-gated as `tests/test_research_b4_leg_reading_basis.py` is — `pytestmark = pytest.mark.data`, the literal-rooted `_DATA_ROOT` form `tests/skip_gates.py` admits, a `nothing_found_under` skip gate whose reason names `data/`, and `_DATA_ROOT == research_command._DATA_ROOT` as the case's first assertion; every other new test is not and runs in CI.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter195`. A frozen set is linked into a checkout — by the controller into this worktree or Task 4's scratch one, by a reader into its own — for a data-gated step alone, both paths absolute and with `-T`, so a destination that is already a directory refuses the link instead of taking it inside: `ln -snT /home/zhaow/Projects/zcrypto-kraken/data/<set> <checkout>/data/<set>`; it is removed by `test -L <checkout>/data/<set> && unlink <checkout>/data/<set>`, never `rm`; each its own call, and the main checkout's `data/` listing read after the last removal (13 entries). `<set>` is `ohlc-15m`, with `ohlc-full` beside it wherever a replay runs, whose skip gate reads it.
- **Probes** — the tier is `full`, so each new test function is a guard probed through its own node id, on a committed tree (`git status --porcelain` empty: `infra/scripts/mutate-probe.sh` refuses a dirty tree and restores by `git checkout`), each row its own call after the previous verdict is read: `infra/scripts/mutate-probe.sh --file <the row's file> --control '<sed>' --mutation '<sed>' -- uv run pytest <the case's node id> -q -p no:cacheprovider`, each printing `KILLED (control proven, …)`. Every mutation substitutes the condition, value or operand its row names on one line and deletes none, so the module still imports and every name it uses stays defined; before each row, `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. A mutation in `cli/research/subjects.py`, whose other builders hold the same lines, carries its own function's address, `/^def <name>(/,/^def /`, or the `SUBJECTS` entry's; a pattern holding `'` writes it as `.`. Every control renames a `def` the case reaches, `s/^def <name>(/def <name>_renamed(/`, so the case fails at import or at its call. The verdict lines, each with its command, go in the next commit's message (no amend).

## Review Focus

1. A follower's bar at a stamp the leader lacks (the basis: 649 across the eleven) — dropped from the grid, counted in `off_grid`, never shifting a close onto a neighbouring stamp. Pinned in Task 1's `test_on_grid_drops_a_follower_bar_the_leader_lacks`.
2. A leader gap inside a forward window (the basis: 3,002 non-15m steps) — the forward return is `None`, never computed across the gap. Pinned in Task 1's `test_forward_return_is_none_across_a_leader_gap`.
3. A `None` return inside the 96-bar scale window — the scale is `None`, and every signal at that bar is none (no threshold against a `None` scale). Pinned in Task 1's `test_scale_is_none_while_a_gap_sits_inside_its_window` (the scale) and `test_signals_fire_beyond_threshold_times_sigma_times_sqrt_lag_on_either_side` (no signal against a `None` scale).
4. A cell with fewer than 2 trades — no `p` key, no mean key at 0 trades, never a `null`, which the registry refuses, and no `ValidationError` escapes. Pinned in Task 1's `test_cell_reads_with_no_trade_and_with_one_trade` and Task 2's `test_the_metrics_hold_only_leaves_the_registry_stores`.
5. A trade's alignment — a trade at signal index `t` reads `forward[t]`, never a neighbour's: the planted lead's signals moved one bar read the opposite bars. Pinned in Task 1's `test_a_trade_reads_the_forward_return_at_its_own_signal_index`.
6. The context rows' pairing — a year's rank IC pairs each move with its own stamp's forward return, never two lists grouped by year apart. Pinned in Task 2's `test_the_context_rows_pair_each_move_with_its_own_forward_return`.
7. A per-year read files each value under the year of its own grid index, and a net read subtracts the cost — the members, each pinned: a cell's per-year `n`, `mean_gross` and `mean_net`, a trade under its signal bar's year and a signal whose forward return is absent left uncounted, and the bootstrap's rows `g − cost`, in Task 1's `test_cell_reads_file_each_trade_under_its_own_bars_year_and_bootstrap_the_net`; `per_year`'s strict zip, which refuses a list off the grid's index, in `test_per_year_groups_present_values_keys_every_year_and_refuses_unequal_lengths`; the span's `mean_net` in `test_cell_reads_with_no_trade_and_with_one_trade`; the signals' per-year counts in Task 2's `test_the_signals_keys_carry_both_sides_and_the_basis_shape`; the context's rank IC and drift per year in Task 2's `test_the_context_rows_pair_each_move_with_its_own_forward_return`.
8. A key names the coordinates its read was taken at — in the fixture the leader's L1 and L4 masks differ, as do its th1 and th2 masks at L4, and an EUR alt's H4 forward returns differ from its H1 ones, so a crossed loop variable moves a pinned figure; the members, each pinned in Task 2: a cell's follower, lag, threshold, horizon and side (`test_each_cell_is_read_at_its_own_lag_threshold_and_horizon`, the planted cell and the flat cross in `test_a_planted_follower_reads_potential_and_a_flat_cross_reads_none`, the empty `down` cell in `test_the_metrics_hold_only_leaves_the_registry_stores`); a context row's lag and horizon, through its move and its forward return each, in `test_the_context_rows_pair_each_move_with_its_own_forward_return`, and its key set in `test_the_build_returns_exactly_the_declared_keys_and_176_cells`; a signal count's lag, threshold and side in `test_the_signals_keys_carry_both_sides_and_the_basis_shape`.
9. Everything Task 4 checks of the subject after the hash — the series Step 6's command requires and the build's figures Step 7 checks — is read by a Task 2 case before it; the members, each pinned: the entry's declared assets, which the command's required-series check reads, in `test_the_subject_is_registered_as_a_reading`; the keys, the cells' names, the context's rows and the constants, and the metrics' `leader` and `followers` against the fixture's `LEADER_COVERAGE` and `FOLLOWER_COVERAGE`, in `test_the_build_returns_exactly_the_declared_keys_and_176_cells`; the `signals` in `test_the_signals_keys_carry_both_sides_and_the_basis_shape`; a cell's every year keyed and `p` absent at 0 trades in `test_the_metrics_hold_only_leaves_the_registry_stores`, `p` present in `test_a_planted_follower_reads_potential_and_a_flat_cross_reads_none`. The labels are the command's own.
10. The inputs half stores nothing beyond Task 2's Interfaces, the hash rule's split between the halves (spec D7) — every container of `_C2ReadingInputs` whose keys the build chooses is pinned in `test_the_inputs_half_reads_no_forward_return`: its fields' names, `leader` whole, each follower's entry whole beside its `closes`, and `signals`' keys.


---

### Task 1: the pure functions in `cli/alpha/c2.py`

**Files:**
- Create: `cli/alpha/c2.py`
- Test: `tests/test_alpha_c2.py`

**Interfaces:**
- Produces, all in `cli/alpha/c2.py`:
  - `STEP = timedelta(minutes=15)`; `LAGS = (1, 4)`; `THRESHOLDS = (1, 2)`; `HORIZONS = (1, 4)`; `SIDES = ("up", "down")`; `COST_ROUND_TRIP = 0.012`; `SIGMA_WINDOW = 96`; `MEAN_BLOCK = 30`; `N_RESAMPLES = 4000`; `SEED = 42`; `LEADER = "BTC/EUR"`; `FOLLOWERS = ("ADA/EUR", "AVAX/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR", "ETH/BTC", "SOL/BTC")`.
  - `log_returns(ts: list[datetime], close: list[float]) -> list[float | None]` — `ln(close[i]/close[i-1])` where `ts[i] - ts[i-1] == STEP`, else `None`; index 0 `None`.
  - `trailing_std(values: list[float | None], *, window: int = SIGMA_WINDOW) -> list[float | None]` — the sample standard deviation over the trailing `window` values ending at each index, `None` until `window` values are present or when any of them is `None` (polars `rolling_std(window_size=window, min_samples=window)` over a Float64 series with nulls).
  - `moves(returns: list[float | None], *, lag: int) -> list[float | None]` — the sum of the last `lag` returns ending at each index, `None` if any is `None` or fewer than `lag` exist.
  - `signals(moves_l: list[float | None], sigma: list[float | None], *, lag: int, threshold: float) -> list[int]` — `+1` where `moves_l[t] > threshold * sigma[t] * sqrt(lag)`, `-1` where `< -threshold * sigma[t] * sqrt(lag)`, else `0`; `0` where either is `None`.
  - `on_grid(grid: list[datetime], ts: list[datetime], close: list[float]) -> tuple[list[float | None], int, int]` — the follower's closes placed on the grid by exact stamp (`None` where absent), and `(on_grid, off_grid)` counts; refuses with `AlphaError` on a duplicate stamp in `grid`.
  - `forward_returns(grid: list[datetime], close_on_grid: list[float | None], *, horizon: int) -> list[float | None]` — `ln(close[t+horizon]/close[t])` when both closes are present, every one of the `horizon` steps from `t` is exactly `STEP`, and every intermediate close is present; else `None`; the last `horizon` indices `None`.
  - `cell_reads(signal: list[int], side: str, forward: list[float | None], years: list[int], *, cost: float = COST_ROUND_TRIP, mean_block: float = MEAN_BLOCK, n_resamples: int = N_RESAMPLES, seed: int = SEED) -> dict` — the trades are the indices with `signal == +1` for `"up"`, `== -1` for `"down"`, and `forward` not `None`; gross `forward` for `up`, `-forward` for `down`; returns `{"per_year": {str(year): {"n", "mean_gross", "mean_net"}} over every year in `years`, "n", "mean_gross", "mean_net", "p"}` with the `mean_*` keys absent at `n` 0, in `per_year` and over the span, and `p` absent at `n` < 2, else `reality_check_pvalue([[g - cost] for g in gross_in_index_order], mean_block=mean_block, n_resamples=n_resamples, seed=seed)["p_value"]` — never a `None` value, since the registry refuses a `null` leaf (spec D6).
  - `rank_ic(x: list[float | None], y: list[float | None]) -> float | None` — Spearman over the indices where both are present, `statistics.correlation(xs, ys, method="ranked")`; `None` at fewer than 2 pairs or when either has no variance (`StatisticsError` caught).
  - `per_year(values: list[float | None], years: list[int]) -> dict[str, list[float]]` — the present values grouped by year, keyed `str(year)`, every year in `years` keyed; `values` and `years` zipped with `strict=True`, so a list off the grid's index — a cell's trades against the grid's years — raises `ValueError`.
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
    assert forward_returns(grid, [1.0, None, 4.0, 8.0, 16.0], horizon=2)[0] is None  # both ends present, 15m steps, the close between absent

def test_cell_reads_with_no_trade_and_with_one_trade():
    years = [2024, 2024, 2025]
    none = cell_reads([0, 0, 0], "up", [0.1, 0.1, 0.1], years)
    assert none == {"per_year": {"2024": {"n": 0}, "2025": {"n": 0}}, "n": 0}
    one = cell_reads([1, 0, 0], "up", [0.03, 0.1, 0.1], years)
    assert one["n"] == 1 and one["mean_gross"] == pytest.approx(0.03) and one["mean_net"] == pytest.approx(0.018) and "p" not in one
    assert one["per_year"]["2025"] == {"n": 0}

def test_cell_reads_take_the_down_side_short_and_skip_an_absent_forward():
    years = [2024] * 4
    c = cell_reads([-1, -1, 1, -1], "down", [-0.02, None, 0.5, -0.04], years, n_resamples=50)
    assert c["n"] == 2 and c["mean_gross"] == pytest.approx(0.03) and c["mean_net"] == pytest.approx(0.018)
    assert 0.0 < c["p"] <= 1.0

def test_cell_reads_file_each_trade_under_its_own_bars_year_and_bootstrap_the_net():
    c = cell_reads([0, 1, 1, 1, 1], "up", [0.5, 0.01, 0.03, None, 0.05], [2023, 2024, 2024, 2025, 2025], n_resamples=50)
    assert c["per_year"]["2023"] == {"n": 0}
    assert c["per_year"]["2024"] == pytest.approx({"n": 2, "mean_gross": 0.02, "mean_net": 0.008})
    assert c["per_year"]["2025"] == pytest.approx({"n": 1, "mean_gross": 0.05, "mean_net": 0.038})
    below = cell_reads([1] * 40, "up", [0.004, 0.008] * 20, [2024] * 40, n_resamples=50)
    assert below["mean_gross"] == pytest.approx(0.006) and below["p"] > 0.5

def test_a_planted_lead_is_recovered_and_a_null_reads_zero():
    # Leader moves +1 at even bars; the follower's next bar return equals the leader's move: gross 0.05 a trade, net 0.038.
    years = [2024] * 200
    sig = [1 if i % 2 == 0 else 0 for i in range(200)]
    fwd = [0.05 if i % 2 == 0 else -0.05 for i in range(200)]
    planted = cell_reads(sig, "up", fwd, years, n_resamples=200)
    assert planted["n"] == 100 and planted["mean_gross"] == pytest.approx(0.05) and planted["p"] < 0.05
    null = cell_reads(sig, "up", [0.0] * 200, years, n_resamples=200)
    assert null["mean_gross"] == pytest.approx(0.0) and null["p"] >= 0.99

def test_a_trade_reads_the_forward_return_at_its_own_signal_index():
    # The planted lead above with every signal one bar later: each trade then reads an odd bar's -0.05, never its neighbour's.
    years = [2024] * 200
    sig = [1 if i % 2 == 0 else 0 for i in range(200)]
    fwd = [0.05 if i % 2 == 0 else -0.05 for i in range(200)]
    delayed = [0] + sig[:-1]
    assert cell_reads(delayed, "up", fwd, years, n_resamples=50)["mean_gross"] == pytest.approx(-0.05)

def test_rank_ic_is_spearman_and_none_without_two_pairs_or_variance():
    assert rank_ic([1.0, 2.0, 3.0, None], [10.0, 30.0, 20.0, 5.0]) == pytest.approx(0.5)
    assert rank_ic([1.0, None], [1.0, 2.0]) is None
    assert rank_ic([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None

def test_per_year_groups_present_values_keys_every_year_and_refuses_unequal_lengths():
    assert per_year([1.0, None, 3.0], [2023, 2023, 2024]) == {"2023": [1.0], "2024": [3.0]}
    assert per_year([None, 3.0], [2023, 2024]) == {"2023": [], "2024": [3.0]}
    with pytest.raises(ValueError):
        per_year([1.0], [2023, 2024])

def test_cell_name():
    assert cell_name("ETH/EUR", 1, 2, 4, "up") == "ETH/EUR|L1|th2|H4|up"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_alpha_c2.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError` on `cli.alpha.c2`.

- [ ] **Step 3: Implement `cli/alpha/c2.py`** with the signatures in Interfaces; `trailing_std` through `pl.Series(values, dtype=pl.Float64).rolling_std(window_size=window, min_samples=window)` with `None` propagating (a null inside the window gives null); `cell_reads` builds the `[[g - cost]]` matrix in index order; `rank_ic` wraps `statistics.correlation(..., method="ranked")` and returns `None` on `statistics.StatisticsError`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_alpha_c2.py -q -p no:cacheprovider`
Expected: `16 passed`.

- [ ] **Step 5: Commit** — `feat(alpha): c2's pure functions — the 15m leader's scale, moves and signals, a follower's grid and forward returns, a cell's reads` with the test line.

- [ ] **Step 6: Probe each case on Step 5's committed tree**, in the Global Constraints' probe form, `--file cli/alpha/c2.py`, the node id `tests/test_alpha_c2.py::<case>`; the eighteen verdict lines, each with its command, appended as each is read to `.local/iter195/probes-task-1.txt`, started empty (`mkdir -p .local/iter195 && : > .local/iter195/probes-task-1.txt` first) — ignored, so the next row's clean-tree check holds — which Task 2 Step 6's message carries whole. The rows, each a case and the mutation it must kill:
  - `test_log_returns_are_none_at_index_0_and_across_a_non_15m_step` — the return's 15-minute step comparison made `True`;
  - `test_trailing_std_is_the_sample_std_and_none_until_the_window_fills` — `min_samples=window` written `min_samples=window - 1`;
  - `test_scale_is_none_while_a_gap_sits_inside_its_window` — the series' nulls filled with `0.0` (`.fill_null(0.0)`) before `rolling_std`;
  - `test_moves_sum_the_last_lag_returns_and_are_none_over_a_gap` — a `None` inside the lag's window summed as `0.0`;
  - `test_signals_fire_beyond_threshold_times_sigma_times_sqrt_lag_on_either_side` — the up side's `sqrt(lag)` written `1`;
  - `test_on_grid_drops_a_follower_bar_the_leader_lacks` — the off-grid count's increment written `0`;
  - `test_on_grid_refuses_a_duplicate_leader_stamp` — the duplicate's condition made `False`;
  - `test_forward_return_is_none_across_a_leader_gap`, two rows — the step check made `True`; then the intermediate-close check narrowed to the closes at `t` and `t + horizon`;
  - `test_cell_reads_with_no_trade_and_with_one_trade` — the `p` bound `>= 2` written `>= 1`, so the utility's `ValidationError` escapes at one trade;
  - `test_cell_reads_take_the_down_side_short_and_skip_an_absent_forward` — the down side's gross left un-negated;
  - `test_cell_reads_file_each_trade_under_its_own_bars_year_and_bootstrap_the_net`, two rows — the bootstrap's rows written `[g]`, the gross; then each trade filed under `years[0]`;
  - `test_a_planted_lead_is_recovered_and_a_null_reads_zero` — the bootstrap's rows written `[cost - g]`;
  - `test_a_trade_reads_the_forward_return_at_its_own_signal_index` — each trade's gross read at `forward[i - 1]`;
  - `test_rank_ic_is_spearman_and_none_without_two_pairs_or_variance` — the caught `statistics.StatisticsError` written `ZeroDivisionError`;
  - `test_per_year_groups_present_values_keys_every_year_and_refuses_unequal_lengths` — `per_year`'s `strict=True` written `strict=False`;
  - `test_cell_name` — the lag and the horizon swapped in the name.

---

### Task 2: the reading subject `c2-lead-lag-reading` in `cli/research/subjects.py`

**Files:**
- Modify: `cli/research/subjects.py` — one block before `SUBJECTS` (`_C2ReadingInputs`, `_c2_reads`, `_c2_reading_inputs`, `_c2_reading_metrics`, `_build_c2_lead_lag_reading`, `_C2_READING_KEYS`), one `SUBJECTS` entry, one import line from `cli.alpha.c2`
- Modify: `README.md:380` — the `--subject` row gains `c2-lead-lag-reading` (C2's lead-lag reading; the frozen 15m set, whole)
- Modify: `tests/test_research_command.py` — `_c2_dataset` after `_declared_series`, and the `_CONTRACT_DATASETS` entry `"c2-lead-lag-reading": _c2_dataset`: the file parametrises nine rows over every `SUBJECTS` entry, and its fallback fixture writes neither cross
- Test: `tests/test_research_c2_lead_lag_reading.py`

**Interfaces:**
- Consumes: Task 1's functions and constants.
- Produces:
  - `class _C2ReadingInputs(NamedTuple)`: `grid: list[datetime]`, `years: list[int]`, `leader: dict` (`bars`, `first_stamp`, `last_stamp`, `non_15m_steps`, `sigma_warm_index`), `returns: list[float | None]`, `sigma: list[float | None]`, `signals: dict[str, list[int]]` keyed `f"L{lag}|th{threshold}"` (the signed signal, both sides in one list), `followers: dict[str, dict]` (`closes: list[float | None]`, `bars`, `first_stamp`, `on_grid`, `off_grid`); every stamp in `leader` and `followers` is its epoch seconds, `int(ts.timestamp())`, the form the metrics carry (spec D6).
  - `_c2_reads(reader: ObservedReader, dataset: str, subject: str) -> dict[str, tuple[list[datetime], list[float]]]` — keyed `LEADER` and each of `FOLLOWERS`, the twelve files read whole through `reader.read_series(dataset, relpath)` (`BTC/EUR/15.parquet`, `<A>/EUR/15.parquet`, `ETH/BTC/15.parquet`, `SOL/BTC/15.parquet`); a `pl.exceptions.PolarsError` or an `OSError` — a missing file raises `FileNotFoundError` — a `SubjectError(f"{dataset}/{relpath}: {exc}")`; a close that is `None` or not above 0 a `SubjectError(f"{_b2_over(subject, None)}: {dataset}/{relpath}: a close that is not a positive number at {ts.isoformat()}")`, so no log ratio meets one.
  - `_c2_reading_inputs(reads: dict, subject: str) -> _C2ReadingInputs` — the grid is the leader's stamps; `on_grid`'s `AlphaError` is left to the build's wrap; a follower with `on_grid` 0 refuses (`SubjectError(f"{subject}: {follower} has no stamp on the leader's grid")`); `sigma_warm_index` the first index whose scale is not `None`, `-1` if none; `non_15m_steps` counts consecutive stamps whose difference is not `STEP`.
  - `_c2_reading_metrics(inputs: _C2ReadingInputs) -> dict` — `cells` (176, `cell_reads` per cell as it returns), `context` (`{follower: {f"L{lag}|H{horizon}": {"rank_ic_per_year": {...}, "drift_per_year": {...}}}}`: year `y`'s rank IC is `rank_ic` of the moves masked to `None` outside `y` against the whole forward-return list, so each move meets its own stamp's forward return — never the two lists each through `per_year` — and `y` is keyed only where `rank_ic` returns a value; the drift is the mean of `per_year`'s forward returns, a year keyed only where it holds one), `signals` (`{f"L{lag}|th{threshold}|{side}": {"per_year": {str(year): n} over every year in `years`, "total": n}}`), `followers` (coverage, no closes), `leader`, and the constants under `_C2_READING_KEYS`' names, each from Task 1's constant (`COST_ROUND_TRIP`, `SIGMA_WINDOW`, `MEAN_BLOCK`, `N_RESAMPLES`, `SEED`); every year key `str(year)`, every leaf a builtin `int` or `float`.
  - `_build_c2_lead_lag_reading(reader, dataset, window, as_of=None, accept_holes=False) -> dict` — refuses `as_of` and `window` with the spec D6 messages verbatim, before any read, then `_c2_reading_metrics(_c2_reading_inputs(_c2_reads(reader, dataset, subject), subject))` inside `except (AlphaError, ValidationError) as exc: raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc`, `_build_b4_leg_reading`'s wrap.
  - `_C2_READING_KEYS = frozenset({"cells", "context", "signals", "followers", "leader", "cost_round_trip", "sigma_window", "mean_block", "n_resamples", "seed"})`.
  - The `SUBJECTS` entry: `"c2-lead-lag-reading": Subject("c2-lead-lag-reading", (15,), _ASSETS, _build_c2_lead_lag_reading, spec="docs/specs/00150-c2-lead-lag-reading-design.md", metric_keys=_C2_READING_KEYS, seeds=(SEED,))` — no `verdict`, `family` or `n_trials`.

- [ ] **Step 1: Write the failing tests** — the synthetic reader and its twelve series in the fence's head; the grid crosses a year so `per_year`, the absent keys and the context's years each meet a year with nothing in it.

```python
# tests/test_research_c2_lead_lag_reading.py
import math
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from cli.alpha.c2 import FOLLOWERS, HORIZONS, LAGS, LEADER, SIDES, STEP, THRESHOLDS, cell_name
from cli.registry.record import validate_metrics
from cli.research import subjects

SUBJECT = "c2-lead-lag-reading"
# 2023 holds the 96 bars before the leader's scale warms, 2024 the other 304.
START, BARS, GAP_AT, LTC_MISSES, SOL_BTC_FROM = datetime(2023, 12, 31, tzinfo=UTC), 400, 200, 50, 96
# The coverage spec D6's `leader` and `followers` keys carry for the series below: the one 30-minute step puts the last
# stamp BARS steps after the first, LTC/EUR is one bar short and SOL/BTC opens at bar SOL_BTC_FROM.
LEADER_COVERAGE = {"bars": BARS, "first_stamp": int(START.timestamp()), "last_stamp": int((START + BARS * STEP).timestamp()), "non_15m_steps": 1, "sigma_warm_index": 96}
FOLLOWER_COVERAGE = {f: {"bars": BARS, "first_stamp": int(START.timestamp()), "on_grid": BARS, "off_grid": 0} for f in FOLLOWERS} | {
    "LTC/EUR": {"bars": BARS - 1, "first_stamp": int(START.timestamp()), "on_grid": BARS - 1, "off_grid": 0},
    "SOL/BTC": {"bars": BARS - SOL_BTC_FROM, "first_stamp": int((START + SOL_BTC_FROM * STEP).timestamp()), "on_grid": BARS - SOL_BTC_FROM, "off_grid": 0},
}

def _series() -> dict[str, tuple[list[datetime], list[float]]]:
    """The leader moves 0.02 at every tenth bar and 0.001 either way between, its grid one 30-minute step at bar GAP_AT;
    each EUR alt's next 15m return is twice the leader's last, LTC/EUR without bar LTC_MISSES; ETH/BTC is flat, and SOL/BTC
    flat from bar SOL_BTC_FROM."""
    ts = [START + (i + (i >= GAP_AT)) * STEP for i in range(BARS)]
    r = [0.0] + [0.02 if i % 10 == 0 else (0.001 if i % 2 else -0.001) for i in range(1, BARS)]
    leader, alt = [100.0], [10.0]
    for i in range(1, BARS):
        leader.append(leader[-1] * math.exp(r[i]))
        alt.append(alt[-1] * math.exp(2 * r[i - 1]))
    out = {LEADER: (ts, leader), "ETH/BTC": (ts, [0.05] * BARS), "SOL/BTC": (ts[SOL_BTC_FROM:], [0.002] * (BARS - SOL_BTC_FROM))}
    out["LTC/EUR"] = (ts[:LTC_MISSES] + ts[LTC_MISSES + 1 :], alt[:LTC_MISSES] + alt[LTC_MISSES + 1 :])
    return {f: (ts, alt) for f in FOLLOWERS} | out

class _Reader:
    def __init__(self, series=None, broken=None):
        self.series, self.broken = series or _series(), broken

    def read_series(self, dataset, relpath, window=None):
        if relpath == self.broken:
            raise FileNotFoundError(relpath)
        ts, close = self.series[relpath.removesuffix("/15.parquet")]
        return pl.DataFrame({"ts": ts, "close": close})

class _RaisingReader:
    def read_series(self, dataset, relpath, window=None):
        raise AssertionError(f"read {relpath}")

def test_the_build_returns_exactly_the_declared_keys_and_176_cells():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    assert set(out) == subjects._C2_READING_KEYS and len(out["cells"]) == 176
    assert set(out["cells"]) == {cell_name(f, L, th, H, s) for f in FOLLOWERS for L in LAGS for th in THRESHOLDS for H in HORIZONS for s in SIDES}
    assert set(out["context"]) == set(FOLLOWERS) and all(set(rows) == {f"L{L}|H{H}" for L in LAGS for H in HORIZONS} for rows in out["context"].values())
    assert out["leader"] == LEADER_COVERAGE
    assert out["followers"] == FOLLOWER_COVERAGE
    assert (out["cost_round_trip"], out["sigma_window"], out["mean_block"], out["n_resamples"], out["seed"]) == (0.012, 96, 30, 4000, 42)

def test_the_inputs_half_reads_no_forward_return():
    inputs = subjects._c2_reading_inputs(subjects._c2_reads(_Reader(), "ohlc-15m", SUBJECT), SUBJECT)
    assert set(inputs._fields) == {"grid", "years", "leader", "returns", "sigma", "signals", "followers"}
    assert inputs.leader == LEADER_COVERAGE
    assert {f: {k: v for k, v in c.items() if k != "closes"} for f, c in inputs.followers.items()} == FOLLOWER_COVERAGE
    assert set(inputs.signals) == {f"L{L}|th{th}" for L in LAGS for th in THRESHOLDS}

def test_the_signals_keys_carry_both_sides_and_the_basis_shape():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    assert set(out["signals"]) == {f"L{L}|th{th}|{s}" for L in LAGS for th in THRESHOLDS for s in SIDES}
    assert all(set(v) == {"per_year", "total"} for v in out["signals"].values())
    assert out["signals"]["L4|th1|up"] == {"per_year": {"2023": 0, "2024": 80}, "total": 80}
    assert out["signals"]["L4|th2|up"]["total"] == out["signals"]["L1|th1|down"]["total"] == 0

def test_a_planted_follower_reads_potential_and_a_flat_cross_reads_none():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    planted = out["cells"]["ETH/EUR|L1|th1|H1|up"]
    assert planted["mean_gross"] > 0.012 and planted["p"] < 0.05 / 176
    assert out["cells"]["ETH/BTC|L1|th1|H1|up"]["mean_gross"] == pytest.approx(0.0, abs=1e-12)

def test_each_cell_is_read_at_its_own_lag_threshold_and_horizon():
    cells = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)["cells"]
    assert cells["ETH/EUR|L1|th1|H4|up"]["mean_gross"] == pytest.approx(0.042)
    assert cells["ETH/EUR|L4|th1|H1|up"]["n"] == 80 and cells["ETH/EUR|L4|th2|H1|up"]["n"] == 0

def test_the_metrics_hold_only_leaves_the_registry_stores():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    validate_metrics(out, "metrics")
    assert out["cells"]["ETH/EUR|L1|th1|H1|down"] == {"per_year": {"2023": {"n": 0}, "2024": {"n": 0}}, "n": 0}

def test_the_context_rows_pair_each_move_with_its_own_forward_return():
    context = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)["context"]
    eth = context["ETH/EUR"]
    assert eth["L1|H1"]["rank_ic_per_year"]["2023"] > 0 and eth["L1|H4"]["rank_ic_per_year"]["2023"] > 0 and eth["L4|H1"]["rank_ic_per_year"]["2023"] > 0
    assert eth["L1|H4"]["drift_per_year"]["2024"] > 3 * eth["L1|H1"]["drift_per_year"]["2024"]
    assert context["ETH/BTC"]["L1|H1"]["drift_per_year"] == {"2023": 0.0, "2024": 0.0}
    assert context["SOL/BTC"]["L1|H1"] == {"rank_ic_per_year": {}, "drift_per_year": {"2024": 0.0}}

def test_as_of_and_window_are_refused_before_any_read():
    with pytest.raises(subjects.SubjectError, match="drop --as-of"):
        subjects._build_c2_lead_lag_reading(_RaisingReader(), "ohlc-15m", None, as_of="2026-01-01")
    with pytest.raises(subjects.SubjectError, match="drop --window"):
        subjects._build_c2_lead_lag_reading(_RaisingReader(), "ohlc-15m", ("2024-01-01", "2024-02-01"))

def test_an_unreadable_file_names_its_relpath():
    with pytest.raises(subjects.SubjectError, match="ohlc-15m/SOL/BTC/15.parquet"):
        subjects._build_c2_lead_lag_reading(_Reader(broken="SOL/BTC/15.parquet"), "ohlc-15m", None)

def test_a_close_that_is_not_a_positive_number_is_refused_naming_its_file():
    series = _series()
    ts, close = series["DOT/EUR"]
    series["DOT/EUR"] = (ts, [*close[:10], 0.0, *close[11:]])
    with pytest.raises(subjects.SubjectError, match="c2-lead-lag-reading over the full history: ohlc-15m/DOT/EUR/15.parquet"):
        subjects._build_c2_lead_lag_reading(_Reader(series), "ohlc-15m", None)

def test_a_follower_with_no_stamp_on_the_leaders_grid_is_refused():
    series = _series()
    ts, close = series["AVAX/EUR"]
    series["AVAX/EUR"] = ([t + timedelta(minutes=7) for t in ts], close)
    with pytest.raises(subjects.SubjectError, match="AVAX/EUR has no stamp on the leader's grid"):
        subjects._build_c2_lead_lag_reading(_Reader(series), "ohlc-15m", None)

def test_a_duplicate_leader_stamp_is_refused_through_the_builds_wrap():
    series = _series()
    ts, close = series[LEADER]
    series[LEADER] = ([*ts[:5], ts[4], *ts[6:]], close)
    with pytest.raises(subjects.SubjectError, match="c2-lead-lag-reading over the full history: .*duplicate"):
        subjects._build_c2_lead_lag_reading(_Reader(series), "ohlc-15m", None)

def test_the_subject_is_registered_as_a_reading():
    s = subjects.SUBJECTS["c2-lead-lag-reading"]
    assert s.verdict is None and s.family is None and s.n_trials is None and s.intervals == (15,) and s.seeds == (42,)
    assert s.spec == "docs/specs/00150-c2-lead-lag-reading-design.md" and s.metric_keys == subjects._C2_READING_KEYS and s.assets == subjects._ASSETS
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_research_c2_lead_lag_reading.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'cli.research.subjects' has no attribute '_build_c2_lead_lag_reading'`.

- [ ] **Step 3: Implement the block and the `SUBJECTS` entry**, the README row, with the refusal messages verbatim from spec D6: `f"{subject} evaluates the frozen 15m set whole, never the rolling dataset as of a day: drop --as-of"` and `f"{_b2_over(subject, window)}: it reads the frozen 15m set whole, and the scale's trailing day reaches back past any window's first stamp; drop --window"`, `subject` the subject's name; and in `tests/test_research_command.py`, after `_declared_series`, the fixture the subject's contract rows read — its 200 bars keep each row that builds under 10 s at 4,000 resamples — with `"c2-lead-lag-reading": _c2_dataset,` closing `_CONTRACT_DATASETS`:

```python
def _c2_dataset(tmp_path: Path, subject: subjects.Subject) -> tuple[Path, datetime]:
    """The subject's ten 15m EUR series and the two crosses, 200 bars each."""
    root = tmp_path / "data"
    relpaths = [f"{asset}/EUR/15.parquet" for asset in subject.assets] + ["ETH/BTC/15.parquet", "SOL/BTC/15.parquet"]
    for i, relpath in enumerate(relpaths):
        _write_series(root, "ohlc-test", relpath, 200, phase=i * 0.7, step=900)
    return root, datetime.fromtimestamp(_EPOCH_2020, UTC)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_research_c2_lead_lag_reading.py tests/test_alpha_c2.py -q -p no:cacheprovider`
Expected: `29 passed`.

- [ ] **Step 5: Run the changed files' direct readers** — the new files staged first, so the list sees them; the list and its stderr in the implementer contract's `.tmp/<role>/`, here `.tmp/implementer/`, both removed before the task's report: `mkdir -p .tmp/implementer && bash infra/scripts/consumers.sh --direct cli/research/subjects.py README.md tests/test_research_command.py 2> .tmp/implementer/consumers.err | sort -u > .tmp/implementer/consumers.txt`, `.tmp/implementer/consumers.err` read for a refusal, then `T=$(cat .tmp/implementer/consumers.txt); [ -n "$T" ] && uv run pytest $T -m "not slow and not data and not retired" -q -p no:cacheprovider`, `tests/test_research_command.py` among them with the subject's nine contract rows — `not retired` deselects the retired subjects' rows as CI does (with them that file alone outruns a 585 s call) and keeps the subject's own until Task 5 retires it — split by file into calls under 600 s where one would pass it, each call setting its own `T` from the file, since no shell variable outlives its call — `T=$(grep -x -F tests/test_research_command.py .tmp/implementer/consumers.txt)` in one, `T=$(grep -v -x -F tests/test_research_command.py .tmp/implementer/consumers.txt)` in another.
Expected: all pass.

- [ ] **Step 6: Commit** — `feat(research): the reading subject c2-lead-lag-reading — spec 00150's 176 cells on the frozen 15m set, no rule, no slot` with the test lines and `.local/iter195/probes-task-1.txt` whole, Task 1 Step 6's verdict lines with their commands — first, its own call, `grep -c 'mutate-probe: [A-Z]* (control proven' .local/iter195/probes-task-1.txt` prints 18, one verdict per Task 1 Step 6 row; any other count is a concern returned, not a commit.

- [ ] **Step 7: Probe each case on Step 6's committed tree**, in the Global Constraints' probe form, `--file cli/research/subjects.py` unless the row names another, each mutation addressed to its own function's range, the node id `tests/test_research_c2_lead_lag_reading.py::<case>`; the nineteen verdict lines, each with its command, appended as each is read to `.local/iter195/probes-task-2.txt`, started empty (`mkdir -p .local/iter195 && : > .local/iter195/probes-task-2.txt` first) — ignored, so the next row's clean-tree check holds — which Task 3 Step 5's message carries whole. The rows, each a case and the mutation it must kill:
  - `test_the_build_returns_exactly_the_declared_keys_and_176_cells`, three rows — the context row's key written with the lag in the horizon's place, `|H{L}` for `|H{H}`; then, in `_c2_reading_inputs`, the leader's `last_stamp` taken at its first stamp; then, in `_c2_reading_metrics`, the `followers` keeping each follower's `closes`;
  - `test_the_inputs_half_reads_no_forward_return`, three rows — `non_15m_steps` counting the steps equal to `STEP`; then a follower's entry carrying a sixth key, `"fwd"` beside `"closes"`; then the signals keyed over `(*THRESHOLDS, 3)` in place of `THRESHOLDS`;
  - `test_the_signals_keys_carry_both_sides_and_the_basis_shape` — the side a signal count counts flipped, `-1` for `up`;
  - `test_a_planted_follower_reads_potential_and_a_flat_cross_reads_none` — `--file cli/alpha/c2.py`, `N_RESAMPLES = 4000` written `N_RESAMPLES = 2000`;
  - `test_each_cell_is_read_at_its_own_lag_threshold_and_horizon` — the cell reading the forward return at its lag in place of its horizon;
  - `test_the_metrics_hold_only_leaves_the_registry_stores` — a signal count's year key written as the `int` year;
  - `test_the_context_rows_pair_each_move_with_its_own_forward_return` — the rank IC's moves taken at the horizon in place of the lag;
  - `test_as_of_and_window_are_refused_before_any_read`, two rows — the `as_of` condition made `False`; then the `window` condition made `False`;
  - `test_an_unreadable_file_names_its_relpath` — `OSError` dropped from the read's `except`;
  - `test_a_close_that_is_not_a_positive_number_is_refused_naming_its_file` — the close check's condition made `False`;
  - `test_a_follower_with_no_stamp_on_the_leaders_grid_is_refused` — the `on_grid` 0 condition made `False`;
  - `test_a_duplicate_leader_stamp_is_refused_through_the_builds_wrap` — the wrap's `except` naming `ValidationError` alone;
  - `test_the_subject_is_registered_as_a_reading`, two rows — the entry's `_ASSETS` written `_ASSETS[:-1]`; then the entry's `seeds=(SEED,)` written `seeds=()`.

---

### Task 3: the data-gated basis test and the decisions-log entries before the hash

**Files:**
- Create: `tests/test_research_c2_lead_lag_reading_basis.py`
- Modify: `docs/research/10.phase4-decisions.md` (append two entries)
- Test: the new file (data-gated), `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py`, `tests/test_data_gated_marker.py`, `tests/test_live_venue_opt_in.py`

**Interfaces:**
- Consumes: `subjects._c2_reads`, `subjects._c2_reading_inputs`; `ObservedReader(_DATA_ROOT)` as `tests/test_research_b3_btc_overlay_basis.py` builds it.

- [ ] **Step 1: Write the data-gated basis case**, gated as the Global Constraints say, the figures copied from spec 00150's measured basis, never from a run — every stamp converted from the spec's ISO form, every signal held by year:

```python
# tests/test_research_c2_lead_lag_reading_basis.py
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from cli.registry.observed import ObservedReader
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SUBJECT = "c2-lead-lag-reading"

def _epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())

# Copied from spec 00150's measured basis, never from a run: the leader's figures, each follower's bars, first stamp,
# on-grid and off-grid counts, and each signal's count per calendar year 2013 through 2026.
LEADER_BASIS = {"bars": 430_560, "first_stamp": _epoch("2013-09-10T23:45:00+00:00"), "last_stamp": _epoch("2026-03-31T23:45:00+00:00"), "non_15m_steps": 3_002, "sigma_warm_index": 2_831}
FOLLOWER_BASIS = {
    "ADA/EUR": (254_419, "2018-09-28T13:15:00+00:00", 254_419, 0),
    "AVAX/EUR": (133_305, "2021-12-21T15:30:00+00:00", 133_305, 0),
    "DOGE/EUR": (199_897, "2019-12-19T14:45:00+00:00", 199_897, 0),
    "DOT/EUR": (191_755, "2020-08-18T17:00:00+00:00", 191_754, 1),
    "ETH/EUR": (361_327, "2015-08-07T11:00:00+00:00", 361_286, 41),
    "LINK/EUR": (210_214, "2019-09-25T13:45:00+00:00", 210_213, 1),
    "LTC/EUR": (356_774, "2013-09-14T08:15:00+00:00", 356_211, 563),
    "SOL/EUR": (166_537, "2021-06-17T15:30:00+00:00", 166_537, 0),
    "XRP/EUR": (309_480, "2017-05-18T15:45:00+00:00", 309_477, 3),
    "ETH/BTC": (347_656, "2016-03-03T07:00:00+00:00", 347_616, 40),
    "SOL/BTC": (160_120, "2021-06-17T15:30:00+00:00", 160_120, 0),
}
SIGNAL_BASIS = {
    "L1|th1|up": [8, 358, 2_139, 4_026, 4_405, 3_399, 3_597, 4_147, 4_123, 3_630, 3_783, 4_328, 4_288, 965],
    "L1|th1|down": [5, 369, 2_068, 3_888, 3_956, 3_601, 3_474, 3_781, 4_135, 3_716, 3_590, 4_126, 4_296, 1_010],
    "L1|th2|up": [1, 93, 394, 745, 887, 697, 787, 837, 853, 821, 908, 1_021, 1_002, 229],
    "L1|th2|down": [1, 98, 476, 805, 985, 894, 819, 869, 872, 937, 862, 1_046, 1_030, 269],
    "L4|th1|up": [3, 291, 1_614, 2_691, 4_571, 3_387, 3_647, 4_032, 4_120, 3_666, 3_693, 4_339, 4_219, 930],
    "L4|th1|down": [4, 315, 1_464, 2_541, 3_795, 3_758, 3_361, 3_549, 4_147, 3_956, 3_376, 4_043, 4_265, 1_009],
    "L4|th2|up": [1, 46, 267, 469, 887, 744, 913, 973, 863, 865, 1_055, 1_048, 961, 210],
    "L4|th2|down": [1, 74, 291, 490, 932, 1_052, 933, 871, 986, 1_109, 900, 1_075, 1_097, 266],
}

@pytest.mark.skipif(nothing_found_under(_DATA_ROOT, "ohlc-15m/*/*/15.parquet"), reason="the frozen ohlc-15m set is absent under data/")
def test_the_inputs_half_reads_the_specs_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    inputs = subjects._c2_reading_inputs(subjects._c2_reads(ObservedReader(_DATA_ROOT), "ohlc-15m", SUBJECT), SUBJECT)
    assert inputs.leader == LEADER_BASIS
    basis = {f: (bars, _epoch(first), on, off) for f, (bars, first, on, off) in FOLLOWER_BASIS.items()}
    assert {f: (v["bars"], v["first_stamp"], v["on_grid"], v["off_grid"]) for f, v in inputs.followers.items()} == basis
    # The computes half is never called here: it is past the hash rule.
    for key, per_year in SIGNAL_BASIS.items():
        signal, side = key.rsplit("|", 1)
        want = 1 if side == "up" else -1
        counts = Counter(y for s, y in zip(inputs.signals[signal], inputs.years) if s == want)
        assert [counts[y] for y in range(2013, 2027)] == per_year, key
```

- [ ] **Step 2: Run it without the data linked** — `uv run pytest tests/test_research_c2_lead_lag_reading_basis.py -q -p no:cacheprovider -rs`. Expected: `1 skipped`, its reason `the frozen ohlc-15m set is absent under data/` (not a failure); then, the controller having linked `data/ohlc-15m`, run it — Expected: `1 passed` in under 3 minutes. (The implementer runs the unlinked form only and reports; the linked run is the controller's at Task 4.)

- [ ] **Step 3: Append the two decisions-log entries** to `docs/research/10.phase4-decisions.md`, the `[iter-195]` key, in the log's shape (question, 2–3 options with tradeoffs, `(Decision: N)`, the `Logged` line):
  1. `[iter-195] C2 opened on the owner's family pick — C2's first step, a no-slot reading of the gross lead-lag surface, the loop's pick under the owner's run instruction (Decision: 1)` — the three options of spec D1, verbatim in substance; the Logged line quoting the owner's words of 2026-10-27 verbatim from the plan review's ledger (`.tmp/plan-review/00150/ledger.md`, copied before the merge to the main checkout's `.local/reads-archive/research/iter-195-c2-lead-lag/plan-review-00150/ledger.md`, Task 6 Step 3) — the family pick, an AskUserQuestion answer: "C2 — BTC→alt lead-lag on 15m (Recommended)"; the run instruction: "skip the questions, write the pre-registration. Ignore the wall clock time gate, but do not start a new task after 10:00Z" — and naming spec 00150 D1.
  2. `[iter-195] C2's lead-lag reading's conventions, pinned by spec 00150 before its hash (Decision: 1)` — one option taken, the alternatives named: entry at the signal bar's close against a one-bar delay (D4); overlapping trades counted apart against a merged hold (D4); the √L scaling of the threshold (D3); the floor at 100 per complete year over 2015–2025 against every complete year (D5); Bonferroni over 176 against no correction (D5); gross against net in legs 1 and 2 (D5); and the four calls the plan review ruled, each named as ruled there — 4,000 resamples against 2,000, at which leg 3 cannot hold (1/2,001 is above 0.05/176), its bound holding at 4,000 only at a bootstrap count of 0 (D4, D5); the 0.012 read as the registered maker-plus-spread basis against a tier-1 taker round trip of 0.016 plus the spread, so a cell clearing it is not yet one a taker clears (D4); the criterion read off a scratch program's printed table against a read by eye off the line, never by the subject's code (D5); a refused run, a failed check of the line or a failed replay before the line's commit a stop before any commit, and a failed replay on the tip the PR pushes a stop before the push, the line and the retirement kept for the owner's ruling, against a fix and a second run on the branch (D7).

- [ ] **Step 4: Run the log's guards and the two walkers the new file's mark and gate meet** — `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py tests/test_data_gated_marker.py tests/test_live_venue_opt_in.py -q -p no:cacheprovider`. Expected: all pass.

- [ ] **Step 5: Commit** — `docs(research): the two [iter-195] entries before spec 00150's hash, and C2's data-gated basis case` with both test lines (the basis case's `skipped` line named as the unlinked run) and `.local/iter195/probes-task-2.txt` whole, Task 2 Step 7's verdict lines with their commands — first, its own call, `grep -c 'mutate-probe: [A-Z]* (control proven' .local/iter195/probes-task-2.txt` prints 19, one verdict per Task 2 Step 7 row; any other count is a concern returned, not a commit.

- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two, each on Opus, model named; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing reads or computes any follower's forward return conditioned on a signal, any cell's means or p, or the context rows — through the code, a program or arithmetic — or runs the reading over the real set, before the spec's hash, and the data-gated case runs with the frozen 15m set linked into the reader's worktree by `ln -snT /home/zhaow/Projects/zcrypto-kraken/data/ohlc-15m <the reader's worktree>/data/ohlc-15m` and unlinked by `test -L <the reader's worktree>/data/ohlc-15m && unlink <the reader's worktree>/data/ohlc-15m` before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 Step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

---

### Task 4 (the controller's): the gate, the spec hash, the develop check, the data test, the run, its read and its commit

`<H>` is Step 2's sha256. The two files this task writes from this plan's fences and never commits — Step 5's notes and Step 7's program — are each extracted from the plan at the tip the last read names, never typed. **The stop** (spec D7): a refused run (Step 6), a failed check of the line (Step 7) or a failed replay (Step 10) stops the task before any commit — any line the run appended stays uncommitted in the worktree, neither committed nor reverted; every data link the task made is removed in the Global Constraints' form, Step 10's scratch worktree after its links; the refusal or the failing check is quoted whole, from the output file its step names, in the SDD ledger and in a `## Findings so far` bullet of T0016 headed `**C2's lead-lag reading (iter-195, spec 00150) — stopped before any commit, no reading kept.**`, written into the worktree and left uncommitted beside it; the steps after it, Task 5 and Task 6 do not run; and the reading's design stands unrun until the cause is fixed as new work with its own reads.

- [ ] **Step 1: The gate** — the plan review closed (`zcrypto-plan-review`); Task 3 Step 6's reads closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ docs/specs/00150-c2-lead-lag-reading-design.md docs/plans/00150-c2-lead-lag-reading.md docs/research/10.phase4-decisions.md` exits 0, its own call; `git status --porcelain` empty.
- [ ] **Step 2: The spec hash** — `sha256sum docs/specs/00150-c2-lead-lag-reading-design.md`, pasted; the spec never edited after.
- [ ] **Step 3: The develop check** — `git fetch origin develop && git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl; echo rc=$?` — `rc=0`, else STOP.
- [ ] **Step 4: Link the data, run the basis case and probe it** — `ln -snT /home/zhaow/Projects/zcrypto-kraken/data/ohlc-15m /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter195/data/ohlc-15m`, its own call; `uv run pytest tests/test_research_c2_lead_lag_reading_basis.py -q -p no:cacheprovider -rs` → `1 passed`, never a skip. Then, on this clean tree (the link is ignored), the new guard file's one case probed in the Global Constraints' probe form, `--file cli/research/subjects.py`, the node id `tests/test_research_c2_lead_lag_reading_basis.py::test_the_inputs_half_reads_the_specs_measured_basis`, the mutation `non_15m_steps` counting the steps equal to `STEP`, its verdict line and command carried in Step 11's commit message. The probe runs the inputs half alone, which the hash rule admits.
- [ ] **Step 5: The notes, written before the run** (spec D7) — `mkdir -p .local/iter195`, its own call; the fence's one line below extracted from the read tip, its placeholder replaced by the spec's own hash, never typed: `git show <the tip the last read names>:docs/plans/00150-c2-lead-lag-reading.md | grep '^subject c2-lead-lag-reading over ohlc-15m, ' | sed "s/[<]H[>]/$(sha256sum docs/specs/00150-c2-lead-lag-reading-design.md | cut -d' ' -f1)/" > .local/iter195/notes.txt`, its own call; then `test "$(wc -l < .local/iter195/notes.txt)" = 1 && ! grep -q '[<]H[>]' .local/iter195/notes.txt` exits 0, its own call:

```text
subject c2-lead-lag-reading over ohlc-15m, the frozen 15m set read whole, no window and no as-of; descriptive: no hypothesis, no bar, no verdict and no C slot; the leader BTC/EUR, its 15m log return, its scale the sample standard deviation of its trailing 96 returns, its move the sum of its last 1 or 4 returns, and a signal, up or down, where the move passes 1 or 2 scales times the square root of the lag; the eleven followers ADA/EUR, AVAX/EUR, DOGE/EUR, DOT/EUR, ETH/EUR, LINK/EUR, LTC/EUR, SOL/EUR, XRP/EUR, ETH/BTC and SOL/BTC, each mapped onto the leader's stamps by exact stamp; 176 cells, follower by lag by threshold by horizon (1 or 4 bars) by side, each trade entered at the signal bar's close, long the follower after an up move and short it after a down move, its gross return the follower's forward log return in the move's direction and its net the gross less the round trip 0.012 at the registered 0.006 a side; per cell, per calendar year and over the whole span, the trades and their mean gross and net return, and over the span the stationary bootstrap p that the mean net return per trade is at or below zero, at mean block 30, 4000 resamples and seed 42; the potential criterion pre-registered by spec 00150's sha256 <H>: its floor at least 100 trades in each complete calendar year the follower spans within 2015 through 2025, then three legs, the mean gross return above 0.012 in every year the floor counts and over the whole span, and the bootstrap p below 0.05/176, Bonferroni over the 176 cells; read by the closeout's pick off a printed table, never by the subject's code.
```

- [ ] **Step 6: The one run** — no plain eval before or after it: `uv run zcrypto research eval --subject c2-lead-lag-reading --dataset ohlc-15m --reading --iteration iter-195 --spec-hash <H> --notes "$(cat .local/iter195/notes.txt)" > .local/iter195/run.out 2>&1; echo "rc=$?" >> .local/iter195/run.out`, one Bash call with `run_in_background: true` — its bootstrap bounded at about 24 minutes (the spec's measured basis) — acted on only at its completion notification, no polling and no other command in this worktree while it lives; then `cat .local/iter195/run.out`. The task continues only on `rc=0` with `recorded reading 7`; every other end — a refusal, `rc=1` naming the subject, a file, the tree, the spec hash, the dataset or the registry's refusal of the metrics; a traceback; a signal — is the stop, `.local/iter195/run.out` quoted.
- [ ] **Step 7: The line's checks and the table** — the program below, extracted from the read tip, its first line to the line before its closing fence, by `mkdir -p .tmp/iter195 && git show <the tip the last read names>:docs/plans/00150-c2-lead-lag-reading.md | sed -n '/^"""Reading 7 off the ledger/,/^\x60\x60\x60$/p' | sed '$d' > .tmp/iter195/reading_7.py`, its own call, and checked by `test -s .tmp/iter195/reading_7.py && uv run python -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' .tmp/iter195/reading_7.py`, exit 0; then `uv run python .tmp/iter195/reading_7.py <H> > .local/iter195/reading_7.out 2>&1; echo "rc=$?" >> .local/iter195/reading_7.out` and `cat .local/iter195/reading_7.out`. `rc=0` follows every check printed `True` with one line per cell the floor admits and the counts; `rc=1` is the stop, the checks line quoted. Spec D5's criterion is read off this table, never by the subject's code; the floor's years are D5's rule applied to the basis's first stamps.

```python
"""Reading 7 off the ledger's last line: its checks against spec 00150's measured basis, then, every check holding, the
table spec 00150 D5's criterion is read off — one line per cell the floor admits, its three legs' values and whether
each holds, then the counts; exit 0 only when every check holds."""

import json
import sys
from pathlib import Path

from cli.alpha.c2 import FOLLOWERS, HORIZONS, LAGS, SIDES, THRESHOLDS, cell_name
from cli.research.subjects import SUBJECTS
from tests.test_research_c2_lead_lag_reading_basis import FOLLOWER_BASIS, LEADER_BASIS, SIGNAL_BASIS, _epoch

YEARS = range(2013, 2027)
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
names = {cell_name(f, L, th, H, s) for f in FOLLOWERS for L in LAGS for th in THRESHOLDS for H in HORIZONS for s in SIDES}
checks = {
    "labels": (r["reading_id"], r["iteration"], r["spec_hash"], r["attempt"]) == (7, "iter-195", sys.argv[1], None),
    "keys": set(m) == SUBJECTS["c2-lead-lag-reading"].metric_keys,
    "leader": m["leader"] == LEADER_BASIS,
    "followers": m["followers"]
    == {f: {"bars": b, "first_stamp": _epoch(s), "on_grid": on, "off_grid": off} for f, (b, s, on, off) in FOLLOWER_BASIS.items()},
    "signals": m["signals"]
    == {k: {"per_year": {str(y): n for y, n in zip(YEARS, v, strict=True)}, "total": sum(v)} for k, v in SIGNAL_BASIS.items()},
    "cells": set(m["cells"]) == names and all(set(c["per_year"]) == {str(y) for y in YEARS} for c in m["cells"].values()),
    "p": all(("p" in c) == (c["n"] >= 2) and ("p" not in c or 0 < c["p"] <= 1) for c in m["cells"].values()),
    "context": set(m["context"]) == set(FOLLOWERS)
    and all(set(rows) == {f"L{L}|H{H}" for L in LAGS for H in HORIZONS} for rows in m["context"].values()),
    "constants": (m["cost_round_trip"], m["sigma_window"], m["mean_block"], m["n_resamples"], m["seed"]) == (0.012, 96, 30, 4000, 42),
}
print(r["reading_id"], checks)
if not all(checks.values()):
    sys.exit(1)
cost, bound = m["cost_round_trip"], 0.05 / len(names)
admitted, held = [], [0, 0, 0]
for name in sorted(names):
    c = m["cells"][name]
    floor = [str(y) for y in range(max(int(FOLLOWER_BASIS[name.split("|")[0]][1][:4]) + 1, 2015), 2026)]
    if not floor or any(c["per_year"][y]["n"] < 100 for y in floor):
        continue
    legs = (all(c["per_year"][y]["mean_gross"] > cost for y in floor), c["mean_gross"] > cost, c["p"] < bound)
    admitted.append((name, all(legs)))
    held = [h + leg for h, leg in zip(held, legs, strict=True)]
    per_year = {y: (c["per_year"][y]["n"], c["per_year"][y]["mean_gross"]) for y in floor}
    print(name, "| floor", floor[0], "to", floor[-1], "| (n, mean gross) per year", per_year, "| span mean gross", c["mean_gross"],
          "| p", c["p"], "| legs 1, 2, 3", legs, "| potential", all(legs))
print("cells", len(names), "| the floor admits", len(admitted), "| hold legs 1, 2, 3", held, "| potential", [n for n, p in admitted if p] or "none")
```

- [ ] **Step 8: Read the criterion** (spec D5) off Step 7's table: the cells the floor admits, how many hold each leg, and the cells with potential, each named, or none.
- [ ] **Step 9: The entry, the slow-cases line and their gate** — `docs/research/10.phase4-decisions.md`'s third entry, `[iter-195] BTC→alt lead-lag read on frozen ohlc-15m (reading 7)`, in the `[iter-190]` reading entry's form: the subject, the set, the spec hash, the headline — how many cells the floor admits, how many hold each leg, the cells with potential (or none) — Step 7's table pasted whole below it, each line indented two spaces as the log's continuation lines are, and what the criterion leaves for C2's next step, the pick's and not this entry's (spec D5): a cell with potential names trial 1, pre-registered in a new spec; with none, the owner's family call, hold or close C2, a 1m horizon left to a later spec (spec 00150's Out of scope); and `tests/slow-cases.txt` gaining `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-7]` at its `sorted()` place. Then `git add docs/reference/reading-ledger.jsonl docs/research/10.phase4-decisions.md tests/slow-cases.txt`, its own call; `uv run pytest tests/test_decisions_log_ties.py tests/test_decisions_log_shape.py tests/test_slow_cases.py tests/test_slow_ledger.py tests/test_trial_registry_provenance.py -q -p no:cacheprovider` — the log's two guards and the staged files' direct readers by `bash infra/scripts/consumers.sh --direct` — every case passing, its result line for the message; `uv run pre-commit run -a` until clean, each rewrite staged by path.
- [ ] **Step 10: The replay, before the commit, on the tree the commit will hold** — the replay refuses a checkout whose ledger line is uncommitted, so it runs in a detached scratch worktree that holds Step 9's index committed, `<R>` written out in each call as `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter195/.tmp/iter195/replay`. Each its own call, in order: `git write-tree`, its printed hash the tree; `git worktree add --detach <R> HEAD`; `git -C <R> read-tree -u --reset <the tree>`; `git -C <R> commit -q -m "test: reading 7's replay at <the tree>"`; the Global Constraints' links of `ohlc-15m` and `ohlc-full` into `<R>`; then `(cd <R> && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-7' -q -p no:cacheprovider -rs) > /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter195/.local/iter195/replay.out 2>&1; echo "rc=$?" >> /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter195/.local/iter195/replay.out`, one Bash call with `run_in_background: true`, as long as the run, acted on only at its completion notification: `1 passed`, never a skip, and any other result is the stop, `.local/iter195/replay.out` quoted; then, whatever the result, both links removed from `<R>` in the Global Constraints' form, `git worktree remove --force <R>`, and the main checkout's `data/` listing read.
- [ ] **Step 11: The commit** — with no `git add` since Step 10's `git write-tree`: `git commit`, its own call, message `docs(research): reading 7 — C2's lead-lag surface on ohlc-15m; [iter-195] its entry`, carrying Step 9's result line, Step 10's replay result line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-7]`, and Step 4's probe verdict line and command; then `test "$(git rev-parse HEAD^{tree})" = <the tree Step 10 printed>` exits 0, its own call; then this worktree's `ohlc-15m` link removed in the Global Constraints' form.

---

### Task 5: T0016, the retirement and the index

Runs only once Task 4 Step 11's commit exists. On Task 4's stop it does not run: T0016's bullet quoting the refusal or the failing check is the controller's, written at the stop and left uncommitted, and `tests/retired_subjects.py` and the subject's test file stay untouched, since a run still to come evaluates the subject.

**Files:**
- Modify: `docs/open-topics/T0016-bucket-b-c-alpha-families.md` — `ripe_when:`'s C2 clause `C2: a tick catalog exists;` becomes ``C2: an activity, C2''s next step after the lead-lag reading is picked — the loop''s pick under a run instruction, else the owner''s, a close the owner''s — reading spec 00150''s potential criterion, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] C2.s next step after the lead-lag reading'' docs/research/10.phase4-decisions.md` prints at least 1;`` — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check in its own backticks (measured on the base: the frontmatter parses, `infra/scripts/topics-index.py` renders, the check prints 0); in `## Findings so far`'s prerequisites bullet, "C2 must re-open it as its own topic" becomes "C2 at 15m needs none, the substrate being tick-reconciled, and a 1m horizon is a later spec's design decision (spec 00150)"; a `## Findings so far` bullet headed `**C2's lead-lag reading (iter-195, spec 00150, reading 7).**`, its figures copied, never recomputed, from the headline the `[iter-195] BTC→alt lead-lag read on frozen ohlc-15m (reading 7)` entry in `docs/research/10.phase4-decisions.md` states — the cells the floor admits, how many hold each leg, the cells with potential or none — and that entry named, as the B4 leg reading's bullet names its own; a `## Done so far` bullet "**C2 opened (iter-195, spec/plan `00150`)** on the owner's family pick of 2026-10-27, its first step a no-slot reading, the loop's pick under the owner's run instruction: the module `cli/alpha/c2.py`, the subject `c2-lead-lag-reading` and its data-gated basis test `tests/test_research_c2_lead_lag_reading_basis.py`; the lead-lag reading (reading 7), no slot spent, bucket C's 10 untouched; the subject retired."
- Modify: `tests/retired_subjects.py` — `"c2-lead-lag-reading"` added under a `# C2's reading.` comment, and the comment above `SUBJECT_TESTS` made the rule: "The file whose cases evaluate a subject named in a parameter; a subject's own test file outside the data-gated family is marked `retired` whole once its subject retires, and elsewhere a subject's name is a checker's data, as in the registry provenance cases, which CI keeps."
- Modify: `tests/test_research_c2_lead_lag_reading.py` — `pytestmark = pytest.mark.retired` after its imports: its cases name the subject in no parameter, so `names_a_retired_subject` never marks them.
- Modify: `docs/open-topics/README.md` — re-rendered by `uv run python infra/scripts/topics-index.py` (the `ripe_when` moved).

- [ ] **Step 1: Edit the four files** as above.
- [ ] **Step 2: Run** `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_retired_subjects.py -q -p no:cacheprovider`. Expected: all pass. Then `uv run pytest --collect-only -q -p no:cacheprovider -m "not retired" tests/test_research_c2_lead_lag_reading.py`. Expected: `no tests collected (13 deselected)` and exit 5, pytest's code for an empty collection — the expected end, not a failure.
- [ ] **Step 3: Commit** — `docs(topics): T0016 carries C2's opening and reading 7; c2-lead-lag-reading retired; the index re-rendered`.

---

### Task 6 (the controller's): the change-index row, the reads and the PR

- [ ] **Step 1:** `open-pr` Steps 1, 2 and 4 — title `feat(research): iter-195 — C2 lead-lag surface on ohlc-15m (reading 7)` (70 characters by `printf '%s' <it> | wc -m`, under the cap), the row `| #<n> | <date> | <title> | iter-195 | 00150 | T0016 |`, committed.
- [ ] **Step 2:** the delta read — `pre-review` of Tasks 4–5's commits and the row's, folds by `fold-check`, then `review` over `<the tip the last read names>..HEAD` and `re-review` over a fix of it within the branch's two, each on Opus, model named, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case runs with the frozen 15m set linked into the reader's worktree by `ln -snT /home/zhaow/Projects/zcrypto-kraken/data/ohlc-15m <the reader's worktree>/data/ohlc-15m` and unlinked by `test -L <the reader's worktree>/data/ohlc-15m && unlink <the reader's worktree>/data/ohlc-15m` before its report, since unlinked it skips, and the replay the messages record, a rebuild of every cell as long as the run, is the controller's (Step 3), never a reader's.
- [ ] **Step 3:** on the tip it pushes, `git status --porcelain` empty, the replay again in this worktree: the Global Constraints' links of `ohlc-15m` and `ohlc-full` into it, then `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-7' -q -p no:cacheprovider -rs > .local/iter195/replay-tip.out 2>&1; echo "rc=$?" >> .local/iter195/replay-tip.out`, one Bash call with `run_in_background: true`, acted on only at its completion notification — `1 passed`, never a skip; any other result stops the task before the push, `.local/iter195/replay-tip.out` quoted whole in the SDD ledger and in a T0016 `## Findings so far` bullet left uncommitted, every commit kept for the owner's ruling (spec D7) — then both links removed in the Global Constraints' form; then the push, the PR through `open-pr` (body: Summary; Spec / Plan naming 00150 and T0016; the read line; `## Changes`, holding the reading's headline, Task 4 Step 7's counts line and its lines for the cells with potential in a fenced block — the whole table, a line per admitted cell, which can pass GitHub's 65,536-character body limit, stays in the `[iter-195] … (reading 7)` entry the body names — and what the criterion leaves for C2's next step; `## Test plan` with every result line pasted; `## Reads`), the CI watch; before `merge-pr`, the plan review's `.tmp/plan-review/00150/` — its ledger the source spec D1 quotes — copied whole, `mkdir -p /home/zhaow/Projects/zcrypto-kraken/.local/reads-archive/research/iter-195-c2-lead-lag && cp -r /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter195/.tmp/plan-review/00150 /home/zhaow/Projects/zcrypto-kraken/.local/reads-archive/research/iter-195-c2-lead-lag/plan-review-00150`; then `merge-pr` when green.
- [ ] **Step 4:** after `merge-pr`, the memo's T0016 item and the coordination table.
