#!/usr/bin/env bash
# Load the vault-encrypted deploy key(s) into a throwaway ssh-agent for this run only.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"; cd "$SD/.."
VPF="${ANSIBLE_VAULT_PASSWORD_FILE:-$SD/vault-pass.sh}"
# One key when --limit names one host whose key exists, every fleet key otherwise (a group or a
# comma list). The bridgehead's sshd offers `MaxAuthTries 2` (infra/runbooks/zaccess.md), so an
# agent holding five keys is refused before its own is tried; a single-key agent, offered alone
# (IdentitiesOnly with the .pub as the identity), is what lets converge.sh reach every host and
# record every converge in docs/reference/deploy-log.jsonl.
LIMIT=""; prev=""
for a in "$@"; do
  [ "$prev" = "--limit" ] && LIMIT="$a"
  case "$a" in --limit=*) LIMIT="${a#--limit=}" ;; esac
  prev="$a"
done
KEYS=(files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519)
if [ -n "$LIMIT" ] && [ -f "files/deploy_${LIMIT}_ed25519" ] && [ -f "files/deploy_${LIMIT}_ed25519.pub" ]; then
  KEYS=("files/deploy_${LIMIT}_ed25519")
  export ANSIBLE_SSH_EXTRA_ARGS="${ANSIBLE_SSH_EXTRA_ARGS:-} -o IdentitiesOnly=yes -o IdentityFile=$PWD/files/deploy_${LIMIT}_ed25519.pub"
fi
eval "$(ssh-agent -s)" >/dev/null
trap 'ssh-agent -k >/dev/null 2>&1 || true' EXIT
for k in "${KEYS[@]}"; do
  uv run ansible-vault view --vault-password-file "$VPF" "$k" | ssh-add - >/dev/null 2>&1
done
exec uv run ansible-playbook "$@"
