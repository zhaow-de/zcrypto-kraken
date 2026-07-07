import math

import pytest

from cli.validation import ValidationError, cpcv_splits, make_groups, n_backtest_paths


def _blocks(sorted_positions):
    """Contiguous runs [a, b] (inclusive) in an ascending list of ints."""
    blocks, start, prev = [], None, None
    for p in sorted_positions:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            blocks.append((start, prev))
            start = prev = p
    if start is not None:
        blocks.append((start, prev))
    return blocks


@pytest.mark.parametrize("n,g", [(10, 10), (23, 5), (100, 7), (12, 4)])
def test_make_groups_tiles_exactly(n, g):
    groups = make_groups(n, g)
    assert len(groups) == g
    assert groups[0][0] == 0 and groups[-1][1] == n
    for (s0, e0), (s1, e1) in zip(groups, groups[1:]):
        assert e0 == s1  # contiguous, no gaps/overlaps
    sizes = [e - s for s, e in groups]
    assert max(sizes) - min(sizes) <= 1
    assert sum(sizes) == n


@pytest.mark.parametrize("n,g", [(1, 2), (3, 5)])
def test_make_groups_guard(n, g):
    with pytest.raises(ValidationError):
        make_groups(n, g)


def test_make_groups_guard_too_few_groups():
    with pytest.raises(ValidationError):
        make_groups(100, 1)


@pytest.mark.parametrize("N,k,expected", [(6, 2, 5), (10, 2, 9), (10, 3, 36), (5, 1, 1)])
def test_n_backtest_paths(N, k, expected):
    assert n_backtest_paths(N, k) == expected


@pytest.mark.parametrize("N,k", [(10, 0), (10, 10), (1, 1)])
def test_n_backtest_paths_guard(N, k):
    with pytest.raises(ValidationError):
        n_backtest_paths(N, k)


def test_cpcv_split_count_and_test_groups():
    splits = cpcv_splits(100, n_groups=10, n_test_groups=2)
    assert len(splits) == math.comb(10, 2)
    from itertools import combinations

    assert [s["test_groups"] for s in splits] == list(combinations(range(10), 2))


def test_cpcv_disjoint_sorted_and_test_matches_groups():
    n, N = 100, 10
    groups = make_groups(n, N)
    for s in cpcv_splits(n, n_groups=N, n_test_groups=2):
        assert set(s["train"]).isdisjoint(s["test"])
        assert s["train"] == sorted(s["train"])
        assert s["test"] == sorted(s["test"])
        expected_test = sorted(p for gi in s["test_groups"] for p in range(*groups[gi]))
        assert s["test"] == expected_test


def test_cpcv_coverage_no_purge():
    n, N, k = 60, 6, 2
    splits = cpcv_splits(n, n_groups=N, n_test_groups=k)
    counts = [0] * n
    for s in splits:
        assert sorted(s["train"] + s["test"]) == list(range(n))  # train ∪ test = all
        for p in s["test"]:
            counts[p] += 1
    assert set(counts) == {math.comb(N - 1, k - 1)}  # each position tested C(N-1,k-1) times


def test_cpcv_purge_removes_forward_leak():
    n, N, H = 100, 10, 3
    for s in cpcv_splits(n, n_groups=N, n_test_groups=2, label_horizon=H):
        train = set(s["train"])
        for a, _b in _blocks(s["test"]):
            assert not (set(range(max(0, a - H), a)) & train)  # nothing in [a-H, a)


def test_cpcv_embargo_removes_after_test():
    n, N, E = 100, 10, 4
    for s in cpcv_splits(n, n_groups=N, n_test_groups=2, embargo=E):
        train = set(s["train"])
        for _a, b in _blocks(s["test"]):
            assert not (set(range(b + 1, min(n, b + 1 + E))) & train)  # nothing in (b, b+E]


def test_cpcv_non_adjacent_test_groups_two_blocks():
    # groups {0,2} of 10 over 100 samples -> two disjoint test blocks
    s = next(s for s in cpcv_splits(100, n_groups=10, n_test_groups=2) if s["test_groups"] == (0, 2))
    assert len(_blocks(s["test"])) == 2
    # adjacent groups {0,1} -> one merged block
    s2 = next(s for s in cpcv_splits(100, n_groups=10, n_test_groups=2) if s["test_groups"] == (0, 1))
    assert len(_blocks(s2["test"])) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_groups": 1},
        {"n_test_groups": 0},
        {"n_test_groups": 10},
        {"label_horizon": -1},
        {"embargo": -1},
    ],
)
def test_cpcv_guards(kwargs):
    with pytest.raises(ValidationError):
        cpcv_splits(100, **kwargs)


def test_cpcv_guard_samples_below_groups():
    with pytest.raises(ValidationError):
        cpcv_splits(5, n_groups=10)
