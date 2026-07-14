---
status: open
ripe_when: Role C (secondary capture + reconciler) has landed — the ops node is a capability upgrade, not a Role C dependency (decided 2026-07-13)
---

# Home ops node — a real-CPU compute tier (deferred until after Role C)

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

## Suggested next steps

- **(human decision, deferred)** **Storage topology** — the load-bearing unanswered question. Options:
  (a) archive stays on the NAS RAID-5, ops node mounts it over 1 GbE NFS (single home, but NFS lands in
  the hot path of every pull/verify/reconcile, and it makes [[T0028]]'s sweep *slower*); (b) ops node
  pulls to local NVMe (hot/compute copy) and replicates to the NAS RAID for durability (no NFS in the hot
  path; two copies to keep coherent); (c) NVMe only (fastest, but abandons RAID for **unbackfillable**
  L2 — only viable with a proven external backup). Decide **before** the migration spec: it changes Role
  A's design, T0028's fix, and the durability story.
- **(autonomous)** Write the ops-node spec: an `ops_host` ansible group reusing the existing roles; a
  parallel-run cutover for Roles A/B/Alloy (both stacks running, diff the two `gate.prom` outputs and the
  two archive trees for ≥1 clean UTC day, then stop the NAS containers — no downtime, no split-brain,
  since both duties are read-only/idempotent); fold in [[T0028]]'s fix while touching Role A.
- **(autonomous)** Write the ops node's **charter as explicit non-goals**: no Kraken trade key, no live
  execution, no sole custody of any durability path. A capable home box invites production duties to drift
  off the hardened fixed-IP VPS, which the master plan's §8 posture forbids.
- **(autonomous)** Once the NAS hosts no zcrypto containers, delete the `-compat` image leg + build arg +
  CI matrix entry.
