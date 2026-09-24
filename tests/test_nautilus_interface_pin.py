"""Every nautilus symbol this project depends on, pinned by path, shape and value: the development
pin moves daily and upstream reshapes our exact surface, so this file answers "what changed under us
on this bump?" in one run — deliberately preferred over adopting more of the library, which does not
deepen what we depend on but enlarges it."""

import ast
import importlib
from pathlib import Path

import pytest
from nautilus_trader.live import SubmissionRecoveryPolicy

# (module, symbol) for every nautilus name imported anywhere under cli/, at the module path cli/
# imports it FROM -- pinning the same object through a different path would pass while a dropped
# re-export broke the live import site.
#
# Not every entry is an import site: `nautilus_trader.__version__` is what the arming gate reads
# through `cli/engine/execgate.py`'s bare module import, and `LiquiditySide`, which cli/ never
# imports, is pinned because the venue's member NAMES are persisted into forensic rows off live
# fill events (`cli/engine/command.py` pins the lower-cased set against it).
PINNED_SYMBOLS = [
    ("nautilus_trader", "__version__"),
    ("nautilus_trader.adapters.kraken", "KRAKEN"),
    ("nautilus_trader.adapters.kraken", "KrakenDataClientConfig"),
    ("nautilus_trader.adapters.kraken", "KrakenDataClientFactory"),
    ("nautilus_trader.adapters.kraken", "KrakenEnvironment"),
    ("nautilus_trader.adapters.kraken", "KrakenExecutionClientConfig"),
    ("nautilus_trader.adapters.kraken", "KrakenExecutionClientFactory"),
    ("nautilus_trader.adapters.kraken", "KrakenProductType"),
    ("nautilus_trader.adapters.kraken", "KrakenSpotHttpClient"),
    ("nautilus_trader.common", "Environment"),
    ("nautilus_trader.common", "LogLevel"),
    ("nautilus_trader.config", "LiveExecutionEngineConfig"),
    ("nautilus_trader.config", "LoggerConfig"),
    ("nautilus_trader.live", "LiveNode"),
    ("nautilus_trader.live", "LiveNodeBuilder"),
    ("nautilus_trader.model", "AccountId"),
    ("nautilus_trader.model", "AccountType"),
    ("nautilus_trader.model", "ClientOrderId"),
    ("nautilus_trader.model", "InstrumentId"),
    ("nautilus_trader.model", "LiquiditySide"),
    ("nautilus_trader.model", "OrderSide"),
    ("nautilus_trader.model", "OrderStatus"),
    ("nautilus_trader.model", "OrderType"),
    ("nautilus_trader.model", "Quantity"),
    ("nautilus_trader.model", "StrategyId"),
    ("nautilus_trader.model", "TimeInForce"),
    ("nautilus_trader.model", "TraderId"),
    ("nautilus_trader.model", "Venue"),
    ("nautilus_trader.model", "VenueOrderId"),
    ("nautilus_trader.trading", "Strategy"),
    ("nautilus_trader.trading", "StrategyConfig"),
]

# Attributes, not just symbols. `Strategy.strategy_id` is read on the live trade path
# (`positions_open(strategy_id=self._client.strategy_id)`).
PINNED_ATTRIBUTES = [
    ("nautilus_trader.trading", "Strategy", "strategy_id"),
    # The two members that name which Kraken venue the engine reaches. Both configs state them
    # explicitly, so a rename breaks the call rather than silently selecting the other member.
    ("nautilus_trader.adapters.kraken", "KrakenProductType", "SPOT"),
    ("nautilus_trader.adapters.kraken", "KrakenEnvironment", "LIVE"),
]


@pytest.mark.parametrize("module_path,cls_name,attr", PINNED_ATTRIBUTES, ids=lambda v: str(v))
def test_every_attribute_we_read_still_exists_on_its_class(module_path, cls_name, attr):
    cls = getattr(importlib.import_module(module_path), cls_name)
    assert hasattr(cls, attr), f"{cls_name}.{attr} is gone -- the live trade path reads it"


@pytest.mark.parametrize("module_path,symbol", PINNED_SYMBOLS, ids=lambda v: v.rsplit(".", 1)[-1])
def test_every_symbol_we_import_still_exists_where_we_import_it(module_path, symbol):
    module = importlib.import_module(module_path)
    assert hasattr(module, symbol), f"{module_path}.{symbol} is gone -- our import site breaks"


