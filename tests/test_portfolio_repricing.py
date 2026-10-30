import math
import types
from dataclasses import fields, replace
from datetime import UTC, datetime, time, timedelta

import pytest

from cli.portfolio import crossfreq_system, repricing
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig
from cli.portfolio.record44_legs import calendar_year_slices
from cli.portfolio.repricing import (
    METRIC_KEYS,
    RepricingError,
    bar_flags,
    conditional_live,
    live_state_returns,
    multipliers_moved,
    refuse_past_in_sample,
    repricing_metrics,
    repricing_verdict,
    spa_cells,
    stressed_config,
)
from cli.portfolio.revalidation import P1_VAR_TRIALS
from cli.research import subjects
from cli.validation import deflated_sharpe_ratio, max_drawdown, sharpe

_LAST_H4 = datetime(2026, 3, 31, 20, tzinfo=UTC)
_REGISTERED = subjects._RECORD44_CONFIG
_BASIS = replace(_REGISTERED, fee_per_side=0.0030, spread_per_side=0.0005)
_SPA_GRID = ((30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))
_SPA_KEYS = ("spa_p_full", "spa_p_decisive", *(f"spa_grid_b{block}_s{seed}" for block, seed in _SPA_GRID))
_FLAG_KEYS = ("dsr_pass", "spa_pass", "cost_stress_pass", "worst_slice_relative_pass", "passes")


def _closes(n: int, j: int) -> list[float]:
    return [100.0 * 1.001**i * (1 + 0.05 * math.sin(i / 7 + 0.7 * j)) for i in range(n)]


def _inputs(last_h4: datetime, days: int):
    last_day = datetime.combine(last_h4.date(), time(), tzinfo=UTC)
    daily_ts = [last_day - timedelta(days=days - 1 - i) for i in range(days)]
    h4_ts = [last_h4 - timedelta(hours=4 * (6 * days - 1 - i)) for i in range(6 * days)]
    assets = CrossfreqSystemConfig().assets
    daily_prices = {a: _closes(days, j) for j, a in enumerate(assets)}
    h4_prices = {a: _closes(6 * days, j) for j, a in enumerate(assets)}
    return daily_ts, daily_prices, h4_ts, h4_prices


def _bench_series(n: int) -> list[float]:
    return [0.0002 * math.sin(i / 3) for i in range(n)]


def _bench_recorder(calls: list):
    def bench(h4_prices, *, cost_per_side):
        calls.append(cost_per_side)
        return _bench_series(len(next(iter(h4_prices.values()))) - 1)

    return bench


def _spa_recorder(calls: list):
    def spa(matrix, *, mean_block, n_resamples, seed):
        calls.append((matrix, mean_block, seed, n_resamples))
        return {"p_value": 0.01}

    return spa


def _figure_run(monkeypatch) -> types.SimpleNamespace:
    daily_ts, daily_prices, h4_ts, h4_prices = _inputs(_LAST_H4, 600)
    configs = [_REGISTERED, _BASIS, *(replace(_BASIS, fee_per_side=0.0030 * m, spread_per_side=0.0005 * m) for m in (1.5, 2.0))]
    run = types.SimpleNamespace(
        configs=configs,
        h4_ts=h4_ts,
        built=[],
        kept={},
        bench_calls=[],
        spa_calls=[],
        dsr_calls=[],
        dsr_returns=[],
        flag_calls=[],
        flag_returns=[],
    )

    # The synthetic prices leave the governor idle at every basis: each build's counts, its ungoverned return 100 and
    # its first t multipliers are set apart here, or a figure read off the wrong build would pass.
    def build(daily_prices, daily_ts, h4_prices, h4_ts, *, config):
        assert config in configs, config
        t = configs.index(config) + 1
        run.built.append(config)
        real = crossfreq_system.build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
        run.kept[t] = replace(
            real,
            cap_breach_bars=t,
            governor_engaged_bars=10 * t,
            ungoverned_net=[r - 0.01 * t if k == 100 else r for k, r in enumerate(real.ungoverned_net)],
            multipliers=[0.5 if k < t else m for k, m in enumerate(real.multipliers)],
        )
        return run.kept[t]

    def dsr(sr, n_obs, *, n_trials, var_trials):
        run.dsr_calls.append((sr, n_obs, n_trials, var_trials))
        run.dsr_returns.append(deflated_sharpe_ratio(sr, n_obs, n_trials, var_trials))
        return run.dsr_returns[-1]

    def flags(**kwargs):
        run.flag_calls.append(kwargs)
        run.flag_returns.append(bar_flags(**kwargs))
        return run.flag_returns[-1]

    monkeypatch.setattr(repricing, "build_crossfreq_system_fast", build)
    monkeypatch.setattr(repricing, "benchmark_4h_net_of_cost", _bench_recorder(run.bench_calls))
    monkeypatch.setattr(repricing, "reality_check_pvalue", _spa_recorder(run.spa_calls))
    monkeypatch.setattr(repricing, "deflated_sharpe_ratio", dsr)
    monkeypatch.setattr(repricing, "bar_flags", flags)
    run.metrics = repricing_metrics(daily_ts, daily_prices, h4_ts, h4_prices, registered=_REGISTERED, basis=_BASIS, n_trials=5)
    return run


