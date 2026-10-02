"""Resolve vaulted credentials for the Grafana scripts.
Two decrypt footguns whose failures MISLEAD: reading `vault_password_file` instead of executing it
surfaces as "no vault secrets were found that could decrypt", which reads as a wrong key rather
than a wrong method; and reading a `!vault` scalar without an initialized `VaultSecretsContext`
raises ReferenceError rather than a vault error. Credentials are returned as locals for the caller
to place in a request header: never printed, never written, never in argv where `ps` would show
it.
"""

from __future__ import annotations

import configparser
import subprocess
from pathlib import Path
from typing import NamedTuple

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
VAULT_FILE = "group_vars/all/vault.yml"


class Stack(NamedTuple):
    """One Grafana the tools address: where it answers, and the vault variable and file holding its token."""

    url: str
    token_var: str
    vault_file: str


# Baked in rather than re-guessed: a wrong URL or datasource uid is accepted happily and still reports
# health=ok, so a guess fails silently. Two stacks until the Grafana Cloud leg retires. `mon`'s token is
# minted by the `mon` role into a vault-encrypted cache outside the tree, the role's `mon_token_cache` and
# `mon_token_var`; `vault_var` reads an absolute file where it is.
STACKS = {
    "cloud": Stack("https://zcrypto2026.grafana.net", "grafana_sa_token", VAULT_FILE),
    "mon": Stack(
        "https://zcrypto-mon.zhaow.me", "mon_grafana_tools_token", str(Path.home() / ".config/zcrypto/grafana-mon.vault.yml")
    ),
}
# The stack a tool reads when none is named: the one that pages.
DEFAULT_STACK = "cloud"
GRAFANA_URL = STACKS[DEFAULT_STACK].url


def stack(name: str = DEFAULT_STACK) -> Stack:
    if name not in STACKS:
        raise SystemExit(f"unknown stack {name!r}: one of {', '.join(sorted(STACKS))}")
    return STACKS[name]


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
    Safe to call more than once: a second `VaultSecretsContext.initialize` raises RuntimeError
    ("already initialized"), which would crash mid-run on the second credential read rather than
    reporting a vault problem.
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
    """One variable's plaintext out of a per-variable-encrypted vault file; `vault_file` is a
    parameter because the credentials live in different group vaults.
    """
    loader, _ = _load_ansible_vault()
    return str(loader.load_from_file(str(ANSIBLE_DIR / vault_file))[name])
