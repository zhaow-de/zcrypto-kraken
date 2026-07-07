from dataclasses import dataclass

from cli.universe.build import build_universe_file, render_markdown
from cli.universe.rules import finalize_universe


@dataclass(frozen=True, kw_only=True)
class _Pair:
    symbol: str
    base: str
    quote: str
    margin_enabled: bool = True
    leverage_buy: tuple[int, ...] = (2, 3, 4)


PAIRS = [
    _Pair(symbol="BTC/EUR", base="BTC", quote="EUR"),
    _Pair(symbol="ETH/EUR", base="ETH", quote="EUR"),
    _Pair(symbol="FOO/EUR", base="FOO", quote="EUR", leverage_buy=(1,)),
]
VOLUMES = {"BTC/EUR": 5_000_000.0, "ETH/EUR": 3_000_000.0, "FOO/EUR": 10.0}
AS_OF = "2026-07-07"
PARAMS = {"min_leverage": 2, "min_median_quote_volume": 1_000_000.0, "window": 30}
PROVENANCE = {"snapshot_sha256": "a" * 64, "ohlc_dataset_hash": "b" * 64}


def test_build_universe_file_deterministic_given_fixed_inputs():
    selection = finalize_universe(PAIRS, VOLUMES)
    a = build_universe_file(selection, as_of=AS_OF, params=PARAMS, provenance=PROVENANCE)
    b = build_universe_file(selection, as_of=AS_OF, params=PARAMS, provenance=PROVENANCE)
    assert a == b
    assert a["as_of"] == AS_OF
    assert a["selected"] == ["BTC/EUR", "ETH/EUR"]
    assert a["params"] == PARAMS
    assert a["provenance"] == PROVENANCE
    assert a["spread_cap"] == "pending-capture"


def test_render_markdown_contains_selected_names_params_and_spread_note():
    selection = finalize_universe(PAIRS, VOLUMES)
    file = build_universe_file(selection, as_of=AS_OF, params=PARAMS, provenance=PROVENANCE)
    md = render_markdown(file)
    assert "BTC/EUR" in md
    assert "ETH/EUR" in md
    assert str(PARAMS["min_median_quote_volume"]) in md
    assert str(PARAMS["min_leverage"]) in md
    assert "pending-capture" in md
