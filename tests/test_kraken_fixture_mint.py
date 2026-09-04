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
import json
import os
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


# Two AssetPairs rows as the venue published them, recorded verbatim: SOL/EUR (the pair this script
# mints on) and XXBTZEUR, whose key, altname and wsname are three different strings.
_LISTING = json.loads((_REPO / "tests" / "fixtures" / "kraken_assetpairs_mint.json").read_text())

# The same limits written out independently of the reader that parses them. They are a FIXTURE, not
# a constant the script may read: every test that asserts a size derives it from these numbers, so a
# script that hardcoded the same figures would pass here and drift silently at the venue.
# `test_sizing_follows_the_listing_rather_than_a_remembered_figure` is what separates the two, and
# `test_the_reader_and_the_hand_written_limits_agree` is what keeps this copy honest.
_LIMITS = mint.PairLimits(ordermin=0.06, costmin=0.45, lot_step=0.00000001, price_step=0.01)
_BEST_BID = 85.76

# Both live doors are shut for this module unless the run opts in. `ZCRYPTO_LIVE_VENUE_TESTS` is the
# repo's existing name for that opt-in (`test_engine_node.py`).
_LIVE_OPT_IN = "ZCRYPTO_LIVE_VENUE_TESTS"


@pytest.fixture(autouse=True)
def _no_unintended_dialling(monkeypatch):
    """Every live door raises unless the venue opt-in is set, so a missed patch fails loudly.

    `_run` takes both factories with no default, so a missed argument is already a TypeError there.
    This covers the rest: a test that reaches `main`, or any later caller that names a live door
    directly. It is not hypothetical -- a test in this module bound `_live_client` as a default at
    definition, built a real client and sent two real requests. Patching `socket` could not see it:
    the client's I/O lives in a compiled extension and never passes through Python's socket layer,
    so a raise on the door itself is the only evidence available from this side.
    """
    if os.environ.get(_LIVE_OPT_IN) == "1":
        return

    def _refuse(*_args, **_kwargs):
        raise AssertionError(
            f"a test reached a live venue door; set {_LIVE_OPT_IN}=1 to allow it deliberately",
        )

    monkeypatch.setattr(mint, "_live_client", _refuse)
    monkeypatch.setattr(mint, "_live_listing", _refuse)


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


class TestTheFloorsComeFromTheRow:
    """Both floors and both steps are the venue's own published row, or the run refuses.

    The adapter's instrument object is the other candidate source and it is the wrong one: it is a
    translation, and it answered None for `min_quantity` on this very pair. A None read as 0.0 is a
    floor that always clears, on the one path where clearing wrongly is a rejected order at best.
    """

    def test_it_reads_both_floors_off_the_row(self) -> None:
        limits = mint.pair_limits(_LISTING, "SOL/EUR")
        assert limits.ordermin == 0.06
        assert limits.costmin == 0.45

    def test_it_derives_both_steps_from_the_row_decimals(self) -> None:
        """`lot_decimals` 8 and `pair_decimals` 2 are what SOL/EUR publishes; a step is 10**-that."""
        limits = mint.pair_limits(_LISTING, "SOL/EUR")
        assert limits.lot_step == 0.00000001
        assert limits.price_step == 0.01

    def test_the_reader_and_the_hand_written_limits_agree(self) -> None:
        """Two independent producers of the same four numbers. A disagreement IS the finding."""
        assert mint.pair_limits(_LISTING, "SOL/EUR") == _LIMITS

    @pytest.mark.parametrize("field", ["ordermin", "costmin", "lot_decimals", "pair_decimals"])
    def test_a_missing_floor_refuses_rather_than_defaulting(self, field: str) -> None:
        listing = {"SOLEUR": {k: v for k, v in _LISTING["SOLEUR"].items() if k != field}}
        with pytest.raises(mint.Refusal) as exc:
            mint.pair_limits(listing, "SOL/EUR")
        assert field in str(exc.value)

    @pytest.mark.parametrize("field", ["ordermin", "costmin", "lot_decimals", "pair_decimals"])
    def test_a_null_floor_refuses_too(self, field: str) -> None:
        """Present-and-null is how a translation reports a field it did not fill. Same refusal."""
        listing = {"SOLEUR": {**_LISTING["SOLEUR"], field: None}}
        with pytest.raises(mint.Refusal) as exc:
            mint.pair_limits(listing, "SOL/EUR")
        assert field in str(exc.value)

    def test_a_pair_absent_from_the_listing_refuses(self) -> None:
        with pytest.raises(mint.Refusal):
            mint.pair_limits(_LISTING, "ADA/EUR")

    def test_it_finds_a_row_whose_key_altname_and_wsname_all_differ(self) -> None:
        """The reader resolves by wsname, so `XXBTZEUR` / `XBTEUR` / `XBT/EUR` is one row to it.

        That is a separate question from whether this script will MINT there -- it will not, and
        `TestTheSameKeyGuard` is the refusal that says so. Keeping them independent is the point:
        a reader that could not find the row would hide the guard behind a lookup failure.
        """
        assert mint.pair_limits(_LISTING, "BTC/EUR").ordermin == 0.00005


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


