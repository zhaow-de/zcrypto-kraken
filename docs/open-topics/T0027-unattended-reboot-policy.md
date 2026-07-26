---
status: partial
ripe_when: implementation (config flip + reboot-required alert) — after `chore/topics-grooming` and PR #191 both merge to develop (the flip gets its own small converge, never folded into a rollout); the mid-order reconciliation test — before the Stage-6b executor session
---

# Unattended-upgrades auto-reboot policy for the live VPS

## Context — what

The capture/engine VPS runs `unattended-upgrades` configured to **auto-reboot at 21:25 UTC (re-decided 2026-07-14 from measured traffic — was 04:00, then 02:00; see `.claude/rules/capture-deploys.md`)** whenever an update sets `/var/run/reboot-required` (typically a kernel upgrade). On **2026-07-11 04:00 UTC** it rebooted for kernel `6.12.88 → 6.12.95`; both containers auto-restarted cleanly (`restart: unless-stopped` + the `zcrypto-capture`/`zcrypto-engine` systemd units), capture gap ~83 s, engine `ExitCode 0`. This will recur on every future kernel/critical update.

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

**Skill placement (asked and answered): a separate skill, not part of [[T0084]]'s rollout skill** — by T0084's own T0081-isolation precedent: different trigger (kernel flag vs new code), different procedure (no digest, no pre-staging, no bake), different failure mode (kernel doesn't come back vs bad application code). What they share is the post-disruption verification **tail** — factor T0084's healthcheck/abort/rollback checklist into a common reference both skills load when the skill family gets built.

The process the flip must come with (attended mode creates a new gap — a reboot flag nobody notices — so the harness is part of the decision, not an optional extra):

1. **Detect** — a small systemd timer writes `node_reboot_required 0|1` to the textfile collector (the same `integrations/unix` transport that already carries the NAS `gate.prom`), plus one alert rule → Slack. No regex, no new plumbing. Without this, attended mode silently stretches the security-patch window.
2. **Schedule** — the measured windows become *guidance for the human* instead of cron facts: traffic trough, ≥1 h off any 4h bar boundary, ≥1 h host separation. Engine host adds: right after a completed 4h cycle, never approaching a boundary; under 6b additionally no in-flight order ([[T0018]]).
3. **Order — attended mode flips spec `00050`'s ordering.** 00050's primary-first (21:25→22:25) is *unattended paging logic*: a failed primary reboot pages while the secondary still captures. Attended, with both hosts taking the **same new kernel**, canary logic wins: **secondary first, verify it boots and captures, then primary.** If the kernel bricks the secondary, the primary is never touched. The 00050 pairwise-distinct window assert stays — the windows remain meaningful as scheduling guidance.
4. **Verify** — the shared checklist (T0084's runbook) plus the reboot-specific expectations: ~83 s capture gap is the measured norm (2026-07-11), containers self-restart via `restart: unless-stopped` + the systemd units.

## Suggested next steps

- **(autonomous — ripe when this topic's trigger fires) Land the flip + detection harness as one small iteration:** Ansible `Automatic-Reboot "false"` for `zcrypto` + `zcrypto-red` only (base role — `--check --diff` first; a pure `/etc/apt` change, no compose render, no capture restart), the `node_reboot_required` textfile timer + alert rule → Slack, verified end-to-end by touching and removing the flag file on one host.
- **(autonomous — a 6b requirement, still open) Confirm order-state reconciliation survives a reboot _mid-order-submission_.** The day-1 proof covers only the **shadow / data-only** cycle (exec disabled, no live orders); a reboot landing during a live 6b order round-trip is a distinct, untested path — [[T0018]].
- **(when the skill family gets built)** The attended-reboot skill as a sibling of [[T0081]]/[[T0084]], sharing the post-disruption verification checklist as a common reference.
