"""§10 portfolio limits — pure pre-trade transforms: per-asset caps, gross-leverage cap, net-exposure band, margin floor.
A governor, not an optimizer: the excess sits in cash; at or inside a limit nothing scales, and an untouched value is bit-identical.
One limit may re-tighten another's input, so the consumer sets the order — recommended: caps → gross → net → margin floor.
Each limit is idempotent in the model but only float-approximately, so any fixed-point loop must not key on bitwise equality."""

from __future__ import annotations

import math

from cli.risk.errors import RiskError


def apply_position_caps(
    positions: dict[str, list[float]], *, long_cap: float = 0.20, short_cap: float = 0.10
) -> dict[str, list[float]]:
    """Clip each asset's per-bar position to [-short_cap, +long_cap]; the defaults are §10's per-asset NAV caps."""
    if not isinstance(positions, dict) or not positions:
        raise RiskError(f"positions must be a non-empty dict, got {positions!r}")
    for cap_name, cap in (("long_cap", long_cap), ("short_cap", short_cap)):
        if not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0:
            raise RiskError(f"{cap_name} must be a finite number > 0, got {cap!r}")
    lengths = set()
    for asset, series in positions.items():
        if not isinstance(series, list) or not series:
            raise RiskError(f"positions[{asset!r}] must be a non-empty list, got {series!r}")
        for p in series:
            if not isinstance(p, (int, float)) or not math.isfinite(p):
                raise RiskError(f"positions[{asset!r}] must contain finite numbers, got {p!r}")
        lengths.add(len(series))
    if len(lengths) != 1:
        raise RiskError(f"all assets must have equal-length series, got lengths {sorted(lengths)}")
    return {asset: [min(p, long_cap) if p >= 0 else max(p, -short_cap) for p in series] for asset, series in positions.items()}


def _validate_positions(positions: dict[str, list[float]]) -> None:
    """Guard shared by the whole-book limits: a non-empty dict of non-empty, equal-length lists of finite numbers."""
    if not isinstance(positions, dict) or not positions:
        raise RiskError(f"positions must be a non-empty dict, got {positions!r}")
    lengths = set()
    for asset, series in positions.items():
        if not isinstance(series, list) or not series:
            raise RiskError(f"positions[{asset!r}] must be a non-empty list, got {series!r}")
        for p in series:
            if not isinstance(p, (int, float)) or not math.isfinite(p):
                raise RiskError(f"positions[{asset!r}] must contain finite numbers, got {p!r}")
        lengths.add(len(series))
    if len(lengths) != 1:
        raise RiskError(f"all assets must have equal-length series, got lengths {sorted(lengths)}")


def apply_gross_leverage_cap(
    positions: dict[str, list[float]], *, soft_cap: float = 1.5, hard_cap: float = 2.0
) -> dict[str, list[float]]:
    """Scale each bar with gross leverage above soft_cap proportionally down to it; the defaults are §10's soft and hard caps.

    hard_cap is §10's alerting constant, validated (soft_cap <= hard_cap) but otherwise unused: a transform that scales
    to soft_cap can never emit gross above it, so hard needs no second code path."""
    _validate_positions(positions)
    for cap_name, cap in (("soft_cap", soft_cap), ("hard_cap", hard_cap)):
        if not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0:
            raise RiskError(f"{cap_name} must be a finite number > 0, got {cap!r}")
    if soft_cap > hard_cap:
        raise RiskError(f"soft_cap must be <= hard_cap, got soft_cap={soft_cap!r} > hard_cap={hard_cap!r}")
    out = {asset: list(series) for asset, series in positions.items()}
    for k in range(len(next(iter(out.values())))):
        gross = sum(abs(series[k]) for series in out.values())
        if gross > soft_cap:
            factor = soft_cap / gross
            for series in out.values():
                series[k] = series[k] * factor
    return out


