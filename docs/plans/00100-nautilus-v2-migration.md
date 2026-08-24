# nautilus-trader v2 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the engine from `nautilus-trader==1.231.0` to 2.x, preserving every behaviour the live trade path depends on, and redesigning the two things v2 removes outright.

**Architecture:** Three phases, and their order is load-bearing. Phase A lands guards that are only meaningful while v1 is still installed — a guard written after the flip can never be seen to bite on the old layout. Phase B flips the pin in one commit; the branch is red from there. Phase C works it green, using the red suite as the work-list.

**Tech Stack:** Python 3.14, uv, pytest, nautilus-trader `2.0.0rc4.dev20260824` (cp314 manylinux) from `https://packages.nautechsystems.io/simple`.

Spec: `docs/specs/00100-nautilus-v2-migration-design.md`. Every `D<N>` below refers to its decisions.

## Global Constraints

- **Pinned wheel:** `nautilus-trader==2.0.0rc4.dev20260824`. Exact, never floating. Bumping it is a deliberate act that re-runs Task 1's pin.
- **The suite is the proof.** It resolves against `pyproject.toml`, so it can only prove the version it runs against. This is why the flip is Phase B, not the end.
- **The branch is red from Task 4 until Phase C completes.** Expected, not a failure. `coverage.yml` triggers on `pull_request` only, and the PR opens at component completion — so no CI noise and no PR until green.
- **Live-trade-path changes take the Fable review floor** (`.claude/rules/spec-plan-locations.md`). `cli/engine/{node,executor,execgate,command}.py` are all live trade path.
- **Never construct a `MessageBus`** (D3). It registers itself globally and replaces the engine's own: orders freeze at `INITIALIZED`, no events fire, nothing raises.
- **`external_order_claims` stays unset** on every strategy, and the token stays absent from `cli/` — the existing structural ban.
- **A `uv.lock` change reaches every test** (D12), so from Task 4 onward the full suite is owed, never the diff's reachable subset. The image is shared — one Dockerfile, one lock — so the pin change rebuilds capture, engine, ops and NAS; the NAS runs `-compat` builds only.
- **One branch, one PR, however large.** Every phase lands here; the PR opens at migration completion.
- **Trailer the reviewer at review time**, not at branch end — `Co-Authored-By:` first, `Reviewed-by:` last, amended onto the commits the review covered while they are still local.
- **Review at each task's completion**, covering that task's commits, rather than one whole-branch pass at the end.
- **Code comments and docstrings describe what the code does now.** No "v1 did X", no migration narrative, no before-and-after. Why it moved belongs in the commit message and the spec; a future reader of `cli/engine/` should not be able to tell a migration happened.
- **Deployment is out of this plan's scope.** The deployable pin is a stable release (D1); nothing here converges anything.

______________________________________________________________________

### Task 0: Cold spec+plan review — before any code

- [ ] **Step 1: Dispatch a fresh-context reviewer at the Fable floor**

Per `.claude/rules/spec-plan-locations.md`, the pair gets a cold review before Task 1: coverage (every spec decision has a task), internal consistency, whether the planned verification pins the spec's load-bearing properties, and that every deferral names a registered topic or an explicit drop. Fable floor because this touches the live trade path.

- [ ] **Step 2: Fold material findings into the plan, not into a notes file**

______________________________________________________________________

**D6 is landed but NOT yet v2-safe.** The fix shipped on this branch because the defect exists on v1 today, but it reads `self._client.id` at its two call sites in `cli/engine/executor.py` (grep it — the read in `_start_intent` and the one in `_reconcile_terminal`), and v2 renames that attribute to `strategy_id` (measured: `hasattr(Strategy, "id")` is `False` on the pinned wheel). Task 7a re-points it. **Its own tests cannot catch this**: `StubClient` sets `self.id`, so the three `test_reconcile_terminal_*` tests stay green while production raises — inside `_reconcile_terminal`'s own `except`, which calls `_trip_kill`, latching the kill switch after every completed intent.

## Phase A — guards that must be proved on v1

### Task 1: The nautilus interface pin (D4)

Our whole dependency is twenty symbols. Pin them exhaustively so a bump reports exactly what moved.

**Files:**

- Create: `tests/test_nautilus_interface_pin.py`

**Interfaces:**

- Produces: nothing importable; it is a guard. Later tasks read its failures as the migration work-list.

