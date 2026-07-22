from __future__ import annotations

import os

from prometheus_client import CollectorRegistry, ProcessCollector, start_http_server

from cli.logging import get_logger

logger = get_logger("obs.metrics")

METRICS_PORT_ENV_VAR = "ZCRYPTO_METRICS_PORT"


def build_registry() -> CollectorRegistry:
    """A fresh, isolated `CollectorRegistry` carrying ONLY the `ProcessCollector` families
    (`process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_open_fds`,
    `process_start_time_seconds`) -- never `prometheus_client`'s global default registry,
    whose `python_gc_*`/`python_info` collectors are unpublished noise here (spec 00069 D2)."""
    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
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
