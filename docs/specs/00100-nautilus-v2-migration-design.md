# 00100 — nautilus-trader v2: the lift-and-shift, and the two things it forces us to redesign

The engine is pinned at `nautilus-trader==1.231.0`. v1 enters maintenance after one or two more minor releases, so every property proved against it is proved against a component on its way out. This migration moves the engine to 2.x before sleeve funding at probe scale, so that what RUNG 1 validates is what RUNG 2 will run. Sunk cost in v1-shaped work is not an input: where a v1 decision exists only because of a v1 limitation, it is re-decided on its merits, not ported.

The lift-and-shift is the deliverable. Adopting v2 capabilities is secondary and admitted only where the swap is trivial and removes real complexity.

## The governing principle

**We do not create legacy at version 0.0.0.** Where v2 offers a better way to meet a requirement, take it — regardless of how much was invested in the v1 form. Effort already spent is not an argument, and a v1 shape preserved inside v2 becomes a maintenance rabbit hole the moment v2 evolves again.

The test for every decision here is therefore not "does it work" and not "is it a faithful port". It is: **if we had only the functional requirement and no v1 code, what would we build on v2?** Build that.

This governs everything nautilus, the external-order observer included. Two things it does NOT license: weakening a guard on the live trade path, and adopting a v2 feature because its name resembles something we hand-rolled — the reason to adopt is that it expresses the requirement better, established by measurement.

The lift-and-shift framing below is the deliverable's SHAPE, not a licence to port v1 idiom. Where the two conflict, this principle wins.

## The measured basis

Every fact below was read off a running v2 wheel or the v2 source at a named ref, not from release notes. The development target is the pinned **nightly** wheel `2.0.0rc4.dev20260825`, cp314 manylinux, from `https://packages.nautechsystems.io/simple`. Nightly rather than the per-run `develop` builds: it is the channel that also publishes ARM64, and its naming is stable enough to bump against daily. Verified identical to the same day's develop build across every symbol, default and method surface this project touches — the version string is the only difference.

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

### D1 — develop against the pinned development wheel, and deploy on it at probe scale

Development targets an exact pinned wheel, bumped deliberately, never a floating "latest". rc3 is already superseded in our own dependency surface — `KrakenExecClientConfig` → `KrakenExecutionClientConfig` and the `trader_id` removal both landed after it — so code written against rc3 would be wrong twice before it shipped.

**The pin flips early, not last.** The suite resolves against `pyproject.toml`, so there is no state in which it is green on v2 while the project is pinned to v1 — the suite is this migration's proof, and it can only prove the version it actually runs against. What lands *before* the flip is exactly the work that must be proved on v1 to mean anything: D4's handler guard, which is worthless unless it is seen to pass on v1 and fail on v2; D6, which fixes a defect v1 has today; and D8's pinning test, which must capture the live tag before a second strategy can move it. The flip is then a single commit — pin plus lock — and the branch is **red** from it until the migration completes. That is the expected state of a migration branch, not a failure, and it costs no CI noise: `coverage.yml` triggers on `pull_request` only, and the PR opens at component completion.

**Amended, on the owner's ruling: the deployable pin is the pinned nightly, not a release.** The original ruling was that deployment waits for a stable release — upstream states plainly that development wheels are not recommended for production with real capital, and the engine arms into real capital at RUNG 1. That ruling is reversed for the same reason it already exempted *running* a dev wheel: RUNG 1 is probe scale, and probe scale is not production. Holding the deploy for a 2.0.0 that is not published would park a finished migration behind an external clock nobody here controls, while the engine keeps trading on a version entering maintenance — the exact exposure this migration exists to end.

What is accepted rather than argued away: upstream's recommendation stands, and we are deploying against it at a scale where the loss is bounded by the probe's own sizing. The compensating controls are the ones already built — the attended order-semantics pass binds to one exact version string, both arming guards refuse any version absent from the record, and the ladder's per-order and per-run notional ceilings bound what a defect can spend. When a stable 2.0.0 does publish, moving to it is a fresh bump owing its own attended pass; it is not automatic, and D11's freeze rule (below) is what makes that deliberate rather than silent.

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

