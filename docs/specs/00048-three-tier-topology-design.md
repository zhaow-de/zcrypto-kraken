# Three-tier data-continuity topology — design (spec 00048)

## Goal

Introduce the NAS as an always-on **middle tier** between the 24×7 producer (the Linode VPS) and the intermittent consumer (the workstation), so that durable data archival, gate verification, and L2-capture redundancy no longer depend on the workstation being online. This supersedes T0003's workstation-pull approach.

## Context & motivation

The current design pins two duties that *want* an always-on home onto the one box that is offline for days at a time:

- **Durably pulling + archiving the VPS's data** (T0003) — a workstation `systemd` timer pulls the capture ring buffer and compacts to the NAS. If the workstation is offline longer than the VPS's ~7-day ring buffer, the VPS evicts un-pulled L2 segments → **permanent, unbackfillable loss.**
- **Verifying the gate** — the daily `zcrypto engine report`/`replay` runs on the workstation, so gate scoring *lags* whenever the workstation is offline; a soft failure mid-window could silently break the Stage-6a streak unseen.

The NAS resolves both. A read-only probe (2026-07-11) confirmed it is a capable, always-on compute node, not just storage:

- **`synology_denverton_1618+`, x86_64, 4 cores, 32 GB RAM, 27 TB** (`/volume1`, RAID-5 across 6 disks, healthy `[6/6]`), **Docker 24.0.2** (Container Manager) at `/usr/local/bin/docker`.
- **x86_64 is load-bearing**: it runs the *exact* `ghcr.io/zhaow-de/zcrypto-*` images unchanged — no rebuild, no ARM problem — so the NAS can run the same capture and engine binaries the VPS runs.
- The workstation mounts `/volume1/ZhaoCrypto` as `/home/zhaow/Projects/zcrypto-kraken-data` (1 GB/s), so anything the NAS archives is immediately visible to R&D.

## The three-tier topology

```
 PRODUCER                 DURABLE OPS NODE               CONSUMER
 VPS (Linode)     ──▶      NAS (Synology DS1618+)  ──▶    Workstation
 24×7, <5 min blips        ~always-on, egress-only        intermittent (days off)
 public IP, inbound-OK     inbound-unreachable            reads the mounted share
 capture + live trade      pull + archive + verify        R&D (auto + interactive)
                           + redundant capture (dual-L2)
```

### Failure-domain map (the reasoning the design rests on)

| Tier | Availability | Correlated with | Reachability |
|---|---|---|---|
| VPS | ~24×7, <5 min blips (unattended-upgrades reboot, Linode migration) | — (independent of the home site) | public IP, inbound + egress |
| NAS | usually online | **workstation** (shared home ISP) | egress only (initiates all connections) |
| Workstation | intermittent (offline for days) | NAS | egress only |

- **VPS downtime is uncorrelated with the home site** — a Linode reboot never coincides with a home-ISP outage. That independence makes the NAS a safe sink and the VPS's ~7-day ring buffer the safety margin.
- **NAS and workstation fail together only on a home-ISP outage** (observed ≤ 14 h, ~2×/yr). During it the VPS keeps capturing and trading; its ~7-day buffer swallows a 14 h pull outage with a **~12× margin**, so the one correlated failure is a non-event for durability.
- **The NAS is "always-on" *relative to the workstation*** — the exact axis that was breaking things.

## Decisions (2026-07-11, human-cleared)

1. **Scope = A + B + C** — build all three NAS roles: always-on pull/archive (A), always-on gate verification (B), and redundant L2 capture (C).
2. **Durability = RAID-5 + dual-capture only** — no extra archive copy now; the redundant 6-disk array plus two independent capture sources are the redundancy floor. Revisit a 3-2-1 leg before scaling capital. *(Non-goal below.)*
3. **VPS reboot window = move `Automatic-Reboot-Time` 04:00 → 02:00 UTC** — a 4h-grid midpoint (2 h clearance from any engine cycle boundary, the max on the grid), 2 h after the daily 00:00 rebalance, overnight for EUR liquidity. Keep unattended auto-reboot (it is proven-tolerated; see T0027). Revisit attended-vs-auto before live 6b.
4. **Observability = keep Grafana Cloud** (external always-on layer; the only watcher during a home-ISP outage) **+ the NAS reports its pull-lag / gate-verify status into the same instance** for one unified pane across all three tiers.

