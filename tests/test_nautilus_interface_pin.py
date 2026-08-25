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
    ("nautilus_trader.adapters.kraken", "KRAKEN"),
    ("nautilus_trader.adapters.kraken", "KrakenDataClientConfig"),
    ("nautilus_trader.adapters.kraken", "KrakenDataClientFactory"),
    ("nautilus_trader.adapters.kraken", "KrakenExecutionClientConfig"),
    ("nautilus_trader.adapters.kraken", "KrakenExecutionClientFactory"),
    ("nautilus_trader.common", "Environment"),
    ("nautilus_trader.common", "LogLevel"),
    ("nautilus_trader.config", "LiveExecutionEngineConfig"),
    ("nautilus_trader.config", "LoggerConfig"),
    ("nautilus_trader.live", "LiveNode"),
    ("nautilus_trader.live", "LiveNodeBuilder"),
    ("nautilus_trader.model", "AccountId"),
    ("nautilus_trader.model", "AccountType"),
    ("nautilus_trader.model", "InstrumentId"),
    ("nautilus_trader.model", "LiquiditySide"),
    ("nautilus_trader.model", "OrderSide"),
    ("nautilus_trader.model", "OrderStatus"),
    ("nautilus_trader.model", "StrategyId"),
    ("nautilus_trader.model", "TimeInForce"),
    ("nautilus_trader.model", "TraderId"),
    ("nautilus_trader.model", "Venue"),
    ("nautilus_trader.trading", "Strategy"),
]

# Attributes, not just symbols. `Strategy.strategy_id` is read on the live trade path
# (`positions_open(strategy_id=self._client.strategy_id)`).
PINNED_ATTRIBUTES = [("nautilus_trader.trading", "Strategy", "strategy_id")]


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
def test_the_exec_engine_defaults_we_rely_on_are_unchanged():
    from nautilus_trader.config import LiveExecutionEngineConfig

    config = LiveExecutionEngineConfig()
    assert config.reconciliation is True
    assert config.filter_unclaimed_external_orders is False, (
        "unclaimed external orders would stop materialising -- the external-order stream, the "
        "adopted-row sweep and the unmatched counter all go dark at once"
    )


# Existence is not enough: every drift this file exists to catch has been a SIGNATURE change --
# an argument removed, an argument newly required, a keyword rejected outright. These construct
# each config exactly the way `cli/engine/node.py` constructs it, so the pin fails on the call we
# actually make rather than on a name that happens to survive.
def test_the_kraken_client_configs_accept_the_arguments_we_pass():
    from nautilus_trader.adapters.kraken import KrakenDataClientConfig, KrakenExecutionClientConfig
    from nautilus_trader.model import AccountId, AccountType

    KrakenDataClientConfig()
    KrakenExecutionClientConfig(
        account_id=AccountId("KRAKEN-001"),
        api_key="a-key",
        api_secret="a-secret",
        spot_account_type=AccountType.MARGIN,
        margin_balance_asset="ZEUR",
        spot_positions_quote_currency="ZEUR",
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
@pytest.mark.parametrize(
    "name", ["builder", "add_strategy", "run", "stop", "dispose", "cache", "trader_id", "environment", "is_running"]
)
def test_the_node_still_exposes_every_member_the_engine_reads(name):
    from nautilus_trader.live import LiveNode

    assert hasattr(LiveNode, name), f"LiveNode.{name} is gone -- the engine reads it"


def test_the_exec_engine_config_accepts_the_arguments_we_pass():
    from nautilus_trader.config import LiveExecutionEngineConfig

    LiveExecutionEngineConfig(reconciliation=True, filter_unclaimed_external_orders=False)
