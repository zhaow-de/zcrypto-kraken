# Fleet pins

The CURRENT pin and rollback operand for every service — a **state file, not a changelog**: every row is re-trued in the change that re-pins or converges it (a pin recorded only on a host is one `docker system prune` from unrecoverable), and that converge's evidence goes in the same commit's message, so `git log --follow` on this file is the deploy chronicle. The Alloy pins on the ops/capture hosts are converge-time-only extra-vars with **no repo default**, so this file is their only record.

Reading rules:

- Every real converge is one machine line in `deploy-log.jsonl` beside this file, appended by `infra/ansible/scripts/converge.sh` — re-true a row from that line, never from memory
- Measure a running pin with `docker inspect <name> --format '{{.Config.Image}}'` — always `.Config.Image`, never `.Image` (host-dependent under classic storage; see the `/zcrypto-bump-alloy` skill).
- Read the running digest from the **container**, never the compose file — a compose file has pinned a wrong image while the container ran the right one, and the drift assert cannot see that failure mode.
- Several rows share the image repo (`ghcr.io/zhaow-de/zcrypto-capture`) — capture, engine, ops, the NAS archive-pull — each pinned **independently**: match the row to the service, never to the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (verified resident at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `ac6172b9ffb2` — revision `4925e060`: the `00109` past-dated predicate and the `cli/engine` corrections | 2026-09-04 17:13:25 | `6ece9ceb1c18` (verified resident at the re-pin) |
| capture | zcrypto-red | `ac6172b9ffb2` — revision `4925e060`, the same payload as the primary row | 2026-09-04 09:27:12 | `6ece9ceb1c18` (verified resident at the re-pin) |
| engine | zcrypto | `ac6172b9ffb2` — revision `4925e060`, the capture build's `cli/engine` corrections and metric HELP text | 2026-09-04 17:14:08 | `6ece9ceb1c18` (verified resident at the re-pin) |
| alloy | zcrypto, zcrypto-red, zcrypto-ops, nas | `491b0578c049` (v1.18.0) — one Alloy on all four hosts, each with its own memory cap and `GOMEMLIMIT` | 2026-07-27 | `4f6ddc56ffdc` (v1.17.1) |
| ops (timers + liquidations) | zcrypto-ops | `6ece9ceb1c18` — revision `8f4ac521`: the reconcile ledger-scan gauge | 2026-09-01 14:26:42 | `08f6abb379a7` (verified resident at the re-pin) |
| archive-pull | nas | `ee5ba1d92b46` — the `-compat` build of `8f4ac521`, with [[T0037]]'s residual detectors (`3fb8f4f5`) | 2026-09-01 14:48:03 | `38fd9d703749` (verified resident at the re-pin) |

**Non-image pins.** `zaccess`'s own apt packages — `caddy` and `alloy` — are **deliberately absent from this file**, and their absence is the record: the access role installs them unversioned and actively clears any `dpkg` hold, so there is no pin to record and nothing here could be a rollback operand. Read the installed versions off the host when you need them (`dpkg-query -W alloy caddy`).

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.4.23` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-08-26 | **a pin here is not a pin in the runtime** — no role task restarts agentboard (a restart drops whoever is on the terminal), though a tunnel-conf converge does through `Requires=wg-quick@zaccess0`; re-pins are attended, no bake — the mTLS edge is its only auth; the running-version read-back and the upgrade recipe are the agentboard bullet in `fleet.md` |

## Standing constraints — they outlive any single converge

- **The NAS runs only `-compat` builds** — an AVX build is a silent `Illegal instruction` on the Atom (T0029); prove `runtime=compat` by **running** polars in the pulled image, never by reading the label.
- **Every ops runner is `--pull never`** with no pull task in the role: an operand that is not **resident** on the host is not a rollback path — verify residency (`docker image ls --digests`) at every re-pin.
- **`ops_image_digest` also repins the liquidations compose, which the role never restarts**: `liquidations_decision=roll-after` is an acknowledgement, not an action — after every ops converge that repins it, `docker compose up -d` in `/etc/zcrypto-ops` is owed by hand, verified from the container.
- **EVERY NAS converge that recreates the container replays the whole gate-export; so does a fingerprint change without a recreate.** The cache is `--cache /tmp/gate-cache.json` (`infra/nas/pull-entrypoint.sh`) and `/tmp` is not a mount, so `-e nas_apply_compose=true` wipes it. Size the window from a figure re-derived at planning time: cycles are `cache_hits + cache_replayed` off `textfile/gate.prom`, at the measured **12.0 s/cycle** (a cold export's seconds ÷ cycles) — never one written here, stale as the journal grows. **The `zcrypto-gate-verify` dead-man tolerates the replay; re-check that if the journal grows much further.**
- **The secondary's capture bake IS the engine's canary gate** — there is no engine secondary; the engine role's assert cites this file for that fact.
- **A single-host capture re-pin costs ~zero data while the other host is healthy** — a per-host gap is healed by splicing the other host, and a healed hour books only what the splice leaves UNFILLED; the real constraint is never restarting **both** capture hosts close together, which books outright as `both_streams_silent`. A restart's own gap is covered by that splice, which is why the exit bar reads the full hours after a restart, never the restart hour.

## Full digests — current pins and their operands only; everything older is in this file's git log

- `ac6172b9ffb2` = `sha256:ac6172b9ffb2c1693fa4b55a2498b1ec93ecbb6d13eb4109c5d81a6e7a0e69dd` — **capture PRIMARY, capture SECONDARY and ENGINE current**, revision `4925e060`; its `-compat` twin `sha256:64262906e4bb84a15218d84a9434cad0dd526464f501dee089d93f6edfa80083` is not pinned here.
- `6ece9ceb1c18` = `sha256:6ece9ceb1c181888daf403329d567041ac3481ce7926d03eb32d137d30a7e912` — the AVX build of `8f4ac521`: **ops current, and the capture pair's and the engine's rollback operand**.
- `ee5ba1d92b46` = `sha256:ee5ba1d92b461e74859ff766c4992f791021be605138796dc8ac962f64506470` — the `-compat` build of `8f4ac521`, **NAS current**; its committed source is `nas_capture_image` (`infra/ansible/host_vars/nas/vars.yml`), which this entry must agree with.
- `08f6abb379a7` = `sha256:08f6abb379a7f16215456a97009d5ca0a5f8e2cc88725407e2f0135b422f9eec` — revision `eb6a503a`, the AVX build carrying `ws_idle_timeout_ms=0` (spec `00101`), **ops' rollback operand only**.
- `38fd9d703749` = `sha256:38fd9d70374939d2f82b6eaeac3ab03ee12b80bb299a643e9c01cf93378c1b0b` — the `-compat` build of `28d32463`, an interim build off T0028's feature branch, **the NAS rollback operand**.
- `491b0578c049` = `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308` — Alloy v1.18.0, the current pin on all four hosts.
- `4f6ddc56ffdc` = `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b` — Alloy v1.17.1, the rollback operand.
