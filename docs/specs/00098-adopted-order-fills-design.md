# 00098 — adopted orders' fills become observable, without widening the kill trip

Resolves [[T0142]]. After a restart, a fill on a preserved resting reducer currently reaches no handler in this process: nautilus 1.230.0 reconciles a venue-resting order under `StrategyId("EXTERNAL")` unless its instrument is claimed, and order events publish on `events.order.<strategy_id>` — a topic this strategy does not subscribe to. The row never appends, no counter moves, and the forensic record the reconciliation trip is measured against silently diverges from venue truth. The topic's original dilemma — claim the instruments and gain observability but route the operator's sanctioned hand settle into the unknown-order kill trip — is a false binary, and this spec dissolves it.

## The measured basis

Verified against the installed library (read, not assumed), 2026-08-22:

- `nautilus_trader/execution/engine.pyx:907-913` — the order-events topic is `f"events.order.{strategy_id}"`, cached per strategy id.
- `engine.pyx:1414-1416` — the fill path ends in `publish_c(topic=_get_order_events_topic(fill.strategy_id), msg=fill)`, **unconditionally**: no special case drops the publish for `EXTERNAL`. A fill on a reconciled external order therefore does publish on `events.order.EXTERNAL`; today it merely has no subscriber.
- `model/identifiers.pyx:776` — `EXTERNAL_STRATEGY_ID = StrategyId("EXTERNAL")`, with `is_external()` as the predicate.
- `common/actor.pyx:187,761` — `self.msgbus` is a public attribute on every registered `Actor`; a `Strategy` may subscribe to any topic.
- Client-order-id continuity across restart-reconciliation is **supported but not yet production-observed** (no order has ever been submitted; the probe window has not run). The installed source: the adapter submits our full id, and reconciliation prefers `report.client_order_id`, falls back to venue-order-id lookup, and otherwise mints a UUID4 id (`live/execution_engine.py:3109-3141`). The venue's echo of `cl_ord_id` across sessions is the one unproven link — and its failure direction is safe: a UUID-minted id matches no ledger row, so the adopt pass cancels the order and its events land unmatched — scope intact, feature inert. The first armed-window restart is where continuity gets its live proof.

## Decisions

### D1 — subscribe to `events.order.EXTERNAL`; never claim

`ProbeExecutor` subscribes (at registration/start, via `self.msgbus`) to the external order-events topic and routes those events to a **dedicated handler** (public `on_external_order_event` wrapping private `_on_external_event`, mirroring `on_order_event`'s shape). `external_order_claims` stays unset. The two properties the topic said could not both be had:

- **Observability**: a matched adopted order's events reach this process the moment they happen.
- **Scope**: the unknown-order trip is untouched — it still runs only on the strategy's own topic, and an unmatched external event (the operator's hand settle) is ignored by the new handler, reaching no trip, no row, no cancel. `node.py`'s scoping precondition survives verbatim and gains a sentence describing the second, filtered path.

### D2 — the handler's matched path reuses the row/counter machinery, and trips on matched overfills only

Matching is against `self._attached` — the ledger-vouched rows the adopt pass re-attached. For a **matched** event:

- `OrderFilled` → overfill check first, exactly as `_trip_on_fill` does for own orders: a fill taking `filled_qty` past the ledgered ordered quantity (beyond `_OVERFILL_TOLERANCE`) records the fill (`_record_trip_fill` semantics — the fill happened; no-fill-without-a-record has no divergence exemption) and **trips the kill switch**. A ledgered adopted row is this engine's own pre-restart order; divergence on it is the same class the existing per-order trip guards, and tripping on matched rows only is what keeps the scope property intact. A clean fill appends to the row (`update_submitted_row`), credits `row["filled_qty"]`, and publishes counters via `_publish_fill`; when it completes the ledgered quantity (within `_OVERFILL_TOLERANCE` — the external path has no active intent to borrow a lot step from), the row is additionally marked `"filled"` and `_inc_order("filled")` counts the completion — nautilus publishes no separate terminal event after a resting order's final fill, so without this the row reads open forever. The entry stays in `_attached` (the no-pop ruling above), guarded so the completion write fires once: a further fill on the completed row goes to `_trip_on_fill`, whose overfill arm latches — the same divergence semantics an own order has.
- Terminal events → row state update via the existing payload idiom. **The entry does NOT leave `_attached` — neither path ever pops** (amended after Task 2's review): the first ruling had the external handler pop on terminal events, which re-created the exact race D4 cites as the reason the own path retains rows — Kraken's `ownTrades` and `openOrders` are separate WS channels with no cross-stream ordering guarantee, so a fill racing a terminal ack would have arrived unmatched, counted but never journaled, falsifying the no-fill-without-a-record invariant on the one path built to restore it. Retained rows make the two paths symmetric: a late fill within the ledgered quantity journals as a detached append; one beyond it trips the overfill arm, on either path. The mapping is ruled here, from `validate_exec_record`'s existing names: `OrderCanceled → "canceled"` (on this path the name makes **no we-requested claim** — the dominant real source is a cancel this very process sent from the adopt pass or a trip, whose ack now arrives matched; `venue_canceled` would be false for those), `OrderExpired → "venue_canceled"` (expiry is the venue's own doing), `OrderRejected → "rejected"`. `OrderCancelRejected` stays out of the map: event append, row stays attached. A side effect worth its own assertion: the adopt pass's cancel acks now **close** their rows, which previously stayed open forever and re-read as possibly-live on every future scan.
- Other events (`OrderAccepted` re-acks etc.) → row event append only.

