import pytest

from cli.benchmark.strategies import BenchmarkError, dynamic_inverse_vol_basket, inverse_vol_basket


def test_dynamic_basket_known_answer_two_assets_entry():
    # B enters (first non-None price) at union-index E=2, so its first return is retB[2]; it only
    # qualifies once its trailing window retB[t-2:t] is fully non-None, i.e. from t = E+lookback = 4.
    a = [100, 102, 99.96, 109.956, 112.15512, 109.9120176]  # retA = [.02,-.02,.10,.02,-.02]
    b = [None, None, 100, 118, 110.92, 116.466]  # retB = [None,None,.18,-.06,.05]
    out = dynamic_inverse_vol_basket({"A": a, "B": b}, lookback=2)

    assert len(out) == len(a) - 1
    assert out[0] == 0.0 and out[1] == 0.0  # t < lookback -> warm-up
    # t=2: only A qualifies (B's window [retB0,retB1] = [None,None]) -> portfolio = retA[2].
    assert out[2] == pytest.approx(0.10)
    # t=3: only A qualifies (B's window [retB1,retB2] = [None, .18]) -> portfolio = retA[3].
    assert out[3] == pytest.approx(0.02)
    # t=4: both qualify. A's window [.10,.02] has stdev s; B's window [.18,-.06] has stdev 3s
    # (by construction) -> weights 0.75/0.25 -> portfolio = .75*(-.02) + .25*(.05) = -.0025.
    assert out[4] == pytest.approx(-0.0025)


def test_dynamic_basket_entry_warmup():
    # B enters (first non-None price) at union-index E=3; before it accrues a full
    # `lookback` of clean returns it contributes zero weight, so the combined basket
    # equals the A-only basket. It joins from t = E + lookback = 5 onward.
    a = [100, 101, 102, 103, 104, 105, 106, 107]
    b = [None, None, None, 100, 102, 99.96, 109.956, 105]
    lookback = 2
    out = dynamic_inverse_vol_basket({"A": a, "B": b}, lookback=lookback)
    a_only = dynamic_inverse_vol_basket({"A": a}, lookback=lookback)

    e = 3
    for t in range(e + lookback):
        assert out[t] == a_only[t]  # B not yet qualifying -> contributes nothing
    assert out[e + lookback] != a_only[e + lookback]  # B has joined -> basket changes


def test_dynamic_basket_gap_disqualifies_until_reaccrual():
    # C has a single mid-series gap (price None at index 5); D is always present and
    # always qualifying. The gap makes ret_C[4] and ret_C[5] None, which disqualifies C
    # for t in {4,5,6,7} (its own return or its trailing window touches the gap); C
    # re-qualifies once the window clears the gap, at t = gap_index + lookback + 1 = 8.
    c = [100, 101, 102, 103, 104, None, 105, 106, 107, 108, 109, 110]
    d = [100, 99, 101, 98, 102, 97, 103, 96, 104, 95, 105, 94]
    lookback = 2
    combined = dynamic_inverse_vol_basket({"C": c, "D": d}, lookback=lookback)
    d_only = dynamic_inverse_vol_basket({"D": d}, lookback=lookback)

    for t in (4, 5, 6, 7):
        assert combined[t] == d_only[t]  # C disqualified by the gap -> D alone drives it
    assert combined[8] != d_only[8]  # C has re-accrued a clean window -> rejoins


def test_dynamic_basket_renormalization_sums_to_one():
    # Three assets qualify at t=2 with DIFFERENT trailing vols (real, unequal weights)
    # but an IDENTICAL realized return r=0.05 at t=2. portfolio[2] == r if and only if
    # the qualifying weights are renormalized to sum to 1 (an un-normalized raw-1/stdev
    # implementation would not land exactly on r).
    x = [100, 102, 99.96, 104.958]  # retX = [.02, -.02, .05]  (window stdev s)
    z = [100, 103, 97.85, 102.7425]  # retZ = [.03, -.05, .05]  (window stdev 2s)
    y = [100, 106, 99.64, 104.622]  # retY = [.06, -.06, .05]  (window stdev 3s)
    out = dynamic_inverse_vol_basket({"X": x, "Y": y, "Z": z}, lookback=2)
    assert abs(out[2] - 0.05) < 1e-12


