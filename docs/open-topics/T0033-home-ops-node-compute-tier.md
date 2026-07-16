---
status: partial
ripe_when: now — OPS-1…4 landed (iter-097/098); the remainder is OPS-5 Offload (reconciler off the Atom, ops-node scraper, staleness alert) and OPS-6 Loop (24×7 research loop + the workstation ./data migration), both autonomous
---

# Home ops node — a real-CPU compute tier

## Context — what

An always-on **home Linux compute node** (hardware on hand: **Intel i7-13700, 16C/24T, 64 GB DDR5,
4 TB NVMe, 1 GbE to the NAS**), running ~24×7 except for unattended-upgrades reboots and
full-system-backup windows.

**Decided 2026-07-13: yes, but *after* Role C.** It was briefly considered as a prerequisite for Role C,
but measurement showed Role C does not need it — capture is cheap (102 MiB / ~0.4 core at peak) and now
lives on a second Linode, and the reconciler's union repair is a vectorized polars anti-join the Atom can
carry. So the ops node is a **capability upgrade on its own merits**, not a blocker.

## Why this matters

The Atom C3538 (no AVX, 4 slow cores, DSM) is the binding constraint on every *compute-bearing* role, and
we keep paying for it in workarounds rather than capability. What a real CPU buys:

- **CRC archive verification** — measured **34–68 min per hour of data on the Atom** (infeasible inside a
  60-min cycle) vs **~8 min single-threaded** on a normal core, and ~1 min parallelised across 10 pairs on
  16 cores. This is the capability that had to be **descoped from Role C**; the ops node restores it.
  (Note the honest limit found while designing it: Kraken's CRC covers only the **top 10** levels, so it
  attests top-10 correctness — depth 11–100 completeness is not provable by any mechanism available.)
- **Role B's "verified" deep-check path** — dropped in spec `00049` purely because the Atom could not
  finish 8 cycles in 40 min. On an AVX box it runs the *same* runtime as the VPS, so the cross-runtime
  determinism question ([[T0029]]) disappears too.
- **A 24×7 research loop.** Phase-4/5 backtests currently only run when the intermittent workstation is
  on. This is arguably the biggest win and it serves the *research* north star, not just Phase 6.
- **[[T0023]]'s Binance liquidations recorder** — already decided (option a, free live-only). Liquidations
  are **not backfillable**, so its value accrues in wall-clock time and **every day of delay is a
  permanently lost day of forward data**. It has no good home today (the VPS is production; the
  workstation is intermittent). Strong candidate for the ops node's first workload.
- **Container metrics return.** cadvisor SIGSEGVs on DSM's cgroup-less kernel, so we collect **zero**
  container CPU/mem series today. Real `cpus:` limits also start working (nothing on the NAS is
  CPU-bounded — a runaway reconciler can starve the pull).
- **Ansible + systemd instead of bespoke glue.** The "no NAS-OS configuration" constraint is what forces
  the hand-rolled `pull-entrypoint.sh` sleep-loop, the 9-step manual deploy, and the hand-edited deployed
  compose. An ops node is managed like the VPS, reusing the existing base/docker/hardening/firewall roles.

## Findings so far

