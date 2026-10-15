import math
import random
import re
from datetime import datetime, timedelta, timezone

import pytest

from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.a2 import A2Config, _asset_directions_a2, a2_book_returns
from cli.alpha.b1_rv import (
    a2_positions_with_weights,
    hourly_rv_inverse_vol_weights,
    per_year_mean_weights,
    weight_total_variation,
    weights_differ_count,
)
from cli.alpha.errors import AlphaError
from cli.benchmark.strategies import vol_target
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.research.subjects import _B1_A2_ARMS, _B1_LOOKBACK, PPY_4H

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
H1 = timedelta(hours=1)
H4 = timedelta(hours=4)
LOOKBACK = 4
# Bucket nets 2, -2, 0, 4, -2, 0, 2: no four consecutive equal, so no 4h window is flat.
SIGNS = [(1, 1, 1, -1), (1, -1, -1, -1), (1, 1, -1, -1), (1, 1, 1, 1), (-1, -1, -1, 1), (-1, -1, 1, 1), (1, -1, 1, 1)]


def _union_and_hourly(paths: dict[str, list[float | None]], start: datetime = START):
    hourly = {}
    last_close: dict[str, dict[datetime, float]] = {}
    for asset, path in paths.items():
        present = [(start + i * H1, c) for i, c in enumerate(path) if c is not None]
        hourly[asset] = ([h for h, _ in present], [c for _, c in present])
        # The measured seam: a 4h bar's close is the close of the last present hourly bar opened in [T, T + 4h).
        last_close[asset] = {start + (h - start) // H4 * H4: c for h, c in present}
    union_ts = sorted(set().union(*last_close.values()))
    prices = {asset: [last_close[asset].get(ts) for ts in union_ts] for asset in paths}
    return union_ts, prices, hourly


def _path(log_returns: list[float], c0: float = 100.0) -> list[float | None]:
    closes: list[float | None] = [c0]
    for r in log_returns:
        closes.append(closes[-1] * math.exp(r))
    return closes


def _random_path(seed: int, n_hours: int, scale: float) -> list[float | None]:
    rng = random.Random(seed)
    return _path([rng.uniform(-scale, scale) for _ in range(n_hours - 1)])


def _plain_paths(n_buckets: int) -> dict[str, list[float | None]]:
    return {
        "BTC": _random_path(1, 4 * n_buckets, 0.01),
        "ETH": _random_path(2, 4 * n_buckets, 0.02),
        "SOL": _random_path(3, 4 * n_buckets, 0.015),
    }


def _weights(paths: dict[str, list[float | None]]) -> list[dict[str, float]]:
    union_ts, prices, hourly = _union_and_hourly(paths)
    return hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)


def _hour(stamp: datetime) -> int:
    return (stamp - START) // H1


