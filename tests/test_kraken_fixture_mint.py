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
from nautilus_trader.model import AccountType, OrderSide, OrderType, TimeInForce

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

    The adapter's instrument object is the other candidate source and it is the wrong one: this
    adapter never maps `costmin` into `min_notional`, so the object cannot supply one of the two
    floors for any pair -- it answers None, always. A None read as 0.0 is a floor that always
    clears, on the one path where clearing wrongly is a rejected order at best.
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

    def test_the_lookup_finds_a_row_whose_key_altname_and_wsname_all_differ(self) -> None:
        """`resolve_row` resolves by wsname, so `XXBTZEUR` / `XBTEUR` / `XBT/EUR` is one row to it.

        Whether this script will MINT there is a separate question, refused twice over by
        `TestTheMeasuredSameKeyRefusal` and `TestTheSameKeyGuard`. Keeping the lookup separately
        checkable is the point: a lookup that could not find the row would hide both refusals
        behind a miss, and a miss looks like a guard working.
        """
        pair_key, row = mint.resolve_row(_LISTING, "BTC/EUR")
        assert pair_key == "XXBTZEUR"
        assert row["altname"] == "XBTEUR"
        assert row["ordermin"] == "0.00005"


class TestTheMeasuredSameKeyRefusal:
    """The second producer of the same fact, read off the venue's row rather than off a list.

    The two are deliberately independent: the list refuses before anything is read, the row refuses
    what the list has not learned. Where they disagree the refusal says so, because a disagreement
    is a finding about the list and not a duplicate refusal.
    """

    def test_a_two_way_spelled_row_refuses(self) -> None:
        with pytest.raises(mint.Refusal) as exc:
            mint.pair_limits(_LISTING, "BTC/EUR")
        assert "XXBTZEUR" in str(exc.value)
        assert "XBTEUR" in str(exc.value)

    def test_the_refusal_says_the_two_guards_agree(self) -> None:
        with pytest.raises(mint.Refusal) as exc:
            mint.pair_limits(_LISTING, "BTC/EUR")
        assert "the hardcoded list agrees" in str(exc.value)

    def test_a_leg_the_list_has_not_learned_names_the_list_as_the_finding(self) -> None:
        """The case that justifies a second producer at all: the venue re-spells a leg and the
        hardcoded list is behind. The refusal must not read as a routine two-way leg."""
        listing = {"SOLEUR": {**_LISTING["SOLEUR"], "altname": "SOLXEUR"}}
        with pytest.raises(mint.Refusal) as exc:
            mint.pair_limits(listing, "SOL/EUR")
        assert "is behind the venue" in str(exc.value)
        assert "SOL/EUR" not in mint.BLIND_ORDER_READ_LEGS

    def test_the_healthy_row_passes(self) -> None:
        """The true positive. SOL/EUR's key and altname are the same string, so nothing fires."""
        assert mint.pair_limits(_LISTING, "SOL/EUR").ordermin == 0.06

    def test_a_row_with_no_altname_refuses_rather_than_comparing_to_none(self) -> None:
        listing = {"SOLEUR": {k: v for k, v in _LISTING["SOLEUR"].items() if k != "altname"}}
        with pytest.raises(mint.Refusal) as exc:
            mint.pair_limits(listing, "SOL/EUR")
        assert "altname" in str(exc.value)


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