def test_the_pin_covers_every_nautilus_name_cli_imports():
    """Every `from nautilus_trader... import X` under cli/ must appear in `PINNED_SYMBOLS` under the
    module it is imported FROM, and a bare `import nautilus_trader...` must have its module pinned
    through some entry. One-directional on purpose: the pin may hold names cli/ does not import (a
    persisted enum has no import site), so only the tree-minus-pin direction is an offence."""
    imported: set[tuple[str, str]] = set()
    modules_imported: set[str] = set()
    files = sorted(Path("cli").rglob("*.py"))
    assert len(files) > 100, f"the walk found only {len(files)} files -- vacuous"
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "nautilus_trader":
                    imported |= {(node.module, alias.name) for alias in node.names}
            elif isinstance(node, ast.Import):
                modules_imported |= {a.name for a in node.names if a.name.split(".")[0] == "nautilus_trader"}
    assert imported, "the walk found no nautilus import at all -- it would pass on an empty pin"

    pinned_modules = {module for module, _ in PINNED_SYMBOLS}
    assert sorted(imported - set(PINNED_SYMBOLS)) == [], "imported under cli/ and not pinned"
    assert sorted(modules_imported - pinned_modules) == [], "module imported under cli/ and not pinned"


# Name -> integer for every enum whose VALUE a stored row depends on, and for any whose MEMBER SET a
# live decision depends on. The two are not the same criterion and the map holds both: a value that
# changes corrupts every persisted row carrying the old one, while a member that empties to bare
# `None` changes what a read returns with nothing renamed and nothing to break at import. Which of
# the two an entry is here for is not uniform -- `PositionSide` is the member-set case and says so.
# The map is a SUBSET of most of these enums, so the parametrised test below checks only that what
# is listed still resolves and still carries its integer.
# `OrderSide` carries no `NO_ORDER_SIDE` entry: the name resolves to bare `None` rather than an enum
# member -- "no side" is `Option`-shaped throughout the library now -- and nothing under cli/ has
# ever persisted its value, so the entry was dropped rather than widened to accept `None`, which
# `int()` cannot pin. `LiquiditySide.NO_LIQUIDITY_SIDE` IS persisted (tracking.py, executor.py) and
# stays pinned below.
PINNED_ENUM_VALUES = {
    "LiquiditySide": {"NO_LIQUIDITY_SIDE": 0, "MAKER": 1, "TAKER": 2},
    "OrderSide": {"BUY": 1, "SELL": 2},
    "TimeInForce": {"GTC": 1, "IOC": 2, "FOK": 3, "GTD": 4},
    "AccountType": {"CASH": 1, "MARGIN": 2, "BETTING": 3},
    # Not a persisted value: `cli/engine/flatten.py` reads a row's side as `str(position_side)` and
    # `_required` turns a `None` there into exit 3, so `FLAT` has to stay a real member -- the
    # Option-shaped redesign above reached `NO_POSITION_SIDE` and could reach `FLAT` next.
    # `test_a_position_report_refuses_a_none_side` below pins the other half.
    "PositionSide": {"FLAT": 1, "LONG": 2, "SHORT": 3},
    # Exactly the members cli/engine references. Generated from the installed wheel, never typed.
    "OrderStatus": {"CANCELED": 8, "DENIED": 2, "EXPIRED": 9, "FILLED": 14, "REJECTED": 7, "VOIDED": 15},
}


# Entries whose real member set must EQUAL the pinned one. `PositionSide` is the only one that needs
# it HERE: a new variant is acted on by a live read, and the assertion below says what that costs.
# `LiquiditySide` is acted on too -- `cli/engine/tracking.py` raises on a name outside its three --
# but its member set is already walked from `LiquiditySide.variants()` by tests/test_engine_executor.py
# and tests/test_engine_metrics.py, so an added variant is red there and a second guard here would
# only move where it is caught.
EXHAUSTIVE_MEMBERS = {"PositionSide"}


def test_the_exhaustive_member_walk_is_not_vacuous():
    """Parametrising over an empty set collects one SKIP and summarises green, so pruning the literal
    below to `set()` would take the only member-set guard out of the suite with no red run -- while
    `docs/open-topics/T0159-engine-flatten-the-red-button.md` still leans on it in prose."""
    assert EXHAUSTIVE_MEMBERS, "EXHAUSTIVE_MEMBERS is empty -- the walk below would skip, not fail"


