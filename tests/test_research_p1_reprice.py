import re
from dataclasses import replace
from pathlib import Path

import pytest

from cli.portfolio.crossfreq_system import build_crossfreq_system_fast
from cli.portfolio.repricing import METRIC_KEYS, repricing_metrics
from cli.registry.observed import ObservedReader
from cli.research import subjects
from tests.test_portfolio_repricing import _bench_recorder, _spa_recorder
from tests.test_research_command import _declared_series, _p1_revalidation_dataset
from tests.test_research_p1_revalidation import _UnreadReader

pytestmark = pytest.mark.retired

SUBJECT = "p1-reprice"
NO_VERDICT = (
    "instrument finding: the data does not rebuild record 47's book at its registered cost, 27337 returns at Sharpe 1.5609; "
    "no verdict, the trial unspent"
)
_REPO = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root, _ = _declared_series(tmp_path, subjects.SUBJECTS[SUBJECT])
    return root


def _built(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    """The real benchmark and SPA put a build over the fixture past the slow line."""
    monkeypatch.setattr("cli.portfolio.repricing.benchmark_4h_net_of_cost", _bench_recorder([]))
    monkeypatch.setattr("cli.portfolio.repricing.reality_check_pvalue", _spa_recorder([]))
    root = _fixture(tmp_path)
    return root, subjects.SUBJECTS[SUBJECT].build(ObservedReader(root), "ohlc-test", None)


def test_the_build_returns_exactly_the_declared_keys(tmp_path, monkeypatch):
    _, build = _built(tmp_path, monkeypatch)

    assert set(build) == subjects.SUBJECTS[SUBJECT].metric_keys == METRIC_KEYS


def test_the_build_is_the_scoring_at_the_registered_basis_and_the_pick(tmp_path, monkeypatch):
    root, build = _built(tmp_path, monkeypatch)
    pick = subjects._P1_REPRICE_CONFIG

    assert build == repricing_metrics(
        *subjects._crossfreq_inputs(ObservedReader(root), "ohlc-test", None),
        registered=subjects._RECORD44_CONFIG,
        basis=pick,
        n_trials=7,
    )
    assert (build["fee_per_side"], build["spread_per_side"]) == (pick.fee_per_side, pick.spread_per_side)


def test_the_pick_is_the_specs_and_every_other_field_record_47s():
    spec = (_REPO / subjects.SUBJECTS[SUBJECT].spec).read_text().splitlines()
    picks = [line for line in spec if line.startswith("- **The pick**")]
    assert len(picks) == 1
    fee, spread = (re.findall(rf"`{term}=([^`]*)`", picks[0]) for term in ("fee_per_side", "spread_per_side"))
    assert len(fee) == len(spread) == 1
    pick = subjects._P1_REPRICE_CONFIG

    assert (pick.fee_per_side, pick.spread_per_side) == (float(fee[0]), float(spread[0]))
    assert replace(pick, fee_per_side=0.0040, spread_per_side=0.0020) == subjects._RECORD44_CONFIG


def test_the_crossfreq_book_is_its_inputs_built_at_the_registered_basis(tmp_path):
    root = _fixture(tmp_path)
    reader, reader2, reader3 = (ObservedReader(root) for _ in range(3))
    reads = (
        *subjects._capturing_union(reader2, "ohlc-test", 1440, None, None, False),
        *subjects._capturing_union(reader2, "ohlc-test", 240, None, None, False),
    )
    daily_ts, daily_prices, h4_ts, h4_prices = reads
    *_, result = subjects._crossfreq_book(reader3, "ohlc-test", None)

    assert subjects._crossfreq_inputs(reader, "ohlc-test", None) == reads
    assert (
        result.governed_net
        == build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=subjects._RECORD44_CONFIG).governed_net
    )


def test_the_crossfreq_book_forwards_its_as_of_and_accept_holes(monkeypatch):
    reads = []

    def _record(*arguments):
        reads.append(arguments)
        return [], {}, [], {}

    monkeypatch.setattr("cli.research.subjects._crossfreq_inputs", _record)
    monkeypatch.setattr("cli.research.subjects.build_crossfreq_system_fast", lambda *inputs, **kwargs: None)
    reader = object()

    subjects._crossfreq_book(reader, "ohlc-test", None, as_of="2026-03-31", accept_holes=True)

    assert reads == [(reader, "ohlc-test", None, "2026-03-31", True)]


def test_a_synthetic_book_is_no_record_47_and_gets_no_verdict(tmp_path, monkeypatch):
    _, build = _built(tmp_path, monkeypatch)

    assert subjects.SUBJECTS[SUBJECT].verdict(build) is None


@pytest.mark.parametrize(("passes", "verdict"), [(1, "adopt"), (0, "park")])
def test_the_subjects_rule_adopts_on_every_leg_and_parks_otherwise(passes, verdict):
    metrics = {
        **dict.fromkeys(METRIC_KEYS, 0),
        "registered_basis_returns": 27337,
        "registered_basis_sharpe": 1.5609,
        "passes": passes,
    }

    assert subjects.SUBJECTS[SUBJECT].verdict(metrics) == verdict


def test_a_window_is_refused():
    window = ("2025-01-01 00:00:00+00:00", "2026-03-31 20:00:00+00:00")

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[SUBJECT].build(_UnreadReader(), "ohlc-test", window)

    assert str(refused.value).startswith("p1-reprice over the window ")
    assert str(refused.value).endswith("drop --window")


def test_the_build_forwards_its_as_of_and_accept_holes(monkeypatch):
    reads = []

    def _record(*arguments):
        reads.append(arguments)
        return ()

    monkeypatch.setattr("cli.research.subjects._crossfreq_inputs", _record)
    monkeypatch.setattr("cli.research.subjects.repricing_metrics", lambda *inputs, **kwargs: {})
    reader = object()

    subjects.SUBJECTS[SUBJECT].build(reader, "ohlc-test", None, as_of="2026-03-31", accept_holes=True)

    assert reads == [(reader, "ohlc-test", None, "2026-03-31", True)]


def test_a_set_reaching_past_the_in_sample_end_is_refused_before_any_build(tmp_path, monkeypatch):
    def unbuilt(*args, **kwargs):
        raise AssertionError("a read past the in-sample end builds no book")

    monkeypatch.setattr("cli.portfolio.repricing.build_crossfreq_system_fast", unbuilt)
    monkeypatch.setattr("cli.research.subjects.build_crossfreq_system_fast", unbuilt)

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[SUBJECT].build(ObservedReader(_p1_revalidation_dataset(tmp_path)), "ohlc-test", None)

    assert str(refused.value).startswith("p1-reprice over the full history of ohlc-test: ")
    assert "2026-10-10 20:00:00+00:00" in str(refused.value)


def test_the_subject_declares_family_p1_its_count_seeds_and_spec():
    subject = subjects.SUBJECTS[SUBJECT]
    crossfreq = subjects.SUBJECTS["record44-crossfreq"]

    assert subject.name == SUBJECT
    assert (subject.family, subject.n_trials, subject.seeds) == ("P1", 7, (42, 7, 1234))
    assert subject.spec == "docs/specs/00154-cost-basis-repricing-design.md"
    assert subject.no_verdict == NO_VERDICT
    assert subject.metric_keys == METRIC_KEYS
    assert subject.incumbent is None
    assert (subject.intervals, subject.assets) == (crossfreq.intervals, crossfreq.assets)