## Roles

### Role A — always-on pull + archive

The NAS pulls the VPS's data and archives it to `/volume1/ZhaoCrypto`, on a schedule, continuously — decoupling durability from the workstation.

- **What it pulls**: (1) the capture ring buffer `/var/lib/zcrypto-capture/segments` (hourly zstd-Parquet L2 book + trade segments + `.sha256` manifests); (2) the engine journal `/var/lib/zcrypto-engine/journal` (append-only per-cycle records + snapshot sidecars).
- **How**: read-only `rrsync` over the VPS's SSH (10022), mirroring the existing engine-journal channel pattern (`command="/usr/bin/rrsync -ro <subtree>",restrict` forced-command on the `deploy` user's `authorized_keys`, keyed by a vaulted ed25519 key). Two subtrees → two least-privilege keys (a capture-segments key and the existing journal key), so the NAS-capture-pull key cannot read the journal and vice-versa.
- **Verification on pull**: each pulled segment's `sha256` is recomputed and checked against its manifest before it is considered archived; a mismatch is logged and alerted, never silently accepted.
- **Eviction stays on the VPS**: the VPS retains a rolling ~7-day window via **time-based pruning** (delete segments older than N ≥ 7 days) — autonomous, VPS-side, independent of the NAS. *(The current daemon caps disk only via a write-stopping watermark and does **not** yet prune; adding the time-based prune is part of this work — a plan task.)* The NAS pull is read-only and never deletes on the VPS: the ~7-day window vs the ≤ 14 h worst-case pull outage is a ~12× margin, so **delete-after-verified** (NAS-confirmed eviction) is unnecessary complexity and a non-goal here. (Engine-journal retention is the separate concern of T0021.)
- **Cadence**: hourly (a segment finalizes on the hour boundary; hourly pull keeps the VPS→NAS lag ≤ ~1 h, far inside the buffer).

### Role B — always-on gate verification

The NAS runs `zcrypto engine report` / `replay` (same x86 image) daily against the pulled journal, so gate scoring is continuous and independent of the workstation.

- Runs after the daily pull settles; emits the streak / gate status / any failure to the log and to Grafana Cloud (role 4-decision above). A failed or mismatched cycle alerts **promptly**, not whenever the workstation next comes online.
- Read-only: it replays from the journal's own snapshot sidecars (self-contained; no live store needed on the fast path), exactly as the workstation gate-ops did.
- This is the always-on answer to the "gate verification lags when the workstation is offline" risk that threatened the Stage-6a window and live 6b.

### Role C — redundant NAS capture + dual-L2 reconciliation

The NAS runs a second `zcrypto capture` container against Kraken's public WS (keyless), giving two independent L2 sources whose downtimes are uncorrelated (a VPS reboot ≠ a home-ISP outage).

- **Two independent streams** land in the archive: the VPS stream (pulled by role A) and the NAS-local stream (written straight to `/volume1/ZhaoCrypto`).
- **Reconciliation — canonical = VPS, NAS = gap-filler** (the VPS has the fixed IP, 24×7 uptime, and is the production node):
  - **Trades**: merge by `trade_id` (globally unique) → a deduplicated union; trivially correct and it heals the reconnect-snapshot overwrite of T0026 (whichever stream has the fuller hour wins per-trade-id).
  - **Book**: the canonical VPS book is authoritative; where it has a **time-window gap** (e.g., the ~83 s reboot gap), splice in the NAS book's segments for exactly that window, **provenance-tagged** as gap-fill. No attempt to merge two overlapping book streams update-for-update (their checksum chains are independent) — canonical-plus-gap-fill only.
