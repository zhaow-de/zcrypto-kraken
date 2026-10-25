import math

import pytest

import cli.alpha.a2 as a2_module
from cli.alpha import A2Config, a2_book_returns
from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.a2 import _asset_directions_a2
from cli.alpha.b3 import b3_book_returns, centred_ranks, momentum_scores, rank_tilt
from cli.alpha.errors import AlphaError

_CONFIG = A2Config(lookbacks=(5, 10), short="off", target_vol=0.12, vol_lookback=20, basket_lookback=20, periods_per_year=2190)


def _prices(n: int = 300) -> dict[str, list[float | None]]:
    """Four assets trending at their own rates through their own waves, ETH missing one close and SOL listing at 40."""
    shapes = {"BTC": (100.0, 1.002, 0.08, 9.0), "ETH": (50.0, 1.003, 0.10, 7.0), "SOL": (20.0, 1.001, 0.12, 11.0)}
    shapes["XRP"] = (1.0, 1.0025, 0.09, 5.0)
    prices = {
        a: [level * growth**k * (1 + depth * math.sin(k / period + i)) for k in range(n)]
        for i, (a, (level, growth, depth, period)) in enumerate(shapes.items())
    }
    prices["ETH"][150] = None
    prices["SOL"][:40] = [None] * 40
    return prices


def test_momentum_scores_read_the_close_lookback_back_and_none_where_either_is_missing():
    prices = [1.0, 2.0, 4.0, None, 8.0, 10.0, 12.0]

    assert momentum_scores(prices, lookback=2) == [None, None, 3.0, None, 1.0, None]
    assert momentum_scores(prices, lookback=2) == momentum_scores([*prices[:6], 99.0], lookback=2)


@pytest.mark.parametrize("lookback", [1, 0, 2.0], ids=["one", "zero", "a-float"])
def test_momentum_scores_refuse_a_lookback_below_2(lookback):
    with pytest.raises(AlphaError, match="lookback must be an int >= 2"):
        momentum_scores([1.0, 2.0, 3.0], lookback=lookback)


def test_centred_ranks_run_from_the_weakest_at_minus_1_to_the_strongest_at_plus_1_ties_at_their_average():
    assert centred_ranks({"BTC": 0.1, "ETH": 0.3, "SOL": 0.2}) == {"BTC": -1.0, "SOL": 0.0, "ETH": 1.0}
    assert centred_ranks({"BTC": 0.1, "ETH": 0.1, "SOL": 0.3, "XRP": -0.2}) == {"XRP": -1.0, "BTC": 0.0, "ETH": 0.0, "SOL": 1.0}
    assert centred_ranks({"BTC": 0.5, "ETH": 0.5}) == {"BTC": 0.0, "ETH": 0.0}


def test_centred_ranks_refuse_fewer_than_2_scores():
    with pytest.raises(AlphaError, match="a rank needs 2 scores or more, got 1"):
        centred_ranks({"BTC": 0.1})


def test_the_tilt_ranks_the_basket_and_moves_the_longs_inside_their_sum():
    weights = {"BTC": 0.375, "ETH": 0.25, "SOL": 0.25, "XRP": 0.125}
    directions = {"BTC": 1.0, "ETH": 2 / 3, "SOL": 1 / 3, "XRP": 0.0}
    scores = {"BTC": 0.1, "ETH": 0.3, "SOL": 0.2, "XRP": 0.9}

    tilted, basket, longs = rank_tilt(weights, directions, scores, strength=0.5, floor=4)

    # The flat XRP ranks strongest, so ETH, SOL and BTC take z 1/3, -1/3 and -1: 7/6, 5/6 and 0.5 times, rescaled by
    # 0.875 / 0.6875; XRP's own weight is untouched.
    assert (basket, longs) == (4, 3) and tilted["XRP"] == 0.125
    for asset, times in (("BTC", 0.5), ("SOL", 5 / 6), ("ETH", 7 / 6)):
        assert math.isclose(tilted[asset], weights[asset] * times * 0.875 / 0.6875, rel_tol=1e-12)
    assert math.isclose(math.fsum(tilted[a] for a in ("BTC", "ETH", "SOL")), 0.875, rel_tol=1e-12)
    assert weights == {"BTC": 0.375, "ETH": 0.25, "SOL": 0.25, "XRP": 0.125}


_EIGHT = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC")


@pytest.mark.parametrize(
    ("unscored", "basket", "longs"),
    [pytest.param("LTC", 7, 0, id="seven-in-the-basket"), pytest.param(None, 8, 8, id="eight-in-the-basket")],
)
def test_the_tilt_engages_at_a_basket_of_8_and_not_at_7(unscored, basket, longs):
    weights = dict.fromkeys(_EIGHT, 0.125)
    scores = {a: None if a == unscored else 0.01 * i for i, a in enumerate(_EIGHT)}

    tilted, ranked, moved = rank_tilt(weights, dict.fromkeys(_EIGHT, 1.0), scores, strength=0.5, floor=8)

    assert (ranked, moved) == (basket, longs)
    if not longs:
        assert tilted is weights
    else:
        # Equal weights and every asset long: the rescale is 1, each asset 1 + 0.5 * (2 * rank - 9) / 7 times its weight.
        for rank, asset in enumerate(_EIGHT, 1):
            assert math.isclose(tilted[asset], 0.125 * (1 + 0.5 * (2 * rank - 9) / 7), rel_tol=1e-12)


