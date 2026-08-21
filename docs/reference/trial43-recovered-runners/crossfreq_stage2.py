"""iter-080 trial 43 stage 2: the ratified kill bar on the cross-frequency combined book.

Sharpe-primary branch (spec 00038): every ratified leg vs the 4h-rebuilt frozen benchmark —
net-of-cost SPA on decisive k>=1380 at convention block 30 AND time-matched block 102, seeds
42/7/1234; benchmark-relative worst-slice (2013/2026 stubs excluded); DSR at the P1 family
count n=3 with var_trials in 4h per-period units (var of the 33 recorded A1 daily per-period
Sharpes / 6, the iter-074 convention); cost stress x1.5 (x2 reported), stressed books
re-governed through the same daily-cadence pipeline.
"""

from __future__ import annotations

import pickle
import statistics
from pathlib import Path

from cli.alpha import a1_kill_bar
from cli.ohlc.dataset import read_parquet
from cli.portfolio.crossfreq import daily_cadence_governor
from cli.registry import TrialRegistry
from cli.validation import reality_check_pvalue, sharpe

SP = Path(__file__).parent
ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
PPY_4H = 2190
DECISIVE = 1380
STUBS = {2013, 2026}

d = pickle.load(open(SP / "trial43_cache.pkl", "rb"))
governed, noc_comb, turn, bench = d["governed"], d["noc_comb"], d["turn_series"], d["bench4h"]
years = d["years_4h"]
nh = d["nh"]

# rebuild the dense-rank day_index (stage 1 didn't cache it)
frames = {a: read_parquet(Path("data/ohlc-full") / a / "EUR" / "240.parquet") for a in ASSETS}
h_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
assert len(h_ts) - 1 == nh
dates = [h_ts[k + 1].date() for k in range(nh)]
seen: dict = {}
day_index = [seen.setdefault(x, len(seen)) for x in dates]

# stressed books: extra cost, re-governed through the same pipeline
def govern(series):
    m = daily_cadence_governor(series, day_index)
    return [m[k] * series[k] for k in range(nh)]


stress15 = govern([noc_comb[k] - turn[k] * 0.003 for k in range(nh)])
stress2x = govern([noc_comb[k] - turn[k] * 0.006 for k in range(nh)])

# var_trials: iter-074 convention — variance of the 33 recorded A1 daily per-period Sharpes / 6
reg = TrialRegistry(Path("docs/research/trial-registry.jsonl"))
pps = [r.metrics["per_period_sharpe"] for r in reg.records if r.family == "A1" and "per_period_sharpe" in r.metrics]
var_trials = statistics.variance(pps) / 6.0
print(f"var_trials {var_trials:.3e} from {len(pps)} A1 daily per-period sharpes / 6", flush=True)


def by_year(series):
    out = {}
    for k in range(nh):
        if years[k] in STUBS:
            continue
        out.setdefault(str(years[k]), []).append(series[k])
    return out


print("running ratified kill bar (block 30, seed 42, 2000 resamples)...", flush=True)
kb = a1_kill_bar(
    governed, bench,
    n_trials=3, var_trials=var_trials, mean_block=30, seed=42,
    cost_stressed_returns=stress15,
    regime_slices=by_year(governed), benchmark_slices=by_year(bench),
    decisive_start=DECISIVE, n_resamples=2000,
)
print(f"kill bar: passes={kb['passes']} dsr={kb['dsr']:.4f}({kb['dsr_pass']}) "
      f"spa={kb['spa_p_value']:.4f}/{kb['spa_p_value_full']:.4f}({kb['spa_pass']}) "
      f"stress15={kb['cost_stress_sharpe']:.4f}({kb['cost_stress_pass']}) "
      f"ws_rel={kb['worst_slice_pass']} {kb['worst_slice_relative'].get('beats_benchmark_worst')}", flush=True)

print("running SPA block/seed grid (decisive window)...", flush=True)
diff = [[governed[k] - bench[k]] for k in range(DECISIVE, nh)]
grid = {}
for block in (30, 102):
    for seed in (42, 7, 1234):
        if block == 30 and seed == 42:
            grid[(block, seed)] = kb["spa_p_value"]
            continue
        out = reality_check_pvalue(diff, mean_block=block, n_resamples=2000, seed=seed)
        grid[(block, seed)] = out["p_value"]
        print(f"  block {block} seed {seed}: p={out['p_value']:.4f}", flush=True)
all_significant = all(p < 0.05 for p in grid.values())

s15 = sharpe(stress15, periods_per_year=PPY_4H)
s2x = sharpe(stress2x, periods_per_year=PPY_4H)
print(f"cost stress (re-governed): x1.5 Sharpe {s15:.4f}, x2 Sharpe {s2x:.4f}", flush=True)

adopt = d["sharpe_primary_trigger"] and kb["passes"] and all_significant
print(f"\n=== STAGE-2 VERDICT INPUTS ===")
print(f"Sharpe {d['s_full']:.4f} >= 1.3263: {d['sharpe_primary_trigger']}; kill bar passes: {kb['passes']}; "
      f"SPA grid all p<0.05: {all_significant}")
print(f"=> {'ADOPT' if adopt else 'REJECT'}", flush=True)

with open(SP / "trial43_stage2.pkl", "wb") as f:
    pickle.dump({
        "kb": kb, "grid": {f"{b}/{s}": p for (b, s), p in grid.items()},
        "stress15_sharpe": s15, "stress2x_sharpe": s2x,
        "var_trials": var_trials, "adopt": adopt,
        "per_period_sharpe_4h": sharpe(governed),
    }, f)
print("cache written: trial43_stage2.pkl", flush=True)
