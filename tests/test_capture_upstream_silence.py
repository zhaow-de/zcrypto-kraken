"""A connected-but-silent book stream is observable (spec 00073, T0101).

On 2026-07-27 both capture hosts lost all 12 book streams for ~209 s and the daemon booked NOTHING:
`zcrypto_capture_gap_seconds_total` read 0.0 on every pair across 97.57 h of uptime containing 33
reconnects, and neither host's log held a single `gap start` line. Every liveness signal answered
correctly -- the socket was open, the library keepalive completed >=11 ping/pong round trips, and no
gap window existed -- because nothing in `cli/capture/` read a last-message timestamp.

Three properties carry this design, each with a test that fails if it is removed:

1. **Silence is booked from `last_seen`, not from detection.** Stamping the window at `now` would
   silently discard the threshold's worth of every outage.
2. **`last_seen` is recorded before every early return.** A disk-watermark breach stops the writers;
   it must not also blind the watchdog, or the two silent-loss modes compound.
3. **The dead-man is NOT gated on silence in this iteration** (D3). `is_healthy()` gates the ping for
   ALL pairs, so an unfitted threshold would darken the fleet's liveness signal on both hosts --
   strictly worse than the metric gap being fixed. Booking first, gating once the distribution is
   measured.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cli.capture.gap_monitor import GapMonitor
from cli.capture.ws_client import classify, compute_backoff

T0 = datetime(2026, 7, 27, 7, 0, 0, tzinfo=UTC)


# --- The monitor's own silence window ------------------------------------------------------------
# A DEDICATED window, exactly as the disk watermark has one and for the same reason: `start_gap` is
# idempotent per pair, so routing silence through it would let a concurrent checksum_resync gap
# swallow the silence -- and worse, whichever closed first would book the other's window as its own.


def test_silence_is_booked_from_when_the_stream_went_quiet_not_from_detection():
    """Property 1. The watchdog cannot notice until the threshold has already elapsed, so stamping
    the window at detection time discards exactly the threshold from every outage -- 30 s of every
    gap, forever, in the under-reporting direction this whole topic is about."""
    m = GapMonitor()
    last_seen = T0
    m.start_silence("BTC/EUR", at=last_seen)  # stamped at last_seen, detected 30 s later
    booked = m.end_silence("BTC/EUR", at=T0 + timedelta(seconds=209))
    assert booked == 209.0, f"booked {booked}s of a 209s silence"


def test_silence_seconds_reach_the_exported_counter():
    """The whole point: `gap_seconds_total` must stop reading 0.0 through a total blackout."""
    m = GapMonitor()
    assert m.gap_seconds("BTC/EUR") == 0.0
    m.start_silence("BTC/EUR", at=T0)
    m.end_silence("BTC/EUR", at=T0 + timedelta(seconds=209))
    assert m.gap_seconds("BTC/EUR") == 209.0


def test_an_open_silence_window_accrues_against_a_clock():
    """An outage in progress must be visible while it is happening, not only once it ends."""
    m = GapMonitor()
    m.start_silence("BTC/EUR", at=T0)
    assert m.gap_seconds("BTC/EUR", at=T0 + timedelta(seconds=50)) == 50.0


def test_start_silence_is_idempotent_and_the_earliest_stamp_wins():
    """The watchdog re-evaluates every 5 s while a pair stays silent; a second open must not reset
    the window's start, or a long outage books one tick's worth."""
    m = GapMonitor()
    m.start_silence("BTC/EUR", at=T0)
    m.start_silence("BTC/EUR", at=T0 + timedelta(seconds=5))
    assert m.end_silence("BTC/EUR", at=T0 + timedelta(seconds=209)) == 209.0


def test_silence_is_per_pair():
    m = GapMonitor()
    m.start_silence("BTC/EUR", at=T0)
    m.end_silence("BTC/EUR", at=T0 + timedelta(seconds=10))
    assert m.gap_seconds("BTC/EUR") == 10.0
    assert m.gap_seconds("ETH/EUR") == 0.0


def test_ending_a_silence_that_never_started_is_a_noop():
    assert GapMonitor().end_silence("BTC/EUR", at=T0) == 0.0


def test_a_backward_clock_step_cannot_produce_negative_gap():
    """Mirrors `end_gap`/`end_watermark_gap`: `at` comes from the wall clock, and this runs inside a
    bare task, so an escaping exception would end silence tracking for the process's life."""
    m = GapMonitor()
    m.start_silence("BTC/EUR", at=T0)
    assert m.end_silence("BTC/EUR", at=T0 - timedelta(seconds=5)) == 0.0
    assert m.gap_seconds("BTC/EUR") == 0.0