class TestTheRestingLegClearsBothFloorsAtItsOwnPrice:
    """`costmin` is a floor on the ORDER's notional, and this order is priced far below the market.

    Sizing it at the best bid clears a floor the resting leg itself misses, and the venue rejects it
    at submit -- an attended pass that gets two of its three ingredients and a rejection.
    """

    # `ordermin` 0.06 clears at the bid on its own, so `costmin` 4.00 is what the resting price has
    # to be sized against: at 85.76 the ordermin-sized 0.06 is worth 5.15 and clears, at the 47.16
    # it will rest at it is worth 2.83 and does not. A costmin either leg clears would prove nothing.
    _SPLIT = mint.PairLimits(ordermin=0.06, costmin=4.0, lot_step=0.00000001, price_step=0.01)

    def _resting(self, limits) -> object:
        legs = mint.plan_legs(pair="SOL/EUR", limits=limits, best_bid=_BEST_BID, existing=mint.AccountState())
        return next(leg for leg in legs if leg.kind == "resting")

    def test_the_notional_at_the_resting_price_clears_costmin(self) -> None:
        leg = self._resting(self._SPLIT)
        assert leg.quantity * leg.price >= self._SPLIT.costmin

    def test_the_quantity_still_clears_ordermin(self) -> None:
        leg = self._resting(self._SPLIT)
        assert leg.quantity >= self._SPLIT.ordermin

    def test_the_printed_notional_is_the_one_the_venue_will_see(self) -> None:
        """The dry run's EUR figure is what the operator approves; it must be the resting one."""
        leg = self._resting(self._SPLIT)
        assert leg.notional_eur == pytest.approx(leg.quantity * leg.price)

    def test_the_live_listing_passes_too(self) -> None:
        """The true positive: SOL/EUR's real floors, where both clear and nothing is walked."""
        leg = self._resting(_LIMITS)
        assert leg.quantity >= _LIMITS.ordermin
        assert leg.quantity * leg.price >= _LIMITS.costmin


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


