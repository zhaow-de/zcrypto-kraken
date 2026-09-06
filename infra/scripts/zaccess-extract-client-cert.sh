#!/usr/bin/env bash
# Extract the vaulted zaccess mTLS client bundle for import into a browser or macOS Keychain, so the
# device can present the certificate the Caddy edge pins (spec 00075 D2/D16). It is a pair of per-
# variable `!vault` scalars, so this loads the file and reads the two in process. The passphrase is
# never printed, only written to its 0600 file; import both, then delete them.
set -euo pipefail
umask 077

OUT_DIR="${HOME:-/tmp}/Downloads"
NAME="macbook"
while [ $# -gt 0 ]; do
  case "$1" in
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# The vault chain (vault-pass.sh via ansible.cfg) resolves relative to infra/ansible.
cd "$(dirname "$0")/../ansible"
mkdir -p "$OUT_DIR"

# In-process decrypt: load only the two variables, write the .p12 (binary) and the passphrase (0600).
# ZACCESS_VAULT_VARS lets a test point at a throwaway vault + var names; defaults are the real ones.
B64_VAR="${ZACCESS_P12_B64_VAR:-zaccess_client_p12_b64}"
PASS_VAR="${ZACCESS_P12_PASS_VAR:-zaccess_client_p12_pass}"
VAULT_FILE="${ZACCESS_VAULT_FILE:-group_vars/all/vault.yml}"

uv run python - "$OUT_DIR" "$NAME" "$B64_VAR" "$PASS_VAR" "$VAULT_FILE" <<'PY'
import base64
import os
import subprocess
import sys

from ansible.parsing.dataloader import DataLoader
from ansible.parsing.vault import VaultSecret, VaultSecretsContext

out_dir, name, b64_var, pass_var, vault_file = sys.argv[1:6]

pw = subprocess.run(["scripts/vault-pass.sh"], capture_output=True, text=True, check=True).stdout.strip()
if not pw:
    sys.exit("vault password helper returned nothing")
secrets = [("default", VaultSecret(pw.encode()))]
VaultSecretsContext.initialize(VaultSecretsContext(secrets))
loader = DataLoader()
loader.set_vault_secrets(secrets)
data = loader.load_from_file(vault_file)

p12 = base64.b64decode(str(data[b64_var]))
if p12[:1] != b"\x30":
    sys.exit("decoded bundle is not a DER PKCS#12 (wrong var or corrupt vault entry)")
passphrase = str(data[pass_var])

p12_path = os.path.join(out_dir, f"zaccess-{name}.p12")
pass_path = os.path.join(out_dir, f"zaccess-{name}.p12.pass")
with open(os.open(p12_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as fh:
    fh.write(p12)
with open(os.open(pass_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
    fh.write(passphrase + "\n")
print(f"wrote {p12_path} ({len(p12)} bytes)")
print(f"wrote {pass_path} (passphrase, mode 0600 -- never printed)")
PY

echo "next: import zaccess-${NAME}.p12 into the browser / Keychain (use the passphrase from the"
echo "      .pass file), then DELETE both files -- the vault holds the durable copy."