def _at_record_47(**fields_: float) -> dict:
    return {**dict.fromkeys(METRIC_KEYS, 0), "registered_basis_returns": 27337, "registered_basis_sharpe": 1.5609, **fields_}


def test_a_bar_past_the_in_sample_end_is_refused_before_any_build(monkeypatch):
    daily_ts, daily_prices, h4_ts, h4_prices = _inputs(_LAST_H4, 600)
    assert refuse_past_in_sample(daily_ts, h4_ts) is None
    later_h4 = [*h4_ts, h4_ts[-1] + timedelta(hours=4)]
    with pytest.raises(RepricingError) as refused:
        refuse_past_in_sample(daily_ts, later_h4)
    assert "2026-04-01 00:00:00+00:00" in str(refused.value)
    with pytest.raises(RepricingError) as refused:
        refuse_past_in_sample([*daily_ts, daily_ts[-1] + timedelta(days=1)], h4_ts)
    assert "2026-04-01 00:00:00+00:00" in str(refused.value)

    builds, bench_calls, spa_calls = [], [], []

    def build(*args, **kwargs):
        builds.append(kwargs)
        raise AssertionError("a book was built over a read past the in-sample end")

    monkeypatch.setattr(repricing, "build_crossfreq_system_fast", build)
    monkeypatch.setattr(repricing, "benchmark_4h_net_of_cost", _bench_recorder(bench_calls))
    monkeypatch.setattr(repricing, "reality_check_pvalue", _spa_recorder(spa_calls))
    later_h4_prices = {a: [*closes, closes[-1]] for a, closes in h4_prices.items()}
    with pytest.raises(RepricingError):
        repricing_metrics(daily_ts, daily_prices, later_h4, later_h4_prices, registered=_REGISTERED, basis=_BASIS, n_trials=5)
    assert (builds, bench_calls, spa_calls) == ([], [], [])


def test_the_stressed_basis_scales_both_terms_and_keeps_every_other_field():
    stressed = stressed_config(replace(_BASIS, long_cap=0.15), 1.5)
    assert (stressed.fee_per_side, stressed.spread_per_side, stressed.long_cap) == (0.0030 * 1.5, 0.0005 * 1.5, 0.15)
    scaled = ("fee_per_side", "spread_per_side", "long_cap")
    assert {f.name: getattr(stressed, f.name) for f in fields(stressed) if f.name not in scaled} == {
        f.name: getattr(_BASIS, f.name) for f in fields(_BASIS) if f.name not in scaled
    }


