from __future__ import annotations

import json
import logging
import threading
import time

import pytest

from cli.logging.formatters import JsonLineFormatter
from cli.logging.ship import LokiShipHandler, ShipConfig
from tests.fake_loki import FakeLoki, SilentServer
from tests.fake_loki import handler_factory as _handler_factory

# Tightened timings (per the plan) so the suite stays fast; the *ratios* between them (min <<
# max, timeout > flush_interval) are what several tests' properties depend on, not these
# absolute numbers.
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
    """The property (not absolute timings, which flake in CI): starts near the floor, grows
    (not flat) on the first uncapped step, never decreases, and settles at the ceiling."""
    slack = backoff_min_s  # generous relative to the min/max spread used by these tests
    assert len(gaps) >= 3
    assert gaps[0] <= backoff_min_s + slack  # starts near the floor
    assert gaps[1] > gaps[0] * 1.3  # genuinely grows early on, not a flat retry interval
    for a, b in zip(gaps, gaps[1:]):
        assert b >= a - slack  # never decreases
    assert backoff_max_s - slack <= gaps[-1] <= backoff_max_s + slack  # reaches the cap and stays there
    assert backoff_max_s - slack <= gaps[-2] <= backoff_max_s + slack


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
            warnings = [r for r in console.records if "recovered" in r.getMessage()]
            assert len(warnings) == 1
            assert warnings[0].getMessage() == "log shipping recovered; 3 lines dropped while unreachable"

            def _warning_shipped() -> bool:
                return any(b"recovered" in body for _, _, body in handler_cls.requests)

            assert _wait_until(_warning_shipped)
        finally:
            handler.close()


def test_recovery_warning_exact_count_after_ring_overflow(handler_factory, ship_logger):
    """Ring overflow (distinct from the 400 poisoned-batch drop, tested separately above):
    batch_max is set larger than ring_capacity, so the worker's first drain always empties the
    WHOLE ring in one shot (`min(len(ring), batch_max)` == len(ring) whenever batch_max exceeds
    capacity). Triggering that drain explicitly (rather than waiting on the periodic timer)
    guarantees it happens only after the whole overflow burst has landed, keeping dropped_total
    deterministic, and leaves the ring empty for the rest of the outage -- so when the held
    batch finally succeeds, the recovery warning lands in an EMPTY ring, not a full one (a full
    ring would evict its own just-appended warning entry, triggering a second, spurious
    recovery announcement for that one extra drop)."""
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


def test_close_joins_the_worker_thread_no_leak(fake_loki):
    url, _requests = fake_loki
    baseline = threading.active_count()
    handler = _make_handler(url)
    assert threading.active_count() == baseline + 1  # the daemon worker is running
    handler.close()
    assert threading.active_count() == baseline  # joined -- no leaked thread
