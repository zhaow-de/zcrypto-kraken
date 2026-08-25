---
status: partial
ripe_when: "the v2 arming pass reaches its go/no-go — `exec_armed` renders `false` today and this decision is owed before it flips. It no longer waits on a converge: the event's only possible origin here is now measured, and it is the framework's reconciliation, never the Kraken adapter."
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
- The Kraken adapter never emits it, and cannot. Established off upstream source (see *Done so far*): the token `voided` appears nowhere in the Kraken crate in any case, and no code path there produces `OrderStatus::Voided` on a status report. What CAN produce the event at this venue is the framework's own reconciliation, which is adapter-agnostic.
- A void only reaches `OrderStatus.VOIDED` when it empties a fill that COMPLETED the order. Void a PARTIAL fill and the order returns to `ACCEPTED` with `filled_qty` back at zero — still resting, still working its full quantity. Measured by applying the library's own events to a real `LimitOrder`.

## Done so far

**The row's terminal `state` — one of the four things a fill moves — is decided and implemented.** `_EXTERNAL_TERMINAL_STATES`, the class-name-keyed map that had no `OrderFillVoided` entry, is deleted; `_on_external_event` reads `cache.order(...).status` through the one `OrderStatus`-keyed map, which is proven total over the library's own closed set and already carried `VOIDED -> "venue_canceled"`. Both row-state paths now answer from the venue's own order.

What that is worth here is smaller than it looks, and the measurements say so:

- **The row does not, and did not, read as possibly-live after a void.** `filled` and `venue_canceled` are both terminal — neither is in `_OPEN_ORDER_STATES` — so no voided row re-attaches on a later scan. Where the order returns to `ACCEPTED` the row keeps an open state and that is CORRECT: the order really is still resting.
- **In the ordinary sequence the VOIDED entry never fires.** A void that empties a completing fill meets a row already reading `filled`, and the completed-row guard suppresses the terminal write. Measured end to end through the executor: the row stays `filled` with `filled_qty` at the quantity the venue just undid. Only where the venue order is smaller than the ledgered quantity does the row reach `venue_canceled`.
- So the state half is settled in the sense that it is now derived from venue truth rather than from an event's name — but the row still MISSTATES a voided complete fill, and it misstates it through the quantity, not through the state.

**The origin is measured, and it is singular.** Read off upstream `nautilus_trader` at `a52de0f914770b635701ae8961994e0f9b9067db` (`develop`, 2026-08-25T22:02:05Z — the day the pinned nightly `2.0.0rc4.dev20260825` was cut), because the installed adapter is compiled and ships only `__init__.pyi`.

- **Not the adapter.** A case-insensitive sweep for `voided` across all 157 files of `crates/adapters/kraken/` returns zero hits, and the `OrderStatus::` values that crate constructs are `Filled`, `PartiallyFilled`, `Canceled`, `Expired`, `Rejected`, `Accepted`, `Triggered`, `New`, `PendingNew`, `Submitted` (plus Kraken's own `Open`/`Closed`/`Pending`/`Untouched`/`Cancelled`) — never `Voided`. The sweep's filter is validated against a positive control rather than trusted empty: the same grep over `crates/adapters/polymarket/src/execution/` returns that adapter's whole void machinery (`OrderEventAny::FillVoided`, `OrderFillVoidedSpec::builder()`, `restore_voided_trade`).
- **The framework, on ONE condition.** `crates/execution/src/reconciliation/orders.rs` constructs `OrderFillVoided` in exactly two places. `create_reconciliation_terminal_fill_void` reverses the leaves of an order whose report says `Voided` — unreachable here, since Kraken never reports that status. `create_reconciliation_fill_voids` fires when a venue snapshot reports a cumulative filled quantity **lower** than the order this process has already applied; it is gated on `allow_fill_decrease`, which `generate_reconciliation_order_snapshot_events` passes as `true`, and `crates/execution/src/engine/mod.rs` takes that path for a bundled status-report-plus-fill-reports reconciliation. Kraken's spot execution client implements `generate_fill_reports`, so it is on that path.
- **So the trigger is the venue reporting less filled than the ledger — which is the same statement 00098 D7's negative-delta arm already trips on.** The library applies its void first (lowering the order's own `filled_qty`), and the startup sweep then reads a ledger claiming MORE than venue truth and latches the kill switch. That is the correct direction and it is why the topic's "correctly, but for a reason nobody will be able to read from the row" is precise rather than rhetorical: the row records a repair-and-trip, and nothing in it says a fill was withdrawn.
- The synthesized fill events carry a **deterministic synthetic `TradeId`** (`crates/execution/src/reconciliation/ids.rs`: `S-{hex_ts}-{hash}`, FNV-1a over the fill fields) — stable across restarts so the engine's own duplicate-fill sanitizer dedupes replays, but by construction NOT equal to the venue's real trade id. Whatever the quantity decision turns out to be, it cannot be keyed on `trade_id` equality between a synthesized event and a venue-sourced one.

One harness landmine was cleared in the same change: a dispatched `OrderFilled` carrying a `position_id` makes a subsequent `OrderFillVoided` raise `Invalid event for order type`, so the fixture stamps that id only on the copy its position arithmetic uses. Without that, no test in this suite could deliver a void at all.

## Suggested next steps

- Decide the reversal semantics for the three things still untouched: the journaled `row["filled_qty"]`, the in-process mirror the overfill trip reads, and the already-published counters (which cannot be retracted — so the decision is what the counter is allowed to mean, not how to undo it). This is the hard part and it has not moved: `update_submitted_row` takes `add_filled_qty` and no path has ever passed it a negative.
- Decide what the row's `state` should say once the quantity is decided, in the one case the completed-row guard currently owns: a void that empties a completing fill leaves `filled` standing over a quantity the venue withdrew. Changing it means deciding what happens to the `_inc_order("filled")` already counted — which is why it belongs with the quantity decision and not before it.
- Give whatever is decided a guard that is seen to bite: a fixture where a voided fill and an un-voided one produce different rows. Note that the obvious fixture does NOT differ — a void of a partial fill leaves the order `ACCEPTED` and both behaviours write nothing — so the fixture has to be the completing-fill case.
