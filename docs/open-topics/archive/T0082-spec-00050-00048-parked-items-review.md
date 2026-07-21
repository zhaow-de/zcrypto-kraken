---
status: resolved
---

# One-shot revival review of spec 00050's non-goals and spec 00048's open questions

## Context — what

Spec `00050` (Role C redundant capture) declared several non-goals to bound its PR, and spec `00048` carries an "Open questions / risks" section. Both lists were deliberate scope cuts made under delivery pressure. This topic is a single review pass over both: assess each parked item and revive the ones that still matter as their own topics.

## Why this matters

A scope cut made to bound a PR is not a decision that the item is worthless — but a parked item with no `ripe_when` is invisible to every future work-picking pass (the standing deferral rule: prose is not registration). One deliberate sweep either registers or consciously drops each, after which nothing in those specs is silently parked.

## Findings so far

_(none at open — the review was the work; its findings are the Resolution below)_

## Resolution (2026-07-21, /zcrypto-auto-exec) — all 15 items dispositioned; one revival

**Spec `00050` non-goals (11):**

1. *Correlated-desync protection* — **drop**: already registered on [[T0008]] (partial; its residuals carry observed-event triggers).
2. *Cross-host row-level book merging* — **drop**: the spec's own rationale stands (measures coalescing, corrupts the book); no consumer wants it.
3. *CRC replay in the hourly loop* — **drop, delivered differently**: verify-replay runs on the ops node (OPS-3/spec 00051; `ops_verify_replay_*` series pinned in the keep-list tests).
4. *Feeding reconciled L2 into live trading* — **drop**: 00048's scope guard stands on its own rationale (research/archive artifact); no consumer proposes it.
5. *Third source / N-way reconciliation* — **drop**: no trigger; the live slice of this concern (provider correlation) is revived as [[T0088]].
6. *Moving Roles A/B or the reconciler to ops* — **drop, partially delivered**: the reconciler + trade-backfill already moved to ops at OPS-5 (`infra/ops/README.md`; the NAS pull-entrypoint says so); the remaining live slice — gate-export (Role B) relocation — is tracked on [[T0069]] (post-gate, queued); no trigger exists for moving Role A.
7. *Alloy/host metrics on the secondary* — **drop, delivered**: all four hosts ship host-level Alloy since iter-105 (2026-07-19; [[T0020]]).
8. *T0032 probe-outage blind spot* — **drop**: tracked on [[T0032]]'s `ripe_when` (fix `3e03aac` rides the next capture-image rollout).
9. *REST trade-backfill* — **drop, delivered**: [[T0050]] resolved (iter-100); daily, alerted.
10. *Multi-provider diversification* — **REVIVED as [[T0088]]**: the only parked item with a live trigger today — "revisit before scaling capital" is dated by the approaching 6b live-capital decision, and it was registered nowhere.
11. *Retro-healing pre-secondary gaps* — **drop**: physically impossible (nothing to splice from); the trades side was later REST-healed anyway ([[T0050]]).

**Spec `00048` open questions (4):**

12. *Capture ToS/rate coupling* — **drop**: answered inline in the spec (unauthenticated public WS, no per-account coupling) and moot in the shipped topology.
13. *In-container scheduler robustness* — **drop, delivered**: the pull-lag dead-man plus the `NAS/Ops · archive-pull stalled` alert rules are live.
14. *NAS resource headroom* — **drop, watched**: host metrics + alerts cover it; the one identified pressure point — gate-export, projected ~10.9 s/cycle on the Atom from the 2026-07-18 datapoint — is tracked on [[T0069]].
15. *Reconciliation edge cases (disagreeing windows)* — **drop, delivered + pinned**: primary-wins with the secondary deficit as a QA signal, `both_streams_silent` ledgered + paged, `total_loss`, dedup-with-count idempotency — 58 tests across `tests/test_archive_reconcile{,_command}.py`.

After this pass nothing in either spec is silently parked: every item is delivered, tracked on a registered topic, revived ([[T0088]]), or explicitly dropped above. One-shot by design — closed in the same pass.

## Suggested next steps

_(none — the original single step, the review itself, completed above; no remainder exists)_