Measured stronger than assumed: registration REFUSES a colliding explicit tag (`RuntimeError: Strategy order_id_tag conflict for '000'`) rather than silently shifting it, and re-derives `strategy_id` from the config at registration. So the prefix is either the pinned value or startup fails loudly — the silent-shift case the pin was written against cannot occur once the tag is explicit. The pin stays: it is what makes the tag explicit.

Passing a `StrategyConfig` does not breach the standing ban on `external_order_claims`, which is a ban on the token and on a non-`None` value; leaving it unset satisfies both. The ban and the claims assertion are extended to cover the observer.

### D9 — the unmatched-external alert is owed at arming, not before

`zcrypto_exec_external_events_total{disposition="unmatched"}` already carries the right meaning — its help text names both the operator's hand settle and unsanctioned activity — and nothing watches it. It is the correct detection channel for what D6 stops catching.

The rule is pushed only after the metric's first record. The counter has never moved (no journaled fills), and a rule pushed before its metric exists pages a spurious no-data alert. The obligation lands on the arming checklist, where the first sample appears.

### D10 — the submission transport is pinned to REST, so the classification stays derived

`use_ws_trade` defaults True, so submission would move from REST to WS. `_KRAKEN_ERROR_MARKERS` and the three-way verdict in `_on_rejected` are REST-shaped, and a rejection that no longer matches classifies as ambiguous, which stops the plan and leaves an open row.

**We pin `use_ws_trade=False`.** The REST classification is the one this project derived against a real venue; re-deriving it for WS needs live submissions, which this migration cannot reach any more than it can reach D2's delivery leg. Migrating the transport and the library together would also conflate two failure sources on the live trade path. The transport is set explicitly rather than inherited, and adopting WS becomes its own change with its own evidence.

### D11 — the arming record is reconciled with a moving pin before the arming pass

`cli/engine/order-semantics-verified.json` records `verified_nautilus_versions`, and both arming guards do exact string membership. On a pin that bumps daily, any bump after the attended probe pass kills the path forward, and nothing warns at the moment of the bump: a running container is untouched, so an engine already armed keeps trading, but the armed converge is refused from that tree and the gate refuses once an image built from it deploys. The refusal arrives at the arming step, which is the worst moment to meet it. The guards are correct; the sequencing is what must change — the arming pass comes after the pin stops moving, and the record's granularity is decided before that pass, not discovered at it.

### D12 — the surfaces that move together

The image is shared: one `Dockerfile`, one `uv.lock`, one image repo. A nautilus pin change rebuilds capture, engine, ops and NAS. The NAS runs `-compat` builds only. A `uv.lock` change reaches every test, so the full suite is owed rather than the diff's reachable subset.

## Verification

The migration is not proved by a green suite. These are the ways it can be green and wrong, each owed an explicit check:

