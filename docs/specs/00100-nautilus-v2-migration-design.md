# 00100 — nautilus-trader v2: the lift-and-shift, and the two things it forces us to redesign

The engine is pinned at `nautilus-trader==1.231.0`. v1 enters maintenance after one or two more minor releases, so every property proved against it is proved against a component on its way out. This migration moves the engine to 2.x before sleeve funding at probe scale, so that what RUNG 1 validates is what RUNG 2 will run. Sunk cost in v1-shaped work is not an input: where a v1 decision exists only because of a v1 limitation, it is re-decided on its merits, not ported.

The lift-and-shift is the deliverable. Adopting v2 capabilities is secondary and admitted only where the swap is trivial and removes real complexity.

## The measured basis

Every fact below was read off a running v2 wheel or the v2 source at a named ref, not from release notes. The development target is the pinned wheel `2.0.0rc4.dev20260824+17843`, cp314 manylinux, from `https://packages.nautechsystems.io/simple`.

**The adapter survives, and so does spot-margin.** `nautilus_trader.adapters.kraken` exists in the shipped wheel, Kraken is rated `stable`, and a `LiveNode` was built with a Kraken spot data client plus a spot exec client in `AccountType.MARGIN` — `Registered DataClient-KRAKEN`, `Registered ExecutionClient-KRAKEN`, `Built successfully`. `spot_account_type`, `margin_balance_asset` and `spot_positions_quote_currency` all survive with identical names.

**Our five imported symbols, and what they became.** The `.config` / `.constants` / `.factories` submodules are gone; everything is flat under `nautilus_trader.adapters.kraken`.

| v1.231.0 | pinned develop wheel |
|---|---|
| `KrakenDataClientConfig` | `KrakenDataClientConfig` (module moved) |
| `KrakenExecClientConfig` | **`KrakenExecutionClientConfig`** |
| `KRAKEN` | `KRAKEN` (module moved) |
| `KrakenLiveDataClientFactory` | **`KrakenDataClientFactory`** |
| `KrakenLiveExecClientFactory` | **`KrakenExecutionClientFactory`** |

Only `KRAKEN` held still across rc3 → nightly → develop. `trader_id` was a required argument in rc3 and in the 08-23 nightly, and is **removed** on the pinned wheel — sourced from the node instead, leaving `account_id`, `api_key`, `api_secret`.

**`msgbus` is gone, and the obvious ports are worse than absent.** A live `Strategy` has no `msgbus` attribute. The Python `MessageBus` class imports and its `subscribe` runs without error, but a Python handler can only ever receive what Python itself published: `PyCallableHandler::handle` downcasts to `PyMessage` and drops anything else with one `ERROR` per message. Measured — a handler subscribed to `snapshots.position.*` was invoked 133 times by Rust and rejected every one. No topic, router or config reaches Rust-native order events. Separately, `MessageBus.__init__` registers itself globally, *replacing any existing bus*: constructing one inside a running engine leaves orders frozen at `INITIALIZED` with no events anywhere. It logs `no registered endpoint 'RiskEngine.queue_execute'` and raises nothing.

**`Strategy.on_order_event` is unaffected** — a direct Rust→Python handler call, not a bus subscription. Measured: 6 hits where the bus handler got 0.

**Handler renames are silent.** `on_quote_tick` no longer exists; the handler is `on_quote`. Python does not complain about a subclass method the framework never calls, and every test drives our handler directly through stubs, so the whole suite stays green while production sees no quotes.

**What did not move.** All six enums we use (`LiquiditySide`, `OrderSide`, `OrderStatus`, `TimeInForce`, `AccountType`, `OrderType`) are identical in member names *and* integer values, so nothing we persist or compare shifts. `LiveExecEngineConfig` is identical across all 33 shared fields, including `reconciliation=True` and `filter_unclaimed_external_orders=False`. `Money`/`Price`/`Quantity` constructors round identically, and the Cache still refuses `str` arguments.

**What moved quietly.** `use_ws_trade` defaults **True**, flipping order submission from REST to WebSocket. `instrument_provider` is rejected outright — the adapter owns instrument loading. `Instrument.make_price` diverges from v1 on 6 of 12 decimal-midpoint probes (v1 rounds the binary float; v2 rounds the exact decimal half-to-even), and `make_qty` raises `value rounded to zero` where v1 returned a quantity.

**Reconciliation identifies external orders differently.** v2 takes `ClientOrderId::from(venue_order_id)` — the Kraken txid — where 00098's basis records a minted UUID4. The id is now *stable across restarts*. 00098's scope property survives, but its stated reason does not.

