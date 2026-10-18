from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.a2 import A2Config, _asset_directions_a2, _donchian_signal, a2_book_returns
from cli.alpha.b1_volume import (
    a2_positions_on_directions,
    asset_directions_confirmed,
    confirmations_by_asset,
    directions_differ_per_year,
    donchian_signal_confirmed,
    entry_events_per_year,
    volume_confirmations,
)
from cli.alpha.errors import AlphaError
from cli.portfolio.crossfreq_system import _ffill_btc

_T0 = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday
_H4, _DAY, _WEEK = timedelta(hours=4), timedelta(days=1), timedelta(days=7)
_SMALL = A2Config(lookbacks=(5, 10, 20), short="off", target_vol=0.12, vol_lookback=12, basket_lookback=8, periods_per_year=2190)
_ADOPTED = tuple(
    A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
)


def _stamps(n: int, step: timedelta = _H4) -> list[datetime]:
    return [_T0 + i * step for i in range(n)]


def _union(n: int) -> dict[str, list[float | None]]:
    prices = {
        asset: [100.0 * 1.001**k * (1 + 0.05 * math.sin(k / 7.0 + i * 0.7)) for k in range(n)]
        for i, asset in enumerate(("BTC", "ETH", "SOL"))
    }
    prices["ETH"][:30] = [None] * 30
    prices["SOL"][50] = None
    return prices


def _index(prices: dict[str, list[float | None]]) -> tuple[list[int], dict[str, list[int]]]:
    n = len(prices["BTC"])
    return list(range(n)), {asset: [k for k, p in enumerate(ps) if p is not None] for asset, ps in prices.items()}


def test_the_level_is_the_median_of_the_prior_bars_and_never_the_bar_itself():
    # lookback 3, the shape at 1: bar 3's level is median(100, 10, 50) = 50 > 20, where median(10, 50, 20) = 20 — bar 3 in
    # its own window — would accept it; bar 4: median(10, 50, 20) = 20, accepted at equality; bar 5: median(50, 20, 20) = 20 > 19.
    volumes = [100.0, 10.0, 50.0, 20.0, 20.0, 19.0]
    assert volume_confirmations(_stamps(6), volumes, lookback=3, min_cell_obs=100) == [True, True, True, False, True, False]
    # lookback 2, an even count, the median the mean of the two middle values: bar 2's level is median(10, 30) = 20 > 15, bar
    # 3's median(30, 15) = 22.5 <= 25; median_low's 10 and 15 would accept every bar.
    assert volume_confirmations(_stamps(4), [10.0, 30.0, 15.0, 25.0], lookback=2, min_cell_obs=100) == [True, True, False, True]


def test_the_hour_of_week_shape_binds_at_min_cell_obs_earlier_observations():
    # Weekly stamps, one cell; lookback 2, min_cell_obs 2. Bar 2: L = 16, no observation, S = 1, 32 >= 16, ratio 2.0. Bar 3:
    # L = 28, one observation, S = 1, 28 >= 28, ratio 1.0. Bar 4: L = 30, S = median(2.0, 1.0) = 1.5, 40 < 45.0, its ratio
    # 4/3 kept though it is rejected. Bar 5: L = 34, S = median(2.0, 1.0, 4/3) = 4/3, 46 >= 45.33. With S held at 1 bar 4
    # would be accepted; the mean, 13/9, would reject bar 5 (46 < 49.11), and so would S without bar 4's ratio (1.5, 46 < 51).
    volumes = [8.0, 24.0, 32.0, 28.0, 40.0, 46.0]
    assert volume_confirmations(_stamps(6, _WEEK), volumes, lookback=2, min_cell_obs=2) == [True, True, True, True, False, True]
    # lookback 1, an even count of ratios: bar 3's L = 30, S = median(1.0, 3.0) = 2.0, 70 >= 60; median_high's 3.0 would
    # reject it.
    assert volume_confirmations(_stamps(4, _WEEK), [10.0, 10.0, 30.0, 70.0], lookback=1, min_cell_obs=2) == [True] * 4
    # Each ratio read against its own L: bars 1 and 2 add 20 / 10 and 40 / 20, so bar 3's L = 40, S = 2.0, 70 < 80; read
    # against E, bar 2's ratio is 40 / 40 = 1.0, S = 1.5 and bar 3 accepted.
    volumes = [10.0, 20.0, 40.0, 70.0]
    assert volume_confirmations(_stamps(4, _WEEK), volumes, lookback=1, min_cell_obs=1) == [True, True, True, False]


