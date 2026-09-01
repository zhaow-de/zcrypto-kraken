from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cli.engine import probeplan
from cli.engine.probeplan import PLAN_TTL, ProbePlanError, parse_plan, plan_refusals

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


def _intent(**overrides) -> dict:
    intent = {"symbol": "BTC/EUR", "side": "buy", "action": "open", "mode": "execute", "notional_eur": 50.0}
    intent.update(overrides)
    return intent


def _doc(*, intents=None, **overrides) -> dict:
    doc = {
        "plan_id": "p-0001",
        "created_at": NOW.isoformat(),
        "intents": intents if intents is not None else [_intent()],
    }
    doc.update(overrides)
    return doc


def _text(**overrides) -> str:
    return json.dumps(_doc(**overrides))


def _plan(**overrides):
    return parse_plan(_text(**overrides))


# ---- parse_plan: one refusal per shape rule, each flipping alone -------------------------------


def test_parse_plan_rejects_non_json():
    with pytest.raises(ProbePlanError, match="not valid JSON"):
        parse_plan("{not json")


def test_parse_plan_rejects_a_non_object_top_level():
    with pytest.raises(ProbePlanError, match="must be a JSON object"):
        parse_plan("[]")


def test_parse_plan_rejects_an_unknown_top_level_key():
    doc = _doc()
    doc["extra"] = "nope"
    with pytest.raises(ProbePlanError, match="unknown key"):
        parse_plan(json.dumps(doc))


def test_parse_plan_rejects_missing_plan_id():
    doc = _doc()
    del doc["plan_id"]
    with pytest.raises(ProbePlanError, match="plan_id must be a non-empty string"):
        parse_plan(json.dumps(doc))


def test_parse_plan_rejects_non_string_plan_id():
    with pytest.raises(ProbePlanError, match="plan_id must be a non-empty string"):
        parse_plan(_text(plan_id=123))


def test_parse_plan_rejects_a_whitespace_plan_id():
    with pytest.raises(ProbePlanError, match="plan_id must be a non-empty string"):
        parse_plan(_text(plan_id="   "))


def test_parse_plan_rejects_missing_created_at():
    doc = _doc()
    del doc["created_at"]
    with pytest.raises(ProbePlanError, match="created_at must be a string"):
        parse_plan(json.dumps(doc))


def test_parse_plan_rejects_non_string_created_at():
    with pytest.raises(ProbePlanError, match="created_at must be a string"):
        parse_plan(_text(created_at=123))


def test_parse_plan_rejects_unparseable_created_at():
    with pytest.raises(ProbePlanError, match="not a valid ISO datetime"):
        parse_plan(_text(created_at="not-a-date"))


def test_parse_plan_rejects_naive_created_at():
    with pytest.raises(ProbePlanError, match="must be timezone-aware"):
        parse_plan(_text(created_at="2026-08-18T12:00:00"))


def test_parse_plan_rejects_missing_intents():
    doc = _doc()
    del doc["intents"]
    with pytest.raises(ProbePlanError, match="intents must be a non-empty list"):
        parse_plan(json.dumps(doc))


def test_parse_plan_rejects_empty_intents():
    with pytest.raises(ProbePlanError, match="intents must be a non-empty list"):
        parse_plan(_text(intents=[]))


def test_parse_plan_rejects_non_list_intents():
    with pytest.raises(ProbePlanError, match="intents must be a non-empty list"):
        parse_plan(_text(intents="oops"))


def test_parse_plan_rejects_a_non_object_intent():
    with pytest.raises(ProbePlanError, match="must be an object"):
        parse_plan(_text(intents=[42]))


def test_parse_plan_rejects_an_unknown_intent_key():
    # The exact typo a reviewer named: "levarage" would otherwise parse cleanly as a SPOT intent,
    # silently dropping the operator's intended leverage instead of refusing.
    intent = _intent()
    intent["levarage"] = 3
    with pytest.raises(ProbePlanError, match="unknown key"):
        parse_plan(_text(intents=[intent]))


