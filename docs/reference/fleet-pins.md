# Fleet pins

The current pin and rollback operand of every service — a state file: a row is re-trued in the change that re-pins or converges it — the digest from that converge's line in `deploy-log.jsonl`, `since` from the container's `.State.StartedAt`, the restart marker — and the converge's evidence goes in the commit message, so `git log --follow` on this file is the deploy chronicle.

`tests/test_fleet_contracts.py` holds the file to state: a date sits in a `since` column alone, a cell, a bullet and a paragraph stay under their caps, no heading sits below the three sections, a digest appears in the tables' digest cells and the glossary alone, the glossary mirrors the table, and the NAS rows agree with `infra/ansible/host_vars/nas/vars.yml`. The Alloy pins on the ops and capture hosts are converge-time extra-vars with no repo default, so their rows are the only record.

Reading rules:

- `infra/ansible/scripts/converge.sh` appends one line per real pass to `deploy-log.jsonl` beside this file, whatever that pass's `rc` — an interrupted pass is recorded, a preview or an aborted confirm is not (`tests/test_converge_sh.py`); a row's digest is re-trued from that line, not from memory, and its `since` is read off the container.
- A running pin is read from the container, `docker inspect <name> --format '{{.Config.Image}}'` — never `.Image`, which is host-dependent under classic storage, and never the compose file, which has pinned one image while the container ran another (set: the non-comment lines of the non-Markdown files under `infra/`, `cli/` and `.claude/` whose `docker inspect` format reads `.Image`, the counter excluded; count: `infra/scripts/count-list.sh inspect-reads-of-dot-image`).
- Capture, engine, ops and the NAS archive-pull share the image repo `ghcr.io/zhaow-de/zcrypto-capture` with independent digests: a row is matched by its service cell, not by the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `7d4c6066d71e` — revision `a1a39280` | 2026-09-19 08:11:46 | `7ccd97eb7e3c` |
| capture | zcrypto-red | `3f291f3cee57` — revision `77df6273` | 2026-09-24 15:48:46 | `7d4c6066d71e` |
| engine | zcrypto | `7d4c6066d71e` — revision `a1a39280` | 2026-09-19 08:25:31 | `ac6172b9ffb2` |
| alloy | zcrypto | `b8ec653c4423` — v1.19.2 | 2026-09-22 10:40:38 | `491b0578c049` — v1.18.0 |
| alloy | zcrypto-red | `b8ec653c4423` — v1.19.2 | 2026-09-22 10:25:05 | `491b0578c049` — v1.18.0 |
| alloy | zcrypto-ops | `b8ec653c4423` — v1.19.2 | 2026-09-22 09:40:56 | `491b0578c049` — v1.18.0 |
| alloy | nas | `491b0578c049` — v1.18.0, upstream `grafana/alloy`, no `-compat` variant | 2026-09-01 14:48:03 | `4f6ddc56ffdc` — v1.17.1 |
| ops (timers + liquidations) | zcrypto-ops | `7d4c6066d71e` — revision `a1a39280` | 2026-09-19 08:40:33 | `6ece9ceb1c18` |
| archive-pull | nas | `ee5ba1d92b46` — revision `8f4ac521`, the `-compat` build | 2026-09-05 00:03:55 | `38fd9d703749` |

**Non-image pins.** `zaccess`'s `caddy` and `alloy` are apt packages the access role installs unversioned, clearing a `dpkg` hold, so they have no row and no rollback operand here; read the installed versions off the host: `dpkg-query -W alloy caddy`.

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.5.3` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-09-17 | restarted by a tunnel-conf converge (`Requires=wg-quick@zaccess0`), not by a role task; re-pins attended, no bake; read-back and upgrade: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade` |

## Standing constraints

A constraint lives where it is enforced or executed: the NAS `-compat` rule and the canary gate in `.claude/rules/fleet-deploys.md`; `--pull never` on the ops runners, the liquidations roll after an ops re-pin and the NAS gate-export replay on a container recreate in `.claude/skills/zcrypto-rollout-image/SKILL.md`. Three hold here because no other page states them:

- A NAS converge that recreates the archive-pull container replays the whole gate export, and its window is sized from the live figures, not a remembered rate: cycles = `zcrypto_gate_cache_hits + zcrypto_gate_cache_replayed`; seconds per cycle = the last cold export's `zcrypto_gate_export_duration_seconds` over its `zcrypto_gate_cache_replayed` (a cold export is one whose replayed count equals the cycle count); `infra/scripts/grafana-query.py` reads the series. The rate drifts as the journal grows.
- The engine's TradeVolume re-pin bar is LIFTED, and the digest above is what lifts it. From `2.0.0rc6.dev20260915` a credentialed load resolved fees through an authenticated `POST /0/private/TradeVolume`; the venue denies it INTERMITTENTLY (`EGeneral:Permission denied`, one in ten, measured) and one denial aborted the whole listing, which reversed the previous engine converge. `nautechsystems/nautilus_trader#5005` falls back to public fees on that denial and rides `2.0.0rc6.dev20260918`, which the engine row above carries — read on the fleet: the engine booted on it with zero instrument-load failures. **The bar returns for a digest whose wheel makes that call without the fallback.**
- Never restart both capture hosts close together. A single-host re-pin costs ~zero data while the other host is healthy — its gap is healed by splicing the other host, and a healed hour books what the splice leaves unfilled — while a pair restarted together books `both_streams_silent` outright; the splice is why an exit bar reads the full hours after a restart, never the restart hour (set: the capture restarts `deploy-log.jsonl` records — a successful row limited to a capture host or to the `capture_host` group, tagged capture or un-tagged — paired across the two hosts within an hour; count: `infra/scripts/count-list.sh capture-hosts-converged-within-an-hour`).

## Full digests

The current pins and their operands; older digests are in this file's git log.

- `3f291f3cee57` = `sha256:3f291f3cee57b2a5209ab4860c8e6bdb14b7e3007ec0e87e8dcf4c2309d32c73` — revision `77df6273`, AVX; capture on the secondary
- `7d4c6066d71e` = `sha256:7d4c6066d71edad9fa9029c4d725f9bfc354ba22b7e7044be95cd01b1c27a107` — revision `a1a39280`, AVX; capture on the primary, the engine and ops; the secondary's operand
- `7ccd97eb7e3c` = `sha256:7ccd97eb7e3c134bd51b09caf9182dc64642fbf7c76b795fe1c9d6c79c51679e` — revision `8d00ead9`; the primary capture's operand
- `ac6172b9ffb2` = `sha256:ac6172b9ffb2c1693fa4b55a2498b1ec93ecbb6d13eb4109c5d81a6e7a0e69dd` — revision `4925e060`; the engine's operand
- `6ece9ceb1c18` = `sha256:6ece9ceb1c181888daf403329d567041ac3481ce7926d03eb32d137d30a7e912` — revision `8f4ac521`, AVX; ops' operand
- `ee5ba1d92b46` = `sha256:ee5ba1d92b461e74859ff766c4992f791021be605138796dc8ac962f64506470` — revision `8f4ac521`, `-compat`; the NAS archive-pull
- `38fd9d703749` = `sha256:38fd9d70374939d2f82b6eaeac3ab03ee12b80bb299a643e9c01cf93378c1b0b` — revision `28d32463`, `-compat`; the NAS operand
- `b8ec653c4423` = `sha256:b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839` — Alloy v1.19.2; the ops and capture hosts
- `491b0578c049` = `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308` — Alloy v1.18.0; the NAS, and those hosts' operand
- `4f6ddc56ffdc` = `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b` — Alloy v1.17.1; the NAS's operand
