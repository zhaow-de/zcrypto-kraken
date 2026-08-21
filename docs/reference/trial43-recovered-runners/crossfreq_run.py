"""iter-080: the 00038 cross-frequency combination — P1 trial (T0011's sole remainder).

Construction per docs/specs/00038-cross-frequency-combination-design.md (pre-registered):
three sleeves on the 4h union calendar — B (daily benchmark w*l3, intraday-held), A1 (A1-lf
weekly v0.12 7-offset-mean positions, intraday-held), A2 (equal-weight ensemble of trials
37-39's native-4h arms) — rolling 180-bar inverse-vol sleeve weights through k-1 (ANY
degenerate window -> all 1/3), cap 20%/10%, full per-asset costing at 0.006/side, §10
governor at daily cadence. QA gates before any verdict; STOP on failure.

Stage 1 (this script): books + QA + combination + headline figures -> trial43_cache.pkl.
Stage 2 (separate, only if the Sharpe-primary branch fires): ratified kill bar.
"""

from __future__ import annotations

import math
import pickle
import statistics
from pathlib import Path

from cli.alpha import A1Config, A2Config, a1_book_returns, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.ohlc.dataset import read_parquet
from cli.portfolio import build_combined_system
from cli.portfolio.crossfreq import daily_cadence_governor, expand_daily_positions
from cli.risk import apply_position_caps
from cli.validation import sharpe

SP = Path(__file__).parent
ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
FEE = 0.006
PPY_4H = 2190
PPY_D = 365
WEIGHT_WINDOW = 180  # 30 days of 4h bars
DECISIVE_4H = 1380
RECORD33_SHARPE = 1.3263
RECORD33_MAXDD = 0.1449
A2_GRIDS = {  # trials 37-39: (lookbacks, target_vol) -> recorded full-window noc Sharpe
    ((20, 50, 100), 0.12): 1.3274,
    ((60, 120, 240), 0.10): 1.3017,
    ((60, 120, 240), 0.12): 1.3585,
}
QA_BENCH4H = (1.2128, 1.2447)  # full / decisive k>=1380
QA_A1LF_BOOK = 1.3798
QA_BENCH_DAILY = 1.2455


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
    prices_ff = dict(prices)
    prices_ff["BTC"] = btc
    return union_ts, prices, prices_ff


print("loading daily + 4h unions...", flush=True)
d_ts, d_prices, d_prices_ff = load_union(1440)
h_ts, h_prices, h_prices_ff = load_union(240)
nd = len(d_ts) - 1
nh = len(h_ts) - 1
print(f"daily union {nd + 1} bars {d_ts[0]} -> {d_ts[-1]}; 4h union {nh + 1} bars {h_ts[0]} -> {h_ts[-1]}", flush=True)

ret_h = {a: [r if r is not None else 0.0 for r in _asset_returns(h_prices_ff[a])] for a in ASSETS}
ret_d = {a: [r if r is not None else 0.0 for r in _asset_returns(d_prices_ff[a])] for a in ASSETS}

# ---------- B sleeve: record 33's benchmark sleeve on the DAILY calendar (builder recipe verbatim) ----------
print("building B sleeve (daily benchmark w*l3)...", flush=True)
b2 = dynamic_inverse_vol_basket(d_prices, lookback=30)
eq = [1.0]
for r in b2:
    eq.append(eq[-1] * (1 + r))
gate = sma_gate(eq, window=200)
vt = vol_target(b2, target_vol=0.10 / math.sqrt(PPY_D), lookback=30, max_leverage=1.0)
l3 = [gate[k] * vt[k] for k in range(nd)]
w_d = _inverse_vol_weights(d_prices, lookback=30)
B_daily = {a: [w_d[k].get(a, 0.0) * l3[k] for k in range(nd)] for a in ASSETS}

# QA: this recipe's noc must reproduce build_combined_system's benchmark elementwise + Sharpe 1.2455
bench_gross = [l3[k] * b2[k] for k in range(nd)]
noc_B_daily, prev = [], dict.fromkeys(ASSETS, 0.0)
for k in range(nd):
    tk = 0.0
    for a in ASSETS:
        p = B_daily[a][k]
        tk += abs(p - prev[a])
        prev[a] = p
    noc_B_daily.append(bench_gross[k] - tk * FEE)
