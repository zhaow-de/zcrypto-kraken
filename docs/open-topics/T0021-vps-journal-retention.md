---
status: open
ripe_when: the VPS root filesystem crosses the 80% disk watermark (the T0020 Grafana disk alert is the trigger mechanism; until that deploys, the daily gate-ops read is the watch), or an attended ops window wants it earlier
---

# VPS engine-journal retention — prune-after-verified-pull

## Context — what

The VPS engine journal (`/var/lib/zcrypto-engine/journal`) is append-only with no pruning — an explicit Phase-6 drop (decisions log `[iter-083]`). Measured at the first VPS cycle (2026-07-11): ~2.1 MB/cycle → ~12 MiB/day → **~0.35 GiB/month** (six cycles/day, full-history snapshots; the rate creeps up as history extends). The workstation pulls a full copy daily (gate-ops timer, rrsync read-only channel), so the VPS copy is not the only home of the evidence after each verified pull.

## Why this matters

Left alone the journal eventually pressures the VPS disk that also hosts the capture daemon's segment staging — and capture is the protected workload (L2 gaps unbackfillable). At ~0.35 GiB/month the horizon is long (years on a typical Linode disk), which is exactly why this is parked with a trigger instead of built now: the pruning design (prune-after-verified-pull, retention window, tamper-evidence across pruning) deserves a real design pass, not a rushed cron job.

## Findings so far

- Growth measured, not estimated: 2,090,692 bytes for cycle-00 (20 snapshot parquets + record) on 2026-07-11.
- The daily gate-ops pull (workstation, 06:30 UTC) + verified replay gives a natural "verified pull" event a pruning rule could key on.
- Cross-links: [[T0003]] (its disk-watch item covers the same filesystem for capture; the NAS sync it builds is where pruned journal history would durably live), [[T0020-grafana-cloud-observability]] (the disk-watermark alert that fires this topic's trigger).

## Suggested next steps

- Design the retention rule: e.g. VPS keeps the rolling N most recent days (N ≥ the gate window 14 + margin); pruning runs only after the workstation's verified replay of the day succeeded; never prune the current UTC day.
- Decide the durable archive home: the workstation copy alone, or fold into T0003's NAS compaction.
- Implement as a small role task or gate-ops extension (attended deploy; touches the engine state dir, never capture's).