def test_parse_plan_rejects_symbol_not_in_basket():
    with pytest.raises(ProbePlanError, match="not in the basket"):
        parse_plan(_text(intents=[_intent(symbol="DOGE/BTC")]))


def test_parse_plan_rejects_invalid_side():
    with pytest.raises(ProbePlanError, match="side must be one of"):
        parse_plan(_text(intents=[_intent(side="long")]))


def test_parse_plan_rejects_invalid_action():
    with pytest.raises(ProbePlanError, match="action must be one of"):
        parse_plan(_text(intents=[_intent(action="hold")]))


def test_parse_plan_rejects_invalid_mode():
    with pytest.raises(ProbePlanError, match="mode must be one of"):
        parse_plan(_text(intents=[_intent(mode="cancel")]))


def test_parse_plan_rejects_both_notional_and_qty():
    with pytest.raises(ProbePlanError, match="exactly one of notional_eur/qty"):
        parse_plan(_text(intents=[_intent(qty=0.01)]))  # the base intent already carries notional_eur


def test_parse_plan_rejects_neither_notional_nor_qty():
    intent = _intent()
    del intent["notional_eur"]
    with pytest.raises(ProbePlanError, match="exactly one of notional_eur/qty"):
        parse_plan(_text(intents=[intent]))


def test_parse_plan_rejects_non_finite_notional():
    with pytest.raises(ProbePlanError, match="finite positive number"):
        parse_plan(_text(intents=[_intent(notional_eur=float("inf"))]))


def test_parse_plan_rejects_non_positive_notional():
    with pytest.raises(ProbePlanError, match="finite positive number"):
        parse_plan(_text(intents=[_intent(notional_eur=0.0)]))


def test_parse_plan_rejects_a_bool_notional():
    # bool is a subclass of int/float — True must not silently become 1.0 EUR.
    with pytest.raises(ProbePlanError, match="must be a number"):
        parse_plan(_text(intents=[_intent(notional_eur=True)]))


def test_parse_plan_rejects_qty_with_action_open():
    intent = _intent()  # action defaults to "open"
    del intent["notional_eur"]
    intent["qty"] = 0.01
    with pytest.raises(ProbePlanError, match="qty requires action == 'close'"):
        parse_plan(_text(intents=[intent]))


def test_parse_plan_rejects_qty_with_leverage():
    intent = _intent(action="close")
    del intent["notional_eur"]
    intent["qty"] = 0.01
    intent["leverage"] = 2
    with pytest.raises(ProbePlanError, match="qty requires action == 'close' and no leverage"):
        parse_plan(_text(intents=[intent]))


def test_parse_plan_rejects_leverage_out_of_range():
    with pytest.raises(ProbePlanError, match=r"leverage must be an int in \[2, 10\]"):
        parse_plan(_text(intents=[_intent(leverage=11)]))


def test_parse_plan_rejects_non_int_leverage():
    with pytest.raises(ProbePlanError, match=r"leverage must be an int in \[2, 10\]"):
        parse_plan(_text(intents=[_intent(leverage="2")]))


def test_parse_plan_accepts_a_valid_plan():
    plan = parse_plan(_text())
    assert plan.plan_id == "p-0001"
    assert plan.created_at == NOW
    assert len(plan.intents) == 1
    assert plan.intents[0].notional_eur == 50.0
    assert plan.intents[0].qty is None
    assert plan.intents[0].leverage is None
    assert plan.raw["plan_id"] == "p-0001"


def test_parse_plan_accepts_a_valid_qty_close_intent():
    intent = _intent(action="close", side="sell")
    del intent["notional_eur"]
    intent["qty"] = 0.01
    plan = parse_plan(_text(intents=[intent]))
    assert plan.intents[0].qty == 0.01
    assert plan.intents[0].notional_eur is None
    assert plan.intents[0].leverage is None


