# 00051 — Home ops node: the compute tier and the data-temperature topology

Ratified 2026-07-15 in an attended design discussion (the parked human decision of [[T0033]]). This spec records the fleet-wide data topology and the ops-node program (`OPS-1` … `OPS-6`); the implementation plan is `docs/plans/00051-ops-node-compute-tier.md`.

Hardware (provisioned 2026-07-14, `ssh hp` / `z-home-zcrypto.zhaow.pro`): i7-13700 (16C/24T, AVX2), 64 GB DDR5, 4 TB NVMe, 1 GbE to the NAS. Runs ~24×7 minus its own reboot/backup windows. It also carries light non-zcrypto duties; zcrypto's storage footprint there is bounded by policy (D3/D5), and its compute claim is the whole point.

## Decision register

- **D1 — Placement rule: custody by durability, computation by weight, capture by redundancy.** The NAS keeps what is I/O-shaped (pull, prune, telemetry) and holds the full durable copy of everything; the ops node runs everything compute-bearing; the VPS pair does nothing but capture (and the primary, the engine). The NAS's compute load *decreases* over time — "payload-free NAS" is not a goal, but Atom-bound compute is a bug, not a resident.
- **D2 — Storage topology (T0033's question), answered as a hybrid of its old options (a)+(b):** the NAS remains the archive home and pull owner (a), and the ops node holds the hot tier on local NVMe (b) — with the network in **no hot path**: research reads are local NVMe; NAS access is hourly ~20 MB ingest increments plus rare cold-history batch scans, for which 1 GbE sequential is ample. No NFS anywhere: every cross-host read is an rsync **pull** with manifest verification, the one mechanism the fleet already runs (D9).
- **D3 — Temperature is by role, not age.** Hot = read by research iterations (compiled/derived datasets) → ops-node NVMe. Cold = read only by compile/materialize steps (raw sources: L2 mirrors, OHLCVT dumps) → NAS. Enforced by the **materialization rule**: anything the research loop reads more than ~once/day must be pre-compiled into the hot tier; raw stays a batch input. A 2013 OHLC bar is hot; yesterday's raw L2 hour is cold.
- **D4 — Only raw L2 is unbackfillable.** Every derived artifact (OHLC compiles, tick bars, the L2 panel) is a deterministic, hash-versioned function of raw and is **recomputable** — its tiering is cache policy, and the worst tiering mistake costs a batch recompute, never data. All archive-grade paranoia stays concentrated on capture → pull → verify → reconcile.
- **D5 — L2 primitives become one wide, append-only panel.** Compiled at ingest: an hourly increment reads the newly settled hour through `canonical_segments` (reconciled-first, so healed hours feed features), computes every primitive column (spread, imbalance@K, depth, weighted mid, …), appends locally, and is replicated to the NAS with `.sha256` manifests. New research features derive hot→hot from panel columns (the existing `cli/features/` pure-function pattern, one layer up). A **new primitive** graduates via a rare, sequential cold backfill over NAS raw → new hash-versioned panel. An **N-day raw working window** on NVMe absorbs primitive prototyping so experiments never touch cold. The **sampling grid is a provisional research parameter** — set at first materialization (T0014's spread is column 1) and recalibrated from data, exactly like `--min-gap-seconds`.
- **D6 — Capture-host retention is ratified as built:** the 14-day time-window prune timer (deployed on the secondary; primary deploy stays gated on the canary + clean-run embargo, per T0032) + the 3 h source-lag alert + the disk watermark. **No delete-after-ack**: it would need a write-back channel that the `rrsync -ro` pull-only posture deliberately forbids. Standing footprint ≈ 7 GB/host, flat; eviction can only lose unpulled data if the puller is dead *and unnoticed* ~100× longer than the alert's detection time.
- **D7 — Workload placement.** *Stays on NAS forever:* Role A pulls + verify + prune, Alloy, dead-men. *Migrates to the ops node:* the reconciler (its trailing-48 h window fits the hot raw window by construction, and the move dissolves T0044's O(ledger)-erodes-cycle-headroom concern), gate-export (opportunistically), the 24×7 research loop, the panel materializer, and T0023's Binance liquidations recorder (forward-only data — every day of delay is a permanently lost day; first workload after OPS-1). *Unblocks for the first time:* Role B's verified path and the CRC archive replay — descoped from 00049/00050 purely because the Atom could not carry them. **Consequence, superseding old T0033 hopes:** there is no Roles-A/B/Alloy cutover at all (the ops node is purely additive), and the `-compat` (no-AVX) image leg is **permanent infrastructure**, since `archive pull` runs on the Atom indefinitely.
- **D8 — Raw feed is chained** (capture → NAS → ops node): zero new surface on the capture hosts, one channel pattern. Costs ≤1 h extra input lag on data that already waits ~2 h for hour-settlement; the 00050 drill assertion widens from "reconciled hour within ~2 h" to ~3 h. Revisit direct capture-host pulls only if the hop ever matters in practice.
- **D9 — Pull-only everywhere, including ops-node outputs.** The ops node exposes its panel + (post-migration) overlay/ledger via its own `rrsync -ro` forced-command channel, and the **NAS pulls** them into its full copy — nobody pushes to anybody, per-channel least-privilege keys, pinned host keys, manifests verified on every hop.
- **D10 — Charter as non-goals:** no Kraken trade key ever renders on the ops node; it never joins `engine_host`; no live execution; **no sole custody** — an NVMe copy is never the only copy of anything (the NAS replica is the durability home). A capable home box invites production drift off the hardened VPS; this line is the fence.
- **D11 — Reuse-first.** New code is one CLI materializer command (+ its `cli/features/` L2-primitive layer) and channel plumbing. Everything else is verbatim reuse: `zcrypto archive pull` (delta transfer now; T0028's delta-verify later upgrades all channels at once), `canonical_segments`, hash-versioned datasets, the prune-timer/systemd pattern, compose + digest-pin deploys, Alloy/textfile/healthchecks.io observability, and the ansible base/hardening/firewall/fail2ban/chrony/docker roles for a new `ops_host` group.

## Topology and flows

| Machine | Custody | Payloads (target) | Standing size |
| --- | --- | --- | --- |
| zcrypto / zcrypto-red | 14-day L2 ring | capture (+ engine on primary) | ~7 GB each, flat |
| NAS (Atom, no AVX) | full copy of everything, forever: both raw mirrors (D7 of 00050), overlay, OHLCVT dumps, replicas of all compiled sets incl. the panel | Role A pulls, prune, Alloy, dead-men | 31 GB + ~1 GB/day raw |
| ops node (AVX2, 4 TB NVMe) | hot tier: compiled OHLC/tick/substrate, L2 panel, N-day raw window | research loop, materializer, reconciler, verified path, CRC replay, liquidations recorder, heavy QA | tens–hundreds GB, policy-bounded |
| workstation | nothing required | interactive R&D; on-demand hot copy | optional |

```
capture hosts ──rrsync──▶ NAS  (raw custody; 14-day ring pruned at source)
NAS ──rrsync──▶ ops node       (compiled sets + recent raw window; chained)
ops node ──(NAS pulls)──▶ NAS  (panel + overlay/ledger replicas)
NAS ──rrsync──▶ workstation    (hot sets, on demand)
```

The OHLC family is unchanged and validates the pattern: quarterly bulk dumps (cold, NAS) + REST delta top-up, base-authoritative merge, compiled output hot — the bulk/delta/next-bulk-validates cycle stays exactly as `cli/backfill/` + `cli/ohlc/` implement it, now runnable on the ops node so no pipeline step needs the workstation.

## The OPS roadmap

Named `OPS-N` deliberately — "Phase" and "Stage" are taken by the master plan's §12 and the 6a/6b go-live vocabulary. Inside the implementation plan these decompose into ordinary per-plan `Task N`.

| ID | Handle | Content | Gate / deps |
| --- | --- | --- | --- |
| OPS-1 | Provision | bootstrap (direct `ansible-playbook`, master key — `run.sh` cannot bootstrap a virgin host), `ops_host` converge reusing the existing roles, **fix the hostname** (currently `zcrypto-red`, colliding with the secondary), pin reboot/backup windows non-overlapping with 21:25/22:25 UTC and off 4 h bar boundaries (T0027 fleet policy), channels + vaulted keys, dead-man checks with notification channels | none |
| OPS-2 | Seed | pull compiled sets + recent raw window from the NAS; verify manifests; start the T0023 liquidations recorder (wall-clock-accruing, needs only OPS-1) | OPS-1 |
| OPS-3 | Replayer | CRC archive replay + Role B verified path — first-ever runs | OPS-2 · **feeds 00050 Task 13** (the drill's replayer) |
| OPS-4 | Panel | materializer v0 (TDD), spread as column 1 (T0014's compute home), hourly increment timer, NAS replica channel, provisional grid recorded | OPS-2 |
| OPS-5 | Offload | reconciler parallel-run (both nodes compute detect-only, diff ledgers/outputs ≥ a clean day) → cutover off the Atom; gate-export opportunistically | OPS-2 |
| OPS-6 | Loop | 24×7 autonomous research on the node; workstation fully optional | OPS-4/5 |

External clocks, not renamed and not owned here: **00050 Task 12** (soak T+48 h), **00050 Task 13** (clean-run gate + OPS-3), **T0032 remainder** (primary prune timer + capture re-pin, canary + embargo).

## Risks, residuals, open parameters

- **Panel sampling grid** — research parameter, provisional at OPS-4, recalibrated from data. Not an ops decision.
- **Raw working-window size N** — sized at OPS-2 from NVMe headroom vs prototyping need (must cover the reconciler's trailing 48 h plus comfortable slack; start generous, e.g. 14–30 days ≈ 14–30 GB, and tune).
- **Hot-again cold** — if a research design ever needs per-iteration raw scans, the materialization rule (D3) is the first defense; a read-through NVMe cache of cold slices is the documented fallback. Do not build the fallback speculatively.
- **Fleet windows** — three hosts now have maintenance windows (21:25, 22:25, ops TBD at OPS-1) plus an ops backup window; overlap darkens multiple streams at once. Pinned and asserted in config at OPS-1 (T0027).
- **1 GbE ceiling** — only ever carries hourly increments and rare batch scans (~180 GB ≈ half an hour); if a future commercial dataset changes that calculus, revisit D8's direct-pull option before anything else.
