import pytest

from cli.alpha import AlphaError, a1_kill_bar, benchmark_relative_worst_slice, net_of_cost_verdict, short_leg_whipsaw
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


def test_net_of_cost_verdict_beats():
    # A real edge (beta=1.2) vs a weaker, noise-only benchmark (beta=0.0) -- both series still have
    # variance (sign_strategy_returns on noise is non-constant) so book_sharpe/benchmark_sharpe are
    # both well-defined, unlike a flat-zero benchmark which would make sharpe() undefined.
    x_book, r_book = linear_signal(N, beta=1.2, noise_sd=1.0, seed=42)
    book = sign_strategy_returns(x_book, r_book)
    x_bench, r_bench = linear_signal(N, beta=0.0, noise_sd=1.0, seed=99)
    benchmark = sign_strategy_returns(x_bench, r_bench)

    result = net_of_cost_verdict(book, benchmark, mean_block=5, seed=7)
    assert result["beats"] is True
    assert result["spa_p_value"] < 0.05
    assert result["mean_outperformance"] > 0


def test_net_of_cost_verdict_no_edge():
    # book == benchmark exactly -> outperformance is identically 0 every period, no edge to detect.
    x, r = linear_signal(N, beta=1.2, noise_sd=1.0, seed=42)
    book = sign_strategy_returns(x, r)

    result = net_of_cost_verdict(book, book, mean_block=5, seed=7)
    assert result["beats"] is False
    assert result["mean_outperformance"] == pytest.approx(0.0)


def test_net_of_cost_verdict_zero_fee_winner_loses_net_of_cost():
    # The A1 scenario this helper exists for: a book that beats the benchmark gross (small planted
    # edge) but a1_kill_bar's SPA leg runs on zero-fee returns, over-crediting a high-turnover family
    # that actually loses net-of-cost once a realistic per-period cost is charged. Here book_gross =
    # benchmark + edge, book_net = book_gross - heavy_cost, with heavy_cost > edge so book_net trails
    # the benchmark by a constant (edge - cost) every period.
    x, r = linear_signal(N, beta=0.8, noise_sd=1.0, seed=11)
    benchmark = sign_strategy_returns(x, r)
    edge = 0.002  # book's gross per-period edge over the benchmark, before cost
    cost = 0.01  # heavy per-period cost that swamps the edge
    book_gross = [b + edge for b in benchmark]
    book_net = [g - cost for g in book_gross]  # == benchmark + (edge - cost), a constant net-of-cost drag

    result = net_of_cost_verdict(book_net, benchmark, mean_block=5, seed=7)
    assert result["beats"] is False
    assert result["mean_outperformance"] < 0
    assert result["mean_outperformance"] == pytest.approx(edge - cost)


@pytest.mark.parametrize(
    "book, benchmark",
    [
        ([0.01, 0.02], [0.01]),  # length mismatch
        ([], []),  # empty
        ([0.01], [0.02]),  # single-element (< 2)
        ([0.01, float("nan")], [0.01, 0.02]),  # non-finite
    ],
)
def test_net_of_cost_verdict_guards(book, benchmark):
    with pytest.raises(AlphaError):
        net_of_cost_verdict(book, benchmark, mean_block=5, seed=1)


def test_benchmark_relative_worst_slice_known_answer():
    # Three hand-built slices; sharpe/total_return/max_drawdown hand-computed for both sides.
    book_slices = {
        "2012": [0.01, 0.02, -0.01],
        "2013": [-0.02, -0.01],
        "2014": [0.03, 0.01, 0.02, -0.01],
    }
    benchmark_slices = {
        "2012": [0.004, 0.006, 0.005],
        "2013": [-0.03, -0.005],
        "2014": [0.0, 0.01, -0.005, 0.01],
    }

    result = benchmark_relative_worst_slice(book_slices, benchmark_slices)

    assert result["skipped"] == []
    assert result["n_compared"] == 3

    per = result["per_slice"]
    assert per["2012"]["book_sharpe"] == pytest.approx(0.4364357804719848)
    assert per["2012"]["benchmark_sharpe"] == pytest.approx(5.0)
    assert per["2012"]["sharpe_delta"] == pytest.approx(0.4364357804719848 - 5.0)
    assert per["2012"]["book_total_return"] == pytest.approx(0.01989799999999997)
    assert per["2012"]["benchmark_total_return"] == pytest.approx(0.015074119999999969)
    assert per["2012"]["book_max_drawdown"] == pytest.approx(0.010000000000000009)
    assert per["2012"]["benchmark_max_drawdown"] == pytest.approx(0.0)

    assert per["2013"]["book_sharpe"] == pytest.approx(-2.1213203435596424)
    assert per["2013"]["benchmark_sharpe"] == pytest.approx(-0.9899494936611665)
    assert per["2013"]["book_total_return"] == pytest.approx(-0.02980000000000005)
    assert per["2013"]["benchmark_total_return"] == pytest.approx(-0.03485000000000005)
    assert per["2013"]["book_max_drawdown"] == pytest.approx(0.02980000000000005)
    assert per["2013"]["benchmark_max_drawdown"] == pytest.approx(0.03485000000000005)

    assert per["2014"]["book_sharpe"] == pytest.approx(0.7319250547114)
    assert per["2014"]["benchmark_sharpe"] == pytest.approx(0.5)
    assert per["2014"]["book_total_return"] == pytest.approx(0.0504949400000001)
    assert per["2014"]["benchmark_total_return"] == pytest.approx(0.014999500000000054)
    assert per["2014"]["book_max_drawdown"] == pytest.approx(0.010000000000000009)
    assert per["2014"]["benchmark_max_drawdown"] == pytest.approx(0.0050000000000000044)

    # Worst book slice is 2013 (-2.121); worst benchmark slice is also 2013 (-0.990).
    assert result["worst_book_slice"] == "2013"
    assert result["worst_book_sharpe"] == pytest.approx(-2.1213203435596424)
    assert result["worst_benchmark_slice"] == "2013"
    assert result["worst_benchmark_sharpe"] == pytest.approx(-0.9899494936611665)
    assert result["worst_slice_sharpe_delta"] == pytest.approx(-2.1213203435596424 - (-0.9899494936611665))
    assert result["beats_benchmark_worst"] is False  # book's worst (-2.121) is worse than benchmark's worst (-0.990)

    # Only 2014 has book_sharpe > benchmark_sharpe; only 2013 has book_max_drawdown < benchmark_max_drawdown.
    assert result["n_slices_book_better_sharpe"] == 1
    assert result["n_slices_book_smaller_drawdown"] == 1


