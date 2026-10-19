from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.alpha.a2 import A2Config, _asset_directions_a2, _donchian_signal, a2_book_returns
from cli.alpha.b1 import book_turnover
from cli.alpha.b1_exit import (
    a2_slot_positions,
    asset_directions_hourly_exit,
    donchian_signal_hourly_exit,
    exit_events_per_year,
    hourly_closes_differ_per_year,
    interior_closes_by_asset,
    intra_turnover,
    net_of_cost_hourly,
    new_low,
    price_paths,
)
from cli.alpha.b2 import net_of_cost
from cli.alpha.errors import AlphaError
from cli.features import channel_position
from cli.portfolio.crossfreq_system import _ffill_btc

_T0 = datetime(2024, 1, 1, tzinfo=UTC)
_H1, _H4 = timedelta(hours=1), timedelta(hours=4)
_SMALL = A2Config(lookbacks=(5, 10, 20), short="off", target_vol=0.12, vol_lookback=12, basket_lookback=8, periods_per_year=2190)
_ADOPTED = tuple(
    A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
    for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
)
_NONE3 = (None, None, None)


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


def test_new_low_is_the_channels_own_test_at_its_ties_and_its_band():
    # A close at the window's low reads 2 * 0 / 2 - 1 = -1 and breaches; a flat window reads 0; 10.5 in [10, 12] reads -0.5,
    # past band 0.5 and short of band 1.0; a close below the prior low widens the window down to itself, a flat one too.
    assert new_low([10.0, 12.0, 11.0], 10.0, band=1.0)
    assert not new_low([10.0, 10.0], 10.0, band=1.0)
    assert not new_low([10.0, 12.0], 10.5, band=1.0) and new_low([10.0, 12.0], 10.5, band=0.5)
    assert new_low([10.0, 12.0], 9.0, band=1.0) and new_low([10.0, 10.0], 9.0, band=1.0)


@pytest.mark.parametrize(("window", "band"), [(2, 1.0), (5, 1.0), (20, 1.0), (5, 0.6)])
def test_new_low_agrees_with_the_channel_position_at_every_whole_window(window, band):
    prices = [100.0 * (1 + 0.05 * math.sin(k / 3.0)) * 0.999**k for k in range(200)]
    cp = channel_position(prices, window=window)
    agree = [new_low(prices[m + 1 - window : m], prices[m], band=band) for m in range(window - 1, len(cp))]
    assert agree == [cp[m] <= -band for m in range(window - 1, len(cp))]
    assert any(agree) and not all(agree)


_PRICES = [10.0, 11.0, 12.0, 13.0, 12.5, 14.0, 15.0, 13.0]
_INTERIOR = [
    (1.0, 1.0, 1.0),  # own bar 0's: read by no interval
    (9.0, 9.0, 9.0),  # interval 0 -> 1: the lookback at its initial 0, unchecked
    (9.0, None, None),  # 1 -> 2: still 0
    (12.5, 10.9, 12.8),  # 2 -> 3: level min(11, 12) = 11; 10.9 breaches at offset 2; 13 makes no new low, a false exit
    (None, 12.0, 11.0),  # 3 -> 4: re-entered at 13, level 12; offset 1 missing; 12.0 ties the low; 11.0 no second exit
    (11.0, None, 10.0),  # 4 -> 5: B held at -1 from the exit, unchecked
    (14.5, 14.8, 14.9),  # 5 -> 6: +1 at 14, level 12.5, no breach
    (14.6, 13.9, 13.5),  # 6 -> 7: level 14; 13.9 breaches at offset 2; 13 is a new 3-bar low, an early exit
]