def apply_net_exposure_band(
    positions: dict[str, list[float]], *, short_bound: float = -0.5, long_bound: float = 1.0
) -> dict[str, list[float]]:
    """Scale each bar whose net exposure leaves [short_bound, long_bound] back to the breached bound; the defaults are §10's band.

    Both sides scale the whole book (factors in (0, 1), so gross shrinks too): a band breach de-risks, never re-optimizes."""
    _validate_positions(positions)
    if not isinstance(short_bound, (int, float)) or not math.isfinite(short_bound) or short_bound >= 0:
        raise RiskError(f"short_bound must be a finite number < 0, got {short_bound!r}")
    if not isinstance(long_bound, (int, float)) or not math.isfinite(long_bound) or long_bound <= 0:
        raise RiskError(f"long_bound must be a finite number > 0, got {long_bound!r}")
    out = {asset: list(series) for asset, series in positions.items()}
    for k in range(len(next(iter(out.values())))):
        net = sum(series[k] for series in out.values())
        if net > long_bound:
            factor = long_bound / net
        elif net < short_bound:
            factor = short_bound / net
        else:
            continue
        for series in out.values():
            series[k] = series[k] * factor
    return out


def _margin_used(long_gross: float, short_gross: float) -> float:
    """Margin used by one bar under the unit-NAV, quote-currency-collateral model (§10).

    Shorts are fully margin-extended and consume collateral first; longs draw margin only beyond the remaining cash.
    Deliberately conservative vs Kraken's tiered leverage schedules — pre-trade research, not the venue's own margining."""
    return short_gross + max(0.0, long_gross - max(0.0, 1.0 - short_gross))


def margin_level(bar_positions: dict[str, float]) -> float:
    """Margin level of one bar of weights under the unit-NAV model (see _margin_used); math.inf when no margin is in use."""
    if not isinstance(bar_positions, dict) or not bar_positions:
        raise RiskError(f"bar_positions must be a non-empty dict, got {bar_positions!r}")
    for asset, weight in bar_positions.items():
        if not isinstance(weight, (int, float)) or not math.isfinite(weight):
            raise RiskError(f"bar_positions[{asset!r}] must be a finite number, got {weight!r}")
    used = _margin_used(
        sum(w for w in bar_positions.values() if w > 0),
        -sum(w for w in bar_positions.values() if w < 0),
    )
    return math.inf if used == 0.0 else 1.0 / used


def _margin_floor_scale(long_gross: float, short_gross: float, floor: float) -> float:
    """Closed-form largest s in (0, 1) scaling a bar of long gross L, short gross S to margin level floor; callers enter below it.

    The branch picks the piece holding the solution — at unit NAV, longs fitting inside the cash shorts leave (margin used sS) or
    longs drawing margin (s(L+2S) − 1) — and floor >= 1, apply_margin_floor's guard, rules out a third (sS >= 1)."""
    t = 1.0 / floor
    if t * (long_gross + short_gross) <= short_gross:
        return t / short_gross
    return (1.0 + t) / (long_gross + 2.0 * short_gross)


def apply_margin_floor(positions: dict[str, list[float]], *, floor: float = 2.5) -> dict[str, list[float]]:
    """Scale each bar whose margin level is below floor down to exactly the floor; the default is §10's self-imposed floor.

    Margin model per _margin_used, scale factor per _margin_floor_scale's closed form. floor must be >= 1: a
    self-imposed margin floor below 100% is past liquidation, meaningless under §10."""
    _validate_positions(positions)
    if not isinstance(floor, (int, float)) or not math.isfinite(floor) or floor < 1.0:
        raise RiskError(f"floor must be a finite number >= 1, got {floor!r}")
    out = {asset: list(series) for asset, series in positions.items()}
    for k in range(len(next(iter(out.values())))):
        long_gross = sum(series[k] for series in out.values() if series[k] > 0)
        short_gross = -sum(series[k] for series in out.values() if series[k] < 0)
        used = _margin_used(long_gross, short_gross)
        if used == 0.0 or 1.0 / used >= floor:
            continue
        factor = _margin_floor_scale(long_gross, short_gross, floor)
        for series in out.values():
            series[k] = series[k] * factor
    return out
