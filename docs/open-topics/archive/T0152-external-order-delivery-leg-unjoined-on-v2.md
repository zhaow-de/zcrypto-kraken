---
status: resolved
---

# The external-order delivery leg is proven in two halves that have never been joined

## Context — what

Spec `00100` D2 replaces the removed `msgbus` subscription with a second `Strategy` registered under `StrategyId("EXTERNAL")`, whose `on_order_event` receives the events unclaimed external orders are published on. Two halves of that path are established, and they have never been joined end to end:

- **The publish leg**, from source: nautilus stamps unclaimed reconciled orders `StrategyId::external()` and publishes them on `events.order.{strategy_id}`.
- **The delivery leg**, by experiment: a strategy registered under that id does receive events delivered on that topic, verified in a backtest.

What is unverified is the join — that a **genuine venue-sourced external order on Kraken** traverses both and arrives at the observer. That needs live reconciliation against the venue, which no backtest reaches and no workstation run can reach either: the exec key is IP-bound to the engine host.

## Why this matters

D2 is the replacement for a mechanism v2 deleted, and it sits on the live trade path. If the join does not hold, adopted orders' fills become unobservable in-process again — the exact regression `00098` exists to prevent — and nothing announces it: an observer that receives nothing looks identical to an account with no external orders. The failure is silent by construction.

The fallback if it does not hold is known but is not free: poll the Cache on the executor's existing 5 s tick (`_TICK_SECONDS`). The tick exists; the polling does not. `00098` D7's adopted-row sweep runs on that tick **once at startup** — `_adopted` is a one-shot latch — so a recurring poll is new behaviour to build, test and guard, not a rider on an existing loop. That makes looking early worth more, not less: the shape of the answer is known, so discovering it late costs a build rather than a redesign, but it is still a build.

## Findings so far

- `00100` D2 records the mechanism and the measured basis, including that `Strategy.on_order_event` is a direct Rust→Python call rather than a bus subscription, so it is unaffected by the `PyMessage` barrier that kills every `MessageBus.subscribe` route.
- Measured on the pinned wheel: an observer built with `StrategyConfig(strategy_id=StrategyId("EXTERNAL"))` and **no** `order_id_tag` keeps `strategy_id == EXTERNAL` through `add_strategy`. Supplying a tag yields `EXTERNAL-001`, which would receive nothing — that trap is recorded in the plan.
- The counter `zcrypto_exec_external_events_total{disposition=...}` is the observable: `matched` or `unmatched` both prove arrival; a flat counter across a window containing a known external order is the refutation.
- **Both label sets are registered eagerly at startup** (`cli/engine/command.py`, the `_EXEC_EXTERNAL_DISPOSITIONS` loop). So the series exists from boot whether or not the observer ever receives anything: `(no series)` means the engine's scrape is down, and **a reading of `0` cannot distinguish a wired observer with nothing to report from an observer that is never called.** This is the mechanism behind the silent failure named above, and it is why only a window containing a KNOWN external order can decide the question.
- **On v1 the join demonstrably worked against the real venue**, which is what makes the v2 mechanism specifically — not the venue's publish side — the thing in doubt. Reconstructed from the metric's own history (see `## Done so far`): the pre-v2 process counted 12 `unmatched` events mid-life and a further 12 across the 2026-08-26 attended probe window.

## Done so far

**The two readings this topic owed — the healthy-boot baseline and the join — are both taken, and the alert the baseline would have unblocked is decided below.** The baseline below was read on 2026-08-27 from the metric's own history via `infra/scripts/grafana-query.py` with PromQL `offset`, cross-checked against `process_start_time_seconds{job="engine_app"}` at every point so a counter reset is never mistaken for a delta. The join bullet's provenance is different and is stated there: a live order placed by the owner, read back by event class from Loki. No host was touched by either.

Trajectory of `zcrypto_exec_external_events_total{disposition="unmatched",host="zcrypto"}`:

| when | process | value |
| --- | --- | --- |
| pre-v2 process boot 2026-08-23 10:21:02Z, +0.5 h → +4.5 h | `1787480462.69` | **0** |
| same process, by 2026-08-23 20:49Z | `1787480462.69` | 12 |
| flat through 2026-08-26 08:00Z | `1787480462.69` | 12 |
| across the attended probe window, 2026-08-26 ~08:40Z | `1787480462.69` | **24** |
| v2 process boot 2026-08-26 16:40:20Z, +0.1 h → +22.1 h | `1787762420.39` | **0** |

