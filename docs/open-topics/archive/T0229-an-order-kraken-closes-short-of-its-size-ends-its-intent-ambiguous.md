---
status: resolved
---

# An order Kraken closes short of its size ends its intent ambiguous

## Context — what

Kraken can close an order with a remainder too small to trade: the order reads `closed`, reason `Insignificant volume remaining`, its `vol_exec` under its `vol`. No terminal event for it reaches the engine on the pinned adapter, so the engine's order stays open and partly filled until its intent's 15-minute box ends; the box's cancel then meets `EOrder:Unknown order`, the intent ends `ambiguous`, and the plan runs no intent after it.

## Why this matters

Each occurrence costs the boundary its remaining legs, which wait for the next boundary's draft, and leaves the order's row `accepted` until a restart's startup pass settles it. Nothing fills wrongly; the refused cancel's CRITICAL line pages `zcrypto-engine-error-logs`. Until then, on the order's UTC day and the next, the open row turns its symbol's placed leg `carried` in each draft; and a socket cut on either of those days while the engine is disarmed leaves its watchdog freeze standing for as long as it stays disarmed (`_stranded_rows`), naming the order for a hand cancel Kraken no longer needs.

## Findings so far

- 2026-11-11 00Z, plan `r3-20261111-00`: DOT's sell `O-20261111-000249-001-000-4`, Kraken's `ONMKDH-ERZI3-DMWCV4`, `vol` 5.18909578 and `vol_exec` 5.18909575, closed about 11 s after it opened; the cancel at 00:17:49Z was refused `EOrder:Unknown order`, and DOGE's sell after it ran at 04Z (`docs/reference/rung3/days.md`'s entry for drill G, 2026-11-11, which reaches `develop` with the week's records).
- The row moved from `accepted` to `filled` at drill G's restart: the startup pass read Kraken's report and logged `restored order … is filled at the venue -- its stale open copy stays in the Cache and no cancel is sent`, spec 00120 D7's handling.
- Drill F2's ambiguous DOT order was a whole fill under the drill's own disconnect, a different cause.
- Registered on the owner's word of 2026-11-11, "register the topic as recommended", ripe beside [[T0226]] and [[T0227]].

## Resolution

Delivered by the pull request from `feat/t0229-closed-short-settles-inline` (spec 00160, plan 00160), on the owner's ruling of 2026-11-16, verbatim "Inline, and the plan resumes": at a cancel the venue refuses, the engine reads Kraken's record of the order at once. An order Kraken reports closed with exactly the fill the engine recorded ends its intent `filled` and its row `filled`, with a `venue_closed` event, and the plan runs its next intent; every other answer, or a read not made or failed, stays `ambiguous` with the remainder dropped, its CRITICAL line naming the answer.

- The 2026-11-11 DOT case, closed 3e-08 short, is `test_a_refused_cancel_kraken_reports_closed_with_the_recorded_fill_ends_filled_and_the_plan_goes_on`; the adapter reading such an order as filled at its executed volume, `test_read_venue_orders_reads_an_order_kraken_closed_short_as_filled_at_its_executed_volume`; a read that fails, `test_a_refused_cancel_whose_read_raises_stays_ambiguous`; all in `tests/test_engine_executor.py`.
- The settled row no longer carries its symbol's leg in the drafts or holds the watchdog's freeze.
- Dropped, the Cache's stale open copy of the order, which stays as the startup pass leaves it: nothing in this process can close it, and it moves no figure — the Cache's position and the draft's `engine_held` read the same with it open (spec 00160 D7).
- Handed over, the missing terminal event: an adapter defect outside this repository, which the coordinator sent the `nautilus` peer on 2026-11-16, with the order's record, as spec 00160 D8 says; this change stands whether or not upstream fixes it.
- Dropped, a measurement of Kraken's own latency for the read: its 30 s bound fails closed, and the first real settle's WARNING line carries the read's seconds (spec 00160 D2).
- It ships on the engine image that carries [[T0226]]'s and [[T0227]]'s fixes, one converge, the fleet's concern (spec 00160 D10).
