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


# --- spread cap rendering (T0024, spec 00067) ---------------------------------------------------


def _sel(entries):
    from cli.universe.rules import UniverseSelection

    return UniverseSelection(entries=tuple(entries))


def _entry(symbol, *, spread_bps, selected=True):
    return {
        "symbol": symbol,
        "selected": selected,
        "margin_enabled": True,
        "max_leverage": 5,
        "median_quote_volume": 1_000_000.0,
        "spread_bps": spread_bps,
        "reasons": [],
    }


CAP = {
    "max_spread_bps": 10.0,
    "reference_notional_eur": 1_400.0,
    "source": "cli/costs/spread.py (T0014, spec 00066) — mean effective spread at size",
    "unevaluated_count": 1,
}


def test_default_spread_cap_is_still_the_placeholder_string():
    file = build_universe_file(_sel([_entry("BTC/EUR", spread_bps=0.428)]), as_of="2026-07-22", params={}, provenance={})
    assert file["spread_cap"] == "pending-capture"


def test_a_structured_cap_is_embedded_verbatim():
    file = build_universe_file(
        _sel([_entry("BTC/EUR", spread_bps=0.428)]),
        as_of="2026-07-22",
        params={},
        provenance={},
        spread_cap=CAP,
    )
    assert file["spread_cap"] == CAP


def test_the_rendered_table_shows_the_spread_and_names_uncaptured_symbols():
    """D3: the null must be legible in the artifact a human reads, not only in the JSON."""
    file = build_universe_file(
        _sel([_entry("BTC/EUR", spread_bps=0.428), _entry("ETH/BTC", spread_bps=None)]),
        as_of="2026-07-22",
        params={},
        provenance={},
        spread_cap=CAP,
    )
    md = render_markdown(file)
    assert "Spread (bps/side)" in md
    assert "0.428" in md
    assert "not screened" in md, "an unscreened symbol must say so in the table, not render blank"


def test_the_rendered_cap_section_states_the_cap_and_the_unscreened_count():
    file = build_universe_file(
        _sel([_entry("BTC/EUR", spread_bps=0.428), _entry("ETH/BTC", spread_bps=None)]),
        as_of="2026-07-22",
        params={},
        provenance={},
        spread_cap=CAP,
    )
    md = render_markdown(file)
    assert "10.0" in md and "1,400" in md
    assert "1 of 2 symbols" in md


def test_the_placeholder_still_renders_without_the_structured_keys():
    """The legacy path must not require the four keys the structured record carries."""
    file = build_universe_file(_sel([_entry("BTC/EUR", spread_bps=None)]), as_of="2026-07-22", params={}, provenance={})
    md = render_markdown(file)
    assert "pending-capture" in md


def test_the_placeholder_path_does_not_claim_symbols_are_uncaptured():
    """On the placeholder path the criterion never ran, so every row is null -- including symbols
    with hundreds of captured hours. Rendering those as "not screened"/"not captured" would assert
    something false about the capture set rather than about the criterion (T0024 review)."""
    file = build_universe_file(_sel([_entry("BTC/EUR", spread_bps=None)]), as_of="2026-07-22", params={}, provenance={})
    md = render_markdown(file)
    assert "not screened" not in md and "not captured" not in md
    assert "| — |" in md