- **Quote starvation** — every test drives our handler directly, so a renamed handler leaves 100% of them green while production sees no quotes. D4's guard is the check; it must be seen to fail on v2 before the rename is applied.
- **Swallowed subscription** — `subscribe_quote_ticks` becoming an `AttributeError` is caught by a blanket `except` that drops the plan with no gate reason and no kill file. Assert on the subscription's effect, not on the absence of an exception.
- **The always-truthy health read** — `Strategy.is_running` changes from property to method, so `if strategy.is_running:` on a bound method is permanently true. `LiveNode.is_running` remains a property, so the trap is real for one object and not the other. Discharged by D14: no engine-side code reads either, so the trap has no surface left here.
- **A held `Order` is a dead snapshot.** `submit_order` copies the order into the Cache and the engine applies every subsequent event to the CACHE's copy; the object the caller kept stays at `INITIALIZED` forever. Measured: after `OrderDenied` had already reached `on_order_event`, the held object still read `status=INITIALIZED, filled_qty=0.0, is_closed=False` while `cache.order(coid)` read `DENIED`. Every read of an order's live state must go through `cache.order(client_order_id)`. This is silent in the worst direction — code that classifies `INITIALIZED` as "never submitted" reports a clean bill while real orders rest at the venue.
- **The unsendable node AND strategy** — both `LiveNode` and `Strategy` are pyo3-unsendable: any attribute read from a thread other than the one that built them aborts the process with SIGABRT, uncatchable. Measured, both exit 134. Nothing in `engine run` reads either off-thread (D14), so what remains is diagnosability — the abort is silent unless faulthandler is armed, which is why `run()` arms it before `node.run()`. Because the strategy is unsendable too, a driver that submits orders cannot run on a second thread while `run()` owns the first — which is what blocks the probe harness.
- **Rounding** — `make_price` diverges on decimal midpoints and `make_qty` gains a raise outside the only `try` that wraps sizing. Both need fixtures on the divergent values, not on round numbers.
- **The arming record** — proved by a refusal: a version not in the record must refuse to arm.
- **D2's delivery leg** — the publish leg is established from source and the delivery leg by experiment, but not yet joined on a genuine venue-sourced external order, which needs live reconciliation. Verified on the disarmed engine before it is relied on.
- **Events the engine manufactures rather than receives** — the in-flight machinery and `generate_missing_orders` are default-ON and synthesize terminal events (and whole orders) marked only by a `reconciliation` bool, so an unanswered cancel could drive a fallback on an ack no venue gave. Ruled on in D15: the flag is read on both order-event surfaces, minted terminals take the ambiguous exit on this engine's own orders and write no venue outcome on adopted ones, reconciled fills keep their record, and every direction is proven by mutation. What remains is the rate at which the machinery fires, which no test can reach — it needs a live exec client, and the reading is a step in the engine runbook's pre-probe checklist.

## Out of scope

- **Adopting v2 capabilities beyond the forced changes**, rejected on measurement rather than caution. `_liquidity`'s survival guard is deleted because `liquidity_side_to_str` no longer exists and `LiquiditySide` is a plain enum with `.name` — forced, and it happens to remove complexity. The rest would import defects: the v2 Kraken parser never reads Kraken's `costmin` field at all, so the risk engine does not subsume `COSTMIN` and deleting it would remove a live-trade-path guard with nothing behind it; `TradingState` reachability *regresses* (`set_trading_state` is exposed in v1 and not in v2); and native execution algorithms are refused on a structural ground, not a reachability one -- `LiveNode.add_exec_algorithm` and `add_exec_algorithm_from_config` both exist (only `add_native_exec_algorithm` is absent), so the machinery IS reachable and is still wrong here: an algorithm's spawned children submit through the algorithm's own surface, which runs neither the arm/kill/venue-status gate that `_submit` TAKES immediately before every venue call nor the ledger write that PRECEDES it. A spawned child could reach Kraken with the kill file set and no row behind it. That reason does not expire with a version. D4's interface pin — not a wider adoption surface — is how upstream drift gets caught.
- **`CommandFailure`** — not reachable. It is a Rust-internal type with no Python binding, so there is nothing to adopt. The reachable rejection events give D10 less than v1 did, not more: `OrderRejected` and `OrderDenied` still carry only a string `reason`, and both lost `venue_order_id`. The one genuine improvement — canonical reason codes in place of free-form prose — arrives with no code from us.
- **The engine converge onto 1.231.0**, cancelled: it would prove properties of a component entering maintenance.

### D13 — the exec credentials become ours to hold, and must never leave a variable

v1's `KrakenExecClientConfig()` took no arguments: the adapter sourced `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` from the environment itself, so our code never touched the trade key and a keyless local construction worked by default. v2 requires `account_id`, `api_key` and `api_secret` as explicit arguments — measured: constructing without them raises `TypeError: missing 3 required positional arguments`.

