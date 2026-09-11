#!/usr/bin/env bash
# Load the vault-encrypted deploy keys into a throwaway ssh-agent for this run only.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"; cd "$SD/.."
VPF="${ANSIBLE_VAULT_PASSWORD_FILE:-$SD/vault-pass.sh}"
# Every fleet key, the --limit host's first when --limit names one host with a key. The hardened hosts' sshd
# offers `MaxAuthTries 2` (roles/hardening leaves devsec's `ssh_max_auth_retries` default), so a key the agent
# presents third is refused before it is tried; and a play's ssh reaches more than its --limit host — the
# capture and engine roles probe the other capture host by delegate_to — so no key is left out, only moved.
LIMIT=""; prev=""
for a in "$@"; do
  [ "$prev" = "--limit" ] && LIMIT="$a"
  case "$a" in --limit=*) LIMIT="${a#--limit=}" ;; esac
  prev="$a"
done
KEYS=(files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519)
if [ -n "$LIMIT" ] && [ -f "files/deploy_${LIMIT}_ed25519" ]; then
  ordered=("files/deploy_${LIMIT}_ed25519")
  for k in "${KEYS[@]}"; do [ "$k" = "files/deploy_${LIMIT}_ed25519" ] || ordered+=("$k"); done
  KEYS=("${ordered[@]}")
fi
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
for k in "${KEYS[@]}"; do
  uv run ansible-vault view --vault-password-file "$VPF" "$k" | ssh-add - >/dev/null 2>&1
done
exec uv run ansible-playbook "$@"
