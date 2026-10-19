# B2's ratio columns and liquidations leg on the 4h close grid — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` — `uv run python infra/scripts/tier.py --paths cli/alpha/b2.py tests/test_alpha_b2.py docs/research/10.phase4-decisions.md docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/README.md` prints `tier: full`, for `tests/test_alpha_b2.py`, a test importing `cli.alpha.b1`.

**Goal:** spec `docs/specs/00136-b2-ratio-liquidation-features-design.md` — `cli/alpha/b2.py` emits the four Binance ratios, each read as a level at a union's 4h closes through the OI rows' one pipeline, and the liquidations leg, per union bar the long, short and total notional and their imbalance from the Coinalyze poller's tree, an hour covered when any coin's tree holds its final and a union closing past the tree's finality frontier refused; each proven on known answers and the truncating-prefix property; the decisions log carries six `[00136]` entries and T0023 records both delivered.

**Architecture:** one module, `cli/alpha/b2.py`. `_oi_at_union_closes` gives its grid, its staleness bound and its lookup to `_rows_at_union_closes` and keeps only the placeholder mapping, and the union's two checks move into `_validate_union_marks`; `ratio_grid_features` reads each ratio through `_rows_at_union_closes` unmapped, its names and validation `ratio_features`' (spec D2). `liquidation_grid_features` lists the poller's finals with `_liquidation_finals`, takes its coverage from every coin's tree under the root, refuses a union whose last close lies past the tree's finality frontier — the newest final's hour close less `_FINALIZE_LAG_SECONDS`, imported from `cli.liquidations.coinalyze` — and sums each union bar's buckets (spec D3, D4, D6) under D5's names. The ratio emitter is a pure function over lists; the liquidation emitter reads parquet with polars and writes nothing. No subject, no registry record, no dataset read by any test.

**Tech stack:** Python 3.14 through uv; polars; pytest; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** binding; D1–D6 are cited by name. **Topic:** T0023. **Branch:** `research/00136-b2-ratio-liquidation-features`, cut from develop at `a5e8bee5a`. A choice this plan makes that the spec leaves open is marked **Author's call**.

## Global Constraints

- TDD per task: the failing test first, the implementation second, the test green third.
- Tests: every pytest run is `mkdir -p .tmp/00136 && uv run pytest <file or node id> -q -p no:cacheprovider --basetemp=.tmp/00136/pt` — pytest creates `--basetemp` but not its parent, and the liquidation tests lay their trees out under it — never a bare `uv run pytest`. Before each commit, the consumers: `T=$(infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/00136/pt`. For `cli/alpha/b2.py` and `tests/test_alpha_b2.py` that is `tests/test_alpha_b1_exit.py`, `tests/test_alpha_b2.py`, `tests/test_research_b1_hourly_exit_basis.py`, `tests/test_research_b1_volume_basis.py`, `tests/test_research_b2_basis.py` and `tests/test_research_command.py`, measured at Task 2's tree as `520 passed, 2 skipped, 48 deselected in 182.87s`, one part under 600 s; the 2 skips are the two B1 basis files' data-gated cases, the frozen `ohlc-full` set being absent under `data/`, and each task report names them. A commit message's test line is a run over that commit's own tree.
- Probes: the tier is `full`, so each guard is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree. After the gate, with the task's files staged:

```bash
TREE=$(git write-tree)
git worktree add --detach .tmp/00136/probe HEAD
git -C .tmp/00136/probe read-tree -u --reset "$TREE"
git -C .tmp/00136/probe commit -q -m "test: probe $TREE"
mkdir -p .tmp/00136/probe/.tmp
```

  then, from `.tmp/00136/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' cli/alpha/b2.py | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' cli/alpha/b2.py) cli/alpha/b2.py | grep -c '^>'` prints 1 — the substitution changes one line, its site standing once or its address range holding one — and the same two for the control. Every mutation substitutes and none deletes a line; every control renames the `def` of a function the case's module imports, so it fails the case at collection. After the last verdict, `git worktree remove --force .tmp/00136/probe`. The task's commit carries in its message each row's command and its verdict line, the script named in both, and after it `test "$(git rev-parse HEAD^{tree})" = "$TREE"` passes. No case here is slow: the longest, the liquidations prefix case, measured 3.79 s (`--durations=3`), under the 10 s that puts a case in `tests/slow-cases.txt`.
- Data: no test and no step reads a dataset or the live liquidations tree; every fixture is synthetic, the liquidation trees laid out under `--basetemp` by the poller's own `SegmentWriter`. Never `/var/lib/zcrypto-ops/liquidations`, `data/ohlc-holdout-*` or `/mnt/zhao-crypto/`; never ssh, docker, `kraken-cli`, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. Never look for, open, count or quote any real account export anywhere outside the repository's tracked fixtures.
- Never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, and the decisions log only through Task 3's append; never `zcrypto research eval`; never compute a return or a performance figure; never `git stash`; no amend; a state-changing git command runs alone.
- Not edited: `cli/features/derivatives.py`, `cli/liquidations/`, `cli/capture/`, `cli/research/subjects.py` — `git diff --quiet develop HEAD -- cli/features cli/liquidations cli/capture cli/research` exits 0 after every task — and the spec after its commit. No task's diff removes a line of `tests/test_alpha_b2.py`: spec `00131`'s OI cases are spec D2's proof of the lifted pipeline, and `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` prints 0 after every task.
- No string literal under `cli/` — an error message, a log line — carries `spec <NNNNN>`, `D<N>`, `T<NNNN>` or `iter-<N>` (`tests/test_internal_terms_not_operator_visible.py`), and no code prose carries a plan-task number (`tests/test_code_prose_citations.py`); comments and docstrings cite `docs/specs/00136 D<N>`.
- Commits: one per task, `feat(alpha)` for Tasks 1–2, `docs(research)` for Task 3 and `docs(open-topics)` for Task 4, staged by explicit path; the gate `uv run pre-commit run -a`, re-run until clean, runs before the probe tree is cut, so the probed tree is the committed one; each message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` and `Claude-Session: <the executing session's URL>`.
- Scratch under this worktree's `.tmp/00136/`, the probe tree removed at the end of its task.

______________________________________________________________________

### Task 1 — the ratio columns, through the OI rows' one pipeline

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

- [ ] **Step 1 — the failing tests** (`tests/test_alpha_b2.py`). In the `from cli.alpha.b2 import (` block, `    ratio_grid_features,` goes below `    per_year_turnover,`; `from cli.features.errors import FeatureError` goes on its own line below `from cli.alpha.errors import AlphaError`. Then, at the end of the file, after two blank lines:

```python
_RATIO_COLUMNS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


def _each_ratio(values: list[float | None]) -> dict[str, list[float | None]]:
    return {name: list(values) for name in _RATIO_COLUMNS}


def _binperp(values: list[float | None]) -> dict[str, list[float | None]]:
    return {f"binperp_{name}": list(values) for name in _RATIO_COLUMNS}


def test_each_ratio_reads_its_bars_last_row_at_the_close_under_its_binperp_name():
    oi_ts = [DAY0 + timedelta(hours=4 * k + 4, minutes=m) for k in range(3) for m in (-10, -5)]
    ratios = {name: [i + 1.0 + r / 10 for r in range(6)] for i, name in enumerate(_RATIO_COLUMNS)}
    # Each bar's later row, from its own column: an earlier row, or a column read in another's place, differs.
    expected = {f"binperp_{name}": [i + 1.0 + r / 10 for r in (1, 3, 5)] for i, name in enumerate(_RATIO_COLUMNS)}
    assert ratio_grid_features(oi_ts, ratios, _hours(0, 4, 8, 12)) == expected


def test_a_ratio_row_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read():
    union = _hours(0, 4, 8, 12)
    assert ratio_grid_features(_hours(4, 12), _each_ratio([1.5, 2.5]), union) == _binperp([1.5, None, 2.5])
    younger = [DAY0 + timedelta(hours=4, seconds=1), DAY0 + timedelta(hours=12)]
    assert ratio_grid_features(younger, _each_ratio([1.5, 2.5]), union) == _binperp([None, 1.5, 2.5])


_TWO_BARS = [DAY0 + timedelta(hours=4, minutes=-10), DAY0 + timedelta(hours=4, minutes=-5), DAY0 + timedelta(hours=8, minutes=-5)]


def test_a_zero_taker_ratio_as_a_bars_last_row_is_read_never_mapped_to_none():
    ratios = _each_ratio([1.2, 1.3, 1.4]) | {"sum_taker_long_short_vol_ratio": [1.2, 0.0, 0.0]}
    # Mapped as an OI placeholder is, both closes would read None.
    assert ratio_grid_features(_TWO_BARS, ratios, _hours(0, 4, 8))["binperp_sum_taker_long_short_vol_ratio"] == [0.0, 0.0]


def test_a_null_ratio_as_a_bars_last_row_is_none_at_its_close_never_the_row_before_it():
    assert ratio_grid_features(_TWO_BARS, _each_ratio([1.2, None, 1.4]), _hours(0, 4, 8)) == _binperp([None, 1.4])


def test_ratio_grid_features_refuses_a_missing_ratio_column():
    with pytest.raises(FeatureError, match="missing ratio column"):
        ratio_grid_features(_hours(1, 5, 9), {name: [1.0, 1.1, 1.2] for name in _RATIO_COLUMNS[:3]}, _hours(0, 4, 8))


def test_ratio_grid_features_refuses_a_ratio_longer_than_the_rows_by_its_name():
    ratios = _each_ratio([1.0, 1.1, 1.2]) | {"count_long_short_ratio": [1.0, 1.1, 1.2, 1.3]}
    with pytest.raises(AlphaError, match="oi_ts and binperp_count_long_short_ratio must be equal length, got 3 and 4"):
        ratio_grid_features(_hours(1, 5, 9), ratios, _hours(0, 4, 8))


def test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_columns_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    # The fixture's `0.0`, bar 35's last row, is a null in three columns and a reading in the taker ratio.
    ratios = _each_ratio([None if v == 0.0 else v / 100 for v in oi_values]) | {
        "sum_taker_long_short_vol_ratio": [v / 100 for v in oi_values]
    }
    full = ratio_grid_features(oi_ts, ratios, union_ts)
    # Return index j closes bar 30 + j up to the missing open: bars 37 and 38 are stale and bar 240 lies past the rows in
    # every column; bar 35 reads None where its last row is null and 0.0 in the taker ratio.
    last = len(union_ts) - 2
    assert {name: [j for j, v in enumerate(values) if v is None] for name, values in full.items()} == {
        f"binperp_{name}": [7, 8, last] if name == "sum_taker_long_short_vol_ratio" else [5, 7, 8, last] for name in _RATIO_COLUMNS
    }
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = ratio_grid_features(
            [oi_ts[i] for i in visible], {name: [values[i] for i in visible] for name, values in ratios.items()}, union_ts[: n + 1]
        )
        assert prefix == {name: values[:n] for name, values in full.items()}, f"prefix at n={n} disagrees with the full run"
```

  The fixtures' arithmetic: the first case's rows stand 10 and 5 minutes before each of three closes, and column `i` holds `i + 1 + r / 10` at row `r`, so each close reads row 1, 3 or 5 of its own column. The 4 h case is spec `00131`'s OI case on the ratios: a row on the 04:00 mark is read there and is 4 h old at 08:00, so `None`; a row a second younger opens the rows' grid at 08:00, so the 04:00 close lies before it. `_TWO_BARS`' middle row is the 04:00 bar's last: the taker ratio's `0.0` there is read, and a null there leaves the close `None` where a fall-back would read the 1.2 before it. The refusals hold each check's silent shape: three columns, which the pipeline would read without complaint, and a column one longer than the rows, read by index; a shorter column fails downstream on its index. The prefix case reuses `_oi_prefix_fixture` — return index `j` closes bar `30 + j` up to the missing open of bar 100, bars 37 and 38 hold no row, bar 240 lies past the rows — its `0.0` at bar 35's last row a null in three columns and a reading in the taker ratio, so the `None` positions are `[5, 7, 8, last]` and `[7, 8, last]`. Run `mkdir -p .tmp/00136 && uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/00136/pt`: collection fails, `ImportError: cannot import name 'ratio_grid_features' from 'cli.alpha.b2'`.

- [ ] **Step 2 — the pipeline and the emitter** (`cli/alpha/b2.py`). In the `cli.features.derivatives` import, `    ratio_features,` goes below `    oi_zscore,`. `_oi_at_union_closes`, from its `def` through its `    return out`, is replaced by:

```python
def _validate_union_marks(union_ts: list[datetime]) -> None:
    _validate_stamps("union_ts", union_ts)
    for i, t in enumerate(union_ts):
        if (t - _EPOCH) % _BOUNDARY:
            raise AlphaError(f"union_ts[{i}] = {t.isoformat()} is not on a 4 h mark")


def _rows_at_union_closes(
    label: str,
    feature: Callable[[list[float | None]], list],
    oi_ts: list[datetime],
    values_name: str,
    levels: list[float | None],
    union_ts: list[datetime],
) -> list:
    """Every emitter over the OI file's 5-minute rows runs this one pipeline (docs/specs/00131 D4-D6, docs/specs/00136
    D2), the union's bar-open stamps in: `feature` runs over the value on `_oi_marks`' grid, never over the raw rows, and
    each union close reads it by exact lookup. A row is read from its own stamp, never truncated as a funding print's is:
    the stamp is when the venue measured the value."""
    if len(oi_ts) != len(levels):
        raise AlphaError(f"oi_ts and {values_name} must be equal length, got {len(oi_ts)} and {len(levels)}")
    _validate_stamps("oi_ts", oi_ts)
    _validate_union_marks(union_ts)
    marks = _oi_marks(oi_ts)
    # The as-of over row indices, so the bound below reads the stamp of the row each mark takes.
    rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)
    grid = [None if j is None or oi_ts[j] <= g - _BOUNDARY else levels[j] for j, g in zip(rows, marks)]
    values = dict(zip(marks, feature(grid)))
    out = [values.get(c) for c in close_grid(union_ts)]
    logger.debug(
        "%s at union closes: %d rows, %d marks, %d return indices, %d None",
        label,
        len(oi_ts),
        len(marks),
        len(out),
        out.count(None),
    )
    return out


def _oi_at_union_closes(
    label: str,
    feature: Callable[[list[float | None]], list],
    oi_ts: list[datetime],
    oi_values: list[float | None],
    union_ts: list[datetime],
) -> list:
    """The `sum_open_interest` level: a `0.0` placeholder is None before the as-of (docs/specs/00110 D5)."""
    return _rows_at_union_closes(f"oi {label}", feature, oi_ts, "oi_values", oi_levels_from_raw(oi_values), union_ts)
```

  Below `oi_momentum_grid_feature`, above `def _check_lengths(`:

```python
def ratio_grid_features(
    oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]
) -> dict[str, list[float | None]]:
    """Each ratio is read as a level, unmapped (docs/specs/00136 D2): a `0.0` taker ratio is an all-sell bar the venue
    published, never an OI placeholder."""
    return {
        name: _rows_at_union_closes(name, list, oi_ts, name, values, union_ts) for name, values in ratio_features(ratios).items()
    }
```

  The checks run in their old order — the length, the rows' stamps, the union's stamps, the union's marks — with their old messages, the length message naming `oi_values` for the four OI emitters, so spec `00131`'s cases read the same refusals; the debug line's label gains an `oi ` prefix from `_oi_at_union_closes` and reads the column's name for a ratio.

- [ ] **Step 3 — green**: the Step 1 command → `99 passed`; `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` → `0`; `uv run ruff format --check cli/alpha/b2.py tests/test_alpha_b2.py` → `2 files already formatted`, `uv run ruff check cli/alpha/b2.py tests/test_alpha_b2.py` → `All checks passed!`.

- [ ] **Step 4 — the consumers and the gate**: the consumers run (Global Constraints) passes; stage `cli/alpha/b2.py` and `tests/test_alpha_b2.py`; `uv run pre-commit run -a` until clean.

