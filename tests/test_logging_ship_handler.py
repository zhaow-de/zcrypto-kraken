from __future__ import annotations

import json
import logging
import time

import pytest

from cli.logging.formatters import JsonLineFormatter
from cli.logging.ship import LokiShipHandler, ShipConfig
from tests.fake_loki import FakeLoki, SilentServer
from tests.fake_loki import handler_factory as _handler_factory

# Tightened so the suite stays fast; the RATIOS (min << max, timeout > flush_interval) are what the
# tests' properties depend on, not these absolute numbers.
_TIGHT = {
    "flush_interval_s": 0.02,
    "timeout_s": 0.3,
    "backoff_min_s": 0.05,
    "backoff_max_s": 0.2,
    "exit_deadline_s": 0.5,
}


@pytest.fixture
def handler_factory():
    return _handler_factory


@pytest.fixture
def fake_loki(handler_factory):
    """A running FakeLoki replying 200 OK; yields `(base_url, requests)` where `requests` is
    the server's live recorded-request list."""
    handler_cls = handler_factory()
    with FakeLoki(handler_cls) as url:
        yield url, handler_cls.requests


@pytest.fixture
def ship_logger():
    """The real logger `_announce_recovery` warns on -- isolated per test (saved/restored) so
    a test's handlers don't leak into others sharing this same global logger object."""
    logger = logging.getLogger("zcrypto.logging.ship")
    saved = (list(logger.handlers), logger.level, logger.propagate)
    logger.handlers, logger.propagate = [], False
    logger.setLevel(logging.DEBUG)
    yield logger
    logger.handlers, logger.level, logger.propagate = saved


