import math
import random

import pytest

from cli.alpha import AlphaError, a1_kill_bar, benchmark_relative_worst_slice, net_of_cost_verdict, short_leg_whipsaw
from cli.validation import linear_signal, sign_strategy_returns

N = 500
# Per-period Sharpe² units, consistent with a1_kill_bar's per-period sr (see its units-contract docstring).
# At this scale a genuine planted edge (sr ~= 0.78) clears the deflated benchmark (~= 0.057) so dsr -> ~1.0,
# while a beta=0 null's noise Sharpe (SE ~= 1/sqrt(N)) falls below it on the majority of seeds -> dsr < 0.5.
VAR_TRIALS_PER_PERIOD = 1e-3

# regime_slices/benchmark_slices also feed benchmark_relative_worst_slice, which compounds returns via
# max_drawdown/total_return: raw noise_sd=1.0 fixtures put individual periods below -100% and break the
# equity curve. sharpe() is mean/stdev and so scale-invariant, which is why scaling a book down changes
# nothing about the DSR/SPA/cost-stress legs or the recorded worst_slice_name/worst_slice_sharpe.
_SLICE_SCALE = 0.01


def _book_and_benchmark(*, beta, seed):
    x, r = linear_signal(N, beta=beta, noise_sd=1.0, seed=seed)
    book = sign_strategy_returns(x, r)
    benchmark = [0.0] * N  # flat benchmark -> the book's outperformance is just its own return
    return book, benchmark


def _slices(returns):
    return {"first_half": returns[: N // 2], "second_half": returns[N // 2 :]}


def _scaled(returns):
    return [r * _SLICE_SCALE for r in returns]


def _book_regime_slices(book):
    """regime_slices fixture built from a raw noise_sd=1.0 book -- see _SLICE_SCALE."""
    return _slices(_scaled(book))


def _noise_series(n, seed):
    """A zero-edge, non-degenerate return series -- a plausible benchmark_slices source."""
    x, r = linear_signal(n, beta=0.0, noise_sd=1.0, seed=seed)
    return sign_strategy_returns(x, r)


# Generic non-degenerate benchmark_slices fixture for tests where the relative worst-slice leg isn't the
# point under test (fixed/deterministic seed, reused across those tests).
_NOISE_BENCHMARK_SLICES = _slices(_scaled(_noise_series(N, seed=999)))


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
        regime_slices=_book_regime_slices(book),
        benchmark_slices=_NOISE_BENCHMARK_SLICES,
    )
    # dsr is a probability, and the ratified bar is 0.95 (T0009), not merely > 0.
    assert result["dsr"] > 0.95
    assert result["dsr_pass"] is True
    assert result["spa_pass"] is True
    assert result["spa_p_value"] < 0.05
    # decisive_start defaults to 0, so the decisive window is the full window here.
    assert result["spa_p_value_full"] == pytest.approx(result["spa_p_value"])
    assert result["cost_stress_pass"] is True
    assert result["worst_slice_pass"] is True
    assert result["passes"] is True
    # worst_slice_relative is the diagnostic's dict minus its per_slice detail.
    assert "per_slice" not in result["worst_slice_relative"]
    assert result["worst_slice_relative"]["beats_benchmark_worst"] is True


def test_a1_kill_bar_null_rarely_passes():
    # Over 20 seeds, a beta=0 (no real edge) book should almost never clear all four kill-bar
    # conditions at once. The DSR leg is the strictest: `deflated_sharpe_ratio` returns a normal CDF,
    # so it underflows toward 0 but never reaches it and a `dsr > 0` gate cannot fail a null at all;
    # the ratified 0.95 bar (T0009) is what makes this leg discriminate.
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
            regime_slices=_book_regime_slices(book),
            benchmark_slices=_NOISE_BENCHMARK_SLICES,
        )
        if result["passes"]:
            passed += 1
        if result["dsr_pass"]:
            dsr_leg_passed += 1
    assert passed <= 2
    assert dsr_leg_passed <= 2


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
        regime_slices=_book_regime_slices(book),
        benchmark_slices=_NOISE_BENCHMARK_SLICES,
    )
    assert result["cost_stress_pass"] is False
    assert result["passes"] is False  # cost stress alone fails the all-must-hold bar


