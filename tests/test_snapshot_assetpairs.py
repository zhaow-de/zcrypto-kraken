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
