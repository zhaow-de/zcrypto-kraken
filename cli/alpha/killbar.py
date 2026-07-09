from __future__ import annotations

import math

from cli.alpha.errors import AlphaError
from cli.validation import ValidationError, deflated_sharpe_ratio, max_drawdown, reality_check_pvalue, sharpe

# Ratified 2026-07-09 (T0009, decisions log [iter-072]): the stricter López-de-Prado 0.95 significance
# bar (not just a positive deflated point estimate) -- SPA-beats-benchmark carries the
# significance-vs-benchmark burden separately.
DSR_PASS_THRESHOLD = 0.95


def a1_kill_bar(
    book_net_returns: list[float],
    benchmark_net_returns: list[float],
    *,
    n_trials: int,
    var_trials: float,
    mean_block: float,
    seed: int,
    cost_stressed_returns: list[float],
    regime_slices: dict[str, list[float]],
    benchmark_slices: dict[str, list[float]],
    decisive_start: int = 0,
    n_resamples: int = 1000,
) -> dict:
    """The Phase-4 kill bar (docs/research/00.master-plan.md sec12; docs/specs/00031), folded to the
    T0009-ratified protocol (2026-07-09, decisions log [iter-072]): a variant is archived unless ALL hold:
    its DSR clears DSR_PASS_THRESHOLD at its trial count, SPA says it beats the benchmark on the decisive
    window, it survives 1.5x cost stress, and its worst regime slice does not underperform the
    benchmark's own worst slice.

    DSR leg: `deflated_sharpe_ratio` here returns a PROBABILITY P(true SR > deflated benchmark), so the
    leg is `dsr > DSR_PASS_THRESHOLD`. Ratified 2026-07-09 (T0009): the bar is the stricter
    López-de-Prado significance threshold, `dsr > 0.95` — not just the pre-ratification 0.5 "deflated
    point estimate positive" bar. SPA-beats-benchmark carries the significance-vs-benchmark burden
    separately.

    SPA leg (ratified 2026-07-09, T0009): the caller passes NET-OF-COST series for both
    `book_net_returns` and `benchmark_net_returns` (each already charged its own turnover + carry — the
    same contract as `net_of_cost_verdict`). The leg is evaluated on the decisive window
    `[decisive_start:]` — `spa_p_value`/`spa_pass` are the decisive-window figures; the full-window
    p-value is also computed and returned as `spa_p_value_full` for reporting. `decisive_start` is the
    benchmark's post-warm-up cut (230 for B3+vt-dynamic). `n_resamples` feeds both windows' bootstrap;
    its default (1000) matches every registry row recorded before the fold-in, while the pre-registered
    trial protocol ([iter-059]) passes 2000 explicitly.

    Units contract: `sr = sharpe(book_net_returns)` is PER-PERIOD (PSR's formula is per-observation with
    n_obs = len(returns)), so `var_trials` MUST be in per-period Sharpe² units (at iter-046 = the variance
    of the 16 variants' per-period Sharpes) — NOT annualized. A per-period trial-Sharpe stdev > 1 is
    nonsensical, so `var_trials > 1.0` is rejected (a likely annualized-vs-per-period units mix-up).

    "survives cost stress" = the cost-stressed series' own Sharpe is still > 0 (own-series, full window;
    a judgment call from the original design, see docs/plans/00031 "Design decisions ... flagged for
    review" — unchanged by T0009). Worst-slice leg (ratified 2026-07-09, T0009): the other original
    judgment call — "worst slice not disqualifying" = every regime_slices entry's Sharpe > 0 — is
    superseded by the benchmark-relative
    `benchmark_relative_worst_slice(regime_slices, benchmark_slices)["beats_benchmark_worst"]`; the
    caller excludes stub/partial-year slices from BOTH `regime_slices` and `benchmark_slices` before
    calling. The book's own worst non-degenerate slice (`worst_slice_name`, `worst_slice_sharpe`) and the
    full relative diagnostic (minus its verbose `per_slice` detail, as `worst_slice_relative`) stay in the
    result for the record, but no longer drive `worst_slice_pass`.

    Worst-slice leg robustness (iter-046, `.tmp/decisions.md`): a regime slice that is zero-variance or
    shorter than 2 periods (e.g. a calendar-year slice sitting entirely inside the 200-day gate warm-up,
    or a bear year a long/flat book correctly sat out) means the book took NO risk that regime — there is
    no risk-adjusted performance to judge and Sharpe is undefined, so the slice is skipped when recording
    the book's own worst-slice fields. If every slice is degenerate this way, `worst_slice_name`/
    `worst_slice_sharpe` fall back to the `<no-nondegenerate-slice>`/nan sentinel, and `worst_slice_pass`
    is False (there is nothing evaluable for the relative diagnostic to compare either, since its
    per-slice skip rule also triggers whenever the book side is degenerate).
    """
    if len(book_net_returns) != len(benchmark_net_returns):
        raise AlphaError("book_net_returns and benchmark_net_returns must have the same length")
    if not isinstance(regime_slices, dict) or not regime_slices:
        raise AlphaError("regime_slices must be a non-empty dict of regime -> return slice")
    if var_trials > 1.0:
        raise AlphaError(
            f"var_trials={var_trials} is implausible for per-period Sharpe² units (implies trial-Sharpe stdev > 1); "
            "the DSR leg is per-period, so pass var_trials in per-period Sharpe² units, not annualized "
            "(see the units contract in a1_kill_bar's docstring)"
        )
    if not isinstance(decisive_start, int):
        raise AlphaError(f"decisive_start must be an int, got {decisive_start!r}")
    if decisive_start < 0 or decisive_start >= len(book_net_returns):
        raise AlphaError(f"decisive_start={decisive_start} must be >= 0 and < len(book_net_returns)={len(book_net_returns)}")
    if not isinstance(n_resamples, int) or n_resamples < 1:
        raise AlphaError(f"n_resamples must be an int >= 1, got {n_resamples!r}")

    try:
        n_obs = len(book_net_returns)
        sr = sharpe(book_net_returns)
        dsr = deflated_sharpe_ratio(sr, n_obs, n_trials, var_trials)
        # dsr is a probability P(true SR > deflated benchmark); ratified bar is dsr > DSR_PASS_THRESHOLD (0.95).
        dsr_pass = dsr > DSR_PASS_THRESHOLD

        outperformance_full = [[b - m] for b, m in zip(book_net_returns, benchmark_net_returns)]
        spa_p_value_full = reality_check_pvalue(outperformance_full, mean_block=mean_block, n_resamples=n_resamples, seed=seed)[
            "p_value"
        ]

        outperformance_decisive = [
            [b - m] for b, m in zip(book_net_returns[decisive_start:], benchmark_net_returns[decisive_start:])
        ]
        spa_p_value = reality_check_pvalue(outperformance_decisive, mean_block=mean_block, n_resamples=n_resamples, seed=seed)[
            "p_value"
        ]
        spa_pass = spa_p_value < 0.05

        cost_stress_sharpe = sharpe(cost_stressed_returns)
        cost_stress_pass = cost_stress_sharpe > 0

        # Skip degenerate slices (no risk taken that regime): too short to have variance, or flat.
        slice_sharpes = {name: sharpe(rets) for name, rets in regime_slices.items() if len(rets) >= 2 and min(rets) != max(rets)}
    except ValidationError as exc:
        raise AlphaError(f"kill-bar computation failed: {exc}") from exc

    if slice_sharpes:
        worst_slice_name = min(slice_sharpes, key=slice_sharpes.get)
        worst_slice_sharpe = slice_sharpes[worst_slice_name]
        relative = benchmark_relative_worst_slice(regime_slices, benchmark_slices)
        worst_slice_pass = relative["beats_benchmark_worst"]
        worst_slice_relative = {k: v for k, v in relative.items() if k != "per_slice"}
    else:
        # Every provided regime_slices entry was degenerate (no risk taken anywhere): not evaluable, so it
        # cannot pass -- and benchmark_relative_worst_slice would have nothing to compare either (its
        # per-slice skip rule also triggers whenever the book side is degenerate), so it is not called.
        worst_slice_name = "<no-nondegenerate-slice>"
        worst_slice_sharpe = math.nan
        worst_slice_pass = False
        worst_slice_relative = {"beats_benchmark_worst": False, "n_compared": 0, "skipped": list(regime_slices)}

    passes = dsr_pass and spa_pass and cost_stress_pass and worst_slice_pass
    return {
        "dsr": dsr,
        "dsr_pass": dsr_pass,
        "spa_p_value": spa_p_value,
        "spa_p_value_full": spa_p_value_full,
        "spa_pass": spa_pass,
        "cost_stress_sharpe": cost_stress_sharpe,
        "cost_stress_pass": cost_stress_pass,
        "worst_slice_name": worst_slice_name,
        "worst_slice_sharpe": worst_slice_sharpe,
        "worst_slice_pass": worst_slice_pass,
        "worst_slice_relative": worst_slice_relative,
        "passes": passes,
    }


