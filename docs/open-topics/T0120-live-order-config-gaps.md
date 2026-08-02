---
status: open
---

# Engine config gaps that only bite when orders flow

## Context — what

Three Nautilus node settings are correct for shadow and wrong for live orders, verified in the capability map 2026-07-30: `default_leverage` is unset; `spot_positions_quote_currency` defaults to `"USDT"` on a EUR-quoted book; and the venue open-order / position-discrepancy polling is OFF (`open_check_interval_secs` / `position_check_interval_secs` both `None`). None of the three can misbehave while the node only logs intents — all three can the day it submits.

## Why this matters

The go/no-go gate's "zero unreconciled order/position states" almost certainly needs the discrepancy polling ON to mean anything — with it off, an unreconciled state is not detected, which reads as zero. The USDT default mis-denominates spot position accounting on a EUR book, and an unset `default_leverage` leaves margin-order semantics to a library default nobody chose. Cheap to fix now; expensive to discover as a rung-1 surprise.

## Findings so far

- All three read from the node build path (2026-07-30 capability audit); none is overridden in `zcrypto.toml` or the engine role's rendered config.
- The right values need one decision each, not research: leverage per the margin plan (§12 kickoff D3), quote currency EUR, polling intervals on with values that respect Kraken's rate budget (the REST pacing floor measured in T0053 is the reference for what the budget tolerates).

## Suggested next steps

- **(autonomous — the values come from existing rulings: leverage per the §12 kickoff margin plan, EUR, polling ON; flag for a decision only if the margin plan turns out to leave leverage genuinely open)** Set all three explicitly in the engine config with a comment naming why each exists; a test pins that a built node carries them (so a library-default change upstream cannot silently revert the semantics).
- **(autonomous)** Verify the discrepancy polling's rate cost against the public/private API budget before picking intervals.
- **(autonomous)** Rides [[T0018]]'s executor iteration (the settings are meaningless before submission exists) but is registered separately so it cannot be lost inside the build.