@pytest.mark.parametrize(
    "stamps",
    [
        pytest.param([_T0 + w * _WEEK + d * _DAY for w in range(3) for d in range(2)], id="two-weekdays-one-hour"),
        pytest.param([_T0 + w * _WEEK + h * _H4 for w in range(3) for h in range(2)], id="two-hours-one-weekday"),
    ],
)
def test_each_hour_of_week_cell_holds_its_own_ratios(stamps):
    # Two cells alternate, Monday and Tuesday at 04:00 or Monday at 04:00 and 08:00; lookback 2, min_cell_obs 1. Bar 4:
    # L = median(10, 30) = 20, S = its own cell's 1.0, 20 >= 20; a key pooling the two cells, the hour alone on the first row
    # and the weekday alone on the second, would add the other cell's 3.0, S = 2.0.
    volumes = [10.0, 10.0, 10.0, 30.0, 20.0, 20.0]
    assert volume_confirmations(stamps, volumes, lookback=2, min_cell_obs=1) == [True, True, True, True, True, False]


def test_the_warm_up_accepts_every_bar_and_a_missing_volume_after_it_never_confirms():
    # lookback 3: a missing volume is no bar, so the warm-up lasts to index 4; index 5 has no volume; index 6:
    # L = median(10, 20, 30) = 20 <= 25.
    volumes = [None, 10.0, 20.0, None, 30.0, None, 25.0]
    assert volume_confirmations(_stamps(7), volumes, lookback=3, min_cell_obs=100) == [True, True, True, True, True, False, True]


def test_a_history_shorter_than_the_lookback_accepts_every_entry():
    assert volume_confirmations(_stamps(5), [5.0, 1.0, 9.0, 0.5, 3.0], lookback=180, min_cell_obs=100) == [True] * 5


def test_no_flag_reads_a_later_bar():
    stamps, volumes = _stamps(120), [10.0 + 9.0 * math.sin(2.7 * i) for i in range(120)]
    full = volume_confirmations(stamps, volumes, lookback=5, min_cell_obs=1)
    assert any(full[5:]) and not all(full[5:])
    for n in range(1, 121):
        assert volume_confirmations(stamps[:n], volumes[:n], lookback=5, min_cell_obs=1) == full[:n]


@pytest.mark.parametrize(
    ("stamps", "volumes", "over", "match"),
    [
        pytest.param(_stamps(3), [1.0, 0.0, 1.0], {}, "volume must be a finite number above 0", id="zero-volume"),
        pytest.param(_stamps(3), [1.0, -1.0, 1.0], {}, "volume must be a finite number above 0", id="negative-volume"),
        pytest.param(_stamps(3), [1.0, math.nan, 1.0], {}, "volume must be a finite number above 0", id="nan-volume"),
        pytest.param(_stamps(3), [1.0, math.inf, 1.0], {}, "volume must be a finite number above 0", id="inf-volume"),
        pytest.param(_stamps(3), [1.0, True, 1.0], {}, "volume must be a finite number above 0", id="bool-volume"),
        pytest.param([_T0, _T0, _T0 + _H4], [1.0] * 3, {}, "strictly increasing", id="repeated-stamp"),
        pytest.param([_T0.replace(tzinfo=None), _T0 + _H4, _T0 + 2 * _H4], [1.0] * 3, {}, "tz-aware", id="naive-stamp"),
        pytest.param(_stamps(3), [1.0] * 2, {}, "stamps and volumes", id="unequal-lengths"),
        pytest.param(_stamps(3), [1.0] * 3, {"lookback": 0}, "lookback must be an int >= 1", id="lookback-0"),
        pytest.param(_stamps(3), [1.0] * 3, {"lookback": True}, "lookback must be an int >= 1", id="lookback-bool"),
        pytest.param(_stamps(3), [1.0] * 3, {"lookback": 1.5}, "lookback must be an int >= 1", id="lookback-float"),
        pytest.param(_stamps(3), [1.0] * 3, {"min_cell_obs": 0}, "min_cell_obs must be an int >= 1", id="min-cell-obs-0"),
    ],
)
def test_volume_confirmations_refuses_an_input_it_cannot_gate(stamps, volumes, over, match):
    with pytest.raises(AlphaError, match=match):
        volume_confirmations(stamps, volumes, **({"lookback": 2, "min_cell_obs": 2} | over))


