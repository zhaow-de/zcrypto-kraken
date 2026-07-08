import pytest

from cli.validation import ValidationError, outperformance_matrix, reality_check_pvalue


def test_reality_check_reproducible():
    m = outperformance_matrix(200, 4, edge=0.0, seed=1)
    a = reality_check_pvalue(m, mean_block=5, n_resamples=100, seed=9)
    b = reality_check_pvalue(m, mean_block=5, n_resamples=100, seed=9)
    assert a == b


def test_reality_check_shape_and_best():
    # column 2 dominates deterministically
    m = [[0.0, 0.0, 5.0, 0.0] for _ in range(50)]
    r = reality_check_pvalue(m, mean_block=4, n_resamples=100, seed=1)
    assert r["best_strategy"] == 2
    assert r["statistic"] == pytest.approx(5.0)
    assert 0.0 < r["p_value"] <= 1.0
    assert r["n_resamples"] == 100


@pytest.mark.parametrize(
    "matrix",
    [
        [[1.0, 2.0]],  # T < 2
        [[], []],  # K < 1
        [[1.0, 2.0], [3.0]],  # non-rectangular
        [[1.0, 2.0], [float("nan"), 3.0]],  # non-finite
    ],
)
def test_reality_check_guards(matrix):
    with pytest.raises(ValidationError):
        reality_check_pvalue(matrix, mean_block=2, n_resamples=50, seed=1)
