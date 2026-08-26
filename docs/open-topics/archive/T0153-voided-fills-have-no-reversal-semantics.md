---
status: resolved
---

# A voided fill has no reversal semantics anywhere on the live order-event path

## Context — what

The installed nautilus carries an order event this engine had no handling for: `OrderFillVoided`, the venue undoing a fill it previously reported (a busted trade, a correction). Applying it to an order that a fill had COMPLETED moves it to `OrderStatus.VOIDED` with `filled_qty` back at zero; applying it to a partial subtracts the event's own `voided_qty` and leaves the order working. Both measured by driving a real `LimitOrder` through the library's own events.

Four things a fill moves, and none of them had a reversal: the journaled `row["filled_qty"]`, the in-process mirror the overfill trip reads, the row's terminal `state`, and the published counters — which cannot be un-published at all, so what is decidable for them is what they are allowed to MEAN.

## Why this matters

This is the live trade path, and the failure was quiet in both directions.

Leave the quantity as it stands and the engine believes it holds inventory the venue says it never got: the ladder sizes its next order against a position that does not exist, and `held` carries it into the weekly drift arithmetic.

Subtract it naively and the overfill trip's base moves under it: the trip compares a running total against the ordered quantity, so a reversal that is not mirrored everywhere the fill was mirrored either disarms the trip or fires it on a healthy order.

## Findings so far

- **The event is real and reachable on the pinned wheel.** Applying it after a full fill lands `OrderStatus.VOIDED`, which the library reports `is_closed`; the terminal-map totality proof is what found it. Applying it after a PARTIAL fill returns the order to `ACCEPTED` — still resting, still working — and where two fills exist, only the referenced one is subtracted.
- **It carries the quantity to reverse.** `voided_qty`, plus `commission_voided`, a `correction_id`, an `is_reopened` flag, and the ORIGINAL fill's `trade_id` — a void references the trade it undoes, unlike a synthesized fill, which mints an id because the report carries none. So a reversal rule COULD have keyed on trade-id equality; the reason none does is the decision below, not an inability to express one.
- **The Kraken adapter never emits it and cannot.** A case-insensitive sweep for `voided` across all 157 files of `crates/adapters/kraken/` returns zero hits (filter validated against a positive control in the polymarket adapter), and no path there produces `OrderStatus::Voided` on a status report.
- **The framework's reconciliation is the only producer, and it cannot reach a running strategy.** Established off upstream `nautilus_trader` at `a52de0f914770b635701ae8961994e0f9b9067db` — the chain is one line with no branches, and it is set out in full in spec 00100 D16. In short: the only Kraken-reachable constructor is `create_reconciliation_fill_voids`, fired when a venue snapshot reports LOWER cumulative filled than the order; it is gated on `allow_fill_decrease`, which only the snapshot generators pass, which only `reconcile_order_with_fills` calls, which at this venue only `reconcile_execution_mass_status` reaches — and that runs inside `perform_startup_reconciliation()`, which `crates/live/src/node/mod.rs` completes BEFORE `start_trader()`. Nothing is subscribed when it publishes. The two periodic checks are off (`open_check_interval_secs` / `position_check_interval_secs` both `None`) and could not reach it anyway: they route through the singular `reconcile_order_report`, which mints a void only for a `Voided` report.
- **So the surface is the Cache, not an event.** The library applies the void to the order before this process has a strategy at all, and the engine's first and only sight of it is a venue order whose own `filled_qty` has come down.

## Done so far

**The row's terminal `state` was settled first.** `_EXTERNAL_TERMINAL_STATES`, the class-name-keyed map that had no `OrderFillVoided` entry, is deleted; `_on_external_event` reads `cache.order(...).status` through the one `OrderStatus`-keyed map, which is proven total over the library's own closed set and already carried `VOIDED -> "venue_canceled"`. Both row-state paths answer from the venue's own order rather than from an event's name.

The measurements bounded what that bought, and they are what pointed at the quantity: in the ordinary sequence the `VOIDED` entry never fires, because a void that empties a completing fill meets a row already reading `filled` and the completed-row guard suppresses the terminal write. The row misstated a voided complete fill, and it misstated it through the quantity.

One harness landmine was cleared in the same change: a dispatched `OrderFilled` carrying a `position_id` makes a subsequent `OrderFillVoided` raise `Invalid event for order type`, so the fixture stamps that id only on the copy its position arithmetic uses. Without that, no test in this suite could deliver a void at all.

## Resolution

The quantity is decided and implemented, in the branch commits "the venue withdrawing a fill from a finished order stops being invisible" and "00100 D16 rules on the fill this engine was told to give back". The rule is one sentence: **a withdrawn fill is believed and never reversed — the ledger keeps what it recorded, and the disagreement between it and venue truth latches the kill switch.**

- **No live handler was added, and the measurement above is why**: the event cannot be dispatched to a strategy on this pin and config, so an arm in `_on_order_event` or `_on_external_event` would be a guard on a door with no caller. `_RECONCILED_TERMINALS`' comment now records that, so the fall-through is not "fixed" later by someone who has not read the chain.
- **The hole was in the sweep that DOES read the Cache.** `_reconcile_adopted_rows` (00098 D7) already latches on the venue reporting less filled than the ledger — but it is fed `open_submitted_rows`, D10's re-attach input, which serves only the states an order can still be live in. A withdrawal that empties a completing fill lands on a row reading `filled`, which is in no re-attach set and was therefore compared against nothing, ever. The partial case was already covered and stays so: voiding a partial leaves the order `ACCEPTED` and the row open, where D7 sweeps it.
- **`closed_submitted_rows` is the complement of the same predicate**, so the two are total over `submitted` by construction and a row in neither set cannot exist. `_reconcile_finished_rows` runs it through one question in one direction on D7's own dead-band — does the venue still report the quantity this row was closed on? — and a shortfall journals a `withdrawn` event and latches, naming both figures.
- **Nothing is reversed**: not `row["filled_qty"]`, not the in-process mirror, not `held`, not the counters. `_inc_order("filled")`, the fills counter and the fee counter mean *fills this engine was told happened and paid for*, never *fills that survived a later correction*; the kill file and the `withdrawn` event are what say a correction landed. The three rejected alternatives — subtracting the quantity, routing to `_strand_ambiguous`, and demoting the row's `state` — are each weighed in 00100 D16 with the reason each loses.
- **Guarded in both directions on a fixture the withdrawal MOVES**: one closed row on the full quantity and a real `LimitOrder` filled to it, the arms differing only in whether `OrderFillVoided` is applied — so one order reads `VOIDED` at zero and the other `FILLED` at the quantity. The un-voided arm is the true positive (a sweep latching on the mere fact that a row is closed would kill the engine at every boot after any order ever filled), and a third arm makes the ledger write raise, because that write stands in front of the trip. Proven by mutation probe.

The accepted residual, named rather than left implicit: `held` keeps the withdrawn quantity, so an operator who clears the kill switch by hand owns reconciling the ledger. Clearing it is already a human act no code performs.