_CLOSES = {"BTC": [100.0, None, 100.0, 100.0, None, 100.0, 100.0, 100.0], "ETH": [50.0] * 8}
_VOLUMES = {"BTC": [10.0, None, 20.0, 30.0, None, 40.0, 5.0, 25.0], "ETH": [8.0] * 8}


def test_a_btc_fill_is_accepted_in_the_warm_up_and_rejected_after_it():
    # lookback 2 on BTC's own bars, the fills at 1 (inside the warm-up) and 4 (past it): bar 3: L = median(10, 20) = 15 <= 30;
    # bar 5: L = median(20, 30) = 25 <= 40; bar 6: L = median(30, 40) = 35 > 5; bar 7: L = median(40, 5) = 22.5 <= 25.
    fed = _ffill_btc(_CLOSES)
    assert confirmations_by_asset(fed, _CLOSES, _stamps(8), _VOLUMES, lookback=2, min_cell_obs=100) == {
        "BTC": [True, True, True, True, False, True, False, True],
        "ETH": [True] * 8,
    }


@pytest.mark.parametrize(
    ("closes", "volumes", "match"),
    [
        pytest.param(
            _CLOSES,
            {**_VOLUMES, "BTC": [10.0, 9.0, *_VOLUMES["BTC"][2:]]},
            r"BTC: a volume where the close is absent at 2024-01-01T04:00:00\+00:00",
            id="a-volume-at-a-fill",
        ),
        pytest.param(
            _CLOSES,
            {**_VOLUMES, "ETH": [8.0, 8.0, 8.0, None, 8.0, 8.0, 8.0, 8.0]},
            r"ETH: no volume where the close is present at 2024-01-01T12:00:00\+00:00",
            id="no-volume-at-a-close",
        ),
        pytest.param(
            {**_CLOSES, "ETH": [None, *[50.0] * 7]},
            _VOLUMES,
            r"ETH: a volume where the close is absent at 2024-01-01T00:00:00\+00:00",
            id="a-volume-before-the-listing",
        ),
        pytest.param(
            _CLOSES,
            {**_VOLUMES, "ETH": [8.0, 8.0, 0.0, 8.0, 8.0, 8.0, 8.0, 8.0]},
            r"ETH: volume must be a finite number above 0, got 0.0 at 2024-01-01T08:00:00\+00:00",
            id="a-zero-volume-named-by-asset",
        ),
        pytest.param(
            {**_CLOSES, "ETH": [50.0, 0.0, *[50.0] * 6]},
            _VOLUMES,
            "prices must be None or finite positive numbers",
            id="a-zero-close",
        ),
        pytest.param(_CLOSES, {"BTC": _VOLUMES["BTC"]}, "volumes' assets", id="an-asset-without-volumes"),
    ],
)
def test_confirmations_by_asset_refuses_a_volume_off_its_close(closes, volumes, match):
    with pytest.raises(AlphaError, match=match):
        confirmations_by_asset(_ffill_btc(closes), closes, _stamps(8), volumes, lookback=2, min_cell_obs=100)


_PRICES = [10.0, 11.0, 12.0, 11.0, 12.0, 13.0, 12.0, 13.0]


