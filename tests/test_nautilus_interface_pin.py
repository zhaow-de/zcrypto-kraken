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
