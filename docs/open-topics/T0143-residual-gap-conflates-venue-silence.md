---
status: open
ripe_when: a second venue-silence window books into `zcrypto_reconcile_residual_gap_seconds_total` (the counter rises while BOTH capture hosts are `up=1` with equal, microsecond-identical event timestamps across the window), or the reconciler gains any venue-status input for another reason
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

## Suggested next steps

- Decide whether the reconciler should take a venue-status or cross-host-agreement input before booking `both_streams_silent`. The cross-host discriminator is already available offline and is strong: identical event timestamps on two independent hosts across a silent window means the silence was upstream. A venue-status read (the same public `SystemStatus` the execution gate already consumes, per spec `00088`) is the other candidate signal.
- If the booking stays as-is by design, give the alert a triage line that names this case, so the operator reading it at 3am has the discriminator in hand rather than having to derive it.
- Decide what, if anything, annotates the historical 6251.35 s already booked — the counter is monotonic, so it cannot be corrected, only explained. `continuity.py`'s 2026-08-20 FAIL needs the same treatment wherever that day's figure is later quoted.