def test_silence_does_not_gate_the_dead_man_in_this_iteration():
    """Property 3, and it is a DELIBERATE negative. `is_healthy()` gates the healthchecks.io ping for
    every pair at once, so wiring a threshold fitted to ~4 days of thin-leg data into it would let
    one twitchy pair darken the liveness signal on both capture hosts.

    When this is intentionally reversed, this test is the thing that must be rewritten -- which is
    the point: the change cannot happen by accident.
    """
    m = GapMonitor()
    m.start_silence("BTC/EUR", at=T0)
    assert m.is_healthy(["BTC/EUR"]) is True, (
        "silence now gates the dead-man -- if that is intended, D3 of spec 00073 must be revised first"
    )


def test_silence_and_a_desync_gap_are_independent_windows():
    """The interaction the dedicated window exists to prevent: both open at once, each books its own
    duration, and neither closes the other."""
    m = GapMonitor()
    m.start_gap("BTC/EUR", "checksum_resync", at=T0)
    m.start_silence("BTC/EUR", at=T0)
    m.end_silence("BTC/EUR", at=T0 + timedelta(seconds=10))
    assert m.is_open("BTC/EUR") is True, "closing the silence window closed the desync gap"
    m.end_gap("BTC/EUR", at=T0 + timedelta(seconds=20))
    assert m.gap_seconds("BTC/EUR") == 30.0  # 10 silence + 20 desync, both counted


# --- classify() must stop discarding the venue's own status ---------------------------------------


def test_the_status_channel_is_recognised_rather_than_discarded():
    """D1. Kraken pushes `status` automatically on connect and on every engine-state change, and its
    planned-downtime notification carries an `effectiveTime`. Today `classify()` returns "other" and
    `_consume` drops it, so "did Kraken announce the outage?" is UNANSWERABLE rather than answered
    no -- an empty log is not an absent event when nothing logs the event.
    """
    assert classify({"channel": "status", "type": "update", "data": [{"system": "online"}]}) == "status"
    assert classify({"channel": "status", "type": "update", "data": [{"system": "maintenance"}]}) == "status"


def test_classifying_status_does_not_disturb_the_existing_categories():
    assert classify({"channel": "book", "type": "snapshot"}) == "book_snapshot"
    assert classify({"channel": "book", "type": "update"}) == "book_update"
    assert classify({"channel": "trade", "type": "update"}) == "trade_update"
    assert classify({"channel": "heartbeat"}) == "heartbeat"
    assert classify({"method": "subscribe", "success": True}) == "subscribe_ack"
    assert classify({"method": "subscribe", "success": False}) == "subscribe_error"
    assert classify({"channel": "something-new"}) == "other"


# --- D6: do not stampede a restarting venue -------------------------------------------------------


def test_an_ordinary_drop_keeps_the_fast_reconnect():
    """~8.2 reconnects/day are ordinary drops that recover in 0.8-6.2 s. They must not be slowed."""
    assert compute_backoff(0) == 1.0
    assert compute_backoff(1) == 2.0
    assert compute_backoff(0, after_service_restart=False) == 1.0


