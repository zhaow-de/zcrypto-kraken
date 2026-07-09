import pytest

from cli.alpha import AlphaError, a1_kill_bar, short_leg_whipsaw
from cli.validation import linear_signal, sign_strategy_returns

N = 500
# Per-period Sharpe² units, consistent with a1_kill_bar's per-period sr (see its units-contract docstring).
# At this scale a genuine planted edge (sr ~= 0.78) clears the deflated benchmark (~= 0.057) so dsr -> ~1.0,
# while a beta=0 null's noise Sharpe (SE ~= 1/sqrt(N)) falls below it on the majority of seeds -> dsr < 0.5.
VAR_TRIALS_PER_PERIOD = 1e-3


def _book_and_benchmark(*, beta, seed):
    x, r = linear_signal(N, beta=beta, noise_sd=1.0, seed=seed)
    book = sign_strategy_returns(x, r)
    benchmark = [0.0] * N  # flat benchmark -> the book's outperformance is just its own return
    return book, benchmark


def _slices(book):
    return {"first_half": book[: N // 2], "second_half": book[N // 2 :]}


def test_a1_kill_bar_planted_edge_passes():
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=VAR_TRIALS_PER_PERIOD,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices=_slices(book),
    )
    # dsr is a probability; a real edge must clear 0.5 (deflated point estimate positive), not just > 0
    # (which the pre-fix gate accepted for a ~5e-43 underflow — see test_a1_kill_bar_null_rarely_passes).
    assert result["dsr"] > 0.5
    assert result["dsr_pass"] is True
    assert result["spa_pass"] is True
    assert result["spa_p_value"] < 0.05
    assert result["cost_stress_pass"] is True
    assert result["worst_slice_pass"] is True
    assert result["passes"] is True


def test_a1_kill_bar_null_rarely_passes():
    # Mirrors tests/test_acceptance.py's null-false-positive-rate style: over 20 seeds, a beta=0 (no
    # real edge) book should almost never clear all four kill-bar conditions simultaneously.
    #
    # This test also proves the DSR leg is a real gate, not the inert no-op it was before the fix. With
    # the pre-fix `dsr > 0` gate on these beta=0 nulls the DSR leg passed 20/20 (deflated_sharpe_ratio is
    # a probability that only underflows to ~5e-43, never <= 0), so only SPA/cost/slice discriminated.
    # With the fixed `dsr > 0.5` gate and per-period var_trials, the observed per-leg null pass tally is
    # dsr=4/20, spa=3/20, cost=8/20, slice=6/20, overall passes=3/20 — DSR now fails the majority of nulls.
    passed = 0
    dsr_leg_passed = 0
    for seed in range(20):
        book, benchmark = _book_and_benchmark(beta=0.0, seed=seed)
        result = a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=VAR_TRIALS_PER_PERIOD,
            mean_block=5,
            seed=seed + 100,
            cost_stressed_returns=book,
            regime_slices=_slices(book),
        )
        if result["passes"]:
            passed += 1
        if result["dsr_pass"]:
            dsr_leg_passed += 1
    assert passed <= 4
    # DSR now contributes discrimination: a beta=0 null clears dsr > 0.5 on only a minority of seeds
    # (vs 20/20 under the broken gate), so the leg is no longer inert.
    assert dsr_leg_passed <= 8


def test_a1_kill_bar_cost_stress_can_fail_alone():
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    stressed = [r - 1.0 for r in book]  # a heavy flat cost drag that flips the stressed series negative
    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=1.0,
        mean_block=5,
        seed=7,
        cost_stressed_returns=stressed,
        regime_slices=_slices(book),
    )
    assert result["cost_stress_pass"] is False
    assert result["passes"] is False  # cost stress alone fails the all-must-hold bar


def test_a1_kill_bar_worst_slice_can_fail_alone():
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    bad_slice = [-0.01 + 0.002 * ((i % 3) - 1) for i in range(50)]  # non-degenerate, clearly negative
    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=1.0,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices={"good": book, "bad_regime": bad_slice},
    )
    assert result["worst_slice_name"] == "bad_regime"
    assert result["worst_slice_pass"] is False
    assert result["passes"] is False


