"""Re-derivation of registry record 44's benchmark-relative validation legs from committed code — no tuning knobs and only
frozen inputs, because re-running it is the whole point. This basis, not record 44's registered ADOPT vs incumbent
trial 43, is what the go/no-go gate rests on (T0125, resolved, records the ruling). The conventions spec 00038 left
unwritten are pinned below and never appended to it — its sha256 is the `spec_hash` that verifies records 43 and 44."""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from pathlib import Path

# Deliberate cross-package import of a1's private weight helper: the frozen benchmark must run the SAME code path the
# registered trial ran, and a reimplementation could silently diverge.
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

# Spec 00038 pre-registers "SPA at blocks 30 AND 102; seeds 42/7/1234" but names neither the headline cell nor the grid's
# window. Recovered by exclusion, not assumed: the registry stores five `spa_grid_*` keys and no `spa_grid_b30_s42`, and
# (30, 42) is the only pair whose two windows reproduce `spa_p_full` and `spa_p_decisive` — so (30, 42) is the headline
# pair; the grid keys below are the DECISIVE-window readings, which `tests/test_record44_legs.py` pins.
SPA_HEADLINE_BLOCK = 30
SPA_HEADLINE_SEED = 42
SPA_GRID = ((30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))


def load_union(interval: int, *, root: Path = DATA_ROOT, read=read_parquet) -> tuple[list[datetime], dict[str, list[float | None]]]:
    """Union-calendar bar-START stamps and per-asset closes (None where an asset has no bar); a capturing `read` (an
    adapter over `ObservedReader.read_series`) is how a run's dataset identity is observed from the bytes this function
    actually opens, rather than claimed alongside it."""
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
    """The frozen 4h benchmark's per-bar net-of-cost return series."""
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
    """`var_trials` in 4h per-period Sharpe^2 units — the sample variance of the recorded A1-family DAILY per-period
    Sharpes divided by 6, the iter-074 convention record 44 registered (per-period Sharpe scales 1/sqrt(6) from daily to
    4h). Bounded to record 44's own predecessors because the registry is append-only: a later A1 append carrying
    `per_period_sharpe` would silently move this derivation."""
    daily_sharpes = [
        r.metrics["per_period_sharpe"]
        for r in TrialRegistry(registry_path).records
        if r.trial_id < 44 and r.family == "A1" and "per_period_sharpe" in r.metrics
    ]
    return statistics.variance(daily_sharpes) / 6


def calendar_year_slices(returns: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
    """Per-period returns grouped by calendar year, stub years dropped, each bar attributed to the year of its CLOSE,
    `h4_ts[k + 1]` — the end-of-move stamping the daily trials used. Spec 00038 pins neither series nor window for the
    worst-slice leg; the GOVERNED net over the FULL history, sliced this way, is what reproduces record 44's registered
    worst-slice notes."""
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
    """Every re-derivable leg of record 44's benchmark-relative basis, keyed by its registry name — the own-series
    `cost_stress_*` and `maxdd*` legs are not among them; `worst_slice_relative` carries the full diagnostic because the
    registered `worst_slice_relative_pass: 1` is a bare flag whose numbers live only in record 44's free-text notes."""
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
