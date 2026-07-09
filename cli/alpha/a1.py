from __future__ import annotations

import math
from dataclasses import dataclass

from cli.alpha.errors import AlphaError

_BASES = frozenset({"btc_only", "equal_risk_basket"})
_REGIMES = frozenset({"single_gate", "ensemble"})
_SHORTS = frozenset({"off", "confirmed_bear"})


def _check_enum(name: str, value: str, allowed: frozenset[str]) -> None:
    if value not in allowed:
        raise AlphaError(f"{name} must be one of {sorted(allowed)}, got {value!r}")


def _check_positive_number(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise AlphaError(f"{name} must be a finite number > 0, got {value!r}")


def _check_window(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 2:
        raise AlphaError(f"{name} must be an int >= 2, got {value!r}")


@dataclass(frozen=True, kw_only=True)
class A1Config:
    """A1 book configuration (docs/specs/00031): the four toggles (base, regime, short, target_vol)
    plus the fixed knobs shared by every trial. Validated at construction; every field is immutable
    thereafter."""

    base: str
    regime: str
    short: str
    target_vol: float
    gate_window: int = 200
    vol_lookback: int = 30
    basket_lookback: int = 30
    trend_lookbacks: tuple[int, ...] = (20, 60, 120)
    short_exposure: float = 0.5
    max_leverage: float = 1.0
    periods_per_year: int = 365

    def __post_init__(self) -> None:
        _check_enum("base", self.base, _BASES)
        _check_enum("regime", self.regime, _REGIMES)
        _check_enum("short", self.short, _SHORTS)
        _check_positive_number("target_vol", self.target_vol)
        _check_window("gate_window", self.gate_window)
        _check_window("vol_lookback", self.vol_lookback)
        _check_window("basket_lookback", self.basket_lookback)
        if not isinstance(self.trend_lookbacks, tuple) or not self.trend_lookbacks:
            raise AlphaError(f"trend_lookbacks must be a non-empty tuple of ints, got {self.trend_lookbacks!r}")
        for lb in self.trend_lookbacks:
            _check_window("trend_lookbacks element", lb)
        if (
            not isinstance(self.short_exposure, (int, float))
            or isinstance(self.short_exposure, bool)
            or not math.isfinite(self.short_exposure)
            or not (0 < self.short_exposure <= 1)
        ):
            raise AlphaError(f"short_exposure must be a finite number in (0, 1], got {self.short_exposure!r}")
        _check_positive_number("max_leverage", self.max_leverage)
        if not isinstance(self.periods_per_year, int) or isinstance(self.periods_per_year, bool) or self.periods_per_year < 1:
            raise AlphaError(f"periods_per_year must be an int >= 1, got {self.periods_per_year!r}")


from cli.benchmark.strategies import sma_gate
from cli.features import trend_agreement


def _map_to_union_index(own_ts: list, own_values: list[float], union_ts: list) -> list[float | None]:
    """Map a feature/gate computed on an asset's own CONTIGUOUS (gap-compressed) calendar (`own_ts`,
    length N; `own_values[j]` = the causal value for the move own_ts[j] -> own_ts[j+1], length N-1)
    onto the union return index (`union_ts`, length M; union period k = the move union_ts[k] ->
    union_ts[k+1]). Union period k gets own_values[own_pos[union_ts[k]]] iff BOTH union_ts[k] and
    union_ts[k+1] are present in own_ts AND are adjacent there (own_pos[union_ts[k+1]] ==
    own_pos[union_ts[k]] + 1) -- the asset was present for both endpoints of that exact move with
    nothing dropped in between; else None. Introduces no look-ahead: own_values[j] itself only used
    data at <= own_ts[j] (inherited from the source feature/gate); this only remaps by timestamp.
    """
    own_pos = {ts: j for j, ts in enumerate(own_ts)}
    mapped: list[float | None] = []
    for k in range(len(union_ts) - 1):
        j0 = own_pos.get(union_ts[k])
        j1 = own_pos.get(union_ts[k + 1])
        if j0 is not None and j1 is not None and j1 == j0 + 1:
            mapped.append(own_values[j0])
        else:
            mapped.append(None)
    return mapped


def _asset_directions(
    prices_by_asset: dict[str, list[float | None]],
    btc_prices: list[float],
    union_ts: list,
    asset_ts: dict[str, list],
    *,
    config: A1Config,
) -> dict[str, list[float | None]]:
    """Per-asset direction d_i[k] on the union return index (docs/specs/00031). Every value uses only
    prices/features at <= union index k -> no look-ahead. None where the asset itself has no valid
    return that period (either endpoint's price is None). Assumes btc_prices/asset_ts["BTC"] have
    full coverage of union_ts (no internal gaps) -- true for the real BTC series; a1_book_returns
    (Task 4) enforces this at its validation boundary."""
    g_btc_own = sma_gate(btc_prices, window=config.gate_window)
    g_btc = _map_to_union_index(asset_ts["BTC"], g_btc_own, union_ts)

    directions: dict[str, list[float | None]] = {}
    for asset, prices in prices_by_asset.items():
        own_prices = [p for p in prices if p is not None]
        ta_own = trend_agreement(own_prices, lookbacks=list(config.trend_lookbacks))
        ta = _map_to_union_index(asset_ts[asset], ta_own, union_ts)

        d: list[float | None] = []
        for k in range(len(union_ts) - 1):
            if prices[k] is None or prices[k + 1] is None:
                d.append(None)
                continue
            gate = g_btc[k] if g_btc[k] is not None else 0.0
            # ta[k] is guaranteed non-None here: prices[k] and prices[k+1] both present means
            # union_ts[k]/union_ts[k+1] are adjacent in this asset's own compressed calendar too.
            ta_k = ta[k]
            if config.regime == "single_gate":
                long_ok = gate == 1.0
            else:
                long_ok = gate == 1.0 and ta_k > 0
            if long_ok:
                d.append(1.0)
            elif config.short == "confirmed_bear" and gate == 0.0 and ta_k < 0:
                d.append(-config.short_exposure)
            else:
                d.append(0.0)
        directions[asset] = d
    return directions
