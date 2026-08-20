---
status: resolved
---

# The residual-gap counter cannot tell venue silence from capture loss

## Context — what

`zcrypto_reconcile_residual_gap_seconds_total` books permanent, unrecoverable loss when no book data exists for a window on either capture host. It has no way to distinguish *we failed to record what the venue sent* from *the venue sent nothing* — and on 2026-08-20 it booked the second case as the first.

## Why this matters

The counter drives `Reconciler · residual gap increased (permanent loss)`, the highest-severity rule in the system, and it is monotonic: whatever it books is permanent in the ledger. A venue outage therefore leaves an indelible "permanent loss" record and pages at the top severity, which trains the operator to discount the one alert that must never be discounted. It also corrupts the denominator of every later data-quality claim: `continuity.py` over 2026-08-20 reports a 1.88 % gap and FAILS its <0.1 % exit bar entirely on this window, so a future reader comparing day-over-day continuity sees a capture regression that did not happen.

## Findings so far

- **The event, measured 2026-08-20**: Kraken's book feed emitted essentially nothing between **07:01:04Z and 07:10:14Z** across all twelve streams. Per-stream gaps 517–550 s; one lone book update mid-window received by both hosts.
- **It was the venue, not the fleet** — the discriminator is that the PRIMARY and the SECONDARY, independent hosts on separate networks and processes, recorded the *same* sparse events with **microsecond-identical timestamps** (`07:01:04.553253` → `07:08:01.113758` on BTC/EUR on both). A capture-side failure cannot produce that agreement. Both hosts read `up{job="capture_app"} = 1` throughout and both dead-men stayed green; Kraken's status page reported no incident (brief degradations often go unposted).
- **What the ledger did with it**: at the 09:12Z reconcile tick, `residual_gap` moved 15636.019483 → 21887.369457 (**+6251.35 s**, 520.9 s per stream) while `healable_gap` did not move at all — i.e. it booked cleanly as `both_streams_silent`, which is exactly right by the counter's definition and exactly wrong as a description of what happened.
- **This is orthogonal to the `00090` deploy** happening the same morning: the primary re-pin's own restart hour (05) booked **zero** — both counters were byte-identical across the run that first covered it.

## Resolution

**Solved by spec `00096` (iter-141).** The reconciler now decides, per fleet-dark episode, whether the evidence weighs toward the venue going quiet or toward our own capture failing, records that verdict on the `both_streams_silent` ledger record, and exports it as `zcrypto_reconcile_dark_episode_seconds_total{verdict=...}`. The alert that pages on this counter gained a triage line and — for the first time — a runbook section.

Each of this topic's three next-steps is discharged:

- **The input was decided: cross-host agreement, not venue status.** `ts` is Kraken's own payload timestamp (`cli/capture/command.py`), never local receipt time, so two independent hosts that receive the same message record byte-identical values by construction and a host that was not receiving cannot manufacture one. Measured against both known venue events, the two candidate signals turn out to be **complementary rather than redundant** — the status page caught 2026-08-06 and missed 2026-08-20; cross-host catches 08-20 and reads 08-06 `undetermined`. The uncovered half is registered as [[T0144]], because Kraken's public endpoint reports current state only and nothing writes status into the archive.
- **The booking stays as-is, by design, and that is now a ruling rather than an accident.** `residual_gap_seconds_total` books the ABSENCE of data, never fault attribution: the verdict is a parallel view and never a subtraction. Verified by construction — with the classifier stubbed to return absurd values, the booked seconds are byte-identical, and identical again to the pre-change tree.
- **The alert got its triage line, and the historical bookings are annotated** in `capture-era-data-hygiene-map.md`, where both venue events now carry their verdict and their booked seconds.

**Replayed against the whole live ledger before merge**: all four `both_streams_silent` records total 21,887.369457 s — 100 % of `residual_gap` — and the recomputed **windows** match the ledgered windows on every hour. Three of the four reproduce their booked seconds exactly under the current code; **2026-07-27 does not, and should not** — it predates the `stream_windows` split, so it booked the intersection × 12 streams (198.820666 × 12 = 2,385.847992 s) where today's per-stream containing-window logic would book 2,430.326091 s. Nothing rides on the difference: `_decided` prevents re-deciding an already-ledgered record, so the historical booking stands as its own era wrote it. On the point that matters, 2026-08-20 reads `venue_silent` (12/12 pairs agreeing, 90 interior updates), and 2026-07-13 — a genuine capture defect (WS 503 plus restart clobber) — reads `undetermined`, refusing to excuse the one historical event that really was ours.

**What this does not do**, recorded so it is not mistaken for a gap: the counter itself still cannot distinguish the two, and was never going to — the distinction lives beside it, in the verdict. An episode with no interior evidence, or more than two dark windows, reads `undetermined` and pages exactly as before. Bounded limitations are written into the spec's own bounded-claims section.
