---
status: partial
ripe_when: "the first v2 engine converge has happened — the engine in production still runs a wheel on which `OrderFillVoided` and `OrderStatus.VOIDED` do not exist, so nothing can produce this event until then"
---

# A voided fill has no reversal semantics anywhere on the live order-event path

## Context — what

The installed nautilus carries an order event this engine has no handling for: `OrderFillVoided`, the venue undoing a fill it previously reported (a busted trade, a correction). Applying it to an order that was `FILLED` moves it to `OrderStatus.VOIDED` — measured by driving a real `LimitOrder` through the library's own events in `tests/test_engine_executor.py`.

Three surfaces meet it, and each does something different:

- **The startup reconciliation** now handles it. `_ADOPTED_TERMINAL_STATES` gained `OrderStatus.VOIDED -> "venue_canceled"`, so an adopted order the venue voided while this process was down closes its row instead of resting in the re-attach set forever.
- **The live external path** (`_on_external_event`) now reads the same `OrderStatus`-keyed map, so the class-name hole is gone; what its row's `state` ends up saying is set out under *Done so far*, and it is not the whole story.
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
- A void only reaches `OrderStatus.VOIDED` when it empties a fill that COMPLETED the order. Void a PARTIAL fill and the order returns to `ACCEPTED` with `filled_qty` back at zero — still resting, still working its full quantity. Measured by applying the library's own events to a real `LimitOrder`.

## Done so far

**The row's terminal `state` — one of the four things a fill moves — is decided and implemented.** `_EXTERNAL_TERMINAL_STATES`, the class-name-keyed map that had no `OrderFillVoided` entry, is deleted; `_on_external_event` reads `cache.order(...).status` through the one `OrderStatus`-keyed map, which is proven total over the library's own closed set and already carried `VOIDED -> "venue_canceled"`. Both row-state paths now answer from the venue's own order.

What that is worth here is smaller than it looks, and the measurements say so:

- **The row does not, and did not, read as possibly-live after a void.** `filled` and `venue_canceled` are both terminal — neither is in `_OPEN_ORDER_STATES` — so no voided row re-attaches on a later scan. Where the order returns to `ACCEPTED` the row keeps an open state and that is CORRECT: the order really is still resting.
- **In the ordinary sequence the VOIDED entry never fires.** A void that empties a completing fill meets a row already reading `filled`, and the completed-row guard suppresses the terminal write. Measured end to end through the executor: the row stays `filled` with `filled_qty` at the quantity the venue just undid. Only where the venue order is smaller than the ledgered quantity does the row reach `venue_canceled`.
- So the state half is settled in the sense that it is now derived from venue truth rather than from an event's name — but the row still MISSTATES a voided complete fill, and it misstates it through the quantity, not through the state.

One harness landmine was cleared in the same change: a dispatched `OrderFilled` carrying a `position_id` makes a subsequent `OrderFillVoided` raise `Invalid event for order type`, so the fixture stamps that id only on the copy its position arithmetic uses. Without that, no test in this suite could deliver a void at all.

## Suggested next steps

- Establish whether Kraken's v2 adapter can produce `OrderFillVoided` at all — read it off a running adapter or off upstream's Kraken execution client source, not off the framework's generic plumbing. If it cannot, the correct outcome is a recorded measurement that this is unreachable at this venue, and the remaining quantity behaviour keeps its current shape with that reason written down.
- If it can, decide the reversal semantics for the three things still untouched: the journaled `row["filled_qty"]`, the in-process mirror the overfill trip reads, and the already-published counters (which cannot be retracted — so the decision is what the counter is allowed to mean, not how to undo it). This is the hard part and it has not moved: `update_submitted_row` takes `add_filled_qty` and no path has ever passed it a negative.
- Decide what the row's `state` should say once the quantity is decided, in the one case the completed-row guard currently owns: a void that empties a completing fill leaves `filled` standing over a quantity the venue withdrew. Changing it means deciding what happens to the `_inc_order("filled")` already counted — which is why it belongs with the quantity decision and not before it.
- Give whatever is decided a guard that is seen to bite: a fixture where a voided fill and an un-voided one produce different rows. Note that the obvious fixture does NOT differ — a void of a partial fill leaves the order `ACCEPTED` and both behaviours write nothing — so the fixture has to be the completing-fill case.
