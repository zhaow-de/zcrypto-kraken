"""The bounded desync-recovery ladder (spec 00072, T0008).

Recovery from a checksum desync is a single fire-and-forget resubscribe, fired only on the
transition into desync — deliberately, because re-firing on every out-of-sync update means hundreds
per second at depth-100, which trips Kraken's subscribe rate limit so the pair can never resync.
The cost of that guard is that a failed first attempt leaves the pair stuck forever.

This ladder adds rungs 2 and 3: bounded retries, then one escalation to a full reconnect.

Three properties carry the design, and each has a test that fails if it is removed:

1. **Retries are driven by desync STATE, never by protocol responses.** A snapshot that fails its
   own checksum produces no error frame — Kraken is satisfied and the book is still wrong — so only
   "still desynced N seconds later" can see it.
2. **The ladder terminates.** Cycling would turn one stuck pair into a reconnect loop, and every
   reconnect drops all 12 pairs; that is strictly worse than the defect being fixed.
3. **It is bounded in wall-clock**, because a desynced pair withholds the host's dead-man ping for
   ALL pairs, not just itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cli.capture.desync_recovery import Action, DesyncRecovery

T0 = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)


def _ladder(**kw) -> DesyncRecovery:
    return DesyncRecovery(grace_seconds=20.0, backoff_seconds=(5.0, 10.0, 20.0), cooldown_seconds=3600.0, **kw)


def test_a_pair_that_never_desynced_is_never_due():
    assert _ladder().due("BTC/EUR", at=T0) is Action.NONE


def test_nothing_fires_before_the_grace_period_expires():
    """The load-bearing negative: a retry inside the grace would fire on a recovery still in
    flight, turning one resubscribe into two and walking toward the rate limit the transition
    guard exists to avoid."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    assert lad.due("BTC/EUR", at=T0 + timedelta(seconds=19.9)) is Action.NONE


def test_the_first_retry_fires_once_the_grace_expires():
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    assert lad.due("BTC/EUR", at=T0 + timedelta(seconds=20.1)) is Action.RETRY


def test_a_recovered_pair_stops_the_ladder_and_forgets_its_history():
    """Recovery is the only thing that resets the ladder — and it must reset fully, or a pair that
    desyncs twice in an hour would escalate on its second, milder event."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    lad.note_recovered("BTC/EUR", at=T0 + timedelta(seconds=5))
    assert lad.due("BTC/EUR", at=T0 + timedelta(seconds=600)) is Action.NONE
    lad.note_desync("BTC/EUR", at=T0 + timedelta(seconds=700))
    assert lad.due("BTC/EUR", at=T0 + timedelta(seconds=700.1)) is Action.NONE  # grace restarts


def test_retries_back_off_and_do_not_fire_early():
    """5s, 10s, 20s after each preceding attempt — bounded by construction."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    now = T0 + timedelta(seconds=20.1)
    assert lad.due("BTC/EUR", at=now) is Action.RETRY
    lad.note_attempt("BTC/EUR", at=now)

    for backoff in (5.0, 10.0, 20.0)[:2]:
        assert lad.due("BTC/EUR", at=now + timedelta(seconds=backoff - 0.1)) is Action.NONE
        now = now + timedelta(seconds=backoff + 0.1)
        assert lad.due("BTC/EUR", at=now) is Action.RETRY
        lad.note_attempt("BTC/EUR", at=now)


def test_it_escalates_to_reconnect_after_the_last_retry():
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    now = T0 + timedelta(seconds=20.1)
    for backoff in (0.0, 5.0, 10.0, 20.0):
        now = now + timedelta(seconds=backoff + 0.1)
        action = lad.due("BTC/EUR", at=now)
        if action is Action.RECONNECT:
            break
        assert action is Action.RETRY
        lad.note_attempt("BTC/EUR", at=now)
    else:
        pytest.fail("never escalated")


