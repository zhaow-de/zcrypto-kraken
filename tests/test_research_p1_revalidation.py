import math
from datetime import UTC, datetime
from functools import partial

import pytest

from cli.portfolio.revalidation import METRIC_KEYS, revalidation_metrics
from cli.registry.observed import ObservedReader
from cli.research import subjects
from tests.test_research_command import _p1_revalidation_dataset

SUBJECT = "p1-revalidation"
NO_VERDICT = (
    "instrument finding: the read's in-sample prefix does not rebuild record 47's book, 27337 returns at Sharpe 1.5609; no "
    "verdict, the trial unspent"
)


def _bench(n: int) -> list[float]:
    return [0.0001 * math.sin(i) for i in range(n)]


def _bench_recorder(calls: list, h4_prices: dict[str, list[float | None]], *, cost_per_side: float) -> list[float]:
    """Stands in for the real benchmark, which over the fixture puts a case at the slow line."""
    calls.append((h4_prices, cost_per_side))
    return _bench(len(next(iter(h4_prices.values()))) - 1)


class _UnreadReader:
    def read_series(self, *args, **kwargs):
        raise AssertionError("a refused window reads no series")


def test_the_build_returns_exactly_the_declared_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", partial(_bench_recorder, []))

    build = subjects.SUBJECTS[SUBJECT].build(ObservedReader(_p1_revalidation_dataset(tmp_path)), "ohlc-test", None)

    assert set(build) == subjects.SUBJECTS[SUBJECT].metric_keys == METRIC_KEYS
    assert build["slice_returns"] == 557


def test_the_build_scores_the_governed_book_beside_the_ungoverned_and_the_benchmark(tmp_path, monkeypatch):
    root, calls = _p1_revalidation_dataset(tmp_path), []
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", partial(_bench_recorder, calls))

    build = subjects.SUBJECTS[SUBJECT].build(ObservedReader(root), "ohlc-test", None)

    *_, h4_ts, h4_prices, result = subjects._crossfreq_book(ObservedReader(root), "ohlc-test", None)
    assert calls == [(h4_prices, 0.006)]
    assert build == revalidation_metrics(result.governed_net, result.ungoverned_net, _bench(len(h4_ts) - 1), h4_ts, n_trials=6)
    assert build["slice_sharpe"] != build["slice_sharpe_ungoverned"]


def test_a_synthetic_book_is_no_record_47_and_gets_no_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", partial(_bench_recorder, []))

    build = subjects.SUBJECTS[SUBJECT].build(ObservedReader(_p1_revalidation_dataset(tmp_path)), "ohlc-test", None)

    assert subjects.SUBJECTS[SUBJECT].verdict(build) is None


@pytest.mark.parametrize(
    ("leg_sharpe_pass", "leg_maxdd_pass", "verdict"), [(1, 1, "adopt"), (0, 1, "park"), (1, 0, "park"), (0, 0, "park")]
)
def test_the_subjects_rule_adopts_on_both_legs_and_parks_on_either_failing(leg_sharpe_pass, leg_maxdd_pass, verdict):
    metrics = {
        **dict.fromkeys(METRIC_KEYS, 0),
        "in_sample_returns": 27337,
        "in_sample_sharpe": 1.5609,
        "leg_sharpe_pass": leg_sharpe_pass,
        "leg_maxdd_pass": leg_maxdd_pass,
    }

    assert subjects.SUBJECTS[SUBJECT].verdict(metrics) == verdict


def test_a_window_is_refused():
    window = ("2026-07-10 00:00:00+00:00", "2026-10-10 20:00:00+00:00")

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[SUBJECT].build(_UnreadReader(), "ohlc-test", window)

    assert str(refused.value).startswith("p1-revalidation over the window ")
    assert str(refused.value).endswith("drop --window")


def test_a_set_ending_before_a_month_of_slice_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", partial(_bench_recorder, []))
    root = _p1_revalidation_dataset(tmp_path, end=datetime(2026, 8, 8, 20, tzinfo=UTC))

    with pytest.raises(subjects.SubjectError, match=r"^p1-revalidation over the full history of ohlc-test: .* holds 179 returns"):
        subjects.SUBJECTS[SUBJECT].build(ObservedReader(root), "ohlc-test", None)


def test_the_subject_declares_family_p1_its_count_and_spec():
    subject = subjects.SUBJECTS[SUBJECT]
    crossfreq = subjects.SUBJECTS["record44-crossfreq"]

    assert subject.name == SUBJECT
    assert (subject.family, subject.n_trials, subject.seeds) == ("P1", 6, ())
    assert subject.spec == "docs/specs/00152-deployable-revalidation-design.md"
    assert subject.no_verdict == NO_VERDICT
    assert subject.metric_keys == METRIC_KEYS
    assert subject.incumbent is None
    assert (subject.intervals, subject.assets) == (crossfreq.intervals, crossfreq.assets)
