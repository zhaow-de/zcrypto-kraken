from __future__ import annotations

import logging
import os
from collections.abc import Iterator

from prometheus_client import CollectorRegistry, ProcessCollector, disable_created_metrics, start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric

from cli.logging import get_logger
from cli.logging.ship import LokiShipHandler

logger = get_logger("obs.metrics")

METRICS_PORT_ENV_VAR = "ZCRYPTO_METRICS_PORT"

# `_created` series (one per `Counter`, e.g. `zcrypto_engine_orders_created`) are in no daemon's keep-list, so they scrape as
# unregistered noise (spec 00069 D2); `_use_created` is process-global and read at render time, so this one call covers all.
disable_created_metrics()


def find_ship_handler() -> LokiShipHandler | None:
    """The live `--ship-logs` handler (`cli/logging/config.py` marks it `_zcrypto_owned`), or `None` -- `cli/__main__.py`'s
    root callback configures logging before any subcommand body, so `None` is opt-out, never not-yet-configured."""
    for h in logging.getLogger("zcrypto").handlers:
        if isinstance(h, LokiShipHandler) and getattr(h, "_zcrypto_owned", False):
            return h
    return None


def build_registry() -> CollectorRegistry:
    """A fresh registry carrying the `ProcessCollector` families plus a `LogshipCollector` bound to this process's live
    `--ship-logs` handler -- never `prometheus_client`'s global default, whose `python_gc_*`/`python_info` collectors are
    unpublished noise here (spec 00069 D2). Every daemon builds its registry here, so the tap is live wherever logs ship."""
    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    registry.register(LogshipCollector(find_ship_handler()))
    return registry


def metrics_port_from_env() -> int | None:
    """`ZCRYPTO_METRICS_PORT` unset, empty or non-integer means no exporter: ansible renders it unguarded, so a typo must
    never stop the daemon it is attached to -- a bad value logs one ERROR and returns `None`, never raises (spec 00069 D5)."""
    raw = os.environ.get(METRICS_PORT_ENV_VAR)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.error("%s is not a valid integer port: %r -- running without the metrics exporter", METRICS_PORT_ENV_VAR, raw)
        return None


def start_metrics_server(port: int, registry: CollectorRegistry) -> bool:
    """Start the `/metrics` HTTP server for `registry`: True = serving, False = failed, logged as one ERROR and never raised,
    because telemetry may never kill a daemon (spec 00069 D5) -- `start_http_server` binds before spawning its thread, so a
    False leaks nothing. `addr="0.0.0.0"` is required, not lax: bridge-networked containers get published-port traffic on
    eth0, never loopback, and the security boundary is the host-side compose publish `127.0.0.1:<port>:<port>`."""
    try:
        start_http_server(port, addr="0.0.0.0", registry=registry)
        return True
    except Exception:
        logger.error("failed to start the metrics server on port %d -- continuing without it", port, exc_info=True)
        return False


class LogshipCollector:
    """Exposes a live `LokiShipHandler`'s counters as scrape-time series; with no handler (`--ship-logs` off) `collect()`
    yields NOTHING -- an absent family is honest, a published zero would falsely claim log shipping runs (spec 00069 D5)."""

    def __init__(self, handler: LokiShipHandler | None) -> None:
        self._handler = handler

    def collect(self) -> Iterator[Metric]:
        handler = self._handler
        if handler is None:
            return
        # The worker's own lock (`cli/logging/ship.py`) -- a scrape racing it sees one consistent snapshot, never a
        # partially-updated mix of old and new values.
        with handler._ring_lock:
            dropped = handler.dropped_total
            shipped = handler.shipped_lines_total
            last_success = handler.last_ship_success_at
            last_cycle = handler.last_cycle_at
        yield CounterMetricFamily(
            "zcrypto_logship_dropped_lines_total", "Log lines dropped by the Loki ship handler.", value=dropped
        )
        yield CounterMetricFamily("zcrypto_logship_shipped_lines_total", "Log lines successfully shipped to Loki.", value=shipped)
        # Liveness only, published from startup: last_success is stale whenever logging is quiet, and a discarded batch still
        # advances this gauge -- "is anything reaching Loki?" is dropped_lines_total's question, not this one.
        yield GaugeMetricFamily(
            "zcrypto_logship_last_cycle_timestamp_seconds",
            "Unix timestamp of the last log-shipping cycle the worker completed -- idle, shipped, or batch discarded.",
            value=last_cycle,
        )
        if last_success is not None:  # absent until the first success -- see the class docstring
            yield GaugeMetricFamily(
                "zcrypto_logship_last_success_timestamp_seconds",
                "Unix timestamp of the last successful Loki ship.",
                value=last_success,
            )