class TestTheVaultedKeyWrappersHaveFixedTargets:
    """Neither wrapper may grow a selector, and this reads BOTH because the property is symmetric.

    The sibling is the one carrying a wildcarded standing grant in `.claude/settings.json`, so it is
    the more dangerous of the two to make selectable: an argument that chose a program would turn
    that grant into "run anything with the live trade key". This script's own wrapper is not
    allowlisted, which is deliberate and is the owner's to change -- so nothing here asserts on
    `settings.json`; what is pinned is only that each wrapper's target is a literal path.
    """

    WRAPPERS = ("mint-with-vaulted-key.sh", "probe-with-vaulted-key.sh")

    # Two rounds of review took this guard apart, and the lesson is that enumerating forbidden
    # FORMS does not work: each round I pinned what the mutation I had imagined would touch, and
    # each round a form I had not imagined walked through -- a selector on the argv line, one inside
    # `os.execve`, one on `venv_python` (which is the program `execve` actually runs), a symmetric
    # edit to BOTH files, and a shell function named `exec` declared ABOVE the anchor, which bash
    # resolves before the builtin. So this pins the SURFACE instead of the forms: everything above
    # the anchor must be comment, the executable body must match the sibling's byte for byte save
    # one line, and the sibling's own body is pinned by digest -- which is what makes a two-file
    # edit fail. A legitimate change to either wrapper is meant to break this and be re-verified.
    _ARGV_LINE = '\' "$repo" "$venv_python" "$harness" "$@"'
    _EXEC_LINE = 'os.execve(python, [python, "-I", harness, *sys.argv[4:]],'
    _PYTHON_LINE = 'venv_python="$repo/.venv/bin/python"'
    _SHEBANG = "#!/usr/bin/env bash"
    # sha256 of `probe-with-vaulted-key.sh` from its `set -euo pipefail` line down, over the RAW
    # BYTES, read from the tree on 2026-09-04.
    #
    # This pin drops NOTHING, on purpose. There are two options and no third: a raw digest cannot be
    # blind but reddens on a comment edit; a canonicalised one survives comment edits and is blind in
    # exactly what it drops. The pressure this one will feel is deletion -- "it trips on a comment".
    # If canonicalisation is ever added to relieve that, strip ONLY above the anchor and leave the
    # quoted interpreter payload byte for byte: in that region a `#` is data and an apostrophe ends
    # the string, so the dropping rule earns the same adversarial read as the guard it serves.
    _PROBE_BODY_SHA256 = "7b4e19d8a370ea794167b2f86f73ea1f45cc9cc63d792cb839747bacfac7ad8c"

    def _src(self, name: str) -> str:
        return (_REPO / "infra" / "scripts" / name).read_text()

    def _body_bytes(self, name: str) -> bytes:
        """The body from the anchor line down, as BYTES.

        Bytes rather than decoded text because `read_text()` decodes with universal newlines: a CRLF
        rewrite of the whole file decodes to the same string and hashes identically -- measured, not
        assumed. A digest that cannot see a line-ending rewrite is not pinning the bytes it claims.
        """
        raw = (_REPO / "infra" / "scripts" / name).read_bytes()
        return raw[raw.index(b"\nset -euo pipefail\n") + 1 :]

    def _body(self, name: str) -> list[str]:
        """Everything from the `set -euo pipefail` LINE down.

        Anchored on the whole line, not on the text: this wrapper's own header quotes the phrase
        while describing the identity below it, and a substring search lands there instead.
        """
        lines = self._src(name).split("\n")
        start = lines.index("set -euo pipefail")
        return lines[start:]

    @pytest.mark.parametrize("name", WRAPPERS)
    def test_the_target_is_assigned_exactly_once_from_a_literal(self, name: str) -> None:
        assignments = re.findall(r"^\s*harness=(.*)$", self._src(name), re.MULTILINE)
        assert len(assignments) == 1, f"{name} assigns its target {len(assignments)} times"
        # `[^"$]+` excluded `$` but not a backtick or `..` -- `\`printenv X\`.py` and a traversal
        # both passed. The target is a plain filename in one known directory; spell that.
        assert re.fullmatch(r'"\$repo/infra/scripts/[A-Za-z0-9_-]+\.py"', assignments[0]), assignments[0]

    @pytest.mark.parametrize("name", WRAPPERS)
    def test_nothing_but_those_literals_routes_the_target_to_the_child(self, name: str) -> None:
        """Both halves of what gets exec'd: the interpreter and the program it is handed."""
        src = self._src(name)
        for line in (self._ARGV_LINE, self._EXEC_LINE, self._PYTHON_LINE):
            assert src.count(line) == 1, f"{name} does not carry {line!r} exactly once"

    @pytest.mark.parametrize("name", WRAPPERS)
    def test_both_interpreters_are_isolated(self, name: str) -> None:
        """`-I` on BOTH, or the cwd leads `sys.path` and `PYTHONINSPECT` keeps the credential in a
        prompt. A flag missing from either invocation reopens those routes and says nothing."""
        src = self._src(name)
        assert src.count('exec "$venv_python" -I -c') == 1, f"{name}: the -c invocation is not -I"
        assert src.count('[python, "-I", harness') == 1, f"{name}: the execve argv is not -I"

    @pytest.mark.parametrize("name", WRAPPERS)
    def test_nothing_executable_sits_above_the_anchor(self, name: str) -> None:
        """`_body` starts at `set -euo pipefail`, so anything above it is invisible to every other
        assertion here -- and a shell function named `exec` declared there shadows the builtin."""
        lines = self._src(name).split("\n")
        above = lines[: lines.index("set -euo pipefail")]
        # The shebang EXECUTES and is also a `#` line, so a comment-and-blank filter waves it
        # through -- which is a hole, not a detail: `#!/usr/bin/env -S BASH_ENV=... bash` makes bash
        # source a file before line 1, and a function named `exec` defined there shadows the builtin
        # and receives this script's whole command line. Pinned verbatim rather than filtered.
        assert lines[0] == self._SHEBANG, lines[0]
        offenders = [ln for ln in above[1:] if ln.strip() and not ln.lstrip().startswith("#")]
        assert offenders == [], offenders

    def test_the_sibling_body_is_the_one_this_was_copied_from(self) -> None:
        """The transitive pin. Without it, a selector added to BOTH wrappers keeps them identical
        and every other assertion here stays green -- which is how a two-file edit would ship."""
        import hashlib

        digest = hashlib.sha256(self._body_bytes("probe-with-vaulted-key.sh")).hexdigest()
        assert digest == self._PROBE_BODY_SHA256, (
            "the sibling wrapper's body changed. Recompute with\n"
            "  sed -n '/^set -euo pipefail$/,$p' infra/scripts/probe-with-vaulted-key.sh | sha256sum\n"
            "and READ THE BODY DIFF before touching the constant: this pin exists so an edit to that "
            "file cannot ride into this one unseen, and updating the hex without reading the diff is "
            "the one way to defeat it."
        )

    def test_the_two_wrappers_differ_in_exactly_one_line_below_the_shebang_block(self) -> None:
        """The identity claim in the header, as an assertion. It is also what closes the selector
        forms a per-line regex misses: any added override is a second differing line."""
        mint, probe = (self._body(n) for n in self.WRAPPERS)
        assert len(mint) == len(probe), "the two wrapper bodies differ in length"
        differing = [(a, b) for a, b in zip(mint, probe, strict=True) if a != b]
        assert len(differing) == 1, differing
        assert differing[0][0].startswith("harness="), differing[0]

    @pytest.mark.parametrize("name", WRAPPERS)
    def test_the_target_exists(self, name: str) -> None:
        target = re.search(r'^harness="\$repo/(.*)"$', self._src(name), re.MULTILINE)
        assert target, f"{name}'s target is not the expected literal shape"
        assert (_REPO / target.group(1)).is_file(), target.group(1)

    def test_the_two_wrappers_do_not_point_at_the_same_program(self) -> None:
        """Two fixed targets is the design; two wrappers onto one program is a copy nobody needs."""
        targets = {re.search(r"^harness=(.*)$", self._src(n), re.MULTILINE).group(1) for n in self.WRAPPERS}
        assert len(targets) == 2, targets

    def test_this_scripts_refusal_names_the_wrapper_that_can_run_it(self, monkeypatch) -> None:
        """The refusal named the sibling, whose target is a different program -- so the operator was
        sent to a wrapper that cannot run this script, at the one moment they need it to."""
        for var in (mint.API_KEY_VAR, mint.API_SECRET_VAR):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(mint.Refusal) as exc:
            mint.require_credentials()
        assert "mint-with-vaulted-key.sh" in str(exc.value)


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

    def __init__(self, *, positions=(), balances=(), orders=()) -> None:
        self.calls: list[str] = []
        self.submitted: list[dict] = []
        self.cached: list[object] = []
        self.read_kwargs: dict[str, dict] = {}
        self._positions = tuple(positions)
        self._balances = tuple(balances)
        self._orders = tuple(orders)

    async def request_instruments(self, pairs=None):
        self.calls.append("request_instruments")
        return [_Instrument()]

    async def request_book_snapshot(self, instrument_id, depth=1):
        self.calls.append("request_book_snapshot")
        return _Book()

    async def request_order_status_reports(self, account, **kw):
        """`open_only` is a MODE here too, and answering the same in both is how the position read
        hid its own defect. Without it the venue also returns CLOSED orders -- the previous pass's
        cancelled FIXMINT rows -- and the resting guard would skip its leg on every later run."""
        self.calls.append("request_order_status_reports")
        self.read_kwargs["orders"] = kw
        if kw.get("open_only") is not True:
            # On the MINT pair, so the leftover can actually produce the skip: a closed row on some
            # other pair fails the kwarg assertion but never reaches the guard it is meant to fool.
            return [*self._orders, _Order("SOL/EUR.KRAKEN")]
        return list(self._orders)

    async def request_position_status_reports(self, account, **kw):
        """Answers what the venue answers, which is NOT the same in every mode.

        The client's own docstring: margin mode calls `OpenPositions`; cash mode with spot reports
        off "returns an empty vector". A stub that returned the positions whatever it was asked
        would let a script reading in the wrong mode pass here and re-mint a leveraged position on
        every run at the venue -- the defect this reproduces rather than hides.
        """
        self.calls.append("request_position_status_reports")
        self.read_kwargs["positions"] = kw
        if kw.get("account_type") is not AccountType.MARGIN:
            return []
        return list(self._positions)

    async def request_account_state(self, account, **kw):
        self.calls.append("request_account_state")
        self.read_kwargs["state"] = kw
        return _AccountReport(self._balances)

    def cache_instrument(self, instrument) -> None:
        self.calls.append("cache_instrument")
        self.cached.append(instrument)

    async def submit_order(self, **kwargs):
        self.calls.append("submit_order")
        self.submitted.append(kwargs)