def short_leg_whipsaw(short_only_returns: list[float]) -> dict:
    """Isolated whipsaw diagnostic for the short leg (finding-2's whipsaw kill test, docs/specs/00031):
    `short_only_returns` is the short leg's own per-period P&L contribution (0.0 when not engaged that
    period, its realized short return when engaged). turnover = fraction of period-to-period
    engagement flips (0 <-> nonzero); hit_rate = fraction of ENGAGED periods with a positive return;
    max_drawdown reuses the validation harness on the short-only series."""
    if not isinstance(short_only_returns, list) or len(short_only_returns) < 2:
        raise AlphaError(f"short_only_returns must be a list of >= 2 values, got {short_only_returns!r}")
    for r in short_only_returns:
        if not isinstance(r, (int, float)) or not math.isfinite(r):
            raise AlphaError(f"short_only_returns must be finite numbers, got {r!r}")

    engaged = [r != 0.0 for r in short_only_returns]
    flips = sum(1 for t in range(1, len(engaged)) if engaged[t] != engaged[t - 1])
    turnover = flips / (len(engaged) - 1)
    active = [r for r in short_only_returns if r != 0.0]
    hit_rate = (sum(1 for r in active if r > 0) / len(active)) if active else 0.0
    try:
        mdd = max_drawdown(short_only_returns)
    except ValidationError as exc:
        raise AlphaError(f"short_leg_whipsaw computation failed: {exc}") from exc
    return {"turnover": turnover, "hit_rate": hit_rate, "max_drawdown": mdd}


