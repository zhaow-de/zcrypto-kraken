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
    # Nominal rate 5%: >= 5 of 20 null seeds flagged has P ~= 0.003 under Binomial(20, 0.05).
    flagged = sum(1 for seed in range(20) if _strategy_psr(beta=0.0, seed=seed) > 0.95)
    assert flagged <= 4


def test_signal_beats_null_median():
    planted = _strategy_psr(beta=0.5, seed=42)
    null_median = statistics.median(_strategy_psr(beta=0.0, seed=seed) for seed in range(20))
    assert planted > null_median
