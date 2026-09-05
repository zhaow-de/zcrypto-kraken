"""Combined-system builder — the adopted P1 system (registry record 33) as one composed pipeline.

Governed cost is pre-governor cost times the multiplier — an approximation (docs/research/13.phase5-decisions.md, iter-058).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Deliberate cross-package import of a1's private helpers: the builder must run the SAME code path
# the QA-gated drivers and registry record 33 ran — a reimplementation could silently diverge.
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.portfolio.errors import PortfolioError
from cli.risk import GovernorConfig, GovernorResult, apply_position_caps, drawdown_governor


@dataclass(frozen=True)
class CombinedSystemConfig:
    """Record 33's frozen parameters as defaults; see docs/specs/00036-combined-system-builder-design.md."""

    basket_lookback: int = 30
    gate_window: int = 200
    target_vol_annual: float = 0.10
    vol_lookback: int = 30
    max_leverage: float = 1.0
    periods_per_year: int = 365
    spot_fee_per_side: float = 0.006
    long_cap: float = 0.20
    short_cap: float = 0.10
    governor: GovernorConfig = GovernorConfig()


@dataclass(frozen=True)
class CombinedSystemResult:
    net_of_cost: list[float]
    benchmark_net_of_cost: list[float]
    capped_net_of_cost: list[float]
    positions: dict[str, list[float]]
    multipliers: list[float]
    governor: GovernorResult
    cap_breach_bars: int
    n_periods: int


def _net_of_cost(positions: dict[str, list[float]], gross: list[float], fee: float) -> list[float]:
    out: list[float] = []
    prev = dict.fromkeys(positions, 0.0)
    for k in range(len(gross)):
        turnover = 0.0
        for asset, series in positions.items():
            p = series[k]
            turnover += abs(p - prev[asset])
            prev[asset] = p
        out.append(gross[k] - turnover * fee)
    return out


def build_combined_system(
    prices_by_asset: dict[str, list[float | None]], *, config: CombinedSystemConfig = CombinedSystemConfig()
) -> CombinedSystemResult:
    """Build the adopted combined system and its frozen benchmark from union-calendar prices.

    The benchmark is master-plan §9's frozen construction, uncapped and ungoverned, for head-to-heads.
    """
    if not isinstance(prices_by_asset, dict) or not prices_by_asset:
        raise PortfolioError(f"prices_by_asset must be a non-empty dict, got {prices_by_asset!r}")
    c = config
    for name, value in (
        ("target_vol_annual", c.target_vol_annual),
        ("max_leverage", c.max_leverage),
        ("spot_fee_per_side", c.spot_fee_per_side),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise PortfolioError(f"{name} must be a finite number > 0, got {value!r}")
    if not isinstance(c.periods_per_year, int) or c.periods_per_year < 1:
        raise PortfolioError(f"periods_per_year must be an int >= 1, got {c.periods_per_year!r}")

    basket = dynamic_inverse_vol_basket(prices_by_asset, lookback=c.basket_lookback)
    equity = [1.0]
    for r in basket:
        equity.append(equity[-1] * (1 + r))
    gate = sma_gate(equity, window=c.gate_window)
    vt = vol_target(
        basket,
        target_vol=c.target_vol_annual / math.sqrt(c.periods_per_year),
        lookback=c.vol_lookback,
        max_leverage=c.max_leverage,
    )
    l3 = [gate[k] * vt[k] for k in range(len(gate))]

    weights = _inverse_vol_weights(prices_by_asset, lookback=c.basket_lookback)
    returns_by_asset = {a: _asset_returns(prices_by_asset[a]) for a in prices_by_asset}
    n = len(basket)

    bench_positions = {a: [weights[k].get(a, 0.0) * l3[k] for k in range(n)] for a in prices_by_asset}
    bench_gross = [l3[k] * basket[k] for k in range(n)]
    benchmark_net_of_cost = _net_of_cost(bench_positions, bench_gross, c.spot_fee_per_side)

    capped = apply_position_caps(bench_positions, long_cap=c.long_cap, short_cap=c.short_cap)
    capped_gross: list[float] = []
    for k in range(n):
        g = 0.0
        for a, series in capped.items():
            p = series[k]
            if p != 0.0:
                r = returns_by_asset[a][k]
                g += p * (r if r is not None else 0.0)
        capped_gross.append(g)
    capped_net_of_cost = _net_of_cost(capped, capped_gross, c.spot_fee_per_side)

    gov = drawdown_governor(capped_net_of_cost, config=c.governor)
    positions = {a: [gov.multipliers[k] * series[k] for k in range(n)] for a, series in capped.items()}
    cap_breach_bars = sum(
        1
        for k in range(n)
        if any(bench_positions[a][k] > c.long_cap or bench_positions[a][k] < -c.short_cap for a in bench_positions)
    )
    return CombinedSystemResult(
        net_of_cost=gov.governed_returns,
        benchmark_net_of_cost=benchmark_net_of_cost,
        capped_net_of_cost=capped_net_of_cost,
        positions=positions,
        multipliers=gov.multipliers,
        governor=gov,
        cap_breach_bars=cap_breach_bars,
        n_periods=n,
    )
