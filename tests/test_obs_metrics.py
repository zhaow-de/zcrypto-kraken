from __future__ import annotations

import logging
import socket
import threading
import time
import urllib.request

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from cli.logging.ship import LokiShipHandler, ShipConfig
from cli.obs.metrics import (
    METRICS_PORT_ENV_VAR,
    LogshipCollector,
    build_registry,
    metrics_port_from_env,
    start_metrics_server,
)
from tests.fake_loki import FakeLoki
from tests.fake_loki import handler_factory as _handler_factory

# Tight worker timings so ship-handler-backed tests stay fast; mirrors tests/test_logging_ship_handler.py.
_TIGHT = {"flush_interval_s": 0.02, "timeout_s": 0.3, "backoff_min_s": 0.05, "backoff_max_s": 0.2, "exit_deadline_s": 0.5}


@pytest.fixture
def handler_factory():
    return _handler_factory


@pytest.fixture
def fake_loki(handler_factory):
    handler_cls = handler_factory()
    with FakeLoki(handler_cls) as url:
        yield url, handler_cls.requests


def _cfg(url: str) -> ShipConfig:
    return ShipConfig(url=f"{url}/loki/api/v1/push", username="alice", password="secret", host="h1", service="svc1")


def _make_handler(url: str, **overrides) -> LokiShipHandler:
    return LokiShipHandler(_cfg(url), **{**_TIGHT, **overrides})


def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(name="test", level=logging.INFO, pathname="test.py", lineno=1, msg=msg, args=(), exc_info=None)


def _wait_until(predicate, timeout: float = 1.0, interval: float = 0.005) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _free_port() -> int:
    """Ask the OS for an unused port: bind ephemeral (port 0), read back the assigned number,
    release it immediately -- the same "let the OS pick" technique tests/fake_loki.py uses,
    adapted for a function (start_metrics_server) that takes a port NUMBER rather than binding
    for us."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        return resp.read().decode()


def _render(registry: CollectorRegistry) -> str:
    return generate_latest(registry).decode()


class TestBuildRegistry:
    def test_contains_process_families_and_nothing_else(self):
        text = _render(build_registry())
        for family in (
            "process_cpu_seconds_total",
            "process_resident_memory_bytes",
            "process_open_fds",
            "process_start_time_seconds",
        ):
            assert family in text
        assert "python_gc_" not in text  # default-registry noise (spec 00069 D2) -- must not appear
        assert "python_info" not in text


class TestMetricsPortFromEnv:
    def test_unset_is_none(self, monkeypatch):
        monkeypatch.delenv(METRICS_PORT_ENV_VAR, raising=False)
        assert metrics_port_from_env() is None

    def test_valid_integer_string_is_parsed(self, monkeypatch):
        monkeypatch.setenv(METRICS_PORT_ENV_VAR, "9101")
        assert metrics_port_from_env() == 9101

    def test_empty_string_is_none(self, monkeypatch):
        monkeypatch.setenv(METRICS_PORT_ENV_VAR, "")
        assert metrics_port_from_env() is None

    def test_non_integer_logs_one_error_naming_the_var_and_value_then_returns_none(self, monkeypatch, caplog):
        monkeypatch.setenv(METRICS_PORT_ENV_VAR, "x")
        with caplog.at_level(logging.ERROR):
            result = metrics_port_from_env()
        assert result is None
        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1  # a deploy typo must never look like a crash-worthy event
        message = errors[0].getMessage()
        assert METRICS_PORT_ENV_VAR in message
        assert "x" in message


class TestStartMetricsServer:
    def test_serves_the_exposition_format(self):
        port = _free_port()
        registry = build_registry()
        assert start_metrics_server(port, registry) is True
        body = _get(f"http://127.0.0.1:{port}/metrics")
        assert "process_resident_memory_bytes" in body

    def test_port_already_taken_returns_false_logs_once_never_raises(self, caplog):
        # A plain socket occupies the port BEFORE start_metrics_server ever touches it, so a
        # bind failure is guaranteed regardless of timing.
        port = _free_port()
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("0.0.0.0", port))
        blocker.listen()
        try:
            with caplog.at_level(logging.ERROR):
                result = start_metrics_server(port, build_registry())
            assert result is False  # no server object is ever handed back -- nothing to leak
            errors = [r for r in caplog.records if r.levelno == logging.ERROR]
            assert len(errors) == 1
        finally:
            blocker.close()


class TestLogshipCollector:
    def test_absent_families_when_no_handler_is_configured(self):
        """absence is honest, zero is a claim: with ship_handler=None (no --ship-logs on this
        daemon), the collector must publish NOTHING for these families, not zeros."""
        registry = CollectorRegistry()
        registry.register(LogshipCollector(None))
        text = _render(registry)
        assert "zcrypto_logship_dropped_lines_total" not in text
        assert "zcrypto_logship_shipped_lines_total" not in text
        assert "zcrypto_logship_last_success_timestamp_seconds" not in text

    def test_renders_all_three_families_from_a_live_handler(self, fake_loki):
        url, requests = fake_loki
        handler = _make_handler(url)
        try:
            handler.emit(_make_record("hello"))
            assert _wait_until(lambda: handler.shipped_lines_total >= 1)

            registry = CollectorRegistry()
            registry.register(LogshipCollector(handler))
            text = _render(registry)
            assert "zcrypto_logship_dropped_lines_total 0.0" in text
            assert "zcrypto_logship_shipped_lines_total 1.0" in text
            assert "zcrypto_logship_last_success_timestamp_seconds" in text
        finally:
            handler.close()

    def test_last_success_family_absent_before_any_successful_ship(self, handler_factory):
        handler_cls = handler_factory(status_code=500)
        with FakeLoki(handler_cls) as url:
            handler = _make_handler(url, batch_max=1, ring_capacity=8)
            try:
                handler.emit(_make_record("still-retrying"))
                assert _wait_until(lambda: len(handler_cls.requests) >= 1)  # a failed attempt happened

                registry = CollectorRegistry()
                registry.register(LogshipCollector(handler))
                text = _render(registry)
                assert "zcrypto_logship_shipped_lines_total 0.0" in text
                assert "zcrypto_logship_last_success_timestamp_seconds" not in text  # no success has ever happened
            finally:
                handler.close()

    def test_collect_snapshots_under_the_same_lock_the_worker_mutates_under(self, fake_loki):
        """The 'tolerates a handler mid-mutation' property, exercised directly: while the test
        thread holds `_ring_lock` (standing in for the worker mid-update), a concurrent
        collect() must block rather than read a partial snapshot -- proving it takes the same
        lock, not merely a copy made without one."""
        url, requests = fake_loki
        handler = _make_handler(url)
        try:
            handler.emit(_make_record("hello"))
            assert _wait_until(lambda: handler.shipped_lines_total >= 1)  # so all three families are due

            collector = LogshipCollector(handler)
            done = threading.Event()
            families: list = []
            with handler._ring_lock:
                t = threading.Thread(target=lambda: (families.extend(collector.collect()), done.set()))
                t.start()
                time.sleep(0.05)
                assert not done.is_set()  # blocked behind the held lock
            t.join(timeout=1.0)
            assert done.is_set()
            assert len(families) == 3
        finally:
            handler.close()
