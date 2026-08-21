"""iter-080 trial 43 verification: independent stage-1 reproduction + win-structure probes.

(i) Rebuild the full construction; assert elementwise identity to trial43_cache.pkl.
(ii) Fixed-1/3-weights counterfactual (the adaptive weighting is the only NEW freedom vs the
     sleeves' individual validations — does the win survive without it?).
(iii) Sleeve pairwise correlations; (iv) per-year Sharpe table; (v) cap/governor decomposition.
"""

from __future__ import annotations

import math
import pickle
import statistics
from datetime import timedelta
from pathlib import Path

from cli.alpha import A1Config, A2Config, a1_book_returns, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.ohlc.dataset import read_parquet
from cli.portfolio.crossfreq import daily_cadence_governor, expand_daily_positions
from cli.risk import apply_position_caps
from cli.validation import sharpe

SP = Path(__file__).parent
ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
FEE = 0.006
PPY_4H = 2190
WEIGHT_WINDOW = 180
cache = pickle.load(open(SP / "trial43_cache.pkl", "rb"))


def load_union(interval):
    frames = {a: read_parquet(Path("data/ohlc-full") / a / "EUR" / f"{interval}.parquet") for a in ASSETS}
    union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
    prices = {}
    for a in ASSETS:
        m = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list()))
        prices[a] = [m.get(t) for t in union_ts]
    btc = list(prices["BTC"])
    last = None
    for i in range(len(btc)):
        if btc[i] is None:
            btc[i] = last
        else:
            last = btc[i]
    pf = dict(prices)
    pf["BTC"] = btc
    return union_ts, prices, pf


d_ts, d_prices, d_pf = load_union(1440)
h_ts, h_prices, h_pf = load_union(240)
nd, nh = len(d_ts) - 1, len(h_ts) - 1
ret_h = {a: [r if r is not None else 0.0 for r in _asset_returns(h_pf[a])] for a in ASSETS}

b2 = dynamic_inverse_vol_basket(d_prices, lookback=30)
eq = [1.0]
for r in b2:
    eq.append(eq[-1] * (1 + r))
gate = sma_gate(eq, window=200)
vt = vol_target(b2, target_vol=0.10 / math.sqrt(365), lookback=30, max_leverage=1.0)
l3 = [gate[k] * vt[k] for k in range(nd)]
w_d = _inverse_vol_weights(d_prices, lookback=30)
B_daily = {a: [w_d[k].get(a, 0.0) * l3[k] for k in range(nd)] for a in ASSETS}

