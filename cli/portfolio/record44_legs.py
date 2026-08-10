"""Re-derivation of registry record 44's benchmark-relative validation legs from committed code.

Record 44 (the deployable system) registered its verdict as ADOPT *vs incumbent trial 43*, whose
construction was never committed — its `run_ref` names scratchpad scripts that no longer exist, so
that comparison cannot be rebuilt (T0125). What CAN be rebuilt is record 44's BENCHMARK-relative
basis: every leg below is recomputed here from `build_crossfreq_system_fast` (record 44 itself)
against the frozen 4h benchmark, through the same committed SPA / DSR / worst-slice primitives the
kill bar uses. This module is the durable replacement for those vanished drivers — re-running it is
the whole point, so it takes no tuning knobs and reads only frozen inputs.

Scope boundary: this covers the benchmark-relative legs. The kill bar's own-series cost-stress leg
(`cost_stress_*`) and the drawdown figures are NOT re-derived here and remain registry-asserted.

Run: `uv run python -m cli.portfolio.record44_legs` (~85 s measured; the benchmark's inverse-vol
weights and the seven SPA bootstraps dominate). The book comes from the fast path, which the
committed full-history equivalence gate holds elementwise-equal to the verified path.

Two conventions spec 00038 left unwritten are pinned here by reproduction rather than by choice —
see `SPA_GRID` and `calendar_year_slices` for which registered figure each is answerable to:

  * The SPA grid's HEADLINE cell is (mean_block 30, seed 42). Its full-window reading is the
    registry's `spa_p_full` and its decisive reading `spa_p_decisive` — which is why no
    `spa_grid_b30_s42` key exists, a gap that otherwise reads as a missing cell. The five
    `spa_grid_*` keys are the DECISIVE readings of the other cells; four of those five match the
    decisive and not the full window, which is what identifies it. (102, 42) reads the same on
    both at 1/2001 granularity and so does not discriminate.
  * The benchmark-relative WORST-SLICE test runs on the governed net over FULL history, with each
    bar's year taken from its CLOSE stamp. On the decisive window the book's worst slice moves
    2022 -> 2014, contradicting record 44's registered note — which is what makes this a recovered
    convention rather than a fitted one.

These live here and NOT in spec 00038 on purpose. Registry records 43 and 44 store
`spec_hash a25d7102…`, which is the sha256 of that spec file — appending to it silently breaks the
pin that verifies the ratified record. A spec named by a registry `spec_hash` is immutable; the
durable home for a recovered convention is committed, runnable code like this module.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from pathlib import Path

# Deliberate cross-package import of a1's private weight helper, for the same reason
# crossfreq_system.py imports it: the frozen benchmark must run the SAME code path the registered
# trial ran, and a reimplementation could silently diverge.
from cli.alpha.a1 import _inverse_vol_weights
from cli.alpha.killbar import benchmark_relative_worst_slice
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.ohlc.dataset import read_parquet
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, build_crossfreq_system_fast
from cli.registry import TrialRegistry
from cli.validation import deflated_sharpe_ratio, reality_check_pvalue, sharpe

_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = _REPO_ROOT / "data" / "ohlc-full"
REGISTRY_PATH = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

PPY_4H = 2190
DECISIVE_START = 1380  # benchmark warm-up analog: 1200 gate + 180 vol bars
N_RESAMPLES = 2000
N_TRIALS_IN_FAMILY = 4
STUB_YEARS = (2013, 2026)  # partial-year slices, excluded from the worst-slice leg

# The frozen 4h benchmark (time-preserving mapping of B3+vt-dynamic onto 4h bars).
BENCH_LOOKBACK = 180  # 30d
BENCH_GATE_WINDOW = 1200  # 200d
BENCH_TARGET_VOL_ANNUAL = 0.10
BENCH_MAX_LEVERAGE = 1.0

# Spec 00038 pre-registers "SPA at blocks 30 AND 102; seeds 42/7/1234" but never says which cell is
# the headline nor which window the grid uses. Recovered by exclusion, not assumed: the registry
# stores five `spa_grid_*` keys and no `spa_grid_b30_s42`, and (30, 42) is the only pair whose two
# windows reproduce `spa_p_full` and `spa_p_decisive` — so it is the headline pair, and the missing
# grid key is missing because that cell IS `spa_p_decisive`. Of the five grid cells, four match the
# decisive window and NOT the full window (measured: b30/s7, b30/s1234, b102/s7, b102/s1234 read
# 0.0025/0.0025/0.0025/0.0040 full vs their registered decisive values); b102/s42 reads identically
# on both windows at the 1/2001 granularity, so it is consistent but non-discriminating.
SPA_HEADLINE_BLOCK = 30
SPA_HEADLINE_SEED = 42
SPA_GRID = ((30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))


def load_union(interval: int, *, root: Path = DATA_ROOT, read=read_parquet) -> tuple[list[datetime], dict[str, list[float | None]]]:
    """Union-calendar bar-START stamps and per-asset closes (None where an asset has no bar).

    `read` is the loader applied to each series path; the default reads the file directly. Passing a
    capturing loader (`ObservedReader.read_series`) is how a run's dataset identity is observed from
    the bytes this function actually opens, rather than claimed alongside it.
    """
    assets = CrossfreqSystemConfig().assets
    frames = {a: read(root / a / "EUR" / f"{interval}.parquet") for a in assets}
    union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
    prices = {}
    for a in assets:
        # Hoisted out of the per-stamp comprehension: building it inside would be quadratic.
        by_ts = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list(), strict=True))
        prices[a] = [by_ts.get(t) for t in union_ts]
    return union_ts, prices


def benchmark_4h_net_of_cost(h4_prices: dict[str, list[float | None]], *, cost_per_side: float) -> list[float]:
    """The frozen 4h benchmark's per-bar net-of-cost return series (registered Sharpe 1.2128 full).

    Time-preserving mapping: dynamic inverse-vol basket at lookback 180 -> SMA gate 1200 on the
    basket's own equity -> vol target 0.10/sqrt(2190) at lookback 180 -> inverse-vol weights at 180,
    charged per-asset turnover.
    """
    assets = CrossfreqSystemConfig().assets
    n = len(next(iter(h4_prices.values()))) - 1
    basket = dynamic_inverse_vol_basket(h4_prices, lookback=BENCH_LOOKBACK)
    equity = [1.0]
    for r in basket:
        equity.append(equity[-1] * (1 + r))
    gate = sma_gate(equity, window=BENCH_GATE_WINDOW)
    vt = vol_target(
        basket,
        target_vol=BENCH_TARGET_VOL_ANNUAL / math.sqrt(PPY_4H),
        lookback=BENCH_LOOKBACK,
        max_leverage=BENCH_MAX_LEVERAGE,
    )
    l3 = [gate[k] * vt[k] for k in range(n)]
    weights = _inverse_vol_weights(h4_prices, lookback=BENCH_LOOKBACK)
    positions = {a: [weights[k].get(a, 0.0) * l3[k] for k in range(n)] for a in assets}

    net: list[float] = []
    prev = dict.fromkeys(assets, 0.0)
    for k in range(n):
        turnover = 0.0
        for a in assets:
            p = positions[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        net.append(l3[k] * basket[k] - turnover * cost_per_side)
    return net


def a1_family_var_trials_4h(*, registry_path: Path = REGISTRY_PATH) -> float:
    """`var_trials` in 4h per-period Sharpe^2 units, the iter-074 convention record 44 registered:
    the sample variance of the recorded A1-family DAILY per-period Sharpes, divided by 6 (per-period
    Sharpe scales 1/sqrt(6) from daily to 4h). Read-only use of the append-only registry.

    Bounded to record 44's own predecessors: the registry grows, and a later A1 append carrying
    `per_period_sharpe` would silently change this derivation — surfacing as "the re-derivation
    broke" rather than "the input set moved". The 33 contributing records are frozen by that bound.
    """
    daily_sharpes = [
        r.metrics["per_period_sharpe"]
        for r in TrialRegistry(registry_path).records
        if r.trial_id < 44 and r.family == "A1" and "per_period_sharpe" in r.metrics
    ]
    return statistics.variance(daily_sharpes) / 6


def calendar_year_slices(returns: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
    """Per-period returns grouped by calendar year, stub years dropped. Return bar k is attributed
    to the year of its CLOSE, `h4_ts[k + 1]` — the end-of-move stamping the daily trials used.

    Spec 00038 says only "benchmark-relative worst-slice, stubs excluded"; it never pins the series
    or the window. Recovered by reproduction: the GOVERNED net over the FULL history, sliced this
    way, is what reproduces record 44's registered notes (book worst 2022 -0.0290, benchmark worst
    2014 -0.0797, book smaller drawdown in 6 of 12 compared years).
    """
    out: dict[str, list[float]] = {}
    for k, r in enumerate(returns):
        year = h4_ts[k + 1].year
        if year in STUB_YEARS:
            continue
        out.setdefault(str(year), []).append(r)
    return out


def rederive_record44_legs(
    daily_ts: list[datetime],
    daily_prices: dict[str, list[float | None]],
    h4_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
    *,
    var_trials: float,
) -> dict:
    """Every re-derivable leg of record 44's benchmark-relative basis, keyed by its registry name.

    `worst_slice_relative` carries the full diagnostic (worst slices, DD counts) because the
    registered `worst_slice_relative_pass: 1` is a bare flag — the numbers that make it checkable
    live only in record 44's free-text notes.
    """
    config = CrossfreqSystemConfig()
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    book = result.governed_net
    bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=config.cost_per_side)
    if len(book) != len(bench):
        raise ValueError(f"book/benchmark length mismatch: {len(book)} vs {len(bench)}")

    outperformance = [[b - m] for b, m in zip(book, bench, strict=True)]

    def spa(block: float, seed: int, *, decisive: bool) -> float:
        matrix = outperformance[DECISIVE_START:] if decisive else outperformance
        return reality_check_pvalue(matrix, mean_block=block, n_resamples=N_RESAMPLES, seed=seed)["p_value"]

    per_period = sharpe(book)
    legs = {
        "ann_sharpe_noc": sharpe(book, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(book[DECISIVE_START:], periods_per_year=PPY_4H),
        "bench4h_sharpe_full": sharpe(bench, periods_per_year=PPY_4H),
        "bench4h_sharpe_decisive": sharpe(bench[DECISIVE_START:], periods_per_year=PPY_4H),
        "cap_breach_bars": result.cap_breach_bars,
        "governor_engaged_bars": result.governor_engaged_bars,
        "per_period_sharpe_4h": per_period,
        "var_trials_4h": var_trials,
        "dsr": deflated_sharpe_ratio(per_period, len(book), N_TRIALS_IN_FAMILY, var_trials),
        "spa_p_full": spa(SPA_HEADLINE_BLOCK, SPA_HEADLINE_SEED, decisive=False),
        "spa_p_decisive": spa(SPA_HEADLINE_BLOCK, SPA_HEADLINE_SEED, decisive=True),
    }
    for block, seed in SPA_GRID:
        legs[f"spa_grid_b{block}_s{seed}"] = spa(block, seed, decisive=True)

    relative = benchmark_relative_worst_slice(calendar_year_slices(book, h4_ts), calendar_year_slices(bench, h4_ts))
    legs["worst_slice_relative_pass"] = int(relative["beats_benchmark_worst"])
    legs["worst_slice_relative"] = {k: v for k, v in relative.items() if k != "per_slice"}
    return legs


def main() -> None:
    registered = {r.trial_id: r.metrics for r in TrialRegistry(REGISTRY_PATH).records}[44]
    daily_ts, daily_prices = load_union(1440)
    h4_ts, h4_prices = load_union(240)
    print(f"union bars: daily {len(daily_ts)}  4h {len(h4_ts)}")
    legs = rederive_record44_legs(daily_ts, daily_prices, h4_ts, h4_prices, var_trials=a1_family_var_trials_4h())
    relative = legs.pop("worst_slice_relative")
    width = max(len(k) for k in legs)
    print(f"{'leg':<{width}}  {'re-derived':<24}  {'registered':<24}  verdict")
    for key, value in legs.items():
        want = registered.get(key)
        if want is None:
            verdict = "(not registered)"
        elif isinstance(value, int) and isinstance(want, (int, float)):
            verdict = "MATCH" if value == want else "MISMATCH"
        else:
            # Same rounding check the test asserts on, so the printed verdict cannot disagree with it.
            verdict = "MATCH" if value == want else ("~match (4dp)" if round(value, 4) == want else "MISMATCH")
        print(f"{key:<{width}}  {value!r:<24}  {want!r:<24}  {verdict}")
    print(f"\nworst-slice diagnostic: {relative}")


if __name__ == "__main__":
    main()
