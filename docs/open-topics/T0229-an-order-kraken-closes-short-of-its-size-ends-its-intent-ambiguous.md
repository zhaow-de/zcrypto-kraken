---
status: open
ripe_when: 'a milestone: rung 3''s first attended week closes; check: `git log --oneline origin/develop --merges --grep=records/rung3-week-1` prints a line'
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

## Suggested next steps

- At a cancel refused `EOrder:Unknown order`, read Kraken's own record of the order, as the startup pass does, and settle the row and the intent from it: an order closed with a fill ends `filled` at that quantity and the plan goes on; any other answer, or a failed read, stays `ambiguous`.
- Prove it with a case whose order the venue closes short with no terminal event, and a case whose venue read fails.
- Hand the missing terminal event to the `nautilus` peer as an adapter defect, with the order's record.
- Ship it on the image that carries [[T0226]]'s and [[T0227]]'s fixes, so one engine converge takes the three.