- **Scope guard**: reconciliation produces a research/archive artifact, not a live trading input. Feeding the merged L2 into a *live* decision is a **non-goal** for this iteration (see Non-goals).
- **Cross-validation bonus**: two independent captures that should agree on overlapping windows are a free QA signal — a systematic divergence flags a capture bug in one stream.

## Component design

### The NAS runtime — no systemd, in-container scheduling

Everything runs **inside containers under Container Manager**, touching zero NAS-OS config (per the standing constraint):

- **Containers run as `1000:1000`** (`--user 1000:1000`): uid 1000 = the NAS `zcrypto` user, gid 1000 = the `zcrypto` group. This matches the workstation's local user (also `1000:1000`), and with the share's NFS **Squash = "No mapping"** the ids pass through unchanged — so archived files are owned consistently across both views (`zcrypto:zcrypto` on the NAS, `zhaow:zhaow` on the workstation, the same numeric `1000:1000`).
- Long-running containers with `restart: unless-stopped` — Synology's Container Manager honors this across NAS reboots via its own package (not systemd), so we rely on the Docker restart policy, **not** on writing systemd units or DSM Task Scheduler entries.
- Periodic work (the hourly pull of role A, the daily gate-verify of role B) is driven by an **in-container scheduler** (a small supervised cron/loop), so the schedule lives in the image, not in the NAS OS.
- `docker` is invoked by absolute path (`/usr/local/bin/docker`) since it is off the login `PATH`. A pre-flight check confirms the `ssh nas` user can run Docker (group membership or the Container Manager socket) — a build-time setup check, not a design gate.

### Archive layout on `/volume1/ZhaoCrypto`

Extends the existing archive (`kraken-ohlcvt-updates/`, `kraken-trades/`) with new subtrees for the forward-capture + journal, keeping the VPS-canonical and NAS-redundant streams separable until reconciled, and the reconciled canonical archive distinct. Exact paths are a plan detail; the invariant is: **raw streams are never overwritten in place; reconciliation writes to a new canonical path** (hash-versioned, per the immutable-data rule).

### NAS share permissions (`infra/nas/normalize-archive-perms.sh`)

The archive share `/volume1/ZhaoCrypto` uses **plain POSIX** — **dirs `0775`, files `0664`, group `zcrypto`, no Synology ACL** (the POSIX-over-ACL rationale is in the script header). Every real actor is covered by owner + group `zcrypto` + other-read: the NAS containers run `--user 1000:1000` (`zcrypto:zcrypto`), the workstation is uid/gid 1000 → `zcrypto` via the NFS "No mapping" squash, and `zcrypto-deploy` is in the `zcrypto` group. New files land at `0664`/`0775` given a **`0002` umask on the container and workstation**. The idempotent normalizer **`infra/nas/normalize-archive-perms.sh`** (run as root; re-run if perms drift) enforces it — **applied + verified 2026-07-12**.

### NAS → VPS pull channels

Two `rrsync -ro` forced-command channels on the VPS `deploy` user (capture segments; engine journal), each keyed by a distinct vaulted ed25519 key. The NAS initiates (egress-only); the VPS firewall already exposes 10022 key-only, so the NAS's dynamic ISP egress IP is bounded by the forced command, not a source-IP allowlist (same posture as the planned workstation channel).

### Observability integration

The NAS ships its pull-lag (VPS→NAS segment age), role-B gate status, and container health into the **existing Grafana Cloud instance** (creds already vaulted, T0020), so one pane spans VPS + NAS + gate. Grafana Cloud (with the healthchecks.io dead-man switches) remains the **external** watcher during a home-ISP outage — it is VPS→internet egress, so it is unaffected when the home site is dark; the NAS layer is the internal always-on complement that pauses during such an outage and catches up after.

### VPS reboot-window change

Change `Unattended-Upgrade::Automatic-Reboot-Time` from `04:00` to `02:00` UTC in the base role (a small, reversible ansible change; attended-deployed with this work). Rationale in decision 3.

## Failure modes & handling