def test_the_exit_check_sets_minus_1_at_the_first_breach_from_plus_1_and_the_4h_rule_continues_from_bs_state():
    # Window 3: arm A's states are 0, 0, then +1 from bar 2 on (bar 4's 12.5 reads 0 in [12, 13] and holds). B holds its exit's
    # -1 through bar 4 and re-enters on bar 5's new high.
    states, exits = donchian_signal_hourly_exit(_PRICES, _INTERIOR, window=3, band=1.0)

    assert _donchian_signal(_PRICES, window=3, band=1.0) == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert states == [
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
        (1.0, 1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0, -1.0),
        (-1.0, -1.0, -1.0, -1.0),
        (1.0, 1.0, 1.0, 1.0),
        (1.0, 1.0, -1.0, -1.0),
    ]
    assert exits == [(2, 2, False), (3, 2, False), (6, 2, True)]


@pytest.mark.parametrize("window", [2, 3, 5])
def test_with_no_interior_close_the_states_are_the_4h_rules(window):
    prices = [100.0 * (1 + 0.05 * math.sin(k / 3.0)) * 1.002**k for k in range(80)]
    states, exits = donchian_signal_hourly_exit(prices, [_NONE3] * 80, window=window, band=1.0)
    assert states == [(s, s, s, s) for s in _donchian_signal(prices, window=window, band=1.0)]
    assert exits == []


@pytest.mark.parametrize(("config", "n"), [(_SMALL, 400), *((config, 600) for config in _ADOPTED)])
def test_with_no_interior_close_arm_bs_directions_positions_and_net_are_arm_as(config, n):
    prices = _union(n)
    union_ts, asset_ts = _index(prices)
    interior = {asset: [_NONE3] * len(ts) for asset, ts in asset_ts.items()}
    book = a2_book_returns(prices, config=config)

    directions, events = asset_directions_hourly_exit(prices, union_ts, asset_ts, interior, config=config)
    slots = a2_slot_positions(
        _inverse_vol_weights(prices, lookback=config.basket_lookback), directions, book["vol_target_positions"]
    )

    d_a = _asset_directions_a2(prices, union_ts, asset_ts, config=config)
    assert directions == {asset: [None if d is None else (d, d, d, d) for d in d_a[asset]] for asset in prices}
    assert all(evs == [] for by_lookback in events.values() for evs in by_lookback.values())
    assert slots == {asset: [(p, p, p, p) for p in ps] for asset, ps in book["asset_positions"].items()}
    returns = {asset: _asset_returns(ps) for asset, ps in prices.items()}
    net_b = net_of_cost_hourly(slots, price_paths(prices, interior), cost_per_side=0.006)
    assert net_b == net_of_cost(book["asset_positions"], returns, cost_per_side=0.006)
    assert intra_turnover(slots) == 0.0
    assert book_turnover({asset: [p for s in ps for p in s] for asset, ps in slots.items()}) == book_turnover(
        book["asset_positions"]
    )


def _dips(prices: dict[str, list[float | None]]) -> dict[str, list[tuple[float | None, float | None, float | None]]]:
    # Each own bar's three interior closes off its predecessor's close, the second missing on every seventh bar.
    out = {}
    for asset, ps in prices.items():
        own = [p for p in ps if p is not None]
        out[asset] = [_NONE3] + [
            (own[j - 1] * 0.998, None if j % 7 == 3 else own[j - 1] * 0.985, own[j] * 0.999) for j in range(1, len(own))
        ]
    return out


def test_an_exit_never_lifts_arm_bs_state_or_direction_above_arm_as_and_both_kinds_of_exit_occur():
    prices = _union(400)
    union_ts, asset_ts = _index(prices)
    interior = _dips(prices)

    d_b, events = asset_directions_hourly_exit(prices, union_ts, asset_ts, interior, config=_SMALL)

    for asset, ps in prices.items():
        own = [p for p in ps if p is not None]
        for w in _SMALL.lookbacks:
            states, _ = donchian_signal_hourly_exit(own, interior[asset], window=w, band=1.0)
            assert all(max(slots) <= a for slots, a in zip(states, _donchian_signal(own, window=w, band=1.0), strict=True))

    d_a = _asset_directions_a2(prices, union_ts, asset_ts, config=_SMALL)
    pairs = [(d_b[asset][k], d_a[asset][k]) for asset in prices for k in range(len(union_ts) - 1)]
    assert all((b is None) == (a is None) for b, a in pairs)
    assert all(max(b) <= a for b, a in pairs if b is not None) and any(min(b) < a for b, a in pairs if b is not None)
    assert {asset: sorted(by_lookback) for asset, by_lookback in events.items()} == {asset: [5, 10, 20] for asset in prices}
    assert {early for by_lookback in events.values() for evs in by_lookback.values() for _, _, early in evs} == {True, False}


