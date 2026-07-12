---
status: open
ripe_when: before the Stage-6b executor session (live orders — the auto-reboot policy must be settled before real money), or on the next disruptive auto-reboot
---

# Unattended-upgrades auto-reboot policy for the live VPS

## Context — what

The capture/engine VPS runs `unattended-upgrades` configured to **auto-reboot at 04:00 UTC** whenever an update sets `/var/run/reboot-required` (typically a kernel upgrade). On **2026-07-11 04:00 UTC** it rebooted for kernel `6.12.88 → 6.12.95`; both containers auto-restarted cleanly (`restart: unless-stopped` + the `zcrypto-capture`/`zcrypto-engine` systemd units), capture gap ~83 s, engine `ExitCode 0`. This will recur on every future kernel/critical update.

## Why this matters

- **Capture (7-day mission):** one auto-reboot is a ~83 s gap ≈ **0.014 %** of a 7-day window — within the `<0.1 %` exit-bar budget for one or a few, but repeated unattended reboots erode the budget, and **each one is also a trade-segment-overwrite event** ([[T0026]]).
- **Engine (live — the bigger risk):** an **unattended** reboot at an arbitrary 04:00 UTC restarts the engine **mid-UTC-day**. During the **Stage-6a gate** (clock from 2026-07-11 00:00 UTC) an unplanned restart risks a disrupted/failed gate cycle; during **Stage-6b** (real orders) it risks an in-flight order-state / reconciliation problem. 04:00 UTC bears no relation to the engine's decision cadence.

## Findings so far

- 2026-07-11 event: clean recovery of both containers (details in [[T0003]] investigation). Config: `Unattended-Upgrade::Automatic-Reboot "true"`, `Automatic-Reboot-Time "04:00"` (04:00 UTC, host tz = UTC).
- The engine's day-1 (2026-07-11) gate cycle was **not yet checked** for reboot impact — see next steps (this is the autonomous sub-item that feeds the decision).

## Suggested next steps

- **(autonomous — feeds the decision) Verify the engine's 2026-07-11 gate cycle** survived the 04:00 UTC reboot cleanly (complete-UTC-day journal + verified replay), so we know whether the Stage-6a clock is intact from day 1.
- **(autonomous — a 6b requirement anyway) Confirm the engine tolerates an unplanned mid-cycle restart** idempotently (no partial-order state, deterministic recovery) — [[T0018]].
- **(human ops decision)** Choose the policy before live 6b: (a) keep auto-reboot but move `Automatic-Reboot-Time` to the least-disruptive point relative to the engine's UTC cadence + capture; (b) set `Automatic-Reboot "false"` and do **attended** kernel reboots (security patches still auto-install; only the reboot becomes manual — adds a standing maintenance duty, bounded by the intermittent-workstation reality in [[T0003]]); (c) keep auto-reboot through the capture-only phase, switch to attended before funding the live sleeve.
