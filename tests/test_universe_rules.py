from dataclasses import dataclass

from cli.universe.rules import (
    DEFAULT_MAX_SPREAD_BPS,
    MAX_NAMES,
    MIN_NAMES,
    SPREAD_REFERENCE_NOTIONAL_EUR,
    finalize_universe,
)


@dataclass(frozen=True, kw_only=True)
class _Pair:
    symbol: str
    base: str
    quote: str
    margin_enabled: bool = True
    leverage_buy: tuple[int, ...] = (2, 3, 4)


def _entry(selection, symbol):
    return next(e for e in selection.entries if e["symbol"] == symbol)


def test_drops_name_below_leverage_floor():
    pairs = [_Pair(symbol="FOO/EUR", base="FOO", quote="EUR", leverage_buy=(1,))]
    volumes = {"FOO/EUR": 2_000_000.0}
    selection = finalize_universe(pairs, volumes)
    entry = _entry(selection, "FOO/EUR")
    assert entry["selected"] is False
    assert any("leverage" in reason for reason in entry["reasons"])


def test_drops_name_below_volume_floor():
    pairs = [_Pair(symbol="FOO/EUR", base="FOO", quote="EUR")]
    volumes = {"FOO/EUR": 10.0}
    selection = finalize_universe(pairs, volumes)
    entry = _entry(selection, "FOO/EUR")
    assert entry["selected"] is False
    assert any("volume" in reason for reason in entry["reasons"])


def test_mandatory_name_kept_even_when_failing_and_flagged():
    pairs = [_Pair(symbol="BTC/EUR", base="BTC", quote="EUR", leverage_buy=(1,))]
    volumes = {"BTC/EUR": 0.0}
    selection = finalize_universe(pairs, volumes)
    entry = _entry(selection, "BTC/EUR")
    assert entry["selected"] is True
    assert any("mandatory" in reason for reason in entry["reasons"])


def test_mandatory_does_not_force_a_non_eur_quoted_leg_sharing_the_base():
    # ETH/BTC shares base "ETH" with mandatory ETH/EUR but is the discretionary BTC-quoted leg (master plan §3).
    pairs = [_Pair(symbol="ETH/BTC", base="ETH", quote="BTC", leverage_buy=(1,))]
    volumes = {"ETH/BTC": 0.0}
    selection = finalize_universe(pairs, volumes)
    entry = _entry(selection, "ETH/BTC")
    assert entry["selected"] is False


def test_passing_entry_has_no_reasons():
    pairs = [_Pair(symbol="BTC/EUR", base="BTC", quote="EUR")]
    volumes = {"BTC/EUR": 2_000_000.0}
    selection = finalize_universe(pairs, volumes)
    entry = _entry(selection, "BTC/EUR")
    assert entry["selected"] is True
    assert entry["reasons"] == []


def test_candidate_at_200k_median_volume_passes_default_floor():
    # T0002: the lowered default floor admits names around €200k that the old €1M floor dropped.
    pairs = [_Pair(symbol="FOO/EUR", base="FOO", quote="EUR")]
    volumes = {"FOO/EUR": 200_000.0}
    selection = finalize_universe(pairs, volumes)
    entry = _entry(selection, "FOO/EUR")
    assert entry["selected"] is True
    assert entry["reasons"] == []


def test_escalate_true_when_selected_below_min_names():
    pairs = [_Pair(symbol=f"S{i}/EUR", base=f"S{i}", quote="EUR") for i in range(MIN_NAMES - 1)]
    volumes = {p.symbol: 2_000_000.0 for p in pairs}
    selection = finalize_universe(pairs, volumes)
    assert len(selection.selected) == MIN_NAMES - 1
    assert selection.escalate is True


def test_escalate_true_when_selected_above_max_names():
    pairs = [_Pair(symbol=f"S{i}/EUR", base=f"S{i}", quote="EUR") for i in range(MAX_NAMES + 1)]
    volumes = {p.symbol: 2_000_000.0 for p in pairs}
    selection = finalize_universe(pairs, volumes)
    assert len(selection.selected) == MAX_NAMES + 1
    assert selection.escalate is True


def test_escalate_false_when_selected_count_within_bounds():
    pairs = [_Pair(symbol=f"S{i}/EUR", base=f"S{i}", quote="EUR") for i in range(MIN_NAMES)]
    volumes = {p.symbol: 2_000_000.0 for p in pairs}
    selection = finalize_universe(pairs, volumes)
    assert len(selection.selected) == MIN_NAMES
    assert selection.escalate is False


# --- spread cap (T0024, spec 00067) -------------------------------------------------------------


