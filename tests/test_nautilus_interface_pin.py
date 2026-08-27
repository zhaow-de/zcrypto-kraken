"""Every nautilus symbol this project depends on, pinned by path, shape and value.

The development pin moves daily and upstream reshapes our exact surface -- `KrakenExecClientConfig`
became `KrakenExecutionClientConfig` and `trader_id` was removed from the exec config within four
days of each other. This file answers "what changed under us on this bump?" for the whole surface we
actually use, in one run. It is deliberately preferred over adopting more of the library to widen
coverage: adopting does not deepen coverage of what we depend on, it enlarges what we depend on.
"""

import ast
import importlib
from pathlib import Path

import pytest

# (module, symbol) for every nautilus name imported anywhere under cli/, at the module path cli/
# imports it FROM -- a re-export upstream drops is a live-path import error, and pinning the same
# object through a different path would pass while production crashes. Coverage of this list against
# the tree is DERIVED below rather than claimed here, so a new import cannot land unpinned.
#
# Two entries are not import sites. `nautilus_trader.__version__` is what the arming gate reads
# through `cli/engine/execgate.py`'s bare module import, which has no symbol to name; `LiquiditySide`
# cli/ never imports at all, and it is pinned because the venue's own member NAMES are persisted into
# forensic rows off live fill events (`cli/engine/command.py` pins the lower-cased set against it).
PINNED_SYMBOLS = [
    ("nautilus_trader", "__version__"),
    ("nautilus_trader.adapters.kraken", "KRAKEN"),
    ("nautilus_trader.adapters.kraken", "KrakenDataClientConfig"),
    ("nautilus_trader.adapters.kraken", "KrakenDataClientFactory"),
    ("nautilus_trader.adapters.kraken", "KrakenEnvironment"),
    ("nautilus_trader.adapters.kraken", "KrakenExecutionClientConfig"),
    ("nautilus_trader.adapters.kraken", "KrakenExecutionClientFactory"),
    ("nautilus_trader.adapters.kraken", "KrakenProductType"),
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
    ("nautilus_trader.model", "StrategyId"),
    ("nautilus_trader.model", "TimeInForce"),
    ("nautilus_trader.model", "TraderId"),
    ("nautilus_trader.model", "Venue"),
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
    """The list above is only worth what its completeness is worth, and a hand-kept list drifts the
    moment an import lands beside it -- silently, because every other test here passes on a list
    that is merely SHORTER than the truth. So the truth is read off the tree instead of restated:
    every `from nautilus_trader... import X` under cli/ must appear in `PINNED_SYMBOLS` under the
    module it is imported FROM, and a bare `import nautilus_trader...` must have its module pinned
    through some entry.

    One-directional on purpose: the pin may hold names cli/ does not import (a persisted enum has no
    import site), so only the tree-minus-pin direction is an offence."""
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


# Name -> integer, for every enum whose VALUE we persist into a durable record or compare across a
# restart. A rename is loud; a silent value change corrupts stored rows, so both halves are pinned.
PINNED_ENUM_VALUES = {
    "LiquiditySide": {"NO_LIQUIDITY_SIDE": 0, "MAKER": 1, "TAKER": 2},
    "OrderSide": {"NO_ORDER_SIDE": 0, "BUY": 1, "SELL": 2},
    "TimeInForce": {"GTC": 1, "IOC": 2, "FOK": 3, "GTD": 4},
    "AccountType": {"CASH": 1, "MARGIN": 2, "BETTING": 3},
    # Exactly the members cli/engine references. Generated from the installed wheel, never typed.
    "OrderStatus": {"CANCELED": 8, "DENIED": 2, "EXPIRED": 9, "FILLED": 14, "REJECTED": 7, "VOIDED": 15},
}


@pytest.mark.parametrize("enum_name", sorted(PINNED_ENUM_VALUES))
def test_enum_member_names_and_integer_values_are_unchanged(enum_name):
    import nautilus_trader.model as nt_enums

    enum_cls = getattr(nt_enums, enum_name)
    for member_name, expected in PINNED_ENUM_VALUES[enum_name].items():
        member = getattr(enum_cls, member_name, None)
        assert member is not None, f"{enum_name}.{member_name} is gone -- stored rows reference it"
        assert int(member) == expected, (
            f"{enum_name}.{member_name} changed from {expected} to {int(member)} -- every persisted "
            f"row carrying the old value now means something else"
        )


# Defaults we rely on WITHOUT setting them. A default that flips is the quietest possible change.
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


def test_the_inflight_defaults_we_now_state_explicitly_are_unchanged():
    """`cli/engine/node.py` states these three rather than inheriting them (spec 00100 D15), so the
    defaults no longer reach production -- but the pin stays: it is what tells us the world moved.
    They set how long the engine waits on an unanswered order before minting that order's terminal
    event itself, and a bump that moved any of them would mean our stated values had stopped being
    restatements and started being a deliberate divergence worth re-deriving."""
    from nautilus_trader.config import LiveExecutionEngineConfig

    config = LiveExecutionEngineConfig()
    assert config.inflight_check_interval_ms == 2000
    assert config.inflight_check_threshold_ms == 5000
    assert config.inflight_check_retries == 5


def test_every_order_event_the_executor_routes_on_carries_the_reconciliation_flag():
    """The flag is the executor's only way to tell a terminal the engine minted from one the venue
    sent, and it reads it off the event with a `getattr` default. If a class ever stopped carrying
    it the read would silently answer False and the manufactured terminal would drive a fallback
    again -- the exact defect D15 removes -- with nothing else red."""
    from nautilus_trader.model import OrderCanceled, OrderExpired, OrderFilled, OrderRejected

    for cls in (OrderRejected, OrderCanceled, OrderExpired, OrderFilled):
        assert hasattr(cls, "reconciliation"), f"{cls.__name__} no longer carries `reconciliation`"


def test_the_exec_client_transport_default_we_now_override_is_unchanged():
    """`cli/engine/node.py` now sets `use_ws_trade=False` explicitly (spec 00100 D10), so this
    default no longer reaches production -- but the pin stays: it is what tells us the world moved.
    If the library default ever flips to False, our explicit `False` stops being a decision and
    starts being a restatement, and D10's re-derivation-for-WS reasoning is worth revisiting."""
    from nautilus_trader.adapters.kraken import KrakenExecutionClientConfig
    from nautilus_trader.model import AccountId

    config = KrakenExecutionClientConfig(account_id=AccountId("KRAKEN-001"), api_key="a-key", api_secret="a-secret")
    assert config.use_ws_trade is True


# Existence is not enough: every drift this file exists to catch has been a SIGNATURE change --
# an argument removed, an argument newly required, a keyword rejected outright. These construct
# each config exactly the way `cli/engine/node.py` constructs it, so the pin fails on the call we
# actually make rather than on a name that happens to survive.
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


# The two readings spec 00101 D1 rests on, measured here rather than remembered: `0` is accepted and
# reads back as `0`, and `None` is NOT "off" -- it silently falls back to the adapter default and
# reinstates the reconnect loop. Readings only: that `0` actually silences the timer is measured
# behaviourally by `test_the_shipped_value_stops_the_loop` in tests/test_engine_data_socket.py.
# A future upstream change to either reading would pass every other test.
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
