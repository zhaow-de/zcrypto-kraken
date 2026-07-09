"""Drawdown governor — master-plan §10's drawdown-governance ladder as a pure returns overlay.

The multiplier for bar t is fixed from the GOVERNED path through bar t-1 (the live book only ever
sees its own equity), then governed_returns[t] = multipliers[t] * returns[t] — no look-ahead by
construction. Semantics per docs/specs/00034-drawdown-governor-design.md: a pure threshold ladder
on drawdown from the governed high-water mark (inclusive boundaries, no hysteresis); a daily-loss
rule (governed return <= -daily_loss_limit) holding daily_loss_multiplier for daily_loss_cooldown
bars, renewed by each new trigger bar; min-composition of the two (the most restrictive control
governs); a ladder rung of exactly 0.0 is terminal — flat for restart_after bars, then re-arm with
the HWM reset to current governed equity (a flat book's drawdown is frozen, so re-arm cannot key
on recovery); restart_after=None stays flat to the end of the series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cli.risk.errors import RiskError


@dataclass(frozen=True)
class GovernorConfig:
    """The D1-ratified §10 constants as defaults; the knobs exist for test isolation + the sensitivity read."""

    daily_loss_limit: float = 0.03
    daily_loss_multiplier: float = 0.5
    daily_loss_cooldown: int = 5
    ladder: tuple[tuple[float, float], ...] = ((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))
    restart_after: int | None = 30


@dataclass(frozen=True)
class GovernorResult:
    multipliers: list[float]
    governed_returns: list[float]
    daily_loss_triggers: int
    rung_bars: dict[float, int]
    breaches: int
    rung_transitions: int


def _validate(returns: list[float], config: GovernorConfig) -> None:
    if not isinstance(returns, list) or not returns:
        raise RiskError(f"returns must be a non-empty list, got {returns!r}")
    for r in returns:
        if not isinstance(r, (int, float)) or not math.isfinite(r) or r <= -1.0:
            raise RiskError(f"returns must be finite numbers > -1, got {r!r}")
    c = config
    if not isinstance(c.daily_loss_limit, (int, float)) or not math.isfinite(c.daily_loss_limit) or c.daily_loss_limit <= 0:
        raise RiskError(f"daily_loss_limit must be a finite number > 0, got {c.daily_loss_limit!r}")
    if (
        not isinstance(c.daily_loss_multiplier, (int, float))
        or not math.isfinite(c.daily_loss_multiplier)
        or not 0.0 <= c.daily_loss_multiplier <= 1.0
    ):
        raise RiskError(f"daily_loss_multiplier must be a finite number in [0, 1], got {c.daily_loss_multiplier!r}")
    if not isinstance(c.daily_loss_cooldown, int) or c.daily_loss_cooldown < 1:
        raise RiskError(f"daily_loss_cooldown must be an int >= 1, got {c.daily_loss_cooldown!r}")
    if not isinstance(c.ladder, tuple) or not c.ladder:
        raise RiskError(f"ladder must be a non-empty tuple of (threshold, multiplier) pairs, got {c.ladder!r}")
    prev_threshold = 0.0
    for rung in c.ladder:
        if not isinstance(rung, tuple) or len(rung) != 2:
            raise RiskError(f"each ladder rung must be a (threshold, multiplier) pair, got {rung!r}")
        threshold, rung_mult = rung
        if not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold <= prev_threshold:
            raise RiskError(f"ladder thresholds must be finite, > 0, and strictly ascending, got {c.ladder!r}")
        if not isinstance(rung_mult, (int, float)) or not math.isfinite(rung_mult) or not 0.0 <= rung_mult <= 1.0:
            raise RiskError(f"ladder multipliers must be finite numbers in [0, 1], got {rung_mult!r}")
        prev_threshold = threshold
    if c.restart_after is not None and (not isinstance(c.restart_after, int) or c.restart_after < 1):
        raise RiskError(f"restart_after must be None or an int >= 1, got {c.restart_after!r}")


def drawdown_governor(returns: list[float], *, config: GovernorConfig = GovernorConfig()) -> GovernorResult:
    """Apply the §10 governor to a (net-of-cost) returns series; see the module docstring for semantics."""
    _validate(returns, config)
    multipliers: list[float] = []
    governed: list[float] = []
    equity = 1.0
    hwm = 1.0
    daily_loss_triggers = 0
    breaches = 0
    rung_bars: dict[float, int] = {}
    cooldown_left = 0
    flat_left = 0
    flat_forever = False

    for r in returns:
        if flat_forever or flat_left > 0:
            mult = 0.0
        else:
            drawdown = 1.0 - equity / hwm
            ladder_mult = 1.0
            for threshold, rung_mult in config.ladder:
                if drawdown >= threshold:
                    ladder_mult = rung_mult
            if ladder_mult == 0.0:
                breaches += 1
                if config.restart_after is None:
                    flat_forever = True
                else:
                    flat_left = config.restart_after
                mult = 0.0
            else:
                daily_mult = config.daily_loss_multiplier if cooldown_left > 0 else 1.0
                mult = min(ladder_mult, daily_mult)
        multipliers.append(mult)
        g = mult * r
        governed.append(g)
        rung_bars[mult] = rung_bars.get(mult, 0) + 1
        equity *= 1.0 + g
        if flat_left > 0:
            flat_left -= 1
            if flat_left == 0:
                hwm = equity  # re-arm: fresh drawdown budget after the stand-down
                cooldown_left = 0
        elif not flat_forever:
            hwm = max(hwm, equity)
            if cooldown_left > 0:
                cooldown_left -= 1
            if g <= -config.daily_loss_limit:
                daily_loss_triggers += 1
                cooldown_left = config.daily_loss_cooldown

    transitions = sum(1 for t in range(1, len(multipliers)) if multipliers[t] != multipliers[t - 1])
    return GovernorResult(
        multipliers=multipliers,
        governed_returns=governed,
        daily_loss_triggers=daily_loss_triggers,
        rung_bars=rung_bars,
        breaches=breaches,
        rung_transitions=transitions,
    )
