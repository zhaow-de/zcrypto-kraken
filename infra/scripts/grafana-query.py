#!/usr/bin/env python3
"""Read PromQL from Grafana Cloud, using the vaulted service-account token.

The capture-rollout gate needs a Cloud read-back (`up{job="capture_app"} == 1`, `hc_check_up`)
that no repo tooling provided: `grafana-push.sh` REQUIRES `GRAFANA_SA_TOKEN` already in the
environment and never obtains it, so every caller improvised the decrypt. This is that operand.

    uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' hc_check_up

NOT for alert states: `ALERTS{alertstate="firing"}` is a Prometheus-native metric and is
structurally EMPTY for Grafana-managed rules (which is all of ours), so its `(no series)` reads
as "nothing firing" regardless of reality. Read rule states from the API instead:
`GET /api/prometheus/grafana/api/v1/rules` with the same bearer token.

The vaulted service-account token is resolved by `grafana_auth.py`, the sibling both Grafana
scripts share.

The token is resolved into a local and used only as a request header: never printed, never written,
never placed in argv where `ps` would show it.
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

# Re-exported so this module's own callers and tests keep one import site.
ANSIBLE_DIR = grafana_auth.ANSIBLE_DIR
GRAFANA_URL = grafana_auth.GRAFANA_URL
vault_password_file = grafana_auth.vault_password_file
vault_password = grafana_auth.vault_password
vault_var = grafana_auth.vault_var

PROM_DS_UID = "grafanacloud-prom"


def query(expr: str, token: str) -> list[dict]:
    """Instant query through the Grafana datasource proxy, so the stack's own auth is what is used."""
    endpoint = f"{GRAFANA_URL}/api/datasources/proxy/uid/{PROM_DS_UID}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    request = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- fixed https endpoint
        return json.load(response)["data"]["result"]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: grafana-query.py '<promql>' ['<promql>' ...]")
        return 2
    token = vault_var("grafana_sa_token")
    failed = False
    for expr in argv:
        # The RENDER is inside the try, not just the request: a scalar (`1`) or a range selector
        # (`up[1m]`) returns a shape without `metric`/`value`, and rendering it outside would raise
        # past the handler and drop every expression after it -- the exact hiding this guards against.
        try:
            print(expr)
            series = query(expr, token)
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
