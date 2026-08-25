---
status: open
ripe_when: "the first v2 engine converge has happened and the engine has run at least one disarmed 4-hourly boundary cycle on it"
---

# The external-order delivery leg is proven in two halves that have never been joined

## Context — what

Spec `00100` D2 replaces the removed `msgbus` subscription with a second `Strategy` registered under `StrategyId("EXTERNAL")`, whose `on_order_event` receives the events unclaimed external orders are published on. Two halves of that path are established, and they have never been joined end to end:

- **The publish leg**, from source: nautilus stamps unclaimed reconciled orders `StrategyId::external()` and publishes them on `events.order.{strategy_id}`.
- **The delivery leg**, by experiment: a strategy registered under that id does receive events delivered on that topic, verified in a backtest.

What is unverified is the join — that a **genuine venue-sourced external order on Kraken** traverses both and arrives at the observer. That needs live reconciliation against the venue, which no backtest reaches and no workstation run can reach either: the exec key is IP-bound to the engine host.

## Why this matters

D2 is the replacement for a mechanism v2 deleted, and it sits on the live trade path. If the join does not hold, adopted orders' fills become unobservable in-process again — the exact regression `00098` exists to prevent — and nothing announces it: an observer that receives nothing looks identical to an account with no external orders. The failure is silent by construction.

The fallback if it does not hold is known and cheap (poll the Cache on the executor's existing 5-second tick, which `00098` D7's adopted-row sweep already does for a different purpose), so the cost of discovering this late is rework rather than redesign — but only if someone actually looks.

## Findings so far

- `00100` D2 records the mechanism and the measured basis, including that `Strategy.on_order_event` is a direct Rust→Python call rather than a bus subscription, so it is unaffected by the `PyMessage` barrier that kills every `MessageBus.subscribe` route.
- Measured on the pinned wheel: an observer built with `StrategyConfig(strategy_id=StrategyId("EXTERNAL"))` and **no** `order_id_tag` keeps `strategy_id == EXTERNAL` through `add_strategy`. Supplying a tag yields `EXTERNAL-001`, which would receive nothing — that trap is recorded in the plan.
- The counter `zcrypto_exec_external_events_total{disposition=...}` is the observable: `matched` or `unmatched` both prove arrival; a flat counter across a window containing a known external order is the refutation.

## Suggested next steps

- After the first v2 engine converge, with the engine **disarmed**, place or settle one order outside the engine on a symbol in the basket and confirm `zcrypto_exec_external_events_total` increments — `unmatched` is the expected disposition for an order the engine's ledger does not vouch for. Read it with `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto"}'`; `(no series)` is a FAIL, not a zero.
- If the counter does not move, the delivery leg is refuted: switch D2 to the Cache-polling fallback on the executor's existing tick rather than working around the observer.
- Record the outcome either way in the phase-6 decisions log — a silent pass leaves the next reader unable to tell a verified join from an unrun check.
- **Take the healthy-boot baseline for the same counter, at the same trigger, before anything is thresholded on it.** The observer is registered when the node is built rather than at `on_start`, so events published during the engine's own startup reconciliation can now reach it and be counted `unmatched` — safe (logged and dropped; `_attached` is empty until the first adopt tick) but it means the counter may rise at **every healthy boot**. Read `zcrypto_exec_external_events_total{disposition="unmatched"}` immediately before and immediately after one clean **disarmed** engine start and record the difference; `(no series)` is a FAIL of the telemetry path, never a zero. Write the number into that version's `docs/research/` verification doc. **Only then** may an unmatched-external alert be authored, with a threshold clear of that baseline, and pushed only **after** the metric has its first record — a rule pushed before its metric exists pages a spurious no-data alert, and `grafana-push.sh` upserts and never deletes. The operating home for both is `infra/runbooks/engine.md`'s pre-probe step 4; this bullet is the registration. Note the ordering against the bullet above: that one wants the counter to MOVE on a deliberate external order, this one wants to know how much it moves without one — take the baseline first, or the deliberate-order reading has nothing to stand against.