class _Recorder:
    """A client that records every call and sends nothing.

    It answers the reads with a listing shaped like the venue's and refuses to grow a cancel method:
    the property under test is what this script does NOT do, and a stub carrying `cancel_order`
    would let a regression that called it pass unnoticed.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.submitted: list[dict] = []
        self.cached: list[object] = []

    async def request_instruments(self, pairs=None):
        self.calls.append("request_instruments")
        return [_Instrument()]

    async def request_book_snapshot(self, instrument_id, depth=1):
        self.calls.append("request_book_snapshot")
        return _Book()

    async def request_order_status_reports(self, account, **kw):
        self.calls.append("request_order_status_reports")
        return []

    async def request_position_status_reports(self, account, **kw):
        self.calls.append("request_position_status_reports")
        return []

    async def request_account_state(self, account, **kw):
        self.calls.append("request_account_state")
        return _AccountReport()

    def cache_instrument(self, instrument) -> None:
        self.calls.append("cache_instrument")
        self.cached.append(instrument)

    async def submit_order(self, **kwargs):
        self.calls.append("submit_order")
        self.submitted.append(kwargs)


class _Instrument:
    """The adapter's instrument object, recorded as the venue actually answered for SOL/EUR.

    Every floor is None because that is what came back, and they are left None deliberately: the
    object is cached and never read for a size, so any sizing path that reached back into it would
    raise on `float(None)` here rather than freeze a floor to zero against real money.
    """

    id = "SOL/EUR.KRAKEN"
    min_quantity = None
    min_notional = None
    size_increment = None
    price_increment = None


class _Level:
    price = 85.76


class _Book:
    def bids(self):
        return [_Level()]


class _AccountReport:
    balances = ()


def _args(execute: bool):
    import argparse

    return argparse.Namespace(pair="SOL/EUR", execute=execute)


def _factories(rec: object) -> dict:
    """Both live doors, replaced. Neither has a default, so a forgotten one is a TypeError."""
    return {"client_factory": lambda _k, _s: rec, "listing_factory": lambda: _LISTING}


@pytest.fixture
def _creds(monkeypatch):
    monkeypatch.setenv(mint.API_KEY_VAR, "not-a-real-key")
    monkeypatch.setenv(mint.API_SECRET_VAR, "not-a-real-secret")


class TestTheDoorsAreShut:
    """The positive trace. A guard nobody saw fire is a guard nobody has evidence of."""

    @pytest.mark.skipif(
        os.environ.get(_LIVE_OPT_IN) == "1",
        reason=f"{_LIVE_OPT_IN}=1 deliberately opens the doors this asserts are shut",
    )
    def test_both_live_doors_raise_for_this_module(self) -> None:
        for door in (mint._live_client, mint._live_listing):
            with pytest.raises(AssertionError, match=_LIVE_OPT_IN):
                door()

    def test_run_cannot_be_called_without_being_told_which_doors_to_use(self) -> None:
        """No default binds the live pair at definition, so a missed patch is a TypeError here.

        This is the assertion the earlier defaulted signature could not carry: a test that patched
        the module attribute and forgot the argument built a real client and sent real requests, and
        nothing in the suite said so.
        """
        with pytest.raises(TypeError):
            mint._run(_args(execute=False))


class TestNothingIsSentWithoutExecute:
    """The dry run is the default, and the default must reach the venue's READS and nothing else."""

    def test_the_dry_run_submits_nothing(self, _creds) -> None:
        import asyncio

        rec = _Recorder()
        rc = asyncio.run(mint._run(_args(execute=False), **_factories(rec)))
        assert rc == 0
        assert rec.submitted == []
        assert "submit_order" not in rec.calls

    def test_the_dry_run_cancels_nothing(self, _creds) -> None:
        """`_Recorder` has no cancel method at all, so a call would raise rather than pass quietly."""
        import asyncio

        rec = _Recorder()
        asyncio.run(mint._run(_args(execute=False), **_factories(rec)))
        assert not any("cancel" in call for call in rec.calls)

    def test_the_dry_run_still_reads_the_account(self, _creds) -> None:
        """A plan printed without reading the account cannot know what is already there."""
        import asyncio

        rec = _Recorder()
        asyncio.run(mint._run(_args(execute=False), **_factories(rec)))
        assert "request_order_status_reports" in rec.calls
        assert "request_instruments" in rec.calls


class TestTheExecutePath:
    """With the flag AND the typed word: exactly the three legs, and still nothing cancelled."""

    def _run_execute(self, rec, typed=None):
        import asyncio

        monkey_prompt = lambda _msg: mint.CONFIRM_WORD if typed is None else typed  # noqa: E731
        return asyncio.run(mint._run(_args(execute=True), **_factories(rec), prompt=monkey_prompt))

    def test_it_submits_exactly_three_legs(self, _creds, monkeypatch) -> None:
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
        rec = _Recorder()
        assert self._run_execute(rec) == 0
        assert len(rec.submitted) == 3

    def test_it_cancels_nothing(self, _creds, monkeypatch) -> None:
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
        rec = _Recorder()
        self._run_execute(rec)
        assert not any("cancel" in call for call in rec.calls)

    def test_it_caches_the_instrument_before_submitting(self, _creds, monkeypatch) -> None:
        """`submit_order` documents `The instrument is not found in cache.` among its errors."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
        rec = _Recorder()
        self._run_execute(rec)
        assert rec.calls.index("cache_instrument") < rec.calls.index("submit_order")

    def test_a_wrong_confirmation_sends_nothing(self, _creds, monkeypatch) -> None:
        """`_run` refuses; `main` is what turns that into a non-zero exit. Both halves matter, and
        the one that matters here is that the plan was printed and NOTHING followed it."""
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
        rec = _Recorder()
        with pytest.raises(mint.Refusal):
            self._run_execute(rec, typed="yes")
        assert rec.submitted == []
        assert "submit_order" not in rec.calls
