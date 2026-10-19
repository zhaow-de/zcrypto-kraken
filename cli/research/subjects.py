"""The evaluable subjects: committed systems, each reproducing a registry record or registering a trial.

A subject declares its `--dataset` series, so the command can refuse an incomplete dataset before any read; a second
dataset its `build` reads goes undeclared, and the build names a file of it that it cannot read.
Every byte a `build` reads goes through `ObservedReader`."""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import polars as pl

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.alpha.a2 import _asset_directions_a2
from cli.alpha.b1 import (
    B1Config,
    book_turnover,
    condition_positions,
    per_year_gated_counts,
    per_year_scaled_counts,
    seasonality_gates,
    vol_state_scale,
)
from cli.alpha.b1_exit import (
    a2_slot_positions,
    asset_directions_hourly_exit,
    exit_events_per_year,
    hourly_closes_differ_per_year,
    interior_closes_by_asset,
    intra_turnover,
    net_of_cost_hourly,
    price_paths,
)
from cli.alpha.b1_rv import (
    a2_positions_with_weights,
    hourly_rv_inverse_vol_weights,
    per_year_mean_weights,
    weight_total_variation,
    weights_differ_count,
)
from cli.alpha.b1_volume import (
    a2_positions_on_directions,
    asset_directions_confirmed,
    confirmations_by_asset,
    directions_differ_per_year,
    entry_events_per_year,
)
from cli.alpha.b2 import (
    B2Config,
    close_grid,
    derisk_scales,
    funding_grid_feature,
    net_of_cost,
    per_year_engaged_counts,
    per_year_max_drawdown,
    per_year_positions_differ,
    per_year_turnover,
    scale_positions,
)
from cli.alpha.errors import AlphaError
from cli.alpha.killbar import a1_kill_bar, net_of_cost_verdict
from cli.backtest.errors import BacktestError
from cli.benchmark.errors import BenchmarkError
from cli.derivatives.funding import PERP_SYMBOLS
from cli.features.derivatives import coverage_by_year
from cli.features.errors import FeatureError
from cli.portfolio.builder import CombinedSystemConfig, build_combined_system
from cli.portfolio.crossfreq_system import (
    CrossfreqSystemConfig,
    CrossfreqSystemResult,
    _ffill_btc,
    build_crossfreq_system_fast,
)
from cli.portfolio.errors import PortfolioError
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices, load_union
from cli.registry.observed import ObservedReader
from cli.risk.errors import RiskError
from cli.validation import ValidationError, max_drawdown, reality_check_pvalue, sharpe

PPY_DAILY = 365
PPY_4H = 2190


class SubjectError(Exception):
    """A subject's refusal of an input it cannot evaluate, its message naming the series or the window: the command exits
    1 on it, never a traceback."""


# The class of every error a subject's build can raise from a compute package; one more is added here and to
# `_COMPUTE_ERRORS` in tests/test_research_command.py.
EVALUATION_ERRORS = (AlphaError, BacktestError, BenchmarkError, FeatureError, PortfolioError, RiskError, ValidationError)


@dataclass(frozen=True)
class Subject:
    name: str
    intervals: tuple[int, ...]
    assets: tuple[str, ...]
    build: Callable[[ObservedReader, str, tuple | None, str | None, bool], dict]
    spec: str | None = None  # repo-relative path; its sha256 is the record's spec_hash
    metric_keys: frozenset[str] = frozenset()  # exactly the keys build returns
    seeds: tuple[int, ...] = ()
    verdict: Callable[[dict], str | None] | None = None  # docs/specs/00129 D4; None: evaluate-only
    no_verdict: str | None = None  # docs/specs/00129 D4, D7: the outcome a reading carries when the rule returns None
    incumbent: str | None = None  # docs/specs/00129 D3: the subject whose book this one builds in the same run
    family: str | None = None  # docs/specs/00133 D4: the registry family key a ruled subject's trials count against
    n_trials: int | None = None  # docs/specs/00133 D4: the count its kill bars deflate at, frozen once a record or reading lands


def required_relpaths(subject: Subject) -> list[str]:
    return [f"{a}/EUR/{i}.parquet" for a in subject.assets for i in subject.intervals]


def _capturing_union(
    reader: ObservedReader,
    dataset: str,
    interval: int,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
):
    """The bare relative root makes each path `load_union` composes `<BASE>/<QUOTE>/<interval>.parquet`: a frozen
    dataset's relative key, or, read as of a day, the rolling dataset's pair and grid."""

    def read(path: Path) -> pl.DataFrame:
        try:
            if as_of is None:
                frame = reader.read_series(dataset, path.as_posix(), window=window)
            else:
                frame = reader.read_rolling(
                    dataset, "/".join(path.parts[:2]), int(path.stem), as_of, window=window, accept_holes=accept_holes
                )
        except pl.exceptions.PolarsError as exc:
            raise SubjectError(f"{dataset}/{path.as_posix()}: {exc}") from exc
        # `load_union` indexes `close` outside this read, where a missing one would no longer name its file; a missing `ts`
        # fails the read itself.
        if "close" not in frame.columns:
            raise SubjectError(f"{dataset}/{path.as_posix()}: no close column")
        return frame

    return load_union(interval, root=Path(), read=read)


def _series(dataset: str, asset: str, interval: int, as_of: str | None) -> str:
    """Read as of a day, a series is the rolling dataset's pair and grid, which no file holds alone."""
    if as_of is None:
        return f"{dataset}/{asset}/EUR/{interval}.parquet"
    return f"{dataset} {asset}/EUR at {interval} minutes as of {as_of}"


def _refuse_unfed_grids(
    dataset: str,
    as_of: str | None,
    daily_ts: list[datetime],
    daily_prices: dict[str, list[float | None]],
    h4_prices: dict[str, list[float | None]],
) -> None:
    """Refused here because `build_crossfreq_system_fast` admits both shapes and then fails on them with a plain
    `ValueError` or `AttributeError`, which the command does not catch."""
    for interval, prices in ((1440, daily_prices), (240, h4_prices)):
        for asset, closes in prices.items():
            if all(close is None for close in closes):
                raise SubjectError(f"{_series(dataset, asset, interval, as_of)}: no close in the window read")
    if daily_prices["BTC"][0] is None:
        raise SubjectError(
            f"{_series(dataset, 'BTC', 1440, as_of)}: no close at {daily_ts[0]}, the first daily stamp of the window read, "
            "and the BTC forward fill cannot bridge a leading gap"
        )


# A legacy subject's cost is a literal of its own, never the shared default a re-price moves (docs/specs/00129 D5): a
# replay of the record it stands for reads the cost that record ran on.
_RECORD44_CONFIG = CrossfreqSystemConfig(fee_per_side=0.0040, spread_per_side=0.0020)
_RECORD33_CONFIG = CombinedSystemConfig(spot_fee_per_side=0.006)


def _crossfreq_book(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> tuple[list[datetime], dict[str, list[float | None]], list[datetime], dict[str, list[float | None]], CrossfreqSystemResult]:
    daily_ts, daily_prices = _capturing_union(reader, dataset, 1440, window, as_of, accept_holes)
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    _refuse_unfed_grids(dataset, as_of, daily_ts, daily_prices, h4_prices)
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=_RECORD44_CONFIG)
    return daily_ts, daily_prices, h4_ts, h4_prices, result