def test_a1_kill_bar_skips_flat_regime_slice():
    # A flat slice (e.g. a calendar year entirely inside gate warm-up, or a bear year a long/flat book
    # correctly sat out) has zero variance -- sharpe() is undefined there, so it must be skipped rather
    # than raising or being treated as the worst (or best) slice.
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    bad_slice = [-0.01 + 0.002 * ((i % 3) - 1) for i in range(50)]  # non-degenerate, clearly negative
    flat_zero = [0.0] * 50
    flat_const = [0.01] * 50

    def _run(regime_slices):
        return a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=1.0,
            mean_block=5,
            seed=7,
            cost_stressed_returns=book,
            regime_slices=regime_slices,
        )

    with_flat = _run({"good": book, "bad_regime": bad_slice, "flat_zero": flat_zero, "flat_const": flat_const})
    without_flat = _run({"good": book, "bad_regime": bad_slice})

    assert with_flat["worst_slice_name"] == "bad_regime"
    assert with_flat["worst_slice_pass"] is False
    assert with_flat["passes"] is False
    # Regression guard: the flat slices must not change the worst-slice result at all.
    assert with_flat["worst_slice_name"] == without_flat["worst_slice_name"]
    assert with_flat["worst_slice_sharpe"] == pytest.approx(without_flat["worst_slice_sharpe"])
    assert with_flat["worst_slice_pass"] == without_flat["worst_slice_pass"]


def test_a1_kill_bar_all_slices_degenerate():
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=1.0,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices={"flat_zero": [0.0] * 50, "too_short": [0.01], "flat_const": [0.01] * 30},
    )
    assert result["worst_slice_name"] == "<no-nondegenerate-slice>"
    assert result["worst_slice_pass"] is False
    assert result["passes"] is False


def test_a1_kill_bar_guards_length_mismatch():
    with pytest.raises(AlphaError):
        a1_kill_bar(
            [0.01, 0.02],
            [0.01],
            n_trials=16,
            var_trials=1.0,
            mean_block=5,
            seed=1,
            cost_stressed_returns=[0.01, 0.02],
            regime_slices={"x": [0.01, 0.02]},
        )


def test_a1_kill_bar_guards_empty_regime_slices():
    with pytest.raises(AlphaError):
        a1_kill_bar(
            [0.01, 0.02, 0.03],
            [0.0, 0.0, 0.0],
            n_trials=16,
            var_trials=1.0,
            mean_block=5,
            seed=1,
            cost_stressed_returns=[0.01, 0.02, 0.03],
            regime_slices={},
        )


def test_short_leg_whipsaw_known_answer():
    short_only = [0.0, 0.02, -0.01, 0.0, 0.03, -0.02, 0.0, 0.01, 0.0]
    # engaged = [F,T,T,F,T,T,F,T,F] -> 6 flips / 8 transitions = 0.75 turnover.
    # active returns = [0.02,-0.01,0.03,-0.02,0.01] -> 3/5 positive = 0.6 hit-rate.
    # equity: 1 -> 1.02 -> 1.0098 -> 1.0098 -> 1.040094 -> 1.01929212(=peak*0.98, dd=0.02 exactly) -> ...
    result = short_leg_whipsaw(short_only)
    assert result["turnover"] == pytest.approx(0.75)
    assert result["hit_rate"] == pytest.approx(0.6)
    assert result["max_drawdown"] == pytest.approx(0.02)


def test_short_leg_whipsaw_never_engaged():
    result = short_leg_whipsaw([0.0, 0.0, 0.0, 0.0])
    assert result["turnover"] == 0.0
    assert result["hit_rate"] == 0.0


@pytest.mark.parametrize("returns", [[0.01], [], [0.01, float("nan")], "not a list"])
def test_short_leg_whipsaw_guards(returns):
    with pytest.raises(AlphaError):
        short_leg_whipsaw(returns)
