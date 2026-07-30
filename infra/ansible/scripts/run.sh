#!/usr/bin/env bash
# Load the vault-encrypted deploy key into a throwaway ssh-agent for this run only.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"; cd "$SD/.."
VPF="${ANSIBLE_VAULT_PASSWORD_FILE:-$SD/vault-pass.sh}"
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
# Per-machine deploy keys (2026-07-16): one vaulted private per ansible-managed host — the two
# capture hosts, the ops node, and the NAS (ansible-managed since T0056).
for k in files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519; do
  uv run ansible-vault view --vault-password-file "$VPF" "$k" | ssh-add - >/dev/null 2>&1
done
exec uv run ansible-playbook "$@"