class _Instrument:
    """The adapter's instrument object as this script uses it: cached, and never read for a size.

    Every field is None as a TRIPWIRE, not as a recording. What the adapter actually returns for
    SOL/EUR, measured on the pinned wheel over a loopback server fed this repo's own AssetPairs
    fixture, is `min_quantity=Quantity(0.06)` and `min_notional=None` -- it fills the quantity floor
    correctly and never maps `costmin` at all. Nulling all four here means any sizing path that
    reached back into the object raises on `float(None)` instead of freezing a floor to zero.
    """

    id = "SOL/EUR.KRAKEN"
    min_quantity = None
    min_notional = None
    size_increment = None
    price_increment = None


class _Currency:
    def __init__(self, code: str) -> None:
        self.code = code


class _Balance:
    """A balance row shaped as the venue's is: the code is a level down, under `currency.code`."""

    def __init__(self, code: str, free: float) -> None:
        self.currency = _Currency(code)
        self.free = free


class _Position:
    def __init__(self, instrument_id: str = "SOL/EUR.KRAKEN") -> None:
        self.instrument_id = instrument_id


class _Order:
    def __init__(self, instrument_id: str = "SOL/EUR.KRAKEN") -> None:
        self.instrument_id = instrument_id


class _Level:
    price = 85.76


