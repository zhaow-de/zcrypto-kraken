"""The seam between the daemon and the recovery ladder (spec 00072, T0008)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from cli.capture.command import _desync_recovery_loop
from cli.capture.desync_recovery import Action, DesyncRecovery

T0 = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)


class _FakeClient:
    def __init__(self, connected: bool = True) -> None:
        self.resubscribed: list[str] = []
        self.reconnects = 0
        self.resubscribes_total = 0
        self.connected = connected

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


def test_the_task_is_both_cancelled_and_awaited_at_shutdown():
    """`_run` carries the recovery task in every shutdown tuple it walks."""
    import inspect
    import re

    from cli.capture import command

    # A task awaited but never cancelled hangs `_run` on its own `while True`: SIGTERM never completes, the
    # container is SIGKILLed, and `writer.close()` never runs -- losing buffered rows on the unbackfillable
    # path. Cancelled but never awaited leaks it instead.
    tuples = re.findall(r"for task in \(([^)]*)\):", inspect.getsource(command._run))
    assert len(tuples) >= 2, f"expected a cancel loop and an await loop in _run, found {len(tuples)}"
    for i, members in enumerate(tuples):
        assert "desync" in members, f"shutdown tuple #{i} omits the desync-recovery task ({members.strip()})"


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
        and "ZCRYPTO_DRILL_DESYNC_SECONDS" in p.read_text(errors="ignore")
    ]
    assert not hits, f"the drill knob is referenced in fleet config: {hits}"


# --- The seam the mutation review found completely untested ---------------------------------------
# `recovery` has no default on `_consume`: dropping it is a TypeError, not a silent None. Covering a
# callee is not covering its caller, so `test_the_consumer_arms_the_ladder_it_was_given` drives
# `_consume` itself.


def _book_msg(pair: str) -> dict:
    return {"data": [{"symbol": pair}]}


class _StubBook:
    """Ingest outcome is scripted; `desynced` tracks it the way OrderBook does."""

    def __init__(self, results: list[bool]) -> None:
        self._results = list(results)
        self.desynced = False

    def _next(self) -> bool:
        ok = self._results.pop(0) if self._results else True
        self.desynced = not ok
        return ok

    def ingest_snapshot(self, entry) -> bool:
        return self._next()

    def ingest_update(self, entry) -> bool:
        return self._next()


def test_the_daemon_arms_the_ladder_when_a_pair_desyncs():
    asyncio.run(_test_the_daemon_arms_the_ladder_when_a_pair_desyncs())


async def _test_the_daemon_arms_the_ladder_when_a_pair_desyncs():
    from cli.capture.command import _handle_book_message

    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _StubBook([False])}
    monitor, watermark = _StubMonitor(), _StubWatermark()
    await _handle_book_message(_book_msg("BTC/EUR"), "book_update", client, books, {}, monitor, watermark, ladder, {})
    assert client.resubscribed == ["BTC/EUR"], "rung 1 did not fire"
    assert ladder.due("BTC/EUR", at=datetime.now(UTC) + timedelta(seconds=25)) is Action.RETRY, (
        "the daemon resubscribed but never told the ladder — it is armed by nothing"
    )


def test_the_daemon_disarms_the_ladder_when_a_pair_recovers():
    asyncio.run(_test_the_daemon_disarms_the_ladder_when_a_pair_recovers())


async def _test_the_daemon_disarms_the_ladder_when_a_pair_recovers():
    from cli.capture.command import _handle_book_message

    ladder, client = DesyncRecovery(), _FakeClient()
    books = {"BTC/EUR": _StubBook([False, True])}
    monitor, watermark = _StubMonitor(), _StubWatermark()
    msg = _book_msg("BTC/EUR")
    await _handle_book_message(msg, "book_update", client, books, {}, monitor, watermark, ladder, {})
    await _handle_book_message(msg, "book_update", client, books, {}, monitor, watermark, ladder, {})
    assert ladder.due("BTC/EUR", at=datetime.now(UTC) + timedelta(seconds=999)) is Action.NONE, (
        "the pair recovered but the ladder still holds it — its record outlives the fault"
    )


def test_the_consumer_arms_the_ladder_it_was_given():
    asyncio.run(_test_the_consumer_arms_the_ladder_it_was_given())


async def _test_the_consumer_arms_the_ladder_it_was_given():
    """The production call site, not just the handler it calls: `_consume` must pass the ladder it was
    given down to `_handle_book_message`, or the daemon resubscribes on the transition and nobody ever
    escalates.
    """
    from cli.capture.command import _consume

    class _ScriptedClient(_FakeClient):
        async def stream(self):
            for msg in ({"channel": "book", "type": "update", **_book_msg("BTC/EUR")},):
                yield msg

    ladder, client = DesyncRecovery(), _ScriptedClient()
    books = {"BTC/EUR": _StubBook([False])}
    await _consume(client, books, {}, {}, _StubMonitor(), _StubWatermark(), ladder, {}, {})

    assert client.resubscribed == ["BTC/EUR"], "the consumer never reached the desync branch"
    assert ladder.due("BTC/EUR", at=datetime.now(UTC) + timedelta(seconds=25)) is Action.RETRY, (
        "_consume resubscribed but did not hand its ladder down — the daemon's ladder is armed by "
        "nothing, and no pair will ever escalate"
    )


class _StubMonitor:
    def start_gap(self, *a, **k) -> None: ...
    def end_gap(self, *a, **k) -> float:
        return 0.0


class _StubWatermark:
    breached = False
    measurable = True


def test_the_drill_knob_moves_the_book_state_not_just_the_return_value():
    """Returning False while leaving `book.desynced` False makes the knob simulate a different fault:
    every forced failure reads as a fresh transition, and the recovery loop -- which reads live book
    state -- never engages.
    """
    from cli.capture import command

    book = _StubBook([])
    book.desynced = False
    original = command._DRILL_DESYNC_SECONDS
    command._DRILL_DESYNC_SECONDS = 60.0
    command._drill_started_at.clear()
    try:
        result = command._drill_maybe_fail("BTC/EUR", "book_update", True, book, datetime.now(UTC))
    finally:
        command._DRILL_DESYNC_SECONDS = original
        command._drill_started_at.clear()

    assert result is False, "the knob did not force the failure"
    assert book.desynced is True, (
        "the knob returned False but left book.desynced False — the transition guard will see a "
        "fresh desync on every message and re-fire rung 1 in a storm"
    )
