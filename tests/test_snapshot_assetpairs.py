import json
from pathlib import Path

from cli.snapshot.assetpairs import derive_universe

_FIXTURES = Path(__file__).parent / "fixtures"
ASSETPAIRS = json.loads((_FIXTURES / "kraken_assetpairs.json").read_text())
ASSETS = json.loads((_FIXTURES / "kraken_assets.json").read_text())


def _by_symbol(rows, symbol):
    return next(r for r in rows if r.symbol == symbol)


def test_btc_eur_resolves_margin_enabled_with_leverage():
    rows = derive_universe(ASSETPAIRS, ASSETS, ["BTC/EUR"])
    row = _by_symbol(rows, "BTC/EUR")
    assert row.found is True
    assert row.pair_key == "XXBTZEUR"
    assert row.wsname == "XBT/EUR"
    assert row.margin_enabled is True
    assert row.leverage_buy == (2, 3, 4, 5, 6, 7, 8, 9, 10)


def test_aliases_resolved_from_assets_result():
    rows = derive_universe(ASSETPAIRS, ASSETS, ["BTC/EUR", "DOGE/EUR"])
    btc = _by_symbol(rows, "BTC/EUR")
    doge = _by_symbol(rows, "DOGE/EUR")
    assert btc.base_altname == "XBT"
    assert doge.base_altname == "XDG"


def test_non_margin_symbol_flagged_not_dropped():
    rows = derive_universe(ASSETPAIRS, ASSETS, ["1INCH/EUR"])
    row = _by_symbol(rows, "1INCH/EUR")
    assert row.found is True
    assert row.margin_enabled is False
    assert row.leverage_buy == ()


def test_absent_symbol_flagged_missing_not_dropped():
    rows = derive_universe(ASSETPAIRS, ASSETS, ["FOO/EUR"])
    row = _by_symbol(rows, "FOO/EUR")
    assert row.found is False
    assert row.margin_enabled is False


def test_btc_quoted_rv_leg_resolves_via_xbt_wsname_token():
    rows = derive_universe(ASSETPAIRS, ASSETS, ["ETH/BTC", "SOL/BTC"])
    eth_btc = _by_symbol(rows, "ETH/BTC")
    sol_btc = _by_symbol(rows, "SOL/BTC")
    assert eth_btc.found is True and eth_btc.pair_key == "XETHXXBT"
    assert sol_btc.found is True and sol_btc.pair_key == "SOLXBT"
    assert eth_btc.quote_altname == "XBT"


def test_fee_schedule_is_extracted_per_pair():
    row = _by_symbol(derive_universe(ASSETPAIRS, ASSETS, ["BTC/EUR"]), "BTC/EUR")
    assert row.fee_taker_base == 0.4
    assert row.fee_maker_base == 0.25
    assert row.fees_taker[0] == (0, 0.4)
    assert len(row.fees_taker) == len(row.fees_maker) > 1


def test_borrow_rate_and_collateral_come_from_the_base_ASSET():
    rows = derive_universe(ASSETPAIRS, ASSETS, ["BTC/EUR", "AVAX/EUR"])
    btc, avax = _by_symbol(rows, "BTC/EUR"), _by_symbol(rows, "AVAX/EUR")
    # distinct values, so a wrong-asset lookup cannot pass by coincidence
    assert btc.base_margin_rate == 0.01
    assert avax.base_margin_rate == 0.03
    assert btc.base_collateral_value == 0.99
    assert avax.base_collateral_value == 0.9


def test_margin_and_position_limits_are_extracted():
    row = _by_symbol(derive_universe(ASSETPAIRS, ASSETS, ["BTC/EUR"]), "BTC/EUR")
    assert row.margin_call == 80
    assert row.margin_stop == 40
    assert row.long_position_limit == 130
    assert row.short_position_limit == 100


def test_absent_symbol_carries_the_new_fields_as_empty_not_missing():
    row = _by_symbol(derive_universe(ASSETPAIRS, ASSETS, ["NOSUCH/EUR"]), "NOSUCH/EUR")
    assert row.found is False
    assert row.fees_taker == () and row.fees_maker == ()
    assert row.fee_taker_base is None and row.base_margin_rate is None
    assert row.margin_call is None and row.short_position_limit is None


def test_quote_borrow_rate_is_extracted_because_it_prices_LONGS():
    """A margin long borrows the QUOTE currency, so the base-side rate never prices it."""
    rows = derive_universe(ASSETPAIRS, ASSETS, ["BTC/EUR", "ETH/BTC"])
    eur_quoted, btc_quoted = _by_symbol(rows, "BTC/EUR"), _by_symbol(rows, "ETH/BTC")
    # EUR leg vs BTC leg: distinct values, so a base/quote mix-up cannot pass by coincidence
    assert eur_quoted.quote_margin_rate == 0.02  # ZEUR
    assert btc_quoted.quote_margin_rate == 0.01  # XXBT
    assert btc_quoted.base_margin_rate == 0.02  # XETH — base and quote genuinely differ here
