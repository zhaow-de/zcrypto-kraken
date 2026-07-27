"""Bounded desync-recovery ladder (spec 00072, T0008).

`cli/capture/command.py` resubscribes ONCE on the transition into a checksum desync — deliberately,
because re-firing on every out-of-sync update is hundreds per second at depth-100 and trips Kraken's
subscribe rate limit, after which the pair can never resync. The cost of that guard is that a first
attempt which does not take leaves the pair stuck forever.

This is rungs 2 and 3 of the ladder: bounded retries, then exactly one escalation to a full
reconnect, then stop.

Pure state and arithmetic, no I/O and no clock of its own — every method takes `at`. That is what
makes the ladder testable without a WS connection, and it keeps the decision (`due`) separate from
the action, so the caller owns every frame actually sent to Kraken.

Three properties the design rests on:

1. **Driven by desync STATE, never by protocol responses.** A snapshot that fails its own checksum
   produces no error frame — Kraken is satisfied, the book is still wrong — so only "still desynced
   N seconds later" can see it. This is why the ladder cannot be replaced by `req_id` correlation.
2. **It terminates.** One escalation per pair per cooldown. Cycling would turn one stuck pair into a
   reconnect loop, and a reconnect drops all 12 pairs — strictly worse than the defect.
3. **It is bounded in wall clock.** A desynced pair withholds the host's healthchecks.io ping for
   EVERY pair (`gap_monitor.is_healthy` is all-or-nothing), so time-to-terminal is a fleet-wide
   liveness budget, not a per-pair nicety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Defaults per spec 00072 D3. NOT fitted to production: `zcrypto_capture_resubscribes_total` reads 0
# on both hosts, because the 2026-07-13 root-cause fix took desyncs to zero, so no heal-latency
# distribution exists to fit. The grace is generous against any plausible snapshot round-trip; the
# retry count and backoff are bounded far below the storm the transition guard guards against
# (3 attempts over ~35 s, versus hundreds per second).
DEFAULT_GRACE_SECONDS = 20.0
DEFAULT_BACKOFF_SECONDS = (5.0, 10.0, 20.0)
DEFAULT_COOLDOWN_SECONDS = 3600.0


class Action(Enum):
    """What the caller should do for this pair, right now."""

    NONE = "none"
    RETRY = "retry"
    RECONNECT = "reconnect"


@dataclass
class _PairState:
    desynced_at: datetime | None = None
    last_attempt_at: datetime | None = None
    attempts: int = 0
    escalated_at: datetime | None = None


@dataclass
class DesyncRecovery:
    """Per-pair retry ladder. One instance is shared by every pair on a host."""

    grace_seconds: float = DEFAULT_GRACE_SECONDS
    backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS
    _pairs: dict[str, _PairState] = field(default_factory=dict, repr=False)

    def note_desync(self, pair: str, *, at: datetime) -> None:
        """Rung 1 has fired (the transition resubscribe). Start the grace clock.

        A pair already inside an unresolved ladder is left alone — the desync branch only fires on
        the transition, so a second call means a genuinely new episode after a recovery.
        """
        state = self._pairs.get(pair)
        if state is not None and state.desynced_at is not None:
            return
        # An escalation older than the cooldown is forgotten here rather than in `due`, so a much
        # later, unrelated desync gets the full ladder instead of inheriting a terminal state.
        escalated_at = None
        if state is not None and state.escalated_at is not None:
            if (at - state.escalated_at).total_seconds() < self.cooldown_seconds:
                escalated_at = state.escalated_at
        self._pairs[pair] = _PairState(desynced_at=at, escalated_at=escalated_at)

    def note_recovered(self, pair: str, *, at: datetime) -> None:
        """The pair is in sync again: clear the active ladder, but KEEP the escalation record.

        Dropping `escalated_at` here would make the cooldown bind only on a pair that stays
        *continuously* desynced — and the likeliest healer is the escalation's own reconnect, which
        forces a fresh snapshot for every pair. That is a positive feedback path: escalate ->
        reconnect -> pair heals -> record erased -> next episode escalates ~55 s later. Measured on
        the real ladder, a pair desyncing every 10 minutes produced 72 reconnects/hour against an
        advertised bound of 12, and a flapping pair produced 610. Each reconnect costs ~39 s of
        silence on all 12 pairs, so that is exactly the "strictly worse than the defect" outcome
        the terminal state exists to prevent.
        """
        state = self._pairs.get(pair)
        if state is None:
            return
        if state.escalated_at is not None and (at - state.escalated_at).total_seconds() < self.cooldown_seconds:
            # Ladder cleared, cooldown preserved — a re-desync inside the hour gets rungs 1 and 2,
            # never a second reconnect.
            self._pairs[pair] = _PairState(escalated_at=state.escalated_at)
            return
        self._pairs.pop(pair, None)

    def note_attempt(self, pair: str, *, at: datetime) -> None:
        """A retry was just issued. Advances the backoff schedule."""
        state = self._pairs.get(pair)
        if state is None:
            return
        state.last_attempt_at = at
        state.attempts += 1

    def note_escalated(self, pair: str, *, at: datetime) -> None:
        """A full reconnect was just issued for this pair. Terminal until the cooldown expires."""
        state = self._pairs.setdefault(pair, _PairState(desynced_at=at))
        state.escalated_at = at

    def due(self, pair: str, *, at: datetime) -> Action:
        """What to do for `pair` now. Pure — call it as often as you like."""
        state = self._pairs.get(pair)
        if state is None or state.desynced_at is None:
            return Action.NONE

        # Terminal WITHIN the cooldown: escalating again would drop all 12 pairs for a pair that
        # has already proven a reconnect does not fix it. The stuck-shape alert carries it from
        # here, and the withheld dead-man is the backstop.
        if state.escalated_at is not None:
            if (at - state.escalated_at).total_seconds() < self.cooldown_seconds:
                return Action.NONE
            # Cooldown expired: terminal must not mean permanently deaf. Re-arm the full ladder —
            # an episode this much later is a different fault, and refusing to try again would
            # leave a recoverable pair stuck for the life of the process.
            state.escalated_at = None
            state.attempts = 0
            state.last_attempt_at = None
            # `desynced_at` deliberately NOT reset: this pair has been desynced for the whole
            # cooldown, so it has already served far more than the grace period. Restarting the
            # grace here would add a pointless 20 s to a fault an hour old.

        since = (at - (state.last_attempt_at or state.desynced_at)).total_seconds()
        wait = (
            self.grace_seconds
            if state.attempts == 0
            else self.backoff_seconds[min(state.attempts - 1, len(self.backoff_seconds) - 1)]
        )
        if since < wait:
            return Action.NONE
        if state.attempts >= len(self.backoff_seconds):
            return Action.RECONNECT
        return Action.RETRY
