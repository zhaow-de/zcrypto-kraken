---
status: partial
ripe_when: 2026-07-20 — linearity MEASURED on the ops i7 (39 controlled runs); the NAS Atom's ~10.9 s/cycle is DERIVED from this topic's single 2026-07-18 datapoint on that host, not a fresh controlled benchmark, so the original "~20 min wall" trigger projects to fire ≈2026-07-29 and 50% of the hourly budget ≈2026-08-07; treat the remedy (incremental scoring, and/or the relocation to ops) as ripe NOW rather than waiting for the trigger
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

## Done so far — profiled + root-caused 2026-07-20 (iter-108 sprint, ops node)

**The super-linear hypothesis is REFUTED; the real cost is N full strategy rebuilds.**

*Scaling* (ops i7-13700, journal subsets 1→7 days, `zcrypto engine gate-export` wall-clock):

| cycles | 6 | 12 | 18 | 24 | 30 | 36 | 39 |
|---|---|---|---|---|---|---|---|
| wall (s) | 10.00 | 19.69 | 29.16 | 38.77 | 48.22 | 57.82 | 62.51 |
| **s/cycle** | 1.667 | 1.640 | 1.620 | 1.615 | 1.607 | 1.606 | **1.603** |

Per-cycle cost is flat (slightly *decreasing* as fixed startup amortizes); every step matches linear and none is near quadratic (6→12 cycles: ×1.97 measured vs ×2.00 linear / ×4.00 quadratic). **gate-export is O(n) — there is no O(n²) bug to fix.**

*Root cause* (`cProfile`, 7-day journal, cumulative):

| | calls | cum s | share |
|---|---|---|---|
| `replay_cycle` | 39 | 148.3 | — |
| `build_crossfreq_system_fast` | **39** | **120.6** | **81%** |
| `snapshot_content_hash` | 780 | 21.4 | 14% |