- **The node is provisioned** (2026-07-14): `z-home-zcrypto.zhaow.pro`, 24 cores / 61 GB / 3.4 TB free, AVX2, Docker not yet installed. The storage-topology decision (NFS vs local NVMe) remains the parked human item. (Note: its hostname is currently set to `zcrypto-red`, colliding with the Amsterdam VPS's name — fix at first converge.)
- Workarounds that become **deletable** once no zcrypto container runs on the Atom: the `-compat`
  (no-AVX) image variant + `POLARS_RUNTIME` build arg + its CI matrix leg; the DSM-ACL/uid dance
  ([[T0030]], `zcrypto-dummy` 1031:1000) and `normalize-archive-perms.sh`; the missing `cpus:` limits;
  the hand-re-pin ritual ([[T0031]]'s whole class). Roughly **250–400 lines of `infra/nas/` glue** is a
  write-off; everything in `cli/` and `infra/grafana/` is platform-agnostic and ports for free.
  **Caveat:** the NAS still runs `archive-pull` + `gate-export` (both use polars), so the `-compat` build
  survives until those move too.
- **T0027 widens** from "VPS reboot policy" to a **fleet maintenance-window policy**: the ops node adds a
  reboot window *and* a backup window. If any window overlaps another host's, multiple streams go dark at
  once. Windows must be pinned non-overlapping (primary 02:00 UTC, secondary 06:00 UTC, ops node
  elsewhere) and asserted in config.

## Done so far

- **The storage-topology decision is made** (ratified 2026-07-15, attended discussion; recorded as `docs/specs/00051-ops-node-compute-tier-design.md`): a **hybrid of options (a)+(b)** — the NAS remains the archive home and pull owner and holds the full durable copy of everything; the ops node holds the **hot tier** (compiled datasets, the L2 primitive panel, an N-day raw working window) on local NVMe. The network sits in **no hot path** (research reads are local; NAS access = hourly ~20 MB increments + rare cold batch scans), and there is **no NFS anywhere** — every cross-host read is an rsync pull with manifest verification. Placement rule: *custody by durability, computation by weight, capture by redundancy*.
- **The old Roles-A/B/Alloy parallel-run cutover is superseded**: under the ratified topology the ops node is **purely additive** — Role A pull/prune and Alloy stay on the NAS forever; only compute migrates (reconciler, gate-export opportunistically) or unblocks for the first time (Role B verified path, CRC replay). No cutover, no split-brain window, far less churn.
- **The charter-as-non-goals is written** into the spec (D10): no trade key, never `engine_host`, no live execution, no sole custody of anything.
- The execution program is `OPS-1 Provision → OPS-2 Seed → OPS-3 Replayer → OPS-4 Panel → OPS-5 Offload → OPS-6 Loop` (named to avoid colliding with the master plan's §12 "Phase" / go-live "Stage" vocabulary), with 00050 Task 13 depending on OPS-3's replayer.
- **Dropped** (explicit, with reason): the "delete the `-compat` image leg once no zcrypto container runs on the Atom" item — the ratified topology keeps `archive pull` on the NAS indefinitely, so the compat variant is **permanent infrastructure**, not a deletable workaround.

## Suggested next steps

- **OPS-1…3 are DONE** (2026-07-15, iter-097 / spec 00051 plan Tasks 1–10): node provisioned + converged (`zcrypto-ops`, Debian 13), the Coinalyze liquidations poller live with NAS replication (the Binance WS recorder shelved in place — geo-fenced, see [[T0023]]), the continuity-replay verifier + verified-path daily timers armed with dead-men, and the archive seeded from the NAS over a new pull-only channel.
- **OPS-4 is DONE** (2026-07-15, iter-098 / spec 00052): the 1-second L2 primitive panel — materialized, verified (1,740 hours, zero errors), NAS-replicated, accruing hourly behind the new recurring NAS→ops pull timer (which also closed the replay-staleness gap). The state-threading correction (real data falsified the snapshot-per-hour premise) also fixed the merged OPS-3 verifier's semantics.
- Execute the remaining increments: **OPS-5 Offload** — **it relocates the overlay writer as ONE unit: the reconciler AND the trade-backfill** (owner directive 2026-07-16, spec `00053` D4). They share the `archive-pull` entrypoint, the `capture-reconciled` overlay, and `union_trades`, so moving one without the other would split a single writer across two hosts with an rsync between them — two writers on one overlay, where the ops-side mints never reach the NAS. The move also owes the ops→NAS reconciled channel it needs regardless (the `PANEL_*` pattern). Because the backfill was built where the reconciler already lives, OPS-5 stays a purely mechanical move with no new code in flight. Also in scope: reconciler off the Atom (dissolves [[T0044]]'s growth concern); wire the ops-node scraper + the replay-staleness alert; scope the verified-replay timer with `--date` once cadence matters. Then **OPS-6 Loop** — which now also owns (owner directive 2026-07-15): **migrate the workstation's `./data` (measured 2026-07-16: **281 MB**) to the ops node** — moved, or rebuilt there from the NAS-held sources — **and synced to the NAS** *(measured while scoping OPS-5, so this iteration starts with evidence: `ohlc-full` 37M, `ohlc-15m` 98M, `ohlc-holdout-2026-07-10` 1.4M, `derivatives-funding` 736K, `engine-store` 7.7M, `snapshots` 3.4M, universe JSON — **none on the NAS**, `data/*` gitignored, and the configured `backup_dir` absent, so it is genuinely single-copy on an intermittent host. The exposure is nonetheless BOUNDED, which is why this is a chore and not an incident: every one is `f(sources that survive)` — the NAS holds `kraken-ohlcvt-updates` 13G + `kraken-trades` 15G, and funding re-fetches from Binance Vision — and [[T0001]] established the reconstruction is bit-identical, so the trial registry's dataset hashes survive a rebuild. One artifact needs care: `ohlc-holdout-2026-07-10` is the pre-registered holdout ([[T0017]], look budget 1, spent) — it rebuilds deterministically from the ratified window, and rebuilding it is NOT a fresh look.)*, so the research loop's inputs are local to where it runs and the loop can never resume blind to data that lives elsewhere (the data-locality half of the catalog-sync discipline).

- **OPS-6's data model — RATIFIED (owner, 2026-07-16); it supersedes the "migrate" framing above.** The end state is a **replication, not a migration**: the **ops node is the premise for the AUTONOMOUS research loop, the workstation is for INTERACTIVE research**, so **both hold an identical copy of the compiled datasets**, and the **NAS is the custody superset of every kind of data**. A script syncs **bi-directionally** with the NAS as hub (workstation ↔ NAS ↔ ops).

  **Why bi-directional is safe here — and exactly where it stops being safe.** It works *because of* an existing invariant, not in spite of it: canonical data is **immutable and hash-versioned** ("derive to new paths, never `latest`"), so a two-way rsync **without `--delete`** is a **union, not a merge** — nothing is mutated in place, so there is no conflict resolution to get wrong. Two hosts building the same dataset produce the same hash ([[T0001]]: bit-identical reconstruction); building different ones produces different paths. Both union cleanly. That safety belongs to the immutable subset ONLY — classified 2026-07-16:

  - **Union-syncable** (immutable, hash-versioned): `ohlc-full`, `ohlc-15m`, `ohlc`, `ohlc-holdout-2026-07-10`, `derivatives-funding`, `snapshots`, `universe`.
  - **NEVER two-way synced — mutated in place**: `engine-store`. `engine seed` *rewrites* it (it is "the documented repair for a poisoned store tail"), so two writers would fight and last-writer-wins could silently poison a tail. It is `f(ohlc-full + REST)` — **rebuild per host, never replicate**.
  - **NEVER two-way synced — per-host IDENTITY, and the name ALREADY collides**: `engine-journal`. On the workstation it is *the workstation's own shadow engine's* journal; `engine-journal-vps` is a pull of the VPS's; and the **NAS's `engine-journal` is the VPS's**. One name, three different engines' journals, three hosts. Union-syncing it would merge distinct engines' cycle records into one stream and make `engine report` / `gate-export` score a **streak that never happened** — a silent, plausible, wrong verdict, precisely the class §9's QA discipline exists to prevent. **NAS-as-superset therefore REQUIRES host-scoped journal paths** (`engine-journal-<host>/`) as a precondition of any such sync, not as a tidy-up afterwards.

  Left open for OPS-6's design (deliberately not decided here): whether this is a true two-way rsync pair, or simply **"each host pulls the union from the NAS and pushes only what it built"** — the latter reaches the same end state along the project's existing pull-only grain (spec `00051` D10) without inventing a new transport direction. Prefer it unless a two-way script proves genuinely simpler.

- **OPS-6 also owns the workstation's LEFTOVER PAYLOADS — and retiring them dissolves the journal problem above** (owner directive 2026-07-16; measured the same day). The workstation still runs two systemd `--user` units, both **alive and working**, both **superseded by the fleet**:

  - **`zcrypto-engine-gateops.timer`** — **already declared retired** (README §Usage; [[T0003]]: "The workstation `zcrypto-engine-gateops` timer (spec 00042) is retired"), superseded by Role B on the always-on NAS. The repo's templates were deleted, **but the installed units never were**, so it has kept firing daily (last run measured: success, `gate (>= 14 clean days): not met`, **12 min 30 s of CPU**) — re-doing the NAS's work and pulling the VPS journal into `data/engine-journal-vps`. The README already ships the exact disable procedure (`systemctl --user disable --now zcrypto-engine-gateops.timer`, remove the two unit files + `~/.ssh/zcrypto-sync_ed25519`, `daemon-reload`); it simply was never run. **A doc that says "retired" while the thing still runs daily is the same class of drift as a metric nobody scrapes.**
  - **`zcrypto-engine-shadow.service`** — active, journaling real cycles (measured 2026-07-16: `cycle-00.json`, `cycle-08.json`). This is the **iter-083 workstation soak**, superseded by the **iter-084 VPS deployment**: [[T0018]]'s Stage-6a gate clock runs on the **VPS's** journal (ticking since 2026-07-11), not this one. So it is a *second* engine producing a *second* journal that no gate reads.

  **This is what makes the `engine-journal` collision above go away rather than need solving.** Retire both and `data/engine-journal`, `data/engine-journal-vps`, and `data/engine-store` stop being *live per-host state* and become *historical artifacts* — at which point the sync's scope is exactly the immutable, hash-versioned compiled datasets, which union cleanly by construction. **Do the retirement FIRST; then host-scoped journal paths may not be needed at all.** Solving a problem that a cleanup deletes is wasted design.

  Decide explicitly (do not just stop them): is the shadow engine **retired outright** (the VPS is authoritative and this journal feeds nothing), or does an equivalent belong on the ops node for the autonomous loop? Recommend **retire** — a second shadow on ops recreates the same two-journals-one-name hazard on a new host. And note `Linger=yes` is set, so these survive logout: they will keep running until deliberately disabled, and the machine being "just a workstation" has not been protecting anything.