- [ ] **Step 1: Write the pin, against v1**

```python
"""Every nautilus symbol this project depends on, pinned by path, shape and value.

The development pin moves daily and upstream reshapes our exact surface -- `KrakenExecClientConfig`
became `KrakenExecutionClientConfig` and `trader_id` was removed from the exec config within four
days of each other. This file answers "what changed under us on this bump?" for the whole surface we
actually use, in one run. It is deliberately preferred over adopting more of the library to widen
coverage: adopting does not deepen coverage of what we depend on, it enlarges what we depend on.
"""

import importlib

import pytest

# (module, symbol) for every nautilus name imported anywhere under cli/.
PINNED_SYMBOLS = [
    ("nautilus_trader.adapters.kraken.config", "KrakenDataClientConfig"),
    ("nautilus_trader.adapters.kraken.config", "KrakenExecClientConfig"),
    ("nautilus_trader.adapters.kraken.constants", "KRAKEN"),
    ("nautilus_trader.adapters.kraken.factories", "KrakenLiveDataClientFactory"),
    ("nautilus_trader.adapters.kraken.factories", "KrakenLiveExecClientFactory"),
    ("nautilus_trader.config", "InstrumentProviderConfig"),
    ("nautilus_trader.config", "LiveExecEngineConfig"),
    ("nautilus_trader.config", "LoggingConfig"),
    ("nautilus_trader.config", "TradingNodeConfig"),
    ("nautilus_trader.live.node", "TradingNode"),
    ("nautilus_trader.model.enums", "AccountType"),
    ("nautilus_trader.model.enums", "LiquiditySide"),
    ("nautilus_trader.model.enums", "OrderSide"),
    ("nautilus_trader.model.enums", "OrderStatus"),
    ("nautilus_trader.model.enums", "TimeInForce"),
    ("nautilus_trader.model.enums", "liquidity_side_to_str"),
    ("nautilus_trader.model.identifiers", "InstrumentId"),
    ("nautilus_trader.model.identifiers", "StrategyId"),
    ("nautilus_trader.model.identifiers", "Venue"),
    ("nautilus_trader.trading.strategy", "Strategy"),
]

# Attributes, not just symbols. `Strategy.id` is read on the live trade path
# (`positions_open(strategy_id=self._client.id)`); v2 renames it `strategy_id`.
PINNED_ATTRIBUTES = [("nautilus_trader.trading.strategy", "Strategy", "id")]


@pytest.mark.parametrize("module_path,cls_name,attr", PINNED_ATTRIBUTES, ids=lambda v: str(v))
def test_every_attribute_we_read_still_exists_on_its_class(module_path, cls_name, attr):
    cls = getattr(importlib.import_module(module_path), cls_name)
    assert hasattr(cls, attr), f"{cls_name}.{attr} is gone -- the live trade path reads it"



@pytest.mark.parametrize("module_path,symbol", PINNED_SYMBOLS, ids=lambda v: v.rsplit(".", 1)[-1])
def test_every_symbol_we_import_still_exists_where_we_import_it(module_path, symbol):
    module = importlib.import_module(module_path)
    assert hasattr(module, symbol), f"{module_path}.{symbol} is gone -- our import site breaks"


# Name -> integer, for every enum whose VALUE we persist into a durable record or compare across a
# restart. A rename is loud; a silent value change corrupts stored rows, so both halves are pinned.
PINNED_ENUM_VALUES = {
    "LiquiditySide": {"NO_LIQUIDITY_SIDE": 0, "MAKER": 1, "TAKER": 2},
    "OrderSide": {"NO_ORDER_SIDE": 0, "BUY": 1, "SELL": 2},
    "TimeInForce": {"GTC": 1, "IOC": 2, "FOK": 3, "GTD": 4},
    "AccountType": {"CASH": 1, "MARGIN": 2, "BETTING": 3},
    # Exactly the members cli/engine references. Generated from the installed wheel, never typed.
    "OrderStatus": {"CANCELED": 8, "DENIED": 2, "EXPIRED": 9, "FILLED": 14, "REJECTED": 7},
}


@pytest.mark.parametrize("enum_name", sorted(PINNED_ENUM_VALUES))
def test_enum_member_names_and_integer_values_are_unchanged(enum_name):
    from nautilus_trader.model import enums as nt_enums

    enum_cls = getattr(nt_enums, enum_name)
    for member_name, expected in PINNED_ENUM_VALUES[enum_name].items():
        member = getattr(enum_cls, member_name, None)
        assert member is not None, f"{enum_name}.{member_name} is gone -- stored rows reference it"
        assert int(member) == expected, (
            f"{enum_name}.{member_name} changed from {expected} to {int(member)} -- every persisted "
            f"row carrying the old value now means something else"
        )


# Defaults we rely on WITHOUT setting them. A default that flips is the quietest possible change.
def test_the_exec_engine_defaults_we_rely_on_are_unchanged():
    from nautilus_trader.config import LiveExecEngineConfig

    config = LiveExecEngineConfig()
    assert config.reconciliation is True
    assert config.filter_unclaimed_external_orders is False, (
        "unclaimed external orders would stop materialising -- the external-order stream, the "
        "adopted-row sweep and the unmatched counter all go dark at once"
    )
```

