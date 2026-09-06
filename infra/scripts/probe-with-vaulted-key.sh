#!/usr/bin/env bash
# Runs the order-semantics probe harness with the vaulted Kraken trade credential in its environment
# and nothing else, so the operation can be whitelisted NARROWLY: the target is a literal, and
# arguments reach the harness only, so none of them selects a program. `-I` on both interpreters is
# load-bearing, not tidy -- without it the cwd leads `sys.path`, `PYTHONPATH` redirects an import, and
# `PYTHONINSPECT=1` drops to an interactive prompt after the program exits with the credential still
# in `os.environ`. The decrypted values reach the child through `execve`'s environment only: never
# echoed, never written, never on a command line, and one process throughout. It refuses outside the
# repo root, so neither the harness nor the vault path can be shadowed.
# `group_vars/engine_host/vault.yml` carries inline `!vault` scalars, so the loader below resolves
# the two values in-process rather than decrypting a file to stdout. The credential is IP-bound:
# infra/runbooks/order-semantics-verification.md adds the workstation's public IP at section 1.3 and
# closes the exception at section 7.3.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$repo/pyproject.toml" ] && [ -d "$repo/infra/ansible" ] \
  || { echo "refusing: $repo is not the repo root" >&2; exit 2; }

harness="$repo/infra/scripts/kraken-order-semantics-probe.py"
venv_python="$repo/.venv/bin/python"
[ -f "$harness" ] || { echo "refusing: $harness is missing" >&2; exit 2; }
[ -x "$venv_python" ] || { echo "refusing: $venv_python is missing -- run 'uv sync'" >&2; exit 2; }

exec "$venv_python" -I -c '
import os, subprocess, sys

from ansible.parsing.dataloader import DataLoader
from ansible.parsing.vault import VaultSecret, VaultSecretsContext

repo, python, harness = sys.argv[1], sys.argv[2], sys.argv[3]
os.chdir(os.path.join(repo, "infra", "ansible"))

# vault-pass.sh is the documented sops+GPG path and enforces its own refusals; a locked GPG agent
# surfaces here as a non-zero exit with its own message rather than as an empty password.
try:
    password = subprocess.run(
        ["scripts/vault-pass.sh"], capture_output=True, text=True, check=True
    ).stdout.strip()
except subprocess.CalledProcessError as exc:
    sys.exit(f"refusing: the vault password could not be read -- {exc.stderr.strip()}")
if not password:
    sys.exit("refusing: the vault password came back empty")

secrets = [("default", VaultSecret(password.encode()))]
# The `!vault` scalars decrypt lazily on first str(), and that decrypt reads the process-wide
# secrets context rather than the loader -- without this it raises "a required context is not
# active" at the point of USE, long after the loader looked correctly configured.
VaultSecretsContext.initialize(VaultSecretsContext(secrets))
loader = DataLoader()
loader.set_vault_secrets(secrets)
vault = loader.load_from_file("group_vars/engine_host/vault.yml")

try:
    key = str(vault["kraken_trade_api_key"])
    secret = str(vault["kraken_trade_api_secret"])
except (KeyError, TypeError):
    sys.exit("refusing: the trade credential is absent from the vault under the expected names")
if not key or not secret:
    sys.exit("refusing: the vaulted trade credential is empty")

os.chdir(repo)
os.execve(python, [python, "-I", harness, *sys.argv[4:]],
          dict(os.environ, KRAKEN_SPOT_API_KEY=key, KRAKEN_SPOT_API_SECRET=secret))
' "$repo" "$venv_python" "$harness" "$@"
