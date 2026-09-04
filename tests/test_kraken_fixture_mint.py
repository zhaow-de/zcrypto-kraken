"""The fixture minter's pure core — the rails that decide what reaches a live account.

`infra/scripts/kraken-fixture-mint.py` is a standalone script, not a package module, so it loads
via `importlib.util.spec_from_file_location` (the precedent `test_order_semantics_probe.py` sets).

What is pinned here is what fails SILENTLY and expensively. A leg minted on a two-way-spelled pair
rests where the verdict this fixture exists to exercise cannot see it, so the run reads clean and
proves nothing. A size taken from a remembered figure rather than the venue's own `ordermin` is
rejected at submit or, worse, accepted at a notional nobody chose. Leverage reaching a leg that was
meant to be spot is a position nobody planned. None of those announce themselves.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "kraken-fixture-mint.py"
_spec = importlib.util.spec_from_file_location("kraken_fixture_mint", _SCRIPT)
mint = importlib.util.module_from_spec(_spec)
# Registered before execution: `@dataclass` resolves its own module out of `sys.modules`, and a
# module absent from it raises during class creation rather than at first use.
sys.modules[_spec.name] = mint
_spec.loader.exec_module(mint)


# SOL/EUR's limits as the venue published them on 2026-09-01. They are a FIXTURE, not a constant the
# script may read: every test that asserts a size derives it from these numbers, so a script that
# hardcoded the same figures would pass here and drift silently at the venue. `test_sizing_follows
# _the_listing_rather_than_a_remembered_figure` is what separates the two.
_LIMITS = mint.PairLimits(ordermin=0.06, costmin=0.45, lot_step=0.00000001, price_step=0.01)
_BEST_BID = 85.76


class TestTheSameKeyGuard:
    """A leg on a pair Kraken spells two ways rests where flatten's verdict cannot see it."""

    @pytest.mark.parametrize("pair", ["BTC/EUR", "ETH/EUR", "XRP/EUR", "LTC/EUR", "ETH/BTC"])
    def test_it_refuses_every_two_way_spelled_leg(self, pair: str) -> None:
        with pytest.raises(mint.Refusal) as exc:
            mint.assert_same_key(pair)
        assert pair in str(exc.value)

    def test_the_healthy_pair_passes(self) -> None:
        """The true positive. A guard that refuses everything ships green and proves nothing."""
        mint.assert_same_key("SOL/EUR")

    def test_the_blind_list_is_imported_rather_than_restated(self) -> None:
        """Two copies of this list already exist on the live trade path. A third would rot apart."""
        from cli.engine.flatten import BLIND_ORDER_READ_LEGS

        assert mint.BLIND_ORDER_READ_LEGS is BLIND_ORDER_READ_LEGS

    def test_the_probe_and_flatten_agree_on_the_blind_legs(self) -> None:
        """The list exists twice on the live trade path. This is the guard that keeps them equal.

        `cli/engine/flatten.py` and `infra/scripts/kraken-order-semantics-probe.py` each define it.
        Neither is edited here; this asserts they have not drifted, which is what makes leaving the
        pair in place safe and what a third copy would have made unenforceable.
        """
        from cli.engine.flatten import BLIND_ORDER_READ_LEGS

        probe_path = _REPO / "infra" / "scripts" / "kraken-order-semantics-probe.py"
        src = probe_path.read_text()
        # Read the literal rather than importing: the probe pulls in a live-venue import surface at
        # module scope, and this assertion needs the constant, not the module.
        match = re.search(r"^RECONCILE_BLIND_LEGS = (\([^)]*\))", src, re.MULTILINE)
        assert match, "the probe's blind-leg constant moved or was renamed"
        assert ast.literal_eval(match.group(1)) == tuple(BLIND_ORDER_READ_LEGS)

    def test_the_planner_refuses_before_it_sizes_anything(self) -> None:
        """The guard runs at plan time, so a dry run on a blind leg refuses rather than printing."""
        with pytest.raises(mint.Refusal):
            mint.plan_legs(pair="BTC/EUR", limits=_LIMITS, best_bid=_BEST_BID, existing=mint.AccountState())


class TestSizing:
    """Sized from what the venue publishes AT RUN TIME, to both floors, never to a memory."""

    def test_quantity_clears_ordermin(self) -> None:
        qty, _ = mint.size_leg(_LIMITS, price=_BEST_BID)
        assert qty >= _LIMITS.ordermin

    def test_quantity_clears_costmin_in_eur(self) -> None:
        qty, notional = mint.size_leg(_LIMITS, price=_BEST_BID)
        assert notional >= _LIMITS.costmin
        assert notional == pytest.approx(qty * _BEST_BID)

    def test_costmin_binds_when_it_is_the_larger_floor(self) -> None:
        """A cheap asset clears `ordermin` long before `costmin`; the larger floor must win."""
        limits = mint.PairLimits(ordermin=1.0, costmin=20.0, lot_step=0.001, price_step=0.0001)
        qty, notional = mint.size_leg(limits, price=2.0)
        assert notional >= 20.0
        assert qty >= 10.0

    def test_the_quantity_lands_on_the_lot_step(self) -> None:
        limits = mint.PairLimits(ordermin=0.06, costmin=0.45, lot_step=0.01, price_step=0.01)
        qty, _ = mint.size_leg(limits, price=_BEST_BID)
        assert qty == pytest.approx(round(qty / 0.01) * 0.01)

    def test_the_resting_price_follows_the_ticker(self) -> None:
        """Move the venue's bid and the resting price must move with it."""
        low = mint.plan_legs(pair="SOL/EUR", limits=_LIMITS, best_bid=40.0, existing=mint.AccountState())
        high = mint.plan_legs(pair="SOL/EUR", limits=_LIMITS, best_bid=120.0, existing=mint.AccountState())
        assert next(l for l in low if l.kind == "resting").price < next(l for l in high if l.kind == "resting").price

    def test_sizing_follows_the_listing_rather_than_a_remembered_figure(self) -> None:
        """The discriminator: move the venue's floor and the size must move with it.

        A script carrying 2026-09-01's `0.06` as a constant passes every assertion above and fails
        this one, which is the whole reason it exists.
        """
        doubled = mint.PairLimits(ordermin=0.12, costmin=0.45, lot_step=0.00000001, price_step=0.01)
        base_qty, _ = mint.size_leg(_LIMITS, price=_BEST_BID)
        moved_qty, _ = mint.size_leg(doubled, price=_BEST_BID)
        assert moved_qty > base_qty
        assert moved_qty >= 0.12