- [ ] **Step 2: Run it — expect green on v1**

Run: `uv run pytest tests/test_nautilus_interface_pin.py -q`
Expected: PASS. It is describing the installed v1.

- [ ] **Step 3: Prove it is not vacuous**

Run `infra/scripts/mutate-probe.sh` against the test file itself, **twice** — once mutating a pinned integer (`"MAKER": 1` → `"MAKER": 7`) and once mutating a `PINNED_ATTRIBUTES` entry (`"id"` → `"id_"`).
Expected: KILLED both times. One probe covers one table: an enum mutation leaves the attribute pin unexercised, and a table no test consumes passes every probe aimed elsewhere.

- [ ] **Step 4: Commit**

```bash
git add tests/test_nautilus_interface_pin.py
git commit -m "test(engine): pin the whole nautilus interface we depend on"
```

### Task 2: The handler-existence guard (D4)

`on_quote_tick` → `on_quote` is invisible: Python does not complain about a subclass method the framework never calls, and every existing test drives our handler directly through stubs, so the suite stays green while production sees no quotes.

**Files:**

- Modify: `tests/test_engine_node.py`

- [ ] **Step 1: Write the guard**

```python
def test_every_handler_our_strategy_overrides_exists_on_the_library_base_class():
    """The silent-rename guard. A handler the framework no longer dispatches to is not an error in
    Python -- it is a method nobody calls, and a stub-driven suite cannot see the difference. This
    turns the whole class of handler renames into one red test.

    It is deliberately general rather than named after `on_quote_tick`: the next rename will be a
    different handler.
    """
    from nautilus_trader.trading.strategy import Strategy

    overridden = {
        name
        for name in vars(ShadowStrategy)
        if name.startswith("on_") and callable(getattr(ShadowStrategy, name, None))
    }
    assert overridden, "found no handlers to check -- the walk is broken, not the strategy"
    missing = sorted(name for name in overridden if not hasattr(Strategy, name))
    assert not missing, (
        f"{missing} are overridden here but do not exist on the library's Strategy -- the framework "
        f"will never call them, and nothing else in this suite would notice"
    )
```

- [ ] **Step 2: Run — expect green on v1**

Run: `uv run pytest tests/test_engine_node.py -k handler_our_strategy -q`
Expected: PASS (v1 `Strategy` has `on_quote_tick`).

- [ ] **Step 3: Prove it bites** — temporarily rename `ShadowStrategy.on_quote_tick` to `on_quote_tickk`, re-run, expect FAIL naming it, restore.

- [ ] **Step 4: Commit**

### Task 3: Pin the strategy identity explicitly (D8)

`order_id_tag` is positional for tag-less strategies (`f"{len(order_id_tags):03d}"`), and `ShadowStrategy` passes no `StrategyConfig`. Registering Task 9's observer would silently change the main strategy's client-order-id prefix — a venue-visible identifier — based on registration order.

**Files:**

- Modify: `cli/engine/node.py`, `tests/test_engine_node.py`

- [ ] **Step 1: Read the CURRENT live tag before pinning anything**

