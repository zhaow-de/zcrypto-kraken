from cli.validation import outperformance_matrix, reality_check_pvalue

T, K, N_RESAMPLES, MB = 300, 5, 200, 5


def test_spa_detects_a_superior_strategy():
    m = outperformance_matrix(T, K, edge=0.3, seed=1)
    r = reality_check_pvalue(m, mean_block=MB, n_resamples=N_RESAMPLES, seed=2)
    assert r["best_strategy"] == 0
    assert r["p_value"] < 0.05


def test_spa_null_false_positive_rate_is_low():
    flagged = 0
    for seed in range(20):
        m = outperformance_matrix(T, K, edge=0.0, seed=seed)
        if reality_check_pvalue(m, mean_block=MB, n_resamples=N_RESAMPLES, seed=seed + 100)["p_value"] < 0.05:
            flagged += 1
    assert flagged <= 4
