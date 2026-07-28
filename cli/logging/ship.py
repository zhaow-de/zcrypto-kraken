from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass

from cli.logging.formatters import JsonLineFormatter

# Bounded ring/batch/backoff tuning (spec 00068 D3) -- exact values, not defaults to be tuned later.
RING_CAPACITY = 4096
BATCH_MAX = 500
FLUSH_INTERVAL_S = 1.0
TIMEOUT_S = 5.0
BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 30.0
EXIT_DEADLINE_S = 2.0


@dataclass(frozen=True)
class ShipConfig:
    """Where to push and how to label it. `service` becomes the Loki `container` label, not
    `host` -- the two are independent axes (one host runs several containers/services)."""

    url: str
    username: str
    password: str
    host: str
    service: str


def build_payload(entries: list[tuple[str, str, str]], cfg: ShipConfig) -> bytes:
    """Serialize `(level, ts_ns, line)` entries as a Loki push-API request body: one stream
    per distinct level, labels exactly `{host, container, level}` (spec 00068), values in the
    order given (callers hand us entries already time-ordered)."""
    streams: dict[str, list[list[str]]] = {}
    for level, ts_ns, line in entries:
        streams.setdefault(level, []).append([ts_ns, line])
    body = {
        "streams": [
            {"stream": {"host": cfg.host, "container": cfg.service, "level": level}, "values": values}
            for level, values in streams.items()
        ]
    }
    return json.dumps(body).encode()


class _RedirectRefused(urllib.request.HTTPRedirectHandler):
    """Loki push never legitimately redirects; a 3xx must not re-send credentials elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _build_opener() -> urllib.request.OpenerDirector:
    # ProxyHandler({}) disables env-proxy pickup; without it a stray http_proxy would
    # reroute credentialed log traffic (spec 00068 D3).
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RedirectRefused())


class LokiShipHandler(logging.Handler):
    """Ships log records to Loki from a background thread; `emit()` only ever appends to a
    bounded in-memory ring under a short lock -- no network I/O runs on the caller's thread, so
    a dead or slow Loki can never block or crash the application (spec 00068 D3)."""

    def __init__(
        self,
        cfg: ShipConfig,
        *,
        ring_capacity: int = RING_CAPACITY,
        batch_max: int = BATCH_MAX,
        flush_interval_s: float = FLUSH_INTERVAL_S,
        timeout_s: float = TIMEOUT_S,
        backoff_min_s: float = BACKOFF_MIN_S,
        backoff_max_s: float = BACKOFF_MAX_S,
        exit_deadline_s: float = EXIT_DEADLINE_S,
    ) -> None:
        super().__init__()
        self.setFormatter(JsonLineFormatter())
        self._cfg, self._batch_max, self._flush_interval_s = cfg, batch_max, flush_interval_s
        self._timeout_s, self._backoff_min_s, self._backoff_max_s = timeout_s, backoff_min_s, backoff_max_s
        self._exit_deadline_s = exit_deadline_s
        self._ring: deque[tuple[str, str, str]] = deque(maxlen=ring_capacity)
        self._ring_lock = threading.Lock()
        self.dropped_total = 0
        self.shipped_lines_total = 0
        self.last_ship_success_at: float | None = (
            None  # unix ts of the last "ok" from the main loop; the exit flush (see _run) does not update it
        )
        # "the worker completed a cycle without failing" -- a different question from
        # last_ship_success_at's "Loki accepted something", and the one an abort/liveness row
        # wants (T0106). A healthy capture daemon is quiet, so an idle cycle stamps this too;
        # a retrying one does not. Seeded here so the series exists from startup rather than
        # being absent until the first ship -- "no data" and "stale" read differently.
        self.last_cycle_at: float = time.time()
        self._dropped_unannounced = 0
        self._held: list[tuple[str, str, str]] = []  # the one in-flight batch (part of the memory bound)
        self._auth = "Basic " + base64.b64encode(f"{cfg.username}:{cfg.password}".encode()).decode()
        self._opener = _build_opener()
        self._stop, self._wake = threading.Event(), threading.Event()
        self._worker = threading.Thread(target=self._run, name="zcrypto-log-ship", daemon=True)
        self._worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = (record.levelname, str(int(record.created * 1_000_000_000)), self.format(record))
            with self._ring_lock:
                if len(self._ring) == self._ring.maxlen:
                    self.dropped_total += 1  # deque evicts the oldest on append
                    self._dropped_unannounced += 1
                self._ring.append(entry)
                full_enough = len(self._ring) >= self._batch_max
            if full_enough:
                self._wake.set()
        except Exception:
            self.handleError(record)

    def _drain(self) -> list[tuple[str, str, str]]:
        with self._ring_lock:
            return [self._ring.popleft() for _ in range(min(len(self._ring), self._batch_max))]

    def _post(self, entries: list[tuple[str, str, str]]) -> str:
        """'ok' | 'retry' | 'drop' -- a non-429 4xx is permanently rejected (e.g. entries older
        than Loki's out-of-order window after a long outage); retrying it forever would wedge
        shipping silently (spec 00068 D3). Any other unexpected exception (e.g. a malformed
        `url` from a config typo) is also 'retry', never left to escape -- an unguarded raise
        here kills the worker thread permanently and silently, defeating D3's no-silent-
        dark-window guarantee."""
        try:
            req = urllib.request.Request(
                self._cfg.url,
                data=build_payload(entries, self._cfg),
                headers={"Content-Type": "application/json", "Authorization": self._auth},
                method="POST",
            )
            with self._opener.open(req, timeout=self._timeout_s):
                pass
            return "ok"
        except urllib.error.HTTPError as e:
            return "retry" if (e.code >= 500 or e.code == 429) else "drop"
        except urllib.error.URLError, OSError, TimeoutError:
            return "retry"
        except Exception:
            return "retry"

    def _run(self) -> None:
        backoff = self._backoff_min_s
        while not self._stop.is_set():
            self._wake.wait(self._flush_interval_s)
            self._wake.clear()
            if not self._held:
                self._held = self._drain()
            if not self._held:
                with self._ring_lock:
                    self.last_cycle_at = time.time()  # idle is the healthy steady state, not a stall
                continue
            outcome = self._post(self._held)
            if outcome == "ok":
                with self._ring_lock:
                    self.shipped_lines_total += len(self._held)
                    self.last_ship_success_at = self.last_cycle_at = time.time()
                self._held, backoff = [], self._backoff_min_s
                self._announce_recovery()
            elif outcome == "drop":
                with self._ring_lock:
                    self.dropped_total += len(self._held)
                    self._dropped_unannounced += len(self._held)
                    self.last_cycle_at = time.time()  # the batch was disposed of; the worker is alive
                self._held, backoff = [], self._backoff_min_s
            else:
                self._stop.wait(backoff)  # interruptible: close() never waits on this
                backoff = min(backoff * 2, self._backoff_max_s)
        while True:  # final best-effort flush; no retry loop
            if not self._held:
                self._held = self._drain()
            if not self._held or self._post(self._held) != "ok":
                break
            self._held = []

    def _announce_recovery(self) -> None:
        with self._ring_lock:
            n, self._dropped_unannounced = self._dropped_unannounced, 0
        if n:
            logging.getLogger("zcrypto.logging.ship").warning("log shipping recovered; %d lines dropped while unreachable", n)

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self._worker.join(self._exit_deadline_s)  # the app's exit-path bound; the daemon
        left = len(self._held) + len(self._ring)  # thread dies with the interpreter if late
        if left:
            print(f"zcrypto log shipping: {left} lines unshipped at exit", flush=True)
        super().close()