class _Book:
    def bids(self):
        return [_Level()]


class _AccountReport:
    def __init__(self, balances=()) -> None:
        self.balances = tuple(balances)


def _args(execute: bool):
    import argparse

    return argparse.Namespace(pair="SOL/EUR", execute=execute)


async def _answer_none(*_args, **_kwargs):
    """A read that answers nothing at all -- distinct from one that answers an empty list."""
    return None


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


class TestTheAccountIsReadTheWayFlattenReadsIt:
    """A read made in a different MODE than the reader this mints for answers a different question.

    Each of these fails in the same expensive direction -- an ingredient re-minted on every run,
    or one skipped so the attended pass has nothing to exercise -- and each is invisible from the
    output, because "nothing there" is what a flat account looks like too.
    """

    def _state(self, rec) -> object:
        import asyncio

        return asyncio.run(mint.read_account(rec, "SOL/EUR", _LIMITS, _BEST_BID))

    def test_positions_are_requested_in_margin_mode(self) -> None:
        """The client returns an empty vector in the cash default, whatever the account holds."""
        rec = _Recorder()
        self._state(rec)
        assert rec.read_kwargs["positions"]["account_type"] is AccountType.MARGIN
        assert rec.read_kwargs["positions"]["use_spot_position_reports"] is False

    def test_orders_are_requested_open_only(self) -> None:
        rec = _Recorder()
        self._state(rec)
        assert rec.read_kwargs["orders"] == {"open_only": True}

    def test_a_closed_leftover_would_skip_the_resting_leg(self) -> None:
        """The money-shaped consequence, not just the kwarg. Read without `open_only` the venue also
        returns the previous pass's cancelled FIXMINT rows, and the plan then silently drops the one
        leg the pass most needs -- indistinguishable, in the printed plan, from a real resting order.
        """
        import asyncio

        # Driven through `read_account`, not by calling the stub: a test that calls the stub proves
        # what the stub does. `_Blind` is the defect itself -- a client that drops `open_only`.
        class _Blind(_Recorder):
            async def request_order_status_reports(self, account, **kw):
                return await super().request_order_status_reports(account)

        state = asyncio.run(mint.read_account(_Blind(), "SOL/EUR", _LIMITS, _BEST_BID))
        assert state.resting_pairs == ("SOL/EUR",)
        kinds = [leg.kind for leg in mint.plan_legs(pair="SOL/EUR", limits=_LIMITS, best_bid=_BEST_BID, existing=state)]
        assert "resting" not in kinds

    def test_an_existing_resting_order_is_actually_SEEN(self) -> None:
        """The resting guard's own positive trace: until now it had only plan-level ones, so the
        projection from an order row to a pair was never exercised against a row that exists."""
        rec = _Recorder(orders=[_Order()])
        assert self._state(rec).resting_pairs == ("SOL/EUR",)

    def test_an_existing_margin_position_is_actually_SEEN(self) -> None:
        """The guard proven on a position that exists, not on an empty list that proves nothing."""
        rec = _Recorder(positions=[_Position()])
        assert self._state(rec).position_pairs == ("SOL/EUR",)

    def test_the_balances_read_names_its_mode(self) -> None:
        """Pinned like its two neighbours. The mode does not change what `balances` returns, so this
        guards the like-for-like with flatten rather than a behaviour -- but an unpinned kwarg is
        how the position read's defect survived, and the claim that all three match must be true."""
        rec = _Recorder()
        self._state(rec)
        assert rec.read_kwargs["state"] == {"account_type": AccountType.CASH}

    def test_the_quote_currency_is_flattens(self) -> None:
        from cli.engine.flatten import QUOTE_CURRENCY

        rec = _Recorder()
        self._state(rec)
        assert rec.read_kwargs["positions"]["quote_currency"] == QUOTE_CURRENCY

    def test_a_balance_below_ordermin_does_not_satisfy_the_spot_leg(self) -> None:
        """A residual from a partial fill is not a sellable balance; flatten drops it and the venue
        refuses it, so counting it would skip the spot leg forever."""
        rec = _Recorder(balances=[_Balance("SOL", _LIMITS.ordermin / 2)])
        assert self._state(rec).non_eur_assets == ()

    def test_a_balance_at_ordermin_does_satisfy_it(self) -> None:
        """The true positive beside it -- a guard that never counts anything skips nothing."""
        rec = _Recorder(balances=[_Balance("SOL", _LIMITS.ordermin)])
        assert self._state(rec).non_eur_assets == ("SOL",)

    def test_a_zero_balance_on_another_asset_is_not_reported_as_held(self) -> None:
        """The venue lists an asset the account no longer holds; printing it as held is the mirror
        of judging every row by this pair's floors."""
        rec = _Recorder(balances=[_Balance("XXBT", 0.0)])
        assert self._state(rec).non_eur_assets == ()

    def test_a_foreign_asset_held_in_size_is_reported_whatever_this_pairs_floors_say(self) -> None:
        """The true positive: 0.01 BTC is under SOL's `ordermin`, and the plan header is also how
        the operator reads the account. Judging it by this pair's floors is what printed `(none)`."""
        rec = _Recorder(balances=[_Balance("XXBT", 0.01)])
        assert self._state(rec).non_eur_assets == ("XXBT",)

    def test_a_balance_whose_notional_misses_costmin_does_not_satisfy_it(self) -> None:
        """`flatten` classifies that balance `dust` and does not sell it, so counting it here would
        leave the sell path a balance the command declines to touch. Quantity alone is not enough."""
        import asyncio

        limits = mint.PairLimits(ordermin=1.0, costmin=20.0, lot_step=0.001, price_step=0.0001)
        rec = _Recorder(balances=[_Balance("SOL", 1.5)])
        state = asyncio.run(mint.read_account(rec, "SOL/EUR", limits, best_bid=2.0))
        assert 1.5 >= limits.ordermin and 1.5 * 2.0 < limits.costmin
        assert state.non_eur_assets == ()

    def test_the_venues_own_spelling_of_an_asset_is_resolved(self) -> None:
        """`XXDG` is how the venue spells DOGE; compared raw it never equals the pair's base."""
        import asyncio

        rec = _Recorder(balances=[_Balance("XXDG", 1000.0)])
        state = asyncio.run(mint.read_account(rec, "DOGE/EUR", _LIMITS, _BEST_BID))
        assert state.non_eur_assets == ("DOGE",)

    def test_eur_never_counts_as_the_non_eur_balance(self) -> None:
        rec = _Recorder(balances=[_Balance("ZEUR", 5000.0)])
        assert self._state(rec).non_eur_assets == ()

    @pytest.mark.parametrize(
        ("method", "what"),
        [
            ("request_order_status_reports", "open orders"),
            ("request_position_status_reports", "positions"),
            ("request_account_state", "the account state"),
        ],
    )
    def test_a_read_that_answers_nothing_refuses_rather_than_reading_as_flat(self, method: str, what: str) -> None:
        """`None` is not an empty account. Read as one it re-mints the leg on every run, and for the
        margin leg that is another leveraged position each time -- while the plan prints `(none)`."""
        import asyncio

        rec = _Recorder()
        setattr(rec, method, _answer_none)
        with pytest.raises(mint.Refusal) as exc:
            asyncio.run(mint.read_account(rec, "SOL/EUR", _LIMITS, _BEST_BID))
        assert what in str(exc.value)

    def test_the_instrument_is_cached_before_the_account_is_read(self, _creds) -> None:
        """The order-report read resolves rows through the cache and drops what it cannot resolve
        while returning success, so a cold cache would empty this guard rather than fail it."""
        import asyncio

        rec = _Recorder()
        asyncio.run(mint._run(_args(execute=False), **_factories(rec)))
        assert rec.calls.index("cache_instrument") < rec.calls.index("request_order_status_reports")


