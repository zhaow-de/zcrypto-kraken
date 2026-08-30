"""Resolve vaulted credentials for the Grafana scripts, once, in one place.

Two decrypt footguns, both of which cost a live rollout an error-and-retry, are handled here so
nobody meets them again:

  * `vault_password_file` in `ansible.cfg` names an EXECUTABLE (`scripts/vault-pass.sh`, a GPG
    helper), not a file containing a password. Reading its bytes yields shell source, and the
    failure surfaces as "no vault secrets were found that could decrypt" — which reads as a wrong
    key rather than a wrong method.
  * A vault file uses per-variable `!vault |` scalars, so `ansible-vault view` cannot yield one key,
    and decrypting a scalar additionally requires an initialized `VaultSecretsContext` — without it,
    str() on the value raises ReferenceError, not a vault error.

Credentials are returned as locals for the caller to place in a request header: never printed, never
written, never placed in argv where `ps` would show it.
"""

from __future__ import annotations

import configparser
import subprocess
from pathlib import Path

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
VAULT_FILE = "group_vars/all/vault.yml"

# Deliberately baked in rather than re-guessed: a wrong datasource uid is accepted happily and still
# reports health=ok, so a guess fails silently.
GRAFANA_URL = "https://zcrypto2026.grafana.net"


def vault_password_file() -> Path:
    """The `vault_password_file` from `ansible.cfg`, resolved against the ansible directory."""
    cfg = configparser.ConfigParser()
    cfg.read(ANSIBLE_DIR / "ansible.cfg")
    return ANSIBLE_DIR / cfg["defaults"]["vault_password_file"]


def vault_password() -> bytes:
    """EXECUTE the password helper and take its stdout. It is a script, not a password file."""
    return subprocess.run([str(vault_password_file())], capture_output=True, check=True).stdout.strip()


_CONTEXT_READY = False


def _load_ansible_vault():
    """A loader that can read `!vault` scalars, and the secrets it was given.

    Safe to call more than once: `VaultSecretsContext.initialize` raises RuntimeError on a second
    call ("already initialized"), which would turn reading a second credential -- the Slack webhook,
    the healthchecks read-only key -- into a crash mid-run. The flag makes that a no-op instead.
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
    return loader, secrets


def vault_var(name: str, vault_file: str = VAULT_FILE) -> str:
    """One variable's plaintext out of a per-variable-encrypted vault file.

    `vault_file` is a parameter because the credentials live in different group vaults: the Grafana
    token in `all/`, the engine's healthcheck URL in `engine_host/`, the healthchecks admin key in
    `capture_host/`.
    """
    loader, _ = _load_ansible_vault()
    return str(loader.load_from_file(str(ANSIBLE_DIR / vault_file))[name])
