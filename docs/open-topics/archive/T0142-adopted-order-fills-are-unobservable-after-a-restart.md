---
status: resolved
---

# Adopted resting orders: their fills are unobservable after a restart

## Context — what

`ProbeExecutor._adopt_resting_orders` (the startup pass, spec 00090 D10) keeps a venue-resting order alive when the exec ledger carries it as a non-terminal reduce-only row: the order is left resting, the row is preserved, and the row is re-attached to `self._attached` so a fill would have somewhere to land.

That last part does not hold across a restart, and the pass cannot make it hold. In the installed nautilus-trader (1.230.0), `LiveExecutionEngine._generate_order` assigns a reconciled venue order `StrategyId("EXTERNAL")` unless the instrument appears in some strategy's `external_order_claims`; `ExecutionEngine._send_to_strategy` then publishes its events on `events.order.<strategy_id>`, and a `Strategy` subscribes only to its own id's topic. So after a restart, a fill on a preserved resting order reaches no handler in this process: no row append, no `zcrypto_exec_fills_total`, no `zcrypto_exec_fees_eur_total`, no position or realized-PnL move. The order is still real and still fills — it is simply reconciled as venue truth and nowhere else.

The obvious fix is to claim the instrument (set `external_order_claims` on the strategy). That is the thing this topic exists to decide, because it is not free.

## Why this matters

Claiming the twelve basket instruments would route **every** externally-originated order on them into this executor — including the operator's own hand-placed acts. The probe procedure has exactly one such act by design: the manual settle of the BTC/EUR margin long in the Kraken web UI, which the engine's adapter cannot perform. Today that settle reaches the executor's event path not at all, which is precisely what keeps the unknown-order kill trip scoped to genuine surprises. Claim the instrument and the sanctioned settle becomes an unknown order arriving at the fill handler, where the trip latches the kill file, cancels resting orders, refuses every further intent, and pages — during a window whose whole purpose is to complete that settle.

So the two properties are in tension and cannot both be had by claiming alone:

- **Observability**: an adopted order's post-restart fills append to their forensic row and move the execution counters.
- **Scope**: the unknown-order trip fires only on orders nobody sanctioned, so a hand settle cannot latch the kill switch mid-window.

Deferring is cheap *while the probe is attended*: a restart inside a window is already an abort, the operator is present, and venue truth is one Kraken page away. It stops being cheap when arming becomes continuous, because then a restart is a routine event and a silently-unaccounted fill is a permanent hole in the forensic record — the record the reconciliation trip itself is measured against.

## Findings so far

- Measured against the installed library, not assumed: `nautilus_trader/live/execution_engine.py` (the `StrategyId("EXTERNAL")` assignment and its `get_external_order_claim` bypass), `nautilus_trader/execution/engine.pyx` (`topic = f"events.order.{strategy_id}"`), `nautilus_trader/model/identifiers.pyx` (`EXTERNAL_STRATEGY_ID`).
- The docstring of `_adopt_resting_orders` previously claimed the opposite — that a preserved order's later fills append to its row. Corrected in place on the 00090 branch, together with a paragraph in the runbook's arm step telling the operator to read such an order from venue truth instead.
- Behaviour was deliberately left unchanged at 00090 merge time: the routing change is not a merge-gate fix, and making it under the deadline would have traded a scoped kill trip for observability nobody needed inside an attended window.

## Resolution

**Resolved 2026-08-22 by spec `00098` (iter-143), ahead of its ripeness trigger by owner fiat** — `exec_armed` still renders `false` and no non-terminal row ever crossed a restart; the owner directed the resolution as its own iteration rather than waiting for continuous arming to make the defect live. The topic's dilemma was a false binary: claiming and observing are separate acts, because the engine publishes a reconciled EXTERNAL order's events unconditionally on `events.order.EXTERNAL` — the topic merely had no subscriber. The engine now subscribes it (`cli/engine/node.py`) and a disposition filter (`cli/engine/executor.py::_on_external_event`) matches events against the ledger-vouched `_attached` rows: a matched fill appends to its row, moves the fill/fee counters, and latches the overfill trip exactly as an own order's fill does; terminal acks close their rows; neither path ever removes a row (the no-pop symmetry, forced by the ownTrades/openOrders cross-stream race). An unmatched event — the operator's sanctioned hand settle — is counted (`zcrypto_exec_external_events_total{disposition="unmatched"}`) and logged, and reaches no trip, no row, no cancel. The library boundary is pinned two ways: a real `MessageBus` publish on the installed engine's own topic format, and a really-registered strategy whose expected topic is derived from the library's register-time subscriptions.

The three suggested next steps, each disposed:

- **The routing decision** — taken and recorded as `[iter-143]` in `docs/research/14.phase6-decisions.md`: all three candidates rejected as written (the exemption allowlist, the startup-only trade-history read, the unconditional cancel), in favour of subscribe+filter, an option none of them contained.
- **The hand-settle visibility measurement** — half dissolved, half already homed: the order-event half is now answered passively and permanently by the `unmatched` counter (spec `00098` D3), no probe-window act needed; the position-propagation half (whether a settle reaches the engine's position view) predates this topic and stays where it is operated — the settle preconditions in `infra/runbooks/engine.md`'s probe-window section, operating-surface text per the iter-140 precedent, taken at the probe window.
- **The two prose surfaces** — `_adopt_resting_orders`' docstring and the runbook's arm step both rewritten in place to the new truth in the same branch, with the claim swept across `cli/`, `infra/`, `tests/`, and `docs/`.

The deploy rides the next canary-gated engine converge, which must run `--tags capture,engine` — the counter's Alloy admission lives in the capture role's keep-regex.
