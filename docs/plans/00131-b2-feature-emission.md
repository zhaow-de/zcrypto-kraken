# B2's remaining funding and OI features on the 4h close grid — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `docs/specs/00131-b2-feature-emission-design.md` — `cli/alpha/b2.py` emits the funding sign run and accrued carry through the z-score's one print pipeline, the OI level on a regular 4h grid over the OI rows' own span, and the OI log-delta, z-score and momentum over that grid series, each read at the union's closes and proven on known answers and the truncating-prefix property; T0023 records the emission delivered and the 1h grid dropped.

**Architecture:** one module, `cli/alpha/b2.py`, beside `funding_grid_feature`: a private print pipeline `_funding_on_close_grid` that `funding_grid_feature` and the two new funding emitters call (spec D2), a print reaching only the closes before its next settlement (spec D5), a private OI pipeline `_oi_at_union_closes` that `oi_grid_levels` and the three OI emitters call — the level on the regular 4h grid of `_oi_marks` with its staleness bound, the feature over that grid series, each union close read by exact lookup (spec D4–D6); the windows are module constants (spec D3). Pure functions over lists, the harness's own functions from `cli/features/derivatives.py` doing the arithmetic. No subject, no registry record, no data read by any test.

**Tech stack:** Python 3.14 through uv; pytest; the repo's `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`.

## Global Constraints

