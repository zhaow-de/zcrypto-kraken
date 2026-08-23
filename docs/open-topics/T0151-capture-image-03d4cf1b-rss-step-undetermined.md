---
status: open
ripe_when: "a capture host reaches an unread T+17-25 h band or ~T+40 h second-anniversary window on whatever capture image it is then running"
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

## Suggested next steps

- **Two windows on the CURRENT image are still reachable and are the cheapest resolution available** — they need no new rollout, only that the host has not restarted: `zcrypto-red`'s second anniversary at **2026-08-24 12:00-16:00Z** (~T+38-42 h), and `zcrypto`'s own first band at **2026-08-24 02:25-10:25Z** (its T+17-25 h). A second step on red of equal-or-greater amplitude escalates to a leak; a decaying second step closes it as a converging allocation; and the primary's own band gives the control this bake never had. Take these before waiting on any rollout.
- At the next capture-image bake, sample the secondary's RSS floor **through** its T+17-25 h band at 2 h resolution — the same method used here — and record whether a step appears, its amplitude, and whether a second step follows at the next anniversary. Two steps with decaying amplitude closes this as a converging allocation; equal-or-growing steps escalate it to a leak and trip the rollback decision on the affected host.
- Read the primary in **its own** band as well, not only at the secondary's anniversary. This bake never did, because the two converges were 11.4 h apart and the gate closed at the secondary's T+22.7 h — the primary's band had not opened. When the two hosts converge far apart, the secondary-anchored read does not cover the primary.
- The live alternative hypothesis is **environmental**, and it has precedent on this exact host: `636012cc`'s +11.04 MiB step was exculpated by a control stepping +10.07 MiB on the old image. What distinguishes this bake is not that it stepped but that it had no usable control, so nothing separates build from environment. Any future bake whose two hosts converge close enough together to give a real control settles this class of question directly.