| Event | Behavior |
|---|---|
| VPS reboot / <5 min blip | Capture ~83 s gap filled by role C (NAS stream); engine cycle re-runs via the restart rule; role A resumes on next pull. No loss. |
| Home-ISP outage (≤ 14 h) | NAS + workstation dark; VPS keeps capturing/trading; VPS 7-day buffer holds; NAS catches up on reconnect. Grafana Cloud still watches the VPS. No loss. |
| Workstation offline for days | Irrelevant to durability/gate — both now live on the NAS. R&D just resumes when it returns. |
| NAS pull falls behind | Alerted via pull-lag metric; bounded by the 7-day buffer. |
| Pulled segment hash mismatch | Logged + alerted, not archived as canonical; re-pull. |
| Two capture streams diverge on an overlapping window | QA alert — indicates a capture bug; canonical (VPS) stands, divergence investigated. |
| NAS disk / single-disk failure | RAID-5 survives one disk; accepted risk beyond that (decision 2). |

## What this supersedes / relates to

- **Supersedes** T0003's workstation-pull approach (T0003 already flagged as superseded → this spec).
- **T0021** (engine-journal retention): the NAS pull makes the journal's durable home the NAS; prune-after-verified is its remaining concern, folded into role A's engine-journal channel.
- **T0026** (reconnect trade-snapshot overwrite): role C's trade-id merge *heals* the symptom in the archive, but the underlying VPS-daemon fix still stands (books unaffected; independent of this spec).
- **T0027** (auto-reboot policy): decision 3 resolves the window; role C makes a reboot's capture gap a non-event; the live-6b order-state-under-reboot check remains T0027's open item.
- **T0020** (Grafana Cloud): decision 4 keeps it and adds the NAS as a reporter.
- **T0014 / T0024** (captured-spread calibration, universe spread-cap): both consume the synced L2 — role A is what makes that L2 durably available off the VPS.

## Non-goals

- **A third (3-2-1) archive copy** — RAID-5 + dual-capture is the agreed floor now; revisit before scaling capital.
- **Feeding reconciled dual-L2 into live trading decisions** — reconciliation is a research/archive artifact this iteration; live consumption is future work.
- **delete-after-verified eviction on the VPS** — the 7-day buffer's 12× margin makes it unnecessary complexity here.
- **Changing NAS-OS configuration** (systemd units, DSM scheduler, RAID/volume layout) — everything stays in-container.
- **Retiring Grafana Cloud in favor of NAS-hosted monitoring** — rejected (worse VPS coverage, blind during a home-ISP outage).

## Testing & verification (outcome, not output)

- **Role A**: a planted segment on the VPS appears hash-verified in the archive within one pull cycle; a corrupted segment is caught (mismatch → alert, not archived); the workstation sees the archived copy through the mount.
- **Role B**: the NAS `engine report` reproduces the workstation's gate verdict on the same journal (bit-identical streak/status); a deliberately mismatched journaled cycle is scored a failure.
- **Role C**: the NAS capture validates CRC32 like the VPS; on a simulated VPS gap, the reconciler splices the NAS window and provenance-tags it; trade-id merge yields the correct deduplicated union on overlapping hours.
- **Reboot window**: after converge, `Automatic-Reboot-Time` reads `02:00` UTC; a check-mode run is idempotent.
- **End-to-end**: kill the VPS capture briefly → confirm zero archive gap (role C filled it) and the pull/verify/gate pipeline stays green.

## Open questions / risks

- **NAS capture ToS/rate**: two keyless public-WS subscriptions from two IPs — public market data, no auth, within Kraken's public limits; confirm no per-account coupling (there is none — it is unauthenticated).
- **In-container scheduler robustness**: the cron/loop must survive container restarts and not silently die (a dead scheduler = a silent pull stop); its liveness is itself a monitored signal (pull-lag metric doubles as the dead-man).
- **NAS resource headroom under role C**: capture + pull + gate-replay on 4 cores / 32 GB — comfortable, but sized and watched.
- **Reconciliation edge cases**: overlapping-but-disagreeing book windows (both streams present, checksums diverge) — canonical wins; log for QA. Exact provenance schema is a plan detail.
