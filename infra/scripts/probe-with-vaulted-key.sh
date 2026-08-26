#!/usr/bin/env bash
# Runs the order-semantics probe harness with the vaulted Kraken trade credential in its
# environment, and nothing else.
#
# It exists so the operation can be whitelisted NARROWLY. The program executed is hardcoded, so no
# argument can turn this into a print-me-a-secret tool: whitelisting this script grants exactly
# "run the probe harness with the trade key present", which is the one thing the attended pass needs.
#
# Properties, each load-bearing:
#   * the target is FIXED. Arguments are forwarded to the harness; none of them selects a program.
#   * the decrypted values go straight into the exec'd child's environment. They are never echoed,
#     never written to a file, and never placed on a command line -- `ps` shows the harness's flags
#     and nothing else. One process throughout, so they never cross a pipe either.
#   * refuses outside the repo root, so neither the harness nor the vault path can be shadowed.
#   * the vault password comes from `infra/ansible/scripts/vault-pass.sh`, which keeps its own
#     ancestry refusals (it declines to hand the password to `ansible-inventory --host/--list/--vars`,
#     all three of which print every vault secret in cleartext).
#   * `group_vars/engine_host/vault.yml` is plain YAML carrying inline `!vault` scalars, NOT a
#     wholly-encrypted file -- `ansible-vault view` refuses it. The loader below resolves the tagged
#     values, which is what reaches them without decrypting the file to stdout.
#   * the harness reads both VALUES out of the environment and passes them into
#     `KrakenExecutionClientConfig(api_key=..., api_secret=...)`, which requires them -- so this
#     wrapper's job is to put them there and nothing more. What bounds the exposure is what the
#     harness then does with them: they are never stored on a harness object, logged, printed,
#     interpolated into a message, or written to the evidence file, and its refusals name the two
#     VARIABLES, never their contents.
#
# The credential is IP-bound. Running this from a workstation needs that workstation's public IP
# temporarily allowlisted on the key, and removing it again is a numbered step of the procedure,
# not an afterthought: infra/runbooks/order-semantics-verification.md.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$repo/pyproject.toml" ] && [ -d "$repo/infra/ansible" ] \
  || { echo "refusing: $repo is not the repo root" >&2; exit 2; }

harness="$repo/infra/scripts/kraken-order-semantics-probe.py"
venv_python="$repo/.venv/bin/python"
[ -f "$harness" ] || { echo "refusing: $harness is missing" >&2; exit 2; }
[ -x "$venv_python" ] || { echo "refusing: $venv_python is missing -- run 'uv sync'" >&2; exit 2; }

exec "$venv_python" -c '
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
os.execve(python, [python, harness, *sys.argv[4:]],
          dict(os.environ, KRAKEN_SPOT_API_KEY=key, KRAKEN_SPOT_API_SECRET=secret))
' "$repo" "$venv_python" "$harness" "$@"
