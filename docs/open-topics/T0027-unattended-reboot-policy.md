---
status: partial
ripe_when: a live 6b order round-trip exists, so a reboot can be staged mid-order-submission.
---

# Unattended-upgrades auto-reboot policy for the live VPS

## Context — what

The capture/engine VPS runs `unattended-upgrades` configured to **auto-reboot at 21:25 UTC (re-decided 2026-07-14 from measured traffic — was 04:00, then 02:00; see `.claude/rules/fleet-deploys.md`)** whenever an update sets `/var/run/reboot-required` (typically a kernel upgrade). On **2026-07-11 04:00 UTC** it rebooted for kernel `6.12.88 → 6.12.95`; both containers auto-restarted cleanly (`restart: unless-stopped` + the `zcrypto-capture`/`zcrypto-engine` systemd units), capture gap ~83 s, engine `ExitCode 0`. This will recur on every future kernel/critical update.

## Why this matters

- **Capture (7-day mission):** one auto-reboot is a ~83 s gap ≈ **0.014 %** of a 7-day window — within the `<0.1 %` exit-bar budget for one or a few, but repeated unattended reboots erode the budget, and **each one is also a trade-segment-overwrite event** ([[T0026]]).
- **Engine (live — the bigger risk):** an **unattended** reboot at an arbitrary 04:00 UTC restarts the engine **mid-UTC-day**. During the **Stage-6a gate** (clock from 2026-07-11 00:00 UTC) an unplanned restart risks a disrupted/failed gate cycle; during **Stage-6b** (real orders) it risks an in-flight order-state / reconciliation problem. 04:00 UTC bears no relation to the engine's decision cadence.

## Findings so far

- 2026-07-11 event: clean recovery of both containers (details in [[T0003]] investigation). Config: `Unattended-Upgrade::Automatic-Reboot "true"`, `Automatic-Reboot-Time "04:00"` (04:00 UTC, host tz = UTC).
- The engine's day-1 (2026-07-11) gate cycle was verified **clean through the reboot** — see Done so far.
- **Fleet-window note (spec `00050`, 2026-07-17).** The capture fleet is now **two** hosts: primary `zcrypto` at **21:25 UTC** and secondary `zcrypto-red` at **22:25 UTC**, deliberately **+1 h apart** so a same-night kernel reboot never overlaps both and a failed primary reboot has time to page before the secondary follows. A converge-time assert that the two hosts' reboot times differ pins this fleet-window policy in config (spec `00050`; also [[T0033]]). The single-VPS policy question below still stands for the **engine** host — only the primary runs the engine.

## Done so far

- **(autonomous sub-item — DONE 2026-07-11) Engine day-1 gate cycle verified intact through the reboot.** The reboot killed the engine dead on the **04:00 UTC boundary** (a 4h cycle stamp), but `node.py`'s restart-inside-a-passable-window rule (`startup_action`) re-ran it: `cycle-04.json` is a **success** record — `started_at 04:01:24 → completed_at 04:01:34`, `cycle_ts 04:00:00` (the no-peek boundary invariant holds), completing at the same ~+90 s offset as every other cycle. Day 2026-07-11 is a **complete clean day**: all six cycles present, zero failed sidecars, and `zcrypto engine replay --date 2026-07-11 --path fast` recomputes **bit-identical** targets for all six (worst |diff| 0.00e+00, the 04:00 cycle included); `zcrypto engine report` shows **streak 1 clean day, last failure none**. So the **Stage-6a gate clock is intact from day 1** — the reboot cost the gate nothing.

## Decision + attended-reboot guideline (2026-07-23)

**The human ops decision is made: option (b) — attended reboots, capture VPSes only.** `zcrypto` and `zcrypto-red` get `Automatic-Reboot "false"`; ops keeps auto-reboot at 02:25 (its poller has recovered cleanly historically, and this keeps the standing manual duty minimal); the NAS is DSM — outside this regime either way. Security patches still auto-install; only the reboot becomes manual. Decided in the 2026-07-23 grooming session; **recorded now, executed later** — the flip rides its own small converge after `chore/topics-grooming` and PR #191 merge, never a rollout converge (one change at a time keeps rollout verification attributable).

**Skill placement — asked, answered, and then OVERTAKEN by how the work actually landed (2026-08-22).** The ruling here was: a separate skill, not part of [[T0084]]'s rollout skill, by T0084's own T0081-isolation precedent — different trigger (kernel flag vs new code), different procedure (no digest, no pre-staging, no bake). That reasoning still holds against *folding it into* T0084. What it did not anticipate is that no skill was the right shape at all: the guidance shipped as operating-surface text in `docs/reference/fleet.md` § Reboots, including the verify-by-outcome checks. See the disposition under `## Done so far` below; nothing here is owed.

