---
status: open
ripe_when: "the first v2 engine converge has happened — `OrderFillVoided` and `OrderStatus.VOIDED` do not exist on the wheel the engine runs today, so nothing can produce this event until then"
---

# A voided fill has no reversal semantics anywhere on the live order-event path

## Context — what

The installed nautilus carries an order event this engine has no handling for: `OrderFillVoided`, the venue undoing a fill it previously reported (a busted trade, a correction). Applying it to an order that was `FILLED` moves it to `OrderStatus.VOIDED` — measured by driving a real `LimitOrder` through the library's own events in `tests/test_engine_executor.py`.

Three surfaces meet it, and each does something different:

- **The startup reconciliation** now handles it. `_ADOPTED_TERMINAL_STATES` gained `OrderStatus.VOIDED -> "venue_canceled"`, so an adopted order the venue voided while this process was down closes its row instead of resting in the re-attach set forever.
- **The live external path** (`_on_external_event`) journals the event into the row's `events` list and leaves the row's `state` untouched: `_EXTERNAL_TERMINAL_STATES` is keyed on event class name and has no `OrderFillVoided` entry, so a matched adopted order whose fill the venue voids keeps a state that says it may still be live.
- **The live own-order path** (`_on_order_event`) dispatches on event class name through a chain that `OrderFillVoided` matches nowhere, so it falls through to the same outcome.

Neither live path is a missing map entry. The quantity is the hard part: `row["filled_qty"]` and the in-process mirror the overfill trip reads were both moved by the fill that is now being undone, and there is no reversal anywhere in `execledger` — `update_submitted_row` takes `add_filled_qty`, and no path has ever passed it a negative. The published counters (`_inc_order`, the fills and fee metrics) cannot be un-published at all.

## Why this matters

This is the live trade path, and the failure is quiet in both directions.

Leave the quantity as it stands and the engine believes it holds inventory the venue says it never got: the ladder sizes its next order against a position that does not exist, and the reconciliation-on-restart sweep sees the venue reporting *less* filled than the ledger — which is the dangerous direction and latches the kill switch, correctly but for a reason nobody will be able to read from the row.

Subtract it naively and the overfill trip's base moves under it: the trip compares a running total against the ordered quantity, so a reversal that is not mirrored everywhere the fill was mirrored either disarms the trip or fires it on a healthy order.

Do nothing at all — today's behaviour — and the row stays open with a `filled_qty` that overstates reality, which is exactly the shape `no fill without a record` exists to prevent, inverted.

## Findings so far

- `OrderFillVoided` is reachable and real on the pinned wheel: applying it after a full fill lands `OrderStatus.VOIDED`, and the library reports that status `is_closed`. The terminal-map totality proof is what found it — `_ADOPTED_TERMINAL_STATES` was total over v1's closed set and silently partial over this one.
- Whether Kraken's adapter ever emits it is **not established**. The adapter is compiled into the extension module and carries no Python source to read; the library-side plumbing exists (`on_order_fill_voided`, an `events.order_fill_voided.*` topic), but that is the framework, not the venue leg.
- The startup half is closed and tested; both live halves are not.

## Suggested next steps

- Establish whether Kraken's v2 adapter can produce `OrderFillVoided` at all — read it off a running adapter or off upstream's Kraken execution client source, not off the framework's generic plumbing. If it cannot, the correct outcome is a recorded measurement that this is unreachable at this venue, and the two live paths keep their current behaviour with that reason written down.
- If it can, decide the reversal semantics as one design, covering all four things a fill moved: the journaled `row["filled_qty"]`, the in-process mirror the overfill trip reads, the row's terminal `state`, and the already-published counters (which cannot be retracted — so the decision is what the counter is allowed to mean, not how to undo it).
- Give whatever is decided a guard that is seen to bite: a fixture where a voided fill and an un-voided one produce different rows, since a fixture built on an order the void does not move passes under either behaviour.