def test_each_figure_is_the_picked_basis_builds_and_the_check_the_registered_build(monkeypatch):
    run = _figure_run(monkeypatch)
    metrics, registered, basis = run.metrics, run.kept[1], run.kept[2]
    g, bench = basis.governed_net, _bench_series(len(run.h4_ts) - 1)
    live = live_state_returns(basis)
    assert metrics["ann_sharpe_noc"] != metrics["registered_basis_sharpe"]
    assert metrics["maxdd"] != metrics["maxdd_pre_governor"]
    assert conditional_live(g, live) != conditional_live(registered.governed_net, live)

    assert run.built == run.configs
    assert metrics["registered_basis_returns"] == registered.n_periods
    assert metrics["registered_basis_sharpe"] == sharpe(registered.governed_net, periods_per_year=2190)
    assert metrics["ann_sharpe_noc"] == sharpe(g, periods_per_year=2190)
    assert metrics["ann_sharpe_noc_decisive"] == sharpe(g[1380:], periods_per_year=2190)
    assert metrics["per_period_sharpe_4h"] == sharpe(g)
    assert (metrics["cap_breach_bars"], metrics["governor_engaged_bars"]) == (2, 20)
    assert (metrics["maxdd"], metrics["maxdd_pre_governor"]) == (max_drawdown(g), max_drawdown(basis.ungoverned_net))
    assert metrics["cost_stress_1_5x_sharpe_ann"] == sharpe(run.kept[3].governed_net, periods_per_year=2190)
    assert metrics["cost_stress_2x_sharpe_ann"] == sharpe(run.kept[4].governed_net, periods_per_year=2190)
    assert metrics["bench4h_sharpe_full"] == sharpe(bench, periods_per_year=2190)
    assert metrics["bench4h_sharpe_decisive"] == sharpe(bench[1380:], periods_per_year=2190)
    assert run.bench_calls == [_BASIS.cost_per_side]
    assert run.dsr_calls == [(sharpe(g), len(g), 5, P1_VAR_TRIALS)]
    assert metrics["dsr"] == run.dsr_returns[0]
    assert metrics["var_trials_4h"] == P1_VAR_TRIALS
    outperformance = [[b - m] for b, m in zip(g, bench, strict=True)]
    matrices = [call[0] for call in run.spa_calls]
    assert (len(matrices), matrices.count(outperformance), matrices.count(outperformance[1380:])) == (7, 1, 6)
    assert (metrics["conditional_live_sharpe"], metrics["conditional_live_bars"]) == (conditional_live(g, live), len(live))
    assert metrics["multipliers_moved"] == 1
    (flag_call,) = run.flag_calls
    assert {key: flag_call[key] for key in ("dsr", "spa", "stress_15")} == {
        "dsr": metrics["dsr"],
        "spa": {key: metrics[key] for key in _SPA_KEYS},
        "stress_15": metrics["cost_stress_1_5x_sharpe_ann"],
    }
    assert {key: metrics[key] for key in _FLAG_KEYS} == run.flag_returns[0]
    assert (metrics["fee_per_side"], metrics["spread_per_side"], metrics["cost_per_side"]) == (0.0030, 0.0005, _BASIS.cost_per_side)


def test_the_spa_cells_read_the_outperformance_over_the_full_and_the_decisive_rows(monkeypatch):
    def p_value(block: int, seed: int, rows: int) -> float:
        return block / 1e4 + seed / 1e7 + rows / 1e10

    calls = []

    def spa(matrix, *, mean_block, n_resamples, seed):
        calls.append((matrix, mean_block, seed, n_resamples))
        return {"p_value": p_value(mean_block, seed, len(matrix))}

    monkeypatch.setattr(repricing, "reality_check_pvalue", spa)
    book = [0.001 * math.sin(i / 5) + 0.0001 for i in range(1500)]
    bench = [0.0008 * math.cos(i / 9) for i in range(1500)]
    cells = spa_cells(book, bench)
    full = [[b - m] for b, m in zip(book, bench, strict=True)]
    decisive_cells = ((30, 42), *_SPA_GRID)
    by_cell = {(block, seed, len(matrix)): (matrix, n_resamples) for matrix, block, seed, n_resamples in calls}
    assert len(calls) == len(by_cell) == 7
    assert by_cell == {(30, 42, 1500): (full, 2000), **{(block, seed, 120): (full[1380:], 2000) for block, seed in decisive_cells}}
    assert cells == {
        "spa_p_full": p_value(30, 42, 1500),
        **{key: p_value(block, seed, 120) for key, (block, seed) in zip(_SPA_KEYS[1:], decisive_cells, strict=True)},
    }


def test_each_leg_at_its_threshold():
    passing_spa = {"spa_p_full": 0.9, **dict.fromkeys(_SPA_KEYS[1:], 0.0499)}
    passing = {"dsr": 0.9500001, "spa": passing_spa, "stress_15": 1e-9, "beats_worst": True}
    every = dict.fromkeys(_FLAG_KEYS, 1)
    assert bar_flags(**passing) == every
    assert bar_flags(**{**passing, "dsr": 0.95}) == {**every, "dsr_pass": 0, "passes": 0}
    for key in _SPA_KEYS[1:]:
        assert bar_flags(**{**passing, "spa": {**passing_spa, key: 0.05}}) == {**every, "spa_pass": 0, "passes": 0}
    assert bar_flags(**{**passing, "stress_15": 0.0}) == {**every, "cost_stress_pass": 0, "passes": 0}
    assert bar_flags(**{**passing, "beats_worst": False}) == {**every, "worst_slice_relative_pass": 0, "passes": 0}