The process the flip must come with (attended mode creates a new gap — a reboot flag nobody notices — so the harness is part of the decision, not an optional extra):

1. **Detect** — a small systemd timer writes `node_reboot_required 0|1` to the textfile collector (the same `integrations/unix` transport that already carries the NAS `gate.prom`), plus one alert rule → Slack. No regex, no new plumbing. Without this, attended mode silently stretches the security-patch window.
2. **Schedule** — the measured windows become *guidance for the human* instead of cron facts: traffic trough, ≥1 h off any 4h bar boundary, ≥1 h host separation. Engine host adds: right after a completed 4h cycle, never approaching a boundary; under 6b additionally no in-flight order ([[T0018]]).
3. **Order — attended mode flips spec `00050`'s ordering.** 00050's primary-first (21:25→22:25) is *unattended paging logic*: a failed primary reboot pages while the secondary still captures. Attended, with both hosts taking the **same new kernel**, canary logic wins: **secondary first, verify it boots and captures, then primary.** If the kernel bricks the secondary, the primary is never touched. The 00050 pairwise-distinct window assert stays — the windows remain meaningful as scheduling guidance.
4. **Verify** — the shared checklist (T0084's runbook) plus the reboot-specific expectations: ~83 s capture gap is the measured norm (2026-07-11), containers self-restart via `restart: unless-stopped` + the systemd units.

## Done so far — the flip and its detector (2026-07-26)

**The attended-reboot guidance shipped as operating-surface text, not as a skill (decided 2026-08-22, owner-approved).** This topic had asked for it as a sibling of [[T0081]]/[[T0084]]; both of those resolved and both skills exist, so that precondition fired. The work landed in a different shape: `docs/reference/fleet.md` § Reboots carries the whole discipline — secondary-before-primary canary order, the schedule constraints (≥1 h from any 4h bar boundary, off the hour, primary in the measured book-traffic trough, ≥1 h host separation, right after a completed engine cycle), the expected ~83 s capture gap, the alert that pages until the reboot happens, and — added in the same change, because this sub-item explicitly asked for it and § Reboots did not yet carry it — the verify-by-outcome checks a reboot owes. A skill was the wrong shape: `zcrypto-bump-alloy` and `zcrypto-rollout-image` wrap multi-host rollouts with canary ordering and verification, whereas a reboot is a single attended act with no staging, no digest and no bake — its whole procedure is when to go and what to read afterwards, which is five bullets of reference text, not a skill. Same disposition the iter-140 probe-checklist items took: operating-surface text, not a registration.

**The flip is live on both capture VPSes.** `Automatic-Reboot "false"`, verified on-host; `zcrypto-ops` still reads `"true"` at 02:25, untouched, because the role default preserves today's behaviour and only `group_vars/capture_host` overrides it. Patches still auto-install. Delivered by spec `00071`.

**The detector that makes attended mode safe is live and proven end-to-end.** `zcrypto-reboot-check` publishes `node_reboot_required` every 15 min; touching `/run/reboot-required` flipped it to 1 in Grafana Cloud and removing it returned it to 0. Four alert rules back it: pending-reboot, plus absent / unreadable / stale coverage for the transport itself.

**The recorded guideline's transport did not exist**, and that is the substantive finding. It called for "the same `integrations/unix` transport that already carries the NAS `gate.prom` — no regex, no new plumbing", but the capture hosts ran **no textfile collector** (dropped with spec `00069` for a reason that had since expired), and `integrations/unix` is static-mode Grafana Agent vocabulary this flow-mode fleet does not use. Building it was its own defect, [[T0100]], which had already cost [[T0021]] all of its observability.

**Ordering hazard, found before it fired:** this topic's own verification step — "touch and remove the flag file" — would have rebooted the live capture + engine primary had it run while `Automatic-Reboot` was still `"true"`, because a present `/run/reboot-required` is exactly what unattended-upgrades acts on. The flip was landed and verified first; the precondition was re-checked on-host in the same command that touched the flag.

**Reboot order is settled and recorded in `fleet-deploys.md`:** secondary first, then primary — the reverse of the image-rollout order, because if the kernel bricks the secondary the primary is never touched.

## Suggested next steps

- **(autonomous — a 6b requirement, still open) Confirm order-state reconciliation survives a reboot _mid-order-submission_.** The day-1 proof covers only the **shadow / data-only** cycle (exec disabled, no live orders); a reboot landing during a live 6b order round-trip is a distinct, untested path — [[T0018]]. **Instrument, 2026-08-29: spec `00105`'s drills A1, A2 and G — this step passes when those drill-log entries read `pass`.**
