"""The evaluable subjects: committed systems, each reproducing a registry record or registering a trial.

A subject declares its `--dataset` series, so the command can refuse an incomplete dataset before any read; a second
dataset its `build` reads goes undeclared, and a file of it that is absent fails the run at that read, inside the build.
Every byte a `build` reads goes through `ObservedReader`."""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _asset_returns
from cli.alpha.b1 import book_turnover
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
from cli.alpha.killbar import a1_kill_bar, net_of_cost_verdict
from cli.derivatives.funding import PERP_SYMBOLS
from cli.features.derivatives import coverage_by_year
from cli.portfolio.builder import build_combined_system
from cli.portfolio.crossfreq_system import (
    _A2_LOOKBACK,
    _PPY_4H,
    CrossfreqSystemConfig,
    _ffill_btc,
    build_crossfreq_system_fast,
)
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices, load_union
from cli.registry.observed import ObservedReader
from cli.validation import max_drawdown, sharpe

PPY_DAILY = 365
PPY_4H = 2190


@dataclass(frozen=True)
class Subject:
    name: str
    intervals: tuple[int, ...]
    assets: tuple[str, ...]
    build: Callable[[ObservedReader, str, tuple | None, str | None, bool], dict]


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
    if as_of is None:
        return load_union(interval, root=Path(), read=lambda path: reader.read_series(dataset, path.as_posix(), window=window))
    return load_union(
        interval,
        root=Path(),
        read=lambda path: reader.read_rolling(
            dataset, "/".join(path.parts[:2]), int(path.stem), as_of, window=window, accept_holes=accept_holes
        ),
    )


def _build_crossfreq(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    config = CrossfreqSystemConfig()
    daily_ts, daily_prices = _capturing_union(reader, dataset, 1440, window, as_of, accept_holes)
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
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
    result = build_combined_system(daily_prices)
    return {
        "ann_sharpe_noc": sharpe(result.net_of_cost, periods_per_year=PPY_DAILY),
        "per_period_sharpe": sharpe(result.net_of_cost),
        "bench_ann_sharpe": sharpe(result.benchmark_net_of_cost, periods_per_year=PPY_DAILY),
        "cap_breach_bars": result.cap_breach_bars,
        "n_periods": result.n_periods,
    }


_ASSETS = CrossfreqSystemConfig().assets

# The B2 trial's fixed constants (docs/specs/00128 D4, D6): a change to one is a new trial, never an edit here.
_DECISIVE_START = 1380
_N_RESAMPLES = 2000
_FROM_2021 = datetime(2021, 1, 1, tzinfo=UTC)


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
) -> _B2Inputs:
    """Arm A's positions, the funding feature and the scales, and no return of arm B: the pre-run engagement read runs on
    this half alone (docs/specs/00128 D6)."""
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, as_of, accept_holes)
    config = B2Config()
    feature = {}
    for asset in _ASSETS:
        # Read whole, never windowed: the z-score warms on the prints before the window opens.
        prints = reader.read_series("derivatives-funding", f"{PERP_SYMBOLS[asset]}/funding.parquet")
        feature[asset] = funding_grid_feature(
            prints["ts"].to_list(), prints["funding_rate"].to_list(), prints["interval_hours"].to_list(), h4_ts, config=config
        )
    fed = _ffill_btc(h4_prices)
    arms = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_A2_LOOKBACK,
                basket_lookback=_A2_LOOKBACK,
                periods_per_year=_PPY_4H,
            ),
        )["asset_positions"]
        for lookbacks, target_vol in CrossfreqSystemConfig().a2_arms
    ]
    arm_a = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(len(h4_ts) - 1)] for a in _ASSETS}
    return _B2Inputs(h4_ts, h4_prices, close_grid(h4_ts), arm_a, feature, derisk_scales(feature, config=config))


def _b2_returns(h4_prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    fed = _ffill_btc(h4_prices)
    return {a: _asset_returns(fed[a]) for a in _ASSETS}


def _b2_slices(series: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
    """`calendar_year_slices` drops 2026 itself; 2020 is the window's other partial year."""
    return {year: s for year, s in calendar_year_slices(series, h4_ts).items() if year != "2020"}


def _b2_arm_a_bar(inputs: _B2Inputs) -> dict:
    """Arm A's headline bar, an instrument check run only after the spec's sha256 is taken (docs/specs/00128 D6)."""
    cost = CrossfreqSystemConfig().cost_per_side
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(inputs.arm_a, returns, cost_per_side=cost)
    net_a_x15 = net_of_cost(inputs.arm_a, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    return a1_kill_bar(
        net_a,
        bench,
        n_trials=1,
        var_trials=0.0,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=_b2_slices(net_a, inputs.h4_ts),
        benchmark_slices=_b2_slices(bench, inputs.h4_ts),
        decisive_start=_DECISIVE_START,
        n_resamples=_N_RESAMPLES,
    )


def _build_b2_funding_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    """Reads nothing past `_b2_inputs`, whose block the basis test pins as the trial's."""
    inputs = _b2_inputs(reader, dataset, window, as_of, accept_holes)
    arm_a, scales, close = inputs.arm_a, inputs.scales, inputs.close
    arm_b = scale_positions(arm_a, scales)
    cost = CrossfreqSystemConfig().cost_per_side
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(arm_a, returns, cost_per_side=cost)
    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    slices_b, slices_bench = _b2_slices(net_b, inputs.h4_ts), _b2_slices(bench, inputs.h4_ts)
    grid = {
        (block, seed): a1_kill_bar(
            net_b,
            bench,
            n_trials=1,
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
    k21 = next((k for k, t in enumerate(close) if t >= _FROM_2021), len(close))
    head_to_head = {}
    for label, start in (("full", 0), ("2021", k21)):
        verdict = net_of_cost_verdict(net_b[start:], net_a[start:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        head_to_head[f"head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
    drawdown_b = max_drawdown(net_b[k21:])
    drawdown_a = max_drawdown(net_a[k21:])
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
        "arm_a_passes": int(_b2_arm_a_bar(inputs)["passes"]),
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


SUBJECTS: dict[str, Subject] = {
    "record44-crossfreq": Subject("record44-crossfreq", (1440, 240), _ASSETS, _build_crossfreq),
    "record33-combined": Subject("record33-combined", (1440,), _ASSETS, _build_combined),
    "b2-funding-derisk": Subject("b2-funding-derisk", (240,), _ASSETS, _build_b2_funding_derisk),
}
