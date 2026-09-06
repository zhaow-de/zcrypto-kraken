from datetime import datetime, timedelta, timezone

import pytest

from cli.alpha import (
    AlphaError,
    B1Config,
    book_turnover,
    condition_positions,
    per_year_gated_counts,
    per_year_scaled_counts,
    seasonality_gates,
    vol_state_scale,
)

UTC = timezone.utc
FOUR_H = timedelta(hours=4)
BAR_15M = timedelta(seconds=900)


def _grid(start: datetime, n: int) -> list[datetime]:
    """Dense 4h union calendar: n bar-start stamps from `start`."""
    return [start + timedelta(hours=4 * i) for i in range(n)]


def _bcell(ts: datetime) -> tuple[int, int]:
    """The (hour, weekday) cell of the stamp's DECISION BOUNDARY ts + 4h (the spec's F3 slot key)."""
    boundary = ts + FOUR_H
    return (boundary.hour, boundary.weekday())


def _m15_series(start: datetime, end_boundary: datetime, *, base: float, mult_fn) -> tuple[list[datetime], list[float]]:
    """Dense 15m bar-START stamps from `start` while ts + 900s <= end_boundary. Closes alternate
    base, base * mult_fn(ts): every consecutive log return has magnitude log(mult), so the trailing
    realized vol is proportional to log(mult) -- mult_fn switches regimes by wall clock."""
    ts_list: list[datetime] = []
    closes: list[float] = []
    t, i = start, 0
    while t + BAR_15M <= end_boundary:
        ts_list.append(t)
        closes.append(base if i % 2 == 0 else base * mult_fn(t))
        t += BAR_15M
        i += 1
    return ts_list, closes


# --- 1. Slot key on the decision boundary (F3) ---------------------------------------------------


def test_slot_key_on_decision_boundary():
    # 6576 stamps = 2020-2022, so by 2022 the (0, Monday) cell holds ~104 training obs, past
    # min_cell_obs=100, and its negative sum can gate; every other cell sums positive.
    ts = _grid(datetime(2020, 1, 1, tzinfo=UTC), 6576)
    noc = [-0.01 if _bcell(t) == (0, 0) else 0.001 for t in ts[:-1]]
    gates = seasonality_gates(noc, ts, config=B1Config())
    assert len(gates) == len(ts) - 1
    sun20 = [k for k in range(len(gates)) if ts[k].year == 2022 and ts[k].weekday() == 6 and ts[k].hour == 20]
    assert sun20  # fixture sanity: 2022 has Sunday-20:00 stamps
    assert all(gates[k] == 0 for k in sun20)  # held: their boundary cell (0, Monday) is unfavorable
    mon00 = [k for k in range(len(gates)) if ts[k].year == 2022 and ts[k].weekday() == 0 and ts[k].hour == 0]
    assert mon00
    assert all(gates[k] == 1 for k in mon00)  # their boundary cell is (4, Monday) -- favorable


# --- 2. Walk-forward isolation --------------------------------------------------------------------


def test_walk_forward_isolation():
    # The negative (0, Monday) pattern is planted only in 2021, so a full-sample (leaky) estimator
    # would see it (104 obs across both years) and gate; walk-forward, 2021's table is trained on
    # flat 2020 alone.
    ts = _grid(datetime(2020, 1, 1, tzinfo=UTC), 4386)
    noc = [-0.05 if (t.year == 2021 and _bcell(t) == (0, 0)) else 0.001 for t in ts[:-1]]
    gates = seasonality_gates(noc, ts, config=B1Config())
    assert all(g == 1 for g in gates)


# --- 3. Completion-time rule (F7) ------------------------------------------------------------------


def test_completion_time_rule():
    # Training cut for 2021 = boundaries <= 2021-01-01T00:00Z. Each disputed stamp's -1.0 sits in a
    # cell of otherwise +0.0001 returns (>= 100 obs), so 2021's gate on that cell reveals whether
    # the disputed return was inside 2021's training. Boundary cells, in fixture order:
    #   ts Dec-31 20:00 -> (0, 4); ts Dec-31 16:00 -> (20, 3); ts Jan-1 00:00 -> (4, 4).
    ts = _grid(datetime(2019, 1, 1, tzinfo=UTC), 6576)
    disputed_in_a = datetime(2020, 12, 31, 20, tzinfo=UTC)
    disputed_in_b = datetime(2020, 12, 31, 16, tzinfo=UTC)
    disputed_out = datetime(2021, 1, 1, 0, tzinfo=UTC)
    noc = [-1.0 if t in (disputed_in_a, disputed_in_b, disputed_out) else 0.0001 for t in ts[:-1]]
    gates = seasonality_gates(noc, ts, config=B1Config())
    checked = set()
    for k in range(len(gates)):
        if ts[k].year != 2021:
            continue
        cell = _bcell(ts[k])
        if cell == (0, 4):
            assert gates[k] == 0  # Dec-31 20:00's return IS in 2021's training -> cell sum < 0
        elif cell == (20, 3):
            assert gates[k] == 0  # Dec-31 16:00's return IS in 2021's training
        elif cell == (4, 4):
            assert gates[k] == 1  # Jan-1 00:00's return is NOT (closes 04:00, past the cut)
        else:
            continue
        checked.add(cell)
    assert checked == {(0, 4), (20, 3), (4, 4)}
    # Fold assignment is by year(ts[k]), so the boundary-crossing stamp is gated by 2020's thin
    # table: gating it with 2021's -- whose training set contains this very return -- would self-leak.
    k_cross = ts.index(disputed_in_a)
    assert gates[k_cross] == 1