def test_a_rejected_entry_leaves_the_state_an_exit_is_always_taken_and_each_touch_off_plus_1_is_an_event():
    # window 2: the channel position is +1 at a higher close, -1 at a lower one. Bar 1's entry is rejected, so bar 2's touch
    # is an event on B's own machine (A is already +1); bar 3's exit is taken with its flag false; bars 4 and 5 touch at -1.
    confirm = [True, False, True, False, False, False, True, True]
    assert donchian_signal_confirmed(_PRICES, confirm, window=2, band=1.0) == (
        [0.0, 0.0, 1.0, -1.0, -1.0, -1.0, -1.0],
        [(1, False), (2, True), (4, False), (5, False)],
    )
    # A rise: bar 1's entry is accepted, so bar 2's touch, B already +1, is no event and keeps +1 though its flag is false.
    assert donchian_signal_confirmed([10.0, 11.0, 12.0, 13.0], [True, True, False, True], window=2, band=1.0) == (
        [0.0, 1.0, 1.0],
        [(1, True)],
    )


@pytest.mark.parametrize("window", [2, 3, 5])
def test_every_entry_confirmed_is_the_unconfirmed_state_machine(window):
    prices = [100.0 * (1 + 0.05 * math.sin(k / 3.0)) * 1.002**k for k in range(80)]
    states, events = donchian_signal_confirmed(prices, [True] * 80, window=window, band=1.0)
    assert states == _donchian_signal(prices, window=window, band=1.0)
    assert events and all(accepted for _, accepted in events)


def _btc_directions(confirm: list[bool], *, short: str = "off", assets: tuple[str, ...] = ("BTC",)):
    prices = {"BTC": list(_PRICES)}
    union_ts, asset_ts = _index(prices)
    config = A2Config(lookbacks=(2,), short=short, target_vol=0.1)
    return asset_directions_confirmed(prices, union_ts, asset_ts, dict.fromkeys(assets, confirm), config=config)


def test_the_directions_map_the_confirmed_states_onto_the_union_clipped_at_0():
    directions, events = _btc_directions([True, False, True, False, False, False, True, True])

    assert directions == {"BTC": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]}
    assert events == {"BTC": {2: [(1, False), (2, True), (4, False), (5, False)]}}


@pytest.mark.parametrize(("config", "n"), [(_SMALL, 400), *((config, 600) for config in _ADOPTED)])
def test_with_every_entry_confirmed_the_directions_and_positions_are_arm_as(config, n):
    prices = _union(n)
    union_ts, asset_ts = _index(prices)
    confirm = {asset: [True] * len(ts) for asset, ts in asset_ts.items()}
    book = a2_book_returns(prices, config=config)

    directions, _ = asset_directions_confirmed(prices, union_ts, asset_ts, confirm, config=config)

    assert directions == _asset_directions_a2(prices, union_ts, asset_ts, config=config)
    weights = _inverse_vol_weights(prices, lookback=config.basket_lookback)
    assert a2_positions_on_directions(weights, directions, book["vol_target_positions"]) == book["asset_positions"]