We read the same environment variables, already rendered onto the host, and pass them explicitly. No new plumbing and no second home for the secret.

What changes is blast radius, and that is what this decision exists to bound. The trade key now lives in a Python variable on the live trade path, so it can reach a traceback, a repr, a log line or an exception message in ways it never could while the adapter held it. It is therefore never interpolated into any message, and the config object carrying it is never logged or included in error text. Keyless local construction survives as a **data-only node**: with no credentials in the environment the exec client is not wired at all. That is what keyless already meant — the key is IP-bound to the engine host, so a local run observes and never trades. If execution is explicitly enabled and the environment is empty, construction **refuses loudly**. Placeholder credentials are never substituted: a node that looks armed and is not is worse than a refusal, because the failure surfaces at first submission instead of at construction.

### D14 — supervision is the node's own; `engine run` adds none

The requirement: a node that never finishes starting — the exec client never connects, startup reconciliation never completes — must fail loudly into the supervisor's restart rather than sit as a live-looking zombie burning ratified gate days.

The node already meets it, measured on the pinned wheel with no network and no credentials. A `LiveNode` whose data client is pointed at a closed loopback port logs `Data client connection timed out, aborting startup`, disconnects, stops, and `run()` raises `RuntimeError: data-connect timeout` at `NodeState.STOPPED`. The same with a reconciliation budget it cannot meet: `Startup reconciliation failed, aborting startup`, then `RuntimeError: Startup reconciliation timeout reached`. Every phase of the abort path is itself bounded by a `LiveNodeConfig` timeout — connection 60 s, portfolio 10 s, reconciliation 30 s, disconnection 10 s, shutdown 5 s.

So `engine run` starts the node and lets the raise escape. `cli/__main__.py` logs it at ERROR, which the `Engine · ERROR logs` rule reads, and exits 1; compose's `restart: unless-stopped` is the recovery.

**A watchdog beside it would be a net loss, not a redundancy.** A timer that force-exits on a not-RUNNING read cannot fire on any of the conditions it names — the node aborts first, in every one of them — and the single state in which it *can* still fire is a node that reached RUNNING and began a graceful shutdown inside the window: a SIGTERM during a converge reads `SHUTTING_DOWN` 0.1 s later and stays there for the residual-event drain (10 s) plus disconnection (up to 10 s), measured. `os._exit(1)` there truncates that drain and the disconnect on the live trade path, and skips `logging.shutdown()`, discarding whatever the log-ship ring has not yet pushed. A hand-derived budget also mis-models the state machine: the path to RUNNING crosses three timeouts, not two.

**The one uncovered case is the abort machinery itself wedging** — `run()` neither returning nor raising, ever. Nothing is added for it: every phase it would have to wedge in carries its own library timeout, so the case is not reachable by any mechanism we can name, and a guard for it would be the same speculative supervision in a longer-sleeved form. `tests/test_engine_node.py` pins the abort by measurement, and its subprocess timeout is what a hang would fail.

### D15 — a terminal event the engine minted for itself is an unknown venue outcome, but a reconciled fill is a real one

Resolves [[T0154]]. The execution engine manufactures order events of its own and dispatches them to strategies exactly as it dispatches the venue's, distinguished only by a `reconciliation` bool the event carries. Nothing under `cli/` read that bool, so every synthesized event was handled as though the venue had said it.

Measured on `2.0.0rc4.dev20260825` and against upstream source at `a52de0f914770b635701ae8961994e0f9b9067db`. `LiveExecutionEngineConfig()` ships `inflight_check_interval_ms=2000`, `inflight_check_threshold_ms=5000`, `inflight_check_retries=5` and `generate_missing_orders=True`; `_exec_engine_config()` set only `reconciliation` and `filter_unclaimed_external_orders`, so all four defaults were live. Three routes reach this engine, and they do **not** fail alike:

- **The in-flight terminal.** An order sitting `SUBMITTED`, `PENDING_UPDATE` or `PENDING_CANCEL` past the threshold is first *queried* — `QueryOrder` to the venue, once per retry — and at the fifth retry `crates/live/src/execution/manager.rs::check_inflight_orders` mints a terminal instead: `OrderRejected` with reason `INFLIGHT_TIMEOUT` for a `SUBMITTED` order, `OrderCanceled` for one pending a modify or cancel. Neither is a statement about what the venue did; both are the engine giving up on waiting. The cancel landed in `_on_cancel_ack`, took the `cancel_requested` branch, wrote the row `canceled` and went on to `_fallback` / `_finish_revoked` — crossing with an IOC on an ack nobody at the venue confirmed, while the original may still be resting. **Double exposure on the live trade path.** The rejection landed safely, but by accident: `INFLIGHT_TIMEOUT` matches neither `_POST_ONLY_MARKER` nor `_KRAKEN_ERROR_MARKERS`, so it fell through to the ambiguous arm. One future entry in the marker list would have turned it into a resubmission with nothing red.
- **The synthesized position order.** `generate_missing_orders` licenses reconciliation to synthesize a whole missing order, with its fill, to make the cache's position agree with a venue position report. Such an order is stamped `StrategyId("EXTERNAL")`, so it arrives on the observer, matches no ledgered row, and is counted `unmatched` and dropped — already contained, and by D2/00098 D3 rather than by anything aimed at this.
- **The reconciled fill.** `crates/execution/src/reconciliation/ids.rs` mints a synthetic `S-{hex_ts}-{hash}` trade id, deterministic across restarts so the duplicate-fill sanitizer dedupes *replays*, but by construction never equal to the venue's real trade id. So `is_duplicate_fill` cannot join a synthesized fill to the venue's later real one; what stops the pair being applied twice is `check_overfill`, with `allow_overfills` defaulting `False`, which refuses the second and does not publish it.

**We read the flag, at the top of `_on_order_event` and above the name dispatch.** `OrderRejected`, `OrderCanceled` and `OrderExpired` carrying `reconciliation=True` route to `_strand_ambiguous`: the row goes to `ambiguous` (an open state, so re-attach still sees an order that may still rest), the intent is journaled `ambiguous`, and the plan halts. The executor's own stated reasoning for that arm — the order may be live at the venue, so no resubmission, no fallback, and the plan stops — is a precise description of a terminal the engine minted for itself, and it is exactly what `_ACK_WAIT` expiring already means. Placing the check above the dispatch is what makes the rejection route's accidental safety deliberate: a marker added to `_KRAKEN_ERROR_MARKERS` later is a statement about the venue's error text only, and cannot promote an in-flight timeout into a verdict.

**Both order-event surfaces read it, because the engine has two and they end differently.** An adopted order's events arrive on `events.order.EXTERNAL` (D2, 00098 D1), where there is no intent to strand — the row is what carries the outcome, and `_venue_terminal_state` decides it by reading the VENUE's own order rather than the event's class name. That read cannot tell a minted terminal from a venue one: the event is applied to the order before it is dispatched, so a minted `OrderCanceled` leaves the Cache's order `CANCELED` exactly as the venue's ack would. So the flag is read there too, ahead of the order read, and a minted terminal writes **no** row state at all — the shape `_venue_terminal_state` already produces for every open status. The event still appends as evidence, the entry stays in `_attached` for a fill that can still arrive, and the row stays in `_OPEN_ORDER_STATES`, which is what the next startup re-attaches from. Writing `canceled` there instead would put a venue claim in the ledger that nobody at the venue made, and close a row that never re-attaches again while the order may still be resting. Nothing on this surface reaches `_fallback`, `_reprice` or `_finish_revoked`, so the double-exposure arm the own surface has is absent here — the defect is the false ledger claim and the lost re-attach, not a second order. Being wrong in the other direction costs one row settled a restart later, when the startup sweep reconciles it against the order's own status; that asymmetry is why the conservative answer is the right one on both surfaces.