cfg_a1 = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
ap_a1 = a1_book_returns(d_pf, d_pf["BTC"], config=cfg_a1)["asset_positions"]
CAD = 7
A1_daily = {
    a: [statistics.mean(ap_a1[a][0 if k < o else o + CAD * ((k - o) // CAD)] for o in range(CAD)) for k in range(nd)]
    for a in ASSETS
}

arm_pos = {}
for lookbacks, tvol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12)):
    cfg = A2Config(lookbacks=lookbacks, short="off", target_vol=tvol, vol_lookback=180, basket_lookback=180, periods_per_year=PPY_4H)
    arm_pos[(lookbacks, tvol)] = a2_book_returns(h_pf, config=cfg)["asset_positions"]
A2_h = {a: [statistics.mean(arm_pos[g][a][k] for g in arm_pos) for k in range(nh)] for a in ASSETS}

d_ts_close = [t + timedelta(days=1) for t in d_ts]
h_ts_close = [t + timedelta(hours=4) for t in h_ts]
B_h = expand_daily_positions(B_daily, d_ts_close, h_ts_close)
A1_h = expand_daily_positions(A1_daily, d_ts_close, h_ts_close)


def sleeve_noc(pos):
    out, prev = [], dict.fromkeys(ASSETS, 0.0)
    for k in range(nh):
        g, tk = 0.0, 0.0
        for a in ASSETS:
            p = pos[a][k]
            g += p * ret_h[a][k]
            tk += abs(p - prev[a])
            prev[a] = p
        out.append(g - tk * FEE)
    return out


nocs = [sleeve_noc(B_h), sleeve_noc(A1_h), sleeve_noc(A2_h)]

dates = [h_ts[k + 1].date() for k in range(nh)]
seen: dict = {}
day_index = [seen.setdefault(x, len(seen)) for x in dates]


def combine(weight_fn):
    comb = {a: [None] * nh for a in ASSETS}
    for k in range(nh):
        w = weight_fn(k)
        for a in ASSETS:
            comb[a][k] = w[0] * B_h[a][k] + w[1] * A1_h[a][k] + w[2] * A2_h[a][k]
    capped = apply_position_caps(comb, long_cap=0.20, short_cap=0.10)
    noc, prev = [], dict.fromkeys(ASSETS, 0.0)
    for k in range(nh):
        g, tk = 0.0, 0.0
        for a in ASSETS:
            p = capped[a][k]
            g += p * ret_h[a][k]
            tk += abs(p - prev[a])
            prev[a] = p
        noc.append(g - tk * FEE)
    m = daily_cadence_governor(noc, day_index)
    return [m[k] * noc[k] for k in range(nh)], noc


def adaptive_w(k):
    if k < WEIGHT_WINDOW:
        return (1 / 3, 1 / 3, 1 / 3)
    vols = [statistics.pstdev(s[k - WEIGHT_WINDOW:k]) for s in nocs]
    if any(v <= 0.0 for v in vols):
        return (1 / 3, 1 / 3, 1 / 3)
    inv = [1 / v for v in vols]
    t = sum(inv)
    return tuple(x / t for x in inv)


governed, noc_comb = combine(adaptive_w)
md_g = max(abs(governed[k] - cache["governed"][k]) for k in range(nh))
md_n = max(abs(noc_comb[k] - cache["noc_comb"][k]) for k in range(nh))
assert md_g < 1e-12 and md_n < 1e-12, f"REPRODUCTION FAILED: {md_g}, {md_n}"
print(f"(i) full reproduction PASS (max diffs {md_g:.1e}, {md_n:.1e})", flush=True)

fixed_governed, fixed_noc = combine(lambda k: (1 / 3, 1 / 3, 1 / 3))
print(f"(ii) fixed-1/3 counterfactual: governed Sharpe {sharpe(fixed_governed, periods_per_year=PPY_4H):.4f} "
      f"(adaptive: {sharpe(governed, periods_per_year=PPY_4H):.4f})", flush=True)


def corr(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    sx, sy = statistics.pstdev(x), statistics.pstdev(y)
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x[k] - mx) * (y[k] - my) for k in range(len(x))) / (len(x) * sx * sy)


names = ["B", "A1", "A2"]
print("(iii) sleeve noc correlations (full window):")
for i in range(3):
    for j in range(i + 1, 3):
        print(f"   {names[i]}-{names[j]}: {corr(nocs[i], nocs[j]):.3f}")
print("   sleeve Sharpes (4h): " + ", ".join(f"{names[i]} {sharpe(nocs[i], periods_per_year=PPY_4H):.4f}" for i in range(3)))

years = [h_ts[k + 1].year for k in range(nh)]
print("(iv) per-year Sharpe (governed vs 4h bench):")
bench = cache["bench4h"]
for y in sorted(set(years)):
    idx = [k for k in range(nh) if years[k] == y]
    if len(idx) < 100:
        continue
    gy = [governed[k] for k in idx]
    by = [bench[k] for k in idx]
    print(f"   {y}: book {sharpe(gy, periods_per_year=PPY_4H):7.3f}  bench {sharpe(by, periods_per_year=PPY_4H):7.3f}")

ungoverned_s = sharpe(noc_comb, periods_per_year=PPY_4H)
print(f"(v) decomposition: ungoverned {ungoverned_s:.4f} -> governed {sharpe(governed, periods_per_year=PPY_4H):.4f}; "
      f"NaN/inf check: {all(math.isfinite(x) for x in governed)}", flush=True)