def test_a_rejected_entry_never_lifts_a_direction_above_arm_as():
    prices = _union(400)
    union_ts, asset_ts = _index(prices)
    confirm = {asset: [j % 3 != 1 for j in range(len(ts))] for asset, ts in asset_ts.items()}

    d_b, events = asset_directions_confirmed(prices, union_ts, asset_ts, confirm, config=_SMALL)

    d_a = _asset_directions_a2(prices, union_ts, asset_ts, config=_SMALL)
    pairs = [(d_b[asset][k], d_a[asset][k]) for asset in prices for k in range(len(union_ts) - 1)]
    assert all((b is None) == (a is None) for b, a in pairs)
    assert all(b <= a for b, a in pairs if b is not None) and any(b < a for b, a in pairs if b is not None)
    assert {asset: sorted(by_lookback) for asset, by_lookback in events.items()} == {asset: [5, 10, 20] for asset in prices}
    assert any(not accepted for by_lookback in events.values() for evs in by_lookback.values() for _, accepted in evs)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(
            lambda: donchian_signal_confirmed(_PRICES, [True] * 7, window=2, band=1.0), "7 flags for 8 prices", id="flags-short"
        ),
        pytest.param(lambda: _btc_directions([True] * 8, short="on"), "short='off'", id="short-on"),
        pytest.param(lambda: _btc_directions([True] * 7), "BTC: confirm holds 7 flags for 8 bars", id="an-asset-one-flag-short"),
        pytest.param(lambda: _btc_directions([True] * 8, assets=("ETH",)), "confirm's assets", id="confirm-off-the-assets"),
        pytest.param(
            lambda: a2_positions_on_directions([{}] * 2, {"BTC": [1.0] * 3}, [1.0] * 3), "differ in length", id="weights-short"
        ),
        pytest.param(
            lambda: a2_positions_on_directions([{}] * 3, {"BTC": [1.0] * 2}, [1.0] * 3), "differ in length", id="a-direction-short"
        ),
    ],
)
def test_the_directions_and_positions_refuse_inputs_off_their_shape(call, match):
    with pytest.raises(AlphaError, match=match):
        call()


def test_entry_events_are_counted_per_bar_start_year_every_year_with_a_state_kept():
    # ETH's bar at 2015-12-31 20:00 closes in 2016 and is keyed 2015; its last bar, alone in 2018, has no state.
    eth = [datetime(2015, 12, 31, 16, tzinfo=UTC), datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC)]
    eth += [datetime(2017, 6, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)]
    events = {"ETH": {2: [(1, False), (2, True)], 3: []}}
    assert entry_events_per_year(events, {"ETH": eth}) == {
        "ETH": {
            "2": {"2015": [1, 1], "2016": [1, 0], "2017": [0, 0]},
            "3": {"2015": [0, 0], "2016": [0, 0], "2017": [0, 0]},
        }
    }


def test_directions_differ_per_bar_start_year_counting_each_stamp_once():
    union_ts = [
        datetime(2014, 12, 31, 20, tzinfo=UTC),
        datetime(2015, 12, 31, 16, tzinfo=UTC),
        datetime(2015, 12, 31, 20, tzinfo=UTC),
    ]
    union_ts += [datetime(2016, 1, 1, tzinfo=UTC), datetime(2016, 1, 1, 4, tzinfo=UTC), datetime(2016, 1, 1, 8, tzinfo=UTC)]
    directions_a = [{"BTC": [0.5, 0.0, 1.0, None, 0.5]}, {"BTC": [1.0, 1.0, 1.0, 1.0, 1.0]}]
    directions_b = [{"BTC": [0.5, 0.0, 0.0, None, 0.0]}, {"BTC": [1.0, 1.0, 0.0, 1.0, 1.0]}]
    # Stamp 2, keyed 2015, differs on both arms and counts once; stamp 3's None equals None; 2014 stays, at 0.
    assert directions_differ_per_year(directions_a, directions_b, union_ts) == {"2014": 0, "2015": 1, "2016": 1}


def test_directions_differ_keys_no_year_whose_only_stamp_is_the_last():
    # Index 1's bar opens 2016-12-31 20:00, closes in 2017 and is keyed 2016; the last stamp opens no bar with a return.
    union_ts = [datetime(2016, 12, 31, 16, tzinfo=UTC), datetime(2016, 12, 31, 20, tzinfo=UTC), datetime(2017, 1, 1, tzinfo=UTC)]
    assert directions_differ_per_year([{"BTC": [1.0, 1.0]}], [{"BTC": [1.0, 0.0]}], union_ts) == {"2016": 1}


def test_directions_differ_keeps_the_last_return_index_year_at_0():
    # Index 1, the last return index, is alone in 2016, so no earlier index keeps that key.
    union_ts = [datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 12, 31, 20, tzinfo=UTC), datetime(2017, 1, 1, tzinfo=UTC)]
    assert directions_differ_per_year([{"BTC": [1.0, 1.0]}], [{"BTC": [0.0, 1.0]}], union_ts) == {"2015": 1, "2016": 0}
