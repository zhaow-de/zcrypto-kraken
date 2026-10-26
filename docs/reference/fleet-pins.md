# Fleet pins

The current pin and rollback operand of every service — a state file: a row is re-trued in the change that converges it — the digest from that converge's line in `deploy-log.jsonl`, `since` from the container's `.State.StartedAt` (the NAS Alloy's `.Created`) — and the converge's evidence goes in the commit message, so `git log --follow` on this file is the deploy chronicle.

Every image pin but the NAS's and Alloy's is a converge-time extra-var, so its row is the only record.

Reading rules:

- `infra/ansible/scripts/converge.sh` appends a line to `deploy-log.jsonl` for each real pass, whatever its `rc` (`tests/test_converge_sh.py`): re-true a row from a line whose `rc` is 0.
- A running pin is read from the container, `docker inspect <name> --format '{{.Config.Image}}'` — never `.Image`, which is host-dependent under classic storage, and never the compose file, which has pinned one image while the container ran another (set: the non-comment lines of the non-Markdown files under `infra/`, `cli/` and `.claude/` whose `docker inspect` format reads `.Image`, the counter excluded; count: `infra/scripts/count-list.sh inspect-reads-of-dot-image`).
- Capture, engine, ops and the NAS archive-pull share the image repo `ghcr.io/zhaow-de/zcrypto-capture` with independent digests: a row is matched by its service cell, not by the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `f102ca375382` — revision `7ab4fc1a` | 2026-10-08 15:24:21 | `3f291f3cee57` |
| capture | zcrypto-red | `f102ca375382` — revision `7ab4fc1a` | 2026-10-08 15:21:15 | `3f291f3cee57` |
| engine | zcrypto | `f102ca375382` — revision `7ab4fc1a` | 2026-09-30 18:22:02 | `3f291f3cee57` |
| cache-proxy | zcrypto | `76928c0d6b39` — HAProxy 3.4.5, upstream `haproxy` | 2026-09-30 18:22:02 | first pin |
| alloy | zcrypto | `89a5a3201683` — v1.21.2 | 2026-10-26 22:35:23 | `2aa2099af76c` — v1.20.1 |
| alloy | zcrypto-red | `89a5a3201683` — v1.21.2 | 2026-10-26 21:27:01 | `2aa2099af76c` — v1.20.1 |
| alloy | zcrypto-ops | `89a5a3201683` — v1.21.2 | 2026-10-26 17:32:11 | `2aa2099af76c` — v1.20.1 |
| alloy | nas | `89a5a3201683` — v1.21.2, upstream `grafana/alloy`, no `-compat` variant | 2026-10-26 21:14:54 | `2aa2099af76c` — v1.20.1 |
| valkey + sentinel | zcrypto-valkey1 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:20:54 | first pin |
| alloy | zcrypto-valkey1 | `89a5a3201683` — v1.21.2 | 2026-10-26 21:17:10 | `2aa2099af76c` — v1.20.1 |
| valkey + sentinel | zcrypto-valkey2 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:24:03 | first pin |
| alloy | zcrypto-valkey2 | `89a5a3201683` — v1.21.2 | 2026-10-26 21:20:16 | `2aa2099af76c` — v1.20.1 |
| valkey + sentinel | zcrypto-valkey3 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:28:18 | first pin |
| alloy | zcrypto-valkey3 | `89a5a3201683` — v1.21.2 | 2026-10-26 21:24:31 | `2aa2099af76c` — v1.20.1 |
| ops (timers + liquidations) | zcrypto-ops | `335e768da985` — revision `02b74a13` | 2026-10-11 12:18:45 | `3f291f3cee57` |
| archive-pull | nas | `41cd06b47528` — revision `c2515308`, the `-compat` build | 2026-10-14 11:58:32 | `d914dad91536` |

**Non-image pins.** `zaccess`'s `caddy` is an apt package the access role installs unversioned, clearing a `dpkg` hold, so it has no row and no rollback operand here; read its installed version off the host: `dpkg-query -W caddy`. Alloy on the hosts that run it as a package is installed at `alloy_deb_version` in `infra/ansible/group_vars/observed/alloy.yml`, held and pinned, and takes an `alloy` row in the table below: its version the host's `dpkg-query -W alloy` read after the converge that installs it, its notes `dpkg hold; pinned at 1001`; the word `held` in the notes, its reason after it, marks a host a wave left behind.

Every host's Alloy runs the fleet's version outside a wave (set: the hosts of the inventory's `observed` group, each by its `alloy` row in either table here, a host with no row counted as off; count: `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version`).

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.5.3` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-09-17 | restarted by a tunnel-conf converge (`Requires=wg-quick@zaccess0`), not by a role task; re-pins attended, no bake; read-back and upgrade: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade` |
| alloy | zaccess | `1.21.2-1` | 2026-10-26 | dpkg hold; pinned at 1001 |
| alloy | zcrypto-mon | `1.21.2-1` | 2026-10-26 | dpkg hold; pinned at 1001 |
| alloy | zcrypto-hc | `1.21.2-1` | 2026-10-26 | dpkg hold; pinned at 1001 |
| hc (the healthchecks clone, `ghcr.io/zhaow-de/healthchecks`, by tag) | zcrypto-hc | `v6.3.1` | 2026-10-26 21:05:14 | rollback `v6.2.0`, on the node: `infra/runbooks/hc.md` `hc-patch-pass` step 6 |

## Standing constraints

A constraint lives where it is enforced or executed: the NAS `-compat` rule, the capture canary gate and the engine's preflight gate in `.claude/rules/fleet-deploys.md`; `--pull never` on the ops runners, the liquidations roll after an ops re-pin and the NAS gate-export replay on a container recreate in `.claude/skills/zcrypto-rollout-image/SKILL.md`. Three hold here because no other page states them:

- A NAS converge that recreates the archive-pull container replays the whole gate export, and its window is sized from the live figures, not a remembered rate: cycles = `zcrypto_gate_cache_hits + zcrypto_gate_cache_replayed`; seconds per cycle = the last cold export's `zcrypto_gate_export_duration_seconds` over its `zcrypto_gate_cache_replayed` (a cold export is one whose replayed count equals the cycle count); `infra/scripts/grafana-query.py` reads the series. The rate drifts as the journal grows.
- The engine's TradeVolume re-pin bar is LIFTED. From `2.0.0rc6.dev20260915` a credentialed load resolved fees through an authenticated `POST /0/private/TradeVolume`, which the venue denies INTERMITTENTLY (`EGeneral:Permission denied`), and one denial aborted the whole listing. `nautechsystems/nautilus_trader#5005` falls back to public fees on that denial from `2.0.0rc6.dev20260918` on, and each wheel's page under `docs/reference/adapter-verification/` says whether it still carries the fallback. **The bar returns for a digest whose wheel makes that call without the fallback.**
- Never restart both capture hosts close together. A single-host re-pin costs ~zero data while the other host is healthy — its gap is healed by splicing the other host, and a healed hour books what the splice leaves unfilled — while a pair restarted together books `both_streams_silent` outright; the splice is why an exit bar reads the full hours after a restart, never the restart hour (set: the capture restarts `deploy-log.jsonl` records since the last refine round closed — a successful row limited to a capture host or to the `capture_host` group, tagged capture or un-tagged — paired across hosts within an hour; count: `infra/scripts/count-list.sh capture-hosts-converged-within-an-hour`).

## Full digests

The current pins and their operands; older digests are in this file's git log.

- `f102ca375382` = `sha256:f102ca3753826c6aac0af4a3c98e0c7c5f5faca0b1906ca104ed99715bdefb62` — revision `7ab4fc1a`, AVX; capture on both hosts and the engine
- `335e768da985` = `sha256:335e768da985e25496a1f15d431f968a34a8d5544bfca351ed8269b05d26e644` — revision `02b74a13`, AVX; ops
- `3f291f3cee57` = `sha256:3f291f3cee57b2a5209ab4860c8e6bdb14b7e3007ec0e87e8dcf4c2309d32c73` — revision `77df6273`, AVX; the ops', the capture pair's and the engine's operand
- `41cd06b47528` = `sha256:41cd06b47528a4b8b1dc8d5866bc96004971b61856e9e6dcd87a30d4cec705e4` — revision `c2515308`, the `-compat` build; the NAS archive-pull
- `d914dad91536` = `sha256:d914dad91536b56823d7a3a2b7452e9d60aa03b17e76a5651bcf77e3c54ef4dd` — revision `7ab4fc1a`, the `-compat` build; the NAS archive-pull's operand
- `418652cfb58e` = `sha256:418652cfb58ef879d4978c33553735d7147016032d5aefaa14c828e611eb9dfd` — Valkey 9.1.2; the cache nodes
- `76928c0d6b39` = `sha256:76928c0d6b39bdd5f1c15d519cf48c47a6aa18c1dc552f7af1c146d2aa003c14` — HAProxy 3.4.5; the engine host's cache proxy
- `89a5a3201683` = `sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18` — Alloy v1.21.2; the ops, capture and cache hosts and the NAS
- `2aa2099af76c` = `sha256:2aa2099af76c0098d4af7a4d6e48f86cb66dc1a000222ad927a1c67c6542d13f` — Alloy v1.20.1; the ops', the capture and cache hosts' and the NAS's operand
