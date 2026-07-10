"""Tests for the record-44 builder (cli/portfolio/crossfreq_system.py): verified + fast paths.

Unit tests run on synthetic two-asset grids (no dataset), including the CI-unconditional
fast-vs-verified equivalence checks. Two tests need the canonical data/ohlc-full machine: the
frozen-figure regression reproduces registry trial 44 end to end and is slow (~4 min measured:
the three A2 arms run twice — once inside the builder's ~2 min verified-path build, once for the
driver-transcribed sleeve-anchor QA), and the fast-path full-history equivalence gate builds both
paths once (~2 min, dominated by the verified build).
"""

import math
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cli.portfolio import (
    CrossfreqSystemConfig,
    CrossfreqSystemResult,
    PortfolioError,
    build_crossfreq_system,
    build_crossfreq_system_fast,
)

CFG2 = CrossfreqSystemConfig(assets=("AAA", "BTC"))


def synthetic_grids(n_days: int, *, n_extra_h4: int = 0):
    """Aligned daily/4h bar-START stamp grids: daily stamps at day k 00:00, 4h stamps every 4h over
    the same span, both ending at the same close (day n_days 00:00) like the canonical dataset.
    n_extra_h4 appends further real 4h bars past the last daily close (the live mid-day case)."""
    start = datetime(2024, 1, 1)
    n_h4 = 6 * n_days + n_extra_h4
    h4_ts = [start + timedelta(hours=4 * k) for k in range(n_h4)]
    daily_ts = [start + timedelta(days=k) for k in range(n_days)]
    h4_prices = {
        "AAA": [80.0 * (1 + 0.0009) ** k * (1 + 0.03 * math.sin(k / 5)) for k in range(n_h4)],
        "BTC": [100.0 * (1 + 0.0011) ** k * (1 + 0.02 * math.sin(k / 7)) for k in range(n_h4)],
    }
    daily_prices = {a: [h4_prices[a][6 * k + 5] for k in range(n_days)] for a in h4_prices}
    return daily_prices, daily_ts, h4_prices, h4_ts


@pytest.mark.parametrize(
    "kwargs",
    [
        {"assets": ()},
        {"assets": ("AAA",)},  # no BTC (the A-sleeve books and the ffill feed require it)
        {"assets": ("BTC", "BTC")},  # duplicate
        {"assets": ("BTC", "")},  # empty name
        {"assets": "BTC"},  # not a tuple
        {"spot_fee_per_side": 0.0},
        {"spot_fee_per_side": float("nan")},
        {"spot_fee_per_side": True},  # bool is not a fee
        {"long_cap": -0.2},
        {"long_cap": True},  # bool is not a cap
        {"short_cap": 0.0},
        {"short_cap": True},  # bool is not a cap
        {"a2_arms": ()},
        {"a2_arms": (((20, 50, 100),),)},  # not a (lookbacks, target_vol) pair
        {"a2_arms": (((), 0.12),)},  # empty lookbacks
        {"a2_arms": (((20, 50, 1), 0.12),)},  # lookback < 2
        {"a2_arms": (((20, 50, 100), 0.0),)},  # target_vol <= 0
        {"a2_arms": (((20, 50, 100), True),)},  # bool is not a target_vol
    ],
)
@pytest.mark.parametrize("builder", [build_crossfreq_system, build_crossfreq_system_fast])
def test_invalid_config(kwargs, builder):
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(3)
    cfg = CrossfreqSystemConfig(**{"assets": ("AAA", "BTC"), **kwargs})
    with pytest.raises(PortfolioError):
        builder(d_prices, d_ts, h_prices, h_ts, config=cfg)


def test_degenerate_inputs():
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(3)
    cases = [
        ({}, d_ts, h_prices, h_ts),  # empty dict
        ("not a dict", d_ts, h_prices, h_ts),
        (None, d_ts, h_prices, h_ts),
        (d_prices, d_ts, {"AAA": h_prices["AAA"]}, h_ts),  # missing asset key
        (d_prices, d_ts, {**h_prices, "XXX": h_prices["AAA"]}, h_ts),  # extra asset key
        (d_prices, [d_ts[0]], h_prices, h_ts),  # ts too short (and mismatched with series)
        (d_prices, list(reversed(d_ts)), h_prices, h_ts),  # not ascending
        (d_prices, [d_ts[0]] * len(d_ts), h_prices, h_ts),  # not strictly ascending
        (d_prices, [1, 2, 3], h_prices, h_ts),  # stamps must be datetimes
        ({**d_prices, "AAA": d_prices["AAA"][:-1]}, d_ts, h_prices, h_ts),  # series/ts length mismatch
        (d_prices, d_ts, h_prices, h_ts[:-1]),  # 4h series/ts length mismatch
        (d_prices, d_ts, h_prices, "not a list"),
    ]
    for args in cases:
        with pytest.raises(PortfolioError):
            build_crossfreq_system(*args, config=CFG2)


