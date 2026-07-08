import statistics

from cli.validation import (
    cpcv_splits,
    linear_signal,
    probabilistic_sharpe_ratio,
    sharpe,
    sign_strategy_returns,
)

N = 2000


def _strategy_psr(*, beta, seed):
    x, r = linear_signal(N, beta=beta, noise_sd=1.0, seed=seed)
    return probabilistic_sharpe_ratio(sharpe(sign_strategy_returns(x, r)), N)


def test_planted_signal_recovered():
    x, r = linear_signal(N, beta=0.5, noise_sd=1.0, seed=42)
    s = sign_strategy_returns(x, r)
    sr = sharpe(s)
    assert sr > 0.25
    assert probabilistic_sharpe_ratio(sr, N) > 0.99
    path_sharpes = [sharpe([s[i] for i in split["test"]]) for split in cpcv_splits(N, n_groups=10, n_test_groups=2)]
    assert statistics.median(path_sharpes) > 0.1


def test_null_false_positive_rate_is_low():
    # One-sided bound: proves the harness does NOT over-declare significance on noise (expected ~1/20 at the
    # nominal 5% rate; P(>=5 | Binomial(20, 0.05)) ~= 0.003). This is only half the story — a harness that NEVER
    # declared significance would pass it trivially — so it MUST stay paired with test_planted_signal_recovered
    # (which requires PSR > 0.99 on a real signal). Do not remove/skip one without the other.
    flagged = sum(1 for seed in range(20) if _strategy_psr(beta=0.0, seed=seed) > 0.95)
    assert flagged <= 4


def test_signal_beats_null_median():
    # Defense-in-depth: an explicit signal-vs-noise contrast. Logically implied by the two tests above passing
    # (planted PSR > 0.99, and >=16/20 null PSRs <= 0.95 forces the null median <= 0.95 < planted), so it adds no
    # independent falsification power — kept as a self-documenting statement of the suite's core claim.
    planted = _strategy_psr(beta=0.5, seed=42)
    null_median = statistics.median(_strategy_psr(beta=0.0, seed=seed) for seed in range(20))
    assert planted > null_median