builder_bench = build_combined_system(d_prices).benchmark_net_of_cost
assert len(builder_bench) == nd, f"builder length {len(builder_bench)} != {nd}"
md = max(abs(noc_B_daily[k] - builder_bench[k]) for k in range(nd))
assert md < 1e-12, f"B sleeve diverges from committed builder: max diff {md}"
s_bench_d = sharpe(noc_B_daily, periods_per_year=PPY_D)
assert abs(s_bench_d - QA_BENCH_DAILY) < 0.005, f"daily bench Sharpe {s_bench_d:.4f} != {QA_BENCH_DAILY}"
print(f"  B QA PASS (elementwise vs builder; Sharpe {s_bench_d:.4f})", flush=True)

# ---------- A1 sleeve: A1-lf weekly v0.12 (trial 34) 7-offset-mean positions on the DAILY calendar ----------
print("building A1 sleeve (A1-lf weekly v0.12 offset-mean)...", flush=True)
cfg_a1 = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
ap_a1 = a1_book_returns(d_prices_ff, d_prices_ff["BTC"], config=cfg_a1)["asset_positions"]
CAD = 7


def block_start(k, o):
    return 0 if k < o else o + CAD * ((k - o) // CAD)


held_by_offset = [{a: [ap_a1[a][block_start(k, o)] for k in range(nd)] for a in ASSETS} for o in range(CAD)]
A1_daily = {a: [statistics.mean(held_by_offset[o][a][k] for o in range(CAD)) for k in range(nd)] for a in ASSETS}

# QA: trial 34's recorded book (mean of the 7 offsets' noc books) reproduces 1.3798
noc_offsets = []
for o in range(CAD):
    held = held_by_offset[o]
    net = [sum(held[a][k] * ret_d[a][k] for a in ASSETS) for k in range(nd)]
    turn = [sum(abs(held[a][k] - (held[a][k - 1] if k > 0 else 0.0)) for a in ASSETS) for k in range(nd)]
    noc_offsets.append([net[k] - turn[k] * FEE for k in range(nd)])
book34 = [statistics.mean(noc_offsets[o][k] for o in range(CAD)) for k in range(nd)]
s_book34 = sharpe(book34, periods_per_year=PPY_D)
assert abs(s_book34 - QA_A1LF_BOOK) < 0.005, f"A1-lf book Sharpe {s_book34:.4f} != {QA_A1LF_BOOK}"
print(f"  A1 QA PASS (trial-34 book Sharpe {s_book34:.4f})", flush=True)

# ---------- A2 sleeve: equal-weight ensemble of trials 37-39 on the 4h calendar ----------
print("building A2 arms (3x a2_book_returns on 4h)...", flush=True)
with open(SP.parent / "a2_4h_cache.pkl", "rb") as f:
    cache74 = pickle.load(f)
assert cache74["n"] == nh, f"4h cache n {cache74['n']} != {nh} (dataset drift?)"
arm_positions = {}
for (lookbacks, tvol), recorded in A2_GRIDS.items():
    cfg = A2Config(
        lookbacks=lookbacks, short="off", target_vol=tvol,
        vol_lookback=180, basket_lookback=180, periods_per_year=PPY_4H,
    )
    out = a2_book_returns(h_prices_ff, config=cfg)
    ap = out["asset_positions"]
    noc, prev = [], dict.fromkeys(ASSETS, 0.0)
    for k in range(nh):
        tk = 0.0
        for a in ASSETS:
            p = ap[a][k]
            tk += abs(p - prev[a])
            prev[a] = p
        noc.append(out["net_returns"][k] - tk * FEE)
    cached = cache74["arms"][str((lookbacks, tvol))]["noc"]
    mdiff = max(abs(noc[k] - cached[k]) for k in range(nh))
    assert mdiff < 1e-12, f"arm {(lookbacks, tvol)} diverges from iter-074 cache: {mdiff}"
    s_arm = sharpe(noc, periods_per_year=PPY_4H)
    assert abs(s_arm - recorded) < 0.005, f"arm {(lookbacks, tvol)} Sharpe {s_arm:.4f} != recorded {recorded}"
    arm_positions[(lookbacks, tvol)] = ap
    print(f"  arm {(lookbacks, tvol)} QA PASS (Sharpe {s_arm:.4f}, elementwise vs cache)", flush=True)
A2_h = {a: [statistics.mean(arm_positions[g][a][k] for g in A2_GRIDS) for k in range(nh)] for a in ASSETS}

# 4h-rebuilt benchmark comparator (iter-074 cache, QA'd there; re-verify figures)
bench4h = cache74["bench_noc"]
s_b4_full = sharpe(bench4h, periods_per_year=PPY_4H)
s_b4_dec = sharpe(bench4h[DECISIVE_4H:], periods_per_year=PPY_4H)
assert abs(s_b4_full - QA_BENCH4H[0]) < 0.005 and abs(s_b4_dec - QA_BENCH4H[1]) < 0.005, \
    f"4h benchmark figures {s_b4_full:.4f}/{s_b4_dec:.4f} != {QA_BENCH4H}"
print(f"  4h benchmark comparator QA PASS ({s_b4_full:.4f}/{s_b4_dec:.4f})", flush=True)

# ---------- expand daily sleeves to the 4h calendar (CLOSE-TIME boundaries) ----------
# Both grids stamp bar STARTS; closes materialize at stamp+interval (verified: daily close stamped D
# == 4h close stamped D 20:00). A close-indexed daily book's position k is decidable only at the
# daily bar-k CLOSE (d_ts[k]+24h) and earns close[k]->close[k+1] — real calendar day k+1. Passing
# raw stamps to expand_daily_positions would apply position k one day EARLY (look-ahead; the wrong
# mapping inflates the B sleeve's 4h Sharpe from ~1.27 to ~1.76 — caught in pre-run review).
# Fix: shift BOTH ts lists to close time so the helper's interval rule operates on decision times.
print("expanding daily sleeves to 4h (close-time boundaries)...", flush=True)
from datetime import timedelta

d_ts_close = [t + timedelta(days=1) for t in d_ts]
h_ts_close = [t + timedelta(hours=4) for t in h_ts]
B_h = expand_daily_positions(B_daily, d_ts_close, h_ts_close)
A1_h = expand_daily_positions(A1_daily, d_ts_close, h_ts_close)
tail_zeroed = sum(1 for k in range(nh) if h_ts_close[k + 1] > d_ts_close[-1])
print(f"  4h tail past last daily close: {tail_zeroed} bars (B/A1 zero there by the helper's tail rule)", flush=True)

# Pre-registered expansion QA (inflation detector): each expanded daily sleeve's 4h noc Sharpe must
# sit near its daily anchor — small drift from intraday compounding/cost timing is expected, a
# +0.5-style jump is the look-ahead signature. Band: anchor - 0.15 <= s_4h <= anchor + 0.10.
for name, pos_h, anchor in (("B", B_h, QA_BENCH_DAILY), ("A1", A1_h, QA_A1LF_BOOK)):
    noc_x, prev = [], dict.fromkeys(ASSETS, 0.0)
    for k in range(nh):
        g, tk = 0.0, 0.0
        for a in ASSETS:
            p = pos_h[a][k]
            g += p * ret_h[a][k]
            tk += abs(p - prev[a])
            prev[a] = p
        noc_x.append(g - tk * FEE)
    s_x = sharpe(noc_x, periods_per_year=PPY_4H)
    assert anchor - 0.15 <= s_x <= anchor + 0.10, f"{name} expanded 4h Sharpe {s_x:.4f} outside [{anchor - 0.15:.3f}, {anchor + 0.10:.3f}] — mapping suspect"
    print(f"  {name} expansion QA PASS (4h noc Sharpe {s_x:.4f} vs daily anchor {anchor})", flush=True)

# ---------- sleeve own net-of-cost series (weight inputs) ----------
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


noc_sleeves = [sleeve_noc(B_h), sleeve_noc(A1_h), sleeve_noc(A2_h)]

# ---------- sleeve weights: trailing 180 bars through k-1; ANY degenerate -> all 1/3 ----------
print("computing sleeve weights...", flush=True)
weights = []
warmup_bars = 0
zero_vol_bars = 0
for k in range(nh):
    if k < WEIGHT_WINDOW:
        weights.append((1 / 3, 1 / 3, 1 / 3))
        warmup_bars += 1
        continue
    vols = [statistics.pstdev(s[k - WEIGHT_WINDOW:k]) for s in noc_sleeves]
    if any(v <= 0.0 for v in vols):
        weights.append((1 / 3, 1 / 3, 1 / 3))
        zero_vol_bars += 1
        continue
    inv = [1 / v for v in vols]
    tot = sum(inv)
    weights.append(tuple(x / tot for x in inv))

# ---------- combined book: weights -> cap -> full costing -> governor at daily cadence ----------
print("combining, capping, costing, governing...", flush=True)
combined = {a: [weights[k][0] * B_h[a][k] + weights[k][1] * A1_h[a][k] + weights[k][2] * A2_h[a][k] for k in range(nh)] for a in ASSETS}
capped = apply_position_caps(combined, long_cap=0.20, short_cap=0.10)
cap_breach_bars = sum(1 for k in range(nh) if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in ASSETS))

