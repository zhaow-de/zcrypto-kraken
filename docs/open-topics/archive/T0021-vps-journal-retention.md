---
status: resolved
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
- **Retention decided (owner ruling, 2026-07-23 grooming): 14 days flat — later raised to 60 at implementation (owner ruling 2026-07-26, between the two converges); the reasoning below is unaffected by the value** — the benefit of a longer window is marginal. Safe because the gate never reads the VPS copy: `zcrypto engine gate-export` scores `$JOURNAL_DEST` on the NAS (`infra/nas/pull-entrypoint.sh:110`), so VPS-local retention cannot starve the ≥14-clean-day gate window — the prune-after-verified-pull condition is what protects evidence, not the length of the local tail. The 14 was chosen partly to match the capture segment prune's `retention_days=14` (spec 00050 D8); the 2026-07-26 raise to 60 drops that symmetry deliberately — the two prunes guard different things (an unbackfillable capture spool vs a journal already mirrored to the NAS).

## Resolution

**Resolved 2026-07-26** by spec `00070` (branch `feat/t0021-journal-retention`), deployed and verified the same evening. All three next-steps are answered:

- **The safety semantics** are spec `00070` D1–D6. "Prune only after the NAS's verified replay" resolves to **margin plus monitoring**, not a mechanical handshake: the architecture is pull-only (`rrsync -ro`, spec `00051` D10), so a NAS→VPS acknowledgement would mean opening a write-capable path *into the trade-key host* — disk hygiene is not worth that trade. A day instead survives **~1,440** hourly pull opportunities before becoming eligible, under a 6 h lag alert (T0069). Verified concretely at deploy rather than argued: the oldest day on the host (`2026-07-11`) measured **127 files / 12,553,096 bytes on both the VPS and the NAS — byte-identical**, so the mirror is complete for the days that will eventually age out.
- **The durable archive home** is the NAS copy alone. No compaction work and no fold into [[T0003]] is needed: the gate already scores the NAS copy, so the VPS tail was only ever a local convenience.
- **The implementation** is a role task, not a gate-export extension — `roles/engine/` installs `zcrypto-engine-journal-prune` + a 01:23 UTC timer, `ProtectSystem=strict` with `ReadWritePaths` the journal dir alone.

**The design's load-bearing guard turned out not to be about disk at all.** `cli/engine/cycle.py` derives each cycle's orders as a delta against the most recent journaled cycle; with no prior record every delta becomes the full target and the engine rebuilds the whole book. An age-only prune reaches that state whenever the engine stops for longer than the retention window. So the prune **also keeps the newest N day-dirs regardless of age** — inert in healthy operation, and the only thing standing between a >60-day outage and a spurious whole-book rebuild.

Retention was never a capacity question: 13 MB/day against 51 GB free is ~11 years of headroom, which is why the design could pay any amount of caution for safety.

**Retention is 60 days, not the 14 originally ruled** — raised by the owner during implementation, *between* the two converges: the first deploy ran at 14, which is why the evidence below spans both values. The design is value-independent (both the cutoff and the floor read the same parameter), so only numbers moved: steady state ~780 MB, ~1,440 pull opportunities of margin.

**Deploy verified by outcome** (2026-07-26, converged at 14 and re-converged at 60): the deployed unit runs `... /var/lib/zcrypto-engine/journal 60` (confirmed via systemd's own resolved `argv[]`, not just the file on disk), timer armed for 01:23 UTC, service `static` (timer-only, so no prune on boot), and the engine container **not restarted** by either converge — `StartedAt` byte-identical across both, `RestartCount` 0.

The prune's correctness was proven on real data *before* the value changed, which is the more informative record: at 14 days a host `--dry-run` returned exactly the predicted `deleted=1 kept=15 cutoff="2026-07-12 UTC"` — the one eligible day, with the day sitting exactly *on* the cutoff correctly spared. At 60 it returns `deleted=0 kept=16 cutoff="2026-05-27 UTC"`; the oldest day is 15 days old, so **the timer is a verified no-op until ~2026-09-10**, when `2026-07-11` first becomes eligible.