Do not derive it. Read an actual `client_order_id` from the exec ledger (or from a built node's strategy) and record the tag it carries. Pinning a wrong value changes every future order id.

- [ ] **Step 2: Write the failing pin test**

```python
def test_the_strategys_order_id_tag_is_explicit_not_positional(tmp_path):
    """`order_id_tag` is assigned as `f"{len(order_id_tags):03d}"` for a strategy that passes no
    config -- so registering a SECOND strategy silently changes this one's client-order-id prefix,
    which is visible at the venue. Pinned so a registration-order change is a red test."""
    strategy = ShadowStrategy(_config(tmp_path))
    assert strategy.order_id_tag == "000"  # the value read off the live ledger in Step 1
```

- [ ] **Step 3: Make it pass** — pass `StrategyConfig(order_id_tag="000")`. Leave `external_order_claims` unset; the standing ban is on the token and on a non-`None` value, and both still hold.

- [ ] **Step 4: Confirm the claims assertion still passes** — `test_the_strategy_claims_no_external_orders` must stay green.

- [ ] **Step 5: Record D7's deliberate asymmetry where it is still unwritten**

`_publish_fill`'s docstring already says its read is instrument-scoped and that `_reconcile_terminal` doubts the strategy-scoped quantity instead. `_realized_eur` carries no such note. Add one: it stays instrument-scoped on purpose, because a hand settle of an engine leg realizes an outcome that is genuinely the engine's, and strategy-scoping would systematically undercount exactly the sanctioned case. Without the note, a later reader aligns it with D6 and reintroduces the phantom-long class of error.

- [ ] **Step 6: Note that this pin does not survive the crossing unaided**

v2 exposes no `order_id_tag` attribute on the class or an instance — only `strategy.config.order_id_tag` and the derived `strategy_id`. Task 7a re-expresses the pin against the registered strategy's *effective* identity, which is what the venue sees.

- [ ] **Step 7: Run the engine suites and commit**

______________________________________________________________________

## Phase B — the flip

### Task 4: Flip the pin (D1)

**Files:**

- Modify: `pyproject.toml`, `uv.lock`

- [ ] **Step 1: Add the index and flip the pin**

```toml
[[tool.uv.index]]
name = "nautechsystems"
url = "https://packages.nautechsystems.io/simple"
explicit = true
```

with `nautilus-trader = { index = "nautechsystems" }` under `[tool.uv.sources]`, and the dependency pinned to `nautilus-trader==2.0.0rc4.dev20260824`. `explicit = true` so this index serves only this package and never shadows PyPI.

- [ ] **Step 2: Relock and sync**

Run: `uv lock && uv sync`
Expected: the pinned wheel resolves. Note the v2 wheel declares no required runtime dependencies where 1.231.0 pulled several — expect the lock to shrink.

- [ ] **Step 3: Capture the red baseline — this IS the work-list**

Run: `uv run pytest -q 2>&1 | tail -80` and save the failure list to the plan's workspace. Every later task in Phase C closes a named part of it. Record the count.

- [ ] **Step 4: Confirm Task 1 and Task 2's guards are among the failures**

If the interface pin and the handler guard are green on v2, they are not doing their job — investigate before proceeding. They should name the renamed symbols and handlers precisely.

- [ ] **Step 5: Commit the flip alone**

```bash
git add pyproject.toml uv.lock
git commit -m "build(config): flip the nautilus pin to the v2 development wheel"
```

______________________________________________________________________

## Phase C — work it green

Each task below closes part of Task 4's baseline. The 58-edit inventory behind these is in the spec's measured basis; where a step says "measured", the value was read off the running wheel and can be trusted without re-deriving.

### Task 5: Mechanical import moves

Flat `nautilus_trader.model` replaces `model.enums` / `model.identifiers`; `nautilus_trader.trading` replaces `trading.strategy`; `adapters.kraken` replaces its three submodules. `nautilus_trader.live.node` and `model.orders.base` have no v2 target.

**Files:** `cli/engine/{node,executor,venuestate}.py`, `tests/test_engine_{executor,node,metrics}.py`, `tests/test_nautilus_adapter.py`, and Task 1's `PINNED_SYMBOLS` table.

- [ ] **Step 1:** Move every import; update `PINNED_SYMBOLS` to the new paths **and the new names**: `KrakenExecutionClientConfig`, `KrakenDataClientFactory`, `KrakenExecutionClientFactory`, and **`LiveExecEngineConfig` → `LiveExecutionEngineConfig`** — measured, and easy to miss because it is the config carrying `reconciliation` and `filter_unclaimed_external_orders`, the two defaults the whole external-order path rests on. Update `PINNED_ATTRIBUTES` to `strategy_id`.
- [ ] **Step 2:** `uv run pytest tests/test_nautilus_interface_pin.py -q` → green again. The pin is now describing v2.
- [ ] **Step 3:** Commit.

### Task 6: Node assembly (D1, D5)

`TradingNodeConfig` / `TradingNode` / `add_data_client_factory` are gone in favour of `LiveNode.builder(name, TraderId(...), Environment.LIVE)`. `LoggingConfig` → `LoggerConfig`. `instrument_provider=` is rejected on both client configs.

**Files:** `cli/engine/node.py`, `tests/test_engine_node.py`

- [ ] **Step 1:** Rewrite `_node_config` / `build_shadow_node` to the builder chain.
- [ ] **Step 2:** Drop `instrument_provider=` from both client configs.
- [ ] **Step 2b (D13): Supply the exec credentials, which v2 now requires**

Measured: `KrakenExecutionClientConfig(...)` without `account_id`, `api_key` and `api_secret` raises `TypeError: missing 3 required positional arguments`. v1 needed none — the adapter read the environment itself. Read the same `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` already rendered onto the host and pass them explicitly; `account_id` is an explicit `AccountId`.

Two properties are load-bearing and each gets a test.

**Keyless local construction builds a DATA-ONLY node** — with no credentials in the environment the exec client is not wired at all, which is what keyless already meant given the key is IP-bound to the host. If execution is explicitly enabled and the environment is empty, construction **refuses loudly**. Never substitute placeholder credentials: a node that looks armed and is not defers the failure from construction to first submission. Two tests: no credentials → a node with no exec client; exec enabled + empty environment → raises.

**The key must never reach a message** — never interpolated into an error string, never logged with its config. Assert on OUR own message-forming paths, not on nautilus's `TypeError` text, which cannot contain a value that was never passed.

- [ ] **Step 3 (D5): Measure how the twelve instruments reach the Cache**, against a running v2 node — do not infer it from config. `venue_state_from_cache` raises if any of `INSTRUMENT_IDS` is absent, so establish what now guarantees their presence before the first cycle, and write the guard that proves it.
- [ ] **Step 4:** Re-point the config-shape pins in `tests/test_engine_node.py`; v2 exposes no node-side config readback, so assert on the config objects handed to the builder instead.
- [ ] **Step 5:** Commit.

### Task 7: Renamed call sites on the live trade path

All measured: `cancel_order(order)` → `cancel_order(order.client_order_id)` at three sites **including the kill sweep**; `subscribe_quote_ticks` → `subscribe_quotes`; `unsubscribe_quote_ticks` → `unsubscribe_quotes` (three sites); `on_quote_tick` → `on_quote`.

**Files:** `cli/engine/{node,executor}.py`

- [ ] **Step 1:** Apply the renames; update the `ProbeExecutor` client-contract docstring, which enumerates the old surface.
- [ ] **Step 2:** Task 2's handler guard goes green — that is the acceptance signal for the handler rename.
- [ ] **Step 3: Assert the subscription's effect, not the absence of an exception.** A missing `subscribe_*` raises `AttributeError` inside `on_timer`'s blanket `except`, which drops the plan with no gate reason and no kill file. A test that only checks "no exception escaped" cannot see it.
- [ ] **Step 4:** Commit.

### Task 7a: Re-point the strategy identity, and stop the stub hiding the next one

The cold review found this: D6's landed fix reads `self._client.id`, v2 renames it `strategy_id`, and the stub-driven suite is structurally blind because `StubClient` sets `self.id`. No test anywhere drives `ProbeExecutor` with a real `Strategy`, so **any** drift between our client contract and the real one is invisible.

**Files:** `cli/engine/executor.py`, `tests/test_engine_executor.py`

- [ ] **Step 1:** Re-point both `self._client.id` call sites in `cli/engine/executor.py` to `self._client.strategy_id`, and rename `StubClient.id` → `strategy_id` to match production.
- [ ] **Step 2: Re-express Task 3's tag pin against the effective identity** — assert the *registered* strategy's `strategy_id` and its client-order-id prefix, parametrised over both registration orders (observer first, observer second). v2 exposes no `order_id_tag` attribute, and the config input is not what the venue sees.
- [ ] **Step 2b: Prove the own-position read's guard.** The try/except around it is unreachable by any current fixture — `StubCache(raises=True)` raises in `instrument()`, which the earlier venue-truth guard catches first. Build a cache that raises only when `strategy_id is not None`, and confirm the intent is refused rather than the exception escaping. Without it, deleting that try passes the whole suite.
- [ ] **Step 3: Add the guard that generalises this.** Assert every attribute and method `ProbeExecutor` calls on `self._client` exists on the real nautilus `Strategy`. A stub is a contract restatement, and an unverified restatement drifts silently — which is exactly how this defect stayed green.
- [ ] **Step 4: Prove BOTH halves bite, separately.** Step 3's guard derives the checked set from production's calls and asserts them against the real `Strategy`, so a defect planted in the stub cannot trip it. Run two probes: (a) revert the stub attribute to `id` — the contract test must fail; (b) point production at a name the real `Strategy` lacks — the real-class assertion must fail. **Record which failure fired each time**; a red exit can be the guard misfiring on a healthy path rather than catching the planted defect.
- [ ] **Step 5:** Restore, then commit.

### Task 8: Delete the `_liquidity` survival guard

Forced: `liquidity_side_to_str` no longer exists and v2 enums are not iterable (`TypeError: 'type' object is not iterable`). `LiquiditySide` is a plain enum with `.name`, so the 27-line guard and `_LIQUIDITY_VALUES` go.

**Files:** `cli/engine/executor.py`, `tests/test_engine_{executor,metrics}.py`

- [ ] **Step 1:** Replace the body with `side.name`; delete `_LIQUIDITY_VALUES` and the `isinstance(side, int)` branch.
- [ ] **Step 2: Rewrite the tests that pinned v1 behaviour**, which is the hazardous half. The composite-`IntFlag` test is unconstructible on v2 (`MAKER | TAKER` raises `TypeError`), and `{str(member) for member in LiquiditySide}` asserted `'1'` where v2 gives `'MAKER'`. A three-case test that still passes verbatim after the migration is proving nothing — replace it, do not keep it.
- [ ] **Step 3:** Commit.

### Task 9: The sealed EXTERNAL observer (D2)

**Files:** `cli/engine/node.py`, `tests/test_engine_node.py`

- [ ] **Step 1:** Add a `Strategy` subclass registered as `StrategyConfig(strategy_id=StrategyId("EXTERNAL"))` with **`order_id_tag` LEFT UNSET**, routing `on_order_event` to the existing external handler.

Measured, and the reason this is spelled out: supplying a tag yields `strategy_id == EXTERNAL-001`, while unclaimed external orders are stamped exactly `EXTERNAL`. The observer would receive nothing — no exception, no log, no failing test — and D2 would evaporate silently. Unset, it survives `add_strategy` as `EXTERNAL`. Assert that **after registration**, not at construction.
- [ ] **Step 2: Seal the order surface** — override all twelve to raise: `submit_order`, `submit_order_list`, `cancel_order`, `cancel_orders`, `cancel_all_orders`, `cancel_gtd_expiry`, `modify_order`, `modify_orders`, `close_position`, `close_all_positions`, `market_exit`, `post_market_exit`.

The first draft listed eight and left `cancel_orders`, `modify_orders` and `post_market_exit` live — which is why Step 3 derives the set rather than trusting this list.
- [ ] **Step 3: Test that each one raises, and that the list is COMPLETE.** Derive the mutating surface — everything on `Strategy` that is absent from `DataActor`, minus `on_*` handlers and the read-only queries — and assert every member of it is sealed. A hand-enumerated seal regains a hole the next time upstream adds a method, silently; a derived one fails loudly and names it. This is the barrier: on an EXTERNAL-registered strategy every scoping default points its authority at the operator's book.
- [ ] **Step 4:** Extend `test_the_strategy_claims_no_external_orders` and `_ORDER_STREAM_WIDENERS` to cover the observer; retire the `msgbus` allowance, which is now zero.
- [ ] **Step 5 (D3): Give the prohibition a guard, because the existing one cannot see it.** `_ORDER_STREAM_WIDENERS` is a `text.count(name)` walk over lowercase `msgbus`, and `"MessageBus".count("msgbus")` is **0** — so a `MessageBus(...)` constructed in `cli/` passes every check in the repo today. Add `"MessageBus": {}` to that map (allowed nowhere) and prove it bites by temporarily constructing one under `cli/`. Text-count, matching the guard's own stated reasoning.

This matters most during Phase C specifically: the red suite hands an implementer failing external-topic tests whose most obvious repair is the forbidden one, and its failure mode is an engine that accepts orders and never sends them.
- [ ] **Step 6:** Commit.

### Task 10: Supervision and the watchdog

`node._config` and `node.trader` do not exist on `LiveNode`. `Strategy.is_running` changes from property to **method**, so `if strategy.is_running:` on a bound method is permanently true — but `LiveNode.is_running`, which Step 1 re-points to, is still a property. Do not assume the trap follows the read; Step 2 proves the watchdog fires either way.

**Files:** `cli/engine/command.py`

- [ ] **Step 1:** Re-point the health read to `node.is_running` / `node.handle().state`.
- [ ] **Step 1b: Re-source the DELAY, which is the watchdog's whole point.** Production computes it from `node._config.timeout_connection + timeout_reconciliation`; v2's `LiveNode` exposes no `_config`, and `LiveNodeConfig` renames both fields to `*_secs`. Take the values from the config the builder was handed in Task 6 and pin them there — a watchdog that fires before a legitimate connect-and-reconcile completes restarts a healthy engine.
- [ ] **Step 2: Prove the watchdog fires**, with a fixture where the condition it watches is false. A watchdog that compiles is not a watchdog that fires — and the permanently-truthy form is the exact defect to construct.
- [ ] **Step 3:** Re-derive the faulthandler re-arm's justification against v2's Rust/tokio runtime, or remove it with the reason recorded.
- [ ] **Step 4:** Commit.

### Task 11: Rejection classification against the WS transport (D10)

`use_ws_trade` defaults **True**, so submission moves REST → WS while `_KRAKEN_ERROR_MARKERS` is REST-shaped. An unmatched rejection classifies as ambiguous, which stops the plan and leaves an open row.

- [ ] **Step 1: Pin `use_ws_trade=False`** (D10). The default is True, which would move submission to WebSocket; the REST classification is the one this project derived against a real venue, and re-deriving for WS needs live submissions this plan cannot reach — the same constraint that moved Task 16 out.
- [ ] **Step 2: Verify the classification still applies over REST on v2**, rather than re-deriving it. `OrderRejected`/`OrderDenied` still carry only a string `reason` (and lost `venue_order_id`), so `_KRAKEN_ERROR_MARKERS` stays string-shaped and applicable. Pin `use_ws_trade`'s value in Task 1's defaults section so a later default flip is a red test rather than a silent transport change.
- [ ] **Step 3:** Record that adopting WS is deliberately deferred and is its own change with its own evidence — not a follow-up hiding in this one.
- [ ] **Step 4:** Commit.

### Task 12: Rounding fixtures

The spec's framing of this was corrected by the cold review: a quantity rounding to zero raises on **both** wheels, so a fixture built on that premise proves nothing. The real divergences are narrower and quieter, and there are three classes:

1. **Price half-even at decimal midpoints** — v1 rounds the binary float, v2 the exact decimal.
2. **`make_qty` raising at the exact half-increment** (`5e-9` at `size_precision=8`) where v1 returned a value.
3. **`make_qty` value divergence at half-increments** (`1.5e-8` → v1 `0.00000001`, v2 `0.00000002`) — a silent one-increment difference in submitted quantity, which the spec named nowhere.

- [ ] **Step 1: Re-measure all three against a REAL nautilus `Instrument`**, not a `Quantity` constructed by hand — the rounding lives in the instrument's precision, so a hand-built value tests a different code path than production takes.
- [ ] **Step 2:** Add fixtures on the **divergent** values from that measurement. Class 3 is the one to get right: it is silent, it changes an order's quantity, and no existing test would see it.
- [ ] **Step 3:** Decide and record whether class 2's raise needs containment — `instrument.make_qty(sized.qty)` sits outside the only `try` wrapping sizing.
- [ ] **Step 4:** Commit.

### Task 12a: Verify every stub that stands in for a nautilus type

Both review rounds produced blocking findings with one root: the engine suite is stub-driven, and each stub is a hand-written restatement of a nautilus contract with nothing verifying the restatement. Point-patching them one at a time is why the second round found two more.

**Files:** `tests/test_engine_executor.py`, `tests/test_engine_node.py`

- [ ] **Step 1: Enumerate every stub standing in for a nautilus type** — `StubClient`, `StubCache`, `_fake_instrument`, `_fake_node`, the order/event doubles — and state, per stub, how it is verified against the real type. Task 7a Step 3 does this for `StubClient`; generalise it.
- [ ] **Step 2: Fix the two already known to be wrong.** (`StubCache`'s strategy-id partition and its `str` refusal were closed on this branch; start the enumeration from what remains.) `_fake_instrument` sets `make_qty=lambda value: value` and `make_price=lambda value: value` — identity — so no fixture through it can reach the production rounding path, which is what Task 12 measures. `_fake_node` fabricates `_config` with `timeout_connection`, a field v2 renames and `LiveNode` no longer exposes at all.
- [ ] **Step 3: Task 12's fixtures must drive `_place` itself** through a real `CurrencyPair` (or a parametrised `_fake_instrument` delegating to one), asserting the SUBMITTED order's quantity and price. A rounding fixture that never reaches the rounding code proves nothing.
- [ ] **Step 4:** Commit.

### Task 13: Repair the guards that lost their anchors

Each of these is a real guard whose *mechanism* v2 removed. The hazard is repairing them into something weaker.

- [ ] **Step 1:** The terminal-map totality proof parses closed statuses out of `Order.is_closed.__doc__`, which is `None` on v2. Find another way to derive the library's own closed set — **do not hardcode the list**, which converts a proof into an assertion.
- [ ] **Step 2:** The external-topic tests need `MessageBus`, `Strategy.register` and `model.events`; re-express them against the observer from Task 9.
- [ ] **Step 3:** Commit.

### Task 14: The probe harness and the logger guard

- [ ] **Step 1:** Port `infra/scripts/kraken-order-semantics-probe.py` — same import and node-assembly port as Task 6. It places real orders and is the only instrument that can validate the arming pass, so it must be ported before that pass can be scheduled.
- [ ] **Step 2:** `infra/scripts/nautilus-logger-guard-probe.py` cannot run on v2 — `is_logging_initialized` does not exist. Re-express it against v2's logging surface or retire it with the reason recorded, and update T0085, which records the probe as discharged for the 1.231.0 bump.
- [ ] **Step 3:** Commit.

### Task 15: Sequencing the arming pass (D9, D11)

Nothing here arms anything; this task makes the arming pass *possible* and correctly ordered.

- [ ] **Step 1: Stop bumping the pin** — declare it, in the runbook. The arming record does exact string membership, so any bump after the attended pass silently disarms the engine.
- [ ] **Step 2:** Decide the record's granularity before the pass, not at it. Update `infra/runbooks/order-semantics-verification.md`'s version-specific instructions and re-derive the six-probe expectations for v2.
- [ ] **Step 3:** Add the unmatched-external alert to the arming checklist as owed **after** the metric's first record — a rule pushed before it exists pages a spurious no-data alert.
- [ ] **Step 4: Do not touch `order-semantics-verified.json`.** It gains a version only after the attended pass has run and its research doc records the PASS.
- [ ] **Step 5:** Commit.

### Task 16: Hand D2's delivery leg to the arming checklist — it cannot execute here

The publish leg is established from source and the delivery leg in a backtest, but the join needs a genuine venue-sourced external order, which needs live Kraken reconciliation. This plan converges nothing, D1 forbids deploying a development wheel, and the exec key is IP-bound to the engine host — so no step in this plan can reach it. Pretending otherwise would produce a step that is silently skipped or improvised into a non-equivalent local check.

- [ ] **Step 1:** Confirm the obligation is registered as `T0152` with a `ripe_when` naming the first v2 converge, and that its index bullet reflects it. Registration and this plan's closeout travel together — prose in a plan is never a deferral's only home.
- [ ] **Step 2:** State the residual plainly in the PR body: D2 merges with its publish leg proven from source and its delivery leg proven only in a backtest. The fallback if the join fails is known and cheap — Cache polling on the executor's existing 5-second tick.

### Task 17: Closeout

- [ ] **Step 1:** `docs/reference/data-catalog*.md` — no dataset change; confirm and move on.
- [ ] **Step 2:** Update T0085's nautilus sub-item and its `ripe_when`, which still names the cancelled 1.231.0 converge.
- [ ] **Step 3:** Append the iterations-history entry via the `iteration-closeout` skill, routed to the Phase-6 changelog. Re-verify every status claim against the full branch log immediately before PR-open.
- [ ] **Step 4:** Commit.
