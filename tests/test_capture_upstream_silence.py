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
    planned-downtime notification carries an `effectiveTime`. `classify()` must return "status" so
    `_consume` records it instead of discarding it. While the frame fell through to "other" and was
    dropped, "did Kraken announce the outage?" was UNANSWERABLE rather than answered no -- an empty
    log is not an absent event when nothing logs the event.
    """
    assert classify({"channel": "status", "type": "update", "data": [{"system": "online"}]}) == "status"
    assert classify({"channel": "status", "type": "update", "data": [{"system": "maintenance"}]}) == "status"


def test_the_consumer_counts_and_records_the_venue_status_it_receives():
    """D1 is "log AND count, keeping system and effectiveTime" -- a log line alone answers the
    question only for whoever thinks to grep Loki. `effectiveTime` is the field that would carry a
    planned-downtime lead time -- the number the pre-drain decision waited on ([[T0105]], settled
    2026-08-06: the first real event carried None throughout, and the pre-drain was dropped);
    capturing `system` while dropping it would have answered only the easy half.
    """
    import asyncio

    from cli.capture.command import _consume
    from cli.capture.desync_recovery import DesyncRecovery

    class _StatusClient(_FakeClient):
        async def stream(self):
            yield {
                "channel": "status",
                "type": "update",
                "data": [{"system": "maintenance", "version": "2.0.11", "effectiveTime": 1784880000}],
            }

    venue_status: dict[str, int] = {}
    asyncio.run(_consume(_StatusClient(), {}, {}, {}, _StubMonitor(), _StubWatermark(), DesyncRecovery(), {}, venue_status))
    assert venue_status == {"maintenance": 1}, f"venue status not counted by system value: {venue_status}"


def test_repeated_venue_status_accumulates_per_system_value():
    import asyncio

    from cli.capture.command import _consume
    from cli.capture.desync_recovery import DesyncRecovery

    class _StatusClient(_FakeClient):
        async def stream(self):
            for system in ("online", "online", "cancel_only"):
                yield {"channel": "status", "type": "update", "data": [{"system": system}]}

    venue_status: dict[str, int] = {}
    asyncio.run(_consume(_StatusClient(), {}, {}, {}, _StubMonitor(), _StubWatermark(), DesyncRecovery(), {}, venue_status))
    assert venue_status == {"online": 2, "cancel_only": 1}


def test_a_status_message_without_a_system_field_does_not_crash_the_consumer():
    """The consumer is the single task the whole daemon runs on; an unexpected payload shape here
    kills capture for all 12 pairs and both kinds."""
    import asyncio

    from cli.capture.command import _consume
    from cli.capture.desync_recovery import DesyncRecovery

    class _OddClient(_FakeClient):
        async def stream(self):
            yield {"channel": "status", "type": "update", "data": [{}]}
            yield {"channel": "status", "type": "update"}  # no data key at all

    venue_status: dict[str, int] = {}
    asyncio.run(
        _consume(_OddClient(), {}, {}, {}, _StubMonitor(), _StubWatermark(), DesyncRecovery(), {}, venue_status)
    )  # must not raise
    # And it must not record a None key. `collect()` does `sorted(self._venue_status.items())`, so a
    # None beside any string key raises TypeError out of the collector -- /metrics 500s and EVERY
    # capture series goes dark, which is a far worse outcome than the malformed message itself.
    assert venue_status == {}, f"a status message with no `system` was counted: {venue_status}"


def test_the_consumer_routes_replies_back_to_the_client():
    """T0102's seam. `note_reply` is what RELEASES the deferred subscribe, so a consumer that never
    calls it leaves every resubscribe waiting out its full ack timeout before recovering -- a
    mechanism nobody feeds, which is the failure class this project keeps rediscovering."""
    import asyncio

    from cli.capture.command import _consume
    from cli.capture.desync_recovery import DesyncRecovery

    seen: list[dict] = []

    class _ReplyClient(_FakeClient):
        def note_reply(self, msg):
            seen.append(msg)

        async def stream(self):
            yield {"method": "unsubscribe", "success": True, "req_id": 7}
            yield {"method": "subscribe", "success": False, "error": "nope", "req_id": 8}

    asyncio.run(_consume(_ReplyClient(), {}, {}, {}, _StubMonitor(), _StubWatermark(), DesyncRecovery(), {}, {}))
    assert [m["req_id"] for m in seen] == [7, 8], f"replies never reached the client: {seen}"


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
            _book_msg("BTC/EUR"),
            "book_update",
            _FakeClient(),
            {"BTC/EUR": _StubBook()},
            {},
            _StubMonitor(),
            _StubWatermark(),
            DesyncRecovery(),
            last_seen,
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
            _book_msg("BTC/EUR"),
            "book_update",
            _FakeClient(),
            {"BTC/EUR": _StubBook()},
            {},
            _StubMonitor(),
            _Breached(),
            DesyncRecovery(),
            last_seen,
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
            _ScriptedClient(),
            {"BTC/EUR": _StubBook()},
            {},
            {},
            _StubMonitor(),
            _StubWatermark(),
            DesyncRecovery(),
            last_seen,
            {},
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
            ["BTC/EUR"],
            monitor,
            last_seen,
            interval=0,
            threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=209),
            once=True,
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
            ["BTC/EUR"],
            monitor,
            {"BTC/EUR": T0},
            interval=0,
            threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=29.9),
            once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is False


def test_the_close_over_books_by_at_most_one_check_interval_and_never_under():
    """Finding 8 of the pre-push review, pinned rather than left as prose.

    The window closes at the pair's `last_seen` as of the CLOSING TICK, not at the first message
    after the silence, so it absorbs up to one `interval` of live traffic. Bounded and always in the
    same direction -- over, never under -- which is the safe direction for a counter whose whole
    defect was under-reporting. If someone later closes at the true resume instant, this test tells
    them the bound they are changing.
    """
    import asyncio

    from cli.capture.command import _staleness_loop

    monitor = GapMonitor()
    last_seen = {"BTC/EUR": T0}
    true_silence = 209.01
    interval = 5.0

    # Tick 1: still silent -> window opens, stamped at T0.
    asyncio.run(
        _staleness_loop(
            ["BTC/EUR"], monitor, last_seen, interval=0, threshold=30.0, now_fn=lambda: T0 + timedelta(seconds=100), once=True
        )
    )
    # Data resumed at +209.01 and has been flowing since; the closing tick sees the LATEST message.
    last_seen["BTC/EUR"] = T0 + timedelta(seconds=209.98)
    asyncio.run(
        _staleness_loop(
            ["BTC/EUR"], monitor, last_seen, interval=0, threshold=30.0, now_fn=lambda: T0 + timedelta(seconds=210), once=True
        )
    )
    booked = monitor.gap_seconds("BTC/EUR")
    assert booked >= true_silence, f"booked {booked}s for a {true_silence}s silence -- UNDER-reporting"
    assert booked <= true_silence + interval, (
        f"booked {booked}s for a {true_silence}s silence -- over-reports by more than one {interval}s interval"
    )


def test_gap_seconds_can_double_count_and_the_ratio_can_exceed_one():
    """Finding 9, pinned as the deliberate behaviour it is. The three window kinds are summed
    independently, so a pair desynced THROUGH an upstream blackout books those seconds twice and
    `gap_ratio` exceeds 1.0. T0105 plans a rule on this counter; that rule must read it as an upper
    bound on lost time, never as a fraction of the window."""
    m = GapMonitor()
    m.start_gap("BTC/EUR", "checksum_resync", at=T0)
    m.start_silence("BTC/EUR", at=T0)
    m.end_gap("BTC/EUR", at=T0 + timedelta(seconds=60))
    m.end_silence("BTC/EUR", at=T0 + timedelta(seconds=60))

    assert m.gap_seconds("BTC/EUR") == 120.0, "the two concurrent windows no longer sum independently"
    assert m.gap_ratio("BTC/EUR", window_seconds=60.0) == 2.0, (
        "gap_ratio no longer exceeds 1.0 on overlapping windows -- if that is intended, T0105's rule "
        "design and the gap_seconds docstring must change with it"
    )


def test_the_threshold_is_exclusive_at_the_boundary():
    """`>` not `>=`, pinned. Spec 00073 D5 claims the threshold deliberately EQUALS the reconciler's
    `--min-gap-seconds` so the two producers measure the same thing -- and T0103 separately records
    that the reconciler's own two predicates disagree at exactly this boundary (`>=` vs `>`). An
    unpinned boundary here would make that alignment claim untestable in the same way."""
    import asyncio

    from cli.capture.command import _staleness_loop

    monitor = GapMonitor()
    asyncio.run(
        _staleness_loop(
            ["BTC/EUR"],
            monitor,
            {"BTC/EUR": T0},
            interval=0,
            threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=30.0),
            once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is False, "exactly-at-threshold opened a window; the comparison is >="


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
            ["BTC/EUR"],
            monitor,
            {},
            interval=0,
            threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=9999),
            once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is False


def test_the_staleness_loop_is_actually_scheduled_by_the_daemon():
    """A watchdog nobody starts is [[T0100]]'s defect in another costume -- and this one was caught by
    mutation rather than by reading: replacing `_run`'s `create_task(_staleness_loop(...))` with a
    no-op sleep passed all 22 tests in this file. Every property above holds on a loop that never
    runs, because every one of them drives the loop body directly.

    Parsed, not grepped: the call must appear inside `_run`'s own body, and the task must be in the
    shutdown tuples, or a cancelled-but-never-awaited task hangs the exit path.
    """
    import ast
    import inspect
    import re

    from cli.capture import command

    run_src = inspect.getsource(command._run)
    tree = ast.parse(run_src.lstrip())
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "_staleness_loop" in called, "_staleness_loop is defined but _run never schedules it"
    # EVERY shutdown tuple must carry it. A task awaited but never cancelled hangs `_run` forever on
    # its own `while True`: SIGTERM never completes, the container is SIGKILLed, and `writer.close()`
    # never runs -- losing buffered rows on the unbackfillable path. Not hypothetical: the first
    # version of this assertion counted occurrences of the word "staleness", which the create_task
    # line alone satisfied, and the defect shipped and hung the suite for 89 minutes.
    tuples = re.findall(r"for task in \(([^)]*)\):", run_src)
    assert len(tuples) >= 2, f"expected a cancel loop and an await loop in _run, found {len(tuples)}"
    for i, members in enumerate(tuples):
        assert "staleness" in members, (
            f"shutdown tuple #{i} omits the staleness task ({members.strip()}) -- awaited-but-not-"
            "cancelled hangs shutdown forever; cancelled-but-not-awaited leaks it"
        )


def test_run_hands_the_SAME_maps_to_the_producer_and_the_consumer_of_each():
    """Findings 1 and 6 of the pre-push review: `_staleness_loop(pairs, monitor, {})` survived all
    350 capture tests, and so did handing `_consume` a throwaway `venue_status`.

    Making `last_seen` a required ARGUMENT only protects the producer side -- the third positional
    parameter accepts any dict, so `_run` can hand the watchdog a map nothing ever writes and every
    test still passes while T0101 ships un-fixed. This is the T0008/T0100 defect one call site over,
    which is exactly why it is asserted structurally rather than trusted.

    Parsed from `_run`'s AST: the identifier passed to `_consume` must be the identifier passed to
    `_staleness_loop` / `CaptureCollector`, not merely *a* dict.
    """
    import ast
    import inspect

    from cli.capture import command

    tree = ast.parse(inspect.getsource(command._run).lstrip())
    args_of = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            args_of[node.func.id] = [a.id for a in node.args if isinstance(a, ast.Name)]

    assert "_consume" in args_of and "_staleness_loop" in args_of, f"call sites not found: {sorted(args_of)}"
    consume_args, stale_args = args_of["_consume"], args_of["_staleness_loop"]

    # The watchdog reads what the handler writes.
    shared = set(consume_args) & set(stale_args)
    assert shared, (
        f"_staleness_loop{tuple(stale_args)} shares NO variable with _consume{tuple(consume_args)} -- "
        "the watchdog is reading a map the daemon never writes"
    )
    assert "last_seen" in stale_args, f"_staleness_loop is not given last_seen: {stale_args}"
    assert "last_seen" in consume_args, f"_consume is not given last_seen: {consume_args}"
    assert "venue_status" in consume_args, f"_consume is not given venue_status: {consume_args}"
    assert "venue_status" in args_of.get("CaptureCollector", []), (
        "the collector exports a venue-status counter fed by a different dict than the consumer writes"
    )


def test_every_pair_is_seeded_so_a_never_delivered_stream_is_not_invisible():
    """Finding 3. Without a seed, a pair that is subscribed and never sends anything has no
    `last_seen`, so the watchdog skips it forever AND the gauge reports 0.0 -- the healthiest value
    there is. The instrument built to see silence would be blind to total silence."""
    import ast
    import inspect

    from cli.capture import command

    src = inspect.getsource(command._run)
    assert "dict.fromkeys(pairs" in src or "for pair in pairs" in src.split("last_seen")[1][:120], (
        "last_seen is not seeded from `pairs` at process start -- a stream that never delivers is invisible"
    )
    tree = ast.parse(src.lstrip())
    seeded = any(
        isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "last_seen"
        and not (isinstance(n.value, ast.Dict) and not n.value.keys)
        for n in ast.walk(tree)
    )
    assert seeded, "last_seen is initialised to an empty dict; seed it from `pairs`"


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
            ["AAA/EUR", "BTC/EUR"],
            monitor,
            last_seen,
            interval=0,
            threshold=30.0,
            now_fn=lambda: T0 + timedelta(seconds=209),
            once=True,
        )
    )
    assert monitor.is_silent("BTC/EUR") is True, "one pair's exception starved the pair after it"