def test_the_weights_are_the_inverse_of_the_planted_hourly_realized_volatility():
    magnitudes = {"BTC": 0.01, "ETH": 0.02, "SOL": 0.035}
    paths = {asset: _path([SIGNS[(i // 4) % len(SIGNS)][i % 4] * m for i in range(1, 4 * 12)]) for asset, m in magnitudes.items()}
    union_ts, prices, hourly = _union_and_hourly(paths)
    weights = hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)
    for t in range(LOOKBACK, len(union_ts) - 1):
        lower, upper = union_ts[t - LOOKBACK] + H4, union_ts[t] + H4
        n_t = {asset: sum(1 for h in hourly[asset][0] if lower < h + H1 <= upper) for asset in magnitudes}
        s = {asset: math.sqrt(n_t[asset] * m**2 / 4) for asset, m in magnitudes.items()}
        total = sum(1 / v for v in s.values())
        assert set(weights[t]) == set(magnitudes), t
        for asset in magnitudes:
            assert math.isclose(weights[t][asset], (1 / s[asset]) / total, rel_tol=1e-12), (t, asset)
        assert abs(sum(weights[t].values()) - 1) <= 1e-15, t


def test_the_window_holds_the_bars_closing_after_its_lower_edge_through_the_decision_instant():
    paths = _plain_paths(10)
    union_ts, _, _ = _union_and_hourly(paths)
    base = _weights(paths)
    t = 6
    assert set(base[t]) == set(base[t + 1]) == {"BTC", "ETH", "SOL"}
    closing_at_lower = _hour(union_ts[t - LOOKBACK] + H4 - H1)
    closing_at_upper = _hour(union_ts[t] + H4 - H1)

    def stepped(j: int) -> list[dict[str, float]]:
        # The step is ln 2: doubling is exact in binary floating point, so every log return but bar j's is unchanged bit for bit.
        return _weights({**paths, "ETH": paths["ETH"][:j] + [c * 2.0 for c in paths["ETH"][j:]]})

    assert stepped(closing_at_lower)[t] == base[t]
    assert stepped(closing_at_lower + 1)[t] != base[t]
    assert stepped(closing_at_upper)[t] != base[t]
    after = stepped(closing_at_upper + 1)
    assert after[t] == base[t]
    assert after[t + 1] != base[t + 1]


def test_no_weight_reads_an_hourly_bar_closing_after_its_decision_instant():
    union_ts, prices, hourly = _union_and_hourly(_plain_paths(12))
    full = hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)
    for n in range(LOOKBACK + 1, len(union_ts) - 1):
        assert full[n - 1], n
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        truncated = {}
        for asset, (stamps, closes) in hourly.items():
            keep = [i for i, h in enumerate(stamps) if h + timedelta(hours=1) <= cutoff]
            assert len(keep) < len(stamps), (n, asset)
            truncated[asset] = ([stamps[i] for i in keep], [closes[i] for i in keep])
        prefix_prices = {asset: p[: n + 1] for asset, p in prices.items()}
        prefix = hourly_rv_inverse_vol_weights(prefix_prices, union_ts[: n + 1], truncated, lookback=LOOKBACK)
        assert prefix == full[:n], n


def test_a_gap_return_and_the_edge_return_reach_back_to_the_previous_present_bar():
    # At t = 8 the window holds the bars opened at hours 20 through 35 (the union is contiguous from START).
    t = 8
    paths = _plain_paths(12)
    rng = random.Random(4)
    eth_returns = {h: rng.uniform(-0.02, 0.02) for h in range(1, 48)}
    eth_returns[29] = eth_returns[30] = 0.0
    eth_returns[31] = 0.08
    eth = _path([eth_returns[h] for h in range(1, 48)])
    eth[19] = eth[29] = eth[30] = None
    paths["ETH"] = eth
    union_ts, prices, hourly = _union_and_hourly(paths)
    assert union_ts[t - LOOKBACK] + H4 == START + 20 * H1 and union_ts[t] + H4 == START + 36 * H1
    assert START + 18 * H1 + H1 < union_ts[t - LOOKBACK] + H4

    def squares(path: list[float | None], pairs: list[tuple[int, int]]) -> list[float]:
        return [math.log(path[b] / path[a]) ** 2 for a, b in pairs]

    consecutive = [(h - 1, h) for h in range(20, 36)]
    eth_pairs = [(18, 20)] + [(h - 1, h) for h in range(21, 29)] + [(28, 31)] + [(h - 1, h) for h in range(32, 36)]
    rv = {
        "BTC": math.fsum(squares(paths["BTC"], consecutive)),
        "ETH": math.fsum(squares(eth, eth_pairs)),
        "SOL": math.fsum(squares(paths["SOL"], consecutive)),
    }
    inv = {asset: 1.0 / math.sqrt(v / LOOKBACK) for asset, v in rv.items()}
    expected = {asset: v / sum(inv.values()) for asset, v in inv.items()}

    weights = hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)[t]
    assert set(weights) == set(expected)
    for asset in expected:
        assert math.isclose(weights[asset], expected[asset], rel_tol=1e-12), asset


def _with_missing_4h_bar(paths: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    ada = _random_path(5, len(paths["BTC"]), 0.02)
    ada[28:32] = [None] * 4
    return {**paths, "ADA": ada}


def _assert_arm_a_s_sets(paths: dict[str, list[float | None]]) -> list[dict[str, float]]:
    union_ts, prices, hourly = _union_and_hourly(paths)
    fed = _ffill_btc(prices)
    weights = hourly_rv_inverse_vol_weights(fed, union_ts, hourly, lookback=LOOKBACK)
    assert [set(w) for w in weights] == [set(w) for w in _inverse_vol_weights(fed, lookback=LOOKBACK)]
    return weights


def test_the_weighted_asset_set_is_arm_a_s_over_a_listing_a_missing_bar_a_flat_window_and_a_filled_btc():
    paths = _with_missing_4h_bar(_plain_paths(16))
    paths["SOL"][:12] = [None] * 12
    dot = _random_path(6, 64, 0.02)
    dot[23:40] = [dot[23]] * 17
    paths["DOT"] = dot
    paths["BTC"][36:40] = [None] * 4
    union_ts, prices, _ = _union_and_hourly(paths)
    assert prices["BTC"][9] is None and len(union_ts) == 16
    fed = _ffill_btc(prices)
    weights = _assert_arm_a_s_sets(paths)
    assert any(len(weights[t]) < sum(fed[asset][t] is not None for asset in fed) for t in range(LOOKBACK, len(weights)))


def test_the_weighted_asset_set_is_arm_a_s_where_a_missing_4h_bar_is_still_in_the_window():
    _assert_arm_a_s_sets(_with_missing_4h_bar(_plain_paths(16)))


def _refused_at(t: int, reason: str) -> str:
    return re.escape(f"'ETH' at {(START + t * H4).isoformat()} (return index {t}): {reason}")


def _eth_hourly_kept(hourly, keep) -> None:
    stamps, closes = hourly["ETH"]
    hourly["ETH"] = ([h for h in stamps if keep(h)], [c for h, c in zip(stamps, closes) if keep(h)])


def test_an_asset_arm_a_weights_with_no_hourly_bar_in_its_window_is_refused():
    union_ts, prices, hourly = _union_and_hourly(_plain_paths(10))
    lower, upper = union_ts[0] + H4, union_ts[LOOKBACK] + H4
    _eth_hourly_kept(hourly, lambda h: not lower < h + H1 <= upper)
    with pytest.raises(AlphaError, match=_refused_at(LOOKBACK, "no hourly bar closes inside the window")):
        hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)


def test_an_asset_whose_first_windowed_bar_has_no_predecessor_row_is_refused():
    union_ts, prices, hourly = _union_and_hourly(_plain_paths(10))
    _eth_hourly_kept(hourly, lambda h: h + H1 > union_ts[0] + H4)
    with pytest.raises(AlphaError, match=_refused_at(LOOKBACK, "the window's first hourly bar has no predecessor row")):
        hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)


def test_an_asset_whose_hourly_closes_are_flat_while_its_4h_closes_move_is_refused():
    union_ts, prices, hourly = _union_and_hourly(_plain_paths(10))
    stamps, closes = hourly["ETH"]
    lower, upper = union_ts[0] + H4, union_ts[LOOKBACK] + H4
    flat = closes[3]
    hourly["ETH"] = (stamps, [flat if lower <= h + H1 <= upper else c for h, c in zip(stamps, closes)])
    assert len({prices["ETH"][k] for k in range(LOOKBACK + 1)}) > 1
    with pytest.raises(AlphaError, match=_refused_at(LOOKBACK, "the window's hourly realized variance is 0")):
        hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)