@pytest.mark.parametrize("enum_name", sorted(EXHAUSTIVE_MEMBERS))
def test_an_exhaustive_enums_real_member_set_is_the_pinned_one(enum_name):
    """The half the value pin cannot see: it walks the names the map lists, so a member ADDED
    upstream is simply absent from the walk and every assertion still passes."""
    import nautilus_trader.model as nt_enums

    enum_cls = getattr(nt_enums, enum_name)
    real = {name for name in dir(enum_cls) if name.isupper() and getattr(enum_cls, name, None) is not None}
    assert real == set(PINNED_ENUM_VALUES[enum_name]), (
        f"{enum_name}'s real member set is {sorted(real)} against the pinned "
        f"{sorted(PINNED_ENUM_VALUES[enum_name])}. A new variant reaches cli/engine/flatten.py as a "
        f"side it cannot close from: the row is filed unclosable and the press exits 2 with the "
        f"position still open. Decide what the member means before pinning it"
    )


@pytest.mark.parametrize("enum_name", sorted(PINNED_ENUM_VALUES))
def test_enum_member_names_and_integer_values_are_unchanged(enum_name):
    import nautilus_trader.model as nt_enums

    enum_cls = getattr(nt_enums, enum_name)
    for member_name, expected in PINNED_ENUM_VALUES[enum_name].items():
        member = getattr(enum_cls, member_name, None)
        assert member is not None, (
            f"{enum_name}.{member_name} is gone, or has emptied to bare `None` as the library's "
            f"Option-shaped redesign did to the NO_* members. Why that matters is per entry, and "
            f"the map says which: a persisted VALUE no stored row can still mean, or a MEMBER a "
            f"live read depends on -- for PositionSide, cli/engine/flatten.py's exit-3 abort"
        )
        assert int(member) == expected, (
            f"{enum_name}.{member_name} changed from {expected} to {int(member)} -- every persisted "
            f"row carrying the old value now means something else"
        )


# Library defaults, pinned even where cli/engine/node.py now states them: a flip is the quietest possible change.
def test_the_strategy_management_defaults_we_rely_on_are_unchanged():
    """These arm order management inside the library, which reaches the venue without passing
    through any method a subclass can override. The external observer sets them explicitly, but a
    flip would also change every strategy that does not -- so the default itself is pinned."""
    from nautilus_trader.config import StrategyConfig

    config = StrategyConfig()
    assert config.manage_contingent_orders is False
    assert config.manage_gtd_expiry is False
    assert config.manage_stop is False


def test_the_exec_engine_defaults_we_rely_on_are_unchanged():
    from nautilus_trader.config import LiveExecutionEngineConfig

    config = LiveExecutionEngineConfig()
    assert config.reconciliation is True
    assert config.filter_unclaimed_external_orders is False, (
        "unclaimed external orders would stop materialising -- the external-order stream, the "
        "adopted-row sweep and the unmatched counter all go dark at once"
    )
    assert config.generate_missing_orders is True, (
        "this one is INHERITED rather than stated, and it gates the synthetic adjustment that "
        "aligns the Cache's startup position with the venue -- the position cli/engine/venuestate.py "
        "freezes into the VenueState the cycle sizes off. False would let the two disagree silently"
    )
    assert config.filter_position_reports is False, (
        "also inherited. True makes the library's reconciliation skip reconcile_position_report "
        "entirely, so startup creates NO position from the venue's own position reports and the "
        "Cache the VenueState is frozen from reads empty against an open position. Upstream "
        "documents the flag for accounts several nodes trade -- which is this account's shape, so "
        "it is a plausible thing for someone to reach for rather than a theoretical flip"
    )
    assert config.allow_overfills is False, (
        "also inherited, and cli/engine/executor.py names it in the paragraph bounding what covers "
        "a fill that did not happen: upstream's check_overfill, with this False, refuses an "
        "application past the order's own quantity. True removes one of the three bounds that "
        "paragraph and specs 00098 and 00100 rest on"
    )