def _build_crossfreq(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    *_, result = _crossfreq_book(reader, dataset, window, as_of, accept_holes)
    return {
        "ann_sharpe_noc": sharpe(result.governed_net, periods_per_year=PPY_4H),
        "per_period_sharpe_4h": sharpe(result.governed_net),
        "ann_sharpe_ungoverned": sharpe(result.ungoverned_net, periods_per_year=PPY_4H),
        "cap_breach_bars": result.cap_breach_bars,
        "governor_engaged_bars": result.governor_engaged_bars,
        "n_periods": result.n_periods,
    }


def _build_combined(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    _, daily_prices = _capturing_union(reader, dataset, 1440, window, as_of, accept_holes)
    result = build_combined_system(daily_prices, config=_RECORD33_CONFIG)
    return {
        "ann_sharpe_noc": sharpe(result.net_of_cost, periods_per_year=PPY_DAILY),
        "per_period_sharpe": sharpe(result.net_of_cost),
        "bench_ann_sharpe": sharpe(result.benchmark_net_of_cost, periods_per_year=PPY_DAILY),
        "cap_breach_bars": result.cap_breach_bars,
        "n_periods": result.n_periods,
    }


_ASSETS = CrossfreqSystemConfig().assets

# The B2 trial's fixed constants (docs/specs/00128 D4-D6, docs/specs/00129 D5): a change to one is a new trial, never an
# edit here, `_B2_N_TRIALS` aside.
_DECISIVE_START = 1380
_N_RESAMPLES = 2000
_FROM_2021 = datetime(2021, 1, 1, tzinfo=UTC)
_B2_COST_PER_SIDE = 0.006
_B2_N_TRIALS = 1  # docs/specs/00133 D4: raised in place until a record or reading of the subject lands
_B2_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
_B2_LOOKBACK = 180


class _B2Inputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    arm_a: dict[str, list[float]]
    binperp_funding_z30d: dict[str, list[float | None]]
    scales: dict[str, list[float]]


def _b2_inputs(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
    *,
    subject: str,
) -> _B2Inputs:
    """Arm A's positions, the funding feature and the scales, and no return of arm B: the pre-run engagement read runs on
    this half alone (docs/specs/00128 D6). `subject` is the name a refusal of the window gives."""
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    _b2_refuse_window(subject, h4_ts, window)
    config = B2Config()
    feature = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/funding.parquet"
        try:
            # Read whole, never windowed: the z-score warms on the prints before the window opens.
            prints = reader.read_series("derivatives-funding", relpath)
            feature[asset] = funding_grid_feature(
                prints["ts"].to_list(), prints["funding_rate"].to_list(), prints["interval_hours"].to_list(), h4_ts, config=config
            )
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-funding/{relpath}: {exc}") from exc
    fed = _ffill_btc(h4_prices)
    arms = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B2_LOOKBACK,
                basket_lookback=_B2_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
        )["asset_positions"]
        for lookbacks, target_vol in _B2_A2_ARMS
    ]
    arm_a = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(len(h4_ts) - 1)] for a in _ASSETS}
    return _B2Inputs(h4_ts, h4_prices, close_grid(h4_ts), arm_a, feature, derisk_scales(feature, config=config))


