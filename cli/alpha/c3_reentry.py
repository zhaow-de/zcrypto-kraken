"""C3 trial 1's compute (docs/specs/00165-c3-trial-1-asopr-reentry-design.md D3, D7): the cell's events and the size a
re-entry takes.

A position is a fraction of NAV held over return index k, from close k to close k + 1."""

from __future__ import annotations

import math
import statistics

from cli.alpha.a1 import A1Config, _inverse_vol_weights
from cli.alpha.c3 import flags
from cli.benchmark.strategies import dynamic_inverse_vol_basket, vol_target
from cli.portfolio.crossfreq_system import _A1_CADENCE, CrossfreqSystemConfig, _block_start, _dummy_close, _ffill_btc

# Records 44's and 47's A1 sleeve.
SLEEVE = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)


def reentry_fires(band: list[str | None], states: dict[str, list[str | None]]) -> dict[str, list[bool]]:
    """Per asset and row, the cell's event: the asset flat with a close while the band is low."""
    return {asset: [flag is True for flag in flags(band, held, tail="low", in_state="flat")] for asset, held in states.items()}


def full_long_positions(daily_prices: dict[str, list[float | None]]) -> dict[str, list[float]]:
    """Per asset and row, the position the sleeve's constants give a book long in every weighted asset: its inverse-vol
    weight times the vol target of the equal-risk basket itself, through the sleeve's weekly 7-offset mean. One row per
    close, the last the forming one."""
    order = CrossfreqSystemConfig().assets
    if tuple(daily_prices) != order:
        raise ValueError(f"daily_prices must be in the order {order}, got {tuple(daily_prices)}")
    d_pf = _ffill_btc({a: list(closes) + [_dummy_close(closes)] for a, closes in daily_prices.items()})
    rows = len(d_pf["BTC"]) - 1
    weights = _inverse_vol_weights(d_pf, lookback=SLEEVE.basket_lookback)
    scale = vol_target(
        dynamic_inverse_vol_basket(d_pf, lookback=SLEEVE.basket_lookback),
        target_vol=SLEEVE.target_vol / math.sqrt(SLEEVE.periods_per_year),
        lookback=SLEEVE.vol_lookback,
        max_leverage=SLEEVE.max_leverage,
    )
    daily = {a: [weights[k].get(a, 0.0) * scale[k] for k in range(rows)] for a in d_pf}
    return {a: [statistics.mean(daily[a][_block_start(k, o)] for o in range(_A1_CADENCE)) for k in range(rows)] for a in d_pf}