def test_benchmark_relative_worst_slice_exposure_blindness():
    # Documents the real iter-053 2014 case (docs/research/09.phase4-a2-results.md): the frozen
    # benchmark's gate held it ~87% flat, so its near-flat slice has a clearly negative per-period
    # Sharpe (small mean, small stdev, both negative) yet only a small total loss and small drawdown.
    # A fully-exposed challenger has a LESS negative Sharpe (bigger stdev shrinks the ratio's magnitude)
    # while its larger swings compound into a BIGGER total loss and BIGGER drawdown -- the exact
    # contradiction a Sharpe-only worst-slice leg hides.
    near_flat_benchmark = [0.0] * 16 + [-0.004, 0.001, -0.004, 0.001]
    fully_exposed_book = [0.05, -0.052] * 10

    result = benchmark_relative_worst_slice(
        {"2014": fully_exposed_book},
        {"2014": near_flat_benchmark},
    )

    per = result["per_slice"]["2014"]
    assert per["book_sharpe"] == pytest.approx(-0.019111361460409683)
    assert per["benchmark_sharpe"] == pytest.approx(-0.23044650151849083)
    assert per["book_total_return"] == pytest.approx(-0.045059386810466395)
    assert per["benchmark_total_return"] == pytest.approx(-0.005998975984000232)
    assert per["book_max_drawdown"] == pytest.approx(0.09053274934330136)
    assert per["benchmark_max_drawdown"] == pytest.approx(0.006991984000000118)

    # The book looks better on the ratio (less negative Sharpe) ...
    assert per["book_sharpe"] > per["benchmark_sharpe"]
    # ... while it actually lost more, and drew down more, than the benchmark.
    assert per["book_total_return"] < per["benchmark_total_return"]
    assert per["book_max_drawdown"] > per["benchmark_max_drawdown"]

    assert result["beats_benchmark_worst"] is True
    assert result["n_slices_book_smaller_drawdown"] == 0


def test_benchmark_relative_worst_slice_skips_degenerate_either_side():
    book_slices = {
        "bench_degenerate": [0.01, 0.02, 0.03],  # benchmark side is constant -> degenerate
        "book_degenerate": [0.01, 0.01],  # book side is constant -> degenerate
        "normal": [0.02, 0.03, -0.01],
    }
    benchmark_slices = {
        "bench_degenerate": [0.0, 0.0, 0.0],
        "book_degenerate": [0.01, 0.02],
        "normal": [0.01, 0.01, 0.02],
    }

    result = benchmark_relative_worst_slice(book_slices, benchmark_slices)

    assert set(result["skipped"]) == {"bench_degenerate", "book_degenerate"}
    assert result["n_compared"] == 1
    assert set(result["per_slice"]) == {"normal"}
    assert result["worst_book_slice"] == "normal"
    assert result["worst_benchmark_slice"] == "normal"


def test_benchmark_relative_worst_slice_all_degenerate_raises():
    book_slices = {
        "bench_degenerate": [0.01, 0.02, 0.03],
        "book_degenerate": [0.01, 0.01],
    }
    benchmark_slices = {
        "bench_degenerate": [0.0, 0.0, 0.0],
        "book_degenerate": [0.01, 0.02],
    }
    with pytest.raises(AlphaError):
        benchmark_relative_worst_slice(book_slices, benchmark_slices)


@pytest.mark.parametrize(
    "book_slices, benchmark_slices",
    [
        ({}, {}),  # both empty
        ({"a": [0.01, 0.02]}, {"b": [0.01, 0.02]}),  # mismatched key sets
        ({"a": [0.01, 0.02]}, {"a": [0.01]}),  # mismatched lengths within a slice
        ({"a": [0.01, float("nan")]}, {"a": [0.01, 0.02]}),  # non-finite value
        ({"a": "not a list"}, {"a": [0.01, 0.02]}),  # slice value not a list
    ],
)
def test_benchmark_relative_worst_slice_guards(book_slices, benchmark_slices):
    with pytest.raises(AlphaError):
        benchmark_relative_worst_slice(book_slices, benchmark_slices)
