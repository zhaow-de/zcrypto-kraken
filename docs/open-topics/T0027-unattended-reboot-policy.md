---
status: partial
ripe_when: before the Stage-6b executor session (live orders — the auto-reboot policy must be settled before real money), or on the next disruptive auto-reboot
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

## Suggested next steps

- **(autonomous — a 6b requirement, still open) Confirm order-state reconciliation survives a reboot _mid-order-submission_.** The day-1 proof covers only the **shadow / data-only** cycle (exec disabled, no live orders); a reboot landing during a live 6b order round-trip is a distinct, untested path — [[T0018]].
- **(human ops decision)** Choose the policy before live 6b: (a) keep auto-reboot but move `Automatic-Reboot-Time` to the least-disruptive point relative to the engine's UTC cadence + capture *\[the timing half of (a) is already enacted — 21:25/22:25 UTC measured from the archive traffic trough, ≥1 h off bar boundaries, fleet windows pairwise-distinct-asserted (spec `00050`, 2026-07-14); the residual decision is genuinely only auto-vs-attended\]*; (b) set `Automatic-Reboot "false"` and do **attended** kernel reboots (security patches still auto-install; only the reboot becomes manual — adds a standing maintenance duty, bounded by the intermittent-workstation reality in [[T0003]]); (c) keep auto-reboot through the capture-only phase, switch to attended before funding the live sleeve.