def _b2_returns(h4_prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    fed = _ffill_btc(h4_prices)
    return {a: _asset_returns(fed[a]) for a in _ASSETS}


def _b2_slices(series: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
    """`calendar_year_slices` drops 2026 itself; 2020 is the window's other partial year."""
    return {year: s for year, s in calendar_year_slices(series, h4_ts).items() if year != "2020"}


def _b2_over(subject: str, window: tuple[str, str] | None) -> str:
    return f"{subject} over " + ("the full history" if window is None else f"the window {window[0]} .. {window[1]}")


def _b2_refuse_window(subject: str, h4_ts: list[datetime], window: tuple[str, str] | None) -> None:
    """The refusals `a1_kill_bar` and `net_of_cost_verdict` make of a window too short for them or lying in partial years,
    raised before the arms are built, in the window's terms."""
    close = close_grid(h4_ts)
    from_2021 = sum(t >= _FROM_2021 for t in close)
    if len(close) < _DECISIVE_START + 2:
        raise SubjectError(
            f"{_b2_over(subject, window)}: it holds {len(close)} return indices, and the kill bar's decisive window opens at index "
            f"{_DECISIVE_START} and needs 2"
        )
    if from_2021 < 2:
        raise SubjectError(
            f"{_b2_over(subject, window)}: {from_2021} of its return indices close at or after 2021-01-01T00:00Z, and the from-2021 "
            "head-to-head needs 2"
        )
    if not _b2_slices([0.0] * len(close), h4_ts):
        raise SubjectError(
            f"{_b2_over(subject, window)}: none of its return indices closes in a calendar year the worst-slice leg reads, partial "
            "years left out"
        )


def _b2_arm_a_bar(inputs: _B2Inputs, *, n_trials: int) -> dict:
    """Arm A's headline bar, the instrument check of docs/specs/00128 D6."""
    cost = _B2_COST_PER_SIDE
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(inputs.arm_a, returns, cost_per_side=cost)
    net_a_x15 = net_of_cost(inputs.arm_a, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    return a1_kill_bar(
        net_a,
        bench,
        n_trials=n_trials,
        var_trials=0.0,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=_b2_slices(net_a, inputs.h4_ts),
        benchmark_slices=_b2_slices(bench, inputs.h4_ts),
        decisive_start=_DECISIVE_START,
        n_resamples=_N_RESAMPLES,
    )


def _b2_build(
    subject: str,
    compute: Callable[[_B2Inputs], dict],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    """Reads nothing past `_b2_inputs`, whose block the basis test pins as the trial's."""
    try:
        return compute(_b2_inputs(reader, dataset, window, as_of, accept_holes, subject=subject))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        # `_b2_inputs` names a funding file's errors; any other a compute package raises, a bad close included, is named
        # as the window's.
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b2_funding_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_build("b2-funding-derisk", _b2_metrics, reader, dataset, window, as_of, accept_holes)


# docs/specs/00129 D7's keys of arm A's bar.
_B2_ARM_A_BAR_FLAGS = frozenset({"dsr_pass", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes"})
_B2_ARM_A_BAR_KEYS = _B2_ARM_A_BAR_FLAGS | {"dsr", "spa_p_value", "spa_p_value_full", "cost_stress_sharpe", "worst_slice_sharpe"}


def _b2_arm_a_bar_metrics(inputs: _B2Inputs) -> dict:
    # 1, the count reading 1 was kept at: `_B2_N_TRIALS` moving never moves that landed reading's replay.
    bar = _b2_arm_a_bar(inputs, n_trials=1)
    return {key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)}


def _build_b2_arm_a_bar(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_build("b2-arm-a-bar", _b2_arm_a_bar_metrics, reader, dataset, window, as_of, accept_holes)


def _b2_metrics(inputs: _B2Inputs) -> dict:
    arm_a, scales, close = inputs.arm_a, inputs.scales, inputs.close
    arm_b = scale_positions(arm_a, scales)
    cost = _B2_COST_PER_SIDE
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(arm_a, returns, cost_per_side=cost)
    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    slices_b, slices_bench = _b2_slices(net_b, inputs.h4_ts), _b2_slices(bench, inputs.h4_ts)
    k21 = next((k for k, t in enumerate(close) if t >= _FROM_2021), len(close))
    drawdown_b = max_drawdown(net_b[k21:])
    drawdown_a = max_drawdown(net_a[k21:])
    if drawdown_a == 0:
        raise ValidationError("arm A never draws down from 2021-01-01T00:00Z, so max_drawdown_reduction_pct divides by zero")
    grid = {
        (block, seed): a1_kill_bar(
            net_b,
            bench,
            n_trials=_B2_N_TRIALS,
            var_trials=0.0,
            mean_block=block,
            seed=seed,
            cost_stressed_returns=net_b_x15,
            regime_slices=slices_b,
            benchmark_slices=slices_bench,
            decisive_start=_DECISIVE_START,
            n_resamples=_N_RESAMPLES,
        )
        for block in (30, 102)
        for seed in (42, 7, 1234)
    }
    headline = grid[(30, 42)]
    head_to_head = {}
    for label, start in (("full", 0), ("2021", k21)):
        verdict = net_of_cost_verdict(net_b[start:], net_a[start:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        head_to_head[f"head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
    positions_differ = per_year_positions_differ(arm_a, arm_b, close)
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_DECISIVE_START:], periods_per_year=PPY_4H),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": int(headline["dsr_pass"]),
        "spa_pass": int(headline["spa_pass"]),
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": int(headline["cost_stress_pass"]),
        "worst_slice_relative_pass": int(headline["worst_slice_pass"]),
        "passes": int(headline["passes"]),
        "decisive_start": _DECISIVE_START,
        "n_resamples": _N_RESAMPLES,
        "arm_a_passes": int(_b2_arm_a_bar(inputs, n_trials=_B2_N_TRIALS)["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": result["spa_p_value"] for (block, seed), result in grid.items()},
        **head_to_head,
        "max_drawdown": drawdown_b,
        "arm_a_max_drawdown": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        "turnover_a": book_turnover(arm_a),
        "turnover_b": book_turnover(arm_b),
        "stamps_positions_differ": sum(positions_differ.values()),
        "engaged_per_year": per_year_engaged_counts(arm_a, scales, close),
        "positions_differ_per_year": positions_differ,
        "turnover_a_per_year": per_year_turnover(arm_a, close),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "binperp_funding_z30d_coverage": {
            asset: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(close, feature).items()}
            for asset, feature in inputs.binperp_funding_z30d.items()
        },
    }


# docs/specs/00128 D7's metric keys.
_B2_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "per_period_sharpe_4h",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "dsr_corrected",
        "dsr_pass",
        "spa_pass",
        "spa_p_full",
        "cost_stress_pass",
        "worst_slice_relative_pass",
        "passes",
        "decisive_start",
        "n_resamples",
        "arm_a_passes",
        "spa_p_decisive_b30_s42",
        "spa_p_decisive_b30_s7",
        "spa_p_decisive_b30_s1234",
        "spa_p_decisive_b102_s42",
        "spa_p_decisive_b102_s7",
        "spa_p_decisive_b102_s1234",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "head_to_head_mean_outperf_2021",
        "head_to_head_spa_p_2021",
        "max_drawdown",
        "arm_a_max_drawdown",
        "max_drawdown_reduction_pct",
        "turnover_a",
        "turnover_b",
        "stamps_positions_differ",
        "engaged_per_year",
        "positions_differ_per_year",
        "turnover_a_per_year",
        "turnover_b_per_year",
        "max_drawdown_per_year",
        "arm_a_max_drawdown_per_year",
        "binperp_funding_z30d_coverage",
    }
)


# docs/specs/00128 D6's matrix plus the two instrument findings its metrics show (docs/specs/00129 D4): a change to it is a
# new spec and a new trial, never an edit here.
def _b2_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["engaged_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_2021"] > 0 and m["max_drawdown_reduction_pct"] > 1e-6:
        return "adopt" if m["head_to_head_spa_p_2021"] < 0.05 else "park"
    return "reject"


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
    """Read whole, never windowed: the scaler's trailing day reaches back past a window's first boundary; its 180-boundary
    median still warms inside the window."""
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
    # A stamp belongs to the year of its bar's start, ts[k], as the decisions log's [iter-086] fold-assignment entry rules.
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
        reason = str(exc).replace(
            "refresh the substrate before conditioning (F8)",
            "pass a --window that ends by the frozen ohlc-15m set's last bar",
        )
        raise SubjectError(f"{_b2_over(subject, window)}: {reason}") from exc


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


# Records 45 and 46's metric keys (docs/specs/00130 D3).
_B1_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "cost_stress_pass",
        "decisive_start",
        "dsr_corrected",
        "dsr_pass",
        "gated_per_year",
        "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016",
        "head_to_head_spa_p_full",
        "max_drawdown",
        "n_resamples",
        "passes",
        "per_period_sharpe_4h",
        "scaled_per_year",
        "spa_p_decisive_b102",
        "spa_p_decisive_b30",
        "spa_p_full",
        "spa_p_seed1234",
        "spa_p_seed7",
        "spa_pass",
        "spot_drag_pct_yr",
        "stamps_held",
        "stamps_positions_differ",
        "stamps_scaled",
        "turnover_a",
        "turnover_b",
        "turnover_reduction_pct",
        "worst_slice_relative_pass",
    }
)


# B1 trial 3 (docs/specs/00132) reads the B1 literals above as its instrument too.
# Records 45 and 46's registered per_period_sharpe_4h: the dispersion reads the registry's values, never a re-derivation (D6).
_B1_RECORDED_PER_PERIOD_SHARPES = (0.02374, 0.02959)
# The B1 family's trial count at this trial, records 45 and 46 its first two.
_B1_HOURLY_RV_N_TRIALS = 3
# The SPA grid (D7), its headline cell first.
_B1_HOURLY_RV_GRID = ((30, 42), (30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))


class _B1HourlyRVReads(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    hourly: dict[str, tuple[list[datetime], list[float]]]


def _b1_hourly_rv_reads(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
    *,
    subject: str,
) -> _B1HourlyRVReads:
    """The union, the window's refusal and the hourly series, and no compute: the basis test runs this half alone. Both
    grids are read under the same bounds, which keep every hourly bar the weights read (D4)."""
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h and hourly series, never the rolling dataset as of a day: drop --as-of "
            "and pass a frozen --dataset"
        )
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    _b1_refuse_window(subject, h4_ts, window)
    hourly = {}
    for asset in _ASSETS:
        relpath = f"{asset}/EUR/60.parquet"
        try:
            frame = reader.read_series(dataset, relpath, window=window)
            # One frame for both lists: the weights do not refuse stamps and closes of unequal length.
            hourly[asset] = (frame["ts"].to_list(), frame["close"].to_list())
        except pl.exceptions.PolarsError as exc:
            raise SubjectError(f"{dataset}/{relpath}: {exc}") from exc
    return _B1HourlyRVReads(h4_ts, h4_prices, hourly)


class _B1HourlyRVInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    hourly: dict[str, tuple[list[datetime], list[float]]]
    fed: dict[str, list[float | None]]
    returns: dict[str, list[float | None]]
    weights_a: list[dict[str, float]]
    weights_b: list[dict[str, float]]
    arm_a: dict[str, list[float]]


def _b1_hourly_rv_inputs(reads: _B1HourlyRVReads) -> _B1HourlyRVInputs:
    """Both weight paths and arm A's positions, and no position or return of arm B: the pre-flight reads this half alone.
    `weights_b` comes first, so its price validation refuses a bad close before `_asset_returns` divides by it."""
    h4_ts, h4_prices, hourly = reads
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    weights_b = hourly_rv_inverse_vol_weights(fed, h4_ts, hourly, lookback=_B1_LOOKBACK)
    returns = {a: _asset_returns(fed[a]) for a in _ASSETS}
    weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)
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
    return _B1HourlyRVInputs(h4_ts, h4_prices, hourly, fed, returns, weights_a, weights_b, arm_a)


def _b1_hourly_rv_arm_a(inputs: _B1HourlyRVInputs) -> tuple[dict, float, list[float], list[float]]:
    """Arm A's bar at the family's dispersion with arm A standing as its third Sharpe (D6), which the pre-flight reads
    before arm B's Sharpe exists."""
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=_B1_COST_PER_SIDE)
    net_a_x15 = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=1.5 * _B1_COST_PER_SIDE)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=_B1_COST_PER_SIDE)
    arm_a_var_trials = statistics.variance([*_B1_RECORDED_PER_PERIOD_SHARPES, sharpe(net_a)])
    bar = a1_kill_bar(
        net_a,
        bench,
        n_trials=_B1_HOURLY_RV_N_TRIALS,
        var_trials=arm_a_var_trials,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),
        benchmark_slices=calendar_year_slices(bench, inputs.h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    return bar, arm_a_var_trials, net_a, bench


def _b1_hourly_rv_metrics(inputs: _B1HourlyRVInputs) -> dict:
    h4_ts, fed, returns, arm_a = inputs.h4_ts, inputs.fed, inputs.returns, inputs.arm_a
    weights_a, weights_b = inputs.weights_a, inputs.weights_b
    n = len(h4_ts) - 1
    # Before the bars: on a book that never trades, `sharpe(net_a)` would refuse first and this refusal would never fire.
    turnover_a, weight_tv_a = book_turnover(arm_a), weight_total_variation(weights_a)
    if turnover_a == 0 or weight_tv_a == 0:
        raise ValidationError(
            f"turnover_a is {turnover_a} and weight_tv_a is {weight_tv_a}, and turnover_reduction_pct and weight_tv_ratio "
            "divide by them"
        )
    arm_a_bar, arm_a_var_trials, net_a, bench = _b1_hourly_rv_arm_a(inputs)
    arms = []
    for lookbacks, target_vol in _B1_A2_ARMS:
        config = A2Config(
            lookbacks=lookbacks,
            short="off",
            target_vol=target_vol,
            vol_lookback=_B1_LOOKBACK,
            basket_lookback=_B1_LOOKBACK,
            periods_per_year=PPY_4H,
        )
        arms.append(a2_positions_with_weights(fed, weights_b, config=config))
    arm_b = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in _ASSETS}
    net_b = net_of_cost(arm_b, returns, cost_per_side=_B1_COST_PER_SIDE)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * _B1_COST_PER_SIDE)
    per_period_sharpe_4h = sharpe(net_b)
    var_trials = statistics.variance([*_B1_RECORDED_PER_PERIOD_SHARPES, per_period_sharpe_4h])
    bar = a1_kill_bar(
        net_b,
        bench,
        n_trials=_B1_HOURLY_RV_N_TRIALS,
        var_trials=var_trials,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_b_x15,
        regime_slices=calendar_year_slices(net_b, h4_ts),
        benchmark_slices=calendar_year_slices(bench, h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    decisive = [[net_b[k] - bench[k]] for k in range(_B1_DECISIVE_START, n)]
    grid = {_B1_HOURLY_RV_GRID[0]: bar["spa_p_value"]} | {
        (block, seed): reality_check_pvalue(decisive, mean_block=block, n_resamples=_B1_N_RESAMPLES, seed=seed)["p_value"]
        for block, seed in _B1_HOURLY_RV_GRID[1:]
    }
    # The bar-start year, as `_b1_metrics` cuts it.
    k16 = next(k for k in range(n) if h4_ts[k] >= _B1_FROM_2016)
    full = net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    from_2016 = net_of_cost_verdict(net_b[k16:], net_a[k16:], mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    turnover_b, weight_tv_b = book_turnover(arm_b), weight_total_variation(weights_b)
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": per_period_sharpe_4h,
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "var_trials": var_trials,
        "dsr_corrected": bar["dsr"],
        "dsr_pass": int(bar["dsr_pass"]),
        "spa_pass": int(bar["spa_pass"]),
        "spa_p_full": bar["spa_p_value_full"],
        "cost_stress_pass": int(bar["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bar["worst_slice_pass"]),
        "passes": int(bar["passes"]),
        "decisive_start": _B1_DECISIVE_START,
        "n_resamples": _B1_N_RESAMPLES,
        "arm_a_var_trials": arm_a_var_trials,
        "arm_a_passes": int(arm_a_bar["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_GRID},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * _B1_COST_PER_SIDE * PPY_4H,
        "arm_a_spot_drag_pct_yr": turnover_a / n * _B1_COST_PER_SIDE * PPY_4H,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_weights_differ": weights_differ_count(weights_a, weights_b),
        "stamps_positions_differ": sum(any(arm_b[a][k] != arm_a[a][k] for a in _ASSETS) for k in range(n)),
        "weight_tv_a": weight_tv_a,
        "weight_tv_b": weight_tv_b,
        "weight_tv_ratio": weight_tv_b / weight_tv_a,
        "mean_weight_per_year": per_year_mean_weights(weights_a, weights_b, h4_ts, list(_ASSETS)),
    }


def _b1_hourly_rv_preflight_metrics(inputs: _B1HourlyRVInputs) -> dict:
    """Arm A's anchors and bar and the stamps whose weights differ (D7's two pre-flights): no position or return of arm B."""
    weights_a, weights_b = inputs.weights_a, inputs.weights_b
    n = len(inputs.h4_ts) - 1
    bar, arm_a_var_trials, net_a, bench = _b1_hourly_rv_arm_a(inputs)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * _B1_COST_PER_SIDE * PPY_4H,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_var_trials": arm_a_var_trials,
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        "stamps_weights_differ": weights_differ_count(weights_a, weights_b),
    }


def _b1_hourly_rv_build(
    subject: str,
    compute: Callable[[_B1HourlyRVInputs], dict],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    reads = _b1_hourly_rv_reads(reader, dataset, window, as_of, accept_holes, subject=subject)
    try:
        return compute(_b1_hourly_rv_inputs(reads))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        # A bad close, an hourly series the weights refuse and a book that never trades among them, named as the window's.
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b1_hourly_rv(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_hourly_rv_build("b1-hourly-rv", _b1_hourly_rv_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b1_hourly_rv_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_hourly_rv_build(
        "b1-hourly-rv-preflight", _b1_hourly_rv_preflight_metrics, reader, dataset, window, as_of, accept_holes
    )


# docs/specs/00132 D7's matrix plus the two instrument findings its metrics show (docs/specs/00129 D4), verbatim: a change to
# it is a new spec and a new trial, never an edit here.
def _b1_hourly_rv_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or m["stamps_weights_differ"] == 0:
        return None  # instrument finding: no verdict, the trial unspent
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_full"] > 0 and m["turnover_b"] < m["turnover_a"]:
        if m["head_to_head_spa_p_full"] < 0.05 and m["spa_p_decisive_b102_s42"] < 0.05:
            return "adopt"
        return "park"
    return "reject"


# docs/specs/00132 D8's keys of the trial and of its pre-flight.
_B1_HOURLY_RV_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "per_period_sharpe_4h",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "var_trials",
        "dsr_corrected",
        "dsr_pass",
        "spa_pass",
        "spa_p_full",
        "cost_stress_pass",
        "worst_slice_relative_pass",
        "passes",
        "decisive_start",
        "n_resamples",
        "arm_a_var_trials",
        "arm_a_passes",
        "spa_p_decisive_b30_s42",
        "spa_p_decisive_b30_s7",
        "spa_p_decisive_b30_s1234",
        "spa_p_decisive_b102_s42",
        "spa_p_decisive_b102_s7",
        "spa_p_decisive_b102_s1234",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016",
        "max_drawdown",
        "arm_a_max_drawdown",
        "spot_drag_pct_yr",
        "arm_a_spot_drag_pct_yr",
        "turnover_a",
        "turnover_b",
        "turnover_reduction_pct",
        "stamps_weights_differ",
        "stamps_positions_differ",
        "weight_tv_a",
        "weight_tv_b",
        "weight_tv_ratio",
        "mean_weight_per_year",
    }
)
_B1_HOURLY_RV_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "arm_a_max_drawdown",
    "turnover_a",
    "arm_a_spot_drag_pct_yr",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "arm_a_var_trials",
    "stamps_weights_differ",
}


# B1 trial 4 (docs/specs/00134) reads the B1 literals above as its instrument too, and trial 3's SPA grid (D10).
# Records 45, 46 and 48's registered per_period_sharpe_4h, record 48's every digit its writer stored: the dispersion reads the
# registry's values, never a re-derivation (D7).
_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES = (*_B1_RECORDED_PER_PERIOD_SHARPES, 0.030191886721210086)
# The B1 family's trial count at this trial: records 45, 46 and 48, and itself (D11).
_B1_VOLUME_N_TRIALS = 4
# The thin-cell rule: a cell's hour-of-week shape is 1 until it holds 100 earlier observations (D3).
_B1_VOLUME_MIN_CELL_OBS = 100


class _B1VolumeReads(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    volumes: dict[str, list[float | None]]


def _b1_volume_reads(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
    *,
    subject: str,
) -> _B1VolumeReads:
    """The union, the window's refusal and the volumes on the union's stamps, and no compute: the basis test runs this half
    alone. The volumes are read under the union's bounds, so a windowed norm warms up from the window's first bar (D4)."""
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series and their volumes, never the rolling dataset as of a day: drop "
            "--as-of and pass a frozen --dataset"
        )
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    _b1_refuse_window(subject, h4_ts, window)
    volumes = {}
    for asset in _ASSETS:
        relpath = f"{asset}/EUR/240.parquet"
        try:
            frame = reader.read_series(dataset, relpath, window=window)
            by_ts = dict(zip(frame["ts"].to_list(), frame["volume"].to_list(), strict=True))
        except pl.exceptions.PolarsError as exc:
            raise SubjectError(f"{dataset}/{relpath}: {exc}") from exc
        volumes[asset] = [by_ts.get(t) for t in h4_ts]
    return _B1VolumeReads(h4_ts, h4_prices, volumes)


class _B1VolumeInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    volumes: dict[str, list[float | None]]
    fed: dict[str, list[float | None]]
    returns: dict[str, list[float | None]]
    weights_a: list[dict[str, float]]
    vt_a: list[list[float]]
    directions_a: list[dict[str, list[float | None]]]
    confirm: dict[str, list[bool]]
    directions_b: list[dict[str, list[float | None]]]
    events: list[dict[str, dict[int, list[tuple[int, bool]]]]]
    own_stamps: dict[str, list[datetime]]
    arm_a: dict[str, list[float]]


def _b1_volume_inputs(reads: _B1VolumeReads) -> _B1VolumeInputs:
    """Arm A's positions, vol scalars and directions, the confirmations and each arm's confirmed directions and entry events,
    one entry per arm of `_B1_A2_ARMS` in its order, and no position or return of arm B: the pre-flight reads this half
    alone. The confirmations come first, so their price validation refuses a bad close before `_asset_returns` divides by it."""
    h4_ts, h4_prices, volumes = reads
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    confirm = confirmations_by_asset(fed, h4_prices, h4_ts, volumes, lookback=_B1_LOOKBACK, min_cell_obs=_B1_VOLUME_MIN_CELL_OBS)
    returns = {a: _asset_returns(fed[a]) for a in _ASSETS}
    # One path for the three arms, each arm's basket_lookback being _B1_LOOKBACK (D1).
    weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)
    # Each asset's own bars as `a2_book_returns` indexes them; the events' bars index `own_stamps`.
    union_idx = list(range(len(h4_ts)))
    asset_ts = {a: [k for k, p in enumerate(fed[a]) if p is not None] for a in _ASSETS}
    own_stamps = {a: [h4_ts[k] for k in asset_ts[a]] for a in _ASSETS}
    positions_a, vt_a, directions_a, directions_b, events = [], [], [], [], []
    for lookbacks, target_vol in _B1_A2_ARMS:
        config = A2Config(
            lookbacks=lookbacks,
            short="off",
            target_vol=target_vol,
            vol_lookback=_B1_LOOKBACK,
            basket_lookback=_B1_LOOKBACK,
            periods_per_year=PPY_4H,
        )
        book = a2_book_returns(fed, config=config)
        positions_a.append(book["asset_positions"])
        vt_a.append(book["vol_target_positions"])
        directions_a.append(_asset_directions_a2(fed, union_idx, asset_ts, config=config))
        confirmed, arm_events = asset_directions_confirmed(fed, union_idx, asset_ts, confirm, config=config)
        directions_b.append(confirmed)
        events.append(arm_events)
    arm_a = {a: [statistics.mean(arm[a][k] for arm in positions_a) for k in range(n)] for a in _ASSETS}
    return _B1VolumeInputs(
        h4_ts, h4_prices, volumes, fed, returns, weights_a, vt_a, directions_a, confirm, directions_b, events, own_stamps, arm_a
    )


def _b1_volume_arm_a(inputs: _B1VolumeInputs) -> tuple[dict, float, list[float], list[float]]:
    """Arm A's bar at the family's dispersion with arm A standing as its fourth Sharpe (D7), which the pre-flight reads
    before arm B's Sharpe exists."""
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=_B1_COST_PER_SIDE)
    net_a_x15 = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=1.5 * _B1_COST_PER_SIDE)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=_B1_COST_PER_SIDE)
    arm_a_var_trials = statistics.variance([*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, sharpe(net_a)])
    bar = a1_kill_bar(
        net_a,
        bench,
        n_trials=_B1_VOLUME_N_TRIALS,
        var_trials=arm_a_var_trials,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),
        benchmark_slices=calendar_year_slices(bench, inputs.h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    return bar, arm_a_var_trials, net_a, bench


def _b1_volume_engagement(inputs: _B1VolumeInputs) -> dict:
    """D8's six keys, read from prices and volumes alone: no position or return of arm B."""
    per_year = {str(i + 1): entry_events_per_year(events, inputs.own_stamps) for i, events in enumerate(inputs.events)}
    counts = [
        count
        for by_asset in per_year.values()
        for by_lookback in by_asset.values()
        for by_year in by_lookback.values()
        for count in by_year.values()
    ]
    events, rejected = sum(count[0] for count in counts), sum(count[1] for count in counts)
    if events == 0:
        raise ValidationError("entry_events is 0, and share_rejected divides by it")
    differ = directions_differ_per_year(inputs.directions_a, inputs.directions_b, inputs.h4_ts)
    return {
        "entry_events_per_year": per_year,
        "entry_events": events,
        "entry_events_rejected": rejected,
        "share_rejected": rejected / events,
        "stamps_directions_differ": sum(differ.values()),
        "stamps_directions_differ_per_year": differ,
    }


def _b1_volume_metrics(inputs: _B1VolumeInputs) -> dict:
    h4_ts, returns, arm_a = inputs.h4_ts, inputs.returns, inputs.arm_a
    weights_a, vt_a, directions_b = inputs.weights_a, inputs.vt_a, inputs.directions_b
    n = len(h4_ts) - 1
    # Before the bars: on a book that never trades, `sharpe(net_a)` would refuse first and this refusal would never fire.
    turnover_a = book_turnover(arm_a)
    if turnover_a == 0:
        raise ValidationError(f"turnover_a is {turnover_a}, and turnover_reduction_pct divides by it")
    engagement = _b1_volume_engagement(inputs)
    arm_a_bar, arm_a_var_trials, net_a, bench = _b1_volume_arm_a(inputs)
    # Arm A's weights and each arm's own vol scalar on arm B's confirmed directions (D1).
    arms = [a2_positions_on_directions(weights_a, directions_b[i], vt_a[i]) for i in range(len(_B1_A2_ARMS))]
    arm_b = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(n)] for a in _ASSETS}
    net_b = net_of_cost(arm_b, returns, cost_per_side=_B1_COST_PER_SIDE)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * _B1_COST_PER_SIDE)
    per_period_sharpe_4h = sharpe(net_b)
    var_trials = statistics.variance([*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, per_period_sharpe_4h])
    bar = a1_kill_bar(
        net_b,
        bench,
        n_trials=_B1_VOLUME_N_TRIALS,
        var_trials=var_trials,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_b_x15,
        regime_slices=calendar_year_slices(net_b, h4_ts),
        benchmark_slices=calendar_year_slices(bench, h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    decisive = [[net_b[k] - bench[k]] for k in range(_B1_DECISIVE_START, n)]
    grid = {_B1_HOURLY_RV_GRID[0]: bar["spa_p_value"]} | {
        (block, seed): reality_check_pvalue(decisive, mean_block=block, n_resamples=_B1_N_RESAMPLES, seed=seed)["p_value"]
        for block, seed in _B1_HOURLY_RV_GRID[1:]
    }
    # The bar-start year, as `_b1_metrics` cuts it.
    k16 = next(k for k in range(n) if h4_ts[k] >= _B1_FROM_2016)
    full = net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    from_2016 = net_of_cost_verdict(net_b[k16:], net_a[k16:], mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    turnover_b = book_turnover(arm_b)
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": per_period_sharpe_4h,
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "var_trials": var_trials,
        "dsr_corrected": bar["dsr"],
        "dsr_pass": int(bar["dsr_pass"]),
        "spa_pass": int(bar["spa_pass"]),
        "spa_p_full": bar["spa_p_value_full"],
        "cost_stress_pass": int(bar["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bar["worst_slice_pass"]),
        "passes": int(bar["passes"]),
        "decisive_start": _B1_DECISIVE_START,
        "n_resamples": _B1_N_RESAMPLES,
        "arm_a_var_trials": arm_a_var_trials,
        "arm_a_passes": int(arm_a_bar["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_GRID},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "spot_drag_pct_yr": turnover_b / n * _B1_COST_PER_SIDE * PPY_4H,
        "arm_a_spot_drag_pct_yr": turnover_a / n * _B1_COST_PER_SIDE * PPY_4H,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_positions_differ": sum(any(arm_b[a][k] != arm_a[a][k] for a in _ASSETS) for k in range(n)),
        **engagement,
    }


def _b1_volume_preflight_metrics(inputs: _B1VolumeInputs) -> dict:
    """The entry events and stamps whose directions differ, and arm A's anchors and bar (D8, D9): no position or return of
    arm B."""
    engagement = _b1_volume_engagement(inputs)
    n = len(inputs.h4_ts) - 1
    bar, arm_a_var_trials, net_a, bench = _b1_volume_arm_a(inputs)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * _B1_COST_PER_SIDE * PPY_4H,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_var_trials": arm_a_var_trials,
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        **engagement,
    }


def _b1_volume_build(
    subject: str,
    compute: Callable[[_B1VolumeInputs], dict],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    reads = _b1_volume_reads(reader, dataset, window, as_of, accept_holes, subject=subject)
    try:
        return compute(_b1_volume_inputs(reads))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        # A bad close or volume, a book that never trades and a build with no entry event among them, named as the window's.
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b1_volume_confirmation(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_volume_build("b1-volume-confirmation", _b1_volume_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b1_volume_confirmation_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_volume_build(
        "b1-volume-confirmation-preflight", _b1_volume_preflight_metrics, reader, dataset, window, as_of, accept_holes
    )


# docs/specs/00134 D10's matrix plus the two instrument findings its metrics show (docs/specs/00129 D4), verbatim: a change to
# it is a new spec and a new trial, never an edit here.
def _b1_volume_confirmation_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or m["stamps_directions_differ"] == 0:
        return None  # instrument finding: no verdict, the trial unspent
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_full"] > 0 and m["turnover_b"] < m["turnover_a"]:
        if m["head_to_head_spa_p_full"] < 0.05 and m["spa_p_decisive_b102_s42"] < 0.05:
            return "adopt"
        return "park"
    return "reject"


# docs/specs/00134 D11's keys of the trial and of its pre-flight.
_B1_VOLUME_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "per_period_sharpe_4h",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "var_trials",
        "dsr_corrected",
        "dsr_pass",
        "spa_pass",
        "spa_p_full",
        "cost_stress_pass",
        "worst_slice_relative_pass",
        "passes",
        "decisive_start",
        "n_resamples",
        "arm_a_var_trials",
        "arm_a_passes",
        "spa_p_decisive_b30_s42",
        "spa_p_decisive_b30_s7",
        "spa_p_decisive_b30_s1234",
        "spa_p_decisive_b102_s42",
        "spa_p_decisive_b102_s7",
        "spa_p_decisive_b102_s1234",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016",
        "max_drawdown",
        "arm_a_max_drawdown",
        "spot_drag_pct_yr",
        "arm_a_spot_drag_pct_yr",
        "turnover_a",
        "turnover_b",
        "turnover_reduction_pct",
        "entry_events",
        "entry_events_rejected",
        "share_rejected",
        "entry_events_per_year",
        "stamps_directions_differ",
        "stamps_directions_differ_per_year",
        "stamps_positions_differ",
    }
)
_B1_VOLUME_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "arm_a_max_drawdown",
    "turnover_a",
    "arm_a_spot_drag_pct_yr",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "arm_a_var_trials",
    "entry_events",
    "entry_events_rejected",
    "share_rejected",
    "entry_events_per_year",
    "stamps_directions_differ",
    "stamps_directions_differ_per_year",
}


# B1 trial 5 (docs/specs/00135) reads the B1 literals above as its instrument too, and trial 3's reads half and SPA grid (D1,
# D5).
# Records 45, 46, 48 and 49's registered per_period_sharpe_4h, record 49's every digit its writer stored: the dispersion reads
# the registry's values, never a re-derivation (D7).
_B1_EXIT_RECORDED_PER_PERIOD_SHARPES = (*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, 0.03028127927651177)
# The B1 family's trial count at this trial: records 45, 46, 48 and 49, and itself (D11).
_B1_EXIT_N_TRIALS = 5


class _B1HourlyExitInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    fed: dict[str, list[float | None]]
    returns: dict[str, list[float | None]]
    weights_a: list[dict[str, float]]
    vt_a: list[list[float]]
    directions_a: list[dict[str, list[float | None]]]
    interior: dict[str, list[tuple[float | None, float | None, float | None]]]
    directions_b: list[dict[str, list[tuple[float, float, float, float] | None]]]
    events: list[dict[str, dict[int, list[tuple[int, int, bool]]]]]
    own_stamps: dict[str, list[datetime]]
    paths: dict[str, list[tuple[float, float, float, float, float] | None]]
    arm_a: dict[str, list[float]]


def _b1_hourly_exit_inputs(reads: _B1HourlyRVReads) -> _B1HourlyExitInputs:
    """Arm A's positions, vol scalars and directions, the interior closes, each arm's slot directions and exit events, one
    entry per arm of `_B1_A2_ARMS` in its order, and the price paths, and no position or return of arm B: the pre-flight
    reads this half alone. The interior closes come first, so their price validation and the hourly refusals (D4) refuse a
    bad close before `_asset_returns` divides by it."""
    h4_ts, h4_prices, hourly = reads
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    interior = interior_closes_by_asset(fed, h4_prices, h4_ts, hourly)
    returns = {a: _asset_returns(fed[a]) for a in _ASSETS}
    # One path for the three arms, each arm's basket_lookback being _B1_LOOKBACK (D1).
    weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)
    # Each asset's own bars as `a2_book_returns` indexes them; the events' bars index `own_stamps`.
    union_idx = list(range(len(h4_ts)))
    asset_ts = {a: [k for k, p in enumerate(fed[a]) if p is not None] for a in _ASSETS}
    own_stamps = {a: [h4_ts[k] for k in asset_ts[a]] for a in _ASSETS}
    positions_a, vt_a, directions_a, directions_b, events = [], [], [], [], []
    for lookbacks, target_vol in _B1_A2_ARMS:
        config = A2Config(
            lookbacks=lookbacks,
            short="off",
            target_vol=target_vol,
            vol_lookback=_B1_LOOKBACK,
            basket_lookback=_B1_LOOKBACK,
            periods_per_year=PPY_4H,
        )
        book = a2_book_returns(fed, config=config)
        positions_a.append(book["asset_positions"])
        vt_a.append(book["vol_target_positions"])
        directions_a.append(_asset_directions_a2(fed, union_idx, asset_ts, config=config))
        slot_directions, arm_events = asset_directions_hourly_exit(fed, union_idx, asset_ts, interior, config=config)
        directions_b.append(slot_directions)
        events.append(arm_events)
    # After the slot directions, which refuse an interior list whose length is not the price series': `price_paths` reads
    # the same lists unchecked.
    paths = price_paths(fed, interior)
    arm_a = {a: [statistics.mean(arm[a][k] for arm in positions_a) for k in range(n)] for a in _ASSETS}
    return _B1HourlyExitInputs(
        h4_ts, h4_prices, fed, returns, weights_a, vt_a, directions_a, interior, directions_b, events, own_stamps, paths, arm_a
    )


def _b1_hourly_exit_arm_a(inputs: _B1HourlyExitInputs) -> tuple[dict, float, list[float], list[float]]:
    """Arm A's bar at the family's dispersion with arm A standing as its fifth Sharpe (D7), which the pre-flight reads
    before arm B's Sharpe exists."""
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=_B1_COST_PER_SIDE)
    net_a_x15 = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=1.5 * _B1_COST_PER_SIDE)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=_B1_COST_PER_SIDE)
    arm_a_var_trials = statistics.variance([*_B1_EXIT_RECORDED_PER_PERIOD_SHARPES, sharpe(net_a)])
    bar = a1_kill_bar(
        net_a,
        bench,
        n_trials=_B1_EXIT_N_TRIALS,
        var_trials=arm_a_var_trials,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),
        benchmark_slices=calendar_year_slices(bench, inputs.h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    return bar, arm_a_var_trials, net_a, bench


def _b1_hourly_exit_engagement(inputs: _B1HourlyExitInputs) -> dict:
    """D8's seven keys, read from closes alone: no position or return of arm B."""
    per_year = {str(i + 1): exit_events_per_year(events, inputs.own_stamps) for i, events in enumerate(inputs.events)}
    counts = [
        count
        for by_asset in per_year.values()
        for by_lookback in by_asset.values()
        for by_year in by_lookback.values()
        for count in by_year.values()
    ]
    events, early, false = (sum(count[i] for count in counts) for i in range(3))
    if events == 0:
        raise ValidationError("exit_events is 0, and share_false divides by it")
    differ = hourly_closes_differ_per_year(inputs.directions_a, inputs.directions_b, inputs.h4_ts)
    return {
        "exit_events_per_year": per_year,
        "exit_events": events,
        "exit_events_early": early,
        "exit_events_false": false,
        "share_false": false / events,
        "hourly_closes_directions_differ": sum(differ.values()),
        "hourly_closes_directions_differ_per_year": differ,
    }


def _b1_hourly_exit_metrics(inputs: _B1HourlyExitInputs) -> dict:
    h4_ts, arm_a = inputs.h4_ts, inputs.arm_a
    n = len(h4_ts) - 1
    # Before the bars: on a book that never trades, `sharpe(net_a)` would refuse first and this refusal would never fire;
    # the drawdown is read off its own `net_of_cost`, so neither refusal waits on a kill bar.
    turnover_a = book_turnover(arm_a)
    drawdown_a = max_drawdown(net_of_cost(arm_a, inputs.returns, cost_per_side=_B1_COST_PER_SIDE))
    if turnover_a == 0 or drawdown_a == 0:
        raise ValidationError(
            f"turnover_a is {turnover_a} and arm_a_max_drawdown is {drawdown_a}, and turnover_reduction_pct and "
            "max_drawdown_reduction_pct divide by them"
        )
    engagement = _b1_hourly_exit_engagement(inputs)
    arm_a_bar, arm_a_var_trials, net_a, bench = _b1_hourly_exit_arm_a(inputs)
    # Arm A's weights and each arm's own vol scalar on arm B's slot directions (D1).
    arms = [a2_slot_positions(inputs.weights_a, inputs.directions_b[i], inputs.vt_a[i]) for i in range(len(_B1_A2_ARMS))]
    arm_b = {a: [tuple(statistics.mean(arm[a][k][i] for arm in arms) for i in range(4)) for k in range(n)] for a in _ASSETS}
    net_b = net_of_cost_hourly(arm_b, inputs.paths, cost_per_side=_B1_COST_PER_SIDE)
    net_b_x15 = net_of_cost_hourly(arm_b, inputs.paths, cost_per_side=1.5 * _B1_COST_PER_SIDE)
    per_period_sharpe_4h = sharpe(net_b)
    var_trials = statistics.variance([*_B1_EXIT_RECORDED_PER_PERIOD_SHARPES, per_period_sharpe_4h])
    bar = a1_kill_bar(
        net_b,
        bench,
        n_trials=_B1_EXIT_N_TRIALS,
        var_trials=var_trials,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_b_x15,
        regime_slices=calendar_year_slices(net_b, h4_ts),
        benchmark_slices=calendar_year_slices(bench, h4_ts),
        decisive_start=_B1_DECISIVE_START,
        n_resamples=_B1_N_RESAMPLES,
    )
    decisive = [[net_b[k] - bench[k]] for k in range(_B1_DECISIVE_START, n)]
    grid = {_B1_HOURLY_RV_GRID[0]: bar["spa_p_value"]} | {
        (block, seed): reality_check_pvalue(decisive, mean_block=block, n_resamples=_B1_N_RESAMPLES, seed=seed)["p_value"]
        for block, seed in _B1_HOURLY_RV_GRID[1:]
    }
    # The bar-start year, as `_b1_metrics` cuts it.
    k16 = next(k for k in range(n) if h4_ts[k] >= _B1_FROM_2016)
    full = net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    from_2016 = net_of_cost_verdict(net_b[k16:], net_a[k16:], mean_block=30, seed=42, n_resamples=_B1_N_RESAMPLES)
    # Each asset's slot positions flattened in time order, so the intra-interval trades count (D3).
    turnover_b = book_turnover({a: [p for slots in arm_b[a] for p in slots] for a in _ASSETS})
    drawdown_b = max_drawdown(net_b)
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": per_period_sharpe_4h,
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "var_trials": var_trials,
        "dsr_corrected": bar["dsr"],
        "dsr_pass": int(bar["dsr_pass"]),
        "spa_pass": int(bar["spa_pass"]),
        "spa_p_full": bar["spa_p_value_full"],
        "cost_stress_pass": int(bar["cost_stress_pass"]),
        "worst_slice_relative_pass": int(bar["worst_slice_pass"]),
        "passes": int(bar["passes"]),
        "decisive_start": _B1_DECISIVE_START,
        "n_resamples": _B1_N_RESAMPLES,
        "arm_a_var_trials": arm_a_var_trials,
        "arm_a_passes": int(arm_a_bar["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": grid[(block, seed)] for block, seed in _B1_HOURLY_RV_GRID},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_2016": from_2016["mean_outperformance"],
        "head_to_head_spa_p_2016": from_2016["spa_p_value"],
        "max_drawdown": drawdown_b,
        "arm_a_max_drawdown": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        "spot_drag_pct_yr": turnover_b / n * _B1_COST_PER_SIDE * PPY_4H,
        "arm_a_spot_drag_pct_yr": turnover_a / n * _B1_COST_PER_SIDE * PPY_4H,
        "turnover_a": turnover_a,
        "turnover_b": turnover_b,
        "turnover_b_intra": intra_turnover(arm_b),
        "turnover_reduction_pct": 100 * (turnover_a - turnover_b) / turnover_a,
        "stamps_positions_differ": sum(any(p != arm_a[a][k] for a in _ASSETS for p in arm_b[a][k]) for k in range(n)),
        **engagement,
    }


def _b1_hourly_exit_preflight_metrics(inputs: _B1HourlyExitInputs) -> dict:
    """The exit events and hourly closes whose directions differ, and arm A's anchors and bar (D8, D9): no position or return
    of arm B."""
    engagement = _b1_hourly_exit_engagement(inputs)
    n = len(inputs.h4_ts) - 1
    bar, arm_a_var_trials, net_a, bench = _b1_hourly_exit_arm_a(inputs)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * _B1_COST_PER_SIDE * PPY_4H,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_B1_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_var_trials": arm_a_var_trials,
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        **engagement,
    }


def _b1_hourly_exit_build(
    subject: str,
    compute: Callable[[_B1HourlyExitInputs], dict],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    reads = _b1_hourly_rv_reads(reader, dataset, window, as_of, accept_holes, subject=subject)
    try:
        return compute(_b1_hourly_exit_inputs(reads))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        # A bad hourly close or bar, a book that never trades or never draws down and a build with no exit event among
        # them, named as the window's.
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b1_hourly_exit(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_hourly_exit_build("b1-hourly-channel-exits", _b1_hourly_exit_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b1_hourly_exit_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b1_hourly_exit_build(
        "b1-hourly-channel-exits-preflight", _b1_hourly_exit_preflight_metrics, reader, dataset, window, as_of, accept_holes
    )


# docs/specs/00135 D10's matrix plus the two instrument findings its metrics show (docs/specs/00129 D4), verbatim: a change to
# it is a new spec and a new trial, never an edit here.
def _b1_hourly_exit_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or m["hourly_closes_directions_differ"] == 0:
        return None  # instrument finding: no verdict, the trial unspent
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_full"] > 0 and m["max_drawdown_reduction_pct"] > 1e-6:
        if m["head_to_head_spa_p_full"] < 0.05 and m["spa_p_decisive_b102_s42"] < 0.05:
            return "adopt"
        return "park"
    return "reject"


# docs/specs/00135 D11's keys of the trial and of its pre-flight.
_B1_EXIT_METRIC_KEYS = frozenset(
    {
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "per_period_sharpe_4h",
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
        "var_trials",
        "dsr_corrected",
        "dsr_pass",
        "spa_pass",
        "spa_p_full",
        "cost_stress_pass",
        "worst_slice_relative_pass",
        "passes",
        "decisive_start",
        "n_resamples",
        "arm_a_var_trials",
        "arm_a_passes",
        "spa_p_decisive_b30_s42",
        "spa_p_decisive_b30_s7",
        "spa_p_decisive_b30_s1234",
        "spa_p_decisive_b102_s42",
        "spa_p_decisive_b102_s7",
        "spa_p_decisive_b102_s1234",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "head_to_head_mean_outperf_2016",
        "head_to_head_spa_p_2016",
        "max_drawdown",
        "arm_a_max_drawdown",
        "max_drawdown_reduction_pct",
        "spot_drag_pct_yr",
        "arm_a_spot_drag_pct_yr",
        "turnover_a",
        "turnover_b",
        "turnover_b_intra",
        "turnover_reduction_pct",
        "exit_events",
        "exit_events_early",
        "exit_events_false",
        "share_false",
        "exit_events_per_year",
        "hourly_closes_directions_differ",
        "hourly_closes_directions_differ_per_year",
        "stamps_positions_differ",
    }
)
_B1_EXIT_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "arm_a_max_drawdown",
    "turnover_a",
    "arm_a_spot_drag_pct_yr",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "arm_a_var_trials",
    "exit_events",
    "exit_events_early",
    "exit_events_false",
    "share_false",
    "exit_events_per_year",
    "hourly_closes_directions_differ",
    "hourly_closes_directions_differ_per_year",
}


SUBJECTS: dict[str, Subject] = {
    "record44-crossfreq": Subject(
        "record44-crossfreq",
        (1440, 240),
        _ASSETS,
        _build_crossfreq,
        spec="docs/specs/00038-cross-frequency-combination-design.md",
        metric_keys=frozenset(
            {
                "ann_sharpe_noc",
                "per_period_sharpe_4h",
                "ann_sharpe_ungoverned",
                "cap_breach_bars",
                "governor_engaged_bars",
                "n_periods",
            }
        ),
    ),
    "record33-combined": Subject(
        "record33-combined",
        (1440,),
        _ASSETS,
        _build_combined,
        spec="docs/specs/00035-combination-trial-design.md",
        metric_keys=frozenset({"ann_sharpe_noc", "per_period_sharpe", "bench_ann_sharpe", "cap_breach_bars", "n_periods"}),
    ),
    "b2-funding-derisk": Subject(
        "b2-funding-derisk",
        (240,),
        _ASSETS,
        _build_b2_funding_derisk,
        spec="docs/specs/00128-b2-family-opening-design.md",
        metric_keys=_B2_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b2_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_N_TRIALS,
    ),
    "b2-arm-a-bar": Subject(
        "b2-arm-a-bar",
        (240,),
        _ASSETS,
        _build_b2_arm_a_bar,
        spec="docs/specs/00128-b2-family-opening-design.md",
        metric_keys=_B2_ARM_A_BAR_KEYS,
        seeds=(42,),
    ),
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
    "b1-hourly-rv": Subject(
        "b1-hourly-rv",
        (240, 60),
        _ASSETS,
        _build_b1_hourly_rv,
        spec="docs/specs/00132-b1-hourly-rv-weights-design.md",
        metric_keys=_B1_HOURLY_RV_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b1_hourly_rv_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar, or arm B's weights equal arm A's at every stamp; no verdict, the trial "
            "unspent"
        ),
        family="B1",
        n_trials=_B1_HOURLY_RV_N_TRIALS,
    ),
    "b1-hourly-rv-preflight": Subject(
        "b1-hourly-rv-preflight",
        (240, 60),
        _ASSETS,
        _build_b1_hourly_rv_preflight,
        spec="docs/specs/00132-b1-hourly-rv-weights-design.md",
        metric_keys=_B1_HOURLY_RV_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
    "b1-volume-confirmation": Subject(
        "b1-volume-confirmation",
        (240,),
        _ASSETS,
        _build_b1_volume_confirmation,
        spec="docs/specs/00134-b1-volume-confirmation-design.md",
        metric_keys=_B1_VOLUME_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b1_volume_confirmation_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every stamp; no verdict, the "
            "trial unspent"
        ),
        family="B1",
        n_trials=_B1_VOLUME_N_TRIALS,
    ),
    "b1-volume-confirmation-preflight": Subject(
        "b1-volume-confirmation-preflight",
        (240,),
        _ASSETS,
        _build_b1_volume_confirmation_preflight,
        spec="docs/specs/00134-b1-volume-confirmation-design.md",
        metric_keys=_B1_VOLUME_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
    "b1-hourly-channel-exits": Subject(
        "b1-hourly-channel-exits",
        (240, 60),
        _ASSETS,
        _build_b1_hourly_exit,
        spec="docs/specs/00135-b1-hourly-channel-exits-design.md",
        metric_keys=_B1_EXIT_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b1_hourly_exit_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every hourly close; no verdict, "
            "the trial unspent"
        ),
        family="B1",
        n_trials=_B1_EXIT_N_TRIALS,
    ),
    "b1-hourly-channel-exits-preflight": Subject(
        "b1-hourly-channel-exits-preflight",
        (240, 60),
        _ASSETS,
        _build_b1_hourly_exit_preflight,
        spec="docs/specs/00135-b1-hourly-channel-exits-design.md",
        metric_keys=_B1_EXIT_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
}

# docs/specs/00129 D3: the records at or below 47 a --comparator-trial may name, each mapped to the subject that reproduces
# its book.
LEGACY_INCUMBENTS: dict[int, str] = {
    33: "record33-combined",
    44: "record44-crossfreq",
    45: "b1-conditioning",
    46: "b1-window-only",
    47: "record44-crossfreq",
}