def test_dummy_close_semantics():
    # The synthetic forming-bar close reuses the last close; a None last close stays None (honest
    # delisted-tail semantics — an asset absent at the snapshot's edge stays absent on the forming
    # bar instead of being resurrected from an older price).
    from cli.portfolio.crossfreq_system import _dummy_close

    assert _dummy_close([100.0, 101.0]) == 101.0
    assert _dummy_close([100.0, None, 102.0]) == 102.0
    assert _dummy_close([100.0, 101.0, None]) is None
    assert _dummy_close([None, None]) is None


@pytest.fixture(scope="module")
def grids220():
    # 220 days: past the 200d gate warm-up for both daily sleeves and the ~420-bar A2 warm-up, so
    # every sleeve is non-flat at the grid's end. (A shorter all-warm-up grid cannot go through the
    # builder at all: the A-sleeve books reject their own zero-variance flat net series.)
    return synthetic_grids(220)


@pytest.fixture(scope="module")
def base_build(grids220):
    return build_crossfreq_system(*grids220, config=CFG2)


def test_end_to_end_shapes_and_identities(base_build, grids220):
    # The synthetic mini-grid end-to-end: shapes, the hand-checkable day_index structure, and an
    # independent recomputation of every layer downstream of the sleeves (fixed 1/3 combine ->
    # caps -> costing -> governor -> targets) compared exactly against the builder's output.
    from cli.portfolio import daily_cadence_governor
    from cli.risk import apply_position_caps

    d_prices, d_ts, h_prices, h_ts = grids220
    res = base_build
    assert isinstance(res, CrossfreqSystemResult)
    assets = CFG2.assets
    n = res.n_periods
    assert n == len(h_ts) - 1 == 6 * 220 - 1
    assert set(res.sleeve_positions) == {"B", "A1", "A2"}
    for a in assets:
        assert len(res.final_targets[a]) == n + 1  # completed bars + the forming interval
        for sleeve in res.sleeve_positions.values():
            assert len(sleeve[a]) == n + 1
        assert res.final_targets[a][:100] == [0.0] * 100  # warm-up is flat
    assert len(res.governed_net) == len(res.ungoverned_net) == n
    assert len(res.multipliers) == n + 1

    # day_index: dense ranks of date(h4_ts[k+1]) over the dummy-extended grid — the first calendar
    # day holds 5 return bars (stamps 04:00..20:00), every later one 6; the forming row (synthetic
    # stamp at midnight) opens a new day.
    assert len(res.day_index) == n + 1
    assert res.day_index[:11] == [0] * 5 + [1] * 6
    assert res.day_index[-1] == res.day_index[-2] + 1 == 220

    # recompute the combination path from the returned sleeves and the raw fixture prices
    third = 1 / 3
    combined = {
        a: [
            third * res.sleeve_positions["B"][a][k]
            + third * res.sleeve_positions["A1"][a][k]
            + third * res.sleeve_positions["A2"][a][k]
            for k in range(n + 1)
        ]
        for a in assets
    }
    capped = apply_position_caps(combined, long_cap=0.20, short_cap=0.10)
    rets = {a: [h_prices[a][k + 1] / h_prices[a][k] - 1 for k in range(n)] for a in assets}
    noc = []
    prev = dict.fromkeys(assets, 0.0)
    for k in range(n):
        gross, turnover = 0.0, 0.0
        for a in assets:
            p = capped[a][k]
            gross += p * rets[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        noc.append(gross - turnover * 0.006)
    assert noc == res.ungoverned_net
    mult = daily_cadence_governor(noc + [0.0], res.day_index)
    assert mult == res.multipliers
    assert [mult[k] * noc[k] for k in range(n)] == res.governed_net
    for a in assets:
        assert [mult[k] * capped[a][k] for k in range(n + 1)] == res.final_targets[a]
    assert res.cap_breach_bars == sum(1 for k in range(n) if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in assets))
    assert res.governor_engaged_bars == sum(1 for m in mult[:n] if m < 1.0)

    # deterministic
    assert build_crossfreq_system(d_prices, d_ts, h_prices, h_ts, config=CFG2) == res


