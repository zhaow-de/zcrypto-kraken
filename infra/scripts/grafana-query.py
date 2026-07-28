#!/usr/bin/env python3
"""Read PromQL from Grafana Cloud, using the vaulted service-account token.

The capture-rollout gate needs a Cloud read-back (`up{job="capture_app"} == 1`, `hc_check_up`)
that no repo tooling provided: `grafana-push.sh` REQUIRES `GRAFANA_SA_TOKEN` already in the
environment and never obtains it, so every caller improvised the decrypt. This is that operand.

    uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' hc_check_up

Two decrypt footguns, both of which cost a live rollout an error-and-retry, are handled here so
nobody meets them again:

  * `vault_password_file` in `ansible.cfg` names an EXECUTABLE (`scripts/vault-pass.sh`, a GPG
    helper), not a file containing a password. Reading its bytes yields shell source, and the
    failure surfaces as "no vault secrets were found that could decrypt" — which reads as a wrong
    key rather than a wrong method.
  * `group_vars/all/vault.yml` uses per-variable `!vault |` scalars, so `ansible-vault view` cannot
    yield one key, and decrypting a scalar additionally requires an initialized
    `VaultSecretsContext` — without it, str() on the value raises ReferenceError, not a vault error.

The token is resolved into a local and used only as a request header: never printed, never written,
never placed in argv where `ps` would show it.
"""

from __future__ import annotations

import configparser
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
VAULT_FILE = "group_vars/all/vault.yml"

# Defaults are this project's verified values, deliberately baked in rather than re-guessed: a wrong
# datasource uid is accepted happily and still reports health=ok, so a guess fails silently.
GRAFANA_URL = "https://zcrypto2026.grafana.net"
PROM_DS_UID = "grafanacloud-prom"


def vault_password_file() -> Path:
    """The `vault_password_file` from `ansible.cfg`, resolved against the ansible directory."""
    cfg = configparser.ConfigParser()
    cfg.read(ANSIBLE_DIR / "ansible.cfg")
    return ANSIBLE_DIR / cfg["defaults"]["vault_password_file"]


def vault_password() -> bytes:
    """EXECUTE the password helper and take its stdout. It is a script, not a password file."""
    return subprocess.run([str(vault_password_file())], capture_output=True, check=True).stdout.strip()


_CONTEXT_READY = False


def vault_var(name: str) -> str:
    """One variable's plaintext out of the per-variable-encrypted vault.

    Safe to call more than once: `VaultSecretsContext.initialize` raises RuntimeError on a second
    call ("already initialized"), which would turn reading a second credential -- `slack_webhook_url`,
    the healthchecks admin token -- into a crash mid-gate. The flag makes that a no-op instead.
    """
    global _CONTEXT_READY
    from ansible.parsing.dataloader import DataLoader
    from ansible.parsing.vault import VaultSecret, VaultSecretsContext

    secrets = [("default", VaultSecret(vault_password()))]
    if not _CONTEXT_READY:
        # Load-bearing, and it looks like dead setup because it returns nothing and `secrets` is
        # passed again below: WITHOUT it, str() on a `!vault` scalar raises ReferenceError.
        VaultSecretsContext.initialize(VaultSecretsContext(secrets=secrets))
        _CONTEXT_READY = True
    loader = DataLoader()
    loader.set_vault_secrets(secrets)
    return str(loader.load_from_file(str(ANSIBLE_DIR / VAULT_FILE))[name])


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