def _pair(symbol, *, margin=True, leverage=(2, 5, 10)):
    base, quote = symbol.split("/")
    return _Pair(symbol=symbol, base=base, quote=quote, margin_enabled=margin, leverage_buy=leverage)


def test_omitting_spreads_screens_nothing_but_still_records_the_gap():
    """D4: the criterion is opt-in -- the selection outcome is unchanged for a caller that omits
    `spreads`. Pinning that against an explicit `spreads=None` would assert nothing: `None` is the
    default, so that is the same call twice."""
    pairs = [_pair("BTC/EUR"), _pair("DOT/EUR")]
    sel = finalize_universe(pairs, {"BTC/EUR": 1e7, "DOT/EUR": 2e5})
    assert sel.selected == ("BTC/EUR", "DOT/EUR")
    for entry in sel.entries:
        assert entry["spread_bps"] is None, "unscreened means null, not 0.0 and not absent"
        assert not any("spread" in r for r in entry["reasons"]), entry["reasons"]


def test_the_shipped_cap_and_reference_notional_are_pinned():
    """The tests that exercise the cap pass `max_spread_bps` explicitly and nothing here reads the
    notional, so nothing else in this file would notice an edit to either constant."""
    assert DEFAULT_MAX_SPREAD_BPS == 10.0
    assert SPREAD_REFERENCE_NOTIONAL_EUR == 1_400.0


def test_a_pair_wider_than_the_cap_is_rejected_with_the_numbers_in_the_reason():
    pairs = [_pair("WIDE/EUR")]
    sel = finalize_universe(pairs, {"WIDE/EUR": 1e7}, spreads={"WIDE/EUR": 25.0}, max_spread_bps=10.0)
    entry = sel.entries[0]
    assert entry["selected"] is False
    assert entry["spread_bps"] == 25.0
    assert any("25.0" in r and "10.0" in r for r in entry["reasons"]), entry["reasons"]


def test_a_pair_inside_the_cap_passes_and_records_its_spread():
    sel = finalize_universe([_pair("DOT/EUR")], {"DOT/EUR": 2e5}, spreads={"DOT/EUR": 6.548}, max_spread_bps=10.0)
    entry = sel.entries[0]
    assert entry["selected"] is True
    assert entry["spread_bps"] == 6.548
    assert not entry["reasons"]


def test_exactly_at_the_cap_passes():
    sel = finalize_universe([_pair("EDGE/EUR")], {"EDGE/EUR": 1e7}, spreads={"EDGE/EUR": 10.0}, max_spread_bps=10.0)
    assert sel.entries[0]["selected"] is True


def test_an_uncaptured_pair_is_recorded_as_unevaluated_and_NOT_rejected():
    """D3: a symbol outside the committed calibration is unevaluated, never auto-rejected -- absence
    of evidence is not evidence of a wide spread."""
    sel = finalize_universe([_pair("ETH/BTC")], {"ETH/BTC": 5.8e5}, spreads={"BTC/EUR": 0.4}, max_spread_bps=10.0)
    entry = sel.entries[0]
    assert entry["selected"] is True
    assert entry["spread_bps"] is None, "an unmeasured pair must be null, not 0.0 and not omitted"
    assert not entry["reasons"]


def test_spread_bps_is_present_on_every_entry_so_the_gap_is_visible():
    pairs = [_pair("BTC/EUR"), _pair("ETH/BTC")]
    sel = finalize_universe(pairs, {"BTC/EUR": 1e7, "ETH/BTC": 5.8e5}, spreads={"BTC/EUR": 0.428}, max_spread_bps=10.0)
    got = {e["symbol"]: e["spread_bps"] for e in sel.entries}
    assert got == {"BTC/EUR": 0.428, "ETH/BTC": None}


def test_a_mandatory_pair_breaching_the_cap_is_kept_but_flagged():
    """The spread reason rides the mandatory override like any other reason."""
    sel = finalize_universe([_pair("BTC/EUR")], {"BTC/EUR": 1e7}, spreads={"BTC/EUR": 99.0}, max_spread_bps=10.0)
    entry = sel.entries[0]
    assert entry["selected"] is True
    assert any("mandatory" in r for r in entry["reasons"])
    assert any("spread" in r for r in entry["reasons"])


def test_a_pair_failing_volume_and_spread_reports_both_reasons():
    sel = finalize_universe([_pair("THIN/EUR")], {"THIN/EUR": 1.0}, spreads={"THIN/EUR": 50.0}, max_spread_bps=10.0)
    reasons = sel.entries[0]["reasons"]
    assert sel.entries[0]["selected"] is False
    assert any("volume" in r for r in reasons)
    assert any("spread" in r for r in reasons)