**Claiming is worse than 00098 D1 judged.** Claimed orders and fills "use the claiming strategy ID and have no external/reconciliation tag" — claiming does not merely weaken the scope property, it erases the evidence any in-code predicate would need to recover it.

**`DataActor` cannot substitute for a strategy here.** It carries `cache` and `clock` and has no order-submission surface at all — and no `on_order_event`. There is no route in v2 to event-driven order observation without order-submission powers.

## Decisions

### D1 — develop against the pinned development wheel; deploy only on a stable release

Development targets an exact pinned wheel, bumped deliberately, never a floating "latest". rc3 is already superseded in our own dependency surface — `KrakenExecClientConfig` → `KrakenExecutionClientConfig` and the `trader_id` removal both landed after it — so code written against rc3 would be wrong twice before it shipped.

**The pin flips early, not last.** The suite resolves against `pyproject.toml`, so there is no state in which it is green on v2 while the project is pinned to v1 — the suite is this migration's proof, and it can only prove the version it actually runs against. What lands *before* the flip is exactly the work that must be proved on v1 to mean anything: D4's handler guard, which is worthless unless it is seen to pass on v1 and fail on v2; D6, which fixes a defect v1 has today; and D8's pinning test, which must capture the live tag before a second strategy can move it. The flip is then a single commit — pin plus lock — and the branch is **red** from it until the migration completes. That is the expected state of a migration branch, not a failure, and it costs no CI noise: `coverage.yml` triggers on `pull_request` only, and the PR opens at component completion.

Deployment waits for a stable release. Upstream states plainly that development wheels are not recommended for production with real capital, and the engine arms into real capital at RUNG 1. Probe scale is not treated as production for the purpose of *running* a dev wheel, but the deployable pin is still a release.

### D2 — a second `Strategy` registered as `StrategyId("EXTERNAL")`, with its order surface sealed

This supersedes 00098 D1's mechanism. D1 bought two properties — observability of a matched adopted order's events, and scope, meaning an operator's hand settle reaches no trip, no row and no cancel. `msgbus` delivered both; it no longer exists.

Unclaimed external orders are stamped `StrategyId::external()` and published on `events.order.{strategy_id}` — the same topic string as v1 — and `StrategyId` explicitly exempts `"EXTERNAL"` from its hyphen rule. A strategy registered under that id receives those events on its own `on_order_event`, claims nothing (`external_order_claims` stays unset), and cannot see the main strategy's topic. Both properties are preserved by the original mechanism.

The cost is real and is bought down rather than accepted: a `Strategy` carries submit/cancel/modify/close powers, and for one registered as `EXTERNAL` every scoping default points those powers **at the operator's book** — `cancel_all_orders(strategy_only=True)` scopes to `EXTERNAL`, which is the operator's orders. The observer therefore overrides every order-submitting method to raise, and a test asserts each one raises. The barrier is explicit and tested rather than structural; `DataActor`, which would have been structural, cannot receive order events at all.

Scope is preserved by a stronger property than 00098 argued. The guarantee rests on **key-space disjointness**: `_attached` acquires keys only from orders this engine's factory built and rows this engine's ledger wrote, so an operator's order can never match — regardless of what nautilus does with topics or population.

### D3 — never construct a `MessageBus`

Named as a prohibition because it is the obvious repair for the dead `msgbus.subscribe` port and its failure is indistinguishable from the strategy doing nothing: orders frozen at `INITIALIZED`, no events, no exception. It is the constructor alone that does this; the class may be imported. On the live trade path this is a submitted order that never leaves and a kill trip that never runs.

### D4 — the interface we depend on is pinned exhaustively, and handler names structurally

`on_quote_tick` → `on_quote` is invisible to Python and to a stub-driven suite. The handler guard is therefore general rather than quote-specific: **every handler our strategies override must exist on the library's `Strategy` base class**. Written against v1 it passes; it fails loudly on v2 for each renamed handler. It lands before the migration it guards, and is seen to bite on both layouts.

That guard is one case of a wider need. The pin moves daily and upstream is reshaping our exact surface — `KrakenExecClientConfig` → `KrakenExecutionClientConfig` and the `trader_id` removal both landed inside four days — so the question "what changed under us on this bump?" is asked continuously, and answering it by reading release notes does not scale.

