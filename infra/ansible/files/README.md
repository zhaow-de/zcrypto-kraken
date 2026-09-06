# Key inventory

Public halves (`*.pub`) are the plaintext record of what is authorized where; a rotation edits the
`.pub` once (every Ansible consumer loads it via `lookup('file', ...)`). Encrypted files are
`ansible-vault`-encrypted **private** keys.

| File | Private half lives | Consumed by |
| -- | -- | -- |
| `deploy_zcrypto_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`'s throwaway agent; `host_vars/zcrypto` |
| `deploy_zcrypto-red_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-red` |
| `deploy_zcrypto-ops_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-ops` |
| `deploy_nas_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`. `ssh nas` uses the operator's local copy — rotate **both** halves together or the next converge loads a stale key. |
| `sync_ed25519.pub` | NAS (`/volume1/docker/zcrypto-archive/keys/`) | engine-journal pull channel (`group_vars/capture_host`) |
| `sync_capture_ed25519.pub` | NAS | primary capture pull channel |
| `sync_capture_red_ed25519.pub` | NAS | secondary capture pull channel (`host_vars/zcrypto-red`) |
| `sync_liquidations_ed25519.pub` | NAS | ops liquidations pull channel; installed on `zcrypto-data` by the ops role as `rrsync -ro` (`host_vars/zcrypto-ops`) |
| `sync_panel_ed25519.pub` | NAS | ops l2-panel pull channel; installed on `zcrypto-data` by the ops role |
| `sync_reconciled_ed25519.pub` | NAS | ops capture-reconciled pull channel; installed on `zcrypto-data` by the ops role |
| `sync_hot_ed25519.pub` | NAS | ops hot-out pull channel (spec 00056 D2); installed on `zcrypto-data` by the ops role |
| `zcrypto_hot_push_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh/zcrypto-hot-push_ed25519`) | the workstation's `zcrypto data push` via the `nas-hot` ssh alias; installed by the nas role, jailed to `hot/`. The **only** write channel into custody (spec 00056 D2). |
