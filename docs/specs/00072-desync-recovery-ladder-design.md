# Desync recovery: a bounded retry ladder that escalates to reconnect (spec 00072, T0008)

**Goal.** Make recovery from a book checksum desync survive its first attempt failing, without reintroducing the resubscribe storm the current single-shot design exists to prevent.

**Scope.** `cli/capture/command.py`'s desync branch and a small amount of per-pair retry state. No change to `OrderBook`, the writers, the gap monitor's contract, or the WS framing. Options (a) bounded retry and (c) escalate-to-reconnect, built as **one ladder**; option (b) `req_id` correlation is deliberately excluded — see D6.

## The defect

Recovery is a **single fire-and-forget resubscribe**, fired only on the `not was_desynced` **transition** (`command.py:148`). That guard is correct and load-bearing: without it a desync re-fires on every subsequent out-of-sync update — hundreds/sec at depth-100 — tripping Kraken's subscribe rate limit so the pair can *never* resync, a self-inflicted cascade.

But the guard has a cost: if the one attempt does not take, `desynced` stays `True`, the transition never re-fires, and the pair is **stuck indefinitely**. Two ways it fails to take:

1. the forced snapshot itself fails its checksum, or
2. the `subscribe` races ahead of the `unsubscribe` server-side and is rejected.

Shadow-mode today; unbackfillable L2 loss for that pair either way, growing without bound.

## D1 — One ladder, three rungs, each clearing strictly more state

| rung | action | clears |
| --- | --- | --- |
| 1 (exists) | resubscribe on the desync transition | that pair's subscription |
| 2 (new) | bounded retries with backoff, while still desynced | the same, repeatedly |
| 3 (new) | full reconnect | the whole connection, all subscriptions, every book |

Escalation is meaningful precisely because each rung clears more: if a per-pair resubscribe keeps failing, a fresh connection is the only remaining state to discard, and it rebuilds every book from a fresh snapshot — which addresses **both** failure causes above.

## D2 — Retries are driven by desync STATE, not by protocol responses

The retry timer keys on "this pair is still desynced N seconds after its last attempt", never on an ack or error frame.

That is the load-bearing choice, and it is what makes cause 1 recoverable: **a snapshot that fails its own checksum produces no error frame at all** — Kraken is satisfied, the protocol succeeded, and the book is still wrong. Only continued desync reveals it. A design driven by protocol responses is structurally blind to half the defect.

## D3 — The parameters, and the honest note on where they come from

**They cannot be derived from production, and the spec says so rather than implying a fit.** `zcrypto_capture_resubscribes_total` and `zcrypto_capture_gap_seconds_total` both read **0 on both hosts** — since the 2026-07-13 root-cause fix (which took a replayed hour from 482/117/398 CRC failures to zero), no desync has occurred at all. The 234/234 first-attempt heals predate both the fix and these counters. There is no heal-latency distribution to fit.

So the parameters are set from the two constraints that *are* known, and confirmed by drill (D5):

- **Grace before the first retry: 20 s.** Must exceed a healthy resubscribe's snapshot round-trip by a wide margin, or a retry fires on a recovery already in flight. No production distribution exists; 20 s is generous against any plausible round-trip and the drill measures the real value.
- **Retries: 3, backing off 5 s / 10 s / 20 s.** Bounded by construction. Against the storm this design guards against — hundreds/sec — three attempts across ~35 s is not a rate-limit risk by any margin.
- **Escalate after the 3rd failed retry.**
- **Terminal state: one escalation per pair per hour, then stop retrying** — see D4. **The cooldown must survive recovery**, and review found it did not: clearing the escalation record on heal made the bound apply only to a *continuously* desynced pair, while the likeliest healer is the escalation's own reconnect (it forces a fresh snapshot for every pair). That closed a feedback loop — escalate → reconnect → heal → record erased → escalate again ~55 s later. Simulated against the real ladder: a pair desyncing every 10 min escalated **6×/hour against the intended 1**, a flapping pair **51×/hour** — **72** and **~610** reconnects/hour fleet-wide across 12 pairs, against 12. Ceilings rather than a steady state (the ladder has no clock, so the reconnect's own downtime goes uncharged); the 6:1 over-run ratio is the finding.

**Total ladder ≈ 55 s to escalation, ≈ 90 s including the reconnect's own resubscribe.** That number is the one that matters, because of D4's budget.

## D4 — The dead-man is the real budget, and it bounds the ladder

While **any** pair is desynced, `gap_monitor.is_healthy()` is `False`, and `command.py:244` gates the healthchecks.io ping on it. So the *entire* ladder runs with that host's dead-man dark **for all 12 pairs**, not just the stuck one.

The ping is every 60 s; the hc.io grace itself is configured on healthchecks.io and is not repo-readable, so the ladder is sized conservatively rather than fitted: ~90 s costs at most one or two missed pings, which any plausible grace absorbs. **This is why the ladder is measured in seconds, not minutes** — a "patient" ladder would silently trade one stuck pair for a fleet-wide dead-man outage.

## D5 — The terminal state matters more than the backoff