The routing keys on the **flag**, never on the mechanism that set it, and that is deliberate: the same config carries two sibling loops of the same shape — the open-order check (`open_check_*`) and the position check (`position_check_*`), each with its own retry budget — whose interval both default to `None` today. Whether that means they never schedule was not established, and it does not have to be: a terminal either carries `reconciliation=True` or it does not, so a route we have not enumerated is covered by construction. What their liveness would change is the *rate*, which is what the runbook reading below measures.

**Fills are excluded, deliberately, and that is the load-bearing half of this decision.** `OrderFilled` carries the same flag, but a reconciled fill is not an outcome the engine invented — it is the venue's own report transcribed late. Its quantity and price are the venue's; only the trade id is minted, *because the report carries none*. It is money that moved. Routing it to the ambiguous exit would skip the row's `add_filled_qty`, the in-process mirror and the published fill, dropping the record and the counter for a real fill — and no-fill-without-a-record has no exemption, so that would be a worse failure than the one the exit prevents. It would also make the next resubmission over-ask by exactly the dropped quantity, which is this same double exposure in the other direction.

**What covers a fill that did NOT happen is narrower than that reads, and the limit is stated rather than glossed.** Three things bound it, and D6's post-terminal reconciliation is **not** among them. `create_incremental_inferred_fill` tops an order up to the report's *cumulative* quantity and infers nothing unless `report_filled_qty > order_filled_qty`, so a stale or replayed report cannot over-report. `check_overfill` — `allow_overfills` measured `False` on the wheel and set nowhere under `cli/` — refuses an application past the order's own quantity. The executor's fill-time trips latch on anything past the quantity the row was submitted for. D6 cannot see a phantom at all: a reconciliation-minted fill is applied to the order and to the Cache before it is dispatched, so it moves `active.filled` and the strategy-scoped position that comparison holds it against by the same amount, and the check passes. A phantom *within* the remaining quantity, born of a venue misreport, is therefore past every client-side guard there is — said plainly here because crediting a check that cannot see it is how a gap acquires a guard's name.

**The three in-flight knobs are stated rather than inherited, at the values they already hold**, in the same idiom as D10's `use_ws_trade` and the data client's `product_type`. They are a **complement** to the routing and never a substitute — widening the wait makes the synthesis rare and cannot remove the case. No Kraken REST ack latency has been measured, so there is nothing to derive a different number from; what an explicit statement buys is that an upstream default flip cannot move the live trade path silently. The interface pin keeps reading the library's own defaults, so a bump that moved any of them tells us our stated values have stopped being restatements.

**Verification is the pair, not the halt.** A fixture built only from `reconciliation=True` events cannot tell a correct implementation from one that ignores the flag — and an implementation that halted on *every* cancel ack would pass it while breaking maker-first outright. So each routing test drives the same time-boxed intent to the same cancel and answers it with the same real library event class, differing only in the flag: the venue's ack fires the bounded IOC and leaves the plan runnable; the minted one submits nothing, writes the row `ambiguous` and refuses every later intent. The fill test asserts the opposite property — both flag values must read identically, down to the remainder the next IOC asks for, which is what a dropped credit would move. The adopted surface is proven on the same principle: one adopted row, one `OrderCanceled`, the venue's order left `CANCELED` in *both* arms — so the status cannot be what decides — and the row closes `canceled` and leaves the re-attach set on the venue's ack while staying `accepted` and inside it on the minted one. The `False` arm is the true positive there too, and not decoration: an implementation that simply stopped writing terminal states on that path would pass the minted arm and strand every venue-acked cancel as an open row forever. Both directions are proven by mutation: reading the flag as constant `False` (the defect) and as constant `True` (halt-on-everything) each fail, and on *opposite* assertions.

What is **not** settled here is the rate. The machinery cannot fire without a live exec client, so how often it fires is unmeasured rather than merely unread; the reading is owed on the first arming window for a version and lives as a step in the engine runbook's pre-probe checklist, beside the healthy-boot `unmatched` baseline it must be read against.