def test_a_service_restart_floors_the_first_delay_at_five_seconds():
    """Kraken's documented guidance is to reconnect no faster than once every 5 s after maintenance.
    Measured 2026-07-27: the primary's attempt 1 fired 1.0 s after the 1012 and was answered HTTP
    503; attempt 2 succeeded. Reconnecting eagerly into a restarting venue cost ~3.9 s of extra
    silence on the unbackfillable path.
    """
    assert compute_backoff(0, after_service_restart=True) == 5.0


def test_the_service_restart_floor_never_shortens_a_later_backoff():
    """The floor raises a too-eager first attempt; it must not cap a genuinely escalating backoff."""
    assert compute_backoff(3, after_service_restart=True) == 8.0
    assert compute_backoff(6, after_service_restart=True) == 60.0


# --- The SEAM: the daemon must actually feed and drive the watchdog -------------------------------
# T0008 shipped a ladder that passed 63 tests while nothing armed it, because every test called the
# decision core directly and none called the production path. These call the real handler AND the
# real consumer. `last_seen` is a required argument on both for the same reason: a defaulted one can
# be dropped from a call site in silence, which is how that defect survived a whole review round.


class _FakeClient:
    def __init__(self) -> None:
        self.resubscribed: list[str] = []
        self.connected = True

    async def resubscribe_book(self, pair: str) -> None:
        self.resubscribed.append(pair)

    async def force_reconnect(self) -> None: ...


class _StubBook:
    def __init__(self, results=None) -> None:
        self._results = list(results or [])
        self.desynced = False

    def _next(self) -> bool:
        ok = self._results.pop(0) if self._results else True
        self.desynced = not ok
        return ok

    def ingest_snapshot(self, entry) -> bool:
        return self._next()

    def ingest_update(self, entry) -> bool:
        return self._next()


class _StubMonitor:
    def start_gap(self, *a, **k) -> None: ...
    def end_gap(self, *a, **k) -> float:
        return 0.0


class _StubWatermark:
    breached = False
    measurable = True


def _book_msg(pair: str) -> dict:
    return {"data": [{"symbol": pair}]}


def test_the_handler_records_last_seen_for_every_book_message():
    import asyncio

    from cli.capture.command import _handle_book_message
    from cli.capture.desync_recovery import DesyncRecovery

    last_seen: dict[str, datetime] = {}
    asyncio.run(
        _handle_book_message(
            _book_msg("BTC/EUR"), "book_update", _FakeClient(), {"BTC/EUR": _StubBook()},
            {}, _StubMonitor(), _StubWatermark(), DesyncRecovery(), last_seen,
        )
    )
    assert "BTC/EUR" in last_seen, "the daemon received a book message and recorded no last-seen time"


def test_last_seen_is_recorded_even_while_the_disk_watermark_is_breached():
    """Property 2. A breach makes the handler `continue` past the writers, so L2 is discarded while
    the socket stays connected -- T0032's silent-death shape. If the breach ALSO stopped `last_seen`
    updating, the watchdog would book a phantom silence on top of a real loss, and the two
    silent-loss modes would compound into one unreadable number.
    """
    import asyncio

    from cli.capture.command import _handle_book_message
    from cli.capture.desync_recovery import DesyncRecovery

    class _Breached(_StubWatermark):
        breached = True

    last_seen: dict[str, datetime] = {}
    asyncio.run(
        _handle_book_message(
            _book_msg("BTC/EUR"), "book_update", _FakeClient(), {"BTC/EUR": _StubBook()},
            {}, _StubMonitor(), _Breached(), DesyncRecovery(), last_seen,
        )
    )
    assert "BTC/EUR" in last_seen, "a watermark breach blinded the staleness watchdog"


