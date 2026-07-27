"""The recovery ladder wired into the daemon (spec 00072, T0008).

`tests/test_desync_recovery_ladder.py` covers the decision arithmetic. This covers the seam: that
the daemon tells the ladder when a pair desyncs and recovers, that the periodic loop turns the
ladder's decisions into real client calls, and that rung 3 actually forces a reconnect.

The loop is time-driven, not message-driven, and that is deliberate: a grace period keyed on
incoming messages would depend on the stuck pair still receiving traffic, and would re-evaluate
hundreds of times per second at depth-100 rather than once per tick.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from cli.capture.command import _desync_recovery_loop
from cli.capture.desync_recovery import Action, DesyncRecovery

T0 = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)


class _FakeClient:
    def __init__(self) -> None:
        self.resubscribed: list[str] = []
        self.reconnects = 0
        self.resubscribes_total = 0

    async def resubscribe_book(self, pair: str) -> None:
        self.resubscribed.append(pair)
        self.resubscribes_total += 1

    async def force_reconnect(self) -> None:
        self.reconnects += 1


class _FakeBook:
    def __init__(self, desynced: bool) -> None:
        self.desynced = desynced


async def _tick(ladder, client, books, *, at):
    """One iteration of the loop's body, with an injected clock."""
    await _desync_recovery_loop(client, books, ladder, interval=0, now_fn=lambda: at, once=True)


def test_a_still_desynced_pair_past_its_grace_gets_a_retry():
    asyncio.run(_test_a_still_desynced_pair_past_its_grace_gets_a_retry())


async def _test_a_still_desynced_pair_past_its_grace_gets_a_retry():
    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    await _tick(ladder, client, books, at=T0 + timedelta(seconds=25))
    assert client.resubscribed == ["BTC/EUR"], "the ladder decided RETRY but no resubscribe was sent"


def test_a_pair_inside_its_grace_is_left_alone():
    asyncio.run(_test_a_pair_inside_its_grace_is_left_alone())


async def _test_a_pair_inside_its_grace_is_left_alone():
    """Retrying inside the grace fires on a recovery still in flight — two resubscribes for one
    desync, walking toward the rate limit the transition guard exists to avoid."""
    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    await _tick(ladder, client, books, at=T0 + timedelta(seconds=5))
    assert client.resubscribed == []


def test_a_pair_that_recovered_is_dropped_from_the_ladder():
    asyncio.run(_test_a_pair_that_recovered_is_dropped_from_the_ladder())


async def _test_a_pair_that_recovered_is_dropped_from_the_ladder():
    """The loop reads live book state, so a pair that healed between ticks must not be retried —
    the ladder's own record would otherwise outlive the fault."""
    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    books["BTC/EUR"].desynced = False
    await _tick(ladder, client, books, at=T0 + timedelta(seconds=25))
    assert client.resubscribed == []
    assert ladder.due("BTC/EUR", at=T0 + timedelta(seconds=999)) is Action.NONE


def test_the_last_rung_forces_a_reconnect_not_another_resubscribe():
    asyncio.run(_test_the_last_rung_forces_a_reconnect_not_another_resubscribe())


async def _test_the_last_rung_forces_a_reconnect_not_another_resubscribe():
    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    now = T0
    for _ in range(40):
        now += timedelta(seconds=5)
        await _tick(ladder, client, books, at=now)
        if client.reconnects:
            break
    assert client.reconnects == 1, f"expected exactly one escalation, got {client.reconnects}"
    assert len(client.resubscribed) == 3, f"expected 3 bounded retries before escalating, got {client.resubscribed}"


def test_it_never_escalates_twice_for_the_same_episode():
    asyncio.run(_test_it_never_escalates_twice_for_the_same_episode())


async def _test_it_never_escalates_twice_for_the_same_episode():
    """A reconnect drops all 12 pairs. Doing it repeatedly for a pair that has already proven a
    reconnect does not help is strictly worse than the stuck pair."""
    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    now = T0
    for _ in range(200):
        now += timedelta(seconds=10)
        await _tick(ladder, client, books, at=now)
    assert client.reconnects == 1, f"reconnect loop: escalated {client.reconnects} times"


def test_one_stuck_pair_does_not_stall_another_pairs_ladder():
    asyncio.run(_test_one_stuck_pair_does_not_stall_another_pairs_ladder())


async def _test_one_stuck_pair_does_not_stall_another_pairs_ladder():
    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _FakeBook(desynced=True), "ETH/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    ladder.note_desync("ETH/EUR", at=T0)
    await _tick(ladder, client, books, at=T0 + timedelta(seconds=25))
    assert sorted(client.resubscribed) == ["BTC/EUR", "ETH/EUR"]


def test_a_failing_client_call_does_not_kill_the_loop():
    asyncio.run(_test_a_failing_client_call_does_not_kill_the_loop())


async def _test_a_failing_client_call_does_not_kill_the_loop():
    """This loop runs as a bare asyncio task beside the consumer; an escaping exception would take
    the daemon's recovery down silently and permanently."""
    ladder = DesyncRecovery()

    class _Boom(_FakeClient):
        async def resubscribe_book(self, pair: str) -> None:
            raise OSError("kraken said no")

    client = _Boom()
    books = {"BTC/EUR": _FakeBook(desynced=True)}
    ladder.note_desync("BTC/EUR", at=T0)
    await _tick(ladder, client, books, at=T0 + timedelta(seconds=25))  # must not raise


def test_the_loop_is_registered_as_a_background_task():
    """A loop nobody starts is the T0100 defect in another costume."""
    src = (__import__("pathlib").Path(__file__).resolve().parents[1] / "cli/capture/command.py").read_text()
    assert "_desync_recovery_loop(" in src.split("async def _desync_recovery_loop", 1)[1], (
        "_desync_recovery_loop is defined but never scheduled"
    )


def test_the_drill_knob_is_inert_unless_explicitly_enabled():
    """The knob ships in the production image on purpose (spec 00072 D7) — the validated binary
    must BE the deployed binary. That is only acceptable if it cannot fire by accident: it reads a
    single env var, once, at import, and that var is set nowhere in the fleet."""
    from cli.capture import command

    assert command._DRILL_DESYNC_SECONDS == 0, "the drill knob is ENABLED in this environment"
    assert command._drill_maybe_fail("BTC/EUR", "book_snapshot", True, None, T0) is True
    assert command._drill_maybe_fail("BTC/EUR", "book_update", False, None, T0) is False


def test_the_drill_knob_is_absent_from_every_infra_config():
    """A knob inert in code but wired in a compose template would be armed in production."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "infra"
    hits = [
        str(p.relative_to(root.parent))
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix in {".j2", ".yaml", ".yml", ".env", ".sh"}
        and "ZCRYPTO_DRILL_FAIL_SNAPSHOTS" in p.read_text(errors="ignore")
    ]
    assert not hits, f"the drill knob is referenced in fleet config: {hits}"
