---
status: open
ripe_when: a gate-export run is observed exceeding ~20 min wall (a meaningful fraction of the 3600 s ARCHIVE_PULL_INTERVAL), OR the engine-journal exceeds ~500 MB / ~5000 files
---

# gate-export CPU cost — ~8 min per archive-pull cycle on a 96 MB journal

## Context — what

`zcrypto engine gate-export` (engine gate scoring, spec `00042`; run by the NAS archive-pull Role B loop each cycle, after the journal pull and before the ops-channel pulls — see `infra/nas/pull-entrypoint.sh`) is CPU-bound for **~8 min per hourly cycle** on the current **96 MB / 995-file** engine-journal. It terminates normally and the loop completes well within the 3600 s interval — this is a steady-state efficiency/scalability observation, **not** an availability outage.

## Why this matters

gate-export runs inline in the single-threaded archive-pull loop, so its ~8 min directly delays every ops-channel mirror pull that follows it in the same cycle, and it consumes ~8 min of the hourly budget. The engine-journal grows monotonically. ~8 min of CPU for a 96 MB journal is far more than a linear scan should cost, which suggests super-linear (repeated full-journal) work; if so, at some journal size the step approaches or exceeds `ARCHIVE_PULL_INTERVAL` (3600 s), at which point the loop can no longer keep up and the whole archive (capture backup **and** ops mirror) genuinely falls behind. Latent scalability risk, worth catching before it bites.

## Findings so far

- Observed 2026-07-18 ~19:40–19:49 (during spec `00057` fleet-users-groups Task 4): `zcrypto engine gate-export` at ~99 % CPU, **~8.5 min wall / ~8 min CPU**, on `/archive/engine-journal` = 96 MB / 995 files. It **completed** (initially mis-read as an infinite loop from a single mid-cycle CPU snapshot — corrected: it terminates, and the loop then pulled all four ops channels cleanly). Invocation: `zcrypto engine gate-export --journal-dir /archive/engine-journal --textfile /textfile/gate.prom --healthcheck-url <hc>`.
- The prior cycle's ops pull (18:57) implies the same ~8 min gate-export step, so this is the **steady-state** duration, not a spike — no regression tied to the Task-4 restart.
- The loop has no per-step timeout: a slow gate-export simply stretches the cycle; a hung one would stall it (not what happened here).
- **This topic also carries the gate-export relocation deferral (registered 2026-07-19).** Spec `00054` D6 deliberately kept gate-export on the NAS ("it works … moving it buys latency on a metric nobody is waiting on") and deferred a move "to OPS-6 or later, on its own merits" — but OPS-6 (spec `00056`) closed without scoping it, and the deferral's only home ([[T0033]]) is now archived, leaving it registered nowhere. It lands here because relocation to the ops node (i7-13700 vs the NAS Atom, and out of the single-threaded archive-pull loop entirely) is precisely the **structural remedy** for this topic's cost concern — the two questions are one decision.
- 2026-07-19 trigger check: journal mirror 108 MB / ~1000 files — both `ripe_when` thresholds (~500 MB / ~5000 files, ~20 min wall) still comfortably unfired.

## Suggested next steps

- **Reproduce + profile** (separate branch, engine subsystem — NOT the fleet-users-groups PR): copy a ~96 MB engine-journal to a scratch dir and run `uv run zcrypto engine gate-export --journal-dir <copy> --textfile /tmp/gate.prom`; time it and profile with `python -X importtime` / `cProfile` / `py-spy` to locate where the ~8 min CPU goes.
- **Determine the complexity** in the gate-export command (`cli/engine/` — the `gate-export` command function + whatever `engine gate-export` calls to score the journal): confirm whether it re-scans the entire journal on each call in a way that is O(n²) within one invocation (the suspect), vs a fine O(n) linear pass.
- **If super-linear, fix it** (incremental scoring, or cache the scored prefix) so per-cycle cost is bounded by the *new* journal tail, not the whole history.
- **Or relocate it to the ops node** (the spec-`00054`-D6 deferred option, homed here since 2026-07-19): run gate-export on the ops node against its NFS view of the journal and ship `gate.prom` back (or emit via the ops Alloy textfile collector), removing the step from the NAS pull loop entirely. Weigh against the profile result — an O(n) fix may make relocation unnecessary; relocation makes the CPU cost irrelevant but moves a Role-B deliverable across hosts (its healthcheck + textfile wiring follow). Decide profile-first: measure, then pick fix-in-place vs relocate.
- **Add observability:** log the gate-export wall/CPU duration each cycle (or emit it as a textfile-collector metric) so growth toward the 3600 s budget is visible in Grafana before a cycle ever overruns.