def test_the_directions_map_each_slots_mean_over_the_lookbacks_onto_the_union_clipped_at_0():
    # Window 2's level is the previous close: its exits are (1, 1) false, (2, 2) false, (3, 2) early on 12.5 < 13 and (6, 1)
    # early. Return index 1 reads mean(1, 0) = 0.5 then mean(-1, 0) = -0.5, clipped to 0; index 4 holds both lookbacks at -1.
    prices = {"BTC": list(_PRICES)}
    union_ts, asset_ts = _index(prices)
    config = A2Config(lookbacks=(2, 3), short="off", target_vol=0.1)

    directions, events = asset_directions_hourly_exit(prices, union_ts, asset_ts, {"BTC": _INTERIOR}, config=config)

    assert directions == {
        "BTC": [
            (0.0, 0.0, 0.0, 0.0),
            (0.5, 0.0, 0.0, 0.0),
            (1.0, 1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0, 1.0),
            (1.0, 0.0, 0.0, 0.0),
        ]
    }
    assert events == {
        "BTC": {2: [(1, 1, False), (2, 2, False), (3, 2, True), (6, 1, True)], 3: [(2, 2, False), (3, 2, False), (6, 2, True)]}
    }


def test_an_interval_no_return_index_maps_still_runs_the_check_and_its_state_carries():
    # ETH misses union stamp 4, so its own interval 3 -> 4 spans union 3 -> 5 and maps to no return index; its false exit
    # there still holds the lookback at -1 into return index 5, where arm A is long.
    prices = {"BTC": [100.0] * 9, "ETH": [*_PRICES[:4], None, *_PRICES[4:]]}
    union_ts, asset_ts = _index(prices)
    interior = {"BTC": [_NONE3] * 9, "ETH": _INTERIOR}
    config = A2Config(lookbacks=(3,), short="off", target_vol=0.1)

    directions, _ = asset_directions_hourly_exit(prices, union_ts, asset_ts, interior, config=config)

    assert directions["ETH"][3:6] == [None, None, (0.0, 0.0, 0.0, 0.0)]
    assert _asset_directions_a2(prices, union_ts, asset_ts, config=config)["ETH"][3:6] == [None, None, 1.0]


def test_a2_slot_positions_scale_each_slots_own_direction_by_the_weight_and_scalar_at_its_index():
    # Index 0: BTC 0.5 * (1, 1, 0.5, 0) * 2 = (1, 1, 0.5, 0), ETH unweighted; index 1: BTC's None direction reads 0, ETH
    # 0.5 * (0, 1, 1, 1) * 4 = (0, 2, 2, 2). A slot read off another slot's direction moves BTC at 0 and ETH at 1.
    weights = [{"BTC": 0.5}, {"BTC": 0.25, "ETH": 0.5}]
    directions = {"BTC": [(1.0, 1.0, 0.5, 0.0), None], "ETH": [(1.0, 0.5, 0.5, 0.0), (0.0, 1.0, 1.0, 1.0)]}
    assert a2_slot_positions(weights, directions, [2.0, 4.0]) == {
        "BTC": [(1.0, 1.0, 0.5, 0.0), (0.0, 0.0, 0.0, 0.0)],
        "ETH": [(0.0, 0.0, 0.0, 0.0), (0.0, 2.0, 2.0, 2.0)],
    }


