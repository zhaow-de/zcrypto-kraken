"""Record 47's book re-priced at a picked cost basis (spec 00154 D2–D6): every registered figure over the picked basis's
build, the instrument check over the registered basis's, read against the benchmark-relative bar it passed. Return `k`
runs from bar `k`'s close to bar `k + 1`'s; a result's sleeve positions and multipliers carry `n_periods + 1` rows, the
last the forming one."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from cli.alpha.killbar import DSR_PASS_THRESHOLD, benchmark_relative_worst_slice
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, CrossfreqSystemResult, build_crossfreq_system_fast
from cli.portfolio.record44_legs import (
    DECISIVE_START,
    N_RESAMPLES,
    SPA_GRID,
    SPA_HEADLINE_BLOCK,
    SPA_HEADLINE_SEED,
    benchmark_4h_net_of_cost,
    calendar_year_slices,
)
from cli.portfolio.revalidation import (
    P1_VAR_TRIALS,
    PPY_4H,
    RECORD_47_RETURNS,
    RECORD_47_SHARPE,
    REFERENCE_LAST_BAR,
    SHARPE_TOLERANCE,
)
from cli.validation import deflated_sharpe_ratio, max_drawdown, reality_check_pvalue, sharpe

LAST_DAILY_BAR = datetime(2026, 3, 31, tzinfo=UTC)
STRESS_MULTIPLIERS = (1.5, 2.0)
SPA_PASS_BELOW = 0.05

METRIC_KEYS: frozenset[str] = frozenset(
    {
        "fee_per_side",
        "spread_per_side",
        "cost_per_side",
        "registered_basis_returns",
        "registered_basis_sharpe",
        "ann_sharpe_noc",
        "ann_sharpe_noc_decisive",
        "per_period_sharpe_4h",
        "bench4h_sharpe_full",
        "bench4h_sharpe_decisive",
        "cap_breach_bars",
        "governor_engaged_bars",
        "maxdd",
        "maxdd_pre_governor",
        "cost_stress_1_5x_sharpe_ann",
        "cost_stress_2x_sharpe_ann",
        "var_trials_4h",
        "dsr",
        "spa_p_full",
        "spa_p_decisive",
        "spa_grid_b30_s7",
        "spa_grid_b30_s1234",
        "spa_grid_b102_s42",
        "spa_grid_b102_s7",
        "spa_grid_b102_s1234",
        "dsr_pass",
        "spa_pass",
        "cost_stress_pass",
        "worst_slice_relative_pass",
        "passes",
        "worst_book_sharpe",
        "worst_benchmark_sharpe",
        "conditional_live_sharpe",
        "conditional_live_bars",
        "multipliers_moved",
    }
)


class RepricingError(Exception):
    pass


def refuse_past_in_sample(daily_ts: list[datetime], h4_ts: list[datetime]) -> None:
    if h4_ts[-1] > REFERENCE_LAST_BAR:
        raise RepricingError(f"its last 4h bar, {h4_ts[-1]}, lies past {REFERENCE_LAST_BAR}, the in-sample end")
    if daily_ts[-1] > LAST_DAILY_BAR:
        raise RepricingError(f"its last daily bar, {daily_ts[-1]}, lies past {LAST_DAILY_BAR}, the in-sample end")


def stressed_config(config: CrossfreqSystemConfig, multiplier: float) -> CrossfreqSystemConfig:
    return replace(
        config,
        fee_per_side=config.fee_per_side * multiplier,
        spread_per_side=config.spread_per_side * multiplier,
    )


def live_state_returns(result: CrossfreqSystemResult) -> list[int]:
    sleeves = result.sleeve_positions
    flat, live = (sleeves["B"], sleeves["A1"]), sleeves["A2"]
    return [
        k for k in range(result.n_periods) if all(p[a][k] == 0.0 for p in flat for a in p) and any(live[a][k] != 0.0 for a in live)
    ]


def conditional_live(governed: list[float], live: list[int]) -> float:
    returns = [governed[k] for k in live]
    # sharpe refuses fewer than two returns and a zero variance; the read is 0.0 there (spec D6).
    if len(returns) < 2 or min(returns) == max(returns):
        return 0.0
    return float(sharpe(returns, periods_per_year=PPY_4H))


def multipliers_moved(registered: CrossfreqSystemResult, basis: CrossfreqSystemResult) -> int:
    return sum(1 for k in range(basis.n_periods) if basis.multipliers[k] != registered.multipliers[k])


def spa_cells(book: list[float], bench: list[float]) -> dict[str, float]:
    outperformance = [[b - m] for b, m in zip(book, bench, strict=True)]
    decisive = outperformance[DECISIVE_START:]

    def p_value(matrix: list[list[float]], block: int, seed: int) -> float:
        return float(reality_check_pvalue(matrix, mean_block=block, n_resamples=N_RESAMPLES, seed=seed)["p_value"])

    cells = {
        "spa_p_full": p_value(outperformance, SPA_HEADLINE_BLOCK, SPA_HEADLINE_SEED),
        "spa_p_decisive": p_value(decisive, SPA_HEADLINE_BLOCK, SPA_HEADLINE_SEED),
    }
    for block, seed in SPA_GRID:
        cells[f"spa_grid_b{block}_s{seed}"] = p_value(decisive, block, seed)
    return cells


def bar_flags(*, dsr: float, spa: dict[str, float], stress_15: float, beats_worst: bool) -> dict[str, int]:
    legs = {
        "dsr_pass": int(dsr > DSR_PASS_THRESHOLD),
        "spa_pass": int(max(v for k, v in spa.items() if k != "spa_p_full") < SPA_PASS_BELOW),
        "cost_stress_pass": int(stress_15 > 0),
        "worst_slice_relative_pass": int(beats_worst),
    }
    return {**legs, "passes": int(all(legs.values()))}


def repricing_metrics(
    daily_ts: list[datetime],
    daily_prices: dict[str, list[float | None]],
    h4_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
    *,
    registered: CrossfreqSystemConfig,
    basis: CrossfreqSystemConfig,
    n_trials: int,
) -> dict:
    refuse_past_in_sample(daily_ts, h4_ts)

    def build(config: CrossfreqSystemConfig) -> CrossfreqSystemResult:
        return build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)

    reg, bas = build(registered), build(basis)
    stress_15, stress_2 = (
        float(sharpe(build(stressed_config(basis, m)).governed_net, periods_per_year=PPY_4H)) for m in STRESS_MULTIPLIERS
    )
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=basis.cost_per_side)
    g = bas.governed_net
    per_period = float(sharpe(g))
    dsr = float(deflated_sharpe_ratio(per_period, len(g), n_trials=n_trials, var_trials=P1_VAR_TRIALS))
    spa = spa_cells(g, bench)
    relative = benchmark_relative_worst_slice(calendar_year_slices(g, h4_ts), calendar_year_slices(bench, h4_ts))
    flags = bar_flags(dsr=dsr, spa=spa, stress_15=stress_15, beats_worst=relative["beats_benchmark_worst"])
    live = live_state_returns(bas)
    return {
        "fee_per_side": float(basis.fee_per_side),
        "spread_per_side": float(basis.spread_per_side),
        "cost_per_side": float(basis.cost_per_side),
        "registered_basis_returns": int(reg.n_periods),
        "registered_basis_sharpe": float(sharpe(reg.governed_net, periods_per_year=PPY_4H)),
        "ann_sharpe_noc": float(sharpe(g, periods_per_year=PPY_4H)),
        "ann_sharpe_noc_decisive": float(sharpe(g[DECISIVE_START:], periods_per_year=PPY_4H)),
        "per_period_sharpe_4h": per_period,
        "bench4h_sharpe_full": float(sharpe(bench, periods_per_year=PPY_4H)),
        "bench4h_sharpe_decisive": float(sharpe(bench[DECISIVE_START:], periods_per_year=PPY_4H)),
        "cap_breach_bars": int(bas.cap_breach_bars),
        "governor_engaged_bars": int(bas.governor_engaged_bars),
        "maxdd": float(max_drawdown(g)),
        "maxdd_pre_governor": float(max_drawdown(bas.ungoverned_net)),
        "cost_stress_1_5x_sharpe_ann": stress_15,
        "cost_stress_2x_sharpe_ann": stress_2,
        "var_trials_4h": float(P1_VAR_TRIALS),
        "dsr": dsr,
        **spa,
        "dsr_pass": int(flags["dsr_pass"]),
        "spa_pass": int(flags["spa_pass"]),
        "cost_stress_pass": int(flags["cost_stress_pass"]),
        "worst_slice_relative_pass": int(flags["worst_slice_relative_pass"]),
        "passes": int(flags["passes"]),
        "worst_book_sharpe": float(relative["worst_book_sharpe"]),
        "worst_benchmark_sharpe": float(relative["worst_benchmark_sharpe"]),
        "conditional_live_sharpe": conditional_live(g, live),
        "conditional_live_bars": int(len(live)),
        "multipliers_moved": int(multipliers_moved(reg, bas)),
    }


def repricing_verdict(metrics: dict) -> str | None:
    if (
        metrics["registered_basis_returns"] == RECORD_47_RETURNS
        and abs(metrics["registered_basis_sharpe"] - RECORD_47_SHARPE) < SHARPE_TOLERANCE
    ):
        return "adopt" if metrics["passes"] else "park"
    return None
