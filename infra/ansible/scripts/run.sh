#!/usr/bin/env bash
# Load the vault-encrypted deploy keys into a throwaway ssh-agent, then hand the process to ansible-playbook.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"; cd "$SD/.."
VPF="${ANSIBLE_VAULT_PASSWORD_FILE:-$SD/vault-pass.sh}"
# Every fleet key, the --limit host's first when --limit names one host with a key. The hardened hosts' sshd
# offers `MaxAuthTries 2` (roles/hardening leaves devsec's `ssh_max_auth_retries` default), so a key the agent
# presents third is refused before it is tried; and a play's ssh reaches more than its --limit host — the
# capture and engine roles probe the other capture host by delegate_to — so no key is left out, only moved.
# A group, a comma list or no --limit keeps the listed order, the bridgehead's key fifth: it converges under
# its own --limit only.
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
# NOT `exec`: exec replaces this shell, so the trap above belonged to a process that no longer existed and the
# agent outlived the converge on every path BEYOND the key loads -- a finished play, a failed play, a signal (0
# kills, measured; a key load that fails still exits with the trap installed, and always did). The
# shell therefore stays and waits; what that costs is signal delivery, which `exec` gave for free because the
# play WAS this process, so a signal aimed at this pid is forwarded by hand. Without the forwarding a `kill` on
# this pid leaves ansible converging a production host unsupervised -- the hazard `.claude/rules/fleet-deploys.md`
# already names for `timeout`. `tests/test_run_sh.py` holds all three halves: the agent dies, the play's own exit
# status reaches the caller, and the play sees the signal.
uv run ansible-playbook "$@" &
play=$!
trap 'kill -INT "$play" 2>/dev/null || true' INT
trap 'kill -TERM "$play" 2>/dev/null || true' TERM
rc=0; wait "$play" || rc=$?
exit "$rc"
