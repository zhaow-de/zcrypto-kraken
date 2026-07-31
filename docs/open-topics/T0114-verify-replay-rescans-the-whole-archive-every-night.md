---
status: open
ripe_when: RIPE NOW — the runway is ~42 days, now measured END TO END rather than extrapolated. A full unwindowed run on 2026-07-30/31 took **7 h 40 m for 5,724 canonical hours = 4.82 s/hour**, growing +288 hours/day (12 pairs x 24 h). Runtime reaches the 24 h cadence at ~17,900 hours, i.e. around **2026-09-11**. (The earlier 4.08 s/hour figure came from the windowed subset and understated it by 18 %.) Both operands are checkable without new instrumentation: count canonical hours with `cli.archive.reader.canonical_segments`, and read the run's own start/finish from `journalctl -u zcrypto-verify-replay.service`
---

# `verify-replay` re-verifies the entire archive every night, and cannot be windowed

## Context — what

`zcrypto archive verify-replay` replays every canonical book hour through `OrderBook` on every run. Measured end to end 2026-07-30/31: **5,724 canonical hours in 7 h 40 m = 4.82 s/hour**, and the archive grows **+288 hours/day** (12 pairs x 24 h, ~5 %/day at today's size).

**The runway is computable and short: runtime reaches the 24 h daily cadence at ~17,900 hours, about 42 days out (~2026-09-11).** Linear extrapolation, which is fair here because each hour is an independent parquet read plus replay.

The obvious mitigation — window the sweep with the CLI's existing `--since` — was tried that evening (spec `00076` D7) and **failed in production**: 1,870 of 2,218 hours reported `anchored=False`, every other check clean. The cause is structural, and `verify_replay`'s own docstring already stated it: *"a hole opened by `--pair`/`--since` counts as 'predecessor not present', same as a real archive gap."* An hour is chain-anchored iff it opens with a snapshot **or** its predecessor was present in the same enumeration and was itself anchored; a window cuts the chain.

Anchor-aware windowing (walk back to the last snapshot, replay from there, report only the window) was then measured and rejected too — see below.

## Why this matters

- **A 7 h 40 m nightly job on a daily timer has a ~42-day runway**, and it is not a cliff the instrument announces: `Type=oneshot` has no start timeout, so an over-running pass is simply skipped by the next tick rather than reported. The node also auto-reboots at 02:25 UTC, which a long run must clear.
- **The 2026-07-30 windowing incident under-measured this twice, and both errors are worth keeping.** First the hour count: the failing run's own output said "replayed 2218 hour(s)" and that number was taken as the archive size — it was the *windowed subset* (7 days x 12 pairs), while the archive is 5,724. Then the rate: 4.08 s/hour derived from that same subset understated the real 4.82 s/hour by 18 %, because a windowed sweep skips the per-pair setup the full one pays. Reading an instrument's output without asking what population it covers is the same class of mistake the whole T0097 thread was about — and it recurred within one evening, in the topic written to record the first instance.
- **The instrument cannot be scoped for investigation.** `--since`/`--pair` remain correct for *ad-hoc* narrow questions only if the operator accepts that `anchored` is meaningless in the narrowed view — a sharp edge on the tool the archive's integrity story depends on.
- Every hour of runtime is also an hour of the reconciled overlay being read under a `ro,soft` NFS mount.
- **A second, earlier cliff sits in front of the runtime one: journald's rate limit, around 2026-08-15.** Since spec `00077` the runner captures the sweep's output and replays it to the journal in one burst (`cat` of the temp file). journald drops anything past **`RateLimitBurst=10000` per 30 s per unit** *before Alloy sees it* — the fact `infra/ansible/roles/ops/files/config.alloy` already records. Today's sweep emits ~5,726 lines (one per hour plus two summaries) and grows +288/day, so at the nominal burst it crosses 10,000 around **2026-08-15**, ~27 days before the runtime cliff. Treat that date as a **floor, not a prediction**: journald scales the *effective* burst up with free journal disk space, so the real crossing may be later — never earlier. Measure before relying on it (`systemd-analyze cat-config systemd/journald.conf` on the host) rather than trusting the nominal figure. What gets dropped is the **tail** — the most recent hours' findings and both summary lines — which is precisely what the new-breakage alert and the runbook tell an operator to read. Alerting itself is unaffected (the counts are parsed from the temp file, not the journal). The checkpointed-incremental fix below dissolves this too, by making the per-run output proportional to *new* hours; the alternative stopgap is `LogRateLimitBurst=` on the unit.

## Findings so far

- **Snapshot anchors are extremely rare, and rarer the healthier capture is.** Measured 2026-07-30 across the canonical tree: each of the 10 EUR pairs has **7 anchors in 537 hours, the most recent 2026-07-13** — 17 days stale. The two BTC-quoted pairs have exactly **1** (their 2026-07-23 genesis), which is the only reason they passed the 7-day windowed run. Anchors arrive on reconnect/resubscribe; since the T0035/T0008 recovery work landed, capture has not reconnected.
- **Therefore anchor-aware windowing does not converge**: anchoring a 7-day window today requires replaying back to 07-13 — effectively the whole archive — and the required lookback grows every day the stream stays healthy. A mitigation that gets more expensive the better the system behaves is not a mitigation.
- The paging half of the original problem is being solved separately and cheaply (alert on *newly*-failed hours rather than on exit code), which removes the schedule pressure but not the runtime.

## Suggested next steps

- *(autonomous, the design)* **Checkpoint the chain state.** Replay fully once; persist per pair the last known-good `(hour, anchored, error-free)` plus the reconstructed `OrderBook` state; on subsequent runs resume from the checkpoint and verify only new hours. Design questions to settle first: the checkpoint's on-disk format and where it lives (ops-local, not the replicated overlay — see the [[T0057]] lesson about writing into a replicated tree); **invalidation when the reconciler rewrites an already-verified overlay hour** (the checkpoint must not certify a hour that later changed — a content hash per verified hour is the obvious guard); and what a corrupt or absent checkpoint does (fall back to a full replay, loudly, never silently skip).
- *(autonomous)* Once checkpointing exists, re-evaluate whether a genuinely windowed verify is worth having at all — with an incremental run the motivation largely disappears.
- *(autonomous, cheap, independent)* Publish the run's wall-clock duration and the hour count as metrics, so the runway is trended by the instrument rather than re-derived by hand. Not a precondition for the trigger — the `ripe_when` above is satisfiable today from the journal and a canonical-hour count — but it is what turns a computed deadline into a watched one.
