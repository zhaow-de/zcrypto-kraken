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

# A published-but-unadmitted series is a trap in as many words (spec 00069 D2): `Counter`'s
# default OpenMetrics `_created` series (one per Counter, e.g. `zcrypto_engine_orders_created`)
# is exposed today but is not in any daemon's keep-list, so it would scrape as unregistered noise.
# `_use_created` is a process-global flag `prometheus_client` reads at render time, not at
# `Counter.__init__` time -- disabling it once here (module import) suppresses `_created` for
# every Counter in the process regardless of when it was constructed.
disable_created_metrics()


def find_ship_handler() -> LokiShipHandler | None:
    """The live --ship-logs handler (cli/logging/config.py marks it `_zcrypto_owned`), or `None`
    when this daemon wasn't started with `--ship-logs`. The root Typer callback (`cli/__main__.py`)
    runs `configure(...)` before any subcommand body, so the handler already exists by the time a
    subcommand calls `build_registry()`."""
    for h in logging.getLogger("zcrypto").handlers:
        if isinstance(h, LokiShipHandler) and getattr(h, "_zcrypto_owned", False):
            return h
    return None


def build_registry() -> CollectorRegistry:
    """A fresh, isolated `CollectorRegistry` carrying the `ProcessCollector` families
    (`process_cpu_seconds_total`, `process_max_fds`, `process_open_fds`,
    `process_resident_memory_bytes`, `process_start_time_seconds`, `process_virtual_memory_bytes`)
    plus a `LogshipCollector` bound to whatever `--ship-logs` handler (if any) is live on this
    process -- never `prometheus_client`'s global default registry, whose `python_gc_*`/`python_info`
    collectors are unpublished noise here (spec 00069 D2). All four daemons share this one call
    site, so registering the logship tap here (rather than per daemon) is what makes it actually
    live everywhere `--ship-logs` runs."""
    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    registry.register(LogshipCollector(find_ship_handler()))
    return registry


def metrics_port_from_env() -> int | None:
    """Read `ZCRYPTO_METRICS_PORT`: unset or empty means opt-out (no exporter). Ansible renders
    this env var unguarded (no deploy-time validation), so a typo here must never be able to
    stop the daemon it's attached to (spec 00069 D5, cold-review I6) -- on a non-integer value,
    log ERROR naming the bad value and return None (run without the exporter), never raise."""
    raw = os.environ.get(METRICS_PORT_ENV_VAR)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.error("%s is not a valid integer port: %r -- running without the metrics exporter", METRICS_PORT_ENV_VAR, raw)
        return None


def start_metrics_server(port: int, registry: CollectorRegistry) -> bool:
    """Start the `/metrics` HTTP server for `registry`. True = serving; False = failed to
    start (port in use, permission denied, ...) -- logged as exactly one ERROR, never raised:
    telemetry may never kill a daemon (spec 00069 D5). `prometheus_client.start_http_server`
    binds its socket before spawning the serving thread, so a failure here means no thread was
    ever started -- nothing to leak.

    `addr="0.0.0.0"` is REQUIRED, not lax (cold-review C1): the app containers are
    bridge-networked, and Docker delivers published-port traffic to the container's eth0,
    never its loopback -- an inside-`127.0.0.1` bind would refuse every scrape (`up=0`
    fleet-wide). The security boundary is the HOST-side compose publish
    `127.0.0.1:<port>:<port>`, not this bind.
    """
    try:
        start_http_server(port, addr="0.0.0.0", registry=registry)
        return True
    except Exception:
        logger.error("failed to start the metrics server on port %d -- continuing without it", port, exc_info=True)
        return False


class LogshipCollector:
    """Exposes a live `LokiShipHandler`'s counters as scrape-time series: `handler` may be
    `None` (this daemon wasn't started with `--ship-logs`) -- `collect()` then yields NOTHING.
    An absent family is honest (log shipping isn't running here); a published zero would
    falsely claim it is (spec 00069 D5)."""

    def __init__(self, handler: LokiShipHandler | None) -> None:
        self._handler = handler

    def collect(self) -> Iterator[Metric]:
        handler = self._handler
        if handler is None:
            return
        # Same lock the worker mutates dropped_total/shipped_lines_total/last_ship_success_at
        # under (cli/logging/ship.py) -- a scrape racing the worker sees one consistent
        # snapshot, never a partially-updated mix of old and new values.
        with handler._ring_lock:
            dropped = handler.dropped_total
            shipped = handler.shipped_lines_total
            last_success = handler.last_ship_success_at
            last_cycle = handler.last_cycle_at
        yield CounterMetricFamily(
            "zcrypto_logship_dropped_lines_total", "Log lines dropped by the Loki ship handler.", value=dropped
        )
        yield CounterMetricFamily("zcrypto_logship_shipped_lines_total", "Log lines successfully shipped to Loki.", value=shipped)
        # Liveness, published from startup: the shipper goes quiet whenever logging is quiet, so
        # last_success below is stale in ordinary steady state and cannot answer "is it alive?".
        # It answers ONLY that -- a permanently-rejected batch (non-429 4xx) still advances it, because the
        # worker did complete a cycle. "Is anything reaching Loki?" is dropped_lines_total's question,
        # and conflating the two is what made last_success useless for liveness in the first place.
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