- TDD per task: the failing test first, the implementation second, the test green third. Every guard is proven with `infra/scripts/mutate-probe.sh` after the task's commit (it refuses a dirty tree), in the form `--file cli/alpha/b2.py --control 's/^def X(/def X_gone(/' --mutation '<sed>' -- uv run pytest -q '<node id>'`, `X` a function the case's module imports, so the control fails the case at collection; one probe at a time, each its own call after the previous verdict is read. Before each probe, its dry run: `sed -e '<sed>' cli/alpha/b2.py | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0; `diff <(sed -e '<sed>' cli/alpha/b2.py) cli/alpha/b2.py | grep -c '^>'` prints 1 — the sed changes one line, its site standing once or its address holding one; `grep -c '^def X(' cli/alpha/b2.py` prints 1. Each verdict line goes in the task report and the PR body, naming the script.
- Before each commit, the consumers of each changed file (`infra/scripts/consumers.sh <path>`), the union, in parts each under about 400 s — `tests/test_cache_restart.py` split by node id into three parts, `tests/test_converge_sh.py` and `tests/test_research_command.py` each its own part, a part that runs past about 400 s split again, nothing backgrounded — deselecting in every run the cases that read a mount or a holdout set: `tests/test_engine_tracking.py::test_simulated_fills_produce_a_non_degenerate_report`, `tests/test_engine_tracking.py::test_the_floor_figures_match_accum_replay_for_the_same_window` and `tests/test_engine_tracking.py::test_the_verdict_is_insufficient_data_before_three_complete_weeks` (their fixtures copy `/mnt/zhao-crypto/engine-journal`), `tests/test_data_manifest.py::test_path_order_re_anchors_the_hub_reach_continuous_digest_and_the_move_is_deliberate` (it reads `/mnt/zhao-crypto/hot`), `tests/test_registry_observed.py::test_loader_reproduces_the_frozen_full_set_extents[ohlc-holdout-2026-07-10]`. The union over the three files is 72 test files. Never `tests/test_grafana_push_sh.py`; never the full suite.
- Data: no test and no step reads a dataset — every fixture is synthetic, so `tests/test_research_b2_basis.py`, a consumer of `cli/alpha/b2.py` gated on `data/ohlc-rolling`, skips in every run here, and each task report and the PR body name it skipped, with that reason. `data/derivatives-funding` and `data/derivatives-oi` are linked into the worktree for the spec's measured basis alone; never `data/ohlc-holdout-*`, never `/mnt/zhao-crypto/`; no ssh; never `kraken`. Never look for, open, count or quote any real account export anywhere outside the repository's tracked fixtures.
- Never write `docs/reference/trial-registry.jsonl`, `docs/reference/reading-ledger.jsonl` or a decisions log; never `zcrypto research eval`; never compute a return or a performance number; never `git stash`; no amend.
- `cli/features/derivatives.py`, `cli/research/subjects.py` and the spec are not edited. No task's diff removes a line of `tests/test_alpha_b2.py`: `funding_grid_feature`'s existing tests are spec D2's proof of the refactor, and `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` prints 0 after every task.
- No string literal under `cli/` — an error message, a log line — carries `spec <NNNNN>`, `D<N>`, `T<NNNN>` or `iter-<N>` (`tests/test_internal_terms_not_operator_visible.py`), and no code prose carries a plan-task number without its serial (`tests/test_code_prose_citations.py`); comments and docstrings cite `docs/specs/00131 D<N>`.
- Commits by kind, each task its own commit, no amend: `feat(alpha)` for Tasks 1–3, `docs(open-topics)` for Task 4. The gate is `uv run pre-commit run -a`, re-run until clean, staging by explicit path. Trailers: `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01Dr2kJsYt2KVuf7VUBuvyhF`.
- Scratch under this worktree's `.tmp/<role>/`, removed at the end of the task.

______________________________________________________________________

### Task 1 — the shared print pipeline, the sign run and the accrued carry

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

- [ ] **Step 1 — the failing tests** (`tests/test_alpha_b2.py`). `from cli.alpha import b2` goes on its own line above `from cli.alpha.b1 import book_turnover`; in the `from cli.alpha.b2 import (` block, `    funding_carry_grid_feature,` goes above `    funding_grid_feature,` and `    funding_sign_grid_feature,` below it. Then, at the end of the file, after two blank lines:

```python
# The sign runs these prints score are 1, 2, 1, 1, 2, 1, 2; 13 return indices close every 4 h from 04:00.
_SIGN_PRINTS = _hours(0, 8, 16, 24, 32, 40, 48)
_SIGN_RATES = [1e-4, 2e-4, 0.0, -1e-4, -3e-4, 2e-4, 1e-4]
_SIGN_UNION = _hours(*range(0, 56, 4))
# The carry over the 90 prints ending at the 90th, 91st and 92nd print is 4095e-6, 4185e-6 and 4275e-6.
_CARRY_PRINTS = _hours(*range(0, 8 * 92, 8))
_CARRY_RATES = [(i + 1) * 1e-6 for i in range(92)]
_CARRY_UNION = _hours(*range(704, 736, 4))


def test_the_sign_run_counts_prints_never_bars_as_of_each_close():
    # Fed the aligned grid instead, each print would count once per bar it carries across: 1, 2, 3, 1, 2, 1, 2, 3, 4, ...
    assert funding_sign_grid_feature(_SIGN_PRINTS, _SIGN_RATES, [8] * 7, _SIGN_UNION) == [1, 2, 2, 1, 1, 1, 1, 2, 2, 1, 1, 2, 2]


def test_an_off_cadence_print_breaks_the_sign_run_and_is_none_while_it_is_the_latest_print():
    intervals = [8, 8, 8, 4, 8, 8, 8]
    rates = _SIGN_RATES[:4] + [0.0] + _SIGN_RATES[5:]
    # Dropped instead of mapped, the 32 h and 36 h closes would continue the 16 h print's zero run, 2.
    expected = [1, 2, 2, 1, 1, None, None, 1, 1, 1, 1, 2, 2]
    assert funding_sign_grid_feature(_SIGN_PRINTS, rates, intervals, _SIGN_UNION) == expected


def test_the_accrued_carry_sums_the_latest_90_prints_as_of_each_close():
    feature = funding_carry_grid_feature(_CARRY_PRINTS, _CARRY_RATES, [8] * 92, _CARRY_UNION)
    # The 704 h print is the 89th, its window one print short.
    assert feature == [None] + [pytest.approx(v * 1e-6) for v in (4095, 4095, 4185, 4185, 4275, 4275)]


def test_an_off_cadence_print_leaves_every_carry_window_holding_it_none():
    intervals = [8, 4] + [8] * 90
    # Dropped instead of mapped, the 720 h print would sum the 90 prints left before it, 4184e-6.
    expected = [None] * 5 + [pytest.approx(4275e-6)] * 2
    assert funding_carry_grid_feature(_CARRY_PRINTS, _CARRY_RATES, intervals, _CARRY_UNION) == expected


def test_the_carry_window_is_the_pre_registered_90_prints():
    assert b2._CARRY_WINDOW == 90


# Each emitter's fixture, the print a test moves, and the return index its own hour closes, where its value differs from
# the one carried before it.
_NEW_FUNDING_EMITTERS = [
    pytest.param(funding_sign_grid_feature, _SIGN_PRINTS, _SIGN_RATES, _SIGN_UNION, 4, 7, id="sign"),
    pytest.param(funding_carry_grid_feature, _CARRY_PRINTS, _CARRY_RATES, _CARRY_UNION, 90, 3, id="carry"),
]


@pytest.mark.parametrize(("emitter", "prints", "rates", "union", "moved", "at"), _NEW_FUNDING_EMITTERS)
def test_every_new_funding_emitter_reads_a_print_30ms_past_its_hour_as_that_hours_settlement(
    emitter, prints, rates, union, moved, at
):
    late = [t + timedelta(milliseconds=30) if i == moved else t for i, t in enumerate(prints)]
    on_hour = emitter(prints, rates, [8] * len(rates), union)
    assert on_hour[at] != on_hour[at - 1]
    assert emitter(late, rates, [8] * len(rates), union) == on_hour


@pytest.mark.parametrize(("emitter", "prints", "rates", "union", "moved", "at"), _NEW_FUNDING_EMITTERS)
def test_every_new_funding_emitter_refuses_a_print_61s_past_its_hour_by_name(emitter, prints, rates, union, moved, at):
    late = [t + timedelta(seconds=61) if i == moved else t for i, t in enumerate(prints)]
    with pytest.raises(AlphaError, match=re.escape(f"prints_ts[{moved}] = {late[moved].isoformat()}")):
        emitter(late, rates, [8] * len(rates), union)


@pytest.mark.parametrize("emitter", [funding_sign_grid_feature, funding_carry_grid_feature], ids=["sign", "carry"])
def test_a_truncated_prefix_of_the_print_inputs_reproduces_every_new_funding_emitter_bit_for_bit(emitter):
    rates = [((7 * i) % 11 - 5) * 1e-5 for i in range(120)]
    prints_ts = [DAY0 + timedelta(hours=8 * i, milliseconds=7 * (i % 3)) for i in range(len(rates))]
    union_ts = _hours(*range(764, 900, 4))
    full = emitter(prints_ts, rates, [8] * len(rates), union_ts)
    assert len(full) == len(union_ts) - 1 and None not in full
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(prints_ts) if t.replace(minute=0, second=0, microsecond=0) <= cutoff]
        prefix = emitter([prints_ts[i] for i in visible], [rates[i] for i in visible], [8] * len(visible), union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


_FUNDING_EMITTERS = [
    pytest.param(lambda *inputs: funding_grid_feature(*inputs, config=B2Config()), id="zscore"),
    pytest.param(funding_sign_grid_feature, id="sign"),
    pytest.param(funding_carry_grid_feature, id="carry"),
]


@pytest.mark.parametrize("emitter", _FUNDING_EMITTERS)
def test_every_funding_emitter_reads_none_from_the_close_a_settlement_past_its_last_print(emitter):
    # The last print settles at 728 h: the 732 h close still reads it, and from 736 h the next settlement is due and absent.
    feature = emitter(_CARRY_PRINTS, _CARRY_RATES, [8] * 92, _hours(*range(720, 748, 4)))
    assert None not in feature[:3] and feature[2] == feature[1] and feature[3:] == [None] * 3


@pytest.mark.parametrize("emitter", _FUNDING_EMITTERS)
@pytest.mark.parametrize(
    ("prints_ts", "intervals", "union_ts", "named"),
    [
        pytest.param(_PRINTS, [8] * 5, _UNION, "equal length", id="longer-intervals"),
        pytest.param(_hours(0, 8, 8, 24), [8] * 4, _UNION, "prints_ts", id="duplicate-prints"),
        pytest.param(_PRINTS, [8] * 4, _hours(8, 12, 12, 16, 20), "union_ts", id="duplicate-union"),
    ],
)
def test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently(emitter, prints_ts, intervals, union_ts, named):
    with pytest.raises(AlphaError, match=named):
        emitter(prints_ts, RATES, intervals, union_ts)
```

  The fixtures' arithmetic: the sign prints' runs are 1, 2, 1, 1, 2, 1, 2 and close `j` reads the print at or before `4(j + 1)` h; the carry's 89th print (index 88, 704 h) has 89 prints, so its window is short, and the next three sum `(1..90)`, `(2..91)`, `(3..92)` millionths. The prefix fixture's 96th print (760 h) precedes the first close (768 h), so the carry is defined at every close. The settlement case runs the carry fixture's 92 prints, the z-score's 90-print window defined from the 90th, to closes past the last print: each emitter reads it at 728 h and 732 h, and `None` from 736 h, where the next settlement is due (spec D5). The refusal case holds one silent shape of each check, one the pipeline reads without it: an intervals list longer than the prints, zipped short, and a repeated print or union stamp, which `align_asof` takes as-of. The existing cases' shapes fail downstream without their check — a shorter list on an index, an unsorted list in `align_asof` — and naive stamps have none: against aware stamps they fail at the first comparison, and beside a naive other list that list's own check refuses them. Run `uv run pytest -q tests/test_alpha_b2.py`: collection fails, `ImportError: cannot import name 'funding_carry_grid_feature' from 'cli.alpha.b2'`.

- [ ] **Step 2 — the pipeline and the two emitters** (`cli/alpha/b2.py`). The import head, from `import math` to the `cli.features.derivatives` import, becomes:

```python
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial

from cli.alpha.errors import AlphaError
from cli.features.derivatives import (
    align_asof,
    funding_accrued_carry,
    funding_sign_persistence,
    funding_zscore,
)
```

  Below `_FUNDING_INTERVAL_HOURS = 8`:

```python
_SETTLEMENT_INTERVAL = timedelta(hours=_FUNDING_INTERVAL_HOURS)
# Pre-registered 30-day windows (docs/specs/00110 D7, docs/specs/00131 D3), not knobs: a change to one is a new trial.
_CARRY_WINDOW = 90
```

  And `funding_grid_feature`, from its `def` through `    return align_asof(normalised, z, close_grid(union_ts))`, is replaced by:

```python
def _funding_on_close_grid(
    label: str,
    feature: Callable[[list[float | None]], list],
    prints_ts: list[datetime],
    prints_rate: list[float | None],
    prints_interval_hours: list[int],
    union_ts: list[datetime],
) -> list:
    """Every funding emitter's one print pipeline (docs/specs/00131 D2), where docs/specs/00128 D2's two stamp rulings
    live: the print stamp truncated to its hour, and `feature`'s print-indexed output as-of on `close_grid`, a print
    reaching a close only before the next settlement is due (docs/specs/00131 D5) -- past a series' last print the
    as-of would carry it on. An off-cadence print is mapped to None before `feature`, never dropped: dropping it would
    let a window span a different horizon under the same label."""
    if not len(prints_ts) == len(prints_rate) == len(prints_interval_hours):
        raise AlphaError(
            "prints_ts, prints_rate and prints_interval_hours must be equal length, "
            f"got {len(prints_ts)}, {len(prints_rate)} and {len(prints_interval_hours)}"
        )
    _validate_stamps("prints_ts", prints_ts)
    _validate_stamps("union_ts", union_ts)

    normalised: list[datetime] = []
    for i, t in enumerate(prints_ts):
        hour = t.replace(minute=0, second=0, microsecond=0)
        if t - hour > _STAMP_TOLERANCE:
            raise AlphaError(
                f"prints_ts[{i}] = {t.isoformat()} is {t - hour} past its hour, beyond the "
                f"{_STAMP_TOLERANCE.total_seconds():.0f} s settlement tolerance"
            )
        normalised.append(hour)

    rates = [r if h == _FUNDING_INTERVAL_HOURS else None for r, h in zip(prints_rate, prints_interval_hours)]
    values = feature(rates)
    logger.debug(
        "funding %s grid feature: %d prints, %d off-cadence mapped to None, %d return indices",
        label,
        len(prints_ts),
        sum(h != _FUNDING_INTERVAL_HOURS for h in prints_interval_hours),
        len(union_ts) - 1,
    )
    closes = close_grid(union_ts)
    # The as-of over print indices, so the bound below reads the hour of the print each close takes.
    latest = align_asof(normalised, list(range(len(normalised))), closes)
    return [None if j is None or normalised[j] <= c - _SETTLEMENT_INTERVAL else values[j] for j, c in zip(latest, closes)]


def funding_grid_feature(
    prints_ts: list[datetime],
    prints_rate: list[float | None],
    prints_interval_hours: list[int],
    union_ts: list[datetime],
    *,
    config: B2Config,
) -> list[float | None]:
    """The trailing funding z-score as-of each return index's close (docs/specs/00128 D2): the union's bar-open stamps
    in, `len(union_ts) - 1` values out, the stamps raw -- a caller shifts none itself."""
    if not isinstance(config, B2Config):
        raise AlphaError(f"config must be a B2Config, got {type(config)!r}")
    zscore = partial(funding_zscore, window=config.z_window)
    return _funding_on_close_grid("z-score", zscore, prints_ts, prints_rate, prints_interval_hours, union_ts)


def funding_sign_grid_feature(
    prints_ts: list[datetime], prints_rate: list[float | None], prints_interval_hours: list[int], union_ts: list[datetime]
) -> list[int | None]:
    return _funding_on_close_grid("sign run", funding_sign_persistence, prints_ts, prints_rate, prints_interval_hours, union_ts)


def funding_carry_grid_feature(
    prints_ts: list[datetime], prints_rate: list[float | None], prints_interval_hours: list[int], union_ts: list[datetime]
) -> list[float | None]:
    carry = partial(funding_accrued_carry, window=_CARRY_WINDOW)
    return _funding_on_close_grid("accrued carry", carry, prints_ts, prints_rate, prints_interval_hours, union_ts)
```

  The config check stays first in `funding_grid_feature`, the pipeline's checks then run in their old order, and its error messages are the old ones, so the existing tests read the same refusals. The settlement bound is the one change to what `funding_grid_feature` returns: a close a settlement or more past its as-of print reads `None` where the old line carried the print, and inside the substrate no close is (spec D5), so `b2-funding-derisk`'s window reads what it read.

- [ ] **Step 3 — green**: `uv run pytest -q tests/test_alpha_b2.py` → `69 passed`; `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` → `0`.

- [ ] **Step 4 — commit** after the consumers of the two files and the gate: `feat(alpha): the B2 funding sign run and accrued carry on the 4h close grid, through the z-score's one print pipeline, each print read to its next settlement`.

- [ ] **Step 5 — probes**, each expected KILLED; the pipeline's lines are probed against `funding_grid_feature`'s existing cases and against each new emitter's (spec D2) — the settlement bound, which no existing case reaches, against each emitter's settlement case, and each check against each emitter's silent shape — and each emitter's feeding against its known answer:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/normalised.append(hour)/normalised.append(t)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_print_30ms_past_its_hour_aligns_as_the_on_hour_print'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/normalised.append(hour)/normalised.append(t)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_new_funding_emitter_reads_a_print_30ms_past_its_hour_as_that_hours_settlement[sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/normalised.append(hour)/normalised.append(t)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_new_funding_emitter_reads_a_print_30ms_past_its_hour_as_that_hours_settlement[carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/if t - hour > _STAMP_TOLERANCE:/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_print_61s_past_its_hour_is_refused_by_name_and_one_60s_past_aligns_as_on_the_hour'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/if t - hour > _STAMP_TOLERANCE:/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_new_funding_emitter_refuses_a_print_61s_past_its_hour_by_name[sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/if t - hour > _STAMP_TOLERANCE:/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_new_funding_emitter_refuses_a_print_61s_past_its_hour_by_name[carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/\[r if h == _FUNDING_INTERVAL_HOURS else None for r, h in/[r for r, h in/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_an_off_cadence_print_is_mapped_to_none_so_every_window_holding_it_is_none'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/\[r if h == _FUNDING_INTERVAL_HOURS else None for r, h in/[r for r, h in/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_an_off_cadence_print_breaks_the_sign_run_and_is_none_while_it_is_the_latest_print'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/\[r if h == _FUNDING_INTERVAL_HOURS else None for r, h in/[r for r, h in/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_an_off_cadence_print_leaves_every_carry_window_holding_it_none'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/closes = close_grid(union_ts)/closes = union_ts[:-1]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_grid_is_the_close_stamp_neither_the_bar_open_nor_the_next_close'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/closes = close_grid(union_ts)/closes = union_ts[:-1]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_sign_run_counts_prints_never_bars_as_of_each_close'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/closes = close_grid(union_ts)/closes = union_ts[:-1]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_accrued_carry_sums_the_latest_90_prints_as_of_each_close'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/closes = close_grid(union_ts)/closes = [t + _BOUNDARY for t in close_grid(union_ts)]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_inputs_reproduces_the_full_run_bit_for_bit'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/closes = close_grid(union_ts)/closes = [t + _BOUNDARY for t in close_grid(union_ts)]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_print_inputs_reproduces_every_new_funding_emitter_bit_for_bit[sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/closes = close_grid(union_ts)/closes = [t + _BOUNDARY for t in close_grid(union_ts)]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_print_inputs_reproduces_every_new_funding_emitter_bit_for_bit[carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/j is None or normalised\[j\] <= c - _SETTLEMENT_INTERVAL/j is None/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_reads_none_from_the_close_a_settlement_past_its_last_print[zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/j is None or normalised\[j\] <= c - _SETTLEMENT_INTERVAL/j is None/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_reads_none_from_the_close_a_settlement_past_its_last_print[sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/j is None or normalised\[j\] <= c - _SETTLEMENT_INTERVAL/j is None/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_reads_none_from_the_close_a_settlement_past_its_last_print[carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/normalised\[j\] <= c - _SETTLEMENT_INTERVAL/normalised[j] < c - _SETTLEMENT_INTERVAL/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_reads_none_from_the_close_a_settlement_past_its_last_print[zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/if not len(prints_ts) == len(prints_rate) == len(prints_interval_hours):/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_print_lists_of_unequal_length_are_refused'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation '/_validate_stamps("prints_ts", prints_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_unsorted_or_naive_stamps_are_refused[unsorted-prints]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation '/_validate_stamps("prints_ts", prints_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_unsorted_or_naive_stamps_are_refused[naive-print]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation '/^def _funding_on_close_grid(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_unsorted_or_naive_stamps_are_refused[unsorted-union]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation '/^def _funding_on_close_grid(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_unsorted_or_naive_stamps_are_refused[naive-union]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation 's/if not len(prints_ts) == len(prints_rate) == len(prints_interval_hours):/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[longer-intervals-zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/if not len(prints_ts) == len(prints_rate) == len(prints_interval_hours):/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[longer-intervals-sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/if not len(prints_ts) == len(prints_rate) == len(prints_interval_hours):/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[longer-intervals-carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation '/_validate_stamps("prints_ts", prints_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[duplicate-prints-zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation '/_validate_stamps("prints_ts", prints_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[duplicate-prints-sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation '/_validate_stamps("prints_ts", prints_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[duplicate-prints-carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_grid_feature(/def funding_grid_feature_gone(/' --mutation '/^def _funding_on_close_grid(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[duplicate-union-zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation '/^def _funding_on_close_grid(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[duplicate-union-sign]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation '/^def _funding_on_close_grid(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently[duplicate-union-carry]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_sign_grid_feature(/def funding_sign_grid_feature_gone(/' --mutation 's/return _funding_on_close_grid("sign run", funding_sign_persistence, \(.*\))$/return funding_sign_persistence(_funding_on_close_grid("sign run", lambda rates: rates, \1))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_sign_run_counts_prints_never_bars_as_of_each_close'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/return _funding_on_close_grid("accrued carry", carry, \(.*\))$/return carry(_funding_on_close_grid("accrued carry", lambda rates: rates, \1))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_accrued_carry_sums_the_latest_90_prints_as_of_each_close'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/^_CARRY_WINDOW = 90$/_CARRY_WINDOW = 89/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_accrued_carry_sums_the_latest_90_prints_as_of_each_close'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def funding_carry_grid_feature(/def funding_carry_grid_feature_gone(/' --mutation 's/^_CARRY_WINDOW = 90$/_CARRY_WINDOW = 91/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_carry_window_is_the_pre_registered_90_prints'
```

  The two feeding probes are T0023's warning as code: the sign run and the carry computed over the aligned grid instead of the prints, each perfectly causal — the prefix case cannot see them, the known answer does.

### Task 2 — the OI level on a regular 4h grid over the rows' span, read at the union's closes

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

- [ ] **Step 1 — the failing tests** (`tests/test_alpha_b2.py`). In the `from cli.alpha.b2 import (` block, `    oi_grid_levels,` goes below `    net_of_cost,`. Then, at the end of the file, after two blank lines:

```python
def test_a_level_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read():
    union = _hours(0, 4, 8, 12)
    assert oi_grid_levels(_hours(4, 12), [100.0, 110.0], union) == [100.0, None, 110.0]
    younger = [DAY0 + timedelta(hours=4, seconds=1), DAY0 + timedelta(hours=12)]
    # The rows' span opens at the 08:00 mark, the first at or after the younger row: the 04:00 close lies before it.
    assert oi_grid_levels(younger, [100.0, 110.0], union) == [None, 100.0, 110.0]


def test_a_late_stamped_row_is_read_from_its_own_stamp_never_from_its_mark():
    # 22 s before the 04:00 close (278 s past 03:55, the largest offset docs/specs/00131's basis measured), and 30 s after it.
    oi_ts = [DAY0 + timedelta(hours=4, seconds=-22), DAY0 + timedelta(hours=4, seconds=30)]
    assert oi_grid_levels(oi_ts, [100.0, 110.0], _hours(0, 4, 8)) == [100.0, 110.0]


def test_a_zero_placeholder_is_none_at_the_close_it_reaches_never_the_level_before_it():
    oi_ts = [DAY0 + timedelta(hours=4, minutes=-10), DAY0 + timedelta(hours=4, minutes=-5), DAY0 + timedelta(hours=8, minutes=-5)]
    assert oi_grid_levels(oi_ts, [100.0, 0.0, 105.0], _hours(0, 4, 8)) == [None, 105.0]


def test_a_union_close_before_or_after_the_rows_span_or_of_an_empty_series_reads_none():
    oi_ts = [DAY0 + timedelta(hours=12, minutes=-5), DAY0 + timedelta(hours=16, minutes=-5)]
    assert oi_grid_levels(oi_ts, [100.0, 110.0], _hours(*range(0, 28, 4))) == [None, None, 100.0, 110.0, None, None]
    assert oi_grid_levels([], [], _hours(0, 4)) == [None]


def test_a_union_stamp_off_a_4h_mark_is_refused_by_name():
    with pytest.raises(AlphaError, match=re.escape("union_ts[2] = 2024-03-01T09:00:00+00:00 is not on a 4 h mark")):
        oi_grid_levels(_hours(1, 5, 9), [100.0, 101.0, 102.0], _hours(0, 4, 9))


@pytest.mark.parametrize(
    ("oi_ts", "union_ts", "named"),
    [
        pytest.param(_hours(5, 1, 9), _hours(0, 4, 8), "oi_ts", id="unsorted-rows"),
        pytest.param(_hours(1, 5, 5), _hours(0, 4, 8), "oi_ts", id="duplicate-rows"),
        pytest.param(_hours(1, 5, 9), _hours(0, 8, 4), "union_ts", id="unsorted-union"),
        pytest.param([DAY0.replace(hour=1, tzinfo=None)] + _hours(5, 9), _hours(0, 4, 8), "oi_ts", id="naive-row"),
        pytest.param(_hours(1, 5, 9), [DAY0.replace(tzinfo=None)] + _hours(4, 8), "union_ts", id="naive-union"),
    ],
)
def test_oi_grid_levels_refuses_unsorted_or_naive_stamps(oi_ts, union_ts, named):
    with pytest.raises(AlphaError, match=named):
        oi_grid_levels(oi_ts, [100.0, 101.0, 102.0], union_ts)


@pytest.mark.parametrize("oi_values", [[100.0, 101.0], [100.0, 101.0, 102.0, 103.0]], ids=["shorter", "longer"])
def test_oi_grid_levels_refuses_lists_of_unequal_length(oi_values):
    with pytest.raises(AlphaError, match="equal length"):
        oi_grid_levels(_hours(1, 5, 9), oi_values, _hours(0, 4, 8))


def _oi_prefix_fixture() -> tuple[list[datetime], list[float], list[datetime]]:
    """Two rows for each of 240 bars but 37 and 38; a union opening at bar 30, missing bar 100's open and closing one
    bar past the rows; and the substrate's shapes planted inside it: a close's own row stamped 30 s late at bar 33, a
    `0.0` placeholder as bar 35's last row, and no row in bars 37 and 38, whose closes find a level 4 h 5 min and
    8 h 5 min old."""
    oi_ts, oi_values = [], []
    for k in range(240):
        close = DAY0 + timedelta(hours=4 * (k + 1))
        if k in (37, 38):
            continue
        last = close + timedelta(seconds=30) if k == 33 else close - timedelta(minutes=5)
        oi_ts += [close - timedelta(minutes=10), last]
        oi_values += [100.0 + (37 * k) % 23, 0.0 if k == 35 else 100.5 + (53 * k) % 29]
    union_ts = [t for t in _hours(*range(4 * 30, 4 * 242, 4)) if t != DAY0 + timedelta(hours=4 * 100)]
    return oi_ts, oi_values, union_ts


def test_a_truncated_prefix_of_the_rows_reproduces_the_grid_levels_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    full = oi_grid_levels(oi_ts, oi_values, union_ts)
    # Return index j closes bar 30 + j up to the missing open, bar 31 + j after it: bars 35, 37 and 38 read None, and so
    # does bar 240, past the rows.
    assert len(full) == len(union_ts) - 1 and [j for j, v in enumerate(full) if v is None] == [5, 7, 8, len(full) - 1]
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = oi_grid_levels([oi_ts[i] for i in visible], [oi_values[i] for i in visible], union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"
```

  The arithmetic: a level reaches a mark from inside the bar it closes, `mark − 4h < ts ≤ mark` (spec D5), and the rows' grid runs from the first 4h mark at or after the first row to the first at or after the last (spec D6), so the younger row's grid opens at 08:00 and the 04:00 close lies before it. In the prefix fixture return index `j` closes bar `30 + j` up to the missing open (bar 100), so bars 35, 37 and 38 sit at indices 5, 7 and 8, and the last close, one bar past the rows' last mark, reads `None`. The refusal cases hold each check's silent shape, as Task 1's do: the longer values list, read by index, the repeated row stamp, which `align_asof` takes as-of, and the unsorted union, each close looked up wherever it stands; the shorter list and the unsorted rows fail downstream without their check, and a naive stamp, row or union, fails on `_EPOCH`'s arithmetic. Run `uv run pytest -q tests/test_alpha_b2.py`: collection fails, `ImportError: cannot import name 'oi_grid_levels' from 'cli.alpha.b2'`.

- [ ] **Step 2 — the grid, the pipeline and the level** (`cli/alpha/b2.py`). `from datetime import datetime, timedelta` becomes `from datetime import UTC, datetime, timedelta`; in the `cli.features.derivatives` import, `    oi_levels_from_raw,` goes below `    funding_zscore,`. Below `_BOUNDARY = timedelta(hours=4)`:

```python
# The 4h marks are the multiples of 4 h from here: the OI grid and every union close stand on them.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
```

  Below `funding_carry_grid_feature`, above `def _check_lengths(`:

```python
def _mark_at_or_after(t: datetime) -> datetime:
    return _EPOCH - (_EPOCH - t) // _BOUNDARY * _BOUNDARY


def _oi_marks(oi_ts: list[datetime]) -> list[datetime]:
    """The regular 4h close grid over the rows' own span (docs/specs/00131 D6): from the close of the bar holding the
    first row to the close of the bar holding the last, each the first 4h mark at or after its row."""
    if not oi_ts:
        return []
    first, last = _mark_at_or_after(oi_ts[0]), _mark_at_or_after(oi_ts[-1])
    return [first + k * _BOUNDARY for k in range((last - first) // _BOUNDARY + 1)]


def _oi_at_union_closes(
    label: str,
    feature: Callable[[list[float | None]], list],
    oi_ts: list[datetime],
    oi_values: list[float | None],
    union_ts: list[datetime],
) -> list:
    """Every OI emitter's one pipeline (docs/specs/00131 D4-D6): the `sum_open_interest` level on `_oi_marks`' grid --
    a `0.0` placeholder None before the as-of, a row read from its own stamp, never normalised as a funding print is,
    and a level reaching a mark only from inside the bar that mark closes, `mark - 4h < ts <= mark`, else None --
    `feature` over that grid series, then each union close's value by exact lookup, None outside the span. The union's
    bar-open stamps in, `len(union_ts) - 1` values out."""
    if len(oi_ts) != len(oi_values):
        raise AlphaError(f"oi_ts and oi_values must be equal length, got {len(oi_ts)} and {len(oi_values)}")
    _validate_stamps("oi_ts", oi_ts)
    _validate_stamps("union_ts", union_ts)
    for i, t in enumerate(union_ts):
        if (t - _EPOCH) % _BOUNDARY:
            raise AlphaError(f"union_ts[{i}] = {t.isoformat()} is not on a 4 h mark")
    marks = _oi_marks(oi_ts)
    levels = oi_levels_from_raw(oi_values)
    # The as-of over row indices, so the bound below reads the stamp of the row each mark takes.
    rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)
    grid = [None if j is None or oi_ts[j] <= g - _BOUNDARY else levels[j] for j, g in zip(rows, marks)]
    values = dict(zip(marks, feature(grid)))
    out = [values.get(c) for c in close_grid(union_ts)]
    logger.debug(
        "oi %s at union closes: %d rows, %d marks, %d return indices, %d None",
        label,
        len(oi_ts),
        len(marks),
        len(out),
        out.count(None),
    )
    return out


def oi_grid_levels(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    return _oi_at_union_closes("level", list, oi_ts, oi_values, union_ts)
```

  `list` is the level's feature: the grid series itself, copied.

- [ ] **Step 3 — green**: `uv run pytest -q tests/test_alpha_b2.py` → `82 passed`; `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` → `0`.

- [ ] **Step 4 — commit** after the consumers of the two files and the gate: `feat(alpha): the B2 OI level on a regular 4h grid over the rows' span, read at the union's closes`.

- [ ] **Step 5 — probes**, each expected KILLED. `_validate_stamps("union_ts", union_ts)` stands in both pipelines, so each probe of it is addressed to its own pipeline's body:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/oi_ts\[j\] <= g - _BOUNDARY/oi_ts[j] < g - _BOUNDARY/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_level_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/j is None or oi_ts\[j\] <= g - _BOUNDARY/j is None/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_level_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/oi_ts\[j\] <= g - _BOUNDARY/oi_ts[j] <= g - 2 * _BOUNDARY/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_level_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/levels = oi_levels_from_raw(oi_values)/levels = oi_values/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_zero_placeholder_is_none_at_the_close_it_reaches_never_the_level_before_it'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof(oi_ts, list(range(len(oi_ts))), [g + _STAMP_TOLERANCE for g in marks])/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_late_stamped_row_is_read_from_its_own_stamp_never_from_its_mark'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof(oi_ts, list(range(len(oi_ts))), [g + _BOUNDARY for g in marks])/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_the_grid_levels_bit_for_bit'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's|range((last - first) // _BOUNDARY + 1)|range((last - first) // _BOUNDARY)|' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_late_stamped_row_is_read_from_its_own_stamp_never_from_its_mark'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's|return _EPOCH - (_EPOCH - t) // _BOUNDARY \* _BOUNDARY|return _EPOCH + (t - _EPOCH) // _BOUNDARY * _BOUNDARY|' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_late_stamped_row_is_read_from_its_own_stamp_never_from_its_mark'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's|first, last = _mark_at_or_after(oi_ts\[0\]),|first, last = _mark_at_or_after(oi_ts[0]) + _BOUNDARY,|' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_level_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/values.get(c) for c in/values[c] for c in/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_union_close_before_or_after_the_rows_span_or_of_an_empty_series_reads_none'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/if not oi_ts:/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_union_close_before_or_after_the_rows_span_or_of_an_empty_series_reads_none'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/if (t - _EPOCH) % _BOUNDARY:/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_union_stamp_off_a_4h_mark_is_refused_by_name'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation 's/if len(oi_ts) != len(oi_values):/if False:/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_lists_of_unequal_length[longer]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation '/_validate_stamps("oi_ts", oi_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_unsorted_or_naive_stamps[duplicate-rows]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation '/_validate_stamps("oi_ts", oi_ts)/d' -- uv run pytest -q 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_unsorted_or_naive_stamps[naive-row]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation '/^def _oi_at_union_closes(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_unsorted_or_naive_stamps[unsorted-union]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_grid_levels(/def oi_grid_levels_gone(/' --mutation '/^def _oi_at_union_closes(/,/^def /{/_validate_stamps("union_ts", union_ts)/d}' -- uv run pytest -q 'tests/test_alpha_b2.py::test_oi_grid_levels_refuses_unsorted_or_naive_stamps[naive-union]'
```

  The fifth probe is funding's 60 s tolerance applied to OI, the normalisation spec D4 rules out; the third widens the staleness bound to two bars; the seventh drops the grid's last mark, the close of the bar holding the last row, which spec D6 keeps; the eighth floors every mark to the one at or before its row; the ninth opens the grid a mark late.

### Task 3 — the OI trio over the regular grid level series

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

- [ ] **Step 1 — the failing tests** (`tests/test_alpha_b2.py`). In the `from cli.alpha.b2 import (` block, below `    oi_grid_levels,`, the three lines `    oi_log_delta_grid_feature,`, `    oi_momentum_grid_feature,`, `    oi_zscore_grid_feature,`. Then, at the end of the file, after two blank lines:

```python
def _oi_on_the_grid(levels: list[float]) -> tuple[list[datetime], list[float], list[datetime]]:
    """Each level the later of two rows inside its bar, the earlier 1.5 times it: a feature over the raw rows and one
    over the grid disagree."""
    union_ts = _hours(*range(0, 4 * (len(levels) + 1), 4))
    oi_ts, oi_values = [], []
    for k, level in enumerate(levels):
        close = union_ts[k] + timedelta(hours=4)
        oi_ts += [close - timedelta(minutes=10), close - timedelta(minutes=5)]
        oi_values += [1.5 * level, level]
    return oi_ts, oi_values, union_ts


def test_the_oi_log_delta_is_bar_to_bar_on_the_grid_never_row_to_row():
    # Over the raw rows it would read each bar's last five minutes, log(1 / 1.5), at every close.
    assert oi_log_delta_grid_feature(*_oi_on_the_grid([100.0, 110.0, 121.0, 133.1])) == [None] + [pytest.approx(math.log(1.1))] * 3


def test_the_oi_zscore_recovers_a_spike_over_180_grid_bars():
    expected = [None] * 179 + [0.0, pytest.approx(179 / math.sqrt(180))]
    assert oi_zscore_grid_feature(*_oi_on_the_grid([100.0] * 180 + [200.0])) == expected


def test_the_oi_momentum_reads_its_base_180_grid_bars_back():
    expected = [None] * 180 + [pytest.approx(1.8), pytest.approx(281 / 101 - 1)]
    assert oi_momentum_grid_feature(*_oi_on_the_grid([100.0 + k for k in range(182)])) == expected


def test_the_oi_windows_are_the_pre_registered_180_bars():
    assert (b2._OI_ZSCORE_WINDOW, b2._OI_MOMENTUM_LOOKBACK) == (180, 180)


def test_a_union_hole_leaves_the_next_oi_log_delta_a_single_4h_step():
    oi_ts, oi_values, union_ts = _oi_on_the_grid([100.0 * 1.1**k for k in range(6)])
    del union_ts[3]
    # The union has no close at 16 h; over its own closes the 20 h log-delta would span 8 h, log(1.21).
    assert oi_log_delta_grid_feature(oi_ts, oi_values, union_ts) == [None] + [pytest.approx(math.log(1.1))] * 4


def test_a_union_opening_inside_the_rows_span_reads_the_oi_zscore_warm():
    oi_ts, oi_values, union_ts = _oi_on_the_grid([100.0] * 180 + [200.0])
    # Two return indices closing on the spike fixture's last two marks; over their own two closes both would be None.
    assert oi_zscore_grid_feature(oi_ts, oi_values, union_ts[179:]) == [0.0, pytest.approx(179 / math.sqrt(180))]


def test_a_zero_placeholder_leaves_every_oi_zscore_window_holding_its_mark_none():
    oi_ts, oi_values, union_ts = _oi_on_the_grid([100.0] * 181)
    oi_values[1] = 0.0
    # Bar 0's later row is the placeholder: fallen back to its earlier row, 150.0, the first window would score.
    assert oi_zscore_grid_feature(oi_ts, oi_values, union_ts) == [None] * 180 + [0.0]


@pytest.mark.parametrize(
    ("emitter", "defined"),
    [(oi_log_delta_grid_feature, 204), (oi_zscore_grid_feature, 22), (oi_momentum_grid_feature, 57)],
    ids=["log-delta", "zscore", "momentum"],
)
def test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit(emitter, defined):
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    full = emitter(oi_ts, oi_values, union_ts)
    # Exact: a stale level the feature reads in place of None defines more closes, and so does a placeholder's fall-back,
    # save the z-score's, which the placeholder case carries.
    assert len(full) == len(union_ts) - 1 and sum(v is not None for v in full) == defined
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = emitter([oi_ts[i] for i in visible], [oi_values[i] for i in visible], union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"
```

  The arithmetic: 179 equal levels and one `d` above them score `(n − 1) / √n` with `n = 180` under the inclusive window and sample stdev spec `00110` D7 pins (`2.8460498941515410` at `n = 10`, its own example); the momentum's base at index 180 is level 0, `280 / 100 − 1`, and at 181 level 1, `281 / 101 − 1`. `_oi_on_the_grid`'s union closes on every mark of its rows' grid, so its known answers are the grid's own; the hole case drops the open of bar 3, and the warm case keeps the opens of bars 179–181, two return indices. On the prefix fixture the z-score is defined at the 22 closes from bar 218 (180 marks after its last gap, bar 38), the momentum at 57, the log-delta at 204, the first close among them — the rows open 30 bars before the union does. Each count is exact because the prefix property cannot see a level that should be `None` reaching the feature — such a feature is causal — and the counts can. Their members, measured on this fixture as log-delta, z-score and momentum: the trio over `align_asof` of `oi_levels_from_raw` on `_oi_marks`' grid, the harness docstring's recipe without spec D5's bound, defines 207, 25 and 59; spec D5's bound applied after the feature instead of before it, 205, 25 and 59; a fall-back past a `0.0` to the row before it (spec D4's refusal), 206, 22 and 58 — the z-score blind to it, since every window holding bar 35 also holds bars 37–38, so the placeholder case carries it: bar 0's later row a `0.0`, its earlier row 150.0, so the fall-back scores the first window where the level `None` leaves it `None`. Run `uv run pytest -q tests/test_alpha_b2.py`: collection fails, `ImportError: cannot import name 'oi_log_delta_grid_feature' from 'cli.alpha.b2'`.

- [ ] **Step 2 — the trio** (`cli/alpha/b2.py`). In the `cli.features.derivatives` import, below `    oi_levels_from_raw,`, the three lines `    oi_log_delta,`, `    oi_momentum,`, `    oi_zscore,`. Below `_CARRY_WINDOW = 90`:

```python
_OI_ZSCORE_WINDOW = 180
_OI_MOMENTUM_LOOKBACK = 180
```

  Below `oi_grid_levels`, above `def _check_lengths(`:

```python
def oi_log_delta_grid_feature(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    return _oi_at_union_closes("log-delta", oi_log_delta, oi_ts, oi_values, union_ts)


def oi_zscore_grid_feature(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    zscore = partial(oi_zscore, window=_OI_ZSCORE_WINDOW)
    return _oi_at_union_closes("z-score", zscore, oi_ts, oi_values, union_ts)


def oi_momentum_grid_feature(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    momentum = partial(oi_momentum, lookback=_OI_MOMENTUM_LOOKBACK)
    return _oi_at_union_closes("momentum", momentum, oi_ts, oi_values, union_ts)
```

- [ ] **Step 3 — green**: `uv run pytest -q tests/test_alpha_b2.py` → `92 passed`; `git diff -U0 develop -- tests/test_alpha_b2.py | grep -c '^-[^-]'` → `0`.

- [ ] **Step 4 — commit** after the consumers of the two files and the gate: `feat(alpha): the B2 OI log-delta, z-score and momentum over the regular grid level series`.

- [ ] **Step 5 — probes**, each expected KILLED; the three raw-fed probes are the harness's module docstring as code — the trio over the raw 5-minute rows instead of the grid series — the two union-grid probes are spec D6's ruling as code, the trio computed on the union's own closes, and the last nine are the prefix counts' members (Step 1), each against the case that carries it:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/^_OI_ZSCORE_WINDOW = 180$/_OI_ZSCORE_WINDOW = 179/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_oi_zscore_recovers_a_spike_over_180_grid_bars'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_grid_feature(/def oi_momentum_grid_feature_gone(/' --mutation 's/^_OI_MOMENTUM_LOOKBACK = 180$/_OI_MOMENTUM_LOOKBACK = 181/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_oi_momentum_reads_its_base_180_grid_bars_back'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/^_OI_MOMENTUM_LOOKBACK = 180$/_OI_MOMENTUM_LOOKBACK = 179/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_oi_windows_are_the_pre_registered_180_bars'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_grid_feature(/def oi_log_delta_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("log-delta", oi_log_delta, oi_ts, oi_values, union_ts)/return align_asof(oi_ts, oi_log_delta(oi_levels_from_raw(oi_values)), close_grid(union_ts))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_oi_log_delta_is_bar_to_bar_on_the_grid_never_row_to_row'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("z-score", zscore, oi_ts, oi_values, union_ts)/return align_asof(oi_ts, zscore(oi_levels_from_raw(oi_values)), close_grid(union_ts))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_oi_zscore_recovers_a_spike_over_180_grid_bars'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_grid_feature(/def oi_momentum_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("momentum", momentum, oi_ts, oi_values, union_ts)/return align_asof(oi_ts, momentum(oi_levels_from_raw(oi_values)), close_grid(union_ts))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_the_oi_momentum_reads_its_base_180_grid_bars_back'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_grid_feature(/def oi_log_delta_grid_feature_gone(/' --mutation 's/marks = _oi_marks(oi_ts)/marks = close_grid(union_ts)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_union_hole_leaves_the_next_oi_log_delta_a_single_4h_step'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/marks = _oi_marks(oi_ts)/marks = close_grid(union_ts)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_union_opening_inside_the_rows_span_reads_the_oi_zscore_warm'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_grid_feature(/def oi_log_delta_grid_feature_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof(oi_ts, list(range(len(oi_ts))), [g + _BOUNDARY for g in marks])/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[log-delta]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof(oi_ts, list(range(len(oi_ts))), [g + _BOUNDARY for g in marks])/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_grid_feature(/def oi_momentum_grid_feature_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof(oi_ts, list(range(len(oi_ts))), [g + _BOUNDARY for g in marks])/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[momentum]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_grid_feature(/def oi_log_delta_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("log-delta", oi_log_delta, oi_ts, oi_values, union_ts)/return [dict(zip(_oi_marks(oi_ts), oi_log_delta(align_asof(oi_ts, oi_levels_from_raw(oi_values), _oi_marks(oi_ts))))).get(c) for c in close_grid(union_ts)]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[log-delta]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("z-score", zscore, oi_ts, oi_values, union_ts)/return [dict(zip(_oi_marks(oi_ts), zscore(align_asof(oi_ts, oi_levels_from_raw(oi_values), _oi_marks(oi_ts))))).get(c) for c in close_grid(union_ts)]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_grid_feature(/def oi_momentum_grid_feature_gone(/' --mutation 's/return _oi_at_union_closes("momentum", momentum, oi_ts, oi_values, union_ts)/return [dict(zip(_oi_marks(oi_ts), momentum(align_asof(oi_ts, oi_levels_from_raw(oi_values), _oi_marks(oi_ts))))).get(c) for c in close_grid(union_ts)]/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[momentum]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_grid_feature(/def oi_log_delta_grid_feature_gone(/' --mutation 's/values = dict(zip(marks, feature(grid)))/values = dict(zip(marks, [None if g is None else v for g, v in zip(grid, feature([None if j is None else levels[j] for j in rows]))]))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[log-delta]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/values = dict(zip(marks, feature(grid)))/values = dict(zip(marks, [None if g is None else v for g, v in zip(grid, feature([None if j is None else levels[j] for j in rows]))]))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[zscore]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_grid_feature(/def oi_momentum_grid_feature_gone(/' --mutation 's/values = dict(zip(marks, feature(grid)))/values = dict(zip(marks, [None if g is None else v for g, v in zip(grid, feature([None if j is None else levels[j] for j in rows]))]))/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[momentum]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_log_delta_grid_feature(/def oi_log_delta_grid_feature_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof([t for t, v in zip(oi_ts, levels) if v is not None], [i for i, v in enumerate(levels) if v is not None], marks)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[log-delta]'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_zscore_grid_feature(/def oi_zscore_grid_feature_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof([t for t, v in zip(oi_ts, levels) if v is not None], [i for i, v in enumerate(levels) if v is not None], marks)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_zero_placeholder_leaves_every_oi_zscore_window_holding_its_mark_none'
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def oi_momentum_grid_feature(/def oi_momentum_grid_feature_gone(/' --mutation 's/rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)/rows = align_asof([t for t, v in zip(oi_ts, levels) if v is not None], [i for i, v in enumerate(levels) if v is not None], marks)/' -- uv run pytest -q 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit[momentum]'
```

### Task 4 — T0023: the emission delivered, the 1h grid dropped

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`.

- [ ] **Step 1 — the edit** (`topic-ops`' edit mechanics: each anchor's `grep -c` reads 1 first, and `grep '^#'` of the file reads the same headings before and after). In `## Done so far`, below the bullet opening `- **B2 emission and trial-1 subject DELIVERED (iter-175, spec/plan `00128`)**`, one blank line and then:

```markdown
- **B2's remaining funding and OI features on the 4h close grid DELIVERED (spec/plan `00131`)**: `cli/alpha/b2.py` — the funding sign run and the 90-print accrued carry through the z-score's one print pipeline, each fed the prints and never the grid, and no print read at a close a settlement or more after it, so from the close a settlement past a series' last print the features read `None`; the OI level `sum_open_interest` on a regular 4h grid over the substrate's own span, as-of on its raw stamps, a `0.0` placeholder `None` and no level older than the bar its mark closes (11 of 104,446 marks measured); the OI log-delta, 180-bar z-score and 180-bar momentum over that grid series, warm for a window opening 30 days into the span save where a `None` level lies in a window — the z-score for the 30 days from 2024-02-16T20:00Z in every symbol, the log-delta at that mark and the next, the momentum at that mark and 180 marks after it; each read at a union's closes by exact lookup, a column's `binperp_` name and per-year coverage the consumer's. No subject, no registry record. The 1h grid is dropped: a same-hour de-risk is an execution-layer knob and a trial on it its own pre-registration (spec `00128` D1), and no committed subject reads a 1h series.
```

  In `## Suggested next steps`, the bullet opening `- **(autonomous) the rest of the substrate→feature emission.**` is replaced whole by the one feature family of spec `00110` D7 no emitter carries yet — its warning is now the emitters' construction and their known answers:

```markdown
- **(autonomous) the ratio columns on the 4h close grid.** `ratio_features` (spec `00110`) carries the four Binance ratios under `binperp_` names, and no emitter reads them at a union's closes (spec `00131`'s Out of scope). They share the OI level's 5-minute rows, so spec `00131` D5's staleness and D6's regular grid carry over; a `0.0` taker ratio is a reading, never a placeholder (spec `00110` D5).
```

  `status` and `ripe_when` do not change, so the index is not re-rendered: `uv run python infra/scripts/topics-index.py --check` exits 0, and `uv run pytest -q tests/test_open_topics_frontmatter.py` passes.

- [ ] **Step 2 — commit** after the consumers of the topic file and the gate: `docs(open-topics): T0023 — B2's remaining funding and OI features on the 4h close grid delivered, the 1h grid dropped`.

### Task 5 — the reads and the PR (the controller's)

- [ ] `git diff --quiet develop HEAD -- cli/features cli/research` exits 0.
- [ ] `uv run pytest -q tests/test_alpha_b2.py tests/test_research_command.py` passes; the probe verdicts of Tasks 1–3, 74 lines, each `KILLED`.
- [ ] The repo's trio over the branch: `pre-review`, `review`, `re-review` at most twice; push only after the read; the PR through `open-pr` — `feat(alpha): 00131 — B2's remaining funding and OI features on the 4h close grid`, its body naming the read line, the probe verdicts and T0023's update; the change-index row; merge on the owner's word through `merge-pr`; the two data links (`data/derivatives-funding`, `data/derivatives-oi`) removed with `rm` before `git worktree remove`, the main checkout's `data/` listing read after.
