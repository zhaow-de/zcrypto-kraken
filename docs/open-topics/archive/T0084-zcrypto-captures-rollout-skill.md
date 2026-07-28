---
status: resolved
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

- **Covers**: the scheduled segment-prune (`zcrypto-capture-prune.service`, 03:17 UTC) — the one recurring writer that mutates the capture data dir *concurrently with* the capture daemon, so a capture-image change that mishandled it would surface only across a prune; and a multi-hour **resource-slope** signal (RSS / threads / fds) that a sub-hour soak cannot produce with any power — under the smallest-window default (Done so far) that signal gets a **≥3-rotation-hour floor inside the window** plus a ~T+24 h post-re-pin re-read on both hosts.
- **Does not cover**: random infra loss. That is a runbook-and-failsafe problem, not a bake problem.
- **Minimal window** = max(time until the next prune completes cleanly on the just-converged host, ≥3 full segment-rotation hours — the slope floor) with every abort signal below clear. In the 2026-07-22 rollout that was ≈ 5.5 h (bounded by the 03:17 prune), an ~80 % cut from 24 h with essentially all the value retained. Skipping the bake entirely still requires the owner's explicit approval per `capture-deploys.md`; this determination shrinks the *default*, it does not remove the gate.
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
- **Owner rulings at build time (2026-07-27):** (1) **the fixed ≥24 h bake is DEPRECATED** — the default gate is the smallest event-coverage window between the two re-pins (with a ≥3-rotation-hour slope floor); `capture-deploys.md`'s canary language was reconciled in the same change, discharging the shrink step's "reconcile ≥24 h" clause early. (2) Invocation flipped to **user-only** (`disable-model-invocation: true`), overriding this topic's earlier model-invocation note. (3) **Host-touching commands run in the main loop only** — the permission gate blocks ssh-sudo inside dispatched workflows/subagents, observed live when a T0101 investigation strand died on exactly that.
- The Slack reminder is now scheduled at the **computed gate-open time**, not a fixed T+24 h.
- **The `capture-deploys.md` shrink landed early** (owner's word, 2026-07-27, same branch): the rule keeps the law — the never-re-pin invariant, the skip-or-degrade approval gate, pair-add ordering, the engine/reboot/vault sections — and points at the skill for every rollout mechanic; net −601 bytes always-loaded. A cold lossless check classified 9 of 11 removals RELOCATED at equal-or-greater precision and caught the one genuinely shared bullet — pre-stage/stop→start also serves engine and pair-add converges, which the skill's scope excludes — restored as a generic bullet.

## Resolution

**Resolved 2026-07-28: the skill ran a real rollout end to end, which was this topic's one remaining step** — secondary `zcrypto-red` converged 2026-07-27T23:58:41Z, primary `zcrypto` 2026-07-28T08:04:29Z, an 8 h 06 m event-coverage bake between them. The run *is* the validation (the T0081 pattern), and it found six defects that only an execution could surface; all six landed in `SKILL.md` in the same change.

**What the run proved.** The event-coverage gate replaced the fixed ≥24 h bake in practice, not just on paper: two complete rotation hours plus the current one, a prune fired on demand rather than waited for, and every abort signal read. Phase 5 came back clean — hour 08 (which spans the primary restart) begins at `08:00:00.014`–`08:00:00.619` on all 12 streams, the NAS pull hash-verified 9,982/9,982 primary and 6,952/6,952 secondary segments at `failed=0`, and `continuity.py` over 9 h × 12 streams reported 0 missing and 0 truncated hours, worst stream 0.0114% against the 0.1% bar. The engine on the same host was never touched (`StartedAt` unchanged), which is the failure mode `capture-deploys.md` warns about.

**The six corrections, each from something that actually went wrong:**

1. **Pre-staging was not gated where it matters.** Phase 0 pulls the candidate on each host, but that runs hours before the gate and nothing re-checks it — the primary was measured *missing* the candidate at Phase 3. A converge that pulls inside its own stop→start window is exactly what pre-staging exists to prevent, so it is now Phase 3's item 0.
2. **Phase 5 was written as post-primary only**, so the secondary leg had no step telling it to update `fleet-pins.md`. That file then claimed the wrong digest for a live host for eight hours. Phase 5 now runs after *every* converge.
3. **The Cloud read-back had no operand.** `grafana-push.sh` requires `GRAFANA_SA_TOKEN` in its env and never obtains it, and spec `00043`'s plan documents a method that cannot work on per-variable `!vault` scalars — so the check was improvised, and cost two failed attempts. `infra/scripts/grafana-query.py` now encapsulates it.
4. **The alloy container is `grafana-alloy`**, not `zcrypto-alloy`; an inspect on the wrong name errors rather than reporting a restart.
5. **The `<HH>.parquet` boundary check cannot run on a capture host** — no `pyarrow`, no repo CLI, so a book final cannot be opened there at all. It has to read the pulled copy, which the deploy rule already prescribes for a different reason.
6. **The NAS pull loop is a container, not a systemd unit.** `journalctl -u zcrypto-archive-pull.service` returns empty — which reads as "no pull ran" rather than "wrong place", the exact shape `agent-ops.md` warns about when an empty query is mistaken for an absent event.

**Two degradations, each accepted explicitly by the owner at the step rather than noted afterwards**, which is what the skill demands: the prune ran in the weak form (`deleted=0` — the secondary's archive begins on the cutoff date), and one abort row read red and was discounted because the signal, not the image, is broken ([[T0106]], opened by this run).

## Suggested next steps

_(none — the skill is built, it has run a real rollout, and that run's corrections are in it. A future rollout that finds more corrections lands them the same way, which is the skill's own instruction rather than an open item here.)_