def test_parse_plan_accepts_a_valid_margin_intent():
    plan = parse_plan(_text(intents=[_intent(leverage=2)]))
    assert plan.intents[0].leverage == 2


# ---- rest-hold: the vocabulary, the two fields, and their refusals -----------------------------


def test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed():
    """Every mode name is a branch in the executor. A mode added here and nowhere else runs with
    `execute` semantics -- joining the touch and crossing the spread at the time box -- so the
    vocabulary is pinned and widening it is a deliberate, reviewed edit."""
    assert probeplan.MODES == frozenset({"execute", "rest-cancel", "rest-hold"})


def _rest_hold_intent() -> dict:
    return {
        "symbol": "BTC/EUR",
        "side": "buy",
        "action": "open",
        "mode": "rest-hold",
        "notional_eur": 20.0,
        "offset_pct": 5.0,
        "hold_minutes": 45,
    }


def test_a_rest_hold_intent_without_both_fields_is_refused():
    """The two fields are what distinguish this mode; an intent missing either has no price and no
    duration, and there is no default that would be safe to invent for a live order."""
    for missing in ("offset_pct", "hold_minutes"):
        raw = _rest_hold_intent()
        del raw[missing]
        with pytest.raises(probeplan.ProbePlanError, match="rest-hold"):
            probeplan._parse_intent(raw)


def test_the_two_fields_are_refused_on_every_other_mode():
    """A hold on an `execute` intent reads as a request the executor will silently ignore. Each
    field alone is that same request: an intent carrying only `offset_pct` is what an `or` turned
    into an `and` lets through, so the halves are refused separately as well as together."""
    for mode in ("execute", "rest-cancel"):
        for dropped in ((), ("offset_pct",), ("hold_minutes",)):
            raw = _rest_hold_intent() | {"mode": mode}
            for key in dropped:
                del raw[key]
            with pytest.raises(probeplan.ProbePlanError, match="only on mode 'rest-hold'"):
                probeplan._parse_intent(raw)


@pytest.mark.parametrize("hold", [0, -1, 61, 600])
def test_a_hold_outside_the_cap_is_refused(hold):
    """The cap is what keeps a plan from resting an order indefinitely -- the one bound on this
    mode that does not depend on anything else in the system still working."""
    with pytest.raises(probeplan.ProbePlanError, match="hold_minutes"):
        probeplan._parse_intent(_rest_hold_intent() | {"hold_minutes": hold})


@pytest.mark.parametrize("offset", [0, -1.0])
def test_a_non_positive_offset_is_refused(offset):
    """Zero or negative prices the order at or through the touch, which the post-only submission
    path rejects -- and which would make a mode built never to fill, fill."""
    with pytest.raises(probeplan.ProbePlanError, match="offset_pct"):
        probeplan._parse_intent(_rest_hold_intent() | {"offset_pct": offset})


def test_a_rest_hold_close_is_refused():
    """No drill needs a resting close, and a resting reduce-only order is a different animal that
    should be specified when something wants it."""
    with pytest.raises(probeplan.ProbePlanError, match="action"):
        probeplan._parse_intent(_rest_hold_intent() | {"action": "close"})


def test_a_well_formed_rest_hold_intent_parses():
    """The true positive: without it, a refusal-only suite is satisfied by a parser that refuses
    everything."""
    intent = probeplan._parse_intent(_rest_hold_intent())
    assert (intent.mode, intent.offset_pct, intent.hold_minutes) == ("rest-hold", 5.0, 45)


# ---- plan_refusals -------------------------------------------------------------------------


def test_plan_refusals_an_expired_plan_refuses():
    created_at = NOW - PLAN_TTL - timedelta(minutes=1)
    plan = _plan(created_at=created_at.isoformat())
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == (f"plan expired: created_at {created_at.isoformat()} is over 60 minutes old",)