def _eth_4h_close(value):
    return lambda u, p, h: (u, {**p, "ETH": p["ETH"][:5] + [value] + p["ETH"][6:]}, h)


def _eth_hourly_stamps(edit):
    return lambda u, p, h: (u, p, {**h, "ETH": (edit(h["ETH"][0]), h["ETH"][1])})


def _eth_hourly_close(value):
    return lambda u, p, h: (u, p, {**h, "ETH": (h["ETH"][0], h["ETH"][1][:5] + [value] + h["ETH"][1][6:])})


def _union(edit):
    return lambda u, p, h: (edit(u), p, h)


@pytest.mark.parametrize(
    "broken,match",
    [
        pytest.param(_eth_4h_close(0.0), "prices must be None or finite positive numbers, got 0.0", id="4h-close-0"),
        pytest.param(
            _eth_hourly_stamps(lambda s: s[:5] + [s[6], s[5]] + s[7:]),
            "hourly stamps must be strictly increasing, violated at index 6",
            id="hourly-stamps-not-increasing",
        ),
        pytest.param(
            _eth_hourly_stamps(lambda s: s[:5] + [s[5].replace(tzinfo=None)] + s[6:]),
            "hourly stamps must be tz-aware",
            id="hourly-stamp-tz-naive",
        ),
        pytest.param(
            _eth_hourly_close(0.0), "hourly closes must be finite numbers above 0, got 0.0 at index 5", id="hourly-close-0"
        ),
        pytest.param(
            _eth_hourly_close(math.nan), "hourly closes must be finite numbers above 0, got nan at index 5", id="hourly-close-nan"
        ),
        pytest.param(
            _eth_hourly_close(math.inf), "hourly closes must be finite numbers above 0, got inf at index 5", id="hourly-close-inf"
        ),
        pytest.param(
            _eth_hourly_close(None), "hourly closes must be finite numbers above 0, got None at index 5", id="hourly-close-None"
        ),
        pytest.param(
            lambda u, p, h: (u, p, {asset: series for asset, series in h.items() if asset != "ETH"}),
            "hourly_by_asset must hold exactly the price assets ['BTC', 'ETH', 'SOL'], got ['BTC', 'SOL']",
            id="hourly-asset-set",
        ),
        pytest.param(
            _union(lambda u: u[:6] + [u[6] - (LOOKBACK + 1) * H4] + u[7:]),
            "union_ts must be strictly increasing, violated at index 6",
            id="union-not-increasing",
        ),
        pytest.param(
            _union(lambda u: u[:3] + [u[3].replace(tzinfo=None)] + u[4:]),
            "union_ts stamps must be tz-aware",
            id="union-stamp-tz-naive",
        ),
        pytest.param(_union(lambda u: u[:-1]), "union_ts must have the price lists' length 10, got 9", id="union-length"),
    ],
)
def test_bad_input_is_refused(broken, match):
    union_ts, prices, hourly = broken(*_union_and_hourly(_plain_paths(10)))
    with pytest.raises(AlphaError, match=re.escape(match)):
        hourly_rv_inverse_vol_weights(prices, union_ts, hourly, lookback=LOOKBACK)