class TestWhatIsSentIsWhatWasPlanned:
    """The plan the operator approves and the orders that go out must be the same set.

    Nothing asserted this before: a `submit` that dropped `leverage`, swapped the side, or sent
    every leg as MARGIN passed the whole suite, because the tests only ever counted the submissions.
    """

    def _sent(self):
        import asyncio

        rec = _Recorder()
        legs = mint.plan_legs(pair="SOL/EUR", limits=_LIMITS, best_bid=_BEST_BID, existing=mint.AccountState())
        asyncio.run(mint._run(_args(execute=True), **_factories(rec), prompt=lambda _m: mint.CONFIRM_WORD))
        return legs, rec.submitted

    @pytest.fixture(autouse=True)
    def _tty(self, monkeypatch, _creds):
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    def test_every_planned_leg_is_sent_with_the_numbers_it_was_planned_with(self) -> None:
        legs, sent = self._sent()
        assert len(sent) == len(legs)
        for leg, kw in zip(legs, sent, strict=True):
            assert float(kw["quantity"]) == leg.quantity, leg.kind
            assert (None if kw["price"] is None else float(kw["price"])) == leg.price, leg.kind
            assert str(kw["instrument_id"]) == mint.INSTRUMENT_IDS[leg.pair], leg.kind

    def test_leverage_and_account_type_reach_the_venue_as_planned(self) -> None:
        """The margin leg is the only one carrying either; a spot leg that did is a position
        nobody planned, and this is the assertion that watches the wire rather than the plan."""
        legs, sent = self._sent()
        for leg, kw in zip(legs, sent, strict=True):
            assert kw["leverage"] == leg.leverage, leg.kind
            expected = AccountType.MARGIN if leg.account_type == "MARGIN" else AccountType.CASH
            assert kw["account_type"] is expected, leg.kind

    def test_side_type_and_time_in_force_reach_the_venue_as_planned(self) -> None:
        legs, sent = self._sent()
        for leg, kw in zip(legs, sent, strict=True):
            assert kw["order_side"] is (OrderSide.BUY if leg.side == "BUY" else OrderSide.SELL)
            assert kw["order_type"] is (OrderType.LIMIT if leg.order_type == "LIMIT" else OrderType.MARKET)
            assert kw["time_in_force"] is getattr(TimeInForce, leg.time_in_force), leg.kind


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
