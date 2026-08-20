---
status: open
ripe_when: a fifth `both_streams_silent` record is booked whose earliest per-stream window opens inside 07:00–07:05 UTC — read straight off `capture-reconciled/reconcile-ledger.jsonl` (`stream_windows`, not `windows`, since the canonical intersection is narrower than the fleet's true start). Measured state, verifiably satisfiable, and it needs no new instrumentation.
---

# Fleet-dark venue episodes keep starting within seconds of 07:01 UTC

## Context — what

Every measurable fleet-dark episode in the live ledger opens at almost exactly the same wall-clock time. Measured from `stream_windows` (the fleet's true earliest start, which the narrower canonical intersection understates):

| Date | Fleet-earliest window start | Booked |
| --- | --- | --- |
| 2026-07-27 | `07:01:04.071744` | 2,385.847992 s |
| 2026-08-06 | `07:01:01.107346` | 10,588.382751 s |
| 2026-08-20 | `07:01:04.336045` | 6,251.349974 s |

Three independent days, spread **3.229 s**. The fourth record, 2026-07-13, is head-truncated by the [[T0036]] restart clobber, so its start reads as the hour boundary `07:00:00.000000` and is unmeasurable — not a counter-example, just silent.

## Why this matters

[[T0105]] dropped the pre-drain because Kraken's `effectiveTime` gave **zero** lead time — every announced transition carried `None`. A clock-time regularity is therefore the *only* candidate source of advance warning that exists, and it costs nothing to exploit if it is real.

The cheap, concrete payoff is scheduling hygiene, available immediately and independent of whether the signature is causal: **do not place a capture re-pin, an engine converge, or a panel regeneration inside 07:00–07:20 UTC.** A converge landing inside a venue-dark window conflates two failure sources in exactly the window where the ledger is least readable — and the fleet already restarts hosts on a schedule we choose.

Note this now spans **two distinct mechanisms**, which is what makes it more than a coincidence worth ignoring: 2026-07-13 and 2026-07-27 were WS service restarts (unannounced, [[T0101]]), while 2026-08-06 and 2026-08-20 were announced `maintenance` ladders. A shared clock time across two different causes points at something scheduled upstream.

## Findings so far

- [[T0101]] recorded this signature at **n=2 and archived it**, explicitly as "a signature worth acting on, not an established schedule", with 2026-07-20 hour 07 clean as a negative control. Nothing has revisited it since; it is now n=3 measurable.
- The two 2026 August episodes are the two announced ones, and both booked at the **09:12Z** reconcile tick — a consequence of the H+2 h settle rule, not of the venue.
- No alert keys on time-of-day, and nothing in the repo schedules around 07:00 UTC today.

## Suggested next steps

- **Autonomous, and NOT gated on the trigger above** (human-gating is per sub-item): sweep every hour-07 book segment across the capture era for max-gap outliers, using the ~40 clean days as negative controls, and record whether the three starts survive as a signature or dissolve into noise. This is a read over `/mnt/zhao-crypto/capture-segments/`, needs no host access, and either outcome is worth writing down.
- **If it survives:** add the 07:00–07:20 UTC exclusion to the converge-scheduling guidance in `.claude/rules/capture-deploys.md`, beside the existing "measured book-traffic trough" constraint — one clause, no machinery.
- **Do not build an alert on it.** A time-of-day rule would fire on the schedule rather than on the event, which is the opposite of what the fleet's rules are for. The value here is scheduling, not detection.