def test_the_ladder_terminates_after_one_escalation():
    """Property 2. A second escalation would drop all 12 pairs again for a pair that has already
    proven a reconnect does not fix it — a loop strictly worse than the stuck pair."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    lad.note_escalated("BTC/EUR", at=T0 + timedelta(seconds=60))
    for minutes in (2, 10, 30, 59):
        assert lad.due("BTC/EUR", at=T0 + timedelta(minutes=minutes)) is Action.NONE, (
            f"escalated again after {minutes} min — that is a reconnect loop"
        )


def test_the_cooldown_expires_so_a_much_later_desync_is_handled_afresh():
    """Terminal must not mean permanently deaf: an unrelated desync an hour later deserves the
    full ladder again."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    lad.note_escalated("BTC/EUR", at=T0)
    lad.note_desync("BTC/EUR", at=T0 + timedelta(seconds=3700))
    assert lad.due("BTC/EUR", at=T0 + timedelta(seconds=3721)) is Action.RETRY


def test_pairs_are_independent():
    """One stuck pair must not consume another's budget — 12 pairs share this object."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    lad.note_escalated("BTC/EUR", at=T0)
    lad.note_desync("ETH/EUR", at=T0)
    assert lad.due("ETH/EUR", at=T0 + timedelta(seconds=20.1)) is Action.RETRY
    assert lad.due("BTC/EUR", at=T0 + timedelta(seconds=20.1)) is Action.NONE


def test_the_whole_ladder_is_bounded_in_wall_clock():
    """Property 3, asserted as a number rather than left implicit: a desynced pair withholds the
    host's dead-man ping for ALL pairs, so the time from desync to terminal is a fleet-wide
    liveness budget, not a per-pair nicety."""
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    now, escalated_at = T0, None
    for _ in range(200):
        now += timedelta(seconds=1)
        action = lad.due("BTC/EUR", at=now)
        if action is Action.RETRY:
            lad.note_attempt("BTC/EUR", at=now)
        elif action is Action.RECONNECT:
            escalated_at = now
            break
    assert escalated_at is not None, "ladder never reached escalation"
    span = (escalated_at - T0).total_seconds()
    assert span <= 90, f"desync-to-escalation took {span}s; the dead-man is dark for every pair meanwhile"


def test_the_escalation_cooldown_survives_a_recovery():
    """H1. The likeliest healer of an escalated pair is the escalation's own reconnect — it forces a
    fresh snapshot for every pair. If recovery erased the escalation record, that would close a
    feedback loop: escalate -> reconnect -> heal -> record gone -> escalate again ~55 s later.
    Simulated against the real ladder before the fix: a pair desyncing every 10 min escalated
    6x/hour against the intended 1, a flapping pair 51x/hour -- 72 and ~610 fleet-wide across 12
    pairs, against 12. Ceilings, not steady state (the ladder has no clock, so the reconnect's own
    downtime is uncharged); the over-run ratio is what matters.
    """
    lad = _ladder()
    lad.note_desync("BTC/EUR", at=T0)
    lad.note_escalated("BTC/EUR", at=T0 + timedelta(seconds=55))
    lad.note_recovered("BTC/EUR", at=T0 + timedelta(seconds=60))  # the reconnect healed it

    # A fresh episode inside the cooldown gets retries, but must NOT reach a second reconnect.
    lad.note_desync("BTC/EUR", at=T0 + timedelta(seconds=600))
    now = T0 + timedelta(seconds=600)
    for _ in range(60):
        now += timedelta(seconds=5)
        if lad.due("BTC/EUR", at=now) is Action.RECONNECT:
            pytest.fail(f"second escalation at +{(now - T0).total_seconds()}s, inside the cooldown")
        if lad.due("BTC/EUR", at=now) is Action.RETRY:
            lad.note_attempt("BTC/EUR", at=now)


def test_a_flapping_pair_cannot_manufacture_reconnects():
    """The same defect from the other direction: heal/re-desync cycling must not mint an escalation
    per cycle. Counts them over a simulated hour."""
    lad = _ladder()
    now, escalations = T0, 0
    for cycle in range(60):
        lad.note_desync("BTC/EUR", at=now)
        for _ in range(14):  # ~70 s desynced — long enough to reach escalation
            now += timedelta(seconds=5)
            action = lad.due("BTC/EUR", at=now)
            if action is Action.RETRY:
                lad.note_attempt("BTC/EUR", at=now)
            elif action is Action.RECONNECT:
                escalations += 1
                lad.note_escalated("BTC/EUR", at=now)
        lad.note_recovered("BTC/EUR", at=now)
        now += timedelta(seconds=10)
    assert escalations <= 2, f"{escalations} escalations in ~80 min of flapping — the cooldown is not binding"
