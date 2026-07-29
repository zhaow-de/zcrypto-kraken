# Fleet pins

The durable record of the image digest each service runs. For the Alloys on ops/capture hosts the pin is a converge-time-only extra-var with **no repo default**, so this file is its only record. Update at every re-pin/converge, **in the same change** — a pin recorded only on a host is one `docker system prune` from unrecoverable.

Capture and engine share the image repo (`ghcr.io/zhaow-de/zcrypto-capture`) but pin **independently** — never read one service's row as the other's.

| service | host | digest (sha256, first 12) | since (UTC) | prior |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `828128f80cb3` | 2026-07-28 08:04 (T0008 + T0101) | `e5a44e1cb138` (2026-07-23) |
| capture | zcrypto-red | `99faf16514e3` | 2026-07-29 00:52 (canary leg, T0107 payload) | `828128f80cb3` (2026-07-28) |
| engine | zcrypto | `e5a44e1cb138` | 2026-07-26 13:35 (00069 Step 7) | `8574aff805c0` (2026-07-10 build, pre-`cli.obs`) |
| alloy | zcrypto, zcrypto-red, zcrypto-ops, nas | `491b0578c049` (v1.18.0, published 2026-07-20) | 2026-07-27 | `4f6ddc56ffdc` (v1.17.1) |
| ops (timers + liquidations) | zcrypto-ops | `0b2fdcfff6e8` | 2026-07-28 15:59 (T0101 remediation: panel `stale_seconds`, reconciler counters, generation guard) | `e5a44e1cb138` |
| archive-pull | nas | `620114511f19` (repo pin `nas_capture_image`, same file; running digest unverified) | — | — |

Full digests:

- **capture SECONDARY only** (`zcrypto-red`, re-pinned 2026-07-29 00:52:53Z — the canary leg of [[T0107]]'s payload): `sha256:99faf16514e3ddc30712c8c63fb4892d7e5f3042823b56935cf0617a3cf2ab44`, built from `3540b0bb`. Carries [[T0102]]'s `req_id` correlation and [[T0106]]'s liveness gauge — both verified from the image's own surface, not the tag. **The PRIMARY is still on the previous digest for the length of the bake** (gate opens 2026-07-29T04:00Z); this file is deliberately split rather than reading "both hosts", because during a canary the two genuinely differ and a single row would be wrong about one of them.
- capture PRIMARY, and the secondary's rollback operand — retained locally on both hosts: `sha256:828128f80cb34a7341394f7aa0bc977207c9b42435b31507b849afc81d4c4224` — built from `3b9c1d12`, carrying [[T0008]]'s recovery ladder and [[T0101]]'s book-staleness window + venue `status` counter. **Retained locally on both hosts, so it is also the engine's forward operand if that is ever wanted — but the engine pins independently and is NOT on it.**
- **ops current**: `sha256:0b2fdcfff6e873b71661fb50cc42c83858394827edc69ca813f5d121deab3d19` (revision `50fc4979`) — the timers converged 2026-07-28 15:59, and the liquidations poller was rolled to match in the same window rather than left armed. **One variable drives two things**: `ops_image_digest` repins the four timer runners *and* the liquidations compose file — which the role renders but never restarts, so after a converge that file points at the new digest while the container still runs the old one, until some later `docker compose up` silently rolls an unbackfillable stream. End every ops converge deciding explicitly whether to roll it. **Verified resident on the host 2026-07-28**, which matters because every ops runner is `--pull never` with no pull task in the role.
- **ops prior, and the rollback operand — verified still present on `zcrypto-ops` 2026-07-28**: `sha256:e5a44e1cb138bcc0d6291fc8be76d00375ce69512e63da532389d3c4821bd8b7`. Residency is the load-bearing half: every ops runner is `--pull never` and the role has no pull task, so a recorded digest that is no longer on disk is not a rollback path. `ops_image_digest` has no repo default by design, so this row IS the record — it was read from the host because **this file carried no ops row at all until then**, which by its own opening rule meant the operand existed nowhere in the repo.
- capture prior, and the rollback operand — verified still present locally on both hosts: `sha256:e5a44e1cb138bcc0d6291fc8be76d00375ce69512e63da532389d3c4821bd8b7`
- **engine current** (unchanged by the 07-28 capture rollout; its container has not restarted since 2026-07-26T13:35:16Z): `sha256:e5a44e1cb138bcc0d6291fc8be76d00375ce69512e63da532389d3c4821bd8b7`
- engine prior: `sha256:8574aff805c0ab6a22d82b3a6dd942c90f194f79d552412b0be6c15e1971a8ad`
- alloy (all four hosts): `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308`
- alloy prior (rollback target, all four): `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b`

**Rollout record — 2026-07-28 capture re-pin.** Secondary converged 2026-07-27T23:58:41Z, primary 2026-07-28T08:04:29Z; the bake ran 8 h 06 m between them. Gate evidence at the primary's word: 0 missing / 0 truncated hours over 7 h x 12 streams on the pulled copy (worst stream 0.0074% against the 0.1% bar), all 12 pairs flowing, `RestartCount` 0 on capture and alloy, `up{job="capture_app"} == 1` for both hosts in Cloud, `hc_checks_down_total` 0, RSS flat (+0.14% over 4.2 h). **The prune ran in the WEAK form (`deleted=0`)** — the secondary's archive begins 2026-07-14 and the 14-day cutoff was 2026-07-14, so the deletion path was never exercised; accepted explicitly by the owner at both the gate and the re-pin. One abort row read red and was discounted on the owner's word: `zcrypto_logship_last_success_timestamp_seconds` is stale whenever logging is quiet, which is a defect in the signal rather than the image ([[T0106]]).

Measure a running pin with `docker inspect <name> --format '{{.Config.Image}}'` — always `.Config.Image`, never `.Image` (host-dependent under classic storage; see the `/zcrypto-bump-alloy` skill).