def test_a1_kill_bar_worst_slice_can_fail_alone():
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    bad_slice = [-0.01 + 0.002 * ((i % 3) - 1) for i in range(50)]  # non-degenerate, clearly negative
    # The benchmark's own "bad_regime" easily beats the book's very negative slice, so the T0009-ratified
    # relative leg fails here too -- same outcome as the old absolute leg, now for a relative reason.
    benchmark_slices = {"good": _scaled(_noise_series(N, seed=501)), "bad_regime": _scaled(_noise_series(50, seed=502))}
    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=1.0,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices={"good": _scaled(book), "bad_regime": bad_slice},
        benchmark_slices=benchmark_slices,
    )
    assert result["worst_slice_name"] == "bad_regime"
    assert result["worst_slice_pass"] is False
    assert result["worst_slice_relative"]["beats_benchmark_worst"] is False
    assert result["passes"] is False


def test_a1_kill_bar_skips_flat_regime_slice():
    # A flat slice (e.g. a calendar year entirely inside gate warm-up, or a bear year a long/flat book
    # correctly sat out) has zero variance -- sharpe() is undefined there, so it must be skipped rather
    # than raising or being treated as the worst (or best) slice. This is the book-side record computation
    # (worst_slice_name/worst_slice_sharpe), unaffected by the T0009 relative worst-slice leg.
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    bad_slice = [-0.01 + 0.002 * ((i % 3) - 1) for i in range(50)]  # non-degenerate, clearly negative
    flat_zero = [0.0] * 50
    flat_const = [0.01] * 50
    good_bench = _scaled(_noise_series(N, seed=501))
    bad_bench = _scaled(_noise_series(50, seed=502))

    def _run(regime_slices, benchmark_slices):
        return a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=1.0,
            mean_block=5,
            seed=7,
            cost_stressed_returns=book,
            regime_slices=regime_slices,
            benchmark_slices=benchmark_slices,
        )

    with_flat = _run(
        {"good": _scaled(book), "bad_regime": bad_slice, "flat_zero": flat_zero, "flat_const": flat_const},
        {
            "good": good_bench,
            "bad_regime": bad_bench,
            "flat_zero": _scaled(_noise_series(50, seed=503)),
            "flat_const": _scaled(_noise_series(50, seed=504)),
        },
    )
    without_flat = _run(
        {"good": _scaled(book), "bad_regime": bad_slice},
        {"good": good_bench, "bad_regime": bad_bench},
    )

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
        # Every regime_slices entry is book-side degenerate, so benchmark_relative_worst_slice would have
        # nothing to compare regardless of these values -- a1_kill_bar short-circuits instead of calling it.
        benchmark_slices={"flat_zero": [0.02] * 50, "too_short": [0.02], "flat_const": [0.02] * 30},
    )
    assert result["worst_slice_name"] == "<no-nondegenerate-slice>"
    assert result["worst_slice_pass"] is False
    assert result["worst_slice_relative"]["beats_benchmark_worst"] is False
    assert result["passes"] is False


def test_a1_kill_bar_dsr_fails_between_old_and_new_bar():
    # A marginal edge (beta=0.4) with var_trials=0.01 lands dsr ~= 0.925 -- strictly between the
    # pre-ratification 0.5 bar and the T0009-ratified 0.95 bar (2026-07-09). It would have passed the old
    # kill bar; it fails the new one, alone (the other three legs still pass).
    x, r = linear_signal(N, beta=0.4, noise_sd=1.0, seed=1)
    book = sign_strategy_returns(x, r)
    benchmark = [0.0] * N
    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=0.01,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices=_book_regime_slices(book),
        benchmark_slices=_NOISE_BENCHMARK_SLICES,
    )
    assert 0.5 < result["dsr"] < 0.95
    assert result["dsr_pass"] is False
    assert result["spa_pass"] is True
    assert result["cost_stress_pass"] is True
    assert result["worst_slice_pass"] is True
    assert result["passes"] is False  # DSR alone fails the all-must-hold bar under the ratified 0.95


def test_a1_kill_bar_spa_decisive_window_diverges_from_full():
    # The book's edge over the benchmark exists ONLY before decisive_start (a constant drift on top
    # of shared noise); from there on book == benchmark exactly. The full window sees the pre-cut
    # edge and is significant, the decisive window is not -- the divergence the decisive-window SPA
    # leg exists to catch (230 is the benchmark's post-warm-up cut for B3+vt-dynamic).
    decisive_start = 230
    rng = random.Random(1)
    book, benchmark = [], []
    for i in range(N):
        shared_noise = rng.gauss(0.0, 0.01)
        benchmark.append(shared_noise)
        book.append(shared_noise + 0.02 if i < decisive_start else shared_noise)

    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=VAR_TRIALS_PER_PERIOD,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices=_slices(book),
        benchmark_slices=_slices(benchmark),
        decisive_start=decisive_start,
    )
    assert result["spa_p_value_full"] < 0.05
    assert result["spa_p_value"] >= 0.05
    assert result["spa_pass"] is False
    assert result["passes"] is False  # SPA alone fails the all-must-hold bar on the decisive window


