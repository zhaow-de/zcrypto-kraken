from datetime import UTC, datetime, timedelta

import numpy
import pytest

from cli.costs.ladder import blend, cost_table, side_costs
from cli.panel.ladder import rows_frame
from cli.validation.bootstrap import bootstrap_ci

START = datetime(2026, 9, 1, 0, 2, tzinfo=UTC)
STEP = timedelta(hours=4)
MID = 100.0
CELL_KEYS = ("span", "2026-08", "2026-09", "2026-10")


def _row(
    ts, side, *, size=0, pair="BTC/EUR", fill_price=None, fill_s=60.0, touch_price=None, touch_qty=5.0, our_qty=1.0, met_qty=None
):
    """An unfilled order unless `fill_price` is given; its box end stale unless `touch_price` is, the three box-end
    columns null together; its `met_qty` its `our_qty` when filled and 0.0 when not, unless given."""
    filled = fill_price is not None
    stale = touch_price is None
    return {
        "ts": ts,
        "pair": pair,
        "side": side,
        "size": size,
        "price": MID - 0.05 if side == "bid" else MID + 0.05,
        "our_qty": our_qty,
        "queue_ahead_qty": 1.0,
        "mid_at_post": MID,
        "spread_at_post_bps": 10.0,
        "filled": filled,
        "time_to_fill_s": fill_s if filled else None,
        "fill_price": fill_price,
        "box_end_mid": None if stale else 101.0,
        "box_end_touch_price": touch_price,
        "box_end_touch_qty": None if stale else touch_qty,
        "met_qty": met_qty if met_qty is not None else (our_qty if filled else 0.0),
    }


def _priced(ts, side, cost, *, size=0, pair="BTC/EUR"):
    """A maker fill priced to `cost` against the mid at the post."""
    sign = 1 if side == "bid" else -1
    return _row(ts, side, size=size, pair=pair, fill_price=MID * (1 + sign * (cost - 0.0040)), touch_price=MID)


def test_the_cost_of_a_side_is_signed_against_the_order():
    rows = [
        _row(START, "bid", fill_price=99.9, touch_price=100.3),
        _row(START + STEP, "ask", fill_price=100.1, touch_price=99.7),
        _row(START + 2 * STEP, "bid", touch_price=100.1),
        _row(START + 3 * STEP, "ask", touch_price=99.9),
    ]

    costs = side_costs(rows_frame(rows))["cost"].to_list()

    assert costs == pytest.approx([-0.001 + 0.0040, -0.001 + 0.0040, 0.001 + 0.0080, 0.001 + 0.0080], abs=1e-12)


def test_an_unpriced_fallback_is_counted_and_left_out_of_the_mean():
    rows = [
        _row(START, "bid", fill_price=99.9),
        _row(START + STEP, "bid", fill_price=99.9, touch_price=100.3),
        _row(START + 2 * STEP, "bid", touch_price=100.1),
        _row(START + 3 * STEP, "bid"),
    ]

    span = cost_table(rows_frame(rows))["bid|S0"]["span"]

    assert (span["posts"], span["unpriced"]) == (4, 1)
    assert span["mean_cost"] == pytest.approx(0.005, abs=1e-12)


def test_the_maker_share_median_and_fallback_shares_read_their_own_denominators():
    filled = [
        _row(START + i * STEP, "bid", fill_price=99.9, fill_s=fill_s, touch_price=100.1, touch_qty=0.5)
        for i, fill_s in enumerate((30.0, 60.0, 90.0, 300.0))
    ]
    unfilled = [
        _row(
            START + (4 + i) * STEP,
            "bid",
            touch_price=None if touch_qty is None else 100.1,
            touch_qty=touch_qty,
            our_qty=2.0,
            met_qty=met_qty,
        )
        for i, (touch_qty, met_qty) in enumerate(
            ((None, 1.0), (0.8, 1.0), (1.2, 1.0), (1.6, 4e-9), (2.0, 1.0), (4.0, 1.5e-9)),
        )
    ]

    span = cost_table(rows_frame(filled + unfilled))["bid|S0"]["span"]

    assert (span["posts"], span["unpriced"]) == (10, 1)
    assert span["maker_share"] == pytest.approx(0.4)
    assert span["median_time_to_fill_s"] == pytest.approx(75.0)
    assert span["fallback_larger_share"] == pytest.approx(3 / 5)
    assert span["fallback_partly_met_share"] == pytest.approx(4 / 5)
    assert {key: type(value) for key, value in span.items()} == {
        "posts": int,
        "unpriced": int,
        "maker_share": float,
        "median_time_to_fill_s": float,
        "mean_cost": float,
        "cost_ci_low": float,
        "cost_ci_high": float,
        "fallback_larger_share": float,
        "fallback_partly_met_share": float,
    }


