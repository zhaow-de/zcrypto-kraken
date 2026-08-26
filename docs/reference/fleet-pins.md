# Fleet pins

The CURRENT pin and rollback operand for every service — a **state file, not a changelog**: every row is re-trued at each re-pin/converge **in the same change** (a pin recorded only on a host is one `docker system prune` from unrecoverable), and each converge's evidence — checks read, values quoted, bake form — lives in that update's **commit message**, so `git log --follow` on this file is the deploy chronicle. For the Alloys on ops/capture hosts the pin is a converge-time-only extra-var with **no repo default**, so this file is its only record.

Reading rules:

- Measure a running pin with `docker inspect <name> --format '{{.Config.Image}}'` — always `.Config.Image`, never `.Image` (host-dependent under classic storage; see the `/zcrypto-bump-alloy` skill).
- Read the running digest from the **container**, never the compose file — a compose file has pinned a wrong image while the container ran the right one (the 2026-07-31 ops-Alloy find), and the drift assert cannot see that failure mode.
- Several rows share the image repo (`ghcr.io/zhaow-de/zcrypto-capture`) — capture, engine, ops, the NAS archive-pull — each pinned **independently**: match the row to the service, never to the repo.

## Current pins

| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (verified resident at the re-pin) |
| --- | --- | --- | --- | --- |
| capture | zcrypto | `03d4cf1b8df7` — spec `00098` (adopted orders' fills observable), revision `f54431a6`. **HOLD, bounded**: the primary follows the secondary onto `f70997320492` once the bake gate opens (2026-08-26 16:00Z) and the Phase-3 checklist reads green — the two hosts differing is an in-flight state of an OPEN rollout, never a resting one. Its converge must carry `capture_alloy_digest` too, or the drift assert fails it | 2026-08-23 09:25:29 | `636012cc00d9` (2026-08-20) |
| capture | zcrypto-red | `f70997320492` — spec `00100` (the engine migrates to nautilus v2), revision `3671b239`; **canary — this host's bake gates the engine re-pin, and that bake is OPEN: gate computes 2026-08-26 16:00Z (full hours 13/14/15; the partial 12:00 hour never counts)**. This leg also carried an Alloy config fix — `zcrypto_exec_tracking_state` was admitted nowhere and had been dark on BOTH hosts since 2026-08-23; the primary still is until its own converge passes `capture_alloy_digest` | 2026-08-26 12:00:23 | `03d4cf1b8df7` (verified resident on both hosts at the re-pin) |
| engine | zcrypto | `03d4cf1b8df7` — spec `00098`, revision `f54431a6`; adopted-order fills now reach their rows and `zcrypto_exec_external_events_total`. Still **DISARMED**: `exec_armed` renders false, no arm file; arming is the probe checklist's separate owner-worded act | 2026-08-23 10:21:03 | `636012cc00d9` (2026-08-19) |
| alloy | zcrypto, zcrypto-red, zcrypto-ops, nas | `491b0578c049` (v1.18.0, published 2026-07-20) | 2026-07-27 | `4f6ddc56ffdc` (v1.17.1) |
| ops (timers + liquidations) | zcrypto-ops | `f70997320492` — spec `00100` (the engine migrates to nautilus v2), revision `3671b239`; the same image the capture secondary is baking, taken here without a bake because this tier is outside the canary regime. The liquidations container roll is always a separate act — see Standing constraints | 2026-08-26 (converge pending) | `06919e5dc50c` (2026-08-21, verified resident at the re-pin) |
| archive-pull | nas | `5f890c26237a` — the `-compat` build of `e0757909`; repo pin `nas_capture_image` (`infra/ansible/host_vars/nas/vars.yml`), the one surface whose pin is a committed file | 2026-08-15 13:40:38 | `620114511f19` (2026-07-17) |

**Non-image pins.** `zaccess`'s own apt packages — `caddy` and `alloy` — are **deliberately absent from this file**, and their absence is the record. They come from third-party apt repos we do not control; since 2026-08-20 the access role installs them unversioned and actively clears any `dpkg` hold, so there is no pin to record and nothing here could be a rollback operand. A version written down anyway would have **no producer and no consumer** — nothing asserts it, nothing updates it, and it would drift into a confidently-wrong number the first time anyone ran `apt upgrade`. Read the installed versions off the host when you need them (`dpkg-query -W alloy caddy`); the role's own note carries the reasoning.

| package | host | version | since (UTC) | notes |
| --- | --- | --- | --- | --- |
| agentboard | zcrypto-ops | `0.4.8` (`@gbasin/agentboard`, npm global as `zhaow`) | 2026-08-05 | **every re-pin is security-relevant** (the mTLS edge is its only auth) — attended, no bake. Read the running version the way the role does: `sudo -u zhaow bash -c 'source /home/zhaow/.nvm/nvm.sh && npm ls -g @gbasin/agentboard --depth=0'` — a bare `npm ls -g` over ssh finds NOTHING here (the package lives under nvm's node, off the non-interactive PATH), so its empty output is not evidence |

## Standing constraints — they outlive any single converge

- **The NAS runs only `-compat` builds** — an AVX build is a silent `Illegal instruction` on the Atom (T0029); prove `runtime=compat` by **running** polars in the pulled image, never by reading the label.
- **Every ops runner is `--pull never`** with no pull task in the role: an operand that is not **resident** on the host is not a rollback path — verify residency (`docker image ls --digests`) at every re-pin.
- **`ops_image_digest` also repins the liquidations compose, which the role never restarts**: `liquidations_decision=roll-after` is an acknowledgement, not an action — the manual `docker compose up -d` in `/etc/zcrypto-ops` is owed after every ops converge that repins it, and verified from the container afterwards.
- **A fingerprint-invalidating NAS pin replays the whole gate-export** — anything touching `journal.py` changes `gate_cache.py`'s fingerprint, and the cold export measured **2490 s**, not the incremental ~627 s: size converge windows against 2490.
- **The secondary's capture bake IS the engine's canary gate** — there is no engine secondary; the engine role's assert cites this file for that fact.
- **A single-host capture re-pin costs ~zero data while the other host is healthy** — a per-host gap is healed by splicing the other host, and a healed hour books only whatever its splice leaves UNFILLED; the real constraint is never restarting **both** capture hosts close together — that books outright as `both_streams_silent`. Measured 2026-08-20: a primary restart's own gap was 4.3–4.8 s per stream, covered continuously by the secondary, leaving nothing unfilled.

## Full digests — current pins and their operands only; everything older is in this file's git log

- `491b0578c049` = `sha256:491b0578c04983fd54fe99b587b6fab4404dc46d0dc16677bd6b00cc1140b308` — Alloy v1.18.0, the current pin on all four hosts.
- `4f6ddc56ffdc` = `sha256:4f6ddc56ffdcf8a6316748fc5162972e20cb301523cac1bb4a31957df733ae9b` — Alloy v1.17.1, the rollback operand; resident on both capture hosts.
- `03d4cf1b8df7` = `sha256:03d4cf1b8df7e26b05aca7a3346d05c6c58498238d2c615ba904fd39e5fbc1f9` — spec `00098` (the adopted-order disposition filter and D7's adopt-time venue-truth reconcile), revision `f54431a6`; also carries `zcrypto_exec_external_events_total` in the capture keep-regex; deployed on both capture hosts and on the engine, so `(no series)` for that family IS a failure.
- `636012cc00d9` = `sha256:636012cc00d9e3f21ab23dba5454eefe2e252e4152bcdee07da16b8e9335fc4f` — spec `00090` (the rung-1 order path), revision `732598ff`, AVX build; running fleet-wide (both captures and the engine).
- `06919e5dc50c` = `sha256:06919e5dc50c1eef3525aa272b8a21e441d17fa30bf67a46575ca1d560c4b3be` — ops current; spec `00097` (the reconcile skip-cache), revision `52b12ca1`, AVX.
- `6b4c13899653` = `sha256:6b4c13899653d4e9300cec8d111cb5c6a8cf94e43a5db64cbcd0b3fa47698bf8` — ops operand; spec `00096`, revision `2c248fe4`.
- `5f890c26237a` = `sha256:5f890c26237af99ad37ae1b7fe884c4d33476d285774be90cc8c909b3ed049a1` — NAS current; the `-compat` build of `e0757909`.
- `620114511f19` = `sha256:620114511f197c306d6b1c2260b0a12793bb679663517a0626841d0018049a28` — NAS operand.
