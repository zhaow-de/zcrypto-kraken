# Key inventory

Public halves (`*.pub`) are the plaintext record of what is authorized where; a rotation edits the
`.pub` once (every consumer loads it via `lookup('file', ...)`). Encrypted files are
`ansible-vault`-encrypted **private** keys.

| File | Private half lives | Consumed by |
| -- | -- | -- |
| `deploy_zcrypto_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`'s throwaway agent; `host_vars/zcrypto` |
| `deploy_zcrypto-red_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-red` |
| `deploy_zcrypto-ops_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-ops` |
| `deploy_nas_ed25519{,.pub}` | vaulted here (backup) + operator `~/.ssh` | **not** loaded by `run.sh` — the NAS is not ansible-managed, so no play connects to it; the `nas` ssh alias uses the operator's local private. The vaulted private is a durable backup of the key material for completeness, nothing more. |
| `sync_ed25519.pub` | NAS (`/volume1/docker/zcrypto-archive/keys/`) | engine-journal pull channel (`group_vars/capture_host`) |
| `sync_capture_ed25519.pub` | NAS | primary capture pull channel |
| `sync_capture_red_ed25519.pub` | NAS | secondary capture pull channel (`host_vars/zcrypto-red`) |
