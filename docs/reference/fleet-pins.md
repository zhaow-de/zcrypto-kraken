# Fleet pins

The durable record of the image digest each service runs. For the Alloys on ops/capture hosts the pin is a converge-time-only extra-var with **no repo default**, so this file is its only record. Update at every re-pin/converge, **in the same change** — a pin recorded only on a host is one `docker system prune` from unrecoverable.

Capture and engine share the image repo (`ghcr.io/zhaow-de/zcrypto-capture`) but pin **independently** — never read one service's row as the other's.

| service | host | digest (sha256, first 12) | since (UTC) | prior |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `828128f80cb3` | 2026-07-28 08:04 (T0008 + T0101) | `e5a44e1cb138` (2026-07-23) |
| capture | zcrypto-red | `828128f80cb3` | 2026-07-27 23:58 (canary leg) | `e5a44e1cb138` (2026-07-23) |
| engine | zcrypto | `e5a44e1cb138` | 2026-07-26 13:35 (00069 Step 7) | `8574aff805c0` (2026-07-10 build, pre-`cli.obs`) |
| alloy | zcrypto, zcrypto-red, zcrypto-ops, nas | `491b0578c049` (v1.18.0, published 2026-07-20) | 2026-07-27 | `4f6ddc56ffdc` (v1.17.1) |
| archive-pull | nas | `620114511f19` (repo pin `nas_capture_image`, same file; running digest unverified) | — | — |

Full digests:

- capture current (both hosts): `sha256:828128f80cb34a7341394f7aa0bc977207c9b42435b31507b849afc81d4c4224` — built from `3b9c1d12`, carrying [[T0008]]'s recovery ladder and [[T0101]]'s book-staleness window + venue `status` counter. **Retained locally on both hosts, so it is also the engine's forward operand if that is ever wanted — but the engine pins independently and is NOT on it.**
- capture prior, and the rollback operand — verified still present locally on both hosts: `sha256:e5a44e1cb138bcc0d6291fc8be76d00375ce69512e63da532389d3c4821bd8b7`
- **engine current** (unchanged by the 07-28 capture rollout; its container has not restarted since 2026-07-26T13:35:16Z): `sha256:e5a44e1cb138bcc0d6291fc8be76d00375ce69512e63da532389d3c4821bd8b7`
- engine prior: `sha256:8574aff805c0ab6a22d82b3a6dd942c90f194f79d552412b0be6c15e1971a8ad`
- alloy (all four hosts): `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308`
- alloy prior (rollback target, all four): `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b`

**Rollout record — 2026-07-28 capture re-pin.** Secondary converged 2026-07-27T23:58:41Z, primary 2026-07-28T08:04:29Z; the bake ran 8 h 06 m between them. Gate evidence at the primary's word: 0 missing / 0 truncated hours over 7 h x 12 streams on the pulled copy (worst stream 0.0074% against the 0.1% bar), all 12 pairs flowing, `RestartCount` 0 on capture and alloy, `up{job="capture_app"} == 1` for both hosts in Cloud, `hc_checks_down_total` 0, RSS flat (+0.14% over 4.2 h). **The prune ran in the WEAK form (`deleted=0`)** — the secondary's archive begins 2026-07-14 and the 14-day cutoff was 2026-07-14, so the deletion path was never exercised; accepted explicitly by the owner at both the gate and the re-pin. One abort row read red and was discounted on the owner's word: `zcrypto_logship_last_success_timestamp_seconds` is stale whenever logging is quiet, which is a defect in the signal rather than the image ([[T0106]]).

Measure a running pin with `docker inspect <name> --format '{{.Config.Image}}'` — always `.Config.Image`, never `.Image` (host-dependent under classic storage; see the `/zcrypto-bump-alloy` skill).
