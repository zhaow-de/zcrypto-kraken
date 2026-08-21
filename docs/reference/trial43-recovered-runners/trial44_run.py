"""iter-081: T0019 fixed-weight P1 trial (trial 44) — trial 43's construction with weights pinned at 1/3.

Pre-registered rule (decisions log [iter-081], incumbent = trial 43): DD-aware branch
(|S-1.5366|<=0.02 AND maxDD <= 11.81%) or Sharpe-primary (S >= 1.5366 + every ratified leg).
QA gates identical to trial 43 + a bit-identity cross-check of the adaptive variant vs the
trial-43 cache (proves this driver IS trial 43's machinery, weights aside).
"""

from __future__ import annotations

import math
import pickle
import statistics
from datetime import timedelta
from pathlib import Path

from cli.alpha import A1Config, A2Config, a1_book_returns, a1_kill_bar, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.ohlc.dataset import read_parquet
from cli.portfolio import build_combined_system
from cli.portfolio.crossfreq import daily_cadence_governor, expand_daily_positions
from cli.registry import TrialRegistry
from cli.risk import apply_position_caps
from cli.validation import reality_check_pvalue, sharpe

SP = Path(__file__).parent
ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
FEE = 0.006
PPY_4H = 2190
PPY_D = 365
WEIGHT_WINDOW = 180
DECISIVE = 1380
STUBS = {2013, 2026}
INCUMBENT_SHARPE = 1.5366
INCUMBENT_MAXDD = 0.1331
QA_BENCH4H = (1.2128, 1.2447)
QA_A1LF_BOOK = 1.3798
QA_BENCH_DAILY = 1.2455
A2_GRIDS = {((20, 50, 100), 0.12): 1.3274, ((60, 120, 240), 0.10): 1.3017, ((60, 120, 240), 0.12): 1.3585}

t43 = pickle.load(open(SP / "trial43_cache.pkl", "rb"))


def max_dd(rs):
    e, p, m = 1.0, 1.0, 0.0
    for r in rs:
        e *= 1 + r
        p = max(p, e)
        m = max(m, 1 - e / p)
    return m


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


print("loading...", flush=True)
d_ts, d_prices, d_pf = load_union(1440)
h_ts, h_prices, h_pf = load_union(240)
nd, nh = len(d_ts) - 1, len(h_ts) - 1
assert nh == t43["nh"]
ret_h = {a: [r if r is not None else 0.0 for r in _asset_returns(h_pf[a])] for a in ASSETS}
ret_d = {a: [r if r is not None else 0.0 for r in _asset_returns(d_pf[a])] for a in ASSETS}

# ---- B sleeve + QA (identical to trial 43) ----
b2 = dynamic_inverse_vol_basket(d_prices, lookback=30)
eq = [1.0]
for r in b2:
    eq.append(eq[-1] * (1 + r))
gate = sma_gate(eq, window=200)
vt = vol_target(b2, target_vol=0.10 / math.sqrt(PPY_D), lookback=30, max_leverage=1.0)
l3 = [gate[k] * vt[k] for k in range(nd)]
w_d = _inverse_vol_weights(d_prices, lookback=30)
B_daily = {a: [w_d[k].get(a, 0.0) * l3[k] for k in range(nd)] for a in ASSETS}
bench_gross = [l3[k] * b2[k] for k in range(nd)]
noc_B, prev = [], dict.fromkeys(ASSETS, 0.0)
for k in range(nd):
    tk = 0.0
    for a in ASSETS:
        p = B_daily[a][k]
        tk += abs(p - prev[a])
        prev[a] = p
    noc_B.append(bench_gross[k] - tk * FEE)
bb = build_combined_system(d_prices).benchmark_net_of_cost
assert max(abs(noc_B[k] - bb[k]) for k in range(nd)) < 1e-12
assert abs(sharpe(noc_B, periods_per_year=PPY_D) - QA_BENCH_DAILY) < 0.005
print("B QA PASS", flush=True)

# ---- A1 sleeve + QA ----
cfg_a1 = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
ap_a1 = a1_book_returns(d_pf, d_pf["BTC"], config=cfg_a1)["asset_positions"]
CAD = 7