If a pair is **still** desynced after the full reconnect, the ladder **stops**. It does not cycle.

Cycling would convert one stuck pair into a reconnect loop — every reconnect drops all 12 pairs, so a loop is strictly worse than the defect it is trying to fix, and repeated whole-connection re-subscribes are exactly the shape that trips the rate limit at connection level. At that point the fault is not ours to fix in-process: `Capture · book desync stuck on a pair` (shipped 2026-07-26, drill-validated 2026-07-27) is the escalation path, and the withheld dead-man is the backstop.

**Escalation cost, priced from a real event.** [[T0101]] measured a reconnect at roughly 39 s of silence per pair across 12 pairs (arithmetic from one incident, not a fitted number). So pulling rung 3 costs a bounded, secondary-covered gap on every pair — clearly worth paying against one pair losing data indefinitely, and clearly not worth paying repeatedly.

## D6 — Why `req_id` correlation is excluded

Option (b) — waiting for `unsubscribe_ack` before sending `subscribe`, treating `unsubscribe_error`/`subscribe_error` as retry signals — is **prevention for cause 2 only**, and structurally cannot see cause 1 (D2). It is therefore not a substitute for this ladder.

Its real value is *observability*: an explicit error frame to count and alert on, where today a failed resubscribe is only inferable from continued desync. That is a genuine improvement with a different justification, and it costs `req_id` plumbed through message classification plus per-pair pending-request state — on the unbackfillable capture path. It belongs in its own topic, not folded in here.

## D7 — Verification: the drill is part of the deliverable

TDD with a fake connection covers the ladder's logic. It does **not** prove the production path runs — which is exactly how [[T0035]] stayed open for weeks while landed, deployed and regression-tested, and how this topic's own alert leg needed a drill before anyone could trust it.

So the build is not done until a sandbox drill on the ops node — throwaway container, same pinned digest, real Kraken, isolated data dir — forces post-resubscribe snapshots to fail CRC and walks every rung. Because the fault is in-process, this yields something [[T0035]]'s drill could not: a true **before/after** — current code demonstrably sticking, new code recovering.

The fault knob is test-only and must not be reachable in a normal run; the drill's value depends on the validated binary being the deployed binary, so it ships in the image, gated on an environment variable absent everywhere in the fleet.

## Drill results (2026-07-27) — and two flaws in the instrument, not the ladder

Both drills ran on the ops node against real Kraken, from an image built off this branch.

**Drill A — hold 45 s (heals before escalation):**

```
12:40:34.435  rung 1: checksum desync - resubscribing   (fires ONCE; the transition guard holds)
12:40:57.868  retry 1   (+23.4 s = 20 s grace + tick)
12:41:02.870  retry 2   (+5.002 s  = backoff[0])
12:41:12.874  retry 3   (+10.004 s = backoff[1])
              hold expires, pair heals, no escalation
```

**Drill B — hold 600 s (every retry fails):**

```
12:45:24.292  ERROR ... still desynced after bounded retries -- forcing a full reconnect  (+20.002 s)
12:45:24.342  reconnecting in 1.0s (attempt 1)          force_reconnect reached stream()
```

`retries=3, escalations=1`, and over the following ~4 minutes with the pair still held desynced there were **no further retries and no second escalation** — the terminal state holds, which is the property no unit test can establish in a live process. `restarts=0` throughout both.

**Desync→escalation measured 58.3 s** against this spec's predicted ~55 s, inside D4's ~90 s budget. That is the first real timing this project has had for the recovery path since desyncs went to zero.

**Two drill runs failed before these, both in the knob:**

1. Faking only `_handle_book_message`'s return value left the book reporting healthy, so `was_desynced` read `False` on every forced failure — the transition guard saw a *fresh* desync each time and re-fired rung 1 twice in 0.5 s, which is the resubscribe storm the guard exists to prevent. Meanwhile the recovery loop, which reads live book state, saw nothing wrong and never engaged.
2. Also setting `book.desynced`, but on a book whose data was genuinely valid, meant the next update recomputed a good CRC and healed it in milliseconds — before the 20 s grace could elapse. The daemon stayed healthy and kept writing parquet, which is exactly what made it look like a pass.

Hence the knob's unit is a **duration**: a pair is stuck for a length of time, and neither a snapshot count nor a state flag alone expresses that. Recorded because the lesson generalises — a fault injector that does not move the state the system actually keys on simulates a different fault, and will do so convincingly.

**Not verified by these drills:** manifest integrity across the fault. Neither run crossed an hour boundary, so only `.part` files existed. That property was established the same day by [[T0035]]'s drill, which did cross one.

## Out of scope

- Option (b) `req_id` correlation — D6, its own topic.
- Booking reconnect silence as a gap ([[T0101]]) — a different defect in a different producer, and its measurement half is unstarted.
- Any change to the desync **detection** path; this spec is entirely about what happens after `in_sync` goes false.

## Deployment note

This is capture-daemon code on the unbackfillable path, so it reaches the fleet only through an image build, the ≥24 h secondary canary bake, then the primary re-pin — `capture-deploys.md`'s canary rule applies in full. The build and its drill validation are independent of that tail and land first.
