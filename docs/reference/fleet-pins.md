# Fleet pins

The current pin and rollback operand of every service — a state file: a row is re-trued in the change that converges it — the digest from that converge's line in `deploy-log.jsonl`, `since` from `.State.StartedAt` unless the row's procedure names another — and the converge's evidence goes in the commit message, so `git log --follow` on this file is the deploy chronicle.

Every image pin but the NAS's and Alloy's is a converge-time extra-var, so its row is the only record.

Reading rules:

- `infra/ansible/scripts/converge.sh` appends a line to `deploy-log.jsonl` for each real pass, whatever its `rc` (`tests/test_converge_sh.py`): re-true a row from a line whose `rc` is 0.
- A running pin is read from the container, `docker inspect <name> --format '{{.Config.Image}}'` — never `.Image`, which is host-dependent under classic storage, and never the compose file, which has pinned one image while the container ran another (set: the non-comment lines of the non-Markdown files under `infra/`, `cli/` and `.claude/` whose `docker inspect` format reads `.Image`, the counter excluded; count: `infra/scripts/count-list.sh inspect-reads-of-dot-image`).
- Capture, engine, ops and the NAS archive-pull share the image repo `ghcr.io/zhaow-de/zcrypto-capture` with independent digests: a row is matched by its service cell, not by the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `1931596fd60b` — revision `9040ca59` | 2026-11-23 22:04:15 | `f102ca375382` |
| capture | zcrypto-red | `1931596fd60b` — revision `9040ca59` | 2026-11-23 13:14:14 | `f102ca375382` |
| engine | zcrypto | `512ba1a02ea9` — revision `bc217e61` | 2026-11-23 22:04:16 | `81a8d6c7df63` |
| cache-proxy | zcrypto | `76928c0d6b39` — HAProxy 3.4.5, upstream `haproxy` | 2026-11-23 22:04:15 | first pin |
| alloy | zcrypto | `9acc2529bc1e` — v1.22.0 | 2026-11-26 20:09:38 | `89a5a3201683` — v1.21.2 |
| alloy | zcrypto-red | `9acc2529bc1e` — v1.22.0 | 2026-11-26 20:02:00 | `89a5a3201683` — v1.21.2 |
| alloy | zcrypto-ops | `9acc2529bc1e` — v1.22.0 | 2026-11-26 17:18:49 | `89a5a3201683` — v1.21.2 |
| alloy | nas | `9acc2529bc1e` — v1.22.0, upstream `grafana/alloy`, no `-compat` variant | 2026-11-26 18:27:00 | `89a5a3201683` — v1.21.2 |
| valkey + sentinel | zcrypto-valkey1 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:20:54 | first pin |
| alloy | zcrypto-valkey1 | `9acc2529bc1e` — v1.22.0 | 2026-11-26 18:46:45 | `89a5a3201683` — v1.21.2 |
| valkey + sentinel | zcrypto-valkey2 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:24:03 | first pin |
| alloy | zcrypto-valkey2 | `9acc2529bc1e` — v1.22.0 | 2026-11-26 19:48:16 | `89a5a3201683` — v1.21.2 |
| valkey + sentinel | zcrypto-valkey3 | `418652cfb58e` — Valkey 9.1.2, upstream `valkey/valkey` | 2026-09-26 21:28:18 | first pin |
| alloy | zcrypto-valkey3 | `9acc2529bc1e` — v1.22.0 | 2026-11-26 19:53:49 | `89a5a3201683` — v1.21.2 |
| ops (timers + liquidations) | zcrypto-ops | `98cfad6c97cf` — revision `3818d749` | 2026-11-23 11:46:52 | `512ba1a02ea9` |
| bitcoind | zcrypto-ops | `987f63d5e223` — Bitcoin Core v32.1, the local build of `infra/docker/bitcoind/Dockerfile` | 2026-11-24 01:18:17 | first pin |
| bitview | zcrypto-ops | `2dbc2962c54c` — BRK at `1a19c5e96976`, the local build of its `docker/Dockerfile` | 2026-11-24 11:09:02 | first pin |
| archive-pull | nas | `164b135f398a` — revision `1dac4013`, the `-compat` build | 2026-11-12 13:53:41 | `c365dae0afee` |

**Non-image pins.** `zaccess`'s `caddy` is an apt package the access role installs unversioned, clearing a `dpkg` hold, so it has no row and no rollback operand here; read its installed version off the host: `dpkg-query -W caddy`. Alloy on the hosts that run it as a package is installed at `alloy_deb_version` in `infra/ansible/group_vars/observed/alloy.yml`, held and pinned, and takes an `alloy` row in the table below: its version the host's `dpkg-query -W alloy` read after the converge that installs it, its notes `dpkg hold; pinned at 1001`; the word `held` in the notes, its reason after it, marks a host a wave left behind.