@pytest.mark.parametrize(
    "directions",
    [
        pytest.param({"BTC": 1.0, "ETH": 0.0, "SOL": 0.0}, id="one-asset-long"),
        pytest.param({"BTC": 1.0, "ETH": None, "SOL": 0.0}, id="a-direction-missing"),
        pytest.param({"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}, id="none-long"),
    ],
)
def test_the_tilt_leaves_a_basket_with_fewer_than_2_longs_untilted(directions):
    weights = {"BTC": 0.5, "ETH": 0.25, "SOL": 0.25}

    tilted, basket, moved = rank_tilt(weights, directions, {"BTC": 0.1, "ETH": 0.2, "SOL": 0.3}, strength=0.5, floor=2)

    assert tilted is weights and (basket, moved) == (3, 0)


def test_the_tilt_ranks_no_asset_without_a_weight_or_a_score():
    weights = {"BTC": 0.5, "ETH": 0.0, "SOL": 0.5}

    tilted, basket, moved = rank_tilt(
        weights, dict.fromkeys(weights, 1.0), {"BTC": 0.1, "ETH": 0.2, "SOL": None}, strength=0.5, floor=2
    )

    assert tilted is weights and (basket, moved) == (1, 0)


def test_the_book_at_strength_0_is_a2s_book_to_the_bit():
    prices = _prices()

    book = b3_book_returns(prices, config=_CONFIG, score_lookback=30, strength=0.0, floor=3)

    assert {key: value for key, value in book.items() if key not in ("ranked", "tilted")} == a2_book_returns(prices, config=_CONFIG)
    assert max(book["tilted"]) >= 2


def test_the_book_is_a2s_book_on_the_tilted_weights(monkeypatch):
    prices = _prices()
    n = len(prices["BTC"]) - 1
    directions = _asset_directions_a2(
        prices, list(range(n + 1)), {a: [k for k, p in enumerate(v) if p is not None] for a, v in prices.items()}, config=_CONFIG
    )
    scores = {a: momentum_scores(v, lookback=30) for a, v in prices.items()}
    tilts = [
        rank_tilt(w, {a: directions[a][k] for a in prices}, {a: scores[a][k] for a in prices}, strength=0.5, floor=3)
        for k, w in enumerate(_inverse_vol_weights(prices, lookback=20))
    ]
    untilted = a2_book_returns(prices, config=_CONFIG)

    book = b3_book_returns(prices, config=_CONFIG, score_lookback=30, strength=0.5, floor=3)

    monkeypatch.setattr(a2_module, "_inverse_vol_weights", lambda prices_by_asset, *, lookback: [w for w, _, _ in tilts])
    assert {key: value for key, value in book.items() if key not in ("ranked", "tilted")} == a2_book_returns(prices, config=_CONFIG)
    assert (book["ranked"], book["tilted"]) == ([basket for _, basket, _ in tilts], [longs for _, _, longs in tilts])
    assert book["asset_positions"] != untilted["asset_positions"]
    assert book["book_base_returns"] != untilted["book_base_returns"]


def test_the_book_at_close_k_reads_no_price_after_k():
    prices = _prices()
    k = 241
    # Each asset's prices after k move by a factor of its own, so a score read past k reorders the ranks at k; every close's
    # presence is kept, since the weights at k, A2's own, read whether close k + 1 exists.
    later = {
        a: [*v[: k + 1], *(None if p is None else p * (1 + 0.3 * i) for p in v[k + 1 :])] for i, (a, v) in enumerate(prices.items())
    }

    book = b3_book_returns(prices, config=_CONFIG, score_lookback=30, strength=0.5, floor=3)
    moved = b3_book_returns(later, config=_CONFIG, score_lookback=30, strength=0.5, floor=3)

    assert all(book["asset_positions"][a][: k + 1] == moved["asset_positions"][a][: k + 1] for a in prices)
    assert (book["ranked"][: k + 1], book["tilted"][: k + 1]) == (moved["ranked"][: k + 1], moved["tilted"][: k + 1])
    assert book["asset_positions"] != moved["asset_positions"]


@pytest.mark.parametrize("strength", [-0.1, 1.0, math.nan, False], ids=["negative", "one", "nan", "a-bool"])
def test_the_book_refuses_a_strength_outside_0_to_1(strength):
    with pytest.raises(AlphaError, match="strength must be a number in"):
        b3_book_returns(_prices(), config=_CONFIG, score_lookback=30, strength=strength, floor=3)


def test_the_book_refuses_a_config_that_is_no_a2_config():
    with pytest.raises(AlphaError, match="config must be an A2Config"):
        b3_book_returns(_prices(), config={"lookbacks": (5, 10)}, score_lookback=30, strength=0.5, floor=3)


def test_the_book_refuses_a_score_lookback_below_2():
    with pytest.raises(AlphaError, match="score_lookback must be an int >= 2"):
        b3_book_returns(_prices(), config=_CONFIG, score_lookback=1, strength=0.5, floor=3)


def test_the_book_refuses_a_floor_below_2():
    with pytest.raises(AlphaError, match="floor must be an int >= 2"):
        b3_book_returns(_prices(), config=_CONFIG, score_lookback=30, strength=0.5, floor=1)