(Share is against `replay_cycle`'s 148.3 s cumulative; cProfile reports a 146.6 s total — the ~1.7 s excess is profiler attribution/rounding, so the figure is 81–82% either way. These are *profiled* seconds, inflated ~2.4× by instrumentation; every rate and projection below uses only the unprofiled 62.51 s wall-clock.)

`_evaluate_journal` calls `replay_cycle` **once per journaled cycle**, and each replay runs a **full ~28k-bar, 10-asset, 12-year strategy rebuild** (~3.1 s). So each hourly run re-verifies the *entire* journal from scratch, redoing every previously-verified cycle. The journal is append-only and hash-verified, so all but the newest cycle were already verified on the previous run.

*Budget extrapolation* (linear, NAS Atom at ~10.9 s/cycle — derived from this topic's own 8.5 min / ~47-cycle observation; the Atom is ~6.8× slower than the ops i7):

| threshold | NAS Atom | ops i7 |
|---|---|---|
| the topic's own "~20 min wall" trigger | **≈2026-07-29** (110 cycles) | ~2026-12 |
| 50% of the 3600 s pull interval | **≈2026-08-07** (166 cycles, 28 d of journal) | ~187 d |
| 100% — the loop can no longer keep up | **≈2026-09-04** (332 cycles, 55 d) | ~374 d |

This **corrects the 2026-07-19 trigger check** ("both thresholds still comfortably unfired"): they were unfired *then*, but the linear projection puts the first one ~9 days out. Linear is not safe when the input grows without bound on a slow CPU.

*Remedy comparison, now evidence-backed:*

- **Incremental scoring** (cache the verified prefix; replay only new cycles) — attacks the actual cause. Bounds the hourly cost at roughly ONE cycle's rebuild (~11 s on the Atom) **regardless of journal growth**: a ~47× cut today and permanently flat. Correctness risk is real (it caches gate evidence), so it wants its own iteration with the cache keyed on the journal's content hashes and a full-recompute escape hatch. **Key the cache on a builder/config version tag as well as the journal hashes** — a content hash detects only *journal*-side change, so a revision to `build_crossfreq_system_fast` or `CrossfreqSystemConfig` would otherwise keep serving stale pre-change outcomes forever, the price data and therefore its hash being unchanged. That is the one scenario that legitimately requires re-replaying already-verified cycles. The escape hatch itself is.
- **Relocation to ops** (the spec-`00054`-D6 deferred option) — buys a *constant* ~6.8× (55 → 374 days) and removes the step from the single-threaded archive-pull loop entirely. Cheaper and lower-risk, but it does not stop the growth; it postpones it.

**Recommendation: do both, incremental first.** Incremental scoring is the structural fix (bounded, not merely postponed); relocation is a complementary operational win that also decouples the pull loop. Relocation is an **attended** deploy (it moves a Role-B deliverable across hosts, with its healthcheck + textfile wiring), so it is parked for a maintenance window.

### Update 2026-07-20 (iter-110, spec `00060`) — incremental scoring landed

The structural fix is **built and verified**, opt-in via `gate-export --cache PATH` (no flag ⇒ today's behaviour byte-for-byte; `report` is never cached). Measured on the ops journal mirror (39 cycles):

| run | wall | replayed | from cache |
|---|---|---|---|
| no `--cache` | 63.11 s | 39 | 0 |
| `--cache` cold | 62.77 s | 39 | 0 |
| `--cache` warm | **0.30 s** | 0 | 39 |

**Gate metrics were identical across all three runs** — the load-bearing property (a cache hit is indistinguishable from a fresh replay) verified on real production evidence, not just fixtures. Cold costs the same as no-cache, so there is no overhead penalty for enabling it.

The 212× is the zero-new-cycles case; steady state is one new cycle per hour ⇒ ~2 s here and ~13 s on the Atom (vs ~510 s today, ~39×). The point is not the ratio but that **the cost stops growing with the journal**, which is what dissolves the ≈2026-08-07 / ≈2026-09-04 budget deadlines projected above. Precisely: the *expensive* term (a full strategy rebuild per cycle, iter-109's 81%) is now bounded to the new cycles only — `_journal_artifacts` still walks every artifact and `evidence_fingerprint` still hashes every record's snapshots each run, a genuinely O(n) scan/hash term with a small constant (the 0.30 s warm run over 39 cycles IS that term) — seconds even at the projected 332-cycle horizon, so the deadlines stay dissolved.

Safety: the cache invalidates wholesale on any change to the ten modules on the replay call graph, the effective config, or the replay path; per-cycle entries key on the **full** `SnapshotEntry` (not just `content_hash`, so a metadata tamper the real replay would reject cannot be served as a cached pass); it fails open on any cache problem. The residual — the execution *environment* (numpy/Python) is not fingerprinted — is registered as [[T0074]].

**Still open here: the attended relocation to the ops node**, and enabling `--cache` in the deployment (both need a maintenance window; the code ships inert until then).

## Suggested next steps

- **(Autonomous, the structural fix — recommended first)** Implement **incremental scoring** in `_evaluate_journal`: persist a cache of already-verified cycles keyed on the journal's own `content_hash` values, replay only cycles absent from it, and keep a full-recompute escape hatch (a flag, plus automatic invalidation if any cached hash no longer matches). This is gate *evidence*, so it wants its own iteration with TDD: a cache hit must be provably identical to a fresh replay, a tampered/renamed journal must miss the cache rather than trust it, and the streak arithmetic must be unchanged. Expected effect: hourly cost drops from ~8.5 min (rising) to roughly one cycle's rebuild (~11 s on the Atom) and stays flat as the journal grows.
- **(ATTENDED — parked for a maintenance window)** Relocate gate-export to the ops node (spec `00054` D6's deferred option): run it against ops' own journal mirror and ship `gate.prom` back, or emit it via the ops Alloy textfile collector. Buys a constant ~6.8× and removes the step from the single-threaded archive-pull loop entirely. Attended because it moves a Role-B deliverable across hosts, with its healthcheck + textfile wiring following. Complementary to incremental scoring, not a substitute — it postpones the growth rather than bounding it.
- **(Autonomous, cheap)** Emit the gate-export wall/CPU duration each cycle as a textfile-collector metric so the approach to the 3600 s budget is visible in Grafana rather than inferred from a linear projection.