def test_newest_row_carries_daily_sleeve_content(base_build):
    # Invariant (a): the forming-interval row must carry the daily sleeves' forming-day positions —
    # guards the expansion tail rule silently zeroing B/A1 on the newest row.
    newest = base_build.n_periods
    for sleeve in ("B", "A1"):
        assert any(base_build.sleeve_positions[sleeve][a][newest] != 0.0 for a in ("AAA", "BTC")), sleeve
    assert any(base_build.final_targets[a][newest] != 0.0 for a in ("AAA", "BTC"))


def test_newest_row_extend_by_one_real_bar(base_build):
    # Invariant (b): extend the 4h grid by one real bar (same daily grid — the live mid-day case);
    # the previously-newest row is now interior and must be reproduced exactly, and every
    # completed-bar quantity is prefix-stable (the frozen figures pin exactly this no-append
    # equivalence on the real dataset).
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(220, n_extra_h4=1)
    ext = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    n = base_build.n_periods
    assert ext.n_periods == n + 1
    for a in ("AAA", "BTC"):
        assert ext.final_targets[a][: n + 1] == base_build.final_targets[a]
        for sleeve in ("B", "A1", "A2"):
            assert ext.sleeve_positions[sleeve][a][: n + 1] == base_build.sleeve_positions[sleeve][a]
    assert ext.multipliers[: n + 1] == base_build.multipliers
    assert ext.day_index[: n + 1] == base_build.day_index
    assert ext.governed_net[:n] == base_build.governed_net
    assert ext.ungoverned_net[:n] == base_build.ungoverned_net


def test_newest_row_extend_by_one_real_daily_bar(base_build):
    # The daily-grid mirror of the 4h extend-by-one invariant: synthetic_grids(221) adds one REAL
    # daily bar (and its day of real 4h bars); every previously-newest row — including the daily
    # sleeves' forming-day row, now decided from a real daily close — must be reproduced exactly,
    # and every completed-bar quantity is prefix-stable.
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(221)
    ext = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    n = base_build.n_periods
    assert ext.n_periods == n + 6
    for a in ("AAA", "BTC"):
        assert ext.final_targets[a][: n + 1] == base_build.final_targets[a]
        for sleeve in ("B", "A1", "A2"):
            assert ext.sleeve_positions[sleeve][a][: n + 1] == base_build.sleeve_positions[sleeve][a]
    assert ext.multipliers[: n + 1] == base_build.multipliers
    assert ext.day_index[: n + 1] == base_build.day_index
    assert ext.governed_net[:n] == base_build.governed_net
    assert ext.ungoverned_net[:n] == base_build.ungoverned_net


def test_newest_row_dummy_close_insensitivity(base_build, monkeypatch):
    # Invariant (c): the synthetic forming-bar close is a placeholder — perturbing it must leave
    # the entire result (newest row included) unchanged.
    import cli.portfolio.crossfreq_system as mod

    orig = mod._dummy_close
    monkeypatch.setattr(mod, "_dummy_close", lambda series: orig(series) * 1.7)
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(220)
    perturbed = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    assert perturbed == base_build


def assert_results_equivalent(fast: CrossfreqSystemResult, verified: CrossfreqSystemResult, tol: float = 1e-12):
    # The equivalence gate's shape: exact on every integer field, elementwise <= tol on every float
    # series (final_targets, both nets, multipliers, all sleeve positions).
    assert fast.n_periods == verified.n_periods
    assert fast.day_index == verified.day_index
    assert fast.cap_breach_bars == verified.cap_breach_bars
    assert fast.governor_engaged_bars == verified.governor_engaged_bars
    assert set(fast.final_targets) == set(verified.final_targets)
    for a in verified.final_targets:
        assert max(abs(f - v) for f, v in zip(fast.final_targets[a], verified.final_targets[a], strict=True)) <= tol, a
    assert set(fast.sleeve_positions) == set(verified.sleeve_positions)
    for name in verified.sleeve_positions:
        for a in verified.sleeve_positions[name]:
            fast_s, ver_s = fast.sleeve_positions[name][a], verified.sleeve_positions[name][a]
            assert max(abs(f - v) for f, v in zip(fast_s, ver_s, strict=True)) <= tol, (name, a)
    for field in ("governed_net", "ungoverned_net", "multipliers"):
        fast_s, ver_s = getattr(fast, field), getattr(verified, field)
        assert max(abs(f - v) for f, v in zip(fast_s, ver_s, strict=True)) <= tol, field


