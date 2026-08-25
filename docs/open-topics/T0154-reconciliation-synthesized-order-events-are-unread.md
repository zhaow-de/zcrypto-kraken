---
status: open
ripe_when: "a v2 engine has run disarmed boundary cycles with the exec client live — the in-flight machinery cannot fire without one, so the rate at which it fires is unmeasurable until then. The routing DECISION below does not wait on that: it rests on facts already measured and is owed before `exec_armed` flips."
---

# Reconciliation synthesizes order events on the live trade path, and nothing reads the flag that says so

## Context — what

The execution engine manufactures order events of its own and dispatches them to strategies exactly as it dispatches the venue's, distinguished only by a `reconciliation` bool the event carries. Nothing under `cli/` reads that bool — `grep -n '\.reconciliation\b' cli/` is empty — so every synthesized event is handled as though the venue had said it.

Measured on the pinned wheel `2.0.0rc4.dev20260825` and against upstream source at `a52de0f914770b635701ae8961994e0f9b9067db` (`develop`, 2026-08-25T22:02:05Z, the day that nightly was cut):

- `LiveExecutionEngineConfig()` ships `inflight_check_interval_ms=2000`, `inflight_check_threshold_ms=5000`, `inflight_check_retries=5` and `generate_missing_orders=True`. `cli/engine/node.py`'s `_exec_engine_config()` sets only `reconciliation` and `filter_unclaimed_external_orders`, so all four defaults are live.
- **The in-flight check does not synthesize fills.** An order sitting `SUBMITTED`, `PENDING_UPDATE` or `PENDING_CANCEL` past the threshold is first *queried* — `QueryOrder` to the venue, once per retry — and at the fifth retry the manager (`crates/live/src/execution/manager.rs::check_inflight_orders`) manufactures a terminal event instead: `OrderRejected` with reason `INFLIGHT_TIMEOUT` for a `SUBMITTED` order, `OrderCanceled` for one pending a modify or cancel. Both are stamped `reconciliation=true`. Neither is a statement about what the venue did; both are the engine giving up on waiting.
- **`generate_missing_orders` is about positions, not in-flight orders.** It licenses reconciliation to synthesize a whole missing order, with its fill, to make the cache's position agree with a venue position report. Such an order is stamped `StrategyId("EXTERNAL")` with a reconciliation tag, so it arrives on `ExternalOrderObserver`, matches no ledgered row, and is counted `unmatched` and dropped — the one route of the three that is already contained, and contained by 00098 D3 rather than by anything aimed at this.
- **A synthesized fill's `TradeId` is synthetic.** `crates/execution/src/reconciliation/ids.rs` mints `S-{hex_ts}-{hash}` (FNV-1a over the fill fields) — deterministic across restarts so the engine's own duplicate-fill sanitizer dedupes *replays*, but by construction never equal to the venue's real trade id. So `is_duplicate_fill` cannot join a synthesized fill to the venue's later real one; what stops the pair being applied twice is `check_overfill`, with `allow_overfills` defaulting `False`, which refuses the second and does **not** publish it.

## Why this matters

This is the live trade path, and one of the three routes reaches an arm that spends money.

A cancel this engine requested sets `active.cancel_requested`. If the venue's ack does not arrive within roughly five retries, the manager manufactures the `OrderCanceled` itself. That lands in `_on_cancel_ack`, takes the `cancel_requested` branch, writes the row `canceled`, and proceeds to `_fallback(active)` or `_finish_revoked(active)` — the executor submitting its next order on the strength of a cancel **nobody at the venue confirmed**. The original may still be resting. This is the same class of ambiguity `_on_rejected` refuses to guess at, handled with a certainty the event does not carry.

The rejection route happens to land safely, and it is worth writing down that it is by accident rather than by decision: `INFLIGHT_TIMEOUT` contains none of `_POST_ONLY_MARKER` or `_KRAKEN_ERROR_MARKERS`, so `_on_rejected` falls through to the **ambiguous** arm — row `ambiguous`, remainder dropped, no resubmission, plan halted. That is exactly the right answer for an unanswered order, reached by a string not matching rather than by anything knowing the event was manufactured. A future marker list that grew a generic entry would silently turn it into a resubmission.

Failure direction across the three routes is not uniform, which is why "it fails safe" is not an available summary: the position route is contained, the rejection route halts, and the cancel route acts.

## Findings so far

- Nothing in `cli/` reads `event.reconciliation`, on any path. The bool is first-class on `OrderFilled`, `OrderRejected` and `OrderCanceled` alike.
- Spec `00100` neither adopts nor rejects this machinery. It records `LiveExecEngineConfig` as "identical across all 33 shared fields" and names only `reconciliation` and `filter_unclaimed_external_orders`; the in-flight knobs and `generate_missing_orders` are not discussed anywhere in the design.
- The engine cannot arm on v2 yet (`exec_armed` renders `false`), so nothing here can fire against real capital before the decision is taken. It can fire on a **disarmed** engine only if orders are submitted, which they are not — so the rate is genuinely unmeasured, not merely unread.
- The `unmatched` half of `zcrypto_exec_external_events_total` is the family a synthesized position-reconciliation order would move, and `zcrypto_exec_orders_total{outcome="ambiguous"}` is the family a synthesized `INFLIGHT_TIMEOUT` rejection would move. Both are already deployed and already charted, so the reading needs no new instrumentation.

## Suggested next steps

- **Decide the routing, which needs no further measurement.** Three candidates, and they are not exclusive:
  1. *Read the flag.* Route any terminal event carrying `reconciliation=True` into the ambiguous arm rather than into `_fallback` / `_reprice` / `_finish_revoked` — the executor's own stated reasoning for the ambiguous arm ("the order may be live at the venue -- no resubmission, no fallback, and the plan halts") is a description of exactly this event. Cheapest, and it makes the rejection route's accidental safety deliberate.
  2. *Widen the wait.* `inflight_check_threshold_ms` and `inflight_check_retries` are ours to set; five retries at five seconds is upstream's guess, not a figure derived against Kraken's REST ack latency. Setting them explicitly, with a recorded basis, makes the synthesis rare instead of merely handled — but it does not remove the case, so it is a complement to (1), never a substitute.
  3. *Refuse the synthesis.* Whether the in-flight terminal generation can be disabled outright, as distinct from delayed, is not established — `generate_missing_orders=False` governs the position route only, and its documented effect is to log an error and reconcile nothing.
- **Take the rate reading once a v2 engine is running disarmed**, from the two families named above plus the engine's own log lines for `INFLIGHT_TIMEOUT`, and record it in the arming pass's evidence. A zero reading is the expected one while nothing submits; it is worth taking anyway, because a non-zero one before any order exists would mean the machinery fires on something nobody has modelled.
- **Give whichever routing is chosen a guard that is seen to bite**, on a fixture where a manufactured cancel ack and a venue-sourced one produce DIFFERENT outcomes — the same event class, the same active intent, `reconciliation` true and false. A fixture built only from `reconciliation=True` events cannot tell a correct implementation from one that ignores the flag.
- **Land the outcome in spec `00100`**, which is currently silent on this whole seam, so the next reader of the design does not have to rediscover that the defaults were never adjudicated.