Our whole dependency is **twenty distinct symbols**. That is small enough to pin exhaustively rather than sample: every symbol we import exists at the path we import it from; every constructor we call still accepts the arguments we pass; every default we rely on still holds (`filter_unclaimed_external_orders`, `use_ws_trade`, the `LiveExecEngineConfig` fields); and every enum member we persist or compare keeps its name **and** integer value. One test file, run on every bump, naming exactly what moved.

Pinning the surface we use is deliberately preferred over adopting more of the library to widen coverage. Adopting does not deepen coverage of what we depend on; it enlarges what we depend on, and each addition is another thing a nightly can break. The pin gives complete coverage of the real surface at no added footprint.

### D5 — instrument loading moves to the adapter, and the start guard must still hold

`instrument_provider=InstrumentProviderConfig(load_all=True)` is rejected on both clients; v2's Kraken adapter loads its own universe. `venue_state_from_cache` raises when any of the twelve `INSTRUMENT_IDS` is absent from the Cache, so what previously guaranteed their presence before the first cycle no longer exists in that form. The replacement must be established by measurement against a running v2 node, not by reading configuration.

### D6 — the post-terminal reconciliation is scoped to this engine's own position

Landed ahead of the migration, because the defect exists on v1 today. `_reconcile_terminal` read the whole instrument position, so an operator hand settle mid-intent latched the kill switch — contradicting 00098 D1's scope property on a path D1 never covered, since D1 addressed the event topic and this is the position read. Both ends are now scoped to this engine's strategy; NETTING position ids are `f"{instrument_id}-{strategy_id}"`, so an external fill lands in a separate position and is excluded by construction.

The two reads are deliberately **not** simultaneous, and need not be: nothing compares the two baselines to each other, an own-strategy fill arriving between them lands on the baseline *and* persists into the terminal read so it cancels, and an external one is excluded from both.

The narrowing this accepts: activity not stamped with our strategy id — a leaked key, another bot — no longer latches the kill switch, because nautilus attributes it identically to a sanctioned hand settle. That is inherent to 00098 D1's semantics, not chosen here. The kill switch is also the wrong instrument for it: it stops our engine, not an intruder. See D9.

### D7 — telemetry stays instrument-scoped, deliberately

`zcrypto_exec_position` and `zcrypto_exec_realized_pnl_eur` keep reading the whole instrument, and the asymmetry with D6 is recorded in the code so it is not "aligned" later.

Scoping the position gauge to our strategy would be actively worse: when the operator settles our leg their sell fills under `EXTERNAL`, so our position stays open and the gauge would report a holding the account does not have. Instrument-scoped matches the gauge's own stated meaning. For realized PnL, a hand settle of an engine leg realizes an outcome that is genuinely the engine's, so strategy-scoping would systematically undercount exactly the sanctioned case 00098 exists for. Telemetry answers *what is on the account*; D6 answers *did my own orders do what I think*. Different questions, different scopes.

### D8 — strategy identity is pinned explicitly, never positional

`order_id_tag` is assigned positionally for tag-less strategies (`f"{len(order_id_tags):03d}"`), and `ShadowStrategy` passes no `StrategyConfig`. Registering D2's observer therefore makes the main strategy's client-order-id prefix — a venue-visible identifier — depend on registration order, silently. Both strategies get an explicit id and tag, and a test pins the main strategy's so a reordering cannot move it.

The current live value is read from a real client order id before being pinned, never derived: pinning a wrong value changes every future order id.

Passing a `StrategyConfig` does not breach the standing ban on `external_order_claims`, which is a ban on the token and on a non-`None` value; leaving it unset satisfies both. The ban and the claims assertion are extended to cover the observer.

### D9 — the unmatched-external alert is owed at arming, not before

`zcrypto_exec_external_events_total{disposition="unmatched"}` already carries the right meaning — its help text names both the operator's hand settle and unsanctioned activity — and nothing watches it. It is the correct detection channel for what D6 stops catching.

The rule is pushed only after the metric's first record. The counter has never moved (no journaled fills), and a rule pushed before its metric exists pages a spurious no-data alert. The obligation lands on the arming checklist, where the first sample appears.

### D10 — the submission transport is pinned to REST, so the classification stays derived

`use_ws_trade` defaults True, so submission would move from REST to WS. `_KRAKEN_ERROR_MARKERS` and the three-way verdict in `_on_rejected` are REST-shaped, and a rejection that no longer matches classifies as ambiguous, which stops the plan and leaves an open row.

