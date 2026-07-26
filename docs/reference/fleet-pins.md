# Fleet pins

The durable record of the image digest each service runs. For the Alloys on ops/capture hosts the pin is a converge-time-only extra-var with **no repo default**, so this file is its only record. Update at every re-pin/converge, **in the same change** — a pin recorded only on a host is one `docker system prune` from unrecoverable.

Capture and engine share the image repo (`ghcr.io/zhaow-de/zcrypto-capture`) but pin **independently** — never read one service's row as the other's.

| service | host | digest (sha256, first 12) | since (UTC) | prior |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `e5a44e1cb138` | 2026-07-23 | — |
| capture | zcrypto-red | `e5a44e1cb138` | 2026-07-23 | — |
| engine | zcrypto | `e5a44e1cb138` | 2026-07-26 13:35 (00069 Step 7) | `8574aff805c0` (2026-07-10 build, pre-`cli.obs`) |
| alloy | zcrypto | `4f6ddc56ffdc` (v1.17.1 fleet pin, T0081) | measured 2026-07-26 | — |
| alloy | zcrypto-red / zcrypto-ops | **unrecorded** — record at the next converge or the `/zcrypto-bump-alloy` first run | — | — |
| alloy | nas | `4f6ddc56ffdc` (repo pin `nas_alloy_image`, `infra/ansible/host_vars/nas/vars.yml`; running digest unverified) | — | — |
| archive-pull | nas | `620114511f19` (repo pin `nas_capture_image`, same file; running digest unverified) | — | — |

Full digests:

- `zcrypto-capture`/engine current: `sha256:e5a44e1cb138bcc0d6291fc8be76d00375ce69512e63da532389d3c4821bd8b7`
- engine prior: `sha256:8574aff805c0ab6a22d82b3a6dd942c90f194f79d552412b0be6c15e1971a8ad`
- alloy (zcrypto): `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b`

Measure a running pin with `docker inspect <name> --format '{{.Config.Image}}'` — always `.Config.Image`, never `.Image` (host-dependent under classic storage; see the `/zcrypto-bump-alloy` skill).