class _ListHandler(logging.Handler):
    """Stand-in for the console handler: records every emitted record, unformatted."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _cfg(url: str) -> ShipConfig:
    return ShipConfig(url=f"{url}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")


def _make_handler(url: str, **overrides) -> LokiShipHandler:
    return LokiShipHandler(_cfg(url), **{**_TIGHT, **overrides})


def _make_record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(name="test", level=level, pathname="test.py", lineno=1, msg=msg, args=(), exc_info=None)


def _wait_until(predicate, timeout: float = 1.0, interval: float = 0.005) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _assert_monotone_doubling_then_capped(gaps: list[float], backoff_min_s: float, backoff_max_s: float) -> None:
    """Checks the shape of the retry gaps against each other, never against an absolute bound: each
    measured gap carries flush_interval_s plus the POST round-trip on top of the backoff itself, so
    pinning to backoff_min_s/backoff_max_s exactly flakes under CI scheduling jitter."""
    assert len(gaps) >= 3
    assert gaps[1] > gaps[0] * 1.3  # genuinely grows early on, not a flat retry interval
    slack = backoff_min_s  # generous relative to the min/max spread used by these tests
    for a, b in zip(gaps, gaps[1:]):
        assert b >= a - slack  # never decreases
    assert gaps[-1] <= gaps[-2] * 1.3  # stopped growing -- the doubling has capped
    assert gaps[-1] <= backoff_max_s * 3  # loose ceiling; not pinned to an exact absolute value


def test_emit_ships_batch_with_correct_line_and_timestamp(fake_loki):
    url, requests = fake_loki
    handler = _make_handler(url)
    try:
        record = _make_record("hello")
        handler.emit(record)
        assert _wait_until(lambda: len(requests) >= 1)
        body = json.loads(requests[0][2])
        values = body["streams"][0]["values"]
        assert len(values) == 1
        ts, line = values[0]
        assert ts == str(int(record.created * 1e9))
        assert line == JsonLineFormatter().format(record)
    finally:
        handler.close()


def test_ring_evicts_oldest_at_capacity(handler_factory):
    """Fills capacity+3 entries before the worker ever gets a chance to drain (batch_max is
    larger than the ring, so `emit()` never wakes it; flush_interval_s is left long for the
    same reason) -- isolates the eviction bookkeeping from any shipping behavior."""
    handler_cls = handler_factory()
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, ring_capacity=10, batch_max=1000, flush_interval_s=10.0)
        try:
            for i in range(13):
                handler.emit(_make_record(f"msg-{i}"))
            assert handler.dropped_total == 3
            survivors = [json.loads(line)["message"] for _, _, line in handler._ring]
            assert survivors == [f"msg-{i}" for i in range(3, 13)]  # oldest 3 evicted, newest 10 kept
        finally:
            handler.close()


def test_drain_caps_the_first_batch_at_batch_max(handler_factory):
    """At most batch_max lines per POST. status_code=500 keeps the first drained batch permanently
    held (a retry never clears it, so `_run` never calls `_drain()` a second time) -- isolating the
    cap on a single drain from any later one."""
    handler_cls = handler_factory(status_code=500)
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, flush_interval_s=10.0, batch_max=3, ring_capacity=32, backoff_min_s=0.05, backoff_max_s=0.1)
        try:
            for i in range(10):
                handler.emit(_make_record(f"m{i}"))
            assert _wait_until(lambda: len(handler_cls.requests) >= 1)
            body = json.loads(handler_cls.requests[0][2])
            assert len(body["streams"][0]["values"]) == 3  # exactly batch_max, not all 10 queued
            assert len(handler._ring) == 7  # the rest stayed behind in the ring
        finally:
            handler.close()


@pytest.mark.parametrize("status_code", [500, 429])
def test_retryable_status_retries_the_same_batch_with_backoff(status_code, handler_factory):
    handler_cls = handler_factory(status_code=status_code)
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, batch_max=1, ring_capacity=16)
        try:
            record = _make_record("retry-me")
            handler.emit(record)
            assert _wait_until(lambda: len(handler_cls.requests) >= 6, timeout=3.0)

            bodies = {r[2] for r in handler_cls.requests[:6]}
            assert len(bodies) == 1  # identical body every attempt -- the same batch, not a new one

            times = handler_cls.request_times[:6]
            gaps = [b - a for a, b in zip(times, times[1:])]
            _assert_monotone_doubling_then_capped(gaps, _TIGHT["backoff_min_s"], _TIGHT["backoff_max_s"])
        finally:
            handler.close()


def test_non_429_4xx_drops_the_batch_and_ships_the_next_with_recovery_count(handler_factory, ship_logger):
    handler_cls = handler_factory(status_code=400)
    console = _ListHandler()
    ship_logger.addHandler(console)
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, batch_max=3, ring_capacity=32)
        ship_logger.addHandler(handler)  # so the internal recovery warning ships too
        try:
            for i in range(3):
                handler.emit(_make_record(f"poison-{i}"))
            assert _wait_until(lambda: len(handler_cls.requests) >= 1)
            time.sleep(0.15)  # long enough for several retries to have happened, if it (wrongly) retried
            assert len(handler_cls.requests) == 1  # the poisoned batch was seen exactly once
            assert handler.dropped_total == 3

            handler_cls.status_code = 200  # let the fake succeed for the next batch
            for i in range(3):
                handler.emit(_make_record(f"good-{i}"))
            assert _wait_until(lambda: len(handler_cls.requests) >= 2)
            second = json.loads(handler_cls.requests[1][2])
            messages = [json.loads(line)["message"] for _, line in second["streams"][0]["values"]]
            assert messages == ["good-0", "good-1", "good-2"]  # the next batch shipped, unaffected

            assert _wait_until(lambda: any("recovered" in r.getMessage() for r in console.records))
            time.sleep(0.2)  # settle: >> the 0.02s ship cadence, so a handler that never stops
            # announcing (recovery bookkeeping not resetting) has time to emit a second one
            warnings = [r for r in console.records if "recovered" in r.getMessage()]
            assert len(warnings) == 1
            assert warnings[0].getMessage() == "log shipping recovered; 3 lines dropped while unreachable"

            def _warning_shipped() -> bool:
                return any(b"recovered" in body for _, _, body in handler_cls.requests)

            assert _wait_until(_warning_shipped)
        finally:
            handler.close()


def test_recovery_warning_exact_count_after_ring_overflow(handler_factory, ship_logger):
    """Ring overflow, distinct from the 400 poisoned-batch drop above: batch_max exceeds
    ring_capacity, so the worker's first drain empties the WHOLE ring and the recovery warning later
    lands in an EMPTY ring -- a full one would evict its own just-appended warning entry and announce
    a second, spurious recovery."""
    handler_cls = handler_factory(status_code=500)
    console = _ListHandler()
    ship_logger.addHandler(console)
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, batch_max=1000, ring_capacity=5)
        ship_logger.addHandler(handler)
        try:
            for i in range(8):
                handler.emit(_make_record(f"overflow-{i}"))
            assert handler.dropped_total == 3  # capacity 5, 8 emitted before any drain -- 3 evicted

            handler._wake.set()  # force the (whole-ring) first drain now, deterministically
            assert _wait_until(lambda: len(handler_cls.requests) >= 1)
            assert len(handler._ring) == 0  # the entire ring moved into the held batch -- headroom restored

            handler_cls.status_code = 200  # let the held batch succeed
            assert _wait_until(lambda: any("recovered" in r.getMessage() for r in console.records), timeout=2.0)
            time.sleep(0.2)  # settle: >> the 0.02s ship cadence, so a handler that never stops
            # announcing (recovery bookkeeping not resetting) has time to emit a second one

            warnings = [r for r in console.records if "recovered" in r.getMessage()]
            assert len(warnings) == 1  # exactly one recovery warning
            assert warnings[0].getMessage() == "log shipping recovered; 3 lines dropped while unreachable"

            def _warning_shipped() -> bool:
                return any(b"recovered" in body for _, _, body in handler_cls.requests)

            assert _wait_until(_warning_shipped, timeout=2.0)
        finally:
            handler.close()


def test_emit_never_blocks_against_a_silent_endpoint():
    with SilentServer() as url:
        handler = _make_handler(url, batch_max=500, ring_capacity=4096)
        try:
            start = time.monotonic()
            for i in range(2000):
                handler.emit(_make_record(f"m{i}"))
            elapsed = time.monotonic() - start
            assert elapsed < 0.5  # the structural guarantee: emit() does no network I/O
        finally:
            handler.close()


def test_post_returns_retry_within_timeout_bound_against_silent_endpoint():
    """Direct test of `_post`'s bound: against a peer that accepts the connection and then
    goes silent, it must return ('retry', not hang) within timeout_s -- proving the worker
    always comes back to the backoff loop instead of blocking forever."""
    with SilentServer() as url:
        handler = _make_handler(url)
        try:
            start = time.monotonic()
            outcome = handler._post([("INFO", "1", "line")])
            elapsed = time.monotonic() - start
        finally:
            handler.close()
    assert outcome == "retry"
    assert elapsed < _TIGHT["timeout_s"] + 0.5  # generous slack; never hangs indefinitely


def test_post_unexpected_exception_is_treated_as_retry_worker_survives():
    """A `url` missing its scheme (a plausible Ansible-render typo) raises ValueError from urllib,
    not one of `_post`'s named transport exceptions -- without a catch-all it escapes `_run`'s loop
    and kills the worker thread permanently and silently, defeating spec 00068 D3's "a shipping
    failure is self-announcing; no silent dark window"."""
    cfg = ShipConfig(url="127.0.0.1/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")
    handler = LokiShipHandler(cfg, **_TIGHT, batch_max=2, ring_capacity=5)
    try:
        for i in range(10):
            handler.emit(_make_record(f"m{i}"))
        time.sleep(0.3)  # let the worker run several failed-post/backoff cycles
        assert handler._worker.is_alive()
        assert handler.dropped_total > 0  # ring kept overflowing while shipping stayed stuck
    finally:
        handler.close()