def test_plan_refusals_age_exactly_at_the_ttl_passes():
    # Strict '>' -- age == PLAN_TTL exactly must NOT refuse.
    created_at = NOW - PLAN_TTL
    plan = _plan(created_at=created_at.isoformat())
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == ()


def test_plan_refusals_a_future_created_at_refuses():
    created_at = NOW + timedelta(minutes=5)
    plan = _plan(created_at=created_at.isoformat())
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == ("created_at is in the future",)


def test_plan_refusals_a_ledgered_plan_id_refuses():
    plan = _plan(plan_id="p-dup")
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset({"p-dup"}), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == ("plan_id already ledgered",)


def test_plan_refusals_over_cap_notional_refuses():
    plan = _plan(intents=[_intent(notional_eur=120.0)])
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == ("plan notional 120.00 EUR exceeds the cap 100.00 EUR",)


def test_plan_refusals_notional_exactly_at_the_cap_passes():
    # Strict '>' -- the boundary itself must NOT refuse, or a future '>' -> '>=' regression is
    # invisible.
    plan = _plan(intents=[_intent(notional_eur=100.0)])
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == ()


def test_plan_refusals_a_nan_cap_refuses():
    # nan defeats "total > nan" (always False) -- must be refused explicitly, not silently pass.
    plan = _plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=float("nan"), free_zeur=1000.0)
    assert reasons == ("max_plan_notional_eur is not finite: nan",)


def test_plan_refusals_an_inf_cap_refuses():
    # inf defeats "total > inf" (always False) -- disables the blast-radius bound entirely.
    plan = _plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=float("inf"), free_zeur=1000.0)
    assert reasons == ("max_plan_notional_eur is not finite: inf",)


def _margin_plan():
    intents = [_intent(notional_eur=30.0, leverage=2), _intent(notional_eur=30.0, leverage=2)]
    return _plan(intents=intents)


def test_plan_refusals_margin_floor_passes_at_free_zeur_100():
    # sum(notional/leverage) = 15 + 15 = 30; 30 x 2.5 = 75 <= 100.
    plan = _margin_plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=100.0)
    assert reasons == ()


def test_plan_refusals_margin_floor_refuses_at_free_zeur_50():
    # Same plan as above; 75 > 50 refuses.
    plan = _margin_plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=50.0)
    assert reasons == ("margin floor: 75.00 EUR required exceeds free_zeur 50.00 EUR",)


def test_plan_refusals_margin_required_exactly_at_free_zeur_passes():
    # Same plan as above (margin_required == 75.0 exactly); the boundary itself must NOT refuse.
    plan = _margin_plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=75.0)
    assert reasons == ()


def test_plan_refusals_a_nan_free_zeur_refuses():
    # The executor passes free_zeur from a live venue balance -- validate at the point of use, not
    # only at config-parse time. nan defeats "required > nan" (always False).
    plan = _plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=float("nan"))
    assert reasons == ("free_zeur is not finite: nan",)


def test_plan_refusals_an_inf_free_zeur_refuses():
    plan = _plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=float("inf"))
    assert reasons == ("free_zeur is not finite: inf",)


def test_plan_refusals_a_valid_plan_returns_empty():
    plan = _plan()
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == ()


def test_plan_refusals_multi_condition_returns_both_reasons_in_declaration_order():
    created_at = NOW - PLAN_TTL - timedelta(minutes=1)
    plan = _plan(created_at=created_at.isoformat(), intents=[_intent(notional_eur=120.0)])
    reasons = plan_refusals(plan, now=NOW, ledgered=frozenset(), max_plan_notional_eur=100.0, free_zeur=1000.0)
    assert reasons == (
        f"plan expired: created_at {created_at.isoformat()} is over 60 minutes old",
        "plan notional 120.00 EUR exceeds the cap 100.00 EUR",
    )