def test_net_of_cost_hourly_splits_each_interval_at_its_interior_closes_in_units_of_the_boundary_close():
    # BTC at 0: (0.5 * 4 - 0.5 * 8 + 0.25 * 2 + 0.25 * 4) / 64 = -0.0078125, traded 0.5 + 0.25; at 1 the equal slots earn
    # 0.25 * (99 / 66 - 1) = 0.125, whatever the path between; at 2 no path, its sale of 0.25 still charged. ETH at 1:
    # (0.5 * -4 + 0.25 * 8) / 32 = 0, traded 0.5 + 0.25; at 2: 0.5 * (55 / 44 - 1) = 0.125, traded 0.25. Cost 0.0625 a side.
    slots = {
        "BTC": [(0.5, 0.5, 0.25, 0.25), (0.25, 0.25, 0.25, 0.25), (0.0, 0.0, 0.0, 0.0)],
        "ETH": [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.5, 0.25), (0.5, 0.5, 0.5, 0.5)],
    }
    paths = {
        "BTC": [(64.0, 68.0, 60.0, 62.0, 66.0), (66.0, 66.0, 70.0, 64.0, 99.0), None],
        "ETH": [(32.0, 32.0, 32.0, 32.0, 32.0), (32.0, 36.0, 40.0, 36.0, 44.0), (44.0, 44.0, 44.0, 44.0, 55.0)],
    }
    assert net_of_cost_hourly(slots, paths, cost_per_side=0.0625) == [-0.0546875, 0.078125, 0.09375]
    # The trades at interior closes alone: BTC's 0.25 at offset 2 of index 0, ETH's 0.5 and 0.25 at offsets 2 and 3 of index 1.
    assert intra_turnover(slots) == 1.0


def test_a_price_path_carries_the_previous_close_over_a_missing_hour_and_reads_the_bar_that_ends_its_interval():
    fed = {"BTC": [64.0, 66.0, 70.0, 72.0], "ETH": [None, 50.0, 52.0, 51.0], "SOL": [10.0, None, 11.0, 12.0]}
    interior = {
        "BTC": [(1.0, 1.0, 1.0), (65.0, None, 67.0), _NONE3, (71.0, 73.0, 72.5)],
        "ETH": [(9.0, 9.0, 9.0), (50.5, None, 51.5), _NONE3],
        "SOL": [(9.0, 9.0, 9.0), (10.5, 10.6, 10.7), (11.5, None, None)],
    }
    assert price_paths(fed, interior) == {
        "BTC": [(64.0, 65.0, 65.0, 67.0, 66.0), (66.0, 66.0, 66.0, 66.0, 70.0), (70.0, 71.0, 73.0, 72.5, 72.0)],
        "ETH": [None, (50.0, 50.5, 50.5, 51.5, 52.0), (52.0, 52.0, 52.0, 52.0, 51.0)],
        "SOL": [None, None, (11.0, 11.5, 11.5, 11.5, 12.0)],
    }


_UNION = [_T0 + k * _H4 for k in range(4)]
_H4_CLOSES = {"BTC": [64.0, None, 66.0, 67.0], "ETH": [None, 50.0, 52.0, 51.0]}


def _hourly(**over: tuple[list[datetime], list]) -> dict[str, tuple[list[datetime], list]]:
    btc = [0, 1, 2, 3, 8, 10, 11, 12, 13, 14, 15]
    eth = [5, 6, 7, 8, 9, 10, 11, 12]
    return {
        "BTC": ([_T0 + h * _H1 for h in btc], [63.0, 63.5, 63.8, 64.0, 65.0, 65.5, 66.0, 66.5, 66.7, 66.9, 67.0]),
        "ETH": ([_T0 + h * _H1 for h in eth], [49.5, 49.8, 50.0, 50.5, 51.0, 51.5, 52.0, 51.8]),
    } | over


def test_interior_closes_are_the_first_three_hourly_closes_of_each_own_bar():
    # BTC's bar 1 is a fill, with no hourly bar; its bar 2 misses 09:00, its 11:00 close is the fourth, never read. ETH's own
    # bars start at union 1, whose 04:00 hour is missing.
    assert interior_closes_by_asset(_ffill_btc(_H4_CLOSES), _H4_CLOSES, _UNION, _hourly()) == {
        "BTC": [(63.0, 63.5, 63.8), _NONE3, (65.0, None, 65.5), (66.5, 66.7, 66.9)],
        "ETH": [(None, 49.5, 49.8), (50.5, 51.0, 51.5), (51.8, None, None)],
    }