_SMALL_A2 = A2Config(lookbacks=(5, 10, 20), short="off", target_vol=0.12, vol_lookback=12, basket_lookback=8, periods_per_year=2190)


def _book_prices(n: int) -> dict[str, list[float | None]]:
    # SOL lists a quarter of the way in and ADA misses one bar mid-history.
    prices = {
        "BTC": _random_path(11, n, 0.02),
        "ETH": _random_path(12, n, 0.03),
        "SOL": _random_path(13, n, 0.04),
        "ADA": _random_path(14, n, 0.025),
    }
    prices["SOL"][: n // 4] = [None] * (n // 4)
    prices["ADA"][n // 2] = None
    return prices


@pytest.mark.parametrize(
    "config,n",
    [pytest.param(_SMALL_A2, 400, id="vol-12-basket-8")]
    + [
        pytest.param(
            A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B1_LOOKBACK,
                basket_lookback=_B1_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
            600,
            id=f"adopted-{'-'.join(map(str, lookbacks))}-{target_vol}",
        )
        for lookbacks, target_vol in _B1_A2_ARMS
    ],
)
def test_given_arm_a_s_weights_the_book_is_a2_s_own(config, n):
    prices = _book_prices(n)
    expected = a2_book_returns(prices, config=config)["asset_positions"]
    assert all(any(expected[asset]) for asset in prices)
    weights = _inverse_vol_weights(prices, lookback=config.basket_lookback)
    assert a2_positions_with_weights(prices, weights, config=config) == expected


def _btc_alone(weights_a: list[dict[str, float]]) -> list[dict[str, float]]:
    return [{"BTC": 1.0} if w else {} for w in weights_a]


def _half_moved_to_ada(weights_a: list[dict[str, float]]) -> list[dict[str, float]]:
    return [{"BTC": 0.5, "ADA": 0.5} if w else {} for w in weights_a]


@pytest.mark.parametrize("plant", [pytest.param(_btc_alone, id="btc-alone"), pytest.param(_half_moved_to_ada, id="half-to-ada")])
def test_the_book_holds_the_given_weights_at_the_vol_target_of_the_base_returns_they_make(plant):
    c = _SMALL_A2
    prices = _book_prices(400)
    n = len(prices["BTC"])
    weights = plant(_inverse_vol_weights(prices, lookback=c.basket_lookback))
    assert weights != _inverse_vol_weights(prices, lookback=c.basket_lookback)
    asset_ts = {a: [k for k, p in enumerate(series) if p is not None] for a, series in prices.items()}
    d = _asset_directions_a2(prices, list(range(n)), asset_ts, config=c)
    r = {
        a: [p[k + 1] / p[k] - 1 if p[k] is not None and p[k + 1] is not None else None for k in range(n - 1)]
        for a, p in prices.items()
    }
    base = []
    for k in range(n - 1):
        # Term by term, as the book adds: `sum()` over floats is compensated, so its last bit can differ.
        total = 0.0
        for a in prices:
            if d[a][k] is not None and r[a][k] is not None:
                total += weights[k].get(a, 0.0) * d[a][k] * r[a][k]
        base.append(total)
    lev = vol_target(
        base, target_vol=c.target_vol / math.sqrt(c.periods_per_year), lookback=c.vol_lookback, max_leverage=c.max_leverage
    )
    assert any(0.0 < x < c.max_leverage for x in lev)
    expected = {a: [weights[k].get(a, 0.0) * (d[a][k] or 0.0) * lev[k] for k in range(n - 1)] for a in prices}
    assert a2_positions_with_weights(prices, weights, config=c) == expected


@pytest.mark.parametrize(
    "edit,match",
    [
        pytest.param(lambda w: w[:-1], "weights must hold one dict per return index, 399, got 398", id="weights-one-short"),
        pytest.param(lambda w: w + [{}], "weights must hold one dict per return index, 399, got 400", id="weights-one-long"),
        pytest.param(
            lambda w: w[:50] + [{**w[50], "XRP": 0.5}] + w[51:],
            "weights at return index 50 name assets the prices lack: ['XRP']",
            id="weight-for-an-asset-the-prices-lack",
        ),
    ],
)
def test_the_book_refuses_weights_that_do_not_fit_the_prices(edit, match):
    prices = _book_prices(400)
    weights = edit(_inverse_vol_weights(prices, lookback=_SMALL_A2.basket_lookback))
    with pytest.raises(AlphaError, match=re.escape(match)):
        a2_positions_with_weights(prices, weights, config=_SMALL_A2)


def test_weights_differ_count_counts_the_return_indices_whose_dicts_differ():
    weights_a = [{}, {"A": 1.0}, {"A": 0.5, "B": 0.5}, {"A": 0.75, "B": 0.25}]
    weights_b = [{}, {"A": 1.0}, {"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}]
    assert weights_differ_count(weights_a, weights_b) == 1


def test_weights_differ_count_refuses_key_sets_that_differ_naming_the_return_index():
    weights_a = [{}, {"A": 1.0}, {"A": 1.0}, {"A": 1.0}]
    weights_b = [{}, {"A": 1.0}, {"A": 0.5, "B": 0.5}, {"A": 1.0}]
    with pytest.raises(AlphaError, match=re.escape("differ at return index 2: ['A'] against ['A', 'B']")):
        weights_differ_count(weights_a, weights_b)


def test_weights_differ_count_refuses_lists_of_unequal_length():
    with pytest.raises(AlphaError, match=re.escape("must have equal length, got 2 and 3")):
        weights_differ_count([{}, {"A": 1.0}], [{}, {"A": 1.0}, {"A": 1.0}])


def test_weight_total_variation_counts_every_move_from_an_empty_start_and_an_asset_that_leaves():
    assert weight_total_variation([{}, {"A": 1.0}, {"A": 0.75, "B": 0.25}, {"B": 1.0}]) == 3.0


def test_weight_total_variation_counts_a_non_empty_first_dict_against_the_empty_previous():
    # Index 0 against {}: 0.75 + 0.25; index 1: A leaves 0.75 and B rises 0.75.
    assert weight_total_variation([{"A": 0.75, "B": 0.25}, {"B": 1.0}]) == 2.5


def _year_case() -> tuple[list[dict[str, float]], list[dict[str, float]], list[datetime]]:
    # Return index 2 opens 2015-12-31 20:00 and closes 2016-01-01 00:00.
    union_ts = [datetime(2015, 12, 31, h, tzinfo=timezone.utc) for h in (12, 16, 20)]
    union_ts += [datetime(2016, 1, 1, h, tzinfo=timezone.utc) for h in (0, 4)]
    weights_a = [{}, {"BTC": 0.5, "ETH": 0.5}, {"BTC": 0.75, "ETH": 0.25}, {"BTC": 1.0}]
    weights_b = [{}, {"BTC": 0.25, "ETH": 0.75}, {"BTC": 0.5, "ETH": 0.5}, {"BTC": 1.0}]
    return weights_a, weights_b, union_ts


def test_per_year_mean_weights_keys_a_return_index_by_its_bar_start_year_arm_b_s_mean_first():
    weights_a, weights_b, union_ts = _year_case()
    assert per_year_mean_weights(weights_a, weights_b, union_ts, ["BTC", "ETH"]) == {
        "BTC": {"2015": [0.75 / 3, 1.25 / 3], "2016": [1.0, 1.0]},
        "ETH": {"2015": [1.25 / 3, 0.75 / 3], "2016": [0.0, 0.0]},
    }


def test_per_year_mean_weights_refuses_a_union_one_stamp_short():
    weights_a, weights_b, union_ts = _year_case()
    with pytest.raises(AlphaError, match=re.escape("got 4 stamps, 4 and 4 dicts")):
        per_year_mean_weights(weights_a, weights_b, union_ts[:-1], ["BTC", "ETH"])


def test_per_year_mean_weights_refuses_weights_b_one_dict_short_of_weights_a():
    weights_a, weights_b, union_ts = _year_case()
    with pytest.raises(AlphaError, match=re.escape("got 5 stamps, 4 and 3 dicts")):
        per_year_mean_weights(weights_a, weights_b[:-1], union_ts, ["BTC", "ETH"])
