from __future__ import annotations

import math

from cli.alpha.errors import AlphaError
from cli.validation import ValidationError, deflated_sharpe_ratio, max_drawdown, reality_check_pvalue, sharpe

# 0.5 = faithful operationalization of the pre-registered "DSR > 0" (deflated point estimate positive);
# the stricter López-de-Prado 0.95 significance bar is the alternative the human can ratify at Phase-5 —
# SPA-beats-benchmark carries the significance-vs-benchmark burden separately.
DSR_PASS_THRESHOLD = 0.5


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
) -> dict:
    """The Phase-4 kill bar (docs/research/00.master-plan.md sec12; docs/specs/00031): a variant is
    archived unless ALL hold: its DSR clears DSR_PASS_THRESHOLD at its trial count, SPA says it beats
    the benchmark, it survives 1.5x cost stress, and its worst walk-forward regime slice is not
    disqualifying.

    DSR leg: `deflated_sharpe_ratio` here returns a PROBABILITY P(true SR > deflated benchmark), so the
    leg is `dsr > 0.5`. 0.5 = faithful operationalization of the pre-registered "DSR > 0" (deflated point
    estimate positive); the stricter López-de-Prado 0.95 significance bar is the alternative the human can
    ratify at Phase-5 — SPA-beats-benchmark carries the significance-vs-benchmark burden separately.

    Units contract: `sr = sharpe(book_net_returns)` is PER-PERIOD (PSR's formula is per-observation with
    n_obs = len(returns)), so `var_trials` MUST be in per-period Sharpe² units (at iter-046 = the variance
    of the 16 variants' per-period Sharpes) — NOT annualized. A per-period trial-Sharpe stdev > 1 is
    nonsensical, so `var_trials > 1.0` is rejected (a likely annualized-vs-per-period units mix-up).

    Two judgment calls made here (see docs/plans/00031 "Design decisions ... flagged for review"):
    "survives cost stress" = the cost-stressed series' own Sharpe is still > 0; "worst slice not
    disqualifying" = every regime_slices entry's Sharpe is > 0. Task 6 (real-data run) may want to
    recalibrate the worst-slice bar against the frozen benchmark's own worst-slice Sharpe instead.
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

    try:
        n_obs = len(book_net_returns)
        sr = sharpe(book_net_returns)
        dsr = deflated_sharpe_ratio(sr, n_obs, n_trials, var_trials)
        # dsr is a probability P(true SR > deflated benchmark); dsr > 0.5 <=> deflated point estimate positive.
        dsr_pass = dsr > DSR_PASS_THRESHOLD

        outperformance = [[b - m] for b, m in zip(book_net_returns, benchmark_net_returns)]
        spa = reality_check_pvalue(outperformance, mean_block=mean_block, seed=seed)
        spa_pass = spa["p_value"] < 0.05

        cost_stress_sharpe = sharpe(cost_stressed_returns)
        cost_stress_pass = cost_stress_sharpe > 0

        slice_sharpes = {name: sharpe(rets) for name, rets in regime_slices.items()}
    except ValidationError as exc:
        raise AlphaError(f"kill-bar computation failed: {exc}") from exc

    worst_slice_name = min(slice_sharpes, key=slice_sharpes.get)
    worst_slice_sharpe = slice_sharpes[worst_slice_name]
    worst_slice_pass = worst_slice_sharpe > 0

    passes = dsr_pass and spa_pass and cost_stress_pass and worst_slice_pass
    return {
        "dsr": dsr,
        "dsr_pass": dsr_pass,
        "spa_p_value": spa["p_value"],
        "spa_pass": spa_pass,
        "cost_stress_sharpe": cost_stress_sharpe,
        "cost_stress_pass": cost_stress_pass,
        "worst_slice_name": worst_slice_name,
        "worst_slice_sharpe": worst_slice_sharpe,
        "worst_slice_pass": worst_slice_pass,
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
