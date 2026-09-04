#!/usr/bin/env bash
# Runs the fixture minter with the vaulted Kraken trade credential in its environment, and nothing
# else. The sibling of `probe-with-vaulted-key.sh`, for the one other repo script that needs the
# trade key: everything below `set -euo pipefail` is that script's body, unchanged, so a `diff` of
# the two shows only the target.
#
# It is a SECOND wrapper rather than a `--target` on the first one, and that is the whole point.
# `.claude/settings.json` carries `Bash(infra/scripts/probe-with-vaulted-key.sh --probes:*)`, whose
# wildcard covers everything after `--probes`: a selector there would ride an already-granted command
# line and turn a standing pre-approval into "run any program with the live trade key
# present". Two scripts, each with a FIXED target, keep the property that makes either
# one safe to whitelist. Never add a selector to either, and never to any line above
# `set -euo pipefail` either -- a shell function named `exec` there shadows the builtin.
#
# BOTH interpreters run `-I` (isolated), and the flag is load-bearing rather than tidy.
# Without it the cwd leads `sys.path` and PYTHON's environment is honoured, so a file in the
# operator's cwd shadows an import, `PYTHONPATH` redirects one, and `PYTHONINSPECT=1`
# drops to an interactive prompt after the program exits with the credential still in
# `os.environ` -- the "shell you keep" the refusal text promises this is not. Measured
# under a pty: without `-I` the prompt appears, with it there is none. What `-I` does NOT
# close is bash's and the loader's environment -- `BASH_ENV`, `LD_PRELOAD`, `PATH` are
# the operator's own and no flag in this file reaches them.
#
# This one is deliberately NOT in `.claude/settings.json`, and that absence is the design. The probe
# reads and places test orders under its own harness's controls; this script SENDS ORDERS that stay
# there -- it has no cancel path, by construction -- so every run should cost a fresh, deliberate
# permission decision. Adding a grant for it would remove the only gate that stands between a
# routine-looking command and three live orders.
#
# It runs CONTROLLER-SIDE, not through the engine image the way an engine-hosted step would. The
# image's `cli` package is pinned to whatever revision that image was built from; the minter imports
# `cli.snapshot.fetch`, `cli.snapshot.assetpairs` and `cli.engine.flatten.BLIND_ORDER_READ_LEGS`,
# none of which is guaranteed to exist there, and the failure would be an ImportError in the middle
# of an attended pass. The repo's own venv is the one tree known to carry them.
#
# The credential is IP-bound. Running this from a workstation needs that workstation's public IP
# temporarily allowlisted on the key, and removing it again is a numbered step of the procedure,
# not an afterthought: infra/runbooks/order-semantics-verification.md section 1.3 owns the mechanics
# for this key, whichever script is being run with it.
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
