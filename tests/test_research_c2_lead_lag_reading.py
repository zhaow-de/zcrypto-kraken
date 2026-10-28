import math
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from cli.alpha.c2 import FOLLOWERS, HORIZONS, LAGS, LEADER, SIDES, STEP, THRESHOLDS, cell_name
from cli.registry.record import validate_metrics
from cli.research import subjects

SUBJECT = "c2-lead-lag-reading"
# 2023 holds the 96 bars before the leader's scale warms, 2024 the other 304.
START, BARS, GAP_AT, LTC_MISSES, SOL_BTC_FROM = datetime(2023, 12, 31, tzinfo=UTC), 400, 200, 50, 96
# Spec D6's `leader` and `followers` keys for the series below: the one 30-minute step puts the last stamp BARS steps
# after the first.
LEADER_COVERAGE = {
    "bars": BARS,
    "first_stamp": int(START.timestamp()),
    "last_stamp": int((START + BARS * STEP).timestamp()),
    "non_15m_steps": 1,
    "sigma_warm_index": 96,
}
FOLLOWER_COVERAGE = {
    f: {"bars": BARS, "first_stamp": int(START.timestamp()), "on_grid": BARS, "off_grid": 0} for f in FOLLOWERS
} | {
    "LTC/EUR": {"bars": BARS - 1, "first_stamp": int(START.timestamp()), "on_grid": BARS - 1, "off_grid": 0},
    "SOL/BTC": {
        "bars": BARS - SOL_BTC_FROM,
        "first_stamp": int((START + SOL_BTC_FROM * STEP).timestamp()),
        "on_grid": BARS - SOL_BTC_FROM,
        "off_grid": 0,
    },
}


def _series() -> dict[str, tuple[list[datetime], list[float]]]:
    """The leader moves 0.02 at every tenth bar and 0.001 either way between, its grid one 30-minute step at bar GAP_AT;
    each EUR alt's next 15m return is twice the leader's last, LTC/EUR without bar LTC_MISSES; ETH/BTC is flat, and SOL/BTC
    flat from bar SOL_BTC_FROM."""
    ts = [START + (i + (i >= GAP_AT)) * STEP for i in range(BARS)]
    r = [0.0] + [0.02 if i % 10 == 0 else (0.001 if i % 2 else -0.001) for i in range(1, BARS)]
    leader, alt = [100.0], [10.0]
    for i in range(1, BARS):
        leader.append(leader[-1] * math.exp(r[i]))
        alt.append(alt[-1] * math.exp(2 * r[i - 1]))
    out = {LEADER: (ts, leader), "ETH/BTC": (ts, [0.05] * BARS), "SOL/BTC": (ts[SOL_BTC_FROM:], [0.002] * (BARS - SOL_BTC_FROM))}
    out["LTC/EUR"] = (ts[:LTC_MISSES] + ts[LTC_MISSES + 1 :], alt[:LTC_MISSES] + alt[LTC_MISSES + 1 :])
    return {f: (ts, alt) for f in FOLLOWERS} | out


class _Reader:
    def __init__(self, series=None, broken=None):
        self.series, self.broken = series or _series(), broken

    def read_series(self, dataset, relpath, window=None):
        if relpath == self.broken:
            raise FileNotFoundError(relpath)
        ts, close = self.series[relpath.removesuffix("/15.parquet")]
        return pl.DataFrame({"ts": ts, "close": close})


class _RaisingReader:
    def read_series(self, dataset, relpath, window=None):
        raise AssertionError(f"read {relpath}")


def test_the_build_returns_exactly_the_declared_keys_and_176_cells():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    assert set(out) == subjects._C2_READING_KEYS and len(out["cells"]) == 176
    assert set(out["cells"]) == {
        cell_name(f, L, th, H, s) for f in FOLLOWERS for L in LAGS for th in THRESHOLDS for H in HORIZONS for s in SIDES
    }
    assert set(out["context"]) == set(FOLLOWERS) and all(
        set(rows) == {f"L{L}|H{H}" for L in LAGS for H in HORIZONS} for rows in out["context"].values()
    )
    assert out["leader"] == LEADER_COVERAGE
    assert out["followers"] == FOLLOWER_COVERAGE
    assert (out["cost_round_trip"], out["sigma_window"], out["mean_block"], out["n_resamples"], out["seed"]) == (
        0.012,
        96,
        30,
        4000,
        42,
    )


def test_the_inputs_half_reads_no_forward_return(monkeypatch):
    monkeypatch.setattr(subjects, "forward_returns", lambda *a, **k: pytest.fail("forward return in the inputs half"))
    inputs = subjects._c2_reading_inputs(subjects._c2_reads(_Reader(), "ohlc-15m", SUBJECT), SUBJECT)
    assert set(inputs._fields) == {"grid", "years", "leader", "returns", "sigma", "signals", "followers"}
    assert inputs.leader == LEADER_COVERAGE
    assert {f: {k: v for k, v in c.items() if k != "closes"} for f, c in inputs.followers.items()} == FOLLOWER_COVERAGE
    assert set(inputs.signals) == {f"L{L}|th{th}" for L in LAGS for th in THRESHOLDS}


