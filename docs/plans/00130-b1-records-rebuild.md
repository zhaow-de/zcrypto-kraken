# Records 45 and 46 re-derived — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec `docs/specs/00130-b1-records-rebuild-design.md` — two evaluate-only research subjects, `b1-conditioning` and `b1-window-only`, that re-derive records 45 and 46 from committed code; a data-gated test proving it at the registered precision; the legacy map grown by 45 and 46; the three legacy digests `81dc9b44`, `ba47e37e`, `45275ebe` recomputed by a test and re-rated in the pins file, spec 00086 D6 amended; T0223 resolved.

**Architecture:** the subjects live in `cli/research/subjects.py` beside the B2 ones and reuse its readers (`_capturing_union`, `ObservedReader`), `cli/alpha/b1.py`'s overlay and `cli/alpha/b2.py::net_of_cost`; their build is the measured driver `.tmp/b1-measure/b1_common.py` (this worktree, scratch) transcribed onto the subject contract. The reproduction test is a new data-gated module; the digests' recipe is a test-side function in the existing data-gated pins test.

**Tech stack:** Python 3.14 through uv; pytest; the repo's `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`.

## Global Constraints

- TDD per task: the failing test first, the implementation second, the test green third. Every guard is proven with `infra/scripts/mutate-probe.sh` after the task's commit (it refuses a dirty tree), in the form `--file F --control 's/^def X(/def X_gone(/' --mutation '<sed>' -- uv run pytest -q '<node id>'`, the sed dry-run through `ast.parse` first and the mutated site's `grep -c` reading 1 — where the text stands at two sites, the step names the sed's address and the addressed range holds one; its verdict line goes in the task report and the PR body, naming the script.
- Before each commit, the consumers of each changed file (`infra/scripts/consumers.sh <path>`), the union, in per-file parts each under about 400 s — `tests/test_cache_restart.py` split by node id into three parts, `tests/test_converge_sh.py` its own part, nothing backgrounded — deselecting in every run `tests/test_registry_conformance.py::test_the_hubs_hot_still_holds_every_byte_a_record_cites`, the three engine-journal cases of `tests/test_engine_tracking.py`, `tests/test_registry_observed.py::test_loader_reproduces_the_frozen_full_set_extents[ohlc-holdout-2026-07-10]`, `tests/test_data_manifest.py::test_path_order_re_anchors_the_hub_reach_continuous_digest_and_the_move_is_deliberate`, `tests/test_engine_soak.py::test_realized_internals_on_real_journal`, `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-1]` (gated on `data/ohlc-full` alone, it reads `ohlc-rolling` and `derivatives-funding`, which are not linked here, and a run before a commit under `cli/` or `tests/` finds the tree dirty; the nightly replays it). Never `tests/test_grafana_push_sh.py`; never the full suite.
- Data: only `data/ohlc-full` and `data/ohlc-15m`, linked into this worktree; never `data/ohlc-holdout-*`, never `/mnt/zhao-crypto/`; no ssh; never `kraken`. Never look for, open, count or quote any real account export anywhere outside the repository's tracked fixtures.
- Never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`; never `zcrypto research eval --register` or `--reading`; never `git stash`; never edit `docs/specs/00045-b1-seasonality-conditioning-design.md` (records 45 and 46 pin its sha256).
- No operator-read surface (`README.md`, a `SubjectError` message) carries `iter-<N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>` (`tests/test_internal_terms_not_operator_visible.py`); comments and docstrings may.
- Commits by kind, each task its own commit (no amend): `feat(research)`, `test(research)`, `docs(reference)`, `docs(specs)`, `docs(open-topics)`. The gate is `uv run pre-commit run -a`, re-run until clean, staging by explicit path. Trailers: `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01Dr2kJsYt2KVuf7VUBuvyhF`.
- Scratch under this worktree's `.tmp/<role>/`, removed at the end of the task.

______________________________________________________________________

### Task 1 — the two subjects

**Files:** `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`.

- [ ] **Step 1 — the failing tests** (`tests/test_research_command.py`):

```python
# Records 45 and 46's metric keys (docs/specs/00130 D3), pinned against the committed records below.
_B1_REGISTERED_KEYS = frozenset(
    {
        "ann_sharpe_noc", "ann_sharpe_noc_decisive", "arm_a_ann_sharpe_noc", "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown", "arm_a_spot_drag_pct_yr", "benchmark_ann_sharpe_noc", "benchmark_ann_sharpe_noc_decisive",
        "cost_stress_pass", "decisive_start", "dsr_corrected", "dsr_pass", "gated_per_year", "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016", "head_to_head_spa_p_full", "max_drawdown", "n_resamples", "passes", "per_period_sharpe_4h",
        "scaled_per_year", "spa_p_decisive_b102", "spa_p_decisive_b30", "spa_p_full", "spa_p_seed1234", "spa_p_seed7",
        "spa_pass", "spot_drag_pct_yr", "stamps_held", "stamps_positions_differ", "stamps_scaled", "turnover_a", "turnover_b",
        "turnover_reduction_pct", "worst_slice_relative_pass",
    }
)


def test_the_b1_subjects_literals_are_the_ones_records_45_and_46_ran_with():
    assert subjects._B1_COST_PER_SIDE == 0.006
    assert subjects._B1_A2_ARMS == (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    assert subjects._B1_LOOKBACK == 180
    assert subjects._B1_DECISIVE_START == 1380
    assert subjects._B1_N_RESAMPLES == 2000
    assert subjects._B1_FROM_2016 == datetime(2016, 1, 1, tzinfo=UTC)
    assert subjects._B1_GRID == ((30, 7), (30, 1234), (102, 42))


@pytest.mark.parametrize(("name", "trial_id", "build"), [("b1-conditioning", 45, "_build_b1_conditioning"), ("b1-window-only", 46, "_build_b1_window_only")])
def test_each_b1_subject_declares_its_records_keys_and_is_evaluate_only(name, trial_id, build):
    subject = subjects.SUBJECTS[name]
    assert subject.metric_keys == _B1_REGISTERED_KEYS == frozenset(_trials()[trial_id]["metrics"])
    assert subject.build is getattr(subjects, build)
    assert (subject.intervals, subject.assets, subject.seeds) == ((240,), _B2_ASSETS, (42, 7, 1234))
    assert subject.spec == "docs/specs/00045-b1-seasonality-conditioning-design.md"
    assert subject.verdict is None and subject.no_verdict is None and subject.incumbent is None
```

  `_trials()` (already imported from `tests.test_trial_registry_provenance`) maps each committed trial id to its record as a dict. The B1 contract fixture, beside `_b2_dataset`:

```python
_B1_START = datetime(2015, 6, 1, tzinfo=UTC)
_B1_BARS = 1_600  # 4h bars: 1,599 return indices, 315 of them from 2016-01-01, closes in 2015 and 2016


def _b1_dataset(tmp_path: Path, *, start: datetime = _B1_START, bars: int = _B1_BARS, m15: bool = True) -> Path:
    """The ten 4h series and, unless `m15` is false, an `ohlc-15m` set of the same span at 15 minutes, whose last bar
    closes four hours past the last 4h decision boundary, so the vol scaler's extent check passes."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        rows = _rows(bars, phase=i * 0.7, start=int(start.timestamp()), step=4 * 3600)
        write_parquet(to_frame(rows), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
        if m15:
            rows = _rows(bars * 16, phase=i * 0.7, start=int(start.timestamp()), step=900)
            write_parquet(to_frame(rows), root / "ohlc-15m" / f"{asset}/EUR/15.parquet")
    return root
```

  `_CONTRACT_DATASETS` gains:

```python
    "b1-conditioning": lambda tmp_path, subject: (_b1_dataset(tmp_path), _B1_START),
    "b1-window-only": lambda tmp_path, subject: (_b1_dataset(tmp_path, m15=False), _B1_START),
```

  so the contract test (`evaluates`, the three short windows, the three spoils on 240) and the shared-defaults test cover both subjects. Then the cases the contract does not drive, below the fixture, since the refusal case's parameters read `_B1_BARS` at import:

```python
@pytest.mark.parametrize(
    ("name", "datasets"),
    [
        pytest.param("b1-conditioning", {"ohlc-test", "ohlc-15m"}, id="b1-conditioning"),
        pytest.param("b1-window-only", {"ohlc-test"}, id="b1-window-only"),
    ],
)
def test_only_b1_conditioning_reads_the_15m_set(tmp_path, name, datasets):
    reader = ObservedReader(_b1_dataset(tmp_path))
    subjects.SUBJECTS[name].build(reader, "ohlc-test", None)
    assert set(reader.block()) == datasets


@pytest.mark.parametrize(
    ("spoil", "cause"),
    [
        pytest.param(Path.unlink, "No such file or directory", id="missing"),
        pytest.param(lambda path: path.write_bytes(b"not a parquet file"), "File out of specification", id="not-parquet"),
    ],
)
def test_b1_conditioning_names_a_15m_file_it_cannot_read(tmp_path, monkeypatch, spoil, cause):
    root = _b1_dataset(tmp_path)
    spoil(root / "ohlc-15m" / "SOL/EUR/15.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b1-conditioning", "--dataset", "ohlc-test"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "ohlc-15m/SOL/EUR/15.parquet" in result.output and cause in result.output


def test_b1_conditioning_refuses_a_15m_set_short_of_the_last_decision_boundary_in_its_own_terms(tmp_path, monkeypatch):
    root = _b1_dataset(tmp_path)
    for path in (root / "ohlc-15m").rglob("15.parquet"):
        # Eight hours off each file: the last close falls four hours short of the last decision boundary.
        pl.read_parquet(path).head(-32).write_parquet(path)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b1-conditioning", "--dataset", "ohlc-test"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "b1-conditioning over the full history: 15m substrate ends at" in result.output


@pytest.mark.parametrize(
    ("start", "bars", "message"),
    [
        pytest.param(
            datetime(2020, 1, 1, tzinfo=UTC), 1_300, "it holds 1299 return indices", id="short-of-the-decisive-window"
        ),
        pytest.param(
            datetime(2015, 1, 1, tzinfo=UTC),
            _B1_BARS,
            "0 of its return indices open at or after 2016-01-01T00:00Z",
            id="before-2016",
        ),
        pytest.param(
            datetime(2026, 1, 1, tzinfo=UTC), _B1_BARS, "none of its return indices closes in a calendar year", id="all-in-2026"
        ),
    ],
)
@pytest.mark.parametrize("name", ["b1-conditioning", "b1-window-only"])
def test_a_b1_history_the_bar_cannot_read_is_refused_before_the_arms(tmp_path, monkeypatch, name, start, bars, message):
    _anchor(monkeypatch, _b1_dataset(tmp_path, start=start, bars=bars, m15=False))
    calls = _recording(monkeypatch, "a2_book_returns", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert f"{name} over the full history: " in result.output and message in result.output
    assert calls == []
```

  Run `uv run pytest -q tests/test_research_command.py -k "b1"`: every new case fails (no `_B1_*`, no B1 subject).

- [ ] **Step 2 — the subjects** (`cli/research/subjects.py`). Imports: `from cli.alpha.b1 import B1Config, book_turnover, condition_positions, per_year_gated_counts, per_year_scaled_counts, seasonality_gates, vol_state_scale` (replacing the `book_turnover` import) and `reality_check_pvalue` beside `ValidationError, max_drawdown, sharpe` from `cli.validation`. After `_b2_verdict`, before `SUBJECTS`:

```python
# The B1 trials' fixed constants (docs/specs/00045's protocol, records 37-39's arms; docs/specs/00130 D2): records 45 and
# 46 ran with these, so a change to one no longer re-derives them.
_B1_COST_PER_SIDE = 0.006
_B1_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
_B1_LOOKBACK = 180
_B1_DECISIVE_START = 1380
_B1_N_RESAMPLES = 2000
_B1_FROM_2016 = datetime(2016, 1, 1, tzinfo=UTC)
# The SPA grid's points past the headline (30, 42) that records 45 and 46 store as keys.
_B1_GRID = ((30, 7), (30, 1234), (102, 42))


def _b1_refuse_window(subject: str, h4_ts: list[datetime], window: tuple[str, str] | None) -> None:
    n = len(h4_ts) - 1
    from_2016 = sum(t >= _B1_FROM_2016 for t in h4_ts[:-1])
    if n < _B1_DECISIVE_START + 2:
        raise SubjectError(
            f"{_b2_over(subject, window)}: it holds {n} return indices, and the kill bar's decisive window opens at index "
            f"{_B1_DECISIVE_START} and needs 2"
        )
    if from_2016 < 2:
        raise SubjectError(
            f"{_b2_over(subject, window)}: {from_2016} of its return indices open at or after 2016-01-01T00:00Z, and the "
            "from-2016 head-to-head needs 2"
        )
    if not calendar_year_slices([0.0] * n, h4_ts):
        raise SubjectError(
            f"{_b2_over(subject, window)}: none of its return indices closes in a calendar year the worst-slice leg reads, "
            "2013 and 2026 left out"
        )


def _b1_m15(reader: ObservedReader) -> dict[str, tuple[list[datetime], list[float]]]:
    """Read whole, never windowed: the scaler's trailing day and its 180-boundary median warm before any window opens."""
    m15 = {}
    for asset in _ASSETS:
        relpath = f"{asset}/EUR/15.parquet"
        try:
            frame = reader.read_series("ohlc-15m", relpath)
            m15[asset] = (frame["ts"].to_list(), frame["close"].to_list())
        except pl.exceptions.PolarsError as exc:
            raise SubjectError(f"ohlc-15m/{relpath}: {exc}") from exc
    return m15


def _b1_metrics(
    h4_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
    m15: dict[str, tuple[list[datetime], list[float]]] | None,
    *,
    n_trials: int,
) -> dict:
    """Records 45 and 46's protocol: arm A the three adopted A2 arms equal-weighted, arm B through the overlay, the
    benchmark, the bar, the grid and the head-to-heads, costed inline at 0.006 per side (docs/specs/00130 D3)."""
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    arms = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B1_LOOKBACK,
                basket_lookback=_B1_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
        )["asset_positions"]
        for lookbacks, target_vol in _B1_A2_ARMS
    ]
    arm_a = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in _ASSETS}
    returns = {a: _asset_returns(fed[a]) for a in _ASSETS}
    cost = _B1_COST_PER_SIDE
    net_a = net_of_cost(arm_a, returns, cost_per_side=cost)
    config = B1Config()
    gates = seasonality_gates(net_a, h4_ts, config=config)
    scales = [1.0] * n if m15 is None else vol_state_scale(m15, h4_ts, config=config)
    arm_b = condition_positions(arm_a, gates, scales)
    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=cost)
    bar = a1_kill_bar(
        net_b,
        bench,
        n_trials=n_trials,
        var_trials=0.0,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_b_x15,
        regime_slices=calendar_year_slices(net_b, h4_ts),
        benchmark_slices=calendar_year_slices(bench, h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    decisive = [[net_b[k] - bench[k]] for k in range(_B1_DECISIVE_START, n)]
    grid = {
        (block, seed): reality_check_pvalue(decisive, mean_block=block, n_resamples=_B1_N_RESAMPLES, seed=seed)["p_value"]
        for block, seed in _B1_GRID
    }
    # A stamp belongs to the year of its bar's start, ts[k], as the gates' fold years do.
    k16 = next(k for k in range(n) if h4_ts[k] >= _B1_FROM_2016)
    full = net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    from_2016 = net_of_cost_verdict(net_b[k16:], net_a[k16:], mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    turnover_a, turnover_b = book_turnover(arm_a), book_turnover(arm_b)
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "dsr_corrected": bar["dsr"],
        "dsr_pass": int(bar["dsr_pass"]),
        "spa_pass": int(bar["spa_pass"]),
        "spa_p_full": bar["spa_p_value_full"],
        "cost_stress_pass": int(bar["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bar["worst_slice_pass"]),
        "passes": int(bar["passes"]),
        "decisive_start": _B1_DECISIVE_START,
        "n_resamples": _B1_N_RESAMPLES,
        "spa_p_decisive_b30": bar["spa_p_value"],
        "spa_p_decisive_b102": grid[(102, 42)],
        "spa_p_seed7": grid[(30, 7)],
        "spa_p_seed1234": grid[(30, 1234)],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * cost * PPY_4H,
        "arm_a_spot_drag_pct_yr": turnover_a / n * cost * PPY_4H,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_held": gates.count(0),
        "stamps_scaled": sum(scale != 1.0 for scale in scales),
        "stamps_positions_differ": sum(any(arm_b[a][k] != arm_a[a][k] for a in _ASSETS) for k in range(n)),
        "gated_per_year": {str(year): count for year, count in per_year_gated_counts(gates, h4_ts).items()},
        "scaled_per_year": {str(year): count for year, count in per_year_scaled_counts(scales, h4_ts).items()},
    }


def _b1_build(
    subject: str,
    conditioning: bool,
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    _b1_refuse_window(subject, h4_ts, window)
    m15 = _b1_m15(reader) if conditioning else None
    try:
        return _b1_metrics(h4_ts, h4_prices, m15, n_trials=1 if conditioning else 2)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        # The scaler's extent check (docs/specs/00045 F8) and a bad close among them, named as the window's.
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b1_conditioning(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_build("b1-conditioning", True, reader, dataset, window, as_of, accept_holes)


def _build_b1_window_only(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_build("b1-window-only", False, reader, dataset, window, as_of, accept_holes)


# Records 45 and 46's 35 keys (docs/specs/00130 D3).
_B1_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc", "ann_sharpe_noc_decisive", "arm_a_ann_sharpe_noc", "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown", "arm_a_spot_drag_pct_yr", "benchmark_ann_sharpe_noc", "benchmark_ann_sharpe_noc_decisive",
        "cost_stress_pass", "decisive_start", "dsr_corrected", "dsr_pass", "gated_per_year", "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016", "head_to_head_spa_p_full", "max_drawdown", "n_resamples", "passes", "per_period_sharpe_4h",
        "scaled_per_year", "spa_p_decisive_b102", "spa_p_decisive_b30", "spa_p_full", "spa_p_seed1234", "spa_p_seed7",
        "spa_pass", "spot_drag_pct_yr", "stamps_held", "stamps_positions_differ", "stamps_scaled", "turnover_a", "turnover_b",
        "turnover_reduction_pct", "worst_slice_relative_pass",
    }
)
```

  `SUBJECTS` gains, after `"b2-arm-a-bar"`:

```python
    "b1-conditioning": Subject(
        "b1-conditioning",
        (240,),
        _ASSETS,
        _build_b1_conditioning,
        spec="docs/specs/00045-b1-seasonality-conditioning-design.md",
        metric_keys=_B1_METRIC_KEYS,
        seeds=(42, 7, 1234),
    ),
    "b1-window-only": Subject(
        "b1-window-only",
        (240,),
        _ASSETS,
        _build_b1_window_only,
        spec="docs/specs/00045-b1-seasonality-conditioning-design.md",
        metric_keys=_B1_METRIC_KEYS,
        seeds=(42, 7, 1234),
    ),
```

  `ruff format` lays the key sets one per line; keep what it writes. Run `uv run pytest -q tests/test_research_command.py -k "b1 or evaluates_its_fixture or shared_defaults or declares"`: green.

- [ ] **Step 3 — `README.md`**: the `--subject` row's list ends `… or b2-arm-a-bar (…)`; make it `…, b2-arm-a-bar (…), b1-conditioning (the A2 4h ensemble through the seasonality gates and the vol scaler, reproducing a past trial; the 4h series of --dataset, and the ohlc-15m set's ten 15-minute series read whole) or b1-window-only (the same ensemble through the seasonality gates alone; the 4h series of --dataset only); neither has a rule, so neither registers`, backticks as the row writes subject names, no internal term.

- [ ] **Step 4 — the whole file and the consumers**: `uv run pytest -q tests/test_research_command.py`, then the consumers of the three files, then the gate; commit `feat(research): records 45 and 46's B1 builds as two evaluate-only research subjects`, its body naming the measured driver it transcribes and that the data-gated proof is the next commit's.

- [ ] **Step 5 — probes** (after the commit, each against the named case in `tests/test_research_command.py`, each expected KILLED, each control the form's `def X` with the `X` named, since a control the case never reaches does not fail it). The refusals and translations the subjects add are five, and each has its case and its probe here — the window refusal's three arms, `_b1_m15`'s catch, `_b1_build`'s catch:
  - `_B1_LOOKBACK = 180` → `181`, `_B1_DECISIVE_START = 1380` → `1381`, and `/^_B1_GRID = /s/(30, 7)/(102, 7)/` (`(30, 7)` also stands in `grid[(30, 7)]`): each against `test_the_b1_subjects_literals_are_the_ones_records_45_and_46_ran_with`, its control `s/^_B1_N_RESAMPLES = /_B1_N_RESAMPLES_GONE = /`, since that case reads constants and calls no function;
  - `/^    "b1-window-only": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/` (the same `seeds=` stands in `b2-funding-derisk`'s entry and `b1-conditioning`'s) against `test_each_b1_subject_declares_its_records_keys_and_is_evaluate_only[b1-window-only-46-_build_b1_window_only]`, `X` `_build_b1_window_only`;
  - the refusal's `if n < _B1_DECISIVE_START + 2:` → `if False:` against `…refused_before_the_arms[b1-window-only-short-of-the-decisive-window]`, `if from_2016 < 2:` → `if False:` against `…[b1-conditioning-before-2016]`, `if not calendar_year_slices(` → `if False and not calendar_year_slices(` against `…[b1-window-only-all-in-2026]`, each `X` `_b1_refuse_window`;
  - `m15 = _b1_m15(reader) if conditioning else None` → `m15 = _b1_m15(reader)` against `test_only_b1_conditioning_reads_the_15m_set[b1-window-only]`, `X` `_b1_metrics`;
  - `/^def _b1_m15/,/^def /s/except pl.exceptions.PolarsError as exc:/except KeyError as exc:/` (the same `except` stands in `_capturing_union`) against `test_b1_conditioning_names_a_15m_file_it_cannot_read[not-parquet]`, `X` `_b1_m15` — the `[missing]` case cannot kill it, since the command's own `OSError` refusal names the path too;
  - `/^def _b1_build/,/^def /s/except (AlphaError,/except (KeyError,/` (the same `except` stands in `_b2_build`) against `test_b1_conditioning_refuses_a_15m_set_short_of_the_last_decision_boundary_in_its_own_terms`, `X` `_b1_metrics` — without the catch the command's handler words it `over the full history of ohlc-test:`.

### Task 2 — the reproduction, data-gated, and the legacy map

**Files:** `tests/test_b1_records_reproduce.py` (new), `cli/research/subjects.py`, `tests/test_trial_registry_provenance.py`, `tests/test_research_command.py`.

- [ ] **Step 1 — the test** (`tests/test_b1_records_reproduce.py`):

```python
"""Records 45 and 46, B1's trials 1 and 2, re-derived by their subjects over ohlc-full at the precision their lost writer
stored (docs/specs/00130 D4): a moved metric, a moved input file or a moved verdict fails here, where the data is."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.registry import TrialRegistry
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_trial_registry_provenance import REGISTRY

pytestmark = pytest.mark.data

_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# The lost writer's decimals (docs/specs/00130's measured basis): 4 unless named; ints and per-year dicts exact.
_DECIMALS = {
    "dsr_corrected": 5,
    "per_period_sharpe_4h": 5,
    "turnover_a": 2,
    "turnover_b": 2,
    "turnover_reduction_pct": 2,
    "head_to_head_mean_outperf_2016": 9,
}


def _matrix(m: dict) -> str:
    """docs/specs/00045's decision matrix, the from-2016 read primary: the test's check, no subject's rule."""
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_2016"] > 0:
        if m["head_to_head_spa_p_2016"] < 0.05:
            return "adopt"
        if m["turnover_reduction_pct"] >= 20:
            return "park"
    return "reject"


def _stored(key: str, value):
    return round(value, _DECIMALS.get(key, 4)) if isinstance(value, float) else value


@pytest.mark.parametrize(
    ("trial_id", "name", "block_hash"),
    [
        pytest.param(
            45,
            "b1-conditioning",
            "<step 2's hash for 45>",
            marks=pytest.mark.skipif(
                not (_DATA_ROOT / "ohlc-15m").is_dir(), reason="data/ohlc-15m absent — the reproduction runs on the data host only"
            ),
            id="record-45",
        ),
        pytest.param(46, "b1-window-only", "<step 2's hash for 46>", id="record-46"),
    ],
)
@pytest.mark.skipif(not (_DATA_ROOT / "ohlc-full").is_dir(), reason="data/ohlc-full absent — the reproduction runs on the data host only")
def test_the_b1_subject_reproduces_its_record(trial_id, name, block_hash):
    record = {r.trial_id: r for r in TrialRegistry(REGISTRY).records}[trial_id]
    reader = ObservedReader(_DATA_ROOT)
    metrics = SUBJECTS[name].build(reader, "ohlc-full", None)

    assert compute_hash(reader.block()) == block_hash
    assert set(metrics) == set(record.metrics)
    assert {key: _stored(key, value) for key, value in metrics.items()} == record.metrics
    assert _matrix(metrics) == record.verdict


@pytest.mark.parametrize(
    ("passes", "outperf", "p_value", "turnover_cut", "verdict"),
    [
        pytest.param(0, 1e-06, 0.0, 50.0, "reject", id="the-bar-fails"),
        pytest.param(1, 0.0, 0.0, 50.0, "reject", id="no-outperformance"),
        pytest.param(1, 1e-06, 0.049, 0.0, "adopt", id="significant"),
        pytest.param(1, 1e-06, 0.05, 20.0, "park", id="turnover-down-20"),
        pytest.param(1, 1e-06, 0.05, 19.99, "reject", id="the-open-case"),
    ],
)
def test_the_matrix_gives_each_leaf_its_verdict(passes, outperf, p_value, turnover_cut, verdict):
    metrics = {
        "passes": passes,
        "head_to_head_mean_outperf_2016": outperf,
        "head_to_head_spa_p_2016": p_value,
        "turnover_reduction_pct": turnover_cut,
    }

    assert _matrix(metrics) == verdict
```

  The data case reaches two of the matrix's five leaves — record 45 the failed bar's, record 46 the no-outperformance one — so the leaf case, which needs no data and runs in CI, holds all five and the three boundaries (the outperformance at 0, `p` at 0.05, the turnover cut at 20). `TrialRecord.metrics` and `.verdict` are its attributes; `REGISTRY` is `tests/test_trial_registry_provenance.py`'s; `_DATA_ROOT` is rooted at `Path(__file__)`, not at that module's `REPO`, because `tests/test_live_venue_opt_in.py`'s skip-gate guard refuses a gate whose root is a name imported from another module; a record's `dataset_hash` is `compute_hash` of its datasets block, so `compute_hash(reader.block())` is the hash a record of this run would carry.

- [ ] **Step 2 — the block hashes**: with the two links present, run each subject once and print `compute_hash(reader.block())` (a scratch script under `.tmp/task2/`); paste each into its param. Expected, measured by the author's run of these fences on 2026-10-14: record 45 (`b1-conditioning`, blocks `ohlc-15m` and `ohlc-full`) `349b04f3808e6364ff6a3b60f13b306d50c4157a6cc43530f5502a8122edf520`, record 46 (`b1-window-only`, block `ohlc-full`) `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`. A printed hash other than Expected stops the task: report it with the block's per-file sha256s beside the input table of `.tmp/b1-measure/report.md`, and paste nothing. Then `uv run pytest -m data -q -rs tests/test_b1_records_reproduce.py -k record-46` and `-k record-45`, each its own call (the author's run, which also computed the grid points `(102, 7)` and `(102, 1234)` this build leaves out, measured 160 s and 179 s): both pass, skip count 0. A metric that differs stops the task: report the key, both values and the measured driver's raw value from `.tmp/b1-measure/out/trial45.json` or `trial46.json`, and change nothing to fit.

- [ ] **Step 3 — the map**: `LEGACY_INCUMBENTS` becomes `{33: "record33-combined", 44: "record44-crossfreq", 45: "b1-conditioning", 46: "b1-window-only", 47: "record44-crossfreq"}`; the literal in `test_the_legacy_incumbents_are_frozen_each_backed_by_a_subject_and_a_record_at_or_below_47` moves with it. The two cases that take 45 as the legacy record no subject reproduces take 43 instead, which stays unmapped: in `tests/test_trial_registry_provenance.py` `pytest.param(_against(45), _WITH_INCUMBENT, None, "names neither", id="45-in-no-map-and-no-invocation")` becomes `_against(43)` with `id="43-in-no-map-and-no-invocation"`, and in `tests/test_research_command.py` `@pytest.mark.parametrize("n", [33, 45], …)` becomes `[33, 43]`, its ids unchanged. Run `uv run pytest -q tests/test_trial_registry_provenance.py`, then `uv run pytest -q tests/test_research_command.py -k legacy`.

- [ ] **Step 4 — commit** after the consumers of the four files: `test(research): records 45 and 46 re-derive from their B1 subjects, and the legacy map holds them`, the body naming both data runs' summary lines.

- [ ] **Step 5 — probes** (each expected KILLED; the data-gated ones against the node id `tests/test_b1_records_reproduce.py::test_the_b1_subject_reproduces_its_record[record-46]` unless named). `mutate-probe.sh` runs the case three times — baseline, control, mutation — so each control is one that fails fast: `X` `_b1_metrics` for a mutation of `cli/research/subjects.py`, and for a mutation of the test file `X` the test's own function, which the node id then no longer finds. A data-gated probe takes about 5–6 minutes, one foreground call with a 600 s timeout.
  - the 2016 cut `if h4_ts[k] >= _B1_FROM_2016)` → `if h4_ts[k + 1] >= _B1_FROM_2016)` in `cli/research/subjects.py` (record 46's from-2016 SPA p moves 0.8061 → 0.8076);
  - `_DECIMALS`' `"head_to_head_mean_outperf_2016": 9` → `5` in the test;
  - `s/^    return "reject"$/    return "adopt"/` in the test (the matrix's last return; its first is indented eight spaces);
  - the block hash literal for 46, one hex digit changed;
  - `scales = [1.0] * n if m15 is None else …` → `scales = [0.5] * n if m15 is None else …` (record 46's turnover, drawdown and differing-stamp count move; a uniform 0.5 halves every net return exactly, so its Sharpes do not);
  - `s/< 0.05:/<= 0.05:/` in the test against `tests/test_b1_records_reproduce.py::test_the_matrix_gives_each_leaf_its_verdict[turnover-down-20]`, needing no data;
  - in `cli/research/subjects.py`, `45: "b1-conditioning"` → `45: "b1-window-only"` against `tests/test_trial_registry_provenance.py::test_the_legacy_incumbents_are_frozen_each_backed_by_a_subject_and_a_record_at_or_below_47`, its control `s/^LEGACY_INCUMBENTS:/LEGACY_INCUMBENTS_GONE:/`, since that case builds nothing.

### Task 3 — the three legacy digests recomputed

**Files:** `tests/test_legacy_dataset_pins.py`, `docs/reference/legacy-dataset-pins.jsonl`, `docs/reference/data-catalog-full.md`, `docs/specs/00086-verifiable-dataset-provenance-design.md`.

- [ ] **Step 1 — the failing test** (`tests/test_legacy_dataset_pins.py`, already module-marked `data`):

```python
_OHLC_FULL = _ROOT / "data" / "ohlc-full"
# The recovered trial44_write.py's manifest (git show 74080b69e:docs/reference/trial43-recovered-runners/trial44_write.py),
# transcribed: per asset its row count, first and last stamp and first and last close, nothing else of the bytes.
_LEGACY_ASSETS = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")


def _legacy_manifest(interval: int) -> str:
    from cli.ohlc.dataset import read_parquet

    parts = []
    for asset in _LEGACY_ASSETS:
        frame = read_parquet(_OHLC_FULL / asset / "EUR" / f"{interval}.parquet")
        parts.append(f"{asset}:{len(frame)}:{frame['ts'][0]}:{frame['ts'][-1]}:{frame['close'][0]}:{frame['close'][-1]}")
    return "|".join(sorted(parts))


@pytest.mark.parametrize(
    ("prefix", "intervals"),
    [("81dc9b44", (240,)), ("ba47e37e", (1440,)), ("45275ebe", (1440, 240))],
)
def test_the_legacy_digest_recomputes_from_the_files_it_names(prefix, intervals):
    if not _OHLC_FULL.is_dir():
        pytest.skip("data/ohlc-full absent — the legacy digests recompute on the data host only")
    row = next(r for r in _rows() if r["hash"].startswith(prefix))
    text = "||".join(_legacy_manifest(i) for i in intervals)
    assert hashlib.sha256(text.encode()).hexdigest() == row["hash"]
    assert row["confidence"] == "reproduced" and row["evidence"]["recipe_intervals"] == list(intervals)
```

  Run it: the three cases fail on `confidence` (the digests themselves already match, measured).

- [ ] **Step 2 — the pins rows and the catalog line**: rewrite all four of `docs/reference/legacy-dataset-pins.jsonl`'s lines — three re-rated, `cccb8d17`'s re-worded — key order as the file writes them, `trial_ids` untouched, then the catalog's line:
  - `81dc9b44…`: `confidence` `reproduced`; `referent` `"data/ohlc-full 4h, the ten EUR assets' 240 files (REPRODUCED by the recovered trial44_write.py manifest recipe — a weak digest: per asset the row count, the first and last stamp and the first and last close, not every byte)"`; `evidence` `{"recipe": "sha256 of '|'.join(sorted(f'{a}:{len(f)}:{ts[0]}:{ts[-1]}:{close[0]}:{close[-1]}' per asset)) over data/ohlc-full/<A>/EUR/240.parquet", "recipe_intervals": [240], "recipe_source": "git show 74080b69e:docs/reference/trial43-recovered-runners/trial44_write.py, manifest(interval)", "executed_by": "tests/test_legacy_dataset_pins.py, data-gated", "ruling": "re-rated reproduced 2026-10-14 on the owner's word (spec 00130 D6), amending spec 00086 D6's unverifiable ruling of 2026-08-09"}`, the whole object, so `not_reproduced` goes;
  - `ba47e37e…`: `confidence` `reproduced`; `referent` `"data/ohlc-full daily, the ten EUR assets' 1440 files (REPRODUCED by the recovered trial44_write.py manifest recipe — a weak digest: per asset the row count, the first and last stamp and the first and last close, not every byte; what trials 33 and 35's drivers read is not established)"`; `evidence` the five keys above, `240` read `1440` in `recipe` and `recipe_intervals` `[1440]`, with `"scope_mismatch": "trial_ids cover 36 A1 records plus 2 P1 records (33, 35); the recipe reproduces the digest from the daily files, and committed state does not establish what those two P1 runs read — both ran from scratchpad drivers — so the reproduction does not extend to them"` before `ruling`; `extent_match`, `exclusion` and `not_reproduced` go, the recipe superseding the first two and falsifying the third;
  - `45275ebe…`: `confidence` `reproduced`; `referent` `"data/ohlc-full daily and 4h, the ten EUR assets' 1440 and 240 files (REPRODUCED by the recovered trial44_write.py manifest recipe, the daily manifest joined to the 4h one by '||' — a weak digest: per asset the row count, the first and last stamp and the first and last close, not every byte)"`; `evidence` the five keys above, `recipe` `"sha256 of manifest(1440) + '||' + manifest(240), each manifest '|'.join(sorted(f'{a}:{len(f)}:{ts[0]}:{ts[-1]}:{close[0]}:{close[-1]}' per asset)) over data/ohlc-full/<A>/EUR/<interval>.parquet"` and `recipe_intervals` `[1440, 240]`, with `extent_pins` before `ruling`, its last clause "those pins, not the digest, are what identifies record 44's dataset" now "those pins and the weak digest identify record 44's dataset"; `inherits` and `stated_recipe_does_not_reproduce` go, the first now false and the second answered by the recipe it says the runbook lacks;
  - `cccb8d17…`: its `referent` loses "the 4h operand is itself unrecoverable, so only the 15m half is traceable to bytes" for "both operands reproduced: the 4h from data/ohlc-full by a weak digest, the 15m from data/ohlc-15m's manifest", and `evidence.operand_4h_caveat` is replaced by `"operand_4h_anchor": "81dc9b44's own row, reproduced from data/ohlc-full's 240 files by a weak digest"`.
  - `docs/reference/data-catalog-full.md`'s schema-4 paragraph, the one live page that counts the pins' grades, drops "— two of the four are accepted as permanently unverifiable": the pins file is where the grades are read.

- [ ] **Step 3 — the grade rules** (`tests/test_legacy_dataset_pins.py`): the module docstring becomes `"""The four pre-schema-4 hashes, each recomputed: three from data/ohlc-full by the recovered manifest recipe, one composed from two operands (spec 00086 D6 as amended by spec 00130 D6)."""`; `test_the_reproduced_recipe_executes_from_its_own_literals` selects the row whose evidence holds `operand_4h`; `test_epistemics_live_in_the_referent_value`'s `reproduced` branch asserts, of every reproduced row, `"REPRODUCED" in row["referent"]` and `"weak digest" in row["referent"]` (the composed row's 4h operand rests on that digest too), of a row whose evidence holds `operand_4h`, `row["evidence"]["operand_4h"][:8] in row["referent"]`, and of one whose evidence holds `scope_mismatch`, `"not established" in row["referent"]` — each qualifier a row's evidence carries is read in its referent, never only in the sibling field; `test_the_reproduced_15m_operand_is_the_manifest_basket_on_disk` selects the same composed row. `uv run pytest -q tests/test_legacy_dataset_pins.py` (the data family runs here; skip count 0 with `data/ohlc-full` and `data/ohlc-15m` linked).

- [ ] **Step 4 — spec 00086's D6** (`docs/specs/00086-verifiable-dataset-provenance-design.md`): after the ruling paragraph, one line: `**Amended 2026-10-14 (spec 00130 D6, the owner's ruling of 2026-10-14):** the recovered trial44_write.py's manifest recipe recomputes 81dc9b44, ba47e37e and 45275ebe from data/ohlc-full; the three rows are reproduced, each naming its weak digest, and tests/test_legacy_dataset_pins.py executes the recipe.`; each of the four bullets ends with an amendment naming the same two — `cccb8d17`'s `Amended (spec 00130 D6, the owner's ruling of 2026-10-14): its 4h operand 81dc9b44 is reproduced by a weak digest, and its referent says so.`, `ba47e37e`'s and `81dc9b44`'s `Amended (spec 00130 D6, the owner's ruling of 2026-10-14): reproduced by a weak digest, named in the referent.` (`ba47e37e`'s adding `The scope note stays, and the referent carries it.`), `45275ebe`'s `Amended (spec 00130 D6, the owner's ruling of 2026-10-14): reproduced by a weak digest over both intervals; the entry drops its runbook-composition note.`; bounded claim 5's "The 44 unresolved hashes stay unresolved; D6 documents, never repairs" gains `— amended by spec 00130 D6, the owner's ruling of 2026-10-14: the three legacy digests recompute; the registry stays append-only and no record changes`. The file keeps its existing wrap.

- [ ] **Step 5 — commits**: `test(research): the three legacy digests recompute from data/ohlc-full by the recovered recipe`, the test, the pins file and the catalog line together, then `docs(specs): spec 00086 D6 amended — the legacy digests are reproduced`. Consumers of each file before its commit.

- [ ] **Step 6 — probes** (each against a case of `tests/test_legacy_dataset_pins.py`, expected KILLED; a sed on the JSON file is addressed by its row, `/^{"hash": "<prefix>/`, and each text it replaces stands once on that row; `ast.parse` does not apply to the JSON file, so its dry-run is `python3 -c 'import json,sys; [json.loads(l) for l in sys.stdin]'` over the sed's output):
  - in the test, the manifest's `"|".join(` → `",".join(`, and `{frame['close'][-1]}` → `{frame['close'][0]}`, each against `test_the_legacy_digest_recomputes_from_the_files_it_names[81dc9b44-intervals0]`;
  - `--file docs/reference/legacy-dataset-pins.jsonl`, the control the `81dc9b44` row's `(REPRODUCED` → `(reproduced` (the referent rule reads the capitals), against `test_epistemics_live_in_the_referent_value`: the `81dc9b44` row's `weak digest` → `strong digest`; the `cccb8d17` row's `the 4h digest 81dc9b44 joined` → `the 4h digest joined`; the `ba47e37e` row's `is not established` → `is established`;
  - `--file docs/reference/legacy-dataset-pins.jsonl`, the control the `cccb8d17` row's `"operand_4h": ` → `"operand_4h_gone": ` (no row then holds the key the two cases select by): that row's `"operand_4h": "81dc9b44` → `"operand_4h": "81dc9b45` against `test_the_reproduced_recipe_executes_from_its_own_literals`, and its `"operand_15m": "0fed24a6` → `"operand_15m": "0fed24a7` against `test_the_reproduced_15m_operand_is_the_manifest_basket_on_disk`.

### Task 4 — T0223 resolved

**Files:** `docs/open-topics/T0223-records-45-and-46-rebuilt-as-a-b1-subject.md` → `docs/open-topics/archive/`, `docs/open-topics/README.md`.

- [ ] **Step 1**: `status: resolved`, `ripe_when:` deleted, `## Suggested next steps` removed, `## Resolution` naming this branch's commits (the subjects, the reproduction test and the map, the digests), the measured result (35 of 35 metrics each at the registered precision; raw equality for 14 of record 45's and 12 of record 46's, every other float rounded by the lost writer), that the subjects are evaluate-only on the owner's ruling of 2026-10-14, so spec 00045's matrix is the reproduction test's check and not a subject's rule, and that the three legacy digests were recomputed on the owner's word — each of the topic's three suggested steps answered there; `git mv` into `archive/`; `uv run python infra/scripts/topics-index.py`; `uv run pytest -q tests/test_open_topics_frontmatter.py`.
- [ ] **Step 2**: commit `docs(open-topics): T0223 resolved — records 45 and 46 re-derive from two committed subjects`, after the consumers of the topic files.

### Task 5 — the reads and the PR (the controller's)

- [ ] `git diff --quiet develop HEAD -- cli/engine` exits 0.
- [ ] With the links present: `uv run pytest -m data -q -rs tests/test_b1_records_reproduce.py tests/test_legacy_dataset_pins.py tests/test_research_control.py`, skip count 0 (the record-45 and record-46 cases in separate calls if a part would pass 400 s); then `uv run pytest -q tests/test_trial_registry_provenance.py`, which carries no `data` mark, so `-m data` would deselect the legacy-map case.
- [ ] The repo's trio over the branch: `pre-review`, `review`, `re-review` at most twice; push only after the read; the PR through `open-pr` — `feat(research): 00130 — records 45 and 46 re-derived as B1 subjects`, its body naming the read line, the probe verdicts and T0223 resolved; the change-index row; merge on the owner's word through `merge-pr`; the two data links removed with `rm` before `git worktree remove`, the main checkout's `data/` listing read after.
