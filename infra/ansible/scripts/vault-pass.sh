#!/usr/bin/env bash
# Refuses to hand the vault password to `ansible-inventory --host/--list/--vars` — each silently decrypts
# the WHOLE vault to stdout (fleet-deploys.md "Ansible secrets"). Walks /proc ancestry so the
# refusal fires wherever ansible-inventory sits in the process chain. Traceability: spec 00083 D4.
pid=$$
while [ "$pid" -gt 1 ] 2>/dev/null; do
  cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$cmd" in
    *ansible-inventory*" --host"*|*ansible-inventory*" --list"*|*ansible-inventory*" --vars"*)
      echo "vault password refused: ansible-inventory --host/--list/--vars prints every vault secret in cleartext — use --graph, --list-tags, or a key-names-only filter" >&2
      exit 1 ;;
  esac
  pid="$(awk '/^PPid:/{print $2}' "/proc/$pid/status" 2>/dev/null)" || break
  [ -n "$pid" ] || break
done
exec "${ZCRYPTO_SOPS_BIN:-/home/zhaow/go/bin/sops}" -d --extract '["vault_password"]' "$(dirname "$0")/../vault-password.sops.yaml"