def test_the_signals_keys_carry_both_sides_and_the_basis_shape():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    assert set(out["signals"]) == {f"L{L}|th{th}|{s}" for L in LAGS for th in THRESHOLDS for s in SIDES}
    assert all(set(v) == {"per_year", "total"} for v in out["signals"].values())
    assert out["signals"]["L4|th1|up"] == {"per_year": {"2023": 0, "2024": 80}, "total": 80}
    assert out["signals"]["L4|th2|up"]["total"] == out["signals"]["L1|th1|down"]["total"] == 0


def test_a_planted_follower_reads_potential_and_a_flat_cross_reads_none():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    planted = out["cells"]["ETH/EUR|L1|th1|H1|up"]
    assert planted["mean_gross"] > 0.012 and planted["p"] < 0.05 / 176
    assert out["cells"]["ETH/BTC|L1|th1|H1|up"]["mean_gross"] == pytest.approx(0.0, abs=1e-12)


def test_each_cell_is_read_at_its_own_lag_threshold_and_horizon():
    cells = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)["cells"]
    assert cells["ETH/EUR|L1|th1|H4|up"]["mean_gross"] == pytest.approx(0.042)
    assert cells["ETH/EUR|L4|th1|H1|up"]["n"] == 80 and cells["ETH/EUR|L4|th2|H1|up"]["n"] == 0


def test_the_metrics_hold_only_leaves_the_registry_stores():
    out = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)
    validate_metrics(out, "metrics")
    assert out["cells"]["ETH/EUR|L1|th1|H1|down"] == {"per_year": {"2023": {"n": 0}, "2024": {"n": 0}}, "n": 0}


def test_the_context_rows_pair_each_move_with_its_own_forward_return():
    context = subjects._build_c2_lead_lag_reading(_Reader(), "ohlc-15m", None)["context"]
    eth = context["ETH/EUR"]
    assert (
        eth["L1|H1"]["rank_ic_per_year"]["2023"] > 0
        and eth["L1|H4"]["rank_ic_per_year"]["2023"] > 0
        and eth["L4|H1"]["rank_ic_per_year"]["2023"] > 0
    )
    assert eth["L1|H4"]["drift_per_year"]["2024"] > 3 * eth["L1|H1"]["drift_per_year"]["2024"]
    assert context["ETH/BTC"]["L1|H1"]["drift_per_year"] == {"2023": 0.0, "2024": 0.0}
    assert context["SOL/BTC"]["L1|H1"] == {"rank_ic_per_year": {}, "drift_per_year": {"2024": 0.0}}


def test_as_of_and_window_are_refused_before_any_read():
    with pytest.raises(subjects.SubjectError, match="drop --as-of"):
        subjects._build_c2_lead_lag_reading(_RaisingReader(), "ohlc-15m", None, as_of="2026-01-01")
    with pytest.raises(subjects.SubjectError, match="drop --window"):
        subjects._build_c2_lead_lag_reading(_RaisingReader(), "ohlc-15m", ("2024-01-01", "2024-02-01"))


def test_an_unreadable_file_names_its_relpath():
    with pytest.raises(subjects.SubjectError, match="ohlc-15m/SOL/BTC/15.parquet"):
        subjects._build_c2_lead_lag_reading(_Reader(broken="SOL/BTC/15.parquet"), "ohlc-15m", None)


def test_a_close_that_is_not_a_positive_number_is_refused_naming_its_file():
    series = _series()
    ts, close = series["DOT/EUR"]
    series["DOT/EUR"] = (ts, [*close[:10], 0.0, *close[11:]])
    with pytest.raises(subjects.SubjectError, match="c2-lead-lag-reading over the full history: ohlc-15m/DOT/EUR/15.parquet"):
        subjects._build_c2_lead_lag_reading(_Reader(series), "ohlc-15m", None)


def test_a_follower_with_no_stamp_on_the_leaders_grid_is_refused():
    series = _series()
    ts, close = series["AVAX/EUR"]
    series["AVAX/EUR"] = ([t + timedelta(minutes=7) for t in ts], close)
    with pytest.raises(subjects.SubjectError, match="AVAX/EUR has no stamp on the leader's grid"):
        subjects._build_c2_lead_lag_reading(_Reader(series), "ohlc-15m", None)


def test_a_duplicate_leader_stamp_is_refused_through_the_builds_wrap():
    series = _series()
    ts, close = series[LEADER]
    series[LEADER] = ([*ts[:5], ts[4], *ts[6:]], close)
    with pytest.raises(subjects.SubjectError, match="c2-lead-lag-reading over the full history: .*duplicate"):
        subjects._build_c2_lead_lag_reading(_Reader(series), "ohlc-15m", None)


def test_the_subject_is_registered_as_a_reading():
    s = subjects.SUBJECTS["c2-lead-lag-reading"]
    assert s.verdict is None and s.family is None and s.n_trials is None and s.intervals == (15,) and s.seeds == (42,)
    assert (
        s.spec == "docs/specs/00150-c2-lead-lag-reading-design.md"
        and s.metric_keys == subjects._C2_READING_KEYS
        and s.assets == subjects._ASSETS
    )