def test_the_live_state_reads_the_returns_own_row():
    flat = [0.0] * 6
    result = types.SimpleNamespace(
        n_periods=5,
        sleeve_positions={
            "B": {"X": flat, "Y": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0]},
            "A1": {"X": [0.0, 1e-18, 0.0, 0.0, 0.0, 0.0], "Y": flat},
            "A2": {"X": [0.0, 0.0, 0.0, 0.3, 0.0, 0.3], "Y": [0.1, 0.1, 0.0, 0.0, -0.1, 0.0]},
        },
    )
    assert live_state_returns(result) == [3, 4]
    assert conditional_live([0.01 * k for k in range(5)], [3]) == 0.0
    assert conditional_live([0.0, 0.0, 0.0, 0.02, 0.02], [3, 4]) == 0.0
    g = [0.001 * math.sin(k) for k in range(40)]
    live = [3, 4, 11, 17, 29]
    assert conditional_live(g, live) == sharpe([g[k] for k in live], periods_per_year=2190)


def test_multipliers_moved_counts_the_completed_rows_alone():
    registered = types.SimpleNamespace(n_periods=5, multipliers=[1.0] * 6)
    basis = types.SimpleNamespace(n_periods=5, multipliers=[1.0, 0.5, 1.0, 0.75, 1.0, 0.25])
    assert multipliers_moved(registered, basis) == 2


@pytest.mark.parametrize("beats", [True, False])
def test_the_worst_slice_reads_the_governed_book_and_the_benchmark_by_close_year(monkeypatch, beats):
    daily_ts, daily_prices, h4_ts, h4_prices = _inputs(_LAST_H4, 600)
    calls = []

    def worst_slice(book_slices, benchmark_slices):
        calls.append((book_slices, benchmark_slices))
        return {"beats_benchmark_worst": beats, "worst_book_sharpe": -0.25, "worst_benchmark_sharpe": -0.5}

    monkeypatch.setattr(repricing, "benchmark_4h_net_of_cost", _bench_recorder([]))
    monkeypatch.setattr(repricing, "reality_check_pvalue", _spa_recorder([]))
    monkeypatch.setattr(repricing, "benchmark_relative_worst_slice", worst_slice)
    metrics = repricing_metrics(daily_ts, daily_prices, h4_ts, h4_prices, registered=_REGISTERED, basis=_BASIS, n_trials=5)
    g = crossfreq_system.build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=_BASIS).governed_net
    bench = _bench_series(len(h4_ts) - 1)
    assert calls == [(calendar_year_slices(g, h4_ts), calendar_year_slices(bench, h4_ts))]
    assert (metrics["dsr_pass"], metrics["spa_pass"], metrics["cost_stress_pass"]) == (1, 1, 1)
    assert (metrics["worst_slice_relative_pass"], metrics["passes"]) == (int(beats), int(beats))
    assert (metrics["worst_book_sharpe"], metrics["worst_benchmark_sharpe"]) == (-0.25, -0.5)


@pytest.mark.parametrize("passes,verdict", [(1, "adopt"), (0, "park")])
def test_the_verdict_adopts_on_every_leg_and_parks_on_any_failing(passes, verdict):
    assert repricing_verdict(_at_record_47(passes=passes)) == verdict


@pytest.mark.parametrize(
    "returns,registered_sharpe,verdict",
    [
        (27336, 1.5609, None),
        (27337, 1.5609 + 0.00006, None),
        (27337, 1.5609 - 0.00006, None),
        (27337, 1.5609 + 0.00004, "adopt"),
        (27337, 1.5609 - 0.00004, "adopt"),
    ],
)
def test_the_instrument_check_gives_no_verdict_off_record_47(returns, registered_sharpe, verdict):
    metrics = _at_record_47(registered_basis_returns=returns, registered_basis_sharpe=registered_sharpe, passes=1)
    assert repricing_verdict(metrics) == verdict


def test_the_metrics_carry_exactly_the_declared_keys_as_builtins(monkeypatch):
    metrics = _figure_run(monkeypatch).metrics
    assert set(metrics) == METRIC_KEYS
    assert {key: type(value) for key, value in metrics.items() if type(value) not in (int, float)} == {}