# --- 4. Thin-cell default open + favorable = summed noc > 0 ----------------------------------------


def test_thin_cell_open_and_favorable_rule():
    # The planted pattern of test_slot_key_on_decision_boundary: the (0, Monday) cell holds ~52
    # training obs in 2021 and ~104 in 2022.
    ts = _grid(datetime(2020, 1, 1, tzinfo=UTC), 6576)
    noc = [-0.01 if _bcell(t) == (0, 0) else 0.001 for t in ts[:-1]]
    gates = seasonality_gates(noc, ts, config=B1Config())
    for k in range(len(gates)):
        cell = _bcell(ts[k])
        if ts[k].year == 2021 and cell == (0, 0):
            assert gates[k] == 1  # thin cell defaults open
        elif ts[k].year == 2022 and cell == (0, 0):
            assert gates[k] == 0  # >= 100 obs, sum <= 0 -> unfavorable
        elif ts[k].year == 2022:
            assert gates[k] == 1  # >= 100 obs, sum > 0 -> favorable


# --- 5. Hold-through semantics ----------------------------------------------------------------------


def test_hold_through_carries_previous_conditioned_position_verbatim():
    gates = [1, 0, 0, 1]
    scales = [1.0, 0.25, 0.25, 0.5]  # scales at held stamps must be IGNORED, not applied to the held value
    positions = {"X": [2.0, 3.0, 4.0, 5.0], "Y": [-1.0, 1.0, 0.5, 2.0]}
    out = condition_positions(positions, gates, scales)
    assert out["X"] == [2.0, 2.0, 2.0, 2.5]  # held stamps carry 2.0 verbatim (zero turnover); update = target * scale
    assert out["Y"] == [-1.0, -1.0, -1.0, 1.0]
    out0 = condition_positions({"X": [7.0, 1.0]}, [0, 1], [1.0, 1.0])
    assert out0["X"] == [0.0, 1.0]


# --- 6. Scaler per-asset (own-median) normalization (F4) --------------------------------------------


def test_scaler_own_median_normalization():
    # Asset A2 lists mid-series at ~3x A1's vol LEVEL: under own-normalization the listing itself
    # never trips the 0.5 scale, while a 3x SPIKE in A1's own series does.
    cfg = B1Config()
    union = _grid(datetime(2024, 1, 1, tzinfo=UTC), 402)  # 401 return indices / boundaries
    last_boundary = union[-2] + FOUR_H
    spike_start = last_boundary - timedelta(hours=24)  # the last boundary's full 96-bar window
    a1 = _m15_series(
        union[0] - timedelta(hours=20), last_boundary, base=100.0, mult_fn=lambda t: 1.03 if t >= spike_start else 1.01
    )
    a2 = _m15_series(union[0] + timedelta(hours=580), last_boundary, base=200.0, mult_fn=lambda t: 1.03)
    scales = vol_state_scale({"A1": a1, "A2": a2}, union, config=cfg)
    assert len(scales) == 401
    # A2 is live (>= 48 bars) from ~boundary 147 and own-median-normalized (>= 180 own boundaries)
    # from ~boundary 327 -- with a state of 1.0 throughout, its 3x level never scales anything.
    assert all(s == 1.0 for s in scales[:395])
    # A1's spiked window: state ~2.97 vs own median; mean with A2's ~1.0 is ~1.98 > 1.5 -> 0.5.
    assert scales[-1] == 0.5


# --- 7. Edge cases (F7/F8) ---------------------------------------------------------------------------


def test_scaler_neutral_before_180_prior_boundaries():
    # Only 49 boundaries: every per-asset state is neutral (< 180 prior boundaries), so even a
    # genuine 3x own-vol spike at the end must NOT scale.
    union = _grid(datetime(2024, 1, 1, tzinfo=UTC), 50)
    last_boundary = union[-2] + FOUR_H
    spike_start = last_boundary - timedelta(hours=24)
    a1 = _m15_series(
        union[0] - timedelta(hours=20), last_boundary, base=100.0, mult_fn=lambda t: 1.03 if t >= spike_start else 1.01
    )
    scales = vol_state_scale({"A1": a1}, union, config=B1Config())
    assert scales == [1.0] * 49