def test_each_month_reads_its_own_rows():
    stamps = [
        datetime(2026, 8, 31, 20, 2, tzinfo=UTC),
        datetime(2026, 9, 1, 0, 2, tzinfo=UTC),
        datetime(2026, 9, 30, 20, 2, tzinfo=UTC),
        datetime(2026, 10, 1, 0, 2, tzinfo=UTC),
        datetime(2026, 10, 2, 12, 2, tzinfo=UTC),
        datetime(2026, 10, 25, 20, 2, tzinfo=UTC),
    ]

    cell = cost_table(rows_frame([_row(ts, "ask", size=1, touch_price=99.9) for ts in stamps]))["ask|S1"]

    assert {key: leaves["posts"] for key, leaves in cell.items()} == {"span": 6, "2026-08": 1, "2026-09": 2, "2026-10": 3}


def test_a_figure_over_no_row_is_an_absent_key():
    table = cost_table(rows_frame([_row(START, "bid"), _row(START + STEP, "bid")]))

    assert set(table) == {"bid|S0", "bid|S1", "ask|S0", "ask|S1"}
    assert table["bid|S0"]["2026-08"] == {"posts": 0, "unpriced": 0}
    assert table["bid|S0"]["span"] == table["bid|S0"]["2026-09"] == {"posts": 2, "unpriced": 2, "maker_share": 0.0}
    assert table["ask|S1"] == {key: {"posts": 0, "unpriced": 0} for key in CELL_KEYS}


def test_the_blend_weights_each_leg_equally():
    b = [START + i * STEP for i in range(5)]
    first = [
        *(row for ts in b[:2] for row in (_priced(ts, "bid", 0.01, pair="ADA/EUR"), _row(ts, "ask", pair="ADA/EUR"))),
        _priced(b[4], "bid", 0.004, pair="ADA/EUR"),
        _row(b[4], "ask", pair="ADA/EUR"),
    ]
    second = [
        *(_priced(ts, side, 0.002, pair="DOT/EUR") for ts in b[:3] for side in ("bid", "ask")),
        *(_row(ts, side, pair="DOT/EUR") for ts in b[3:] for side in ("bid", "ask")),
    ]
    frames = {
        "ADA/EUR": rows_frame(first),
        "DOT/EUR": rows_frame(second),
        "XRP/EUR": rows_frame([_priced(ts, "bid", 0.05, pair="XRP/EUR") for ts in b]),
    }

    blended = blend(frames, ("ADA/EUR", "DOT/EUR"))

    interval = bootstrap_ci([0.006, 0.006, 0.002, 0.004], numpy.mean, mean_block=6, n_resamples=2000, alpha=0.05, seed=42)
    assert blended["S0"]["boundaries"] == 4
    assert blended["S0"]["mean_cost"] == pytest.approx(0.018 / 4, abs=1e-12)
    assert (blended["S0"]["cost_ci_low"], blended["S0"]["cost_ci_high"]) == pytest.approx(
        (interval["lower"], interval["upper"]), abs=1e-12
    )
    assert blended["S1"] == {"boundaries": 0}


def test_the_blend_sums_each_boundarys_legs_in_their_name_order():
    # In name order the two 1e16 legs cancel before the 1.0 joins them and the mean is 1/3; a sum that meets the 1.0 first
    # loses it against 1e16 and reads 0.0. Polars' group order moves from call to call, so one call can land on the name
    # order by chance.
    costs = {"ADA/EUR": 1e16, "AVAX/EUR": -1e16, "BTC/EUR": 1.0}
    frames = {leg: rows_frame([_priced(START, side, cost, pair=leg) for side in ("bid", "ask")]) for leg, cost in costs.items()}

    means = [blend(frames, ("BTC/EUR", "ADA/EUR", "AVAX/EUR"))["S0"]["mean_cost"] for _ in range(20)]

    assert means == [1 / 3] * 20


def test_the_interval_is_bootstrap_ci_at_the_constants():
    cell_costs = [0.004, 0.012, 0.001, 0.009, 0.003, 0.030, 0.002, 0.007, 0.005, 0.011, 0.006, 0.008]
    blend_costs = [0.020, 0.003, 0.006, 0.001, 0.009, 0.004, 0.002, 0.012, 0.005, 0.007, 0.010, 0.008]
    stamps = [START + i * STEP for i in range(12)]
    cell_rows = [_priced(ts, "ask", cost, size=1) for ts, cost in zip(stamps, cell_costs, strict=True)]
    leg_rows = [row for ts, cost in zip(stamps, blend_costs, strict=True) for row in (_priced(ts, "bid", cost), _row(ts, "ask"))]

    cell = cost_table(rows_frame(cell_rows).reverse())["ask|S1"]["span"]
    blended = blend({"BTC/EUR": rows_frame(leg_rows).reverse()}, ("BTC/EUR",))["S0"]

    for figures, series in ((cell, cell_costs), (blended, blend_costs)):
        direct = bootstrap_ci(series, numpy.mean, mean_block=6, n_resamples=2000, alpha=0.05, seed=42)
        read = (figures["mean_cost"], figures["cost_ci_low"], figures["cost_ci_high"])
        assert read == pytest.approx((direct["point"], direct["lower"], direct["upper"]), rel=1e-12)
        assert [type(figure) for figure in read] == [float, float, float]
