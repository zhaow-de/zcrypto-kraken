"""§10 portfolio limits — pure pre-trade transforms: per-asset caps, gross-leverage cap, net-exposure band, margin floor.

Transform only, no redistribution (a §10 limit is a pre-trade governor, not an optimizer; the excess
sits in cash). Inclusive: a book exactly at a limit passes untouched, and untouched paths return their
values bit-identical. Each limit is individually idempotent in the model (f(f(x)) = f(x)), but only
float-approximately in practice — a double application may differ in the last bits, so a future
fixed-point loop must not key on bitwise equality. Applying one limit may re-tighten another's input;
the consumer decides the order — recommended: position caps → gross leverage cap → net exposure band →
margin floor.
"""

from __future__ import annotations

import math

from cli.risk.errors import RiskError


def apply_position_caps(
    positions: dict[str, list[float]], *, long_cap: float = 0.20, short_cap: float = 0.10
) -> dict[str, list[float]]:
    """Clip each asset's per-bar position to [-short_cap, +long_cap]; §10 defaults 20%/10% NAV."""
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
    """Scale each bar with gross leverage above soft_cap proportionally down to it; §10 defaults 1.5× soft / 2.0× hard.

    The pre-trade governor always targets the soft cap, leaving headroom below hard; hard_cap is validated
    (soft_cap <= hard_cap) and named here as the §10 alerting constant — a transform that already scales to
    soft_cap can never emit gross above it, so hard needs no second code path. Inclusive: a bar exactly at
    soft_cap passes unscaled.
    """
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
    """Scale each bar whose net exposure leaves [short_bound, long_bound] back to the breached bound; §10 defaults −0.5/+1.0.

    Whole-book proportional scaling on both sides (both factors in (0, 1), so gross shrinks too): a §10 band
    breach is a de-risking event, never a re-optimization. Inclusive at both bounds; a net of zero never scales.
    """
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

    Shorts are fully margin-extended and consume collateral first; longs draw margin only beyond the
    remaining cash: m = S + max(0, L − max(0, 1 − S)). Deliberately conservative vs Kraken's tiered
    leverage schedules — backtest/pre-trade research use; the live engine reconciles at 6b.
    """
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
    """Closed-form largest s in (0, 1) such that the bar scaled by s has margin level >= floor.

    With unit NAV, long gross L and short gross S (both scale linearly in s; the cash offset does not), the
    scaled bar's margin used is m(s) = sS + max(0, sL − max(0, 1 − sS)), and level(s) = 1/m(s) >= floor is
    m(s) <= t with t = 1/floor. m(s) is continuous, piecewise linear, and nondecreasing with m(0) = 0, so the
    largest admissible s solves m(s) = t on whichever piece contains it. The domain is floor >= 1 (guarded by
    apply_margin_floor), i.e. t <= 1, so the shorts-exhaust-the-collateral piece (sS >= 1, where m = s(L+S))
    is unreachable — its solution s = t/(L+S) would need tS > L+S, impossible with t <= 1 since tS <= S <= L+S
    — leaving two pieces:

      (a) longs fit in the cash left by shorts, s(L+S) <= 1:  m(s) = sS          → s = t/S          iff t(L+S) <= S
      (b) longs draw margin, cash remains, sS < 1 < s(L+S):   m(s) = s(L+2S) − 1 → s = (1+t)/(L+2S) iff t(L+S) > S

    Each piece's iff-condition is its solution substituted back into the piece's own s-range ((b)'s upper
    bound sS <= 1 reduces to tS <= L+S, automatic with t <= 1), the pieces agree at the breakpoint (at
    s(L+S) = 1 both give sS), and m is strictly increasing wherever m > 0, so the solution is unique.
    Callers only reach here with m(1) > t > 0, hence s in (0, 1).
    """
    t = 1.0 / floor
    if t * (long_gross + short_gross) <= short_gross:
        return t / short_gross
    return (1.0 + t) / (long_gross + 2.0 * short_gross)


def apply_margin_floor(positions: dict[str, list[float]], *, floor: float = 2.5) -> dict[str, list[float]]:
    """Scale each bar whose margin level is below floor down to exactly the floor; §10 default 2.5 (the 250% self-floor).

    Margin model per _margin_used (unit NAV, quote-currency collateral); the scale factor is the closed form
    derived in _margin_floor_scale — no bisection. floor must be >= 1: a self-imposed margin floor below 100%
    is past liquidation, meaningless under §10. A bar using no margin (m = 0, level inf) never scales.
    Inclusive: a bar exactly at the floor passes unscaled.
    """
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