def test_silent_endpoint_times_out_and_retains_the_batch():
    with SilentServer() as url:
        handler = _make_handler(url, batch_max=2, ring_capacity=16, timeout_s=0.2, backoff_min_s=0.05, backoff_max_s=0.1)
        try:
            handler.emit(_make_record("a"))
            handler.emit(_make_record("b"))
            time.sleep(0.2 + 0.1 + 0.1)  # >= one timeout + one backoff cycle, with slack
            assert handler.dropped_total == 0
            assert len(handler._held) + len(handler._ring) == 2  # nothing lost -- still queued for retry
        finally:
            handler.close()


def test_close_flushes_remainder_against_live_endpoint(fake_loki, capsys):
    url, requests = fake_loki
    # flush_interval_s deliberately long: proves close() itself drives the flush, not the
    # periodic timer (which wouldn't fire again for 10s).
    handler = _make_handler(url, flush_interval_s=10.0)
    handler.emit(_make_record("last"))
    start = time.monotonic()
    handler.close()
    elapsed = time.monotonic() - start
    assert elapsed < _TIGHT["exit_deadline_s"] + 0.3
    assert len(requests) == 1
    assert "unshipped" not in capsys.readouterr().out


def test_close_against_silent_endpoint_prints_exact_unshipped_count(capsys):
    # timeout_s is deliberately much larger than exit_deadline_s: the in-flight POST that close()
    # interrupts won't resolve on its own for seconds, so the observed bound can only come from
    # the join deadline itself -- not from the attempt happening to finish quickly regardless.
    with SilentServer() as url:
        handler = _make_handler(url, batch_max=2, ring_capacity=16, timeout_s=2.0)
        for i in range(5):
            handler.emit(_make_record(f"m{i}"))
        # let the worker pick up its first batch (now blocked inside the network call) before
        # closing, so held+ring is a stable, deterministic split of the same 5 records.
        time.sleep(0.05)
        start = time.monotonic()
        handler.close()
        elapsed = time.monotonic() - start
        assert elapsed <= _TIGHT["exit_deadline_s"] + 0.3
        assert "zcrypto log shipping: 5 lines unshipped at exit" in capsys.readouterr().out


