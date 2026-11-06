---
status: resolved
---

# The engine and the helper read Kraken's live ordermin

## Context — what

The engine and the plan helper hold an intent's quantity against an `ordermin` that does not follow the venue: the Cache instrument's `min_quantity` (`cli/engine/venuestate.py`), loaded when the adapter connects. Rung 3's drafting loop reads it there (`cli/engine/executor.py::_draft_table`), and `zcrypto engine draft-plan` (`cli/engine/draftplan.py::venue_view`) and `zcrypto engine probe-plan --check` read it from each boundary's venue record. Kraken moves its minimums without notice. The dust check, `cli/engine/executor.py::_is_flat_dust`, reads the Cache instrument's `min_quantity` directly.

## Why this matters

The 2026-10-30 ETH/EUR sell of 0.00109968 cleared the engine's 0.001 floor and was refused by Kraken's 0.002 as `volume minimum not met`; it ended `ambiguous` and halted its plan. The 2026-10-31 exit held every intent against Kraken's public `AssetPairs` by hand before each drop. From rung 3's first armed boundary the loop drafts and places unattended, so nobody holds the intent against the venue: a raised minimum halts the plan, and a lowered one leaves as dust a remainder Kraken would take.

## Findings so far

- Reference-data sweep #4 (2026-10-31, the log in `docs/reference/kraken-snapshot-register.md`) found `ordermin` moved on eight of the twelve legs since #3 (2026-10-01), four raised and four lowered; `costmin` did not move.
- On 2026-10-31 `zcrypto engine probe-plan --check` printed ETH 0.001, LTC 0.1 and XRP 1.65, the floors before the move.
- Each boundary's `read_venue_book` (`cli/engine/executor.py`) already fetches Kraken's full instrument listing, `request_instruments()`, on its own client, and uses it only to resolve the margin positions' rows; the draft that follows reads the Cache's `min_quantity`.
- `costmin` is a committed constant (`cli/engine/instruments.py::COSTMIN`) under `tests/test_costmin_drift.py`, which fires only in a sweep, since it skips without `data/snapshots/`; `ordermin` has no such guard.

## Resolution

Delivered by the pull request from `feat/00156-boundary-ordermin` (spec 00156, plan 00156): the source is the listing the boundary's venue read already fetches, and the engine and both helpers hold a quantity against the higher of that listing's floor and the Cache's.

- A raised floor holds from the next book read and a lowered one from the next start. The lowered half, the second harm above, is bounded by the owner's ruling and is not open (spec D2).
- `engine-rung-3`'s entry gate reads the pin row's revision and the venue record's floors (`infra/runbooks/engine-procedures.md`, step 1).
- The 2026-10-30 case is proved by `test_the_boundary_carries_the_ten_thirty_sell_under_the_listings_raised_floor` and `test_a_plan_holding_the_ten_thirty_sell_is_refused_under_the_listings_raised_floor`, in `tests/test_engine_executor.py`.