Every host's Alloy runs the fleet's version outside a wave (set: the hosts of the inventory's `observed` group, each by its `alloy` row in either table here, a host with no row counted as off; count: `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version`).

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.5.3` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-09-17 | restarted by a tunnel-conf converge (`Requires=wg-quick@zaccess0`), not by a role task; re-pins attended, no bake; read-back and upgrade: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade` |
| alloy | zaccess | `1.22.0-1` | 2026-11-26 | dpkg hold; pinned at 1001 |
| alloy | zcrypto-mon | `1.22.0-1` | 2026-11-26 | dpkg hold; pinned at 1001 |
| alloy | zcrypto-hc | `1.22.0-1` | 2026-11-26 | dpkg hold; pinned at 1001 |
| hc (the healthchecks clone, `ghcr.io/zhaow-de/healthchecks`, by tag) | zcrypto-hc | `v6.3.1` | 2026-11-08 10:29:13 | rollback `v6.2.0`, pulled from the registry first, the node rebuilt 2026-11-08 holding `v6.3.1` alone: `infra/runbooks/hc.md` `hc-patch-pass` step 6 |

## Standing constraints

A constraint lives where it is enforced or executed: the NAS `-compat` rule, the capture canary gate and the engine's preflight gate in `.claude/rules/fleet-deploys.md`; `--pull never` on the ops runners, the liquidations roll after an ops re-pin and the NAS gate-export replay on a container recreate in `.claude/skills/zcrypto-rollout-image/SKILL.md`. These hold here because no other page states them:

- A NAS converge that recreates the archive-pull container replays the whole gate export, and its window is sized from the live figures, not a remembered rate: cycles = `zcrypto_gate_cache_hits + zcrypto_gate_cache_replayed`; seconds per cycle = the last cold export's `zcrypto_gate_export_duration_seconds` over its `zcrypto_gate_cache_replayed` (a cold export is one whose replayed count equals the cycle count); `infra/scripts/grafana-query.py` reads the series. The rate drifts as the journal grows.
- The engine's TradeVolume re-pin bar is LIFTED. From `2.0.0rc6.dev20260915` a credentialed load resolved fees through an authenticated `POST /0/private/TradeVolume`, which the venue denies INTERMITTENTLY (`EGeneral:Permission denied`), and one denial aborted the whole listing. `nautechsystems/nautilus_trader#5005` falls back to public fees on that denial from `2.0.0rc6.dev20260918` on, and each wheel's page under `docs/reference/adapter-verification/` says whether it still carries the fallback. **The bar returns for a digest whose wheel makes that call without the fallback.**
- Never restart both capture hosts close together. A single-host re-pin costs ~zero data while the other host is healthy — its gap is healed by splicing the other host, and a healed hour books what the splice leaves unfilled — while a pair restarted together books `both_streams_silent` outright; the splice is why an exit bar reads the full hours after a restart, never the restart hour (set: the capture restarts `deploy-log.jsonl` records since the last refine round closed — a successful row limited to a capture host or to the `capture_host` group, tagged capture or un-tagged — paired across hosts within an hour; count: `infra/scripts/count-list.sh capture-hosts-converged-within-an-hour`).
- No image built before `1dac40132` carries `zcrypto vintage`. Rolling ops back to one renders the recorder's runner on an image without the command, so its ticks fail, and a UTC day without a tick is a permanent hole in the record (`zcrypto-ops-vintage-not-recorded` at 25 h, the `zcrypto-vintage-record` dead-man); rolling the NAS back to one leaves the custody copy unverified (`host_vars/nas/vars.yml`'s comment on its pin). Such a roll back is weighed against those days, the owner's call.

## Full digests

The current pins and their operands; older digests are in this file's git log.

- `1931596fd60b` = `sha256:1931596fd60b12c9a208d9def21d4949464440b6a3880e93941cebf588bf10a7` — revision `9040ca59`, AVX; capture on both hosts
- `512ba1a02ea9` = `sha256:512ba1a02ea9524ea52ee2496c64bd6d9a31cedf64d1b6c771de9c4d6ccd3c44` — revision `bc217e61`, AVX; the engine, and the ops' operand
- `98cfad6c97cf` = `sha256:98cfad6c97cff51f406062eecf118a7d0f511bde97d7ac502ec0cf1134f7c78e` — revision `3818d749`, AVX; ops
- `987f63d5e223` = `sha256:987f63d5e2239038dfc40218aa29966f27aee83b045e47863e01756406fad9b4` — Bitcoin Core v32.1, a local image id; the on-chain node
- `2dbc2962c54c` = `sha256:2dbc2962c54c6a7bbd9ce8e2d27fecd8469be1e6cf89245b939935edd1545d61` — BRK at `1a19c5e96976`, a local image id; the on-chain index
- `81a8d6c7df63` = `sha256:81a8d6c7df632d133e11e49bc7b14fc19fdd12ba97179131378b8ff3adc499fd` — revision `ff0d3422`, AVX; the engine's operand
- `f102ca375382` = `sha256:f102ca3753826c6aac0af4a3c98e0c7c5f5faca0b1906ca104ed99715bdefb62` — revision `7ab4fc1a`, AVX; the capture pair's operand
- `164b135f398a` = `sha256:164b135f398ad2b04f1c7a3b9101f5d7657db88a39d0f3059c61c5555bad6c7f` — revision `1dac4013`, the `-compat` build; the NAS archive-pull
- `c365dae0afee` = `sha256:c365dae0afee6d83b7f5569ae4d5bc9cc3b36f99c447ae38166ea81e381e83be` — revision `9040ca59`, the `-compat` build; the NAS archive-pull's operand
- `418652cfb58e` = `sha256:418652cfb58ef879d4978c33553735d7147016032d5aefaa14c828e611eb9dfd` — Valkey 9.1.2; the cache nodes
- `76928c0d6b39` = `sha256:76928c0d6b39bdd5f1c15d519cf48c47a6aa18c1dc552f7af1c146d2aa003c14` — HAProxy 3.4.5; the engine host's cache proxy
- `89a5a3201683` = `sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18` — Alloy v1.21.2; the container Alloy rows' operand
- `9acc2529bc1e` = `sha256:9acc2529bc1edb7f5b2bd801dd8334ebc80c158e3a9e5526ecd7c9a273d43189` — Alloy v1.22.0, the fleet's version