def _eth(hours: list[float], closes: list) -> dict[str, tuple[list[datetime], list]]:
    return {"ETH": ([_T0 + timedelta(hours=h) for h in hours], closes)}


_ETH_HOURS, _ETH_CLOSES = [5, 6, 7, 8, 9, 10, 11, 12], [49.5, 49.8, 50.0, 50.5, 51.0, 51.5, 52.0, 51.8]


@pytest.mark.parametrize(
    ("hourly", "h4", "match"),
    [
        *(
            pytest.param(
                _eth(_ETH_HOURS, [49.5, bad, *_ETH_CLOSES[2:]]),
                _H4_CLOSES,
                rf"ETH: hourly close must be a finite number above 0, got {re_bad} at 2024-01-01T06:00:00\+00:00",
                id=name,
            )
            for name, bad, re_bad in (
                ("zero-close", 0.0, "0.0"),
                ("negative-close", -1.0, "-1.0"),
                ("nan-close", math.nan, "nan"),
                ("inf-close", math.inf, "inf"),
                ("none-close", None, "None"),
                ("bool-close", True, "True"),
            )
        ),
        pytest.param(
            _eth([5, 6, 6, 8, 9, 10, 11, 12], _ETH_CLOSES),
            _H4_CLOSES,
            r"ETH: hourly stamps must be strictly increasing, violated at 2024-01-01T06:00:00\+00:00",
            id="repeated-stamp",
        ),
        pytest.param(
            {"ETH": ([_T0.replace(tzinfo=None) + timedelta(hours=5), *_hourly()["ETH"][0][1:]], _ETH_CLOSES)},
            _H4_CLOSES,
            "ETH: hourly stamps must be tz-aware",
            id="naive-stamp",
        ),
        pytest.param(
            _eth([5, 6.5, 7, 8, 9, 10, 11, 12], _ETH_CLOSES),
            _H4_CLOSES,
            r"ETH: hourly stamp off the hour at 2024-01-01T06:30:00\+00:00",
            id="off-the-hour",
        ),
        pytest.param(
            _eth(_ETH_HOURS, _ETH_CLOSES[:-1]), _H4_CLOSES, "ETH: hourly stamps and closes differ in length: 8 and 7", id="unequal"
        ),
        pytest.param(
            _eth([1, *_ETH_HOURS], [49.0, *_ETH_CLOSES]),
            _H4_CLOSES,
            r"ETH: an hourly bar at 2024-01-01T01:00:00\+00:00 lies in a 4h bar the 240 series lacks",
            id="a-bar-the-240-lacks",
        ),
        pytest.param(
            {"BTC": ([_T0 + h * _H1 for h in (0, 5)], [63.0, 64.0])},
            _H4_CLOSES,
            r"BTC: an hourly bar at 2024-01-01T05:00:00\+00:00 lies in a 4h bar the 240 series lacks",
            id="a-bar-in-a-fills-span",
        ),
        pytest.param(
            _eth([*_ETH_HOURS, 16], [*_ETH_CLOSES, 51.0]),
            _H4_CLOSES,
            r"ETH: an hourly bar at 2024-01-01T16:00:00\+00:00 lies in a 4h bar the 240 series lacks",
            id="a-bar-off-the-union",
        ),
        pytest.param(
            {},
            {**_H4_CLOSES, "ETH": [None, 50.0, 0.0, 51.0]},
            "prices must be None or finite positive numbers",
            id="a-zero-4h-close",
        ),
        pytest.param({"ETH": None}, _H4_CLOSES, "hourly's assets", id="an-asset-without-hourly-bars"),
    ],
)
def test_interior_closes_refuse_an_hourly_series_the_check_cannot_read(hourly, h4, match):
    series = {k: v for k, v in (_hourly() | hourly).items() if v is not None}
    with pytest.raises(AlphaError, match=match):
        interior_closes_by_asset(_ffill_btc(h4), h4, _UNION, series)


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(
            lambda: asset_directions_hourly_exit(
                {"BTC": list(_PRICES)},
                list(range(8)),
                {"BTC": list(range(8))},
                {"BTC": _INTERIOR[:-1]},
                config=A2Config(lookbacks=(3,), short="off", target_vol=0.1),
            ),
            "BTC: interior holds 7 triples for 8 prices",
            id="interior-short",
        ),
        pytest.param(
            lambda: asset_directions_hourly_exit(
                {"BTC": list(_PRICES)},
                list(range(8)),
                {"BTC": list(range(8))},
                {"BTC": _INTERIOR},
                config=A2Config(lookbacks=(3,), short="on", target_vol=0.1),
            ),
            "short='off'",
            id="short-on",
        ),
        pytest.param(
            lambda: asset_directions_hourly_exit(
                {"BTC": list(_PRICES)},
                list(range(8)),
                {"BTC": list(range(8))},
                {"ETH": _INTERIOR},
                config=A2Config(lookbacks=(3,), short="off", target_vol=0.1),
            ),
            "interior's assets",
            id="interior-off-the-assets",
        ),
        pytest.param(
            lambda: a2_slot_positions([{}] * 2, {"BTC": [(1.0,) * 4] * 3}, [1.0] * 3), "differ in length", id="weights-short"
        ),
        pytest.param(
            lambda: a2_slot_positions([{}] * 3, {"BTC": [(1.0,) * 4] * 2}, [1.0] * 3), "differ in length", id="a-direction-short"
        ),
    ],
)
def test_the_state_machine_directions_and_positions_refuse_inputs_off_their_shape(call, match):
    with pytest.raises(AlphaError, match=match):
        call()