# Every `LiveExecutionEngineConfig` default, measured from the installed wheel rather than typed.
# `cli/engine/node.py` states five of these and inherits the other thirty-three, so a default that
# moves upstream moves production here silently, with no import to break and no rename to notice.
# The three that carry a reasoned assertion below say WHY they matter; this map says only what a
# wheel reported, which is the one claim it can make honestly about fields whose behaviour nothing
# in this repo has established.
EXEC_ENGINE_DEFAULTS = {
    "allow_overfills": False,
    "debug": False,
    "external_clients": None,
    "filter_position_reports": False,
    "filter_unclaimed_external_orders": False,
    "filtered_client_order_ids": None,
    "generate_missing_orders": True,
    "inflight_check_interval_ms": 2000,
    "inflight_check_retries": 5,
    "inflight_check_threshold_ms": 5000,
    "load_cache": True,
    "manage_own_order_books": False,
    "max_single_order_queries_per_cycle": 10,
    "open_check_interval_secs": None,
    "open_check_lookback_mins": 60,
    "open_check_missing_retries": 5,
    "open_check_open_only": True,
    "open_check_threshold_ms": 5000,
    "own_books_audit_interval_secs": None,
    "position_check_interval_secs": None,
    "position_check_lookback_mins": 60,
    "position_check_retries": 3,
    "position_check_threshold_ms": 5000,
    "purge_account_events_interval_mins": None,
    "purge_account_events_lookback_mins": None,
    "purge_closed_orders_buffer_mins": None,
    "purge_closed_orders_interval_mins": None,
    "purge_closed_positions_buffer_mins": None,
    "purge_closed_positions_interval_mins": None,
    "reconciliation": True,
    "reconciliation_instrument_ids": None,
    "reconciliation_lookback_mins": None,
    "reconciliation_startup_delay_secs": 10.0,
    "single_order_query_delay_ms": 100,
    "snapshot_orders": False,
    "snapshot_positions": False,
    "snapshot_positions_interval_secs": None,
    "submission_recovery_policy": SubmissionRecoveryPolicy.RESOLVE_LOCALLY,
}


def test_every_exec_engine_default_is_the_one_we_measured():
    """The tripwire over the whole config, in both directions. A value that moved is the obvious
    half. A field that APPEARED is the other: a knob upstream adds is a behaviour someone chose a
    default for on our behalf, and the bump that adds it is the only cheap moment to read it."""
    from nautilus_trader.config import LiveExecutionEngineConfig

    config = LiveExecutionEngineConfig()
    # No `callable` filter: this config's public attributes are all plain values, and filtering on
    # callability would silently drop a NEW field defaulting to a factory or a type -- exactly the
    # shape the field-set arm below exists to catch.
    live = {name: getattr(config, name) for name in dir(config) if not name.startswith("_")}
    assert set(live) == set(EXEC_ENGINE_DEFAULTS), (
        "the exec engine's FIELD SET moved -- added "
        f"{sorted(set(live) - set(EXEC_ENGINE_DEFAULTS))}, removed "
        f"{sorted(set(EXEC_ENGINE_DEFAULTS) - set(live))}. Read what the new one does before "
        "re-measuring this map: an inherited default is production behaviour nobody chose here"
    )
    moved = {
        name: (EXEC_ENGINE_DEFAULTS[name], live[name]) for name in EXEC_ENGINE_DEFAULTS if live[name] != EXEC_ENGINE_DEFAULTS[name]
    }
    assert moved == {}, f"exec engine defaults moved (was, now): {moved}"


def test_the_inflight_defaults_we_now_state_explicitly_are_unchanged():
    """`cli/engine/node.py` states these three rather than inheriting them (spec 00100 D15), so the
    defaults no longer reach production -- but the pin stays: a bump that moved any of them would
    turn our stated values from restatements into a deliberate divergence worth re-deriving."""
    from nautilus_trader.config import LiveExecutionEngineConfig

    config = LiveExecutionEngineConfig()
    assert config.inflight_check_interval_ms == 2000
    assert config.inflight_check_threshold_ms == 5000
    assert config.inflight_check_retries == 5


def test_a_position_report_refuses_a_none_side():
    """The other half of `PositionSide`'s pin, and the half an enum-value map cannot state: the red
    button's abort path stays unreachable only while the library refuses to BUILD a report carrying
    no side. Let a future wheel accept `None` there and `cli/engine/flatten.py`'s `_required` raises
    on it -- `run_flatten` exits 3, refusing to flatten an account, rather than naming the row and
    flattening the rest."""
    from nautilus_trader.model import AccountId, InstrumentId, PositionSide, PositionStatusReport, Quantity

    head = (AccountId("KRAKEN-901"), InstrumentId.from_str("BTC/EUR.KRAKEN"))
    tail = (Quantity.from_str("0"), 0, 0)
    assert str(PositionStatusReport(*head, PositionSide.FLAT, *tail).position_side) == "FLAT"
    with pytest.raises(TypeError):
        PositionStatusReport(*head, None, *tail)


def test_every_order_event_the_executor_routes_on_carries_the_reconciliation_flag():
    """The flag is the executor's only way to tell a terminal the engine minted from one the venue
    sent, and it reads it off the event with a `getattr` default -- so a class that stopped carrying
    it would silently answer False and drive the fallback D15 removes."""
    from nautilus_trader.model import OrderCanceled, OrderExpired, OrderFilled, OrderRejected

    for cls in (OrderRejected, OrderCanceled, OrderExpired, OrderFilled):
        assert hasattr(cls, "reconciliation"), f"{cls.__name__} no longer carries `reconciliation`"


