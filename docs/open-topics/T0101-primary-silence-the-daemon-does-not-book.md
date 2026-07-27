---
status: open
ripe_when: NOW for the measurement half (the ledger records the event and is readable today); the fix half is ripe once the measurement says whether reconnect silence is systematically unbooked or this was one bad patch
---

# The reconciler sees primary silence the capture daemon does not book as a gap

## Context — what

On 2026-07-27 the *Reconciler · primary gap rate high (degrading host)* rule fired (activeAt 09:48:00Z). The primary needed **2,318 s (~39 min)** of healing in the preceding 6 h, against a threshold of 10 min per 24 h.

The reconciler and the capture daemon disagree about what happened, and that disagreement is the topic:

| signal, primary, same 6 h window | value |
| --- | --- |
| `zcrypto_reconcile_healable_gap_seconds_total` | **2,318 s** |
| `zcrypto_capture_gap_seconds_total` (the daemon's own) | **0** |
| `zcrypto_capture_book_desynced` | 0 |
| `zcrypto_capture_reconnects_total` | 5 |

The daemon booked **no gap at all** for a period the reconciler measured as 39 minutes of coverable silence.

## Why this matters

**Not data loss** — and that is verified, not assumed: `zcrypto_reconcile_healed_gap_seconds_total[24h]` equals 2,313 s, so the reconciler minted essentially every second of it from the secondary. The redundant-capture design did exactly its job, silently. This is the *good* outcome.

What it exposes is a **measurement gap**, and the direction is the dangerous one: the daemon under-reports. Everything keyed on `zcrypto_capture_gap_seconds_total` — including the operator's intuition about how healthy the primary is — reads clean through a 39-minute hole. Had the secondary not covered it, the first hint would have been an archive continuity check days later.

It also matters for the redundancy argument itself: the secondary is justified by the primary being imperfect, but if the primary's imperfection is invisible in its own metrics, the fleet cannot tell a good week from a bad one.

## Findings so far

- **Shape: one event, not a trend.** `increase(...healable_gap_seconds_total[Xh])` measures **0 s at 1 h, 2,318 s at 6 h, 2,313 s at 24 h, 2,312 s at 7 d** — so essentially all healable gap in seven days fell inside one window in the last six hours, and it has stopped. The rule fired on a real one-off, correctly.
- **Arithmetic that suggests a cause, not a conclusion:** 2,318 s over 12 pairs ≈ 193 s per pair, across 5 reconnects ≈ ~39 s per pair per reconnect. That is the right order for a reconnect → resubscribe → fresh-snapshot cycle, which would mean **reconnect silence is simply not booked as a gap** — the daemon opens a gap on desync (`start_gap(pair, "checksum_resync")`) but a reconnect takes a different path. Unverified: the per-pair split has not been read out of the ledger.
- Not caused by that morning's drills — the alert predates them by 41 min, and both ran on the ops node and the secondary, never the primary.
- Not caused by the Alloy bump (01:33–01:58 UTC): that is ~8 h before, outside the 6 h window, and the 7 d total shows nothing before this event.

## [[T0008]]'s ladder makes this blind spot reachable more often (2026-07-27)

Registered the same day, and it cuts against this topic staying parked.

T0008's recovery ladder adds a **full reconnect** as its last rung (spec `00072`, rung 3). This topic's leading hypothesis is that **reconnect silence is precisely what the daemon does not book** — the arithmetic that fits the 2026-07-27 event is ~39 s per pair per reconnect, across 12 pairs.

If both hold, then once the ladder deploys, every escalation manufactures exactly the silence that `zcrypto_capture_gap_seconds_total` cannot see. The ladder is bounded — one escalation per pair per hour, a bound that review had to repair before it actually held — so this is not a runaway; but it converts an accidental blind spot into one the system will now walk into deliberately, by design, as part of a recovery path.

That does not merge the two topics: this is a different defect in a different producer, and its first step is still a measurement. It does mean the measurement is worth doing **before** T0008's image reaches the fleet, so the ladder is not deployed on top of an accounting gap nobody has characterised.

## Suggested next steps

- **(autonomous, measurement first) Read the reconcile ledger for the event** — `would_mint`/`minted` records over the window — and establish the per-pair, per-hour shape and the exact wall-clock span. That answers whether this is reconnect silence (expected-but-unbooked) or something else, and it is the input every other decision needs.
- **(autonomous, once measured) Decide whether the daemon should book reconnect silence.** If reconnect gaps are genuinely unbooked, either book them (so `gap_seconds_total` means what operators think it means) or document explicitly that it counts desync gaps only — the current state, where the name implies coverage it does not have, is the defect regardless of which way it is resolved.
- **(depends on the above) Re-derive the alert threshold.** 10 min/24 h was set against an assumed baseline; if reconnect silence is normal-and-unbooked, the reconciler's view will trip this rule on ordinary weeks and the number needs deriving from measured data rather than intuition — the same mistake [[T0069]] corrected for the journal-pull lag.
