#!/usr/bin/env bash
# Vaults one secret into a file of inline `!vault` entries, run from infra/ansible so that ansible-vault takes the
# vault password ansible.cfg names. The value is read from the terminal without echo (VAULT_APPEND_SECRET_TTY names
# another source, for a test), so no command line carries it, and it is printed and written in clear nowhere. It reaches
# `ansible-vault encrypt_string` through the builtin `printf %s`, so no argv carries it and no newline is encrypted.
# The shape is a regex body, anchored here as ^(<shape>)$; the value, exactly as typed, must match it whole before it
# is encrypted.
# Usage: vault-append-secret.sh <vault-file> <key> <shape-regex> [--replace]
# Refuses, rc 2, before the value is read: another usage, an empty shape, a shape that is not a regular expression, a
# key that is not a variable name, a file that does not exist, a file encrypted whole (its first line opens
# `$ANSIBLE_VAULT;`), a key the file carries more than once, a key the file carries unless --replace, and --replace
# for a key the file lacks.
# Refuses, rc 2, after the read: more than one line pasted at a terminal, the rest drained so the operator's shell does
# not run it; an empty value, whatever the shape admits; a value off the shape, naming the key and the shape, never the
# value; and an encryptor's output that does not open with the key's `!vault |` line.
# A failed encryption exits with its own rc and writes nothing. --replace swaps the key's line and the indented lines
# under it for the new block and leaves every other line of the file as it was; the file keeps its mode.
# Prints `<key>: appended` or `<key>: replaced` and nothing else.
# An inherited xtrace or allexport (`bash -x`, an exported SHELLOPTS) would print the value or export it to the
# encryptor's environment.
set +xa
set -euo pipefail

value=""; tmp=""
cleanup() {
  unset value
  if [[ -n $tmp ]]; then rm -f -- "$tmp"; fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

refuse() { echo "vault-append-secret: $*" >&2; exit 2; }

usage="usage: vault-append-secret.sh <vault-file> <key> <shape-regex> [--replace]"
if [[ $# -eq 4 && $4 == --replace ]]; then replace=1
elif [[ $# -eq 3 ]]; then replace=0
else refuse "$usage"; fi
file=$1; key=$2; shape=$3
[[ -n $shape ]] || refuse "the shape is empty; $usage"
shape_rc=0
# shellcheck disable=SC2319  # the status wanted is the regex test's own, 2 for a shape that does not compile
[[ "" =~ ^($shape)$ ]] || shape_rc=$?
[[ $shape_rc -ne 2 ]] || refuse "the shape '$shape' is not a regular expression"
[[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || refuse "the key '$key' is not a variable name"
[[ -f $file ]] || refuse "$file does not exist"
first=""; IFS= read -r first < "$file" || true
[[ $first != "\$ANSIBLE_VAULT;"* ]] || refuse "$file is encrypted whole; this script writes to a file of inline !vault entries"
carried=$(KEY="$key:" awk 'index($0, ENVIRON["KEY"]) == 1 { n++ } END { print n + 0 }' "$file")
[[ $carried -le 1 ]] || refuse "$file carries $key $carried times"
if [[ $replace -eq 0 && $carried -gt 0 ]]; then refuse "$file already carries $key; --replace replaces its block"; fi
if [[ $replace -eq 1 && $carried -eq 0 ]]; then refuse "$file carries no $key to replace"; fi

IFS= read -rs -p "$key (not echoed): " value < "${VAULT_APPEND_SECRET_TTY:-/dev/tty}" || true
# The read has already reported a terminal that cannot be opened.
if [ -t 0 ] 2>/dev/null < "${VAULT_APPEND_SECRET_TTY:-/dev/tty}"; then
  printf '\n' >&2
  pending=0
  while IFS= read -rs -t 0.1 -n 1 _ < "${VAULT_APPEND_SECRET_TTY:-/dev/tty}"; do pending=1; done
  [[ $pending -eq 0 ]] || refuse "more than one line was pasted for $key; the rest was discarded and nothing was written"
fi
[[ -n $value ]] || refuse "no value was read for $key"
[[ $value =~ ^($shape)$ ]] || refuse "the value for $key does not match the shape '$shape'; nothing was written"
block=$(printf %s "$value" | uv run ansible-vault encrypt_string --stdin-name "$key")
[[ $block == "$key: !vault |"$'\n'* ]] || refuse "the encryptor's output does not open with $key's !vault line; nothing was written"

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