def test_exit_events_are_counted_per_bar_start_year_early_and_false_every_year_with_a_state_kept():
    # ETH's bar at 2015-12-31 20:00 closes in 2016 and is keyed 2015; its last bar, alone in 2018, has no state.
    eth = [datetime(2015, 12, 31, 16, tzinfo=UTC), datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC)]
    eth += [datetime(2017, 6, 1, tzinfo=UTC), datetime(2018, 1, 1, tzinfo=UTC)]
    events = {"ETH": {2: [(1, 2, True), (2, 1, False)], 3: []}}
    assert exit_events_per_year(events, {"ETH": eth}) == {
        "ETH": {
            "2": {"2015": [1, 1, 0], "2016": [1, 0, 1], "2017": [0, 0, 0]},
            "3": {"2015": [0, 0, 0], "2016": [0, 0, 0], "2017": [0, 0, 0]},
        }
    }


def test_hourly_closes_differ_per_bar_start_year_counting_each_close_once():
    union_ts = [
        datetime(2014, 12, 31, 20, tzinfo=UTC),
        datetime(2015, 12, 31, 16, tzinfo=UTC),
        datetime(2015, 12, 31, 20, tzinfo=UTC),
    ]
    union_ts += [datetime(2016, 1, 1, tzinfo=UTC), datetime(2016, 1, 1, 4, tzinfo=UTC), datetime(2016, 1, 1, 8, tzinfo=UTC)]
    directions_a = [{"BTC": [0.5, 0.0, 1.0, None, 0.5]}, {"BTC": [1.0, 1.0, 1.0, None, 1.0]}]
    directions_b = [
        {"BTC": [(0.5, 0.5, 0.5, 0.5), (0.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 1.0), None, (0.0, 0.0, 0.0, 0.0)]},
        {"BTC": [(1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0), (1.0, 0.0, 1.0, 1.0), None, (1.0, 1.0, 1.0, 1.0)]},
    ]
    # Index 2, keyed 2015, differs at offsets 1 and 2, offset 1 on both arms, counted once; index 3's None equals None.
    assert hourly_closes_differ_per_year(directions_a, directions_b, union_ts) == {"2014": 0, "2015": 2, "2016": 4}
