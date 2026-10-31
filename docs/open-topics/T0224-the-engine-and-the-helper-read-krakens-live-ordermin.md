---
status: open
ripe_when: 'a milestone: rung 2''s exit report recorded, a read of rung 3''s entry gate (`engine-rung-3` step 1, item 1, in `infra/runbooks/engine-procedures.md`); check: `docs/research/14.phase6-decisions.md` carries the exit report entry, due by Fri 2026-11-06'
---

# The engine and the helper read Kraken's live ordermin

## Context — what

The engine and the plan helper hold an intent's quantity against an `ordermin` that does not follow the venue: the Cache instrument's `min_quantity` (`cli/engine/venuestate.py`), loaded when the adapter connects. Rung 3's drafting loop reads it there (`cli/engine/executor.py::_draft_table`), and `zcrypto engine draft-plan` (`cli/engine/draftplan.py::venue_view`) and `zcrypto engine probe-plan --check` read it from each boundary's venue record. Kraken moves its minimums without notice.

## Why this matters

The 2026-10-30 ETH/EUR sell of 0.00109968 cleared the engine's 0.001 floor and was refused by Kraken's 0.002 as `volume minimum not met`; it ended `ambiguous` and halted its plan. The 2026-10-31 exit held every intent against Kraken's public `AssetPairs` by hand before each drop. From rung 3's first armed boundary the loop drafts and places unattended, so nobody holds the intent against the venue: a raised minimum halts the plan, and a lowered one leaves as dust a remainder Kraken would take.

## Findings so far

- Reference-data sweep #4 (2026-10-31, the log in `docs/reference/kraken-snapshot-register.md`) found `ordermin` moved on eight of the twelve legs since #3 (2026-10-01), four raised and four lowered; `costmin` did not move.
- On 2026-10-31 `zcrypto engine probe-plan --check` printed ETH 0.001, LTC 0.1 and XRP 1.65, the floors before the move.
- Each boundary's `read_venue_book` (`cli/engine/executor.py`) already fetches Kraken's full instrument listing, `request_instruments()`, on its own client, and uses it only to resolve the margin positions' rows; the draft that follows reads the Cache's `min_quantity`.
- `costmin` is a committed constant (`cli/engine/instruments.py::COSTMIN`) under `tests/test_costmin_drift.py`, which fires only in a sweep, since it skips without `data/snapshots/`; `ordermin` has no such guard.

## Suggested next steps

- Choose the source, the design choice this topic leaves open: the engine and the helper read the live `ordermin` — Kraken's public `AssetPairs`, or the listing the boundary's venue read already fetches — or a committed per-leg `ordermin` beside `COSTMIN`, refreshed from each sweep under a drift guard like `tests/test_costmin_drift.py`.
- Prove it on the 2026-10-30 case: an ETH/EUR sell of 0.00109968 against a 0.002 floor is carried or refused before submission, never sent.
- Land it before rung 3's arm pull request (`engine-rung-3` step 1, item 2, in `infra/runbooks/engine-procedures.md`).
