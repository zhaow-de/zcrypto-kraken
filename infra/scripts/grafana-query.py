#!/usr/bin/env python3
"""Read PromQL, or with --loki a LogQL metric query, from a Grafana stack with its vaulted service-account token.
    uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' hc_check_up
    uv run python infra/scripts/grafana-query.py --loki 'sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))'
    uv run python infra/scripts/grafana-query.py --stack mon 'up{host="zcrypto-mon"}'
`--stack` names one of `grafana_auth.STACKS`; with none, the default stack, the one that pages, is read.
NOT for alert states: `ALERTS{alertstate="firing"}` is Prometheus-native and structurally EMPTY
for Grafana-managed rules, which is all of ours, so its `(no series)` reads as "nothing firing"
whatever is true -- read rule states from `GET /api/prometheus/grafana/api/v1/rules` with the same
bearer token. The token is only ever a request header: never printed, never written, never in
argv.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_AUTH = Path(__file__).resolve().parent / "grafana_auth.py"
_auth_spec = importlib.util.spec_from_file_location("grafana_auth", _AUTH)
grafana_auth = importlib.util.module_from_spec(_auth_spec)
_auth_spec.loader.exec_module(grafana_auth)

GRAFANA_URL = grafana_auth.GRAFANA_URL
vault_var = grafana_auth.vault_var

PROM_DS_UID = "grafanacloud-prom"
LOKI_DS_UID = "grafanacloud-logs"


def endpoint(expr: str, loki: bool = False) -> str:
    """The instant-query URL through the Grafana datasource proxy, so the stack's own auth is what is used. It reads
    `GRAFANA_URL` when called: `main` rebinds that name to the stack it was asked for."""
    ds_uid, path = (LOKI_DS_UID, "loki/api/v1/query") if loki else (PROM_DS_UID, "api/v1/query")
    return f"{GRAFANA_URL}/api/datasources/proxy/uid/{ds_uid}/{path}?" + urllib.parse.urlencode({"query": expr})


def query(expr: str, token: str, loki: bool = False) -> list[dict]:
    request = urllib.request.Request(endpoint(expr, loki), headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed https endpoint
        return json.load(response)["data"]["result"]


def main(argv: list[str]) -> int:
    global GRAFANA_URL
    loki = "--loki" in argv
    argv = [a for a in argv if a != "--loki"]
    name = grafana_auth.DEFAULT_STACK
    if "--stack" in argv:
        at = argv.index("--stack")
        name, argv = (argv[at + 1] if at + 1 < len(argv) else ""), argv[:at] + argv[at + 2 :]
    if not argv or name not in grafana_auth.STACKS:
        print(__doc__.strip().splitlines()[0])
        print(f"usage: grafana-query.py [--stack {'|'.join(sorted(grafana_auth.STACKS))}] [--loki] '<query>' ['<query>' ...]")
        return 2
    GRAFANA_URL = grafana_auth.stack(name).url
    token = grafana_auth.token(name)
    failed = False
    for expr in argv:
        # The RENDER is inside the try, not just the request: a scalar (`1`) or a range selector
        # (`up[1m]`) returns a shape without `metric`/`value`, and rendering it outside would raise
        # past the handler and drop every expression after it -- the exact hiding this guards against.
        try:
            print(expr)
            series = query(expr, token, loki=loki)
            if not series:
                # An empty result is NOT the same as a zero, and a gate that reads it as one is why
                # this says so out loud: absent series and a series at 0 fail differently.
                print("  (no series)")
                continue
            for s in series:
                labels = ", ".join(f"{k}={v}" for k, v in sorted(s["metric"].items()) if k != "__name__")
                print(f"  {{{labels}}} = {s['value'][1]}")
        except Exception as exc:  # noqa: BLE001 -- one bad expression must not hide the others
            print(f"  ERROR {type(exc).__name__}: {exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