### D3 — unmatched external events are counted and logged, never acted on

`zcrypto_exec_external_events_total{disposition="matched"|"unmatched"}` (counter), plus one info-level log line naming event type, instrument, and client order id. This is deliberately the **only** instrumentation of externally-originated activity: it makes a hand settle's existence visible in forensics with zero behavioural coupling — and it passively answers the question T0142's second next-step wanted a probe-window measurement for (whether external acts are visible to this process at all), so that sub-item dissolves. Metric lifecycle obligations travel with it, and one has a converge consequence: the capture role's `config.alloy` keep-regex **enumerates families with no wildcard**, so `zcrypto_exec_external_events_total` must join it — which makes this change touch `roles/capture/files/config.alloy`, and per `capture-deploys.md` the engine converge that ships this image must run `--tags capture,engine` with both currently-running digests, never `--tags engine` alone, or the family publishes unadmitted and silently. Also: the Alloy pin test's hand-pinned name list, a dashboard target on `engine-dashboard.json` (the charted-family guard enforces this), HELP text with no internal tokens, and eager registration at 0 for both label values so `increase()` is never blind to a first event (the counter is registered at startup, not born on the event — the venue-not-online lesson inverted deliberately: here presence-at-zero is correct because the family must exist before any external event does).

### D4 — lifecycle and wiring

Subscription established once, where the strategy's own handlers are wired (`node.py` / executor start), against the topic string derived from `StrategyId("EXTERNAL")` through the same format the engine uses. The handler is defensive in the `on_order_event` idiom: wrapped, logging on internal failure, never raising into the event loop. **Neither path removes rows from `_attached`** (amended after Task 2's review — the earlier external-pop ruling re-created the race this very paragraph names) — a late fill after a cancel ack must land as a detached append, and popping at the ack would send that fill to `_trip_on_fill`'s no-attachment branch and latch the kill on a routine late fill (the existing `test_a_late_fill_on_a_superseded_order_shrinks_the_next_resubmission` pins exactly this). No new venue calls anywhere.

### D5 — resolution is at merge; the deploy rides the standing converge cadence

The engine is live but **disarmed** (`exec_armed` renders `false`): submission happens only inside attended windows, where a restart is an abort, so the defect this spec fixes cannot fire in production before the fix deploys. T0142 resolves when the routing is decided (this spec), implemented, proven at the library boundary, and merged with both doc surfaces moved — the image change reaches the engine at its next canary-gated converge per `capture-deploys.md`, and the engine's payload proof is, as always, its next disarmed boundary cycles. No special converge is owed, and holding the topic open for an unschedulable live scenario (restart + resting reducer + fill) would repeat the `ripe_when` trap T0145 closed.

### D6 — the surfaces that must move together

- `executor.py::_adopt_resting_orders` docstring — currently states the unobservability as standing fact, with the T0142 pointer. Rewritten to describe the subscription path.
- `infra/runbooks/engine.md`'s arm step — the paragraph telling the operator to read an adopted order from venue truth. Rewritten: fills now append to the row; the hand settle remains invisible to the engine by design and is *counted*, not acted on.
- `node.py`'s scoping comment — extended as in D1. **And the structural guard that enforces the scoping**: `tests/test_engine_node.py::test_no_module_widens_the_engines_order_event_stream` bans the literal text `msgbus` in every `cli/**/*.py`. It is widened **red-first, before the code change** (the widen-the-guard-before-migration rule): an allowlist admits exactly `cli/engine/node.py` for `msgbus` — `external_order_claims` stays banned everywhere, `msgbus` stays banned in every other `cli` file — and the widened guard is re-proven by planting `msgbus` in `executor.py` and seeing red.
- The decisions-log entry (phase 6) records D1's choice against the topic's three original candidates.

## Verification

- **The library boundary is proven with the real message bus, not a mock of our own assumption**: a test constructs a `MessageBus`, publishes a genuine `OrderFilled` on the topic the *installed engine's own format* produces for `StrategyId("EXTERNAL")`, and asserts the handler received it. This doubles as the tripwire for the pending nautilus bump (PR #270): if a future version renames the topic or stops publishing external events, this test — not production — is where it surfaces.
- Constructed-event tests (the repo already constructs real nautilus fills — `venuestate.py`'s precedent): matched fill → row append + counters; matched overfill → kill trip latched, fill still recorded; unmatched fill → counter increments, log line, **no** row, no trip, no cancel; terminal event → row terminal + detached.
- The existing suite pins the own-topic path unchanged; the trip's own tests must pass untouched.
- Both counter label values present at startup (eager registration test), HELP swept by the operator-facing-text test, Alloy pin + dashboard target guards green.

## Out of scope

- `external_order_claims` in any form; any change to `_trip_on_fill`'s own-topic behaviour; any venue REST surface.
- The nautilus 1.231.0 bump (PR #270) — deliberately untouched; the library-boundary test is written to survive it or fail loudly.
- Arming policy (`exec_armed`), the probe plan, and every other 00090 surface.
