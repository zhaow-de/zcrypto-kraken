#!/usr/bin/env bash
# Runs the fixture minter with the vaulted Kraken trade credential in its environment and nothing
# else. The sibling of `probe-with-vaulted-key.sh`: everything below `set -euo pipefail` is that
# script's body unchanged, so a `diff` of the two shows only the target. It is a SECOND wrapper
# rather than a `--target` on the first because `.claude/settings.json` carries a standing grant for
# that script's `--probes` argument, whose wildcard covers everything after it: a selector would ride
# that grant and turn it into "run any program with the live trade key present". Never add a selector
# to either script, and never any line above `set -euo pipefail` either -- a shell function named
# `exec` there shadows the builtin. `-I` on both interpreters is load-bearing, not tidy: without it
# the cwd leads `sys.path`, `PYTHONPATH` redirects an import, and `PYTHONINSPECT=1` drops to an
# interactive prompt with the credential still in `os.environ`. This script is deliberately absent
# from that grant file, and the absence is the design: it SENDS ORDERS and has no cancel path, so
# every run should cost a fresh permission decision. It runs CONTROLLER-SIDE rather than through the
# engine image, whose pinned `cli` package is not guaranteed to carry the modules the minter imports.
# The credential is IP-bound: infra/runbooks/order-semantics-verification.md section 1.3 owns the
# allowlist steps for this key, whichever script is run with it.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$repo/pyproject.toml" ] && [ -d "$repo/infra/ansible" ] \
  || { echo "refusing: $repo is not the repo root" >&2; exit 2; }

harness="$repo/infra/scripts/kraken-fixture-mint.py"
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
