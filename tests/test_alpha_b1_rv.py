import math
import random
import re
from datetime import datetime, timedelta, timezone

import pytest

from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.b1_rv import hourly_rv_inverse_vol_weights
from cli.alpha.errors import AlphaError
from cli.portfolio.crossfreq_system import _ffill_btc

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
