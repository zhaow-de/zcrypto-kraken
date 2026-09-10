# Fleet pins

The current pin and rollback operand of every service — a state file: a row is re-trued in the change that re-pins or converges it, from that converge's line in `deploy-log.jsonl`, and the converge's evidence goes in the commit message, so `git log --follow` on this file is the deploy chronicle. `tests/test_fleet_contracts.py` holds the file to state: a date sits in a `since` column alone, a cell stays under its cap, the digest glossary mirrors the table, and the NAS rows agree with `infra/ansible/host_vars/nas/vars.yml`. The Alloy pins on the ops and capture hosts are converge-time extra-vars with no repo default, so their row is their only record.

Reading rules:

- `infra/ansible/scripts/converge.sh` appends one line per real pass to `deploy-log.jsonl` beside this file (`tests/test_converge_sh.py`); a row is re-trued from that line, not from memory.
- A running pin is read from the container, `docker inspect <name> --format '{{.Config.Image}}'` — never `.Image`, which is host-dependent under classic storage, and never the compose file, which has pinned one image while the container ran another (set: tracked non-Markdown `docker inspect` formats reading `.Image`; count: `infra/scripts/count-list.sh inspect-reads-of-dot-image`).
- Capture, engine, ops and the NAS archive-pull share the image repo `ghcr.io/zhaow-de/zcrypto-capture` with independent digests: a row is matched by its service cell, not by the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `06998998e876` — revision `c7067af3` | 2026-09-07 19:04:29 | `ac6172b9ffb2` |
| capture | zcrypto-red | `06998998e876` — revision `c7067af3` | 2026-09-07 15:55:10 | `ac6172b9ffb2` |
| engine | zcrypto | `ac6172b9ffb2` — revision `4925e060` | 2026-09-04 17:14:08 | `6ece9ceb1c18` |
| alloy | zcrypto, zcrypto-red, zcrypto-ops, nas | `491b0578c049` — v1.18.0 | 2026-07-27 | `4f6ddc56ffdc` — v1.17.1 |
| ops (timers + liquidations) | zcrypto-ops | `6ece9ceb1c18` — revision `8f4ac521` | 2026-09-01 14:26:42 | `08f6abb379a7` |
| archive-pull | nas | `ee5ba1d92b46` — revision `8f4ac521`, the `-compat` build | 2026-09-01 14:48:03 | `38fd9d703749` |

**Non-image pins.** `zaccess`'s `caddy` and `alloy` are apt packages the access role installs unversioned, clearing a `dpkg` hold, so they have no row and no rollback operand here; read the installed versions off the host: `dpkg-query -W alloy caddy`.

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.4.23` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-08-26 | restarted by a tunnel-conf converge (`Requires=wg-quick@zaccess0`), not by a role task; re-pins attended, no bake; read-back and upgrade: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade` |

## Standing constraints

A constraint lives where it is enforced or executed: the NAS `-compat` rule and the canary gate in `.claude/rules/fleet-deploys.md`; `--pull never` on the ops runners, the liquidations roll after an ops re-pin and the NAS gate-export replay on a container recreate in `.claude/skills/zcrypto-rollout-image/SKILL.md`. Two hold here because no other page states them:

- A NAS converge that recreates the archive-pull container replays the whole gate export, and its window is sized from the live figures, not a remembered rate: cycles = `zcrypto_gate_cache_hits + zcrypto_gate_cache_replayed`; seconds per cycle = the last cold export's `zcrypto_gate_export_duration_seconds` over its `zcrypto_gate_cache_replayed` (a cold export is one whose replayed count equals the cycle count); `infra/scripts/grafana-query.py` reads the series. The rate drifts as the journal grows.
- Never restart both capture hosts close together. A single-host re-pin costs ~zero data while the other host is healthy — its gap is healed by splicing the other host, and a healed hour books what the splice leaves unfilled — while a pair restarted together books `both_streams_silent` outright; the splice is why an exit bar reads the full hours after a restart, never the restart hour (set: `deploy-log.jsonl` rows that converge capture on the two hosts; count: `infra/scripts/count-list.sh capture-hosts-converged-within-an-hour`).

## Full digests

The current pins and their operands; older digests are in this file's git log.

- `06998998e876` = `sha256:06998998e8760edecb3b98dccafcd5f28b0f257b7c1f2a881cecebd7d32a2b1d` — revision `c7067af3`; capture on both hosts
- `ac6172b9ffb2` = `sha256:ac6172b9ffb2c1693fa4b55a2498b1ec93ecbb6d13eb4109c5d81a6e7a0e69dd` — revision `4925e060`; the engine, and the capture pair's operand
- `6ece9ceb1c18` = `sha256:6ece9ceb1c181888daf403329d567041ac3481ce7926d03eb32d137d30a7e912` — revision `8f4ac521`, AVX; ops, and the engine's operand
- `ee5ba1d92b46` = `sha256:ee5ba1d92b461e74859ff766c4992f791021be605138796dc8ac962f64506470` — revision `8f4ac521`, `-compat`; the NAS archive-pull
- `08f6abb379a7` = `sha256:08f6abb379a7f16215456a97009d5ca0a5f8e2cc88725407e2f0135b422f9eec` — revision `eb6a503a`, AVX; ops' operand
- `38fd9d703749` = `sha256:38fd9d70374939d2f82b6eaeac3ab03ee12b80bb299a643e9c01cf93378c1b0b` — revision `28d32463`, `-compat`; the NAS operand
- `491b0578c049` = `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308` — Alloy v1.18.0; the four hosts
- `4f6ddc56ffdc` = `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b` — Alloy v1.17.1; the Alloy operand