def test_the_consumer_hands_its_last_seen_map_down_to_the_handler():
    """The production CALL SITE, not just the callee. Covering a handler is not covering its caller
    -- that exact gap let a mutation survive the entire suite on the T0008 branch."""
    import asyncio

    from cli.capture.command import _consume
    from cli.capture.desync_recovery import DesyncRecovery

    class _ScriptedClient(_FakeClient):
        async def stream(self):
            yield {"channel": "book", "type": "update", **_book_msg("BTC/EUR")}

    last_seen: dict[str, datetime] = {}
    asyncio.run(
        _consume(
            _ScriptedClient(), {"BTC/EUR": _StubBook()}, {}, {},
            _StubMonitor(), _StubWatermark(), DesyncRecovery(), last_seen,
        )
    )
    assert "BTC/EUR" in last_seen, "_consume never handed its last-seen map down -- the watchdog is fed by nothing"


def test_the_staleness_loop_books_silence_stamped_at_the_last_message():
    """The whole feature, end to end against the real loop body: a pair goes quiet, the window opens
    at its last message, and the booked duration is the TRUE silence -- not silence minus threshold."""
    import asyncio

    from cli.capture.command import _staleness_loop

    monitor = GapMonitor()
    last_seen = {"BTC/EUR": T0}
    # Detected 209 s later; the window must still be stamped at T0.
    asyncio.run(
        _staleness_loop(
            ["BTC/EUR"], monitor, last_seen, interval=0, threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=209), once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is True
    assert monitor.gap_seconds("BTC/EUR", at=T0 + timedelta(seconds=209)) == 209.0


def test_the_staleness_loop_does_not_fire_inside_the_threshold():
    """The load-bearing negative: the worst measured natural book spacing is 12.196 s (ETH/BTC), so
    a threshold that fired early would book ordinary quiet as loss on the thinnest legs."""
    import asyncio

    from cli.capture.command import _staleness_loop

    monitor = GapMonitor()
    asyncio.run(
        _staleness_loop(
            ["BTC/EUR"], monitor, {"BTC/EUR": T0}, interval=0, threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=29.9), once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is False


def test_a_returning_stream_closes_the_silence_window():
    import asyncio

    from cli.capture.command import _staleness_loop

    monitor = GapMonitor()
    last_seen = {"BTC/EUR": T0}
    tick = [T0 + timedelta(seconds=209)]
    asyncio.run(_staleness_loop(["BTC/EUR"], monitor, last_seen, interval=0, threshold=30.0, now_fn=lambda: tick[0], once=True))
    assert monitor.is_silent("BTC/EUR") is True

    last_seen["BTC/EUR"] = T0 + timedelta(seconds=209)  # data resumed
    tick[0] = T0 + timedelta(seconds=210)
    asyncio.run(_staleness_loop(["BTC/EUR"], monitor, last_seen, interval=0, threshold=30.0, now_fn=lambda: tick[0], once=True))
    assert monitor.is_silent("BTC/EUR") is False
    assert monitor.gap_seconds("BTC/EUR") == 209.0


def test_a_pair_that_has_never_produced_a_message_is_not_booked_as_silent():
    """Startup: before the first snapshot arrives there is no `last_seen`, and booking from process
    start would charge every restart a threshold's worth of phantom gap on all 12 pairs."""
    import asyncio

    from cli.capture.command import _staleness_loop

    monitor = GapMonitor()
    asyncio.run(
        _staleness_loop(
            ["BTC/EUR"], monitor, {}, interval=0, threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=9999), once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is False


def test_one_pair_raising_does_not_starve_the_others():
    """T0008's H2, pre-empted here rather than re-learned: `pairs` is ordered, so a sweep-wide
    try/except starves every pair after the raising one, deterministically and forever."""
    import asyncio

    from cli.capture.command import _staleness_loop

    class _Exploding(GapMonitor):
        def start_silence(self, pair, *, at):
            if pair == "AAA/EUR":
                raise RuntimeError("boom")
            super().start_silence(pair, at=at)

    monitor = _Exploding()
    last_seen = {"AAA/EUR": T0, "BTC/EUR": T0}
    asyncio.run(
        _staleness_loop(
            ["AAA/EUR", "BTC/EUR"], monitor, last_seen, interval=0, threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=209), once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is True, "one pair's exception starved the pair after it"