def test_fast_path_equivalence_mini_grid(base_build, grids220):
    # The CI-unconditional equivalence check: on the synthetic 220-day fixture the fast path must
    # reproduce the verified path on every field (exact integers, <= 1e-12 elementwise floats).
    fast = build_crossfreq_system_fast(*grids220, config=CFG2)
    assert_results_equivalent(fast, base_build)
    # The paths are in fact bit-identical by construction — enforce it in CI, not just on the data machine.
    assert fast == base_build


def test_fast_path_equivalence_mini_grid_mid_day(base_build):
    # Same gate on the live mid-day shape (one real 4h bar past the last daily close) — the grid
    # geometry the engine's intraday cycles actually present.
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(220, n_extra_h4=1)
    verified = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    fast = build_crossfreq_system_fast(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    assert_results_equivalent(fast, verified)
    assert fast == verified
    assert fast.n_periods == base_build.n_periods + 1


def test_fast_path_equivalence_none_bearing_grid():
    # None paths in CI: a late-listed asset with mid-history gaps and a delisted None tail, plus a
    # mid-history BTC union gap — the shapes that exercise _trailing_stdevs' None counter,
    # _map_own_to_union, ret_valid masking, and _dummy_close's None-tail semantics.
    d_prices, d_ts, h_prices, h_ts = synthetic_grids(220)
    for prices, span in ((d_prices, len(d_ts)), (h_prices, len(h_ts))):
        aaa = list(prices["AAA"])
        late_until = span // 4
        for k in range(late_until):
            aaa[k] = None  # late listing
        aaa[span // 2] = None  # mid-history gap
        aaa[span // 2 + 1] = None
        for k in range(span - 3, span):
            aaa[k] = None  # delisted tail
        prices["AAA"] = aaa
        btc = list(prices["BTC"])
        btc[span // 3] = None  # BTC union gap (ffill path)
        prices["BTC"] = btc
    verified = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    fast = build_crossfreq_system_fast(d_prices, d_ts, h_prices, h_ts, config=CFG2)
    assert_results_equivalent(fast, verified)
    assert fast == verified


DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "ohlc-full"

ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
FEE = 0.006
DECISIVE = 1380

# The frozen trial-43/44 oracle's extent (per-pair completed-bar count + last bar-start stamp),
# read from this machine's data/ohlc-full at implementation time. data/ohlc-full is never appended
# to — the engine's live store is a separate root (T0018).
EXTENT = {
    1440: {
        "ADA": 2742,
        "AVAX": 1562,
        "BTC": 4581,
        "DOGE": 2295,
        "DOT": 2052,
        "ETH": 3890,
        "LINK": 2380,
        "LTC": 4542,
        "SOL": 1749,
        "XRP": 3239,
    },
    240: {
        "ADA": 16446,
        "AVAX": 9365,
        "BTC": 27332,
        "DOGE": 13710,
        "DOT": 12306,
        "ETH": 23292,
        "LINK": 14267,
        "LTC": 26746,
        "SOL": 10486,
        "XRP": 19423,
    },
}
LAST_TS = {
    1440: datetime(2026, 3, 31, 0, 0, tzinfo=timezone.utc),
    240: datetime(2026, 3, 31, 20, 0, tzinfo=timezone.utc),
}


def max_dd(rs):
    eq, peak, dd = 1.0, 1.0, 0.0
    for r in rs:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return dd


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_frozen_figures_regression():
    # Registry trial 44's figures, reproduced through the committed verified path (the iter-081
    # driver's QA gates, made permanent). Extent guard FIRST, then the driver-transcribed sleeve
    # anchors, then the builder's frozen headline figures.
    from cli.alpha import A1Config, A2Config, a1_book_returns, a2_book_returns
    from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
    from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
    from cli.ohlc.dataset import read_parquet
    from cli.portfolio import build_combined_system, expand_daily_positions
    from cli.validation import sharpe

    def load_union(interval):
        frames = {a: read_parquet(DATA_ROOT / a / "EUR" / f"{interval}.parquet") for a in ASSETS}
        for a in ASSETS:
            ts = frames[a]["ts"].to_list()
            assert len(ts) == EXTENT[interval][a] and ts[-1] == LAST_TS[interval], (
                f"canonical dataset drifted — STOP: {a}/{interval} has {len(ts)} bars ending {ts[-1]}, expected "
                f"{EXTENT[interval][a]} ending {LAST_TS[interval]}; data/ohlc-full is the frozen trial-44 regression "
                "oracle and must never be appended to (the engine's live store is a separate root, T0018)"
            )
        union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
        prices = {}
        for a in ASSETS:
            m = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list()))
            prices[a] = [m.get(t) for t in union_ts]
        return union_ts, prices

    d_ts, d_prices = load_union(1440)
    h_ts, h_prices = load_union(240)
    nd, nh = len(d_ts) - 1, len(h_ts) - 1

    def ffill_btc(prices):
        btc = list(prices["BTC"])
        last = None
        for i, v in enumerate(btc):
            if v is None:
                btc[i] = last
            else:
                last = v
        out = dict(prices)
        out["BTC"] = btc
        return out

    d_pf, h_pf = ffill_btc(d_prices), ffill_btc(h_prices)
    ret_d = {a: [r if r is not None else 0.0 for r in _asset_returns(d_pf[a])] for a in ASSETS}

    # --- B sleeve anchor: elementwise identity with record 33's benchmark + daily bench Sharpe ---
    b2 = dynamic_inverse_vol_basket(d_prices, lookback=30)
    eq = [1.0]
    for r in b2:
        eq.append(eq[-1] * (1 + r))
    gate = sma_gate(eq, window=200)
    vt = vol_target(b2, target_vol=0.10 / math.sqrt(365), lookback=30, max_leverage=1.0)
    l3 = [gate[k] * vt[k] for k in range(nd)]
    w_d = _inverse_vol_weights(d_prices, lookback=30)
    b_daily = {a: [w_d[k].get(a, 0.0) * l3[k] for k in range(nd)] for a in ASSETS}
    bench_gross = [l3[k] * b2[k] for k in range(nd)]
    noc_b, prev = [], dict.fromkeys(ASSETS, 0.0)
    for k in range(nd):
        tk = 0.0
        for a in ASSETS:
            p = b_daily[a][k]
            tk += abs(p - prev[a])
            prev[a] = p
        noc_b.append(bench_gross[k] - tk * FEE)
    bench = build_combined_system(d_prices).benchmark_net_of_cost
    assert max(abs(noc_b[k] - bench[k]) for k in range(nd)) < 1e-12
    assert sharpe(noc_b, periods_per_year=365) == pytest.approx(1.2455, abs=0.005)

    # --- A1 sleeve anchor: A1-lf weekly v0.12, 7-offset-mean book ---
    cfg_a1 = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    ap_a1 = a1_book_returns(d_pf, d_pf["BTC"], config=cfg_a1)["asset_positions"]

    def bs(k, o):
        return 0 if k < o else o + 7 * ((k - o) // 7)

    held = [{a: [ap_a1[a][bs(k, o)] for k in range(nd)] for a in ASSETS} for o in range(7)]
    a1_daily = {a: [statistics.mean(held[o][a][k] for o in range(7)) for k in range(nd)] for a in ASSETS}
    noc_offs = []
    for o in range(7):
        net = [sum(held[o][a][k] * ret_d[a][k] for a in ASSETS) for k in range(nd)]
        turn = [sum(abs(held[o][a][k] - (held[o][a][k - 1] if k > 0 else 0.0)) for a in ASSETS) for k in range(nd)]
        noc_offs.append([net[k] - turn[k] * FEE for k in range(nd)])
    book = [statistics.mean(noc_offs[o][k] for o in range(7)) for k in range(nd)]
    assert sharpe(book, periods_per_year=365) == pytest.approx(1.3798, abs=0.005)

    # --- A2 arm anchors: the three adopted arms, each short=off, 180/180, ppy 2190 ---
    arms = []
    for (lookbacks, tvol), anchor in (
        (((20, 50, 100), 0.12), 1.3274),
        (((60, 120, 240), 0.10), 1.3017),
        (((60, 120, 240), 0.12), 1.3585),
    ):
        cfg = A2Config(
            lookbacks=lookbacks, short="off", target_vol=tvol, vol_lookback=180, basket_lookback=180, periods_per_year=2190
        )
        out = a2_book_returns(h_pf, config=cfg)
        ap = out["asset_positions"]
        noc, prev = [], dict.fromkeys(ASSETS, 0.0)
        for k in range(nh):
            tk = 0.0
            for a in ASSETS:
                p = ap[a][k]
                tk += abs(p - prev[a])
                prev[a] = p
            noc.append(out["net_returns"][k] - tk * FEE)
        assert sharpe(noc, periods_per_year=2190) == pytest.approx(anchor, abs=0.005), (lookbacks, tvol)
        arms.append(ap)

    # driver-style (no-append) expanded sleeves for the builder cross-check
    d_close = [t + timedelta(days=1) for t in d_ts]
    h_close = [t + timedelta(hours=4) for t in h_ts]
    b_h = expand_daily_positions(b_daily, d_close, h_close)
    a1_h = expand_daily_positions(a1_daily, d_close, h_close)
    a2_h = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(nh)] for a in ASSETS}

    # --- the builder: registry record 44's frozen headline figures ---
    res = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts)
    assert res.n_periods == nh
    assert sharpe(res.governed_net, periods_per_year=2190) == pytest.approx(1.5609, abs=0.005)
    assert sharpe(res.governed_net[DECISIVE:], periods_per_year=2190) == pytest.approx(1.5583, abs=0.005)
    assert max_dd(res.governed_net) == pytest.approx(0.1357, abs=0.0005)
    assert max_dd(res.ungoverned_net) == pytest.approx(0.1866, abs=0.0005)
    assert res.cap_breach_bars == 1318
    assert res.governor_engaged_bars == 7302

    # completed-bar sleeve rows == the driver-style no-append construction, elementwise
    for name, recon in (("B", b_h), ("A1", a1_h), ("A2", a2_h)):
        for a in ASSETS:
            got = res.sleeve_positions[name][a]
            assert len(got) == nh + 1
            assert max(abs(got[k] - recon[a][k]) for k in range(nh)) <= 1e-12, (name, a)


