from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

# Bounded ring/batch/backoff tuning (spec 00068 D3) -- exact values, not defaults to be
# tuned later. Tests override them via LokiShipHandler kwargs; production always uses these.
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
