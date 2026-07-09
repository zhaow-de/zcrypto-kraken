from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from cli.alpha.a1 import _map_to_union_index
from cli.alpha.errors import AlphaError
from cli.features import channel_position

_SHORTS = frozenset({"off", "on"})


@dataclass(frozen=True, kw_only=True)
class A2Config:
    """A2 book configuration (docs/specs/00033): the per-asset Donchian breakout ensemble's toggles
    (lookbacks, short, target_vol) plus the fixed knobs shared by every trial. Validated at
    construction; every field is immutable thereafter."""

    lookbacks: tuple[int, ...]
    short: str
    target_vol: float
    band: float = 1.0
    short_exposure: float = 0.5
    vol_lookback: int = 30
    basket_lookback: int = 30
    max_leverage: float = 1.0
    periods_per_year: int = 365

    def __post_init__(self) -> None:
        if not isinstance(self.lookbacks, tuple) or not self.lookbacks:
            raise AlphaError(f"lookbacks must be a non-empty tuple of ints, got {self.lookbacks!r}")
        for lb in self.lookbacks:
            if not isinstance(lb, int) or isinstance(lb, bool) or lb < 2:
                raise AlphaError(f"lookbacks element must be an int >= 2, got {lb!r}")
        if self.short not in _SHORTS:
            raise AlphaError(f"short must be one of {sorted(_SHORTS)}, got {self.short!r}")
        if (
            not isinstance(self.target_vol, (int, float))
            or isinstance(self.target_vol, bool)
            or not math.isfinite(self.target_vol)
            or self.target_vol <= 0
        ):
            raise AlphaError(f"target_vol must be a finite number > 0, got {self.target_vol!r}")
        if (
            not isinstance(self.band, (int, float))
            or isinstance(self.band, bool)
            or not math.isfinite(self.band)
            or not (0 < self.band <= 1)
        ):
            raise AlphaError(f"band must be a finite number in (0, 1], got {self.band!r}")


def _donchian_signal(prices: list[float], *, window: int, band: float) -> list[float]:
    """Per-lookback Donchian breakout state machine (docs/specs/00033): +1 when the Donchian channel
    position hits a new window-high (channel_position >= band), -1 on a new window-low
    (channel_position <= -band), else HOLDS the prior signal (0.0 before the first break). Strictly
    causal: channel_position itself only reads prices[<= k]; this only carries state forward.
    Length len(prices)-1."""
    cp = channel_position(prices, window=window)
    out: list[float] = []
    held = 0.0
    for k in range(len(cp)):
        if cp[k] >= band:
            held = 1.0
        elif cp[k] <= -band:
            held = -1.0
        out.append(held)
    return out


def _asset_directions_a2(
    prices_by_asset: dict[str, list[float | None]],
    union_ts: list,
    asset_ts: dict[str, list],
    *,
    config: A2Config,
) -> dict[str, list[float | None]]:
    """Per-asset direction d_i[k] on the union return index (docs/specs/00033): for each asset, run
    _donchian_signal on its own CONTIGUOUS (None-filtered) price series at every lookback in
    config.lookbacks, map each to the union calendar (_map_to_union_index), and ensemble by mean.
    None where any lookback's mapping is None at k (the asset's return isn't valid there). Short
    toggle: short="off" clips the ensemble to [0, inf); short="on" scales only the negative part by
    short_exposure (never a naked full short)."""
    directions: dict[str, list[float | None]] = {}
    for asset, prices in prices_by_asset.items():
        own_prices = [p for p in prices if p is not None]
        mapped = [
            _map_to_union_index(asset_ts[asset], _donchian_signal(own_prices, window=w, band=config.band), union_ts)
            for w in config.lookbacks
        ]
        d: list[float | None] = []
        for k in range(len(union_ts) - 1):
            values = [m[k] for m in mapped]
            if any(v is None for v in values):
                d.append(None)
                continue
            ensemble = statistics.mean(values)
            if config.short == "off":
                d.append(max(ensemble, 0.0))
            else:
                d.append(ensemble if ensemble >= 0 else ensemble * config.short_exposure)
        directions[asset] = d
    return directions