noc_comb, prev = [], dict.fromkeys(ASSETS, 0.0)
turn_series = []
for k in range(nh):
    g, tk = 0.0, 0.0
    for a in ASSETS:
        p = capped[a][k]
        g += p * ret_h[a][k]
        tk += abs(p - prev[a])
        prev[a] = p
    turn_series.append(tk)
    noc_comb.append(g - tk * FEE)

# day_index: return bar k spans close-times (h_ts[k]+4h, h_ts[k+1]+4h], whose midnight-bounded
# calendar day is date(h_ts[k+1]) (stamps are bar starts). DENSE RANKS, not true ordinals: the 4h
# union misses 3 calendar days in the 2013 stub (09-12, 09-20, 09-26/27), and record 33's ratified
# daily governor counted PRESENT bars (a missing day is simply absent), so compression is the
# semantics-consistent choice; dense ranks satisfy the helper's contiguity guard by construction.
dates = [h_ts[k + 1].date() for k in range(nh)]
seen: dict = {}
day_index = [seen.setdefault(d, len(seen)) for d in dates]
mult = daily_cadence_governor(noc_comb, day_index)
governed = [mult[k] * noc_comb[k] for k in range(nh)]

# ---------- headline + engagement evidence ----------
s_full = sharpe(governed, periods_per_year=PPY_4H)
s_dec = sharpe(governed[DECISIVE_4H:], periods_per_year=PPY_4H)
mdd = max_dd(governed)
mdd_pre_gov = max_dd(noc_comb)
w_arrays = list(zip(*weights))
w_stats = [
    {"min": min(w_arrays[i]), "max": max(w_arrays[i]), "mean": statistics.mean(w_arrays[i])}
    for i in range(3)
]
gov_engaged = sum(1 for m in mult if m < 1.0)
spot_drag = statistics.mean(turn_series) * FEE * PPY_4H