def test_close_ships_a_still_held_batch_via_the_final_flush_loop(handler_factory, capsys):
    """Exercises `_run`'s trailing best-effort flush: the batch is already sitting in `_held`,
    mid-backoff, when `close()` fires, so `_stop.set()` interrupts `_stop.wait(backoff)` and trips
    the main loop's `while not self._stop.is_set()` false -- only the trailing loop can ship it."""
    handler_cls = handler_factory(status_code=500)
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, batch_max=2, ring_capacity=16, flush_interval_s=10.0, backoff_min_s=0.3, backoff_max_s=1.0)
        handler.emit(_make_record("a"))
        handler.emit(_make_record("b"))
        assert _wait_until(lambda: len(handler_cls.requests) >= 1)  # the 500 was seen, backoff begun
        time.sleep(0.05)  # comfortably inside the 0.3s backoff wait
        handler_cls.status_code = 200  # let the held batch succeed once close() retries it
        handler.close()
        assert len(handler_cls.requests) >= 2
        body = json.loads(handler_cls.requests[-1][2])
        messages = [json.loads(line)["message"] for _, line in body["streams"][0]["values"]]
        assert messages == ["a", "b"]  # the held batch reached the fake, not just discarded
        assert "unshipped" not in capsys.readouterr().out


def test_successful_ship_updates_shipped_counter_and_last_success_timestamp(fake_loki):
    url, requests = fake_loki
    handler = _make_handler(url)
    try:
        before = time.time()
        for i in range(3):
            handler.emit(_make_record(f"m{i}"))
        assert _wait_until(lambda: handler.shipped_lines_total >= 3)
        assert handler.shipped_lines_total == 3
        assert handler.last_ship_success_at is not None
        assert before - 0.1 <= handler.last_ship_success_at <= time.time() + 0.1

        for i in range(2):  # a second successful batch accumulates, it does not replace
            handler.emit(_make_record(f"n{i}"))
        assert _wait_until(lambda: handler.shipped_lines_total == 5)
    finally:
        handler.close()


def test_shipped_counter_and_timestamp_only_move_on_the_ok_outcome(handler_factory):
    """dropped_total grows on 'drop'/ring-overflow; shipped_lines_total and
    last_ship_success_at are the 'ok'-only counterpart -- a poisoned (400) batch must leave
    them untouched, and only a later successful batch moves them."""
    handler_cls = handler_factory(status_code=400)
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, batch_max=3, ring_capacity=32)
        try:
            for i in range(3):
                handler.emit(_make_record(f"poison-{i}"))
            assert _wait_until(lambda: handler.dropped_total == 3)
            assert handler.shipped_lines_total == 0
            assert handler.last_ship_success_at is None

            handler_cls.status_code = 200
            for i in range(3):
                handler.emit(_make_record(f"good-{i}"))
            assert _wait_until(lambda: handler.shipped_lines_total == 3)
            assert handler.last_ship_success_at is not None
        finally:
            handler.close()