- **The healthy-boot baseline is 0 — the sub-item's question is answered.** The worry was that v2 registers the observer at node build rather than at `on_start`, so the engine's own startup reconciliation could now be counted at every healthy boot. Measured: the v2 process sat at 0 for 22.1 hours from boot. The pre-v2 process also read 0 for its first 4.5 hours, and its 12 arrived **mid-life**, not at boot — so the registration-point change did not move the boot behaviour.
- **The caveat belongs with the number: both boots were on a FLAT account** — no open orders, no positions, EUR only. Startup reconciliation had nothing to reconcile. `0` is therefore the baseline for *a boot on a flat account*, which is every boot before rung 1 and none after it. A threshold set from this number is not yet validated for a boot carrying live orders.
- **The 2026-08-26 probe window's rise is +12, within one process** — `process_start_time_seconds` is identical either side, so it is a true delta and not a reset artifact. This answers the question `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` recorded as unanswerable ("no before-reading was taken, so the 24 is an absolute value and not a delta"); that record is updated in the same change as this one.
- **THE JOIN IS PROVEN — 2026-08-27, against the live venue, engine disarmed.** The owner placed one post-only limit outside the engine on `ETH/EUR`; `unmatched` moved **0 → 1** and then **1 → 2**. The counter carries only a `disposition` label, so it cannot say WHICH events those were — the executor's own log line can, and does (`zcrypto.engine.executor`, shipped to Loki; at 15:56:24Z and 16:00:25Z, quoted verbatim):

  ```
  external order event ignored: OrderInitialized for OHJWB7-SO3K2-7F2NSN on ETH/EUR.KRAKEN -- no ledgered adopted row
  external order event ignored: OrderCanceled for OHJWB7-SO3K2-7F2NSN on ETH/EUR.KRAKEN -- no ledgered adopted row
  ```

  Same `client_order_id` both times, so the second increment is that order's own terminal and not an unrelated event — publish → observer → counted → dropped holds for a lifecycle event and for a terminal. Note the first is `OrderInitialized`, not an acceptance: what reaches the observer is the reconciled order's initialization, and no `OrderAccepted` arrived at all.

  **Controls, and which of them actually discriminate.** `process_start_time_seconds` was unchanged throughout, so no counter reset could be read as a result, and `up{job="engine_app",host="zcrypto"}` was 1, so a zero would have been a dead scrape rather than a measurement — that selector is host-scoped deliberately, since the secondary is scraped for the same job and reads 0 permanently. `matched` stayed 0, as expected for an order this ledger does not vouch for. **`zcrypto_exec_kill_tripped` 0 and the twelve `zcrypto_exec_position` series flat are consistent with a counted-and-dropped event but do NOT discriminate here**, and the distinction is worth keeping: `_trip_on_fill` is entered only for `OrderFilled` and `set_position` is written only by `_publish_fill`, so on an order that never filled neither could have moved under any hypothesis. They are a degenerate control, not evidence. Whether an external fill the ledger does not vouch for reaches neither was answered separately, on 2026-08-26: the attended pass's BTC/EUR market orders produced two `OrderFilled` events classified `unmatched`, and `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` item 5 records the kill switch and all twelve position series at 0 read after them.

  Spec `00100` D2 stands as designed and the Cache-polling fallback is not needed; recorded in `docs/research/14.phase6-decisions.md` as `[iter-147]`.
- **One count corrected against the prediction rather than smoothed over:** the attended probe pass averaged ~2 events per order, so ~2 was expected here at placement; a resting order that never fills produced **1**, and the second arrived only at cancel. The per-order event count depends on the order's lifecycle, not on the observer.
- **The unmatched-external alert: DECIDED, no rule.** The baseline this item waited on exists (0), so the question was live and was answered on its merits rather than left open. The candidate design on file — `unmatched` rising while `zcrypto_exec_armed` is 0 — is unsound, and the fault is the sensor, not the framing. `zcrypto_exec_armed` is published only when the gate is evaluated, which while disarmed is at engine start and each 4-hourly cycle, so it is a 4-hourly snapshot stale in both directions: for ~4 h after arming it still reads 0 and the rule pages on the owner's own attended work, and for ~4 h after disarming it still reads 1 and the rule is mute through the highest-risk hour. It would have paged on the 2026-08-27 delivery-leg proof above, and from rung 1 onward every disarmed converge is a candidate page. Visibility is untouched — panel 61 of the engine dashboard plots both dispositions, and the standard is rule ⇒ panel, never the converse — so what is declined is paging, not watching. The reasoning, and the one change that would make a rule viable (publishing `zcrypto_exec_armed` at an attendance cadence rather than at gate evaluation), are recorded where the next reader will meet them: the `NOT_A_FAULT_SIGNAL` entry in `tests/test_infra_alert_rules.py`, beside the sibling metric that carries the same deliberate no-rule disposition.
