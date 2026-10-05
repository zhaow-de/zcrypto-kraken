#!/usr/bin/env bash
# Vaults one secret into a file of inline `!vault` entries, run from infra/ansible so that ansible-vault takes the
# vault password ansible.cfg names. The value is read from the terminal without echo (VAULT_APPEND_SECRET_TTY names
# another source, for a test), so no command line carries it, and it is printed and written in clear nowhere. It reaches
# `ansible-vault encrypt_string` through the builtin `printf %s`, so no argv carries it and no newline is encrypted.
# The shape is a regex body, anchored here as ^(<shape>)$; the value must match it whole before it is encrypted.
# Usage: vault-append-secret.sh <vault-file> <key> <shape-regex> [--replace]
# Refuses, rc 2, before the value is read: another usage, an empty shape, a key that is not a variable name, a file
# that does not exist, a key the file already carries unless --replace, and --replace for a key the file lacks.
# Refuses, rc 2, after the read: an empty value, whatever the shape admits, and a value off the shape, naming the key
# and the shape, never the value.
# A failed encryption exits with its own rc and writes nothing. --replace swaps the key's line and the indented lines
# under it for the new block and leaves every other line of the file as it was; the file keeps its mode.
# Prints `<key>: appended` or `<key>: replaced` and nothing else.
# An inherited xtrace, `bash -x` or an exported SHELLOPTS, would print the value on stderr.
set +x
set -euo pipefail

value=""; tmp=""
cleanup() {
  unset value
  if [[ -n $tmp ]]; then rm -f -- "$tmp"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

refuse() { echo "vault-append-secret: $*" >&2; exit 2; }

usage="usage: vault-append-secret.sh <vault-file> <key> <shape-regex> [--replace]"
if [[ $# -eq 4 && $4 == --replace ]]; then replace=1
elif [[ $# -eq 3 ]]; then replace=0
else refuse "$usage"; fi
file=$1; key=$2; shape=$3
[[ -n $shape ]] || refuse "the shape is empty; $usage"
[[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || refuse "the key '$key' is not a variable name"
[[ -f $file ]] || refuse "$file does not exist"
carried=$(KEY="$key:" awk 'index($0, ENVIRON["KEY"]) == 1 { n++ } END { print n + 0 }' "$file")
if [[ $replace -eq 0 && $carried -gt 0 ]]; then refuse "$file already carries $key; --replace replaces its block"; fi
if [[ $replace -eq 1 && $carried -eq 0 ]]; then refuse "$file carries no $key to replace"; fi

read -rs -p "$key (not echoed): " value < "${VAULT_APPEND_SECRET_TTY:-/dev/tty}" || true
# The read has already reported a terminal that cannot be opened.
if [ -t 0 ] 2>/dev/null < "${VAULT_APPEND_SECRET_TTY:-/dev/tty}"; then printf '\n' >&2; fi
[[ -n $value ]] || refuse "no value was read for $key"
[[ $value =~ ^($shape)$ ]] || refuse "the value for $key does not match the shape '$shape'; nothing was written"
block=$(printf %s "$value" | uv run ansible-vault encrypt_string --stdin-name "$key")

tmp=$(mktemp "$(dirname -- "$file")/.vault-append-secret.XXXXXX")
if [[ $replace -eq 1 ]]; then
  KEY="$key:" BLOCK="$block" awk '
    index($0, ENVIRON["KEY"]) == 1 { print ENVIRON["BLOCK"]; inside = 1; next }
    inside && /^[ \t]/ { next }
    { inside = 0; print }
  ' "$file" > "$tmp"
else
  BLOCK="$block" awk '{ print } END { print ENVIRON["BLOCK"] }' "$file" > "$tmp"
fi
chmod --reference="$file" -- "$tmp"
mv -f -- "$tmp" "$file"
tmp=""
verbs=(appended replaced)
printf '%s: %s\n' "$key" "${verbs[replace]}"