def test_close_joins_the_worker_thread_no_leak(fake_loki):
    url, _requests = fake_loki
    handler = _make_handler(url)
    worker = handler._worker
    assert worker.is_alive()  # the daemon worker is running
    handler.close()
    assert not worker.is_alive()  # joined -- no leaked thread


def test_last_cycle_timestamp_advances_on_an_idle_cycle(fake_loki):
    """T0106: the abort-signal gauge must mean 'the worker is alive', not 'Loki accepted
    something'. A healthy capture daemon is quiet, so an empty flush -- the ordinary steady
    state -- must still advance it, while last_ship_success_at correctly stays put."""
    url, _ = fake_loki
    handler = _make_handler(url)
    try:
        first = handler.last_cycle_at
        assert first is not None  # never absent: stamped at construction, so no 'no data' state
        assert handler.last_ship_success_at is None
        assert _wait_until(lambda: handler.last_cycle_at > first)  # nothing was emitted
        assert handler.last_ship_success_at is None  # ... and no ship was claimed
    finally:
        handler.close()


def test_last_cycle_timestamp_stalls_while_the_post_keeps_failing(handler_factory):
    """The other half: a shipper whose posts fail is NOT alive for this gauge's purpose, so a
    retrying cycle must not stamp it -- otherwise the row is green through a real outage."""
    handler_cls = handler_factory(status_code=500)  # 5xx -> 'retry', the wedged case
    with FakeLoki(handler_cls) as url:
        # Short backoff, so several failing cycles elapse inside the wait: spanning several of them is
        # what discriminates a variant that wrongly stamps on the retry path from one that does not.
        handler = _make_handler(url, batch_max=2, ring_capacity=32, backoff_min_s=0.05)
        try:
            for i in range(2):
                handler.emit(_make_record(f"m{i}"))
            assert _wait_until(lambda: len(handler_cls.requests) >= 1)
            # Seed AFTER the batch is held: until then the worker is idle and idle cycles legitimately
            # stamp every flush_interval_s, so a pre-emit seed made CORRECT code fail this. With a
            # batch held, no idle cycle can intervene and every later stamp would be the bug.
            seed = handler.last_cycle_at
            assert _wait_until(lambda: len(handler_cls.requests) >= 4)  # several failed cycles elapsed
            assert handler.last_cycle_at == seed, "a retrying cycle must not advance the liveness gauge"
        finally:
            handler_cls.status_code = 200
            handler.close()


def test_last_cycle_timestamp_is_exported_as_its_own_series(fake_loki):
    """It is a separate series, not a redefinition of the ship-success gauge -- both are
    published so a rule can tell 'worker dead' from 'Loki rejecting'."""
    from cli.obs.metrics import LogshipCollector

    url, _ = fake_loki
    handler = _make_handler(url)
    try:
        names = {m.name for m in LogshipCollector(handler).collect()}
        assert "zcrypto_logship_last_cycle_timestamp_seconds" in names
        assert "zcrypto_logship_last_success_timestamp_seconds" not in names  # no ship yet
    finally:
        handler.close()


def test_a_permanently_rejected_batch_still_advances_the_liveness_gauge(handler_factory):
    """The drop path IS a completed cycle: `cli/obs/metrics.py`'s HELP for the gauge and the alert
    rule's own comment both state it as contract."""
    handler_cls = handler_factory(status_code=400)  # non-429 4xx -> 'drop', permanently rejected
    with FakeLoki(handler_cls) as url:
        handler = _make_handler(url, batch_max=2, ring_capacity=32, flush_interval_s=5.0)
        try:
            seed = handler.last_cycle_at
            for i in range(2):
                handler.emit(_make_record(f"m{i}"))
            assert _wait_until(lambda: handler.dropped_total >= 2)  # the batch was rejected
            # flush_interval_s is 5 s, so no idle cycle can have run in the interim -- any advance
            # is the drop branch's own stamp, which is the property under test.
            assert handler.last_cycle_at > seed, "a discarded batch must still count as a completed cycle"
            assert handler.last_ship_success_at is None, "nothing shipped, so ship-success must not move"
        finally:
            handler.close()
