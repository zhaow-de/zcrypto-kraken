from __future__ import annotations

import logging
import socket
import urllib.request

from prometheus_client import CollectorRegistry, generate_latest

from cli.obs.metrics import METRICS_PORT_ENV_VAR, build_registry, metrics_port_from_env, start_metrics_server


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
