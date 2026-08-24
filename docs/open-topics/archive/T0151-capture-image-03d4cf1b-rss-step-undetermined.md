---
status: resolved
---

# The 03d4cf1b capture image took one RSS step, and one step cannot tell a converging allocation from a leak

## Context — what

The 2026-08-23 bake of capture image `03d4cf1b8df7` produced a **step** in the capture daemon's resident set on the secondary, and **no control existed to test it against** — which is the whole of why it is undetermined. Steps here are not novel: the immediately preceding image `636012cc00d9` stepped **+11.04 MiB** at its 2026-08-19 bake and was discharged precisely because the primary control stepped **+10.07 MiB** in the same window *while running the old image*, making it environmental. Two images back, `419feafc304f` showed no step at all. So a step on red is a question, not a verdict — and the answer has always come from the control. Measured on `zcrypto-red` (T0 = 2026-08-22 22:00:39Z), floors via `min_over_time(process_resident_memory_bytes{job="capture_app"}[1h])` at named hours:

| T+ (h) | floor (MiB) |
| -- | -- |
| 2.7 | 132.58 |
| 4.7 | 135.83 |
| 6.7 | 137.23 |
| 8.7 | 138.68 |
| 10.7 | 139.00 |
| 12.7 | 139.13 |
| 14.7 | 139.19 |
| 16.7 | 139.48 |
| 18.7 | 142.14 |
| 20.7 | 142.19 |
| 22.7 | 142.17 |

Warm-up completes by ~T+10.7 and the floor is flat for six hours (139.00 → 139.48). Then a **+3.05 MiB step over a ~2 h ramp**, resolved at 30 min: 139.21 (T+15.8) → 140.93 (T+16.8) → 142.26 (T+17.8), flat afterwards for ~5 h.

## Why this matters

The rollout skill's own discriminator: two steps of decaying amplitude, each with a flat trough, is a **converging allocation**; equal-or-growing steps are a **real leak**. One step and a quiet stretch cannot tell them apart. This bake produced exactly one step and a quiet stretch, so the verdict is **undetermined** — not passed, and not failed.

The gate was closed anyway, on the owner's explicit call, because another engine rollout was expected shortly and its bake re-observes the same question on a fresh band. That is a **knowingly degraded gate**, recorded here so the next reader does not mistake it for a clean discharge.

## Findings so far

- **The primary cannot serve as the control for this step.** It converged 11.4 h after the secondary (2026-08-23 09:25:29Z), so at the secondary's step it was still warming: 155.75 MiB (its T+4.4) → 160.23 (T+6.4) across the same wall-clock window. A rise there is indistinguishable from warm-up, so the wall-clock coincidence neither implicates nor exculpates the environment.
- **The primary was never read in its own band during this bake.** At gate-close (2026-08-23 20:44Z) it stood at T+11.3 h, flat at ~160.2 MiB since T+7.4 h — a clean warm-up plateau, and no more than that. Its own T+17-25 h band opened after the gate closed.
- **Nothing else in the bake was adverse.** `restarts=0` on both hosts (so the process-lifetime counter is valid and both T0s stand), `zcrypto_logship_dropped_lines_total` 0, `prometheus_remote_storage_samples_failed_total` 0 read **on-host** at `127.0.0.1:12345` (it is absent from Cloud, where `(no series)` would have read as a false pass), `up{job="capture_app"}` 1 on both, both capture dead-men 1, no `quarantined`/`ambiguous`/`merge failed` in 2 h of logs on either host against non-empty log volume, and 21/20 parquet files written in the preceding 3 minutes.
- **Headroom is not the concern.** The secondary sits at ~142 MiB against a 1 GiB container limit, the primary at ~160 MiB against 2 GiB. Even a genuine leak of this amplitude has a long runway; the reason to resolve this is diagnostic honesty about the image, not an imminent OOM.

## Resolution

**Resolved 2026-08-24: the step is ENVIRONMENTAL, and the control this bake lacked was recovered from the primary's own band.** Neither host had restarted (`restarts=0`, and both recorded T0s match `.State.StartedAt` exactly), so the process-lifetime counters were valid and both windows were still readable.

Floors via `min_over_time(process_resident_memory_bytes{job="capture_app"}[1h])`, read at common WALL-CLOCK times so the two hosts are directly comparable:

| wall clock (UTC) | red T+ | red MiB | zcrypto T+ | zcrypto MiB |
| -- | -- | -- | -- | -- |
| 08-23 20:00 | 22 | 142.12 | 10.6 | 160.05 |
| 08-23 22:00 | 24 | 142.23 | 12.6 | 160.31 |
| 08-24 00:00 | 26 | 144.33 | 14.6 | 162.86 |
| 08-24 02:00 | 28 | 144.83 | 16.6 | 163.63 |
| 08-24 04:00 | 30 | 145.95 | 18.6 | 163.93 |
| 08-24 06:00 | 32 | 145.88 | 20.6 | 163.99 |
| 08-24 10:00 | 36 | 145.97 | 24.6 | 164.07 |
| 08-24 12:00 | 38 | 146.01 | 26.6 | 164.23 |

**Both hosts stepped in the SAME wall-clock window — 08-23 22:00Z → 08-24 04:00Z — at process ages differing by 11.4 h**: red at its T+24→30 (+3.72 MiB), the primary at its T+12.6→18.6 (+3.62 MiB). The amplitudes agree within 0.1 MiB, and each is followed by a flat plateau of 8+ hours.

The synchronisation excludes both AGE-driven hypotheses — a leak and a converging allocation, the two that trip a rollback decision — because neither can make two processes 11.4 h apart in age step simultaneously in wall clock. What it cannot by itself exclude is the build responding to a shared WALL-CLOCK event: both hosts ran the same image at read time, the step window spans UTC midnight, and the daemon rolls day partitions there — so "not the build" rests on the `636012cc` precedent, where an OLD-image control stepped +10.07 MiB in sync with the new image's +11.04, showing this step class occurs regardless of image. Red's first step (13:48–15:48Z, no midnight in window) further weakens the clock-trigger alternative. Either way the operational verdict is the same: the step plateaus and does not grow, so it is not a leak and trips nothing.

**The undetermined verdict is therefore discharged rather than merely aged out.** The first step (+3.05 MiB at red's T+15.8→17.8) is the same phenomenon: its wall clock is 08-23 13:48→15:48Z, during which the primary rose 155.75 → 160.23 MiB. That rise was recorded here as indistinguishable from warm-up, and it remains so — but it is no longer load-bearing, because the second event supplies a control that is not confounded by warm-up.

**What the amplitude comparison would have said on its own, and why it was wrong.** Taken as two steps on red alone, +3.05 followed by +3.72 is equal-or-growing, which the rollout skill's discriminator escalates to a leak. That reading is available only if the control is ignored. It is recorded here because the next reader will meet the same temptation: the amplitude rule is a fallback for when no control exists, not a substitute for one.

Headroom was never the concern and is not now: red sits at ~146 MiB against 1 GiB, the primary ~164 MiB against 2 GiB.

## What became of the next steps

The first bullet is discharged — both windows were read, and the Resolution above is what they said. The last is discharged as the confirmed hypothesis.

**The middle two were method, not backlog, and they now live where a bake actually reads them** — folded into the `zcrypto-captures-rollout` skill (Phase 2, the bake gate) rather than left here, because a prescription for the NEXT bake dies if its only home is an archived topic. The skill also gained the discriminator this resolution turned on, which it did not carry before.


- **Two windows on the CURRENT image are still reachable and are the cheapest resolution available** — they need no new rollout, only that the host has not restarted: `zcrypto-red`'s second anniversary at **2026-08-24 12:00-16:00Z** (~T+38-42 h), and `zcrypto`'s own first band at **2026-08-24 02:25-10:25Z** (its T+17-25 h). (Both windows are in the past and were taken — the Resolution above is what they yielded.)
- At the next capture-image bake, sample the secondary's RSS floor **through** its T+17-25 h band at 2 h resolution — the same method used here — and record whether a step appears, its amplitude, and whether a second step follows at the next anniversary. Two steps with decaying amplitude closes this as a converging allocation; equal-or-growing steps escalate it to a leak and trip the rollback decision on the affected host.
- Read the primary in **its own** band as well, not only at the secondary's anniversary. This bake never did, because the two converges were 11.4 h apart and the gate closed at the secondary's T+22.7 h — the primary's band had not opened. When the two hosts converge far apart, the secondary-anchored read does not cover the primary.
- The live alternative hypothesis is **environmental**, and it has precedent on this exact host: `636012cc`'s +11.04 MiB step was exculpated by a control stepping +10.07 MiB on the old image. What distinguishes this bake is not that it stepped but that it had no usable control, so nothing separates build from environment. Any future bake whose two hosts converge close enough together to give a real control settles this class of question directly.
