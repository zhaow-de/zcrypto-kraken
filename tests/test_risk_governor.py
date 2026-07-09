import math

import pytest

from cli.risk import GovernorConfig, GovernorResult, RiskError, drawdown_governor

# Configs that isolate one rule by disabling the other.
LADDER_ONLY = GovernorConfig(daily_loss_limit=0.5, restart_after=2)  # daily rule can't trigger on these paths
DAILY_ONLY = GovernorConfig(ladder=((0.99, 0.5),))  # ladder can't trigger on these paths

# Hand-computed ladder walk (spec §TDD): dd path 0 -> 5% -> 9.75% -> 12.01% -> 16.41% (breach) -> re-arm.
WALK_RETURNS = [-0.05, -0.05, -0.05, -0.2, 0.1, 0.1, -0.05, 0.0]
WALK_MULTS = [1.0, 1.0, 0.5, 0.25, 0.0, 0.0, 1.0, 1.0]


def test_planted_ladder_walk():
    res = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    assert res.multipliers == WALK_MULTS
    assert res.breaches == 1
    assert res.rung_bars == {1.0: 4, 0.5: 1, 0.25: 1, 0.0: 2}
    assert res.rung_transitions == 4


def test_ladder_boundary_inclusive():
    # Exact binary numbers: E = 0.75 exactly, dd = 0.25 exactly; DD >= threshold selects the rung.
    cfg = GovernorConfig(daily_loss_limit=0.5, ladder=((0.25, 0.5),))
    res = drawdown_governor([-0.25, 0.0], config=cfg)
    assert res.multipliers == [1.0, 0.5]


def test_no_lookahead():
    base = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    perturbed = list(WALK_RETURNS)
    t = 3
    perturbed[t] = perturbed[t] + 0.5
    pert = drawdown_governor(perturbed, config=LADDER_ONLY)
    assert pert.multipliers[: t + 1] == base.multipliers[: t + 1]


def test_governed_feedback_prevents_breach():
    # Ungoverned this path breaches 15%; damped by the rungs, governed stays above -15%.
    returns = [-0.07, -0.05, -0.05, -0.05]
    equity = 1.0
    for r in returns:
        equity *= 1.0 + r
    assert 1.0 - equity > 0.15  # ungoverned breaches
    res = drawdown_governor(returns, config=GovernorConfig(daily_loss_limit=0.99, restart_after=None))
    assert res.breaches == 0
    assert res.multipliers == [1.0, 1.0, 0.25, 0.25]


def test_daily_loss_trigger_cooldown_and_renewal():
    # Trigger at bar 0 (governed -3%, inclusive), renewal at bar 3 (governed 0.5 * -0.08 = -4%).
    returns = [-0.03, 0.0, 0.0, -0.08, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01]
    res = drawdown_governor(returns, config=DAILY_ONLY)
    assert res.multipliers == [1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0]
    assert res.daily_loss_triggers == 2


def test_daily_loss_strict_boundary():
    res = drawdown_governor([-0.0299, 0.0, 0.0], config=DAILY_ONLY)
    assert res.multipliers == [1.0, 1.0, 1.0]
    assert res.daily_loss_triggers == 0


def test_min_composition_not_product():
    # Bar 1: ladder says 0.5 (dd 6% >= 5%) AND daily rule says 0.5 -> min is 0.5, not 0.25.
    cfg = GovernorConfig(ladder=((0.05, 0.5),))
    res = drawdown_governor([-0.06, 0.0], config=cfg)
    assert res.multipliers[1] == 0.5


def test_terminal_no_restart():
    res = drawdown_governor(WALK_RETURNS, config=GovernorConfig(daily_loss_limit=0.5, restart_after=None))
    assert res.multipliers == [1.0, 1.0, 0.5, 0.25, 0.0, 0.0, 0.0, 0.0]
    assert res.breaches == 1


def test_rearm_resets_hwm():
    # After the 2-bar stand-down the HWM resets to current equity: bar 6's fresh -5% dip
    # is measured from the new base (dd 5% < 7.5%), so bar 7 stays at 1.0.
    res = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    assert res.multipliers[6] == 1.0
    assert res.multipliers[7] == 1.0


def test_identity_and_occupancy():
    res = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    for t in range(len(WALK_RETURNS)):
        assert res.governed_returns[t] == pytest.approx(res.multipliers[t] * WALK_RETURNS[t])
    assert sum(res.rung_bars.values()) == len(WALK_RETURNS)


def test_all_positive_inert():
    res = drawdown_governor([0.01] * 10)
    assert res.multipliers == [1.0] * 10
    assert res.daily_loss_triggers == 0
    assert res.breaches == 0
    assert res.rung_bars == {1.0: 10}
    assert res.rung_transitions == 0


def test_result_type():
    assert isinstance(drawdown_governor([0.01, 0.02]), GovernorResult)


@pytest.mark.parametrize(
    "returns",
    [[], [0.01, float("nan")], [0.01, float("inf")], [0.01, -1.0], [0.01, -1.5], "not a list"],
)
def test_invalid_returns(returns):
    with pytest.raises(RiskError):
        drawdown_governor(returns)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"daily_loss_limit": 0.0},
        {"daily_loss_limit": -0.03},
        {"daily_loss_limit": float("nan")},
        {"daily_loss_multiplier": -0.1},
        {"daily_loss_multiplier": 1.5},
        {"daily_loss_cooldown": 0},
        {"daily_loss_cooldown": 2.5},
        {"ladder": ()},
        {"ladder": ((0.11, 0.5), (0.075, 0.25))},  # not ascending
        {"ladder": ((0.0, 0.5),)},  # threshold must be > 0
        {"ladder": ((0.075, 1.5),)},  # multiplier out of [0, 1]
        {"ladder": ((0.075, 0.5, 0.1),)},  # not a pair
        {"restart_after": 0},
        {"restart_after": -5},
        {"restart_after": 2.5},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(RiskError):
        drawdown_governor([0.01, 0.02], config=GovernorConfig(**kwargs))


def test_daily_multiplier_zero_is_not_terminal():
    # A 0.0 daily multiplier flattens for the cooldown but is NOT a breach and re-arms without HWM reset.
    cfg = GovernorConfig(ladder=((0.99, 0.5),), daily_loss_multiplier=0.0, daily_loss_cooldown=2)
    res = drawdown_governor([-0.03, 0.0, 0.0, 0.01], config=cfg)
    assert res.multipliers == [1.0, 0.0, 0.0, 1.0]
    assert res.breaches == 0
