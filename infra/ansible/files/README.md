# Key inventory

Public halves (`*.pub`) are the plaintext record of what is authorized where; a rotation edits the
`.pub` once (every consumer loads it via `lookup('file', ...)`). Encrypted files are
`ansible-vault`-encrypted **private** keys.

| File | Private half lives | Consumed by |
| -- | -- | -- |
| `deploy_zcrypto_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`'s throwaway agent; `host_vars/zcrypto` |
| `deploy_zcrypto-red_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-red` |
| `deploy_zcrypto-ops_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-ops` |
| `deploy_nas_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`'s throwaway agent (the NAS is ansible-managed since T0056); `host_vars/nas`. The `nas` ssh alias uses the operator's local copy — rotate **both** halves together or the next converge loads a stale key. |
| `sync_ed25519.pub` | NAS (`/volume1/docker/zcrypto-archive/keys/`) | engine-journal pull channel (`group_vars/capture_host`) |
| `sync_capture_ed25519.pub` | NAS | primary capture pull channel |
| `sync_capture_red_ed25519.pub` | NAS | secondary capture pull channel (`host_vars/zcrypto-red`) |