def net_of_cost_verdict(
    book_net_of_cost: list[float],
    benchmark_net_of_cost: list[float],
    *,
    mean_block: float,
    seed: int,
    n_resamples: int = 2000,
) -> dict:
    """Net-of-cost head-to-head verdict: the SPA check the pre-registered `a1_kill_bar`'s SPA leg omits.

    A1's investigation found that `a1_kill_bar`'s SPA leg ran on the zero-fee `book_net_returns`/
    `benchmark_net_returns` the caller happened to pass in, over-crediting a high-turnover family that
    actually loses net-of-cost. The net-of-cost contract was folded into `a1_kill_bar`'s SPA leg per
    T0009 (decisions log [iter-072], 2026-07-09); this standalone tool remains for drivers/diagnostics.
    Both `book_net_of_cost` and `benchmark_net_of_cost` must already be
    charged their own realistic cost by the caller (the book's turnover plus any short margin carry; the
    benchmark's own turnover) before being passed in here.

    Builds the T x 1 outperformance matrix (book minus benchmark per period) and runs
    `reality_check_pvalue` on it -- the same SPA machinery `a1_kill_bar`'s SPA leg uses -- so `beats` is
    `spa_p_value < 0.05`. Sharpe figures are per-period (no annualization), consistent with
    `a1_kill_bar`.
    """
    if len(book_net_of_cost) != len(benchmark_net_of_cost):
        raise AlphaError("book_net_of_cost and benchmark_net_of_cost must have the same length")
    if len(book_net_of_cost) < 2:
        raise AlphaError(f"book_net_of_cost/benchmark_net_of_cost must have >= 2 values, got {len(book_net_of_cost)}")
    for r in (*book_net_of_cost, *benchmark_net_of_cost):
        if not isinstance(r, (int, float)) or not math.isfinite(r):
            raise AlphaError(f"book_net_of_cost/benchmark_net_of_cost must be finite numbers, got {r!r}")

    try:
        outperformance = [[b - m] for b, m in zip(book_net_of_cost, benchmark_net_of_cost)]
        spa = reality_check_pvalue(outperformance, mean_block=mean_block, n_resamples=n_resamples, seed=seed)
        book_sharpe = sharpe(book_net_of_cost)
        benchmark_sharpe = sharpe(benchmark_net_of_cost)
    except ValidationError as exc:
        raise AlphaError(f"net_of_cost_verdict computation failed: {exc}") from exc

    spa_p_value = spa["p_value"]
    mean_outperformance = sum(row[0] for row in outperformance) / len(outperformance)
    return {
        "spa_p_value": spa_p_value,
        "beats": spa_p_value < 0.05,
        "book_sharpe": book_sharpe,
        "benchmark_sharpe": benchmark_sharpe,
        "mean_outperformance": mean_outperformance,
    }


def _total_return(returns: list[float]) -> float:
    cumulative = 1.0
    for r in returns:
        cumulative *= 1 + r
    return cumulative - 1


