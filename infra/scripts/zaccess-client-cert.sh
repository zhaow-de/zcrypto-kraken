#!/usr/bin/env bash
# Issue a pinned mTLS client leaf for the zaccess edge (spec 00075 D16).
#   zaccess-client-cert.sh issue <name> [--days N] [--out-dir DIR] [--p12-dir DIR]
# The CA private key is STREAMED from the vault (never written to disk): default
#   ZACCESS_CA_KEY_CMD="uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/zaccess_ca.key.vault"
# run from infra/ansible/. Revocation is the PEM's absence: delete it from pinned-leaves/ and
# converge. Tests override ZACCESS_CA_KEY_CMD/ZACCESS_CA_CRT/ZACCESS_P12_PASS.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CMD="${1:?usage: issue <name> [--days N]}"; shift
[ "$CMD" = "issue" ] || { echo "unknown command: $CMD" >&2; exit 2; }
NAME="${1:?leaf name required}"; shift
[[ "$NAME" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "invalid leaf name: $NAME" >&2; exit 2; }
DAYS=365
OUT_DIR="$REPO/infra/ansible/roles/access/files/pinned-leaves"
P12_DIR="${HOME:-/tmp}/Downloads"
while [ $# -gt 0 ]; do case "$1" in
  --days) DAYS="$2"; shift 2;;
  --out-dir) OUT_DIR="$2"; shift 2;;
  --p12-dir) P12_DIR="$2"; shift 2;;
  *) echo "unknown flag: $1" >&2; exit 2;;
esac; done
CA_CRT="${ZACCESS_CA_CRT:-$REPO/infra/ansible/files/zaccess_ca.crt}"
CA_KEY_CMD="${ZACCESS_CA_KEY_CMD:-cd $REPO/infra/ansible && uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/zaccess_ca.key.vault}"
LEAF="$OUT_DIR/$NAME.pem"
[ -e "$LEAF" ] && { echo "refusing: $LEAF exists — revoke (delete) first or pick a new name" >&2; exit 1; }
mkdir -p "$OUT_DIR" "$P12_DIR"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout "$WORK/leaf.key" -out "$WORK/leaf.csr" -subj "/CN=zaccess-$NAME"
# Certificate extensions: client auth with no intermediate authority
cat > "$WORK/ext.cnf" << 'EXTEOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=clientAuth
EXTEOF
bash -c "$CA_KEY_CMD" | openssl x509 -req -in "$WORK/leaf.csr" -CA "$CA_CRT" \
  -CAkey /dev/stdin -CAserial "$WORK/ca.srl" -CAcreateserial -days "$DAYS" \
  -extfile "$WORK/ext.cnf" -out "$WORK/leaf.pem"
PASS="${ZACCESS_P12_PASS:-$(openssl rand -base64 18)}"
PF="$P12_DIR/zaccess-$NAME.p12.pass"
( umask 077; printf '%s\n' "$PASS" > "$PF" )   # passphrase file created before pkcs12, never in argv
# -legacy is the documented fallback if macOS Keychain rejects OpenSSL 3's default PBES2 encoding.
openssl pkcs12 -export -in "$WORK/leaf.pem" -inkey "$WORK/leaf.key" -certfile "$CA_CRT" \
  -name "zaccess-$NAME" -out "$P12_DIR/zaccess-$NAME.p12" -passout "file:$PF"
mv "$WORK/leaf.pem" "$LEAF"
echo "leaf pinned: $LEAF"
echo "bundle:      $P12_DIR/zaccess-$NAME.p12   (passphrase in $PF, mode 0600)"
echo "next: import the .p12, vault bundle+passphrase, DELETE both local files, converge zaccess"