def test_a1_kill_bar_relative_worst_slice_passes_despite_negative_sharpe():
    # Same construction as test_benchmark_relative_worst_slice_exposure_blindness, where the P&L and
    # drawdown contradiction is asserted: the fully-exposed book loses more than the near-flat
    # benchmark yet has a LESS negative Sharpe, because its bigger stdev shrinks the ratio's magnitude
    # and `beats_benchmark_worst` keys on Sharpe -- so the relative leg passes it.
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    near_flat_benchmark = [0.0] * 16 + [-0.004, 0.001, -0.004, 0.001]
    fully_exposed_book = [0.05, -0.052] * 10

    result = a1_kill_bar(
        book,
        benchmark,
        n_trials=16,
        var_trials=VAR_TRIALS_PER_PERIOD,
        mean_block=5,
        seed=7,
        cost_stressed_returns=book,
        regime_slices={"2014": fully_exposed_book},
        benchmark_slices={"2014": near_flat_benchmark},
    )
    assert result["worst_slice_sharpe"] < 0
    assert result["worst_slice_pass"] is True
    assert result["worst_slice_relative"]["beats_benchmark_worst"] is True
    assert "per_slice" not in result["worst_slice_relative"]
    assert result["passes"] is True


def test_a1_kill_bar_requires_benchmark_slices_kwarg():
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    with pytest.raises(TypeError):
        a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=VAR_TRIALS_PER_PERIOD,
            mean_block=5,
            seed=7,
            cost_stressed_returns=book,
            regime_slices=_book_regime_slices(book),
        )


@pytest.mark.parametrize("decisive_start", [-1, N, 1.5, "10"])
def test_a1_kill_bar_guards_bad_decisive_start(decisive_start):
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    with pytest.raises(AlphaError):
        a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=VAR_TRIALS_PER_PERIOD,
            mean_block=5,
            seed=7,
            cost_stressed_returns=book,
            regime_slices=_book_regime_slices(book),
            benchmark_slices=_NOISE_BENCHMARK_SLICES,
            decisive_start=decisive_start,
        )


def test_a1_kill_bar_n_resamples_passthrough():
    # n_resamples feeds the SPA leg's reality_check_pvalue (both windows). Default 1000 matches every
    # registry row recorded before the fold-in; the pre-registered trial protocol ([iter-059]) passes
    # 2000 explicitly. Different resample counts give different bootstrap p-values, so only shape and
    # finiteness are asserted -- never exact p equality across counts.
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)

    def _run(n_resamples):
        return a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=VAR_TRIALS_PER_PERIOD,
            mean_block=5,
            seed=7,
            cost_stressed_returns=book,
            regime_slices=_book_regime_slices(book),
            benchmark_slices=_NOISE_BENCHMARK_SLICES,
            n_resamples=n_resamples,
        )

    low = _run(100)
    high = _run(2000)
    assert set(low) == set(high)  # result dict shape is independent of the resample count
    for result in (low, high):
        assert math.isfinite(result["spa_p_value"])
        assert math.isfinite(result["spa_p_value_full"])
        assert 0 < result["spa_p_value"] <= 1
        assert 0 < result["spa_p_value_full"] <= 1


@pytest.mark.parametrize("n_resamples", [0, -1, 1.5, "10"])
def test_a1_kill_bar_guards_bad_n_resamples(n_resamples):
    book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
    with pytest.raises(AlphaError):
        a1_kill_bar(
            book,
            benchmark,
            n_trials=16,
            var_trials=VAR_TRIALS_PER_PERIOD,
            mean_block=5,
            seed=7,
            cost_stressed_returns=book,
            regime_slices=_book_regime_slices(book),
            benchmark_slices=_NOISE_BENCHMARK_SLICES,
            n_resamples=n_resamples,
        )


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
            benchmark_slices={"x": [0.01, 0.02]},
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
            benchmark_slices={},
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
    # The scenario this helper exists for: a book that beats the benchmark GROSS but trails it once
    # a realistic per-period cost is charged, which a comparison run on zero-fee returns reads as an
    # edge and over-credits a high-turnover family.
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
    # The real iter-053 2014 case (docs/research/09.phase4-a2-results.md): the frozen benchmark's
    # gate held it near-flat, so its slice has a clearly negative per-period Sharpe yet only a small
    # total loss and drawdown, while a fully-exposed challenger has a LESS negative Sharpe (bigger
    # stdev shrinks the ratio) with a BIGGER loss and drawdown -- what a Sharpe-only leg hides.
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
