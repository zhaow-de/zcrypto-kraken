"""Resolve vaulted credentials for the Grafana scripts, and on load make their `urlopen` close first.
Credentials are returned as locals for the caller to place in a request header: never printed, never written,
never in argv where `ps` would show it.
"""

from __future__ import annotations

import configparser
import http.client
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
VAULT_FILE = "group_vars/all/vault.yml"


class _ClientClosesFirst(http.client.HTTPSConnection):
    """Drops the `Connection: close` urllib hard-codes. With it the server closes first and keeps state on a public port the
    workstation's NAT hands out again at once, and a later connection landing on that state hangs in its TLS handshake.
    Without it this side closes first, and the server keeps nothing."""

    def request(self, method, url, body=None, headers={}, *, encode_chunked=False):  # the library's own signature
        kept = {name: value for name, value in headers.items() if name.lower() != "connection"}
        super().request(method, url, body, kept, encode_chunked=encode_chunked)


class _ClientClosesFirstHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_ClientClosesFirst, req, context=self._context)


# Process-wide, so a tool that loads this module and calls `urlopen` on an https URL with no `context` closes first.
urllib.request.install_opener(urllib.request.build_opener(_ClientClosesFirstHandler()))


class Stack(NamedTuple):
    url: str
    token_var: str
    vault_file: str
    missing: str


# The one stack is the observability node; its token is minted by the `mon` role into its
# `mon_token_cache`, outside the tree.
STACKS = {
    "mon": Stack(
        "https://zcrypto-mon.zhaow.me",
        "mon_grafana_tools_token",
        str(Path.home() / ".config/zcrypto/grafana-mon.vault.yml"),
        "the node's converge writes it (infra/runbooks/mon.md, mon-token-rotate)",
    ),
}
DEFAULT_STACK = "mon"
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


def token(name: str = DEFAULT_STACK) -> str:
    """The stack's service-account token. A missing vault file exits 1 in one line, not a traceback:
    on a fresh controller the `mon` cache's absence is the normal state.
    """
    from ansible.errors import AnsibleFileNotFound

    s = stack(name)
    try:
        return vault_var(s.token_var, s.vault_file)
    except AnsibleFileNotFound:
        print(f"no token for stack {name!r}: {ANSIBLE_DIR / s.vault_file} is missing; {s.missing}", file=sys.stderr)
        raise SystemExit(1) from None