def bs(k, o):
    return 0 if k < o else o + CAD * ((k - o) // CAD)


held = [{a: [ap_a1[a][bs(k, o)] for k in range(nd)] for a in ASSETS} for o in range(CAD)]
A1_daily = {a: [statistics.mean(held[o][a][k] for o in range(CAD)) for k in range(nd)] for a in ASSETS}
noc_offs = []
for o in range(CAD):
    net = [sum(held[o][a][k] * ret_d[a][k] for a in ASSETS) for k in range(nd)]
    turn = [sum(abs(held[o][a][k] - (held[o][a][k - 1] if k > 0 else 0.0)) for a in ASSETS) for k in range(nd)]
    noc_offs.append([net[k] - turn[k] * FEE for k in range(nd)])
book34 = [statistics.mean(noc_offs[o][k] for o in range(CAD)) for k in range(nd)]
assert abs(sharpe(book34, periods_per_year=PPY_D) - QA_A1LF_BOOK) < 0.005
print("A1 QA PASS", flush=True)

# ---- A2 arms + QA (elementwise vs iter-074 cache) ----
cache74 = pickle.load(open(SP.parent / "a2_4h_cache.pkl", "rb"))
assert cache74["n"] == nh
arm_pos = {}
for (lookbacks, tvol), recorded in A2_GRIDS.items():
    cfg = A2Config(lookbacks=lookbacks, short="off", target_vol=tvol, vol_lookback=180, basket_lookback=180, periods_per_year=PPY_4H)
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
    assert max(abs(noc[k] - cache74["arms"][str((lookbacks, tvol))]["noc"][k]) for k in range(nh)) < 1e-12
    assert abs(sharpe(noc, periods_per_year=PPY_4H) - recorded) < 0.005
    arm_pos[(lookbacks, tvol)] = ap
    print(f"arm {(lookbacks, tvol)} QA PASS", flush=True)
A2_h = {a: [statistics.mean(arm_pos[g][a][k] for g in arm_pos) for k in range(nh)] for a in ASSETS}
bench4h = cache74["bench_noc"]
assert abs(sharpe(bench4h, periods_per_year=PPY_4H) - QA_BENCH4H[0]) < 0.005
assert abs(sharpe(bench4h[DECISIVE:], periods_per_year=PPY_4H) - QA_BENCH4H[1]) < 0.005
print("bench4h QA PASS", flush=True)

# ---- expansion (close-time contract) + inflation QA ----
d_close = [t + timedelta(days=1) for t in d_ts]
h_close = [t + timedelta(hours=4) for t in h_ts]
B_h = expand_daily_positions(B_daily, d_close, h_close)
A1_h = expand_daily_positions(A1_daily, d_close, h_close)


def noc_of(pos):
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


for name, pos, anchor in (("B", B_h, QA_BENCH_DAILY), ("A1", A1_h, QA_A1LF_BOOK)):
    s_x = sharpe(noc_of(pos), periods_per_year=PPY_4H)
    assert anchor - 0.15 <= s_x <= anchor + 0.10, f"{name} expansion QA fail: {s_x}"
print("expansion QA PASS", flush=True)

nocs = [noc_of(B_h), noc_of(A1_h), noc_of(A2_h)]

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
    breach = sum(1 for k in range(nh) if any(abs(capped[a][k] - comb[a][k]) > 1e-15 for a in ASSETS))
    noc, prev = [], dict.fromkeys(ASSETS, 0.0)
    turn = []
    for k in range(nh):
        g, tk = 0.0, 0.0
        for a in ASSETS:
            p = capped[a][k]
            g += p * ret_h[a][k]
            tk += abs(p - prev[a])
            prev[a] = p
        turn.append(tk)
        noc.append(g - tk * FEE)
    m = daily_cadence_governor(noc, day_index)
    return [m[k] * noc[k] for k in range(nh)], noc, turn, breach, m


# cross-check: the adaptive variant through THIS driver reproduces trial 43 bit-identically
def adaptive_w(k):
    if k < WEIGHT_WINDOW:
        return (1 / 3, 1 / 3, 1 / 3)
    vols = [statistics.pstdev(s[k - WEIGHT_WINDOW:k]) for s in nocs]
    if any(v <= 0.0 for v in vols):
        return (1 / 3, 1 / 3, 1 / 3)
    inv = [1 / v for v in vols]
    t = sum(inv)
    return tuple(x / t for x in inv)


g43, n43, _, _, _ = combine(adaptive_w)
assert max(abs(g43[k] - t43["governed"][k]) for k in range(nh)) < 1e-12
print("trial-43 bit-identity cross-check PASS", flush=True)

# ---- the trial: fixed 1/3 weights ----
governed, noc_comb, turn, cap_breach, mult = combine(lambda k: (1 / 3, 1 / 3, 1 / 3))
s_full = sharpe(governed, periods_per_year=PPY_4H)
s_dec = sharpe(governed[DECISIVE:], periods_per_year=PPY_4H)
mdd = max_dd(governed)
mdd_pre = max_dd(noc_comb)
gov_engaged = sum(1 for m in mult if m < 1.0)
spot_drag = statistics.mean(turn) * FEE * PPY_4H
print(f"\nfixed-1/3 book: Sharpe {s_full:.4f}/{s_dec:.4f}, maxDD {mdd:.2%} (pre-gov {mdd_pre:.2%}), "
      f"cap breach {cap_breach}, gov engaged {gov_engaged}/{nh}, drag {spot_drag:.2%}/yr", flush=True)

dd_aware = abs(s_full - INCUMBENT_SHARPE) <= 0.02 and mdd <= INCUMBENT_MAXDD - 0.015
primary = s_full >= INCUMBENT_SHARPE
print(f"DD-aware: {dd_aware}; Sharpe-primary trigger: {primary}", flush=True)

# ---- ratified legs ----
years = [h_ts[k + 1].year for k in range(nh)]


def by_year(series):
    out = {}
    for k in range(nh):
        if years[k] in STUBS:
            continue
        out.setdefault(str(years[k]), []).append(series[k])
    return out


reg = TrialRegistry(Path("docs/research/trial-registry.jsonl"))
pps = [r.metrics["per_period_sharpe"] for r in reg.records if r.family == "A1" and "per_period_sharpe" in r.metrics]
var_trials = statistics.variance(pps) / 6.0


def govern(series):
    m = daily_cadence_governor(series, day_index)
    return [m[k] * series[k] for k in range(nh)]


stress15 = govern([noc_comb[k] - turn[k] * 0.003 for k in range(nh)])
stress2x = govern([noc_comb[k] - turn[k] * 0.006 for k in range(nh)])

print("kill bar...", flush=True)
kb = a1_kill_bar(
    governed, bench4h,
    n_trials=4, var_trials=var_trials, mean_block=30, seed=42,
    cost_stressed_returns=stress15,
    regime_slices=by_year(governed), benchmark_slices=by_year(bench4h),
    decisive_start=DECISIVE, n_resamples=2000,
)
print(f"kill bar: passes={kb['passes']} dsr={kb['dsr']:.4f} spa={kb['spa_p_value']:.4f}/{kb['spa_p_value_full']:.4f} "
      f"stress_pp={kb['cost_stress_sharpe']:.5f} ws={kb['worst_slice_pass']}", flush=True)

diff = [[governed[k] - bench4h[k]] for k in range(DECISIVE, nh)]
grid = {}
for block in (30, 102):
    for seed in (42, 7, 1234):
        if block == 30 and seed == 42:
            grid[(block, seed)] = kb["spa_p_value"]
            continue
        grid[(block, seed)] = reality_check_pvalue(diff, mean_block=block, n_resamples=2000, seed=seed)["p_value"]
        print(f"  SPA block {block} seed {seed}: p={grid[(block, seed)]:.4f}", flush=True)
all_sig = all(p < 0.05 for p in grid.values())

s15 = sharpe(stress15, periods_per_year=PPY_4H)
s2x = sharpe(stress2x, periods_per_year=PPY_4H)
adopt = (dd_aware or (primary and kb["passes"] and all_sig))
print(f"\nstress x1.5/x2: {s15:.4f}/{s2x:.4f}; SPA grid all sig: {all_sig}")
print(f"=> {'ADOPT' if adopt else 'REJECT'}", flush=True)

with open(SP / "trial44_cache.pkl", "wb") as f:
    pickle.dump({
        "s_full": s_full, "s_dec": s_dec, "mdd": mdd, "mdd_pre": mdd_pre,
        "cap_breach": cap_breach, "gov_engaged": gov_engaged, "spot_drag": spot_drag,
        "dd_aware": dd_aware, "primary": primary, "kb": kb,
        "grid": {f"{b}/{s}": p for (b, s), p in grid.items()},
        "stress15": s15, "stress2x": s2x, "var_trials": var_trials,
        "per_period_sharpe_4h": sharpe(governed), "adopt": adopt,
        "governed": governed, "bench4h": bench4h, "years": years, "nh": nh,
    }, f)
print("cache written: trial44_cache.pkl", flush=True)