def test_scaler_excludes_asset_below_min_vol_bars():
    # A1's spike is exactly 1.6x its own trailing vol: 1.6 alone trips the 1.5 threshold, but
    # (1.6 + 1.0) / 2 = 1.3 does not -- so the two variants discriminate a second asset EXCLUDED
    # (< min_vol_bars) from one included, and pin the mean-of-states composition.
    union = _grid(datetime(2024, 1, 1, tzinfo=UTC), 200)  # 199 boundaries; last has 198 prior (>= 180)
    last_boundary = union[-2] + FOUR_H
    spike_start = last_boundary - timedelta(hours=24)
    spike_mult = 1.01**1.6  # log return exactly 1.6x the baseline's -> realized-vol ratio exactly 1.6
    a1 = _m15_series(
        union[0] - timedelta(hours=20), last_boundary, base=100.0, mult_fn=lambda t: spike_mult if t >= spike_start else 1.01
    )
    a2_stale = _m15_series(union[0] - timedelta(hours=20), union[0] - timedelta(hours=15), base=200.0, mult_fn=lambda t: 1.03)
    assert len(a2_stale[0]) == 20
    scales_a = vol_state_scale({"A1": a1, "A2": a2_stale}, union, config=B1Config())
    assert all(s == 1.0 for s in scales_a[:193])
    assert scales_a[-1] == 0.5  # A2 excluded (0 bars in window) -> state = A1's 1.6 alone
    a2_dense = _m15_series(union[0] - timedelta(hours=20), last_boundary, base=200.0, mult_fn=lambda t: 1.03)
    scales_b = vol_state_scale({"A1": a1, "A2": a2_dense}, union, config=B1Config())
    assert scales_b[-1] == 1.0  # A2 included at state 1.0 -> mean 1.3 <= 1.5


def test_scaler_neutral_when_no_qualifying_asset():
    # A mid-series 15m outage: boundaries whose window has no (or < 48) bars have no qualifying
    # asset -> the boundary state is neutral 1.0 (the empty mean must not crash).
    union = _grid(datetime(2024, 1, 1, tzinfo=UTC), 60)
    last_boundary = union[-2] + FOUR_H
    gap_lo = union[0] + timedelta(hours=100)
    gap_hi = union[0] + timedelta(hours=140)
    ts_full, closes_full = _m15_series(union[0] - timedelta(hours=20), last_boundary, base=100.0, mult_fn=lambda t: 1.01)
    kept = [(t, c) for t, c in zip(ts_full, closes_full) if not (gap_lo <= t < gap_hi)]
    a1 = ([t for t, _ in kept], [c for _, c in kept])
    scales = vol_state_scale({"A1": a1}, union, config=B1Config())
    assert len(scales) == 59
    assert scales == [1.0] * 59  # includes the in-gap boundaries (e.g. index 32), which hit the empty-mean path


def test_scaler_substrate_extent_assertion():
    # F8: the 15m substrate's last close must reach the last 4h decision boundary; a short substrate
    # must fail loudly, not silently un-condition the tail.
    union = _grid(datetime(2024, 1, 1, tzinfo=UTC), 12)
    a1 = _m15_series(union[0] - timedelta(hours=20), union[0] + timedelta(hours=20), base=100.0, mult_fn=lambda t: 1.01)
    with pytest.raises(AlphaError, match="substrate"):
        vol_state_scale({"A1": a1}, union, config=B1Config())


def test_interface_guards():
    ts = _grid(datetime(2024, 1, 1, tzinfo=UTC), 5)
    with pytest.raises(AlphaError):
        seasonality_gates([0.1, 0.1], ts, config=B1Config())  # length != len(union_ts) - 1
    with pytest.raises(AlphaError):
        condition_positions({"X": [1.0, 2.0]}, [1, 1, 1], [1.0, 1.0, 1.0])  # mismatched lengths


# --- 8. Engagement helpers ----------------------------------------------------------------------------


def test_engagement_helpers():
    ts = [
        datetime(2020, 12, 31, 12, tzinfo=UTC),
        datetime(2020, 12, 31, 16, tzinfo=UTC),
        datetime(2020, 12, 31, 20, tzinfo=UTC),
        datetime(2021, 1, 1, 0, tzinfo=UTC),
        datetime(2021, 1, 1, 4, tzinfo=UTC),
    ]
    assert per_year_gated_counts([1, 0, 0, 0], ts) == {2020: 2, 2021: 1}
    assert per_year_scaled_counts([1.0, 0.5, 0.5, 1.0], ts) == {2020: 2, 2021: 0}
    turnover = book_turnover({"X": [1.0, 1.0, 0.5], "Y": [0.0, -1.0, -1.0]})
    assert turnover == pytest.approx(2.5)  # |1-0| + |−1−0| + |0.5−1| from flat starts
    # Hold-through reduces turnover: the conditioned book never trades at a held stamp.
    conditioned = condition_positions({"X": [1.0, -1.0, 0.5]}, [1, 0, 1], [1.0, 1.0, 1.0])
    assert book_turnover(conditioned) < book_turnover({"X": [1.0, -1.0, 0.5]})
