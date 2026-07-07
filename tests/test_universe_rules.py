from dataclasses import dataclass

from cli.universe.rules import MAX_NAMES, MIN_NAMES, finalize_universe


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
    # ETH/BTC shares base "ETH" with the mandatory ETH/EUR leg, but it is the discretionary
    # BTC-quoted relative-value leg (master plan §3), not the flagship EUR-quoted pair.
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
    # T0002: the lowered €150k/day floor admits names around €200k that the old €1M floor dropped.
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
