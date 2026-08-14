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

Resolved 2026-08-14. **Outcome 2 of the three this topic pre-decided: a second step of smaller amplitude — the T0131 pattern, converging.** Discharged with the decay recorded.

**The first attempt to close this was wrong, and the correction is the point.** A T+48 h read taken 2026-08-13 14:11Z reported 22 flat hours and was written up as "no second step". Review refused it: step 1's mass sat in Aug-12 12:00→16:00, so the ~24 h anniversary band was Aug-13 ~08:00–16:00 with jitter to ~18:00, and the 14:11Z read sat **inside** it — breaking the rule [[T0131]]'s own file codifies, that a floor read must sit ENTIRELY outside the event band because the band is a ramp. T0131 refused a discharge at 26 flat hours for exactly this reason, and its failure #4 was a discharge overlapping the band by 54 minutes. The read was also clock-driven (T+48 h fell at 14:13Z) rather than band-driven, and was taken two minutes *before* its own trigger.

The band-clearing reads then found what the premature one had missed: the floor had **left the plateau**. Step 2 ran Aug-13 14:00→18:00 for **+1.38 MiB**, landing exactly where the anniversary band predicted.

**Floor trajectory, `min_over_time(...[1h])` at named hours, restart-free throughout (`RestartCount` 0 for 61 h):**

| Sample | MiB | Δ |
| --- | --- | --- |
| Aug-12 16:00 (step 1 ends) | 140.20 | — |
| Aug-12 22:00 | 140.13 | −0.07 |
| Aug-13 14:00 (the premature read) | 140.13 | +0.00 |
| Aug-13 16:00 (band clears) | 141.05 | +0.92 |
| Aug-13 18:00 (step 2 ends) | 141.51 | +0.46 |
| Aug-13 20:00 | 141.46 | −0.05 |
| Aug-14 00:00 | 141.64 | +0.18 |
| Aug-14 03:00 | 141.54 | −0.10 |

**Two steps, each followed by a flat trough: +4.17 MiB then +1.38 MiB — a measured decay ratio of 0.33, steeper than T0131's 0.49.** Step 1 was followed by 22 flat hours, step 2 by 9 and counting (141.46–141.64, range 0.18 MiB, inside the ±0.1 MiB noise). Geometric continuation at 0.33 sums to roughly **+0.7 MiB** of remaining growth — the series converges rather than running away. Final state **141.5 MiB against a 1 GiB limit (13.8%)**, ~882 MiB headroom.

The control (`zcrypto`, image unchanged) read 126.77 MiB at the close, against 126.61–126.86 across the observation — flat throughout, so the steps are the re-pinned image's own behaviour and not environmental.

**No Phase 4 rollback.** Converging allocation at 13.8% of limit is not a trip, and a rollback would restart live capture on the unbackfillable path to buy nothing.

**The rule that made this correctable now has an operating home**: `zcrypto-captures-rollout`'s Phase 2 residual carries the band-clearing requirement, so the next RSS re-read is scheduled against the event band rather than a clock. A ruling recorded only in an archived topic is invisible at execution time — this session broke the same rule twice in one day to prove it.

## Suggested next steps

_(none — the band-clearing re-reads above were the last open step; every earlier bullet is discharged by them)_