print("\n=== TRIAL 43 STAGE-1 RESULTS ===", flush=True)
print(f"governed noc Sharpe: {s_full:.4f} full / {s_dec:.4f} decisive (k>={DECISIVE_4H})")
print(f"maxDD: {mdd:.2%} governed / {mdd_pre_gov:.2%} pre-governor; cap-breach bars {cap_breach_bars}; "
      f"governor-engaged bars {gov_engaged}/{nh}; spot drag {spot_drag:.2%}/yr")
print(f"weights (B/A1/A2): " + " | ".join(f"min {s['min']:.3f} max {s['max']:.3f} mean {s['mean']:.3f}" for s in w_stats))
print(f"equal-weight fallback bars: {warmup_bars} warm-up + {zero_vol_bars} zero-vol degenerate")

# engagement QA: all three sleeve weights vary; none pinned at 0/1
for i, s in enumerate(w_stats):
    assert s["max"] - s["min"] > 1e-6, f"sleeve {i} weight never varies"
    assert s["max"] < 1.0 - 1e-9 and s["min"] > 0.0, f"sleeve {i} weight pinned at 0/1"
print("engagement QA PASS", flush=True)

dd_aware = abs(s_full - RECORD33_SHARPE) <= 0.02 and mdd <= RECORD33_MAXDD - 0.015
sharpe_primary_trigger = s_full >= RECORD33_SHARPE
print(f"\nDD-aware branch (|S-{RECORD33_SHARPE}|<=0.02 AND maxDD<={RECORD33_MAXDD - 0.015:.4f}): {dd_aware}")
print(f"Sharpe-primary trigger (S>={RECORD33_SHARPE}): {sharpe_primary_trigger} -> stage-2 kill bar required" if sharpe_primary_trigger and not dd_aware else "", flush=True)

with open(SP / "trial43_cache.pkl", "wb") as f:
    pickle.dump({
        "governed": governed, "noc_comb": noc_comb, "mult": mult, "bench4h": bench4h,
        "weights": weights, "turn_series": turn_series, "nh": nh,
        "years_4h": [h_ts[k + 1].year for k in range(nh)],
        "s_full": s_full, "s_dec": s_dec, "mdd": mdd, "mdd_pre_gov": mdd_pre_gov,
        "cap_breach_bars": cap_breach_bars, "gov_engaged": gov_engaged,
        "warmup_bars": warmup_bars, "zero_vol_bars": zero_vol_bars, "w_stats": w_stats, "spot_drag": spot_drag,
        "dd_aware": dd_aware, "sharpe_primary_trigger": sharpe_primary_trigger,
    }, f)
print("cache written: trial43_cache.pkl", flush=True)
