---
status: open
ripe_when: the secondary capture daemon reaches T+48 h restart-free from its 2026-08-11 14:13:17Z converge (i.e. from 2026-08-13 ~14:13Z, while `RestartCount` is still 0) — re-read the 1 h RSS floor trajectory and compare any second step's amplitude against the first's +4.17 MiB. A restart before then voids the observation and the clock restarts with it.
---

# The 00088 capture bake's RSS residual is unresolved — one discrete step observed

## Context — what

Spec `00088`'s capture re-pin (`zcrypto-red` → `6c5151d9f3af`, 2026-08-11 14:13:17Z) passed its bake gate, but the bake's slope row spans only three rotation hours and a leak slower than that window passes it. The rollout discipline names a residual owed at ~T+24 h: re-read RSS against the daemon's own earlier samples.

That re-read was taken at T+32 h and **did not discharge**. The secondary's warm floor rose **+5.39 MiB over 26 h**, and the rise is not a smooth drift — it is one discrete step of **+4.17 MiB between 2026-08-12 08:00 and 16:00 UTC**, followed by six hours of flat floor. The primary, which was not re-pinned and serves as the control, moved **+0.25 MiB** over the same window, so the cause is not environmental.

## Why this matters

The shape matches [[T0131]], a previously-resolved capture leak whose signature was discrete steps roughly 24 h apart with decaying amplitude. That topic's first write-up declared "no leak, residual closed" on a flat stretch; review refuted it, and the refutation reproduced — **the flat stretch had been the trough between two steps, not a plateau.** The six flat hours currently sitting after this step are exactly that evidence, so they discharge nothing on their own.

What is not in doubt: this does **not** trip Phase 4 rollback. 140.13 MiB against a 1 GiB limit is 13.7% utilisation with 884 MiB of headroom, and even a naive linear extrapolation of +5.39 MiB/26 h leaves roughly 195 days. The question is whether the amplitude decays (T0131's did, converging harmlessly) or repeats, and one step cannot answer it.

## Findings so far

- **Floor trajectory, `zcrypto-red`, restart-free throughout** (`min_over_time(process_resident_memory_bytes[1h] @ <ts>)`, so the rotation sawtooth is excluded): Aug-11 20:00 134.74 → Aug-12 00:00 134.98 → 04:00 135.20 → 08:00 136.03 → 10:00 136.10 → 12:00 136.88 → 14:00 138.61 → **16:00 140.20** → 18:00 140.21 → 20:00 140.03 → 22:00 140.13 MiB.
- Decomposed: +1.29 MiB of slow drift over the first 12 h, then **+4.17 MiB in the 8 h to 16:00**, then **−0.07 MiB over the following 6 h**.
- **Control**, `zcrypto` capture (unchanged image `99faf16514e3`, running since 2026-07-29): 126.61 → 126.86 MiB over the same window, +0.25 MiB. Compared only against itself — the two hosts' memory limits differ (2 GiB primary, 1 GiB secondary), so a cross-host comparison would be meaningless.
- The 116.0 MiB figure recorded at converge is a **cold-start** number taken two minutes after restart and is not a valid comparison point; the daemon read 133.2 MiB an hour later, which is warm-up. The warm baseline used above is the 2026-08-11 18:00–24:00Z floor.
- `RestartCount` 0 on capture and Alloy throughout, so no restart explains the step.

## Suggested next steps

- At T+48 h (2026-08-13 ~14:13Z), re-read the 1 h floor trajectory across the intervening window and look specifically for a **second step**. Three outcomes, each with a different disposition: no second step and a still-flat floor ⇒ the first step was a one-off allocation (a cache or arena reaching steady state) and the residual discharges; a second step of **smaller** amplitude ⇒ the T0131 pattern, converging, discharge with the decay recorded; a second step of **equal or larger** amplitude ⇒ a genuine unbounded leak — size the doubling time and decide rollback versus a fix on the merits, since the headroom is large enough that rollback is not automatic.
- Read the floor, never an instantaneous sample: the rotation sawtooth spans ~4 MiB and would swamp the signal.
- If a restart intervenes for any reason, the observation voids — the counter is process-lifetime and the clock restarts with it. Record that rather than comparing across the restart.
- Whatever the outcome, record it on the `capture | zcrypto-red` row of `docs/reference/fleet-pins.md`, which currently carries this as open.