**We pin `use_ws_trade=False`.** The REST classification is the one this project derived against a real venue; re-deriving it for WS needs live submissions, which this migration cannot reach any more than it can reach D2's delivery leg. Migrating the transport and the library together would also conflate two failure sources on the live trade path. The transport is set explicitly rather than inherited, and adopting WS becomes its own change with its own evidence.

### D11 — the arming record is reconciled with a moving pin before the arming pass

`cli/engine/order-semantics-verified.json` records `verified_nautilus_versions`, and both arming guards do exact string membership. On a pin that bumps daily, any bump after the attended probe pass silently disarms the engine. The guards are correct; the sequencing is what must change — the arming pass comes after the pin stops moving, and the record's granularity is decided before that pass, not discovered at it.

### D13 — the exec credentials become ours to hold, and must never leave a variable

v1's `KrakenExecClientConfig()` took no arguments: the adapter sourced `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` from the environment itself, so our code never touched the trade key and a keyless local construction worked by default. v2 requires `account_id`, `api_key` and `api_secret` as explicit arguments — measured: constructing without them raises `TypeError: missing 3 required positional arguments`.

We read the same environment variables, already rendered onto the host, and pass them explicitly. No new plumbing and no second home for the secret.

What changes is blast radius, and that is what this decision exists to bound. The trade key now lives in a Python variable on the live trade path, so it can reach a traceback, a repr, a log line or an exception message in ways it never could while the adapter held it. It is therefore never interpolated into any message, and the config object carrying it is never logged or included in error text. Keyless local construction survives as a **data-only node**: with no credentials in the environment the exec client is not wired at all. That is what keyless already meant — the key is IP-bound to the engine host, so a local run observes and never trades. If execution is explicitly enabled and the environment is empty, construction **refuses loudly**. Placeholder credentials are never substituted: a node that looks armed and is not is worse than a refusal, because the failure surfaces at first submission instead of at construction.

### D12 — the surfaces that move together

The image is shared: one `Dockerfile`, one `uv.lock`, one image repo. A nautilus pin change rebuilds capture, engine, ops and NAS. The NAS runs `-compat` builds only. A `uv.lock` change reaches every test, so the full suite is owed rather than the diff's reachable subset.

## Verification

The migration is not proved by a green suite. These are the ways it can be green and wrong, each owed an explicit check:

- **Quote starvation** — every test drives our handler directly, so a renamed handler leaves 100% of them green while production sees no quotes. D4's guard is the check; it must be seen to fail on v2 before the rename is applied.
- **Swallowed subscription** — `subscribe_quote_ticks` becoming an `AttributeError` is caught by a blanket `except` that drops the plan with no gate reason and no kill file. Assert on the subscription's effect, not on the absence of an exception.
- **The always-truthy watchdog** — `is_running` changes from property to method, so `if strategy.is_running:` on a bound method is permanently true. The supervision watchdog must be proved to fire, not merely to compile.
- **Rounding** — `make_price` diverges on decimal midpoints and `make_qty` gains a raise outside the only `try` that wraps sizing. Both need fixtures on the divergent values, not on round numbers.
- **The arming record** — proved by a refusal: a version not in the record must refuse to arm.
- **D2's delivery leg** — the publish leg is established from source and the delivery leg by experiment, but not yet joined on a genuine venue-sourced external order, which needs live reconciliation. Verified on the disarmed engine before it is relied on.

## Out of scope

- **Adopting v2 capabilities beyond the forced changes**, rejected on measurement rather than caution. `_liquidity`'s survival guard is deleted because `liquidity_side_to_str` no longer exists and `LiquiditySide` is a plain enum with `.name` — forced, and it happens to remove complexity. The rest would import defects: the v2 Kraken parser never reads Kraken's `costmin` field at all, so the risk engine does not subsume `COSTMIN` and deleting it would remove a live-trade-path guard with nothing behind it; `TradingState` reachability *regresses* (`set_trading_state` is exposed in v1 and not in v2); and native execution algorithms exist only on `BacktestEngine`, not on the live node. D4's interface pin — not a wider adoption surface — is how upstream drift gets caught.
- **`CommandFailure`** — not reachable. It is a Rust-internal type with no Python binding, so there is nothing to adopt. The reachable rejection events give D10 less than v1 did, not more: `OrderRejected` and `OrderDenied` still carry only a string `reason`, and both lost `venue_order_id`. The one genuine improvement — canonical reason codes in place of free-form prose — arrives with no code from us.
- **The engine converge onto 1.231.0**, cancelled: it would prove properties of a component entering maintenance.
