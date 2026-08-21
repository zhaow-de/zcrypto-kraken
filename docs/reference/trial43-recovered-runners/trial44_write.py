"""iter-081: registry append for trial 44 — the fixed-weight P1 combination (ADOPT)."""

import hashlib
import pickle
from pathlib import Path

from cli.alpha import benchmark_relative_worst_slice
from cli.ohlc.dataset import read_parquet
from cli.registry import TrialRegistry

SP = Path(__file__).parent
ASSETS = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
STUBS = {2013, 2026}

s = pickle.load(open(SP / "trial44_cache.pkl", "rb"))
assert s["adopt"] is True and s["kb"]["passes"] is True

def manifest(interval):
    parts = []
    for a in ASSETS:
        f = read_parquet(Path("data/ohlc-full") / a / "EUR" / f"{interval}.parquet")
        parts.append(f"{a}:{len(f)}:{f['ts'][0]}:{f['ts'][-1]}:{f['close'][0]}:{f['close'][-1]}")
    return "|".join(sorted(parts))

m_daily, m_4h = manifest(1440), manifest(240)
dataset_hash = hashlib.sha256((m_daily + "||" + m_4h).encode()).hexdigest()
spec_hash = hashlib.sha256(Path("docs/specs/00038-cross-frequency-combination-design.md").read_bytes()).hexdigest()

reg = TrialRegistry(Path("docs/research/trial-registry.jsonl"))
assert hashlib.sha256(m_daily.encode()).hexdigest() == reg.records[0].dataset_hash, "daily canonical drifted -- STOP"
assert len(reg.records) == 43 and reg.records[-1].trial_id == 43
assert dataset_hash == reg.records[-1].dataset_hash, "dataset hash differs from trial 43 -- STOP"

years, nh = s["years"], s["nh"]

def by_year(series):
    out = {}
    for k in range(nh):
        if years[k] in STUBS:
            continue
        out.setdefault(str(years[k]), []).append(series[k])
    return out

ws = benchmark_relative_worst_slice(by_year(s["governed"]), by_year(s["bench4h"]))
ws_note = (f"worst-slice relative: beats_benchmark_worst={ws['beats_benchmark_worst']}, book worst "
           f"{ws['worst_book_slice']}={ws['worst_book_sharpe']:.4f} vs bench worst {ws['worst_benchmark_slice']}="
           f"{ws['worst_benchmark_sharpe']:.4f}, book smaller DD {ws['n_slices_book_smaller_drawdown']}/{ws['n_compared']}.")

kb = s["kb"]
metrics = {
    "ann_sharpe_noc": round(s["s_full"], 4), "ann_sharpe_noc_decisive": round(s["s_dec"], 4),
    "maxdd": round(s["mdd"], 4), "maxdd_pre_governor": round(s["mdd_pre"], 4),
    "per_period_sharpe_4h": s["per_period_sharpe_4h"],
    "dsr": round(kb["dsr"], 5), "dsr_pass": int(kb["dsr_pass"]),
    "spa_p_decisive": kb["spa_p_value"], "spa_p_full": kb["spa_p_value_full"], "spa_pass": int(kb["spa_pass"]),
    "spa_grid_b30_s7": s["grid"]["30/7"], "spa_grid_b30_s1234": s["grid"]["30/1234"],
    "spa_grid_b102_s42": s["grid"]["102/42"], "spa_grid_b102_s7": s["grid"]["102/7"],
    "spa_grid_b102_s1234": s["grid"]["102/1234"],
    "cost_stress_1_5x_sharpe_ann": round(s["stress15"], 4), "cost_stress_2x_sharpe_ann": round(s["stress2x"], 4),
    "cost_stress_pass": int(kb["cost_stress_pass"]), "worst_slice_relative_pass": int(kb["worst_slice_pass"]),
    "cap_breach_bars": s["cap_breach"], "governor_engaged_bars": s["gov_engaged"],
    "spot_drag_pct_yr": round(s["spot_drag"], 4),
    "incumbent_trial43_sharpe": 1.5366, "incumbent_trial43_maxdd": 0.1331,
    "bench4h_sharpe_full": 1.2128, "bench4h_sharpe_decisive": 1.2447,
    "criterion_dd_aware": int(s["dd_aware"]), "criterion_sharpe_primary": int(s["primary"]),
    "var_trials_4h": s["var_trials"], "decisive_start": 1380, "n_resamples": 2000, "passes": int(kb["passes"]),
}

rec = reg.append(
    iteration="iter-081", family="P1",
    variant="P1-crossfreq-fixedthird-B3vtdyn+A1lfw012+A2ens4h-cap-govD",
    spec_hash=spec_hash, dataset_hash=dataset_hash, seeds=[42, 7, 1234],
    metrics=metrics, n_trials_in_family=4, verdict="adopt",
    run_ref="iter-081 trial43/trial44_run.py + trial44_write.py (scratchpad)",
    notes=(
        "ADOPT under the pre-registered [iter-073]/[iter-081] rule vs incumbent trial 43: Sharpe-primary 1.5609 >= 1.5366 "
        "with every ratified leg passing (SPA grid max p 0.0060 over blocks 30/102 x seeds 42/7/1234; DSR ~1.0 at n=4; "
        "benchmark-relative worst-slice pass; stress x1.5/x2 re-governed 1.3029/1.2106 — x2 slightly below trial 43's "
        "1.2400, disclosed). Construction = trial 43 with sleeve weights FIXED at 1/3 (T0019's simplification; the "
        "adaptive-weighting mechanism removed); same spec 00038 construction otherwise — spec_hash pins the same amended "
        "spec as trial 43; weights-rule delta pre-registered in the decisions log [iter-081]. HONESTY: the headline Sharpe "
        "was NOT blind — 1.5609 was first seen as trial 43's verification counterfactual (iter-080 stage1b); this trial's "
        "new information is the ratified legs + registration. QA: all five sleeve anchors reproduced; the SAME driver "
        "reproduces trial 43's governed series bit-identically (cross-check) before the weight change. maxDD 13.57% vs "
        "trial 43's 13.31% (pre-governor 18.66% vs 19.46%); drag 3.15%/yr vs 3.40%. " + ws_note +
        " TRIAL 44 SUPERSEDES TRIAL 43 as the deployable-system candidate — simpler to build/journal/reconcile in the "
        "Phase-6 engine (no adaptive-weight state); engine scope tracked in T0018."
    ),
)
print(f"appended trial {rec.trial_id} family={rec.family} n={rec.n_trials_in_family} verdict={rec.verdict}")
reg2 = TrialRegistry(Path("docs/research/trial-registry.jsonl"))
print(f"reload: {len(reg2.records)} records, chain intact")
print(ws_note)
