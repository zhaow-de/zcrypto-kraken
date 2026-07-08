#!/usr/bin/env bash
# Load the vault-encrypted deploy key into a throwaway ssh-agent for this run only.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"; cd "$SD/.."
VPF="${ANSIBLE_VAULT_PASSWORD_FILE:-$SD/vault-pass.sh}"
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
uv run ansible-vault view --vault-password-file "$VPF" files/deploy_ed25519 | ssh-add - >/dev/null 2>&1
exec uv run ansible-playbook "$@"
