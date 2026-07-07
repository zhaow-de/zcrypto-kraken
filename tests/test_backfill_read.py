from __future__ import annotations

from cli.backfill.read import dump_pair_name


def test_dump_pair_name_maps_all_universe_pairs():
    cases = {
        "BTC/EUR": "XBTEUR",
        "ETH/EUR": "ETHEUR",
        "SOL/EUR": "SOLEUR",
        "XRP/EUR": "XRPEUR",
        "ADA/EUR": "ADAEUR",
        "LINK/EUR": "LINKEUR",
        "DOGE/EUR": "XDGEUR",
        "LTC/EUR": "LTCEUR",
        "DOT/EUR": "DOTEUR",
        "AVAX/EUR": "AVAXEUR",
        "ETH/BTC": "ETHXBT",
        "SOL/BTC": "SOLXBT",
    }
    for sym, want in cases.items():
        assert dump_pair_name(sym) == want
