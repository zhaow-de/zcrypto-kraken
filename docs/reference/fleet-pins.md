# Fleet pins

The current pin and rollback operand of every service — a state file: a row is re-trued in the change that re-pins or converges it — the digest from that converge's line in `deploy-log.jsonl`, `since` from the container's `.State.StartedAt`, the restart marker — and the converge's evidence goes in the commit message, so `git log --follow` on this file is the deploy chronicle.

`tests/test_fleet_contracts.py` holds the file to state. Every pin but the NAS's is a converge-time extra-var with no repo default, so its row is the only record.

Reading rules:

- `infra/ansible/scripts/converge.sh` appends a line to `deploy-log.jsonl` for each real pass, whatever its `rc` (`tests/test_converge_sh.py`): re-true a row from a line whose `rc` is 0.
- A running pin is read from the container, `docker inspect <name> --format '{{.Config.Image}}'` — never `.Image`, which is host-dependent under classic storage, and never the compose file, which has pinned one image while the container ran another (set: the non-comment lines of the non-Markdown files under `infra/`, `cli/` and `.claude/` whose `docker inspect` format reads `.Image`, the counter excluded; count: `infra/scripts/count-list.sh inspect-reads-of-dot-image`).
- Capture, engine, ops and the NAS archive-pull share the image repo `ghcr.io/zhaow-de/zcrypto-capture` with independent digests: a row is matched by its service cell, not by the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `3f291f3cee57` — revision `77df6273` | 2026-09-26 13:28:11 | `7d4c6066d71e` |
| capture | zcrypto-red | `3f291f3cee57` — revision `77df6273` | 2026-09-26 09:54:52 | `7d4c6066d71e` |
| engine | zcrypto | `3f291f3cee57` — revision `77df6273` | 2026-09-26 16:58:53 | `7d4c6066d71e` |
| alloy | zcrypto | `b8ec653c4423` — v1.19.2 | 2026-09-26 13:28:09 | `491b0578c049` — v1.18.0 |
| alloy | zcrypto-red | `b8ec653c4423` — v1.19.2 | 2026-09-26 09:54:50 | `491b0578c049` — v1.18.0 |
| alloy | zcrypto-ops | `b8ec653c4423` — v1.19.2 | 2026-09-22 15:55:36 | `491b0578c049` — v1.18.0 |
| alloy | nas | `491b0578c049` — v1.18.0, upstream `grafana/alloy`, no `-compat` variant | 2026-09-27 09:56:09 | `4f6ddc56ffdc` — v1.17.1 |
| valkey + sentinel | zcrypto-valkey1 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:20:54 | first pin |
| alloy | zcrypto-valkey1 | `b8ec653c4423` — v1.19.2 | 2026-09-26 22:35:40 | first pin |
| valkey + sentinel | zcrypto-valkey2 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:24:03 | first pin |
| alloy | zcrypto-valkey2 | `b8ec653c4423` — v1.19.2 | 2026-09-26 22:39:05 | first pin |
| valkey + sentinel | zcrypto-valkey3 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:28:18 | first pin |
| alloy | zcrypto-valkey3 | `b8ec653c4423` — v1.19.2 | 2026-09-26 22:41:11 | first pin |
| ops (timers + liquidations) | zcrypto-ops | `3f291f3cee57` — revision `77df6273` | 2026-09-24 20:04:48 | `7d4c6066d71e` |
| archive-pull | nas | `c4135ac75b72` — revision `77df6273`, the `-compat` build | 2026-09-27 09:56:05 | `ee5ba1d92b46` |

**Non-image pins.** `zaccess`'s `caddy` and `alloy` are apt packages the access role installs unversioned, clearing a `dpkg` hold, so they have no row and no rollback operand here; read the installed versions off the host: `dpkg-query -W alloy caddy`.

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.5.3` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-09-17 | restarted by a tunnel-conf converge (`Requires=wg-quick@zaccess0`), not by a role task; re-pins attended, no bake; read-back and upgrade: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade` |

## Standing constraints

A constraint lives where it is enforced or executed: the NAS `-compat` rule and the canary gate in `.claude/rules/fleet-deploys.md`; `--pull never` on the ops runners, the liquidations roll after an ops re-pin and the NAS gate-export replay on a container recreate in `.claude/skills/zcrypto-rollout-image/SKILL.md`. Three hold here because no other page states them:

- A NAS converge that recreates the archive-pull container replays the whole gate export, and its window is sized from the live figures, not a remembered rate: cycles = `zcrypto_gate_cache_hits + zcrypto_gate_cache_replayed`; seconds per cycle = the last cold export's `zcrypto_gate_export_duration_seconds` over its `zcrypto_gate_cache_replayed` (a cold export is one whose replayed count equals the cycle count); `infra/scripts/grafana-query.py` reads the series. The rate drifts as the journal grows.
- The engine's TradeVolume re-pin bar is LIFTED. From `2.0.0rc6.dev20260915` a credentialed load resolved fees through an authenticated `POST /0/private/TradeVolume`, which the venue denies INTERMITTENTLY (`EGeneral:Permission denied`), and one denial aborted the whole listing. `nautechsystems/nautilus_trader#5005` falls back to public fees on that denial from `2.0.0rc6.dev20260918` on, and each wheel's page under `docs/reference/adapter-verification/` says whether it still carries the fallback. **The bar returns for a digest whose wheel makes that call without the fallback.**
- Never restart both capture hosts close together. A single-host re-pin costs ~zero data while the other host is healthy — its gap is healed by splicing the other host, and a healed hour books what the splice leaves unfilled — while a pair restarted together books `both_streams_silent` outright; the splice is why an exit bar reads the full hours after a restart, never the restart hour (set: the capture restarts `deploy-log.jsonl` records — a successful row limited to a capture host or to the `capture_host` group, tagged capture or un-tagged — paired across the two hosts within an hour; count: `infra/scripts/count-list.sh capture-hosts-converged-within-an-hour`).

## Full digests

The current pins and their operands; older digests are in this file's git log.

- `3f291f3cee57` = `sha256:3f291f3cee57b2a5209ab4860c8e6bdb14b7e3007ec0e87e8dcf4c2309d32c73` — revision `77df6273`, AVX; capture on both hosts, the engine and ops
- `7d4c6066d71e` = `sha256:7d4c6066d71edad9fa9029c4d725f9bfc354ba22b7e7044be95cd01b1c27a107` — revision `a1a39280`, AVX; the capture pair's, the engine's and ops' operand
- `c4135ac75b72` = `sha256:c4135ac75b72206d3499c99d476b375d1cc0c3326a4bb8acee255287bb2f3164` — revision `77df6273`, the `-compat` build; the NAS archive-pull
- `ee5ba1d92b46` = `sha256:ee5ba1d92b461e74859ff766c4992f791021be605138796dc8ac962f64506470` — revision `8f4ac521`, the `-compat` build; the NAS archive-pull's operand
- `418652cfb58e` = `sha256:418652cfb58ef879d4978c33553735d7147016032d5aefaa14c828e611eb9dfd` — Valkey 9.1.2; the cache nodes
- `b8ec653c4423` = `sha256:b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839` — Alloy v1.19.2; the ops, capture and cache hosts
- `491b0578c049` = `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308` — Alloy v1.18.0; the NAS, and the ops and capture hosts' operand
- `4f6ddc56ffdc` = `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b` — Alloy v1.17.1; the NAS's operand