class TestThePlan:
    """Three legs, each exercising a different half of what flatten has to do."""

    def _plan(self, existing: object | None = None) -> list:
        return mint.plan_legs(
            pair="SOL/EUR",
            limits=_LIMITS,
            best_bid=_BEST_BID,
            existing=existing if existing is not None else mint.AccountState(),
        )

    def test_it_mints_the_three_ingredients(self) -> None:
        kinds = [leg.kind for leg in self._plan()]
        assert kinds == ["resting", "margin", "spot"]

    def test_the_resting_leg_is_unfillable_and_rests(self) -> None:
        leg = next(l for l in self._plan() if l.kind == "resting")
        assert leg.order_type == "LIMIT"
        assert leg.time_in_force == "GTC"
        assert leg.side == "BUY"
        # Below the venue's own best bid at run time, by a stated fraction, rounded to the pair's
        # price step. Never a remembered figure: 2026-09-01's 45.95 is not a property of any run.
        assert leg.price is not None
        assert leg.price == pytest.approx(mint.resting_price(_BEST_BID, _LIMITS.price_step))
        assert leg.price < _BEST_BID

    def test_the_margin_leg_is_marketable_because_it_needs_a_fill(self) -> None:
        leg = next(l for l in self._plan() if l.kind == "margin")
        assert leg.order_type == "MARKET"
        assert leg.account_type == "MARGIN"
        assert leg.leverage is not None and leg.leverage >= 2

    def test_the_spot_leg_leaves_a_sellable_non_eur_balance(self) -> None:
        leg = next(l for l in self._plan() if l.kind == "spot")
        assert leg.order_type == "MARKET"
        assert leg.side == "BUY"
        assert leg.account_type == "CASH"

    def test_leverage_reaches_the_margin_leg_and_nothing_else(self) -> None:
        """No surprise leverage: a spot leg that carries it is a position nobody planned."""
        for leg in self._plan():
            if leg.kind == "margin":
                assert leg.leverage is not None
            else:
                assert leg.leverage is None, f"{leg.kind} leg carries leverage {leg.leverage}"

    def test_every_leg_is_on_the_same_key_pair(self) -> None:
        assert {leg.pair for leg in self._plan()} == {"SOL/EUR"}

    def test_every_leg_states_a_notional_so_the_dry_run_can_print_it(self) -> None:
        for leg in self._plan():
            assert leg.notional_eur > 0


class TestTheDoubleMintGuard:
    """A re-run must not double the fixture; it reports what is already there and skips it."""

    def test_an_existing_resting_order_drops_that_leg(self) -> None:
        state = mint.AccountState(resting_pairs=("SOL/EUR",))
        kinds = [leg.kind for leg in self._plan_with(state)]
        assert "resting" not in kinds

    def test_an_existing_position_drops_the_margin_leg(self) -> None:
        state = mint.AccountState(position_pairs=("SOL/EUR",))
        kinds = [leg.kind for leg in self._plan_with(state)]
        assert "margin" not in kinds

    def test_an_existing_non_eur_balance_drops_the_spot_leg(self) -> None:
        state = mint.AccountState(non_eur_assets=("SOL",))
        kinds = [leg.kind for leg in self._plan_with(state)]
        assert "spot" not in kinds

    def test_a_fully_minted_account_plans_nothing(self) -> None:
        state = mint.AccountState(resting_pairs=("SOL/EUR",), position_pairs=("SOL/EUR",), non_eur_assets=("SOL",))
        assert self._plan_with(state) == []

    def test_an_unrelated_pair_does_not_satisfy_a_leg(self) -> None:
        """The guard keys on THIS pair; a resting ADA order is not this fixture's resting leg."""
        state = mint.AccountState(resting_pairs=("ADA/EUR",))
        assert "resting" in [leg.kind for leg in self._plan_with(state)]

    @staticmethod
    def _plan_with(state: object) -> list:
        return mint.plan_legs(pair="SOL/EUR", limits=_LIMITS, best_bid=_BEST_BID, existing=state)


class TestTheConfirmGate:
    """`--execute` alone sends nothing; the typed word is the second half of the gate."""

    def test_the_exact_word_passes(self) -> None:
        mint.check_confirmation(mint.CONFIRM_WORD)

    @pytest.mark.parametrize("typed", ["", "yes", "y", "mint", " MINT", "mint "])
    def test_anything_else_refuses(self, typed: str) -> None:
        with pytest.raises(mint.Refusal):
            mint.check_confirmation(typed)

    def test_the_word_is_not_yes(self) -> None:
        """A gate answerable by reflex is not a gate."""
        assert mint.CONFIRM_WORD.lower() not in {"y", "yes", "ok"}
