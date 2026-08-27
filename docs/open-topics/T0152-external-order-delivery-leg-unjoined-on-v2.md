---
status: partial
ripe_when: "RIPE NOW — the trigger fired at the 2026-08-26 16:40:20Z v2 converge. The remainder needs one order placed outside the engine, on the account, while the engine runs disarmed; only the account owner can place it"
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

**One of the two sub-items is measured; the join is not.** Everything below was read on 2026-08-27 from the metric's own history via `infra/scripts/grafana-query.py` with PromQL `offset`, cross-checked against `process_start_time_seconds{job="engine_app"}` at every point so a counter reset is never mistaken for a delta. No host was touched.

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
- **What none of it proves: the join.** The v2 counter has read 0 for 22.1 h, but no order is known to have existed outside the engine in that window, so the 0 is uninformative by construction — exactly the silent-failure shape this topic exists to catch. The delivery leg remains unverified on v2.

## Suggested next steps

- **The join, and only the owner can run it.** With the engine **disarmed**, place one order outside the engine on a basket symbol, then read `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_external_events_total{host="zcrypto"}'`. `unmatched` incrementing is the pass — that is the expected disposition for an order this engine's ledger does not vouch for. A counter still at 0 **with a known external order in the window** is the refutation; a 0 with no such order proves nothing, because both label sets are registered eagerly (`## Findings so far`). It need not cost anything: a resting post-only limit far from the market is free until filled (`docs/reference/kraken-fee-schedule.md`), and reconciliation stamps unclaimed **open** orders, not only fills — so placing one and cancelling it should be enough. That last point is itself unverified and is part of what the run measures: if an open-but-unfilled order does not move the counter, retry with a fill before concluding the leg is refuted.
- **Then dispose of what it shows, in the same change.** A pass: record it in the phase-6 decisions log — a silent pass leaves the next reader unable to tell a verified join from an unrun check. A refutation: switch D2 to the Cache-polling fallback on the executor's existing 5 s tick (`_TICK_SECONDS`). Note the fallback is real work, not a rider: `00098` D7's adopted-row sweep runs on that tick **once at startup** — `_adopted` is a one-shot latch — so a recurring Cache poll is new behaviour to build and guard, not an existing loop to hook.
- **Author AND push the unmatched-external alert — the baseline it waited on now exists (0).** Both halves belong to this item: authoring in `infra/grafana/alerts.yaml` is ordinary work, the push is owner-worded, and an authored-but-unpushed rule protects nothing — so this item is not drained until a rule is live. The one constraint the baseline hands it: the threshold cannot simply be *any increase above 0*, because from rung 1 onward the owner's own hand-placed settling orders are external by construction and would page on legitimate activity. The rule must key on something that separates them, or be scoped to windows where no attended probe is open. Push only after the metric has a record — it has had one since 2026-08-23, so that gate is already satisfied — and note that `grafana-push.sh` upserts and never deletes, so a wrong threshold is a prune to undo, not an edit. The 0 is a flat-account baseline; the reading owed at the first disarmed boot carrying live orders lives on `infra/runbooks/engine.md`'s pre-probe step 4, beside it.
