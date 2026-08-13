---
status: resolved

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

## Resolution

Resolved 2026-08-13 by the T+48 h re-read the topic prescribed, taken at 14:11Z with `RestartCount` still 0 — the trigger's restart-free condition held for the full 48 hours.

**Outcome 1 of the three pre-decided: no second step.** Hourly floors across Aug-13 00:00→14:00 read 140.18, 140.18, 140.20, 140.11, 140.28, 140.26 MiB — flat for **22 hours** since the +4.17 MiB step ended at Aug-12 16:00 (range 140.03–140.28, net ≈ +0.1 MiB, inside the rotation noise), spanning the full ~24 h-later window where a [[T0131]]-style repeat would have landed, the 03:17 prune included. The control (`zcrypto`, image unchanged) read 126.82 MiB, also flat. The first step was a one-off allocation reaching steady state — a cache or arena filling once — not the first of a T0131-style train, whose signature at this point would have been a second step of comparable amplitude.

The discharge is licensed by the trajectory's SHAPE, not by a flat stretch alone: the T+32 h read refused to discharge on 6 flat hours precisely because T0131's trough between steps looked the same; 22 flat hours through the expected second-step window is the evidence that distinguishes the two. Final state: 140.26 MiB against a 1 GiB limit (13.7 %), 884 MiB headroom. Recorded on the `capture | zcrypto-red` row of `docs/reference/fleet-pins.md` in the same change.

## Suggested next steps

_(none — the T+48 h re-read above was the last open step; every earlier bullet is discharged by it)_