def benchmark_relative_worst_slice(
    book_slices: dict[str, list[float]],
    benchmark_slices: dict[str, list[float]],
) -> dict:
    """Benchmark-relative, exposure-aware alternative to `a1_kill_bar`'s worst-slice leg.

    The pre-registered worst-slice leg is absolute ("every non-degenerate slice's Sharpe > 0") and
    exposure-blind. On real data (iter-053, docs/research/09.phase4-a2-results.md) the frozen benchmark
    fails that very leg: its 2014 per-period Sharpe is -0.108 (ann. -2.07) even though its gate kept it
    ~87% flat, so it lost only -5.5% with a 6.0% drawdown -- while a fully-exposed challenger with a
    BETTER Sharpe (ann. -1.80) actually lost -8.4% with an 8.4% drawdown. A Sharpe-only slice test
    punishes prudent non-participation and hides P&L. This diagnostic reports Sharpe AND total return
    AND max drawdown, per slice, book vs. benchmark, so that contradiction is visible.

    This check was folded into `a1_kill_bar`'s worst-slice leg per T0009 (decisions log [iter-072],
    2026-07-09); the standalone tool remains for drivers/diagnostics.

    `book_slices` and `benchmark_slices` are keyed by the same slice labels (e.g. calendar years), each
    mapping to that slice's per-period return series. A slice is degenerate (Sharpe undefined) using the
    same rule `a1_kill_bar` applies: len(rets) < 2 or min(rets) == max(rets). A slice is skipped -- the
    book-vs-benchmark comparison is undefined -- if EITHER side is degenerate.
    """
    if not book_slices or not benchmark_slices:
        raise AlphaError("book_slices and benchmark_slices must both be non-empty dicts")
    if set(book_slices) != set(benchmark_slices):
        raise AlphaError("book_slices and benchmark_slices must have identical key sets")
    for label, book_rets in book_slices.items():
        benchmark_rets = benchmark_slices[label]
        if not isinstance(book_rets, list) or not isinstance(benchmark_rets, list):
            raise AlphaError(f"slice {label!r} must map to a list of returns on both sides")
        if len(book_rets) != len(benchmark_rets):
            raise AlphaError(f"slice {label!r} has mismatched book/benchmark lengths")
        for r in (*book_rets, *benchmark_rets):
            if not isinstance(r, (int, float)) or not math.isfinite(r):
                raise AlphaError(f"slice {label!r} must contain only finite numbers, got {r!r}")

    def _degenerate(rets: list[float]) -> bool:
        return len(rets) < 2 or min(rets) == max(rets)

    per_slice = {}
    skipped = []
    try:
        for label, book_rets in book_slices.items():
            benchmark_rets = benchmark_slices[label]
            if _degenerate(book_rets) or _degenerate(benchmark_rets):
                skipped.append(label)
                continue
            book_sharpe = sharpe(book_rets)
            benchmark_sharpe = sharpe(benchmark_rets)
            per_slice[label] = {
                "book_sharpe": book_sharpe,
                "benchmark_sharpe": benchmark_sharpe,
                "sharpe_delta": book_sharpe - benchmark_sharpe,
                "book_total_return": _total_return(book_rets),
                "benchmark_total_return": _total_return(benchmark_rets),
                "book_max_drawdown": max_drawdown(book_rets),
                "benchmark_max_drawdown": max_drawdown(benchmark_rets),
            }
    except ValidationError as exc:
        raise AlphaError(f"benchmark_relative_worst_slice computation failed: {exc}") from exc

    if not per_slice:
        raise AlphaError("no non-degenerate slice to compare (every slice was degenerate on some side)")

    worst_book_slice = min(per_slice, key=lambda label: per_slice[label]["book_sharpe"])
    worst_benchmark_slice = min(per_slice, key=lambda label: per_slice[label]["benchmark_sharpe"])
    worst_book_sharpe = per_slice[worst_book_slice]["book_sharpe"]
    worst_benchmark_sharpe = per_slice[worst_benchmark_slice]["benchmark_sharpe"]

    return {
        "per_slice": per_slice,
        "skipped": skipped,
        "worst_book_slice": worst_book_slice,
        "worst_book_sharpe": worst_book_sharpe,
        "worst_benchmark_slice": worst_benchmark_slice,
        "worst_benchmark_sharpe": worst_benchmark_sharpe,
        "worst_slice_sharpe_delta": worst_book_sharpe - worst_benchmark_sharpe,
        "beats_benchmark_worst": worst_book_sharpe >= worst_benchmark_sharpe,
        "n_slices_book_better_sharpe": sum(1 for s in per_slice.values() if s["book_sharpe"] > s["benchmark_sharpe"]),
        "n_slices_book_smaller_drawdown": sum(
            1 for s in per_slice.values() if s["book_max_drawdown"] < s["benchmark_max_drawdown"]
        ),
        "n_compared": len(per_slice),
    }
