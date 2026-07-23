---
status: open
ripe_when: NOW — the retention parameter is decided (14 d, owner 2026-07-23) and the remainder is a small well-scoped build; take it at the next attended ops window (attended deploy — engine state dir on the VPS + Role B on the NAS, never capture's). The old disk-pressure trigger is retired — it guarded the then-undecided design and would not have fired for years at ~0.35 GiB/month
---

# VPS engine-journal retention — prune-after-verified-pull

## Context — what

The VPS engine journal (`/var/lib/zcrypto-engine/journal`) is append-only with no pruning — an explicit Phase-6 drop (decisions log `[iter-083]`). Measured at the first VPS cycle (2026-07-11): ~2.1 MB/cycle → ~12 MiB/day → **~0.35 GiB/month** (six cycles/day, full-history snapshots; the rate creeps up as history extends). The NAS now pulls a full copy hourly via its own least-privilege `sync_journal` key (Role B, superseding the workstation's `zcrypto-engine-gateops` timer as of iter-094), so the VPS copy is not the only home of the evidence after each verified pull.

## Why this matters

Left alone the journal eventually pressures the VPS disk that also hosts the capture daemon's segment staging — and capture is the protected workload (L2 gaps unbackfillable). At ~0.35 GiB/month the horizon is long (years on a typical Linode disk), which is exactly why this is parked with a trigger instead of built now: the pruning design (prune-after-verified-pull, retention window, tamper-evidence across pruning) deserves a real design pass, not a rushed cron job.

## Findings so far

- Growth measured, not estimated: 2,090,692 bytes for cycle-00 (20 snapshot parquets + record) on 2026-07-11.
- The NAS's hourly Role B journal pull + gate-verify replay gives a natural "verified pull" event a pruning rule could key on (superseded the workstation's daily 06:30 UTC gate-ops pull, iter-094).
- Cross-links: [[T0003]] (its disk-watch item covers the same filesystem for capture; the NAS archive Role B builds is where pruned journal history would durably live), [[T0020-grafana-cloud-observability]] (the NAS `/volume1` disk-free alert that fires this topic's trigger).
- **Retention decided (owner ruling, 2026-07-23 grooming): 14 days flat** — the benefit of a longer window is marginal. Safe because the gate never reads the VPS copy: `zcrypto engine gate-export` scores `$JOURNAL_DEST` on the NAS (`infra/nas/pull-entrypoint.sh:110`), so VPS-local retention cannot starve the ≥14-clean-day gate window — the prune-after-verified-pull condition is what protects evidence, not the length of the local tail. 14 also matches the fleet's existing convention: the capture segment prune runs `retention_days=14` (spec 00050 D8).

## Suggested next steps

- Design the remaining safety semantics around the **decided 14-day window** (the N question is closed — see Findings): pruning runs only after the NAS's verified replay of the day succeeded, never prune the current UTC day, and tamper-evidence across the prune boundary.
- Decide the durable archive home: the NAS copy alone, or fold into T0003's NAS compaction.
- Implement as a small role task or a Role B gate-export extension (attended deploy; touches the engine state dir, never capture's).