- [ ] **Step 5 — probes** on the commit's own tree (Global Constraints), each expected KILLED — the ratio rulings against the ratio cases, and the lifted pipeline's moved lines (the mapping, the length check, the union's two checks and their call) against spec `00131`'s OI cases (spec D2):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/oi_ts\[j\] <= g - _BOUNDARY/oi_ts[j] < g - _BOUNDARY/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_ratio_row_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/j is None or oi_ts\[j\] <= g - _BOUNDARY/j is None/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_ratio_row_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/_rows_at_union_closes(name, list, oi_ts, name, values, union_ts)/_rows_at_union_closes(name, list, oi_ts, name, oi_levels_from_raw(values), union_ts)/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_zero_taker_ratio_as_a_bars_last_row_is_read_never_mapped_to_none'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof([t for t, v in zip(oi_ts, levels) if v is not None], [i for i, v in enumerate(levels) if v is not None], marks)/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_null_ratio_as_a_bars_last_row_is_none_at_its_close_never_the_row_before_it'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/for name, values in ratio_features(ratios).items()/for name, values in ratios.items()/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_each_ratio_reads_its_bars_last_row_at_the_close_under_its_binperp_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/for name, values in ratio_features(ratios).items()/for name, values in ratios.items()/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_ratio_grid_features_refuses_a_missing_ratio_column'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/if len(oi_ts) != len(levels):/if False:/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_ratio_grid_features_refuses_a_ratio_longer_than_the_rows_by_its_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_grid_features(/def ratio_grid_features_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof(oi_ts, list(range(len(oi_ts))), [g + _BOUNDARY for g in marks])/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_columns_bit_for_bit'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/"oi_values", oi_levels_from_raw(oi_values), union_ts)/"oi_values", oi_values, union_ts)/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_zero_placeholder_is_none_at_the_close_it_reaches_never_the_level_before_it'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/if len(oi_ts) != len(levels):/if False:/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_lists_of_unequal_length[longer]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation '/^def _validate_union_marks(/,/^def /s/_validate_stamps("union_ts", union_ts)/None/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_unsorted_or_naive_stamps[unsorted-union]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/if (t - _EPOCH) % _BOUNDARY:/if False:/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_stamp_off_a_4h_mark_is_refused_by_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation '/^def _rows_at_union_closes(/,/^def /s/_validate_union_marks(union_ts)/None/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_stamp_off_a_4h_mark_is_refused_by_name'
```

  The fourth row is the fall-back spec D2 refuses, the as-of over the non-null rows alone; the eighth reads each mark from the bar after it, the look-ahead the prefix case exists for; the ninth leaves an OI placeholder unmapped, the mapping's move proven against the case that carried it before.

- [ ] **Step 6 — commit**: `feat(alpha): the B2 ratio columns read as levels at a union's 4h closes through the OI rows' one pipeline`, its body the Step 3 and Step 4 result lines and the thirteen rows, each with its verdict line; then `test "$(git rev-parse HEAD^{tree})" = "$TREE"`.

### Task 2 — the liquidations leg from the poller's tree

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

- [ ] **Step 1 — the failing tests** (`tests/test_alpha_b2.py`). `import shutil` goes below `import re`; `from pathlib import Path` below `from datetime import datetime, timedelta, timezone`; in the `from cli.alpha.b2 import (` block, `    liquidation_grid_features,` below `    funding_sign_grid_feature,`; `from cli.capture.segment_writer import LIQ_AGG_SCHEMA, SegmentWriter` below `from cli.alpha.errors import AlphaError`. Then, at the end of the file, after two blank lines:

```python
def _liquidation_tree(root: Path, buckets: dict[str, list[tuple[int, float, float]]], *, finalize: bool = True) -> Path:
    """`buckets[coin]` holds `(minute after DAY0, long_usd, short_usd)` in order, laid out by the poller's own writer;
    unfinalized, each coin's last hour stays as parts."""
    for coin, rows in buckets.items():
        writer = SegmentWriter(root, coin, "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
        for minute, long_usd, short_usd in rows:
            ts = DAY0 + timedelta(minutes=minute)
            symbol = f"{coin}USDT_PERP.A"
            event_id = f"{symbol}-{int(ts.timestamp())}"
            writer.append({"ts": ts, "symbol": symbol, "long_usd": long_usd, "short_usd": short_usd, "event_id": event_id})
        if finalize:
            writer.finalize_completed_hours(DAY0 + timedelta(days=365))
        writer.close()
    return root


# BTC holds a bucket in each hour from 00:00 to 15:00 but 09:00, which no tree holds; DOT one at 00:10 and one at 15:00;
# ETH one 46 h 30 min after DAY0, the tree's newest final, whose hour closes 31 h after 16:00, the union's last close.
_LIQUIDATIONS = {
    "BTC": [
        (5, 100.0, 0.0),
        (65, 0.0, 300.0),
        (130, 25.0, 25.0),
        (239, 50.0, 0.0),
        (240, 0.0, 80.0),
        (300, 20.0, 0.0),
        (370, 10.0, 0.0),
        (479, 0.0, 10.0),
        (485, 5.0, 0.0),
        (610, 0.0, 7.0),
        (700, 3.0, 0.0),
        (725, 1.0, 0.0),
        (790, 0.0, 2.0),
        (850, 4.0, 4.0),
        (950, 0.0, 6.0),
    ],
    "DOT": [(10, 0.0, 40.0), (900, 9.0, 0.0)],
    "ETH": [(60 * 46 + 30, 1.0, 0.0)],
}
_LIQUIDATION_UNION = _hours(0, 4, 8, 12, 16)


@pytest.fixture(scope="module")
def liquidation_root(tmp_path_factory):
    return _liquidation_tree(tmp_path_factory.mktemp("liquidations"), _LIQUIDATIONS)


def test_each_liquidation_column_sums_its_bars_buckets_under_its_lower_bound_name(liquidation_root):
    # The 03:59 bucket closes at 04:00 and is bar 0's; the 04:00 bucket is bar 1's. Bar 2 holds the uncovered 09:00.
    assert liquidation_grid_features(liquidation_root, "BTC", _LIQUIDATION_UNION) == {
        "binperp_liq_lowerbound_long_usd": [175.0, 30.0, None, 5.0],
        "binperp_liq_lowerbound_short_usd": [325.0, 90.0, None, 12.0],
        "binperp_liq_lowerbound_total_usd": [500.0, 120.0, None, 17.0],
        "binperp_liq_lowerbound_imbalance": [-0.3, -0.5, None, -7 / 17],
    }


def test_a_covered_bar_with_no_bucket_for_the_coin_reads_zero_notional_and_no_imbalance(liquidation_root):
    # DOT's own tree holds no hour from 01:00 to 14:00: BTC's is what shows the poller covered bar 1.
    assert liquidation_grid_features(liquidation_root, "DOT", _LIQUIDATION_UNION) == {
        "binperp_liq_lowerbound_long_usd": [0.0, 0.0, None, 9.0],
        "binperp_liq_lowerbound_short_usd": [40.0, 0.0, None, 0.0],
        "binperp_liq_lowerbound_total_usd": [40.0, 0.0, None, 9.0],
        "binperp_liq_lowerbound_imbalance": [-1.0, None, None, 1.0],
    }


def test_a_bar_holding_an_hour_no_tree_finalized_reads_none_never_zero(liquidation_root):
    # Read as a quiet hour, 09:00 would leave BTC's bar 2 the sum of its other three hours, 8.0 long and 7.0 short.
    for coin in ("BTC", "DOT"):
        features = liquidation_grid_features(liquidation_root, coin, _LIQUIDATION_UNION)
        assert [values[2] for values in features.values()] == [None] * 4


def test_an_hour_holding_only_parts_is_not_covered(tmp_path):
    # Closed unfinalized, BTC's writer leaves 07:00 as parts: the poller has not finished that hour. ETH's final at 38:30
    # puts the frontier on the union's last close, 08:00.
    _liquidation_tree(tmp_path, {"ETH": [(60 * 38 + 30, 1.0, 0.0)]})
    root = _liquidation_tree(tmp_path, {"BTC": _LIQUIDATIONS["BTC"][:8]}, finalize=False)
    assert liquidation_grid_features(root, "BTC", _hours(0, 4, 8))["binperp_liq_lowerbound_total_usd"] == [500.0, None]


def test_a_union_closing_on_the_finality_frontier_is_read_and_one_closing_a_step_past_it_is_refused(liquidation_root):
    # ETH's final is the newest: its hour closes at 47:00, and the frontier lies 31 h before, at 16:00.
    assert liquidation_grid_features(liquidation_root, "BTC", _LIQUIDATION_UNION)["binperp_liq_lowerbound_total_usd"][-1] == 17.0
    past = "union_ts closes at 2024-03-01T20:00:00+00:00, past the finality frontier (2024-03-01T16:00:00+00:00)"
    with pytest.raises(AlphaError, match=re.escape(past)):
        liquidation_grid_features(liquidation_root, "BTC", _hours(0, 4, 8, 12, 16, 20))


def test_a_tree_holding_no_final_refuses_every_union(tmp_path):
    root = _liquidation_tree(tmp_path, {"BTC": [(5, 100.0, 0.0)]}, finalize=False)
    with pytest.raises(AlphaError, match=re.escape("past the finality frontier (none, no final)")):
        liquidation_grid_features(root, "BTC", _hours(0, 4))


def test_a_coin_with_no_tree_under_the_root_is_refused_by_name(liquidation_root):
    # Read anyway, SOL would sum to zero at every bar BTC's tree covers.
    with pytest.raises(AlphaError, match=re.escape(f"no liquidations tree for 'SOL' under {liquidation_root}")):
        liquidation_grid_features(liquidation_root, "SOL", _LIQUIDATION_UNION)


def test_a_liquidation_union_stamp_off_a_4h_mark_is_refused_by_name(liquidation_root):
    with pytest.raises(AlphaError, match=re.escape("union_ts[1] = 2024-03-01T05:00:00+00:00 is not on a 4 h mark")):
        liquidation_grid_features(liquidation_root, "BTC", _hours(0, 5, 9))


def _hours_closed_by(src: Path, dst: Path, cutoffs: dict[str, datetime]) -> Path:
    """A copy of `src` holding each coin's hours that close at or before its cutoff: with a cutoff on the hour, exactly
    the buckets stamped before it, each closing a minute after its stamp."""
    for path in src.rglob("*.parquet*"):
        coin, _, year, month, day, name = path.relative_to(src).parts
        if datetime(int(year), int(month), int(day), int(name[:2]), tzinfo=UTC) + timedelta(hours=1) <= cutoffs[coin]:
            (dst / path.relative_to(src)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dst / path.relative_to(src))
    return dst


def test_a_truncated_prefix_of_the_buckets_reproduces_every_liquidation_column_bit_for_bit(tmp_path):
    # BTC holds a bucket in each of the 56 hours from DAY0 but the 13th and the 26th, DOT in eight of them, the 13th among
    # them: every hour is covered but the 26th, which no tree holds. ETH only witnesses finality: a final 30 hours after
    # each close the union can end on, which puts the tree's frontier on that close.
    btc = [(60 * h + (17 * h) % 60, float(h % 3), float(h % 4 + 1)) for h in range(56) if h not in (13, 26)]
    dot = [(60 * h + 30, 2.0, 0.0) for h in (0, 7, 13, 14, 21, 35, 42, 49)]
    eth = [(60 * h + 30, 1.0, 0.0) for h in range(38, 87, 4)]
    root = _liquidation_tree(tmp_path / "full", {"BTC": btc, "DOT": dot, "ETH": eth})
    # Return index j opens bar j + 1 up to the missing open of bar 7, bar j + 2 after it; the last closes on the last hour.
    union_ts = [t for t in _hours(*range(4, 60, 4)) if t != DAY0 + timedelta(hours=28)]
    full = {coin: liquidation_grid_features(root, coin, union_ts) for coin in ("BTC", "DOT")}
    # Exact: bar 6 holds the uncovered 26th hour in both trees, and DOT holds no bucket in bars 2, 4, 9, 11 and 13.
    assert [j for j, v in enumerate(full["BTC"]["binperp_liq_lowerbound_total_usd"]) if v is None] == [5]
    assert [j for j, v in enumerate(full["DOT"]["binperp_liq_lowerbound_total_usd"]) if v is None] == [5]
    assert [j for j, v in enumerate(full["DOT"]["binperp_liq_lowerbound_imbalance"]) if v is None] == [1, 3, 5, 7, 9, 11]
    for n in range(1, len(union_ts)):
        # The two coins read truncated at the cutoff, the witness 31 h past it: the union's last close is the frontier.
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        cutoffs = {"BTC": cutoff, "DOT": cutoff, "ETH": cutoff + timedelta(hours=31)}
        prefix_root = _hours_closed_by(root, tmp_path / f"n{n}", cutoffs)
        for coin, features in full.items():
            prefix = liquidation_grid_features(prefix_root, coin, union_ts[: n + 1])
            assert prefix == {name: values[:n] for name, values in features.items()}, f"{coin} prefix at n={n} disagrees"
```

  The fixtures' arithmetic: BTC's bar 0 sums 100 + 0 + 25 + 50 = 175 long and 0 + 300 + 25 + 0 = 325 short, the imbalance −150 / 500; bar 1, 20 + 10 = 30 long and 80 + 10 = 90 short, −60 / 120; bar 3, 1 + 4 = 5 long and 2 + 4 + 6 = 12 short, −7 / 17 — each sum exact in binary floating point and each quotient the division the test writes. DOT's two buckets give bar 0 40 short and bar 3 9 long; its bar 1 holds none of its own inside BTC's coverage. Bar 2 holds 09:00, which neither tree holds. ETH's one bucket, 46 h 30 min after DAY0, is the fixture's newest final: its hour closes at 47:00, so the frontier is 16:00, the union's last close — the boundary case reads that union and refuses the one closing at 20:00, a 4h step past. The parts case keeps BTC's first eight buckets, 00:05 to 07:59, unfinalized: the writer finalizes 00:00 to 06:00 as each later hour's bucket arrives and leaves 07:00 as `07.part0000.parquet` at `close()`; ETH's final at 38:30 puts that tree's frontier on its union's last close, 08:00. The no-final case leaves BTC's one bucket as parts, so the tree holds no final. The prefix case's trees hold 75 finals, BTC's 54 hours, DOT's eight and ETH's 13 — ETH only witnesses finality, a final every 4 h from hour 38 to hour 86, 30 hours after each close the union can end on, so the full run's frontier is 56:00, the union's last close, and each copy, the read coins truncated at the cutoff and ETH 31 h past it, has its frontier on the prefix union's last close while the hour after the cutoff stays absent from it (**Author's call**: truncating every coin at the cutoff would put the frontier 31 h before the prefix union's last close and refuse it, and truncating every coin 31 h past the cutoff would let a look-ahead of up to 31 h pass); the union's 12 return indices open bars 1–6 and 8–13, index 5 opening bar 6, which holds the 26th hour; bar 3 holds BTC's missing 13th hour, which DOT's tree covers; DOT's buckets fall in bars 0, 1, 3, 5, 8, 10 and 12, so its imbalance is `None` at the indices opening bars 2, 4, 9, 11 and 13 and at index 5. Run the Step 1 command of Task 1: collection fails, `ImportError: cannot import name 'liquidation_grid_features' from 'cli.alpha.b2'`.

- [ ] **Step 2 — the reader and the emitter** (`cli/alpha/b2.py`). `import re` goes below `import math`; `from pathlib import Path` below `from functools import partial`, then a blank line and `import polars as pl` above the `cli` imports, ruff's third-party section; `from cli.liquidations.coinalyze import _FINALIZE_LAG_SECONDS` goes on its own line above `from cli.logging import get_logger`, the lag's one copy. Below `_OI_MOMENTUM_LOOKBACK = 180`:

```python
_HOUR = timedelta(hours=1)
_FINALIZE_LAG = timedelta(seconds=_FINALIZE_LAG_SECONDS)
# A final the poller's writer committed, `<YYYY>/<MM>/<DD>/<HH>.parquet` under a coin's tree: parts, held spills and
# merging files are not final, so an hour holding only those is not read (docs/specs/00136 D3).
_LIQUIDATION_FINAL = re.compile(r"(\d{4})/(\d{2})/(\d{2})/(\d{2})\.parquet")
# The stream is a proxy, not the tape, and every column's name says so (docs/specs/00136 D5).
_LIQUIDATION_COLUMNS = (
    "binperp_liq_lowerbound_long_usd",
    "binperp_liq_lowerbound_short_usd",
    "binperp_liq_lowerbound_total_usd",
    "binperp_liq_lowerbound_imbalance",
)
```

  Below `ratio_grid_features`, above `def _check_lengths(`:

```python
def _liquidation_finals(tree: Path) -> dict[datetime, Path]:
    finals: dict[datetime, Path] = {}
    for path in tree.rglob("*.parquet"):
        if m := _LIQUIDATION_FINAL.fullmatch(path.relative_to(tree).as_posix()):
            finals[datetime(*map(int, m.groups()), tzinfo=UTC)] = path
    return finals


def liquidation_grid_features(root: Path, coin: str, union_ts: list[datetime]) -> dict[str, list[float | None]]:
    """The coin's 1-minute liquidation buckets as the poller lays them out under `root`, summed over each union bar
    (docs/specs/00136 D3-D6). An hour is covered when any coin's tree holds its final, since one poll fetches every coin:
    a covered bar with no bucket reads zero, a bar holding an uncovered hour None."""
    _validate_union_marks(union_ts)
    tree = root / coin / "liquidations-1m"
    if not tree.is_dir():
        raise AlphaError(f"no liquidations tree for {coin!r} under {root}")
    covered = {hour for other in root.glob("*/liquidations-1m") for hour in _liquidation_finals(other)}
    # The newest final's hour closed before the cycle that wrote it, and a cycle's sweep finalizes every coin's hour that
    # started more than 31 h before it: every hour closing by here is final for every coin (docs/specs/00136 D3).
    frontier = max(covered) + _HOUR - _FINALIZE_LAG if covered else None
    closes = close_grid(union_ts)
    if closes and (frontier is None or closes[-1] > frontier):
        bound = "none, no final" if frontier is None else frontier.isoformat()
        raise AlphaError(
            f"union_ts closes at {closes[-1].isoformat()}, past the finality frontier ({bound}) of the liquidations tree under {root}"
        )
    finals = _liquidation_finals(tree)
    out: dict[str, list[float | None]] = {name: [] for name in _LIQUIDATION_COLUMNS}
    for t in union_ts[:-1]:
        hours = [t + k * _HOUR for k in range(_BOUNDARY // _HOUR)]
        if not covered.issuperset(hours):
            for values in out.values():
                values.append(None)
            continue
        frames = [pl.read_parquet(finals[h], columns=["long_usd", "short_usd"]) for h in hours if h in finals]
        long_usd = sum((f["long_usd"].sum() for f in frames), 0.0)
        short_usd = sum((f["short_usd"].sum() for f in frames), 0.0)
        total = long_usd + short_usd
        imbalance = None if total == 0 else (long_usd - short_usd) / total
        for name, value in zip(_LIQUIDATION_COLUMNS, (long_usd, short_usd, total, imbalance)):
            out[name].append(value)
    logger.debug(
        "liquidations %s at union closes: %d finals, %d covered hours, %d return indices, %d None",
        coin,
        len(finals),
        len(covered),
        len(union_ts) - 1,
        out[_LIQUIDATION_COLUMNS[0]].count(None),
    )
    return out
```

  **Author's call:** a bar's hours are `range(_BOUNDARY // _HOUR)`, four, tied to the bar's width rather than a literal; and each final is read once per bar that holds its hour, the union's bars never overlapping; the frontier is the newest final's hour close less 31 h, an hour more conservative than the sweep's own bound (spec D3), and a tree holding no final refuses every union with a close.

- [ ] **Step 3 — green**: the Step 1 command of Task 1 → `108 passed`; `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` → `0`; the two ruff commands clean as in Task 1.

- [ ] **Step 4 — the consumers and the gate**: the consumers run passes — `520 passed, 2 skipped, 48 deselected`, measured at this tree; stage `cli/alpha/b2.py` and `tests/test_alpha_b2.py`; `uv run pre-commit run -a` until clean.

- [ ] **Step 5 — probes** on the commit's own tree, each expected KILLED:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/if not covered.issuperset(hours):/if False:/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_bar_holding_an_hour_no_tree_finalized_reads_none_never_zero'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/covered = {hour for other in .*$/covered = set(_liquidation_finals(tree))/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_covered_bar_with_no_bucket_for_the_coin_reads_zero_notional_and_no_imbalance'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/imbalance = None if total == 0 else/imbalance = 0.0 if total == 0 else/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_covered_bar_with_no_bucket_for_the_coin_reads_zero_notional_and_no_imbalance'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's|range(_BOUNDARY // _HOUR)|range(1, _BOUNDARY // _HOUR + 1)|' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_buckets_reproduces_every_liquidation_column_bit_for_bit'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's|(long_usd - short_usd) / total|(short_usd - long_usd) / total|' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_each_liquidation_column_sums_its_bars_buckets_under_its_lower_bound_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's|\\\.parquet")|(?:\\.part\\d{4})?\\.parquet")|' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_an_hour_holding_only_parts_is_not_covered'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/if not tree.is_dir():/if False:/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_coin_with_no_tree_under_the_root_is_refused_by_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation '/^def liquidation_grid_features(/,/^def /s/_validate_union_marks(union_ts)/None/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_liquidation_union_stamp_off_a_4h_mark_is_refused_by_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/"binperp_liq_lowerbound_imbalance",/"binperp_liq_imbalance",/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_each_liquidation_column_sums_its_bars_buckets_under_its_lower_bound_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/or closes\[-1\] > frontier):/or closes[-1] >= frontier):/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_closing_on_the_finality_frontier_is_read_and_one_closing_a_step_past_it_is_refused'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/frontier = max(covered) + _HOUR - _FINALIZE_LAG if covered/frontier = max(covered) - _FINALIZE_LAG if covered/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_closing_on_the_finality_frontier_is_read_and_one_closing_a_step_past_it_is_refused'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/if closes and (frontier is None or closes\[-1\] > frontier):/if False:/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_closing_on_the_finality_frontier_is_read_and_one_closing_a_step_past_it_is_refused'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's|_FINALIZE_LAG = timedelta(seconds=_FINALIZE_LAG_SECONDS)|_FINALIZE_LAG = timedelta(seconds=_FINALIZE_LAG_SECONDS // 2)|' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_closing_on_the_finality_frontier_is_read_and_one_closing_a_step_past_it_is_refused'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/or closes\[-1\] > frontier):/or closes[0] > frontier):/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_union_closing_on_the_finality_frontier_is_read_and_one_closing_a_step_past_it_is_refused'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_grid_features(/def liquidation_grid_features_gone(/' --mutation 's/(frontier is None or closes\[-1\] > frontier)/(closes[-1] > frontier)/' -- uv run pytest -q -p no:cacheprovider --basetemp=.tmp/pt 'tests/test_alpha_b2.py::test_a_tree_holding_no_final_refuses_every_union'
```

  The first two rows are spec D4 both ways — a gap read as a quiet hour, and coverage read from the coin's own tree alone; the fourth reads each bar's hours one later, its last the next bar's first, the look-ahead the prefix case exists for; the sixth lets a part count as a final (spec D3); the ninth renames a column off D5's provenance. The last six are spec D3's refusal: the frontier compared with `>=`, so a union closing on it is refused; the frontier taken from the newest final's hour start rather than its close; the refusal removed; the poller's lag halved; the union's first close compared in place of its last; and a tree with no final compared against no frontier.

- [ ] **Step 6 — commit**: `feat(alpha): the B2 liquidations leg per union bar from the poller's tree, an hour covered when any coin's tree holds its final`, its body the Step 3 and Step 4 result lines and the fifteen rows, each with its verdict line; then `test "$(git rev-parse HEAD^{tree})" = "$TREE"`.

### Task 3 — the decisions log: six `[00136]` entries

**Files:** `docs/research/10.phase4-decisions.md`.

- [ ] **Step 1 — the entries** (R1 as amended at 2026-10-19T15:39:57Z; `iteration-closeout`'s shape, as the six `[00131]` entries the backfill `1fe25796f` wrote). At the end of the file, one blank line below its last entry, one entry per decision D1–D6 — the question, the ruling it rests on, two or three options each with its tradeoff, the pick marked `(Decision: N)` with its one-line why, and its source:

```markdown
[00136] T0023's two remaining autonomous emission items, the ratio columns and the liquidations leg: one spec or a spec each, and where do they sit? (Decision: 1)
  The controller's ruling R1, one of R1–R6 of 2026-10-19 in the attended session, on the owner's words "directly run C for B1, then B2‘s data work, then B2 baseline ruling" and, after #738, "yes, start the B2 data work after the merge"; R1 and R3 amended at 2026-10-19T15:39:57Z after the author's report.
  1. **One spec, both emitters in `cli/alpha/b2.py`** beside spec 00131's, each returning named columns, one value per return index at `close_grid(union_ts)`; no subject, no registry record, no trial; the Bybit funding cross-check stays a nice-to-have on T0023. Chosen: emission infrastructure the next B2 pre-registration names, and the owner's word that day, "the transient issue shouldn't be over prepared", keeps the design minimal.
  2. **A spec each** — two review cycles for two small emitters that share the 4h close grid and the union's checks.
  3. **The Bybit cross-check beside them** — a robustness check no B2 trial waits on.
  Logged 2026-10-19, from docs/specs/00136-b2-ratio-liquidation-features-design.md D1.

[00136] The four Binance ratios at a union's 4h closes: read as levels through the OI level's pipeline, a `0.0` mapped as an OI placeholder is, or a null falling back to the row before it? (Decision: 1)
  1. **Read as levels through spec 00131's pipeline, unmapped** — its regular grid over the rows' span, its staleness bound `mark − 4h < ts ≤ mark` and its raw stamps; names and validation `ratio_features`'; the placeholder mapping lifted out of the shared pipeline into its OI caller; a null as a bar's last row `None` at that close. Chosen (the controller's ruling R2): the ratios are columns of the OI level's own rows, and a `0.0` taker ratio is an all-sell bar the venue published (spec 00110 D5) — 45 rows, and the bar's last row at 6 marks.
  2. **A `0.0` mapped to `None` as an OI placeholder is** — those 6 closes would read `None` where the venue published a reading.
  3. **A null falling back to the row before it** — a reading the venue did not show at that stamp, against spec 00110 D5's no-imputation rule; 19,205, 19,194, 1,211 and 7,759 of the 104,446 marks read `None` under option 1.
  Logged 2026-10-19, from docs/specs/00136-b2-ratio-liquidation-features-design.md D2.

[00136] The liquidations leg's data: the Coinalyze poller's live tree in place or a frozen copy, which files count, and how close to the tree's newest hour may a union reach? (Decision: 1)
  1. **The poller's tree in place, finals only, a union refused past the tree's finality frontier** — `liquidation_grid_features(root, coin, union_ts)` reads `<root>/<coin>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet`, never a part, a held spill or a merging file; a coin with no tree is refused by name; a union whose last close lies past the newest final's hour close less `_FINALIZE_LAG_SECONDS`, 31 h, imported from `cli.liquidations.coinalyze`, is refused naming both stamps. Chosen (the controller's ruling R3, its refusal ruled at 2026-10-19T15:39:57Z): freezing a block is the pre-registration of the first trial that reads it, and inside the newest 31 h a sparse coin's buckets may still sit in the writer's memory while another coin's final covers the hour; at the read the frontier was 2026-10-18T08:00Z. If wrong, a caller cuts its union about 31 h back.
  2. **A frozen copy or a new dataset directory now** — a freeze before any trial pre-registers its block.
  3. **The frontier left to the caller, the author's first draft** — an unchecked union reads a sparse coin low inside the newest 31 h, and higher on a later read. Amended by the refusal.
  Logged 2026-10-19, from docs/specs/00136-b2-ratio-liquidation-features-design.md D3.

[00136] Liquidation coverage: when does a 4h bar with no bucket read zero, and when `None`? (Decision: 1)
  1. **An hour is covered when any coin's tree holds its final; a covered bar with no bucket reads zero, a bar holding an uncovered hour `None`** — one poll fetches all ten coins, so the poller's uptime is one fact for the ten. Chosen (the controller's ruling R4, read as the author corrected it): a coin's own tree writes nothing for a quiet hour, the bucket watermark lives in memory and is never durable, and a manifest exists only beside a final; measured, none of the 2,302 closed hours from 2026-07-14T10Z lacks every coin's final, while the coins' own trees lack 11 (ETH) to 828 (LTC) of them.
  2. **Coverage from the coin's own tree** — a quiet hour and a gap leave the same nothing, so LTC would read 828 quiet hours as gaps.
  3. **No coverage rule, a bar with no bucket always zero** — a poller gap would read as a quiet market, a manufactured zero.
  Logged 2026-10-19, from docs/specs/00136-b2-ratio-liquidation-features-design.md D4.

[00136] How does a liquidation column say it comes from a lossy stream? (Decision: 1)
  1. **`binperp_liq_lowerbound_` names** — `long_usd`, `short_usd`, `total_usd` and `imbalance`, stated once: the three notionals are lower bounds of the notional liquidated on the venue, and the imbalance names its stream and bounds nothing. Chosen (the controller's ruling R5, read as the author corrected it): the stream is a lower-bound proxy, not the tape, the catalog's hard caveat, and the name is the one place the caveat survives every downstream join.
  2. **A lower-bound suffix on every name** — it would call the imbalance a lower bound, which a ratio of two undercounts is not.
  3. **Plain `binperp_liq_` names, the caveat in the documentation** — a column beside the funding and OI columns would read as the venue's tape.
  Logged 2026-10-19, from docs/specs/00136-b2-ratio-liquidation-features-design.md D5.

[00136] The liquidation features per 4h bar, and a spike flag? (Decision: 1)
  1. **The long, short and total notional summed over the bar's buckets and the imbalance `(long − short) / total`, `None` at a zero total; no spike flag** — a bucket stamped in `[open, open + 4h)` is the bar's. Chosen (the controller's ruling R6, the definitions the author's call): a spike is a threshold either fitted to the data or a trial's pre-registration, and the scale offers no unfitted one — the median bucket 404 to 4,819 USD across the coins, the largest 838,953 to 68,253,711; the leg's only history is the live tape since 2026-07-14, so a 30-day window would spend 180 of its 575 closed bars warming.
  2. **A spike flag at a multiple of a trailing median or past a z-score cut** — a threshold chosen before any trial pre-registers it.
  3. **Windowed features, a z-score or a persistence over the totals** — each a trial's pre-registration, built over these sums.
  Logged 2026-10-19, from docs/specs/00136-b2-ratio-liquidation-features-design.md D6.
```

  The figures are the spec's measured basis's, and the log stays off the mdformat allowlist, so nothing reflows it. A merge of develop that meets another branch's entries at the log's end keeps both by hand and takes a re-review (`iteration-closeout`). Checks: `grep -c '^\[00136\]' docs/research/10.phase4-decisions.md` prints 6, and `mkdir -p .tmp/00136 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/00136/pt`, the log's two glob readers, passes (measured `50 passed`).

- [ ] **Step 2 — commit** after the gate: `docs(research): 00136 — six decisions on B2's ratio columns and liquidations leg in phase 4's log`.

### Task 4 — T0023: the two items delivered

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`.

- [ ] **Step 1 — the edit** (`topic-ops`' edit mechanics: each anchor's `grep -c` reads 1 first, and `grep '^#'` of the file reads the same headings before and after). In `## Done so far`, below the bullet opening `- **B2's remaining funding and OI features on the 4h close grid DELIVERED (spec/plan `00131`)**`, one blank line and then:

```markdown
- **B2's ratio columns and liquidations leg on the 4h close grid DELIVERED (spec/plan `00136`)**: `cli/alpha/b2.py` — `ratio_grid_features`, the four Binance ratios under their `binperp_` names, each read as a level through the OI level's pipeline on spec `00131`'s regular grid with its staleness bound, a `0.0` taker ratio a reading and a null as a bar's last row `None`, never the row before it; and `liquidation_grid_features`, which reads the Coinalyze poller's tree in place, finals only, and gives per union bar the long, short and total liquidated notional and their imbalance under `binperp_liq_lowerbound_` names, the stream a proxy and not the tape. An hour is covered when any coin's tree holds its final, since one poll fetches all ten, so a covered bar with no bucket reads zero and a bar holding an uncovered hour `None` — no such hour in the 2,302 closed hours measured from 2026-07-14T10Z, where LTC's own tree lacks 828. No spike flag: a threshold on these totals is a trial's pre-registration. A union whose last close lies past the tree's finality frontier — the newest final's hour close less the poller's 31 h finalization lag — is refused, so every hour read is final for every coin. No subject, no registry record.
```

  In `## Suggested next steps`, the bullets opening `- **(autonomous) the ratio columns on the 4h close grid.**` and `- **(autonomous) the liquidations feature leg.**` are deleted, and the bullet opening `- **(later trials, after the instrument ruling, each its own pre-registration against the shared B budget)**` is replaced whole by:

```markdown
- **(later trials, after the instrument ruling, each its own pre-registration against the shared B budget)** the OI leg, the z < −2 re-risk, and the threshold, scale or window variants spec `00128` names; a liquidations trial freezes its block of the live tape as its pre-registration, its union closing at or before the block's finality frontier, and defines any spike threshold there (spec `00136` D3, D6).
```

  The Bybit cross-check stays a nice-to-have, and the instrument ruling stays the owner's. `status` and `ripe_when` do not change, so the index is not re-rendered: `uv run python infra/scripts/topics-index.py --check` exits 0, and `mkdir -p .tmp/00136 && uv run pytest tests/test_open_topics_frontmatter.py -q -p no:cacheprovider --basetemp=.tmp/00136/pt` passes (measured `1104 passed`).

- [ ] **Step 2 — commit** after the gate — `infra/scripts/consumers.sh --direct` lists no test for the topic file: `docs(open-topics): T0023 — B2's ratio columns and liquidations leg on the 4h close grid delivered`.

### Task 5 — the reads and the PR (the controller's)

- [ ] `git diff --quiet develop HEAD -- cli/features cli/liquidations cli/capture cli/research` exits 0.
- [ ] `mkdir -p .tmp/00136 && uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/00136/pt` → `108 passed`; the 28 probe verdicts of Tasks 1–2, each `KILLED`, carried into the PR body.
- [ ] The repo's trio over the branch: `pre-review`, `review`, `re-review` at most twice; push only after the read; the PR through `open-pr` — `feat(alpha): 00136 — B2's ratio columns and liquidations leg on the 4h close grid`, its body naming the read line, the probe verdicts and T0023's update; the change-index row; merge on the owner's word through `merge-pr`; the two data links (`data/derivatives-funding`, `data/derivatives-oi`) unlinked before `git worktree remove`, the main checkout's `data/` listing read after.
- [ ] Decisions log: Task 3's six `[00136]` entries in `docs/research/10.phase4-decisions.md`, committed before the whole-branch read so the read covers them.
