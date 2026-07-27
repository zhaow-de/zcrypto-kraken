---
status: partial
ripe_when: the next capture-image rollout — it runs VIA the skill and is the skill's validation (the T0081 pattern); the pending T0008/T0101 capture image is the standing candidate, and the capture-deploys.md shrink keys on that run completing
---

# `/zcrypto-captures-rollout` — wrap the capture-image canary rollout into a skill

## Context — what

The capture-image rollout discipline (canary order, ≥24 h secondary bake, Slack T+24h reminder, primary re-pin gates, verification by outcome) lives in `.claude/rules/capture-deploys.md` — an always-loaded rule file that cannot be scoped to a path, so it sits in every session's context forever. This topic tracks wrapping the procedure into a skill callable by human or model, so the discipline is *executable* rather than ambient.

Deliberately isolated from [[T0081]] (the Alloy bump skill): different procedure, different risk profile (capture images restart unbackfillable capture; Alloy is telemetry-only), different triggers.

## Why this matters

Standing rules grow context on every session whether or not a rollout is near; a skill loads only when invoked. And a procedure encoded as an executable checklist (with its gates as steps) is harder to half-follow than one recalled from ambient prose — the canary rule's history shows the cost of a missed step is permanent data loss.

## Findings so far

- `capture-deploys.md` already contains the full procedure: canary rule, digest verification by label, pre-staging, stop→start window contents, outcome verification (`<HH>.parquet` boundaries, manifests, continuity.py), maintenance windows, and the Slack-scheduled T+24h reminder.
- The rule file cannot shrink to a pointer until the skill exists and has run at least one real rollout.
- **The 24 h bake is a fixed clock standing in for an event-driven gate** (determined during the 00068/00069 rollout, 2026-07-22 — see the runbook section below). It defends only against a *correlated bad deploy* (where the un-converged host is the surviving control), never against random VPS loss — a bake is not a durability measure, and cloud VPS resources fail without regard to any window. The skill should encode the bake as **event-coverage** (span the next scheduled prune plus ≥1 segment-rotation hour with all abort signals clear), not a fixed 24 h, and pair it with the written healthcheck + rollback runbook so the wait is a real gate rather than crossed fingers.

## Rollout healthcheck + failsafe runbook

Distilled from the 00068/00069 attended rollout (2026-07-22). This is the substance the skill's "bake + verify + abort" steps should encode; it is written to be executable as-is in the meantime.

### What the bake actually buys (and does not)