def _load_union_guarded(interval):
    # The full-history loader with the extent guard (per-pair bar count + last ts pinned to the
    # frozen trial-43/44 oracle) — fails loudly before any figure comparison if the dataset drifts.
    from cli.ohlc.dataset import read_parquet

    frames = {a: read_parquet(DATA_ROOT / a / "EUR" / f"{interval}.parquet") for a in ASSETS}
    for a in ASSETS:
        ts = frames[a]["ts"].to_list()
        assert len(ts) == EXTENT[interval][a] and ts[-1] == LAST_TS[interval], (
            f"canonical dataset drifted — STOP: {a}/{interval} has {len(ts)} bars ending {ts[-1]}, expected "
            f"{EXTENT[interval][a]} ending {LAST_TS[interval]}; data/ohlc-full is the frozen trial-44 regression "
            "oracle and must never be appended to (the engine's live store is a separate root, T0018)"
        )
    union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
    prices = {}
    for a in ASSETS:
        m = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list()))
        prices[a] = [m.get(t) for t in union_ts]
    return union_ts, prices


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_fast_path_full_history_equivalence():
    """The equivalence gate (spec 00040, hard): fast vs verified over the full frozen history —
    elementwise <= 1e-12 on final_targets and both net series, IDENTICAL cap_breach_bars and
    governor_engaged_bars, headline Sharpes/maxDD rounding to the same 4dp values.

    Measured wall-clock on the data machine (2026-07-10): verified 111.5 s, fast 1.9 s (~58x).
    """
    from cli.validation import sharpe

    d_ts, d_prices = _load_union_guarded(1440)
    h_ts, h_prices = _load_union_guarded(240)

    t0 = time.perf_counter()
    verified = build_crossfreq_system(d_prices, d_ts, h_prices, h_ts)
    t_verified = time.perf_counter() - t0
    t0 = time.perf_counter()
    fast = build_crossfreq_system_fast(d_prices, d_ts, h_prices, h_ts)
    t_fast = time.perf_counter() - t0
    print(f"\nwall-clock: verified {t_verified:.1f}s, fast {t_fast:.1f}s ({t_verified / t_fast:.1f}x)")

    assert_results_equivalent(fast, verified)
    # headline figures (registry record 44's set) round to the same 4dp values
    assert round(sharpe(fast.governed_net, periods_per_year=2190), 4) == round(
        sharpe(verified.governed_net, periods_per_year=2190), 4
    )
    assert round(sharpe(fast.governed_net[DECISIVE:], periods_per_year=2190), 4) == round(
        sharpe(verified.governed_net[DECISIVE:], periods_per_year=2190), 4
    )
    assert round(max_dd(fast.governed_net), 4) == round(max_dd(verified.governed_net), 4)
    assert round(max_dd(fast.ungoverned_net), 4) == round(max_dd(verified.ungoverned_net), 4)