def test_dynamic_basket_all_absent_or_warmup_is_zero():
    a = [None, None, 100, 101, 102, 103]
    b = [None, None, 100, 99, 101, 100]
    out = dynamic_inverse_vol_basket({"A": a, "B": b}, lookback=2)
    assert out[0] == 0.0  # both fully absent -> no returns at all
    assert out[1] == 0.0  # still absent -> no returns
    assert out[2] == 0.0  # both entered at index 2, but warm-up (need E+lookback=4)
    assert out[3] == 0.0  # still warm-up


def test_dynamic_basket_no_look_ahead():
    # Strictly causal: period t's weights must use only returns strictly BEFORE t.
    # (1) Future-leak direction: two series identical through union-index 6, differing
    #     from index 7 on -> output[:6] (whose windows and applied returns never reach
    #     the differing tail) must be bit-identical.
    common_a = [100, 101, 102, 103, 104, 105, 106]
    common_b = [100, 99, 101, 100, 102, 101, 103]
    a1, a2 = common_a + [107, 108, 109], common_a + [500, 2, 777]
    b1, b2 = common_b + [104, 105, 106], common_b + [3, 900, 12]
    out1 = dynamic_inverse_vol_basket({"A": a1, "B": b1}, lookback=2)
    out2 = dynamic_inverse_vol_basket({"A": a2, "B": b2}, lookback=2)
    assert out1[:6] == out2[:6]

    # (2) Self-referential direction: the trailing window must be the OLDEST `lookback` returns
    #     strictly before t, not shifted to admit ret_i[t] itself. Perturbing the OLDEST price in
    #     period t=2's window (lookback=2 -> window is returns[0:2], driven by prices[0]) must
    #     change output[2]; a shift to returns[t-lookback+1:t+1] would leave output[2] unchanged.
    a3 = [100, 101, 102, 101, 103, 104]
    b3 = [100, 99, 101, 100, 102, 101]
    base = dynamic_inverse_vol_basket({"A": a3, "B": b3}, lookback=2)
    a3_perturbed = a3.copy()
    a3_perturbed[0] = 60.0  # only affects returns_A[0], inside period 2's legitimate window
    perturbed = dynamic_inverse_vol_basket({"A": a3_perturbed, "B": b3}, lookback=2)
    assert base[2] != perturbed[2]


def test_dynamic_basket_reduces_to_fixed():
    a = [100, 101, 102, 103, 104, 105, 106, 107]
    b = [100, 99, 101, 100, 102, 101, 103, 102]
    lookback = 3
    dyn = dynamic_inverse_vol_basket({"A": a, "B": b}, lookback=lookback)
    fixed = inverse_vol_basket({"A": a, "B": b}, lookback=lookback)
    assert dyn == fixed


@pytest.mark.parametrize("lookback", [1, 1.5, True, "2"])
def test_dynamic_basket_guards_lookback(lookback):
    with pytest.raises(BenchmarkError):
        dynamic_inverse_vol_basket({"A": [100.0, 101.0, 102.0]}, lookback=lookback)


def test_dynamic_basket_guards_empty_dict():
    with pytest.raises(BenchmarkError):
        dynamic_inverse_vol_basket({}, lookback=2)


def test_dynamic_basket_guards_unequal_lengths():
    with pytest.raises(BenchmarkError):
        dynamic_inverse_vol_basket({"A": [100.0, 101.0, 102.0], "B": [100.0, 101.0]}, lookback=2)


@pytest.mark.parametrize(
    "prices",
    [
        [100.0, float("nan"), 102.0],
        [100.0, -5.0, 102.0],
        [100.0, 0.0, 102.0],
        "not a list",
    ],
)
def test_dynamic_basket_guards_bad_elements(prices):
    with pytest.raises(BenchmarkError):
        dynamic_inverse_vol_basket({"A": prices}, lookback=2)
