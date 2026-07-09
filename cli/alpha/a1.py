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