- **Covers**: the scheduled segment-prune (`zcrypto-capture-prune.service`, 03:17 UTC) — the one recurring writer that mutates the capture data dir *concurrently with* the capture daemon, so a capture-image change that mishandled it would surface only across a prune; and a multi-hour **resource-slope** signal (RSS / threads / fds) that a sub-hour soak cannot produce with any power — under the smallest-window default (Done so far) that signal moves to a **post-re-pin watch** at ~T+6 h and ~T+24 h rather than a pre-re-pin wait.
- **Does not cover**: random infra loss. That is a runbook-and-failsafe problem, not a bake problem.
- **Minimal window** = max(time until the next prune completes cleanly on the just-converged host, ≥1 full segment-rotation hour) with every abort signal below clear. In the 2026-07-22 rollout that was ≈ 5.5 h (bounded by the 03:17 prune), an ~80 % cut from 24 h with essentially all the value retained. Skipping the bake entirely still requires the owner's explicit approval per `capture-deploys.md`; this determination shrinks the *default*, it does not remove the gate.
- **The prune wait is collapsible on demand (2026-07-23 addendum).** The constraint is *a clean prune under the new image*, not the clock: `sudo systemctl start zcrypto-capture-prune.service` on the just-converged host fires it immediately, turning the up-to-24 h wait into minutes with zero standing change — raising the scheduled cadence was considered and declined (it would alter a steady-state production process, retune the dead-man's expected cadence, and multiply the concurrent-deletion windows in normal operation, all to serve a rare rollout gate). **Caveat — read `deleted=N` in the result**: a `deleted=0` run exercises the scan concurrently with capture writes but never the deletion path, and is the weaker signal; note which form the bake actually got. Measured 2026-07-22: the secondary's archive is younger than its 14-day retention (`cutoff=2026-07-08, deleted=0`), so its prunes are scan-only until ≈ 2026-07-29 regardless of trigger; check `deleted=N` on the primary's first post-converge prune — its older archive may already be deleting daily, which is where the strong-form coverage lives today.

### Abort signals — monitor on the just-converged host; any one trips a rollback decision

Read from the daemon's own `/metrics` (`:9101` capture / `:9102` engine / `:9103` liquidations, loopback) and `docker inspect`:

- `zcrypto_logship_dropped_lines_total` **> 0** (was 0 at converge) — direct-ship is shedding load.
- `zcrypto_logship_last_success_timestamp_seconds` **stale > ~120 s** — ship worker wedged.
- `RestartCount` **> 0** on the capture or alloy container — crash loop.
- Capture stdout carries `quarantined` / `ambiguous` / `merge failed` (the resubscribe-**replay** `dropping ... event` burst in the first seconds after a restart is healthy, not a signal — `capture-deploys.md`).
- Newest `<HH>.parquet` **not advancing** (`find <data-dir> -name '*.parquet' -mmin -3` returns 0) — capture stalled.
- RSS **slope** materially positive across the bake against the daemon's own earlier samples (never a cross-host RSS comparison — the hosts carry different `mem_limit`s: primary 2 GiB, secondary 1 GiB).
- The 03:17 prune unit does **not** finish `Result=success`.

### Rollback — verified feasible, no pull required

The previous-good digest is retained locally on **both** capture hosts (confirmed 2026-07-22: `sha256:63708539c3f9…` present, 8 days old, not GC'd), so a rollback is a re-pin of the compose file to that digest + `docker compose up -d` — no registry round-trip, ≈ 2 min. Sequence: edit the compose image pin back to the retained digest → `docker compose up -d` in the project dir → re-verify the same positive traces (up==1, ship succeeding, parquet advancing). Because the previous image is exactly the running-until-now code, rollback re-opens no data gap.

### Pre-re-pin verification (primary)

Identical to the Slack T+24h reminder's 7-point checklist (running digest == candidate, `StartedAt` ≥ window with `RestartCount` 0, capture green, dead-man `Result=success`, `dropped_lines_total` 0 + fresh `last_success`, Alloy `remote_storage_samples_failed_total` 0 + `up{job="capture_app"}`==1, `continuity.py` on a *pulled* copy shows no new truncated hours). The skill should emit this checklist as its own gate step, not rely on the ambient reminder.

## Done so far

- **The skill is BUILT** — `.claude/skills/zcrypto-captures-rollout/SKILL.md` (branch `feat/t0084-captures-rollout-skill`): five phases encoding the runbook above verbatim-in-substance — preflight with the rollback operand captured up front, secondary converge, the event-coverage bake with the abort-signal table, the 7-point primary gate emitted as the skill's own step, the no-pull rollback, verify-by-outcome with the fleet-pins update.
- **Owner rulings at build time (2026-07-27):** (1) **the fixed ≥24 h bake is DEPRECATED** — the default gate is the smallest event-coverage window between the two re-pins; `capture-deploys.md`'s canary language was reconciled in the same change, discharging the shrink step's "reconcile ≥24 h" clause early. (2) Invocation flipped to **user-only** (`disable-model-invocation: true`), overriding this topic's earlier model-invocation note. (3) **Host-touching commands run in the main loop only** — the permission gate blocks ssh-sudo inside dispatched workflows/subagents, observed live when a T0101 investigation strand died on exactly that.
- The Slack reminder is now scheduled at the **computed gate-open time**, not a fixed T+24 h.

## Suggested next steps

- **(At the next capture-image rollout)** Run it via the skill — the run is the validation, and corrections land in `SKILL.md` in the same change (the T0081 pattern).
- **(After that run)** Shrink `capture-deploys.md` to the invariants + a pointer to the skill; the rule file keeps only what must hold even outside a rollout (SSH posture, vault safety, window times). The "≥ 24 h" reconciliation already landed with the build.