def test_the_exec_client_transport_default_we_now_override_is_unchanged():
    """`cli/engine/node.py` now sets `use_ws_trade=False` explicitly (spec 00100 D10), so this
    default no longer reaches production -- but the pin stays: if the library default ever flips to
    False, our explicit `False` stops being a decision and D10's reasoning is worth revisiting."""
    from nautilus_trader.adapters.kraken import KrakenExecutionClientConfig
    from nautilus_trader.model import AccountId

    config = KrakenExecutionClientConfig(account_id=AccountId("KRAKEN-001"), api_key="a-key", api_secret="a-secret")
    assert config.use_ws_trade is True


# Existence is not enough -- a removed or newly-required argument leaves the name intact. These
# construct each config the way `cli/engine/node.py` constructs it, so the pin fails on the call we
# actually make.
def test_the_kraken_client_configs_accept_the_arguments_we_pass():
    from nautilus_trader.adapters.kraken import (
        KrakenDataClientConfig,
        KrakenEnvironment,
        KrakenExecutionClientConfig,
        KrakenProductType,
    )
    from nautilus_trader.model import AccountId, AccountType

    KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
    )
    KrakenExecutionClientConfig(
        account_id=AccountId("KRAKEN-001"),
        api_key="a-key",
        api_secret="a-secret",
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        spot_account_type=AccountType.MARGIN,
        margin_balance_asset="ZEUR",
        spot_positions_quote_currency="ZEUR",
        use_ws_trade=False,
    )


# The readings spec 00101 D1 rests on, measured rather than remembered: `None` is not "off" -- it
# falls back to the adapter default and reinstates the reconnect loop. Readings only; that `0`
# actually silences the timer is `test_the_shipped_value_stops_the_loop` in
# tests/test_engine_data_socket.py.
def test_ws_idle_timeout_zero_disables_and_none_means_the_default():
    from nautilus_trader.adapters.kraken import KrakenDataClientConfig, KrakenEnvironment, KrakenProductType

    off = KrakenDataClientConfig(product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=0)
    assert off.ws_idle_timeout_ms == 0, "0 must read back as 0 -- that is the literal the engine ships"

    fallback = KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=None
    )
    assert fallback.ws_idle_timeout_ms == 10000, (
        f"None must read back as the adapter default (10000), not as off: {fallback.ws_idle_timeout_ms!r}"
    )
    assert fallback.ws_idle_timeout_ms != off.ws_idle_timeout_ms, (
        "if these ever coincide, None has become a valid 'off' and D1's literal-0 rule is moot"
    )


# The credentials are required arguments, and the refusal that guards a keyless armed node reads
# this as its own precondition: were they to become optional again, an engine with an empty
# environment could construct an exec client that authenticates as nobody.
def test_the_exec_client_config_still_requires_the_credentials():
    from nautilus_trader.adapters.kraken import KrakenExecutionClientConfig

    with pytest.raises(TypeError):
        KrakenExecutionClientConfig()


# The credentials go in and never come back out -- no attribute, no repr, no str. That is what makes
# the config object safe to hand to a logger or an exception, and it is the library's property, so
# it is pinned rather than assumed.
def test_the_exec_client_config_never_exposes_the_credentials():
    from nautilus_trader.adapters.kraken import KrakenExecutionClientConfig
    from nautilus_trader.model import AccountId

    secret = "kraken-live-credential-sentinel"
    config = KrakenExecutionClientConfig(account_id=AccountId("KRAKEN-001"), api_key=secret + "-key", api_secret=secret + "-secret")
    assert secret not in repr(config)
    assert secret not in str(config)
    assert not [name for name in dir(config) if secret in str(getattr(config, name, ""))]


# The node members the engine reaches for after assembly. The BUILDER's method set is pinned in
# `tests/test_engine_node.py` instead, derived from the calls node assembly actually makes -- a
# second hand-written list here would be free to drift from them.
@pytest.mark.parametrize("name", ["builder", "add_strategy", "run", "stop", "dispose", "cache", "trader_id", "environment"])
def test_the_node_still_exposes_every_member_the_engine_reads(name):
    from nautilus_trader.live import LiveNode

    assert hasattr(LiveNode, name), f"LiveNode.{name} is gone -- the engine reads it"


def test_the_exec_engine_config_accepts_the_arguments_we_pass():
    from nautilus_trader.config import LiveExecutionEngineConfig

    LiveExecutionEngineConfig(
        reconciliation=True,
        filter_unclaimed_external_orders=False,
        inflight_check_interval_ms=2000,
        inflight_check_threshold_ms=5000,
        inflight_check_retries=5,
    )
