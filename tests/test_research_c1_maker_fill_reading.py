import json
import shutil
from datetime import date

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.alpha.c1 import HORIZONS_S, MONTHS, PAIRS, SIDES, SIZES, THRESHOLDS, cell_name
from cli.panel.fills import write_fills_manifest
from cli.registry.observed import ObservedReader
from cli.registry.record import validate_metrics
from cli.research import subjects
from tests.l2_fills_fixtures import EMPTY_PRIMARY, WRITTEN_AT, write_l2_fills_set

SUBJECT = "c1-maker-fill-reading"
DATASET = "l2-fills-test"
OUTCOMES = (
    "filled",
    "time_to_fill_s",
    "cancelled_s",
    "fill_price",
    "mid_at_fill_plus_60s",
    "mid_at_fill_plus_900s",
    "mid_at_post_plus_900s",
    "mid_at_post_plus_3600s",
)
runner = CliRunner()


def _build(root):
    return subjects.SUBJECTS[SUBJECT].build(ObservedReader(root), DATASET, None)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("c1-set") / "data"
    write_l2_fills_set(root, DATASET)
    return _build(root)


def _eval(monkeypatch, root):
    monkeypatch.setattr("cli.research.command._DATA_ROOT", root)
    return runner.invoke(app, ["research", "eval", "--subject", SUBJECT, "--dataset", DATASET])


def _refused(result, cause):
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert cause in result.output, result.output


def test_the_build_returns_exactly_the_declared_keys_96_cells_and_a_fill_table_per_pair(built):
    assert set(built) == {"fill_table", "cells", "coverage", "constants"}
    assert set(built["cells"]) == {
        cell_name(pair, threshold, size, side) for pair in PAIRS for threshold in THRESHOLDS for size in SIZES for side in SIDES
    }
    assert len(built["cells"]) == 96
    assert all(set(cell) == {"n_signals", "fill_rate_900", "n_unmarked", "months", "span"} for cell in built["cells"].values())
    assert list(built["fill_table"]) == list(PAIRS) and set(built["coverage"]) == set(PAIRS)
    for k, pair in enumerate(PAIRS, start=1):
        table = built["fill_table"][pair]
        assert set(table) == {f"{side}|S{size}|H{horizon}" for side in SIDES for size in SIZES for horizon in HORIZONS_S}
        assert table["bid|S0|H900"]["span"]["n_filled"] == k, pair
    assert built["constants"] == {
        "maker_round_trip": 0.008,
        "horizons_s": [60, 300, 900],
        "thresholds": [1, 2],
        "mean_block": 30,
        "n_resamples": 4000,
        "seed": 42,
        "grid_s": 15,
        "horizon_s": 900,
    }


def test_each_pairs_eight_cells_read_its_own_frame_and_differ(built):
    cells = built["cells"]
    # ETH/EUR, the sixth pair: fifteen down moves past 1 sigma, three of them past 2, and seven up moves, two past 2; its
    # rung-0 bid fills at the first six medium down moves, its rung-1 bid at the three big ones, its rung-0 ask at the five
    # medium up moves and its rung-1 ask at the two big ones.
    expected = {
        "ETH/EUR|th1|S0|bid": (15, 6),
        "ETH/EUR|th1|S1|bid": (15, 3),
        "ETH/EUR|th2|S0|bid": (3, 0),
        "ETH/EUR|th2|S1|bid": (3, 3),
        "ETH/EUR|th1|S0|ask": (7, 5),
        "ETH/EUR|th1|S1|ask": (7, 2),
        "ETH/EUR|th2|S0|ask": (2, 0),
        "ETH/EUR|th2|S1|ask": (2, 2),
    }
    assert {name: (cells[name]["n_signals"], cells[name]["span"]["n"]) for name in expected} == expected
    assert [cells[cell_name(pair, 1, 0, "bid")]["span"]["n"] for pair in PAIRS] == list(range(1, 13))
    eights = {
        pair: [cells[cell_name(pair, threshold, size, side)] for threshold in THRESHOLDS for size in SIZES for side in SIDES]
        for pair in PAIRS
    }
    assert all(eights[a] != eights[b] for a in PAIRS for b in PAIRS if a < b)


def test_the_inputs_half_receives_only_the_columns_known_at_the_post(tmp_path, monkeypatch):
    root = tmp_path / "data"
    write_l2_fills_set(root, DATASET)
    inputs, received = subjects._c1_reading_inputs, []

    def recording(frames, provenance):
        received.append({pair: frame.columns for pair, frame in frames.items()})
        return inputs(frames, provenance)

    monkeypatch.setattr(subjects, "_c1_reading_inputs", recording)
    _build(root)

    assert subjects._C1_INPUT_COLUMNS == (
        "ts",
        "pair",
        "side",
        "size",
        "mid_at_post",
        "spread_at_post_bps",
        "stale_seconds_at_post",
        "queue_ahead_qty",
        "queue_ahead_notional",
        "our_qty",
    )
    assert len(received) == 1 and set(received[0]) == set(PAIRS)
    assert all(columns == list(subjects._C1_INPUT_COLUMNS) for columns in received[0].values())
    assert not set(OUTCOMES) & {column for columns in received[0].values() for column in columns}


def _months(aug_posts):
    """The fixture's queue-ahead notional by side and rung, 100 more on its September day; its spread 2 bps; a stale
    second unknown at each day's first post."""
    queue = {"bid|S0": 1000.0, "bid|S1": 2000.0, "ask|S0": 1500.0, "ask|S1": 2500.0}
    return {
        "2026-08": {
            key: {"posts": aug_posts, "queue_ahead_notional_mean": q, "spread_at_post_bps_mean": 2.0, "stale_seconds_null": 1}
            for key, q in queue.items()
        },
        "2026-09": {
            key: {"posts": 96, "queue_ahead_notional_mean": q + 100.0, "spread_at_post_bps_mean": 2.0, "stale_seconds_null": 1}
            for key, q in queue.items()
        },
        "2026-10": {key: {"posts": 0, "stale_seconds_null": 0} for key in queue},
    }


def test_the_inputs_half_reads_the_skip_counts_and_gaps_from_the_manifest(tmp_path):
    root = tmp_path / "data"
    write_l2_fills_set(root, DATASET, gaps=True)
    coverage = _build(root)["coverage"]

    assert set(coverage) == set(PAIRS)
    ada = coverage["ADA/EUR"]
    # 21 hours posted on the first day and 24 on the second, at 960 a posted hour less the day's 336 and 384 posts and
    # its 404 skipped with no quote.
    assert {key: value for key, value in ada.items() if key != "months"} == {
        "days": 2,
        "skipped_no_quote": 808,
        "skipped_stale": 41672,
        "hours_unanchored": 1,
        "hours_absent": 2,
        "trades_absent": 3,
    }
    btc = coverage["BTC/EUR"]
    assert {key: value for key, value in btc.items() if key != "months"} == {
        "days": 2,
        "skipped_no_quote": 824,
        "skipped_stale": 44488,
        "hours_unanchored": 0,
        "hours_absent": 0,
        "trades_absent": 0,
    }
    for pair in PAIRS:
        months = coverage[pair]["months"]
        assert list(months) == list(MONTHS), pair
        expected = _months(84 if pair == "ADA/EUR" else 96)
        for month in MONTHS:
            assert set(months[month]) == set(expected[month]), (pair, month)
            for key, leaves in expected[month].items():
                assert months[month][key] == pytest.approx(leaves), (pair, month, key)
        if pair != "ADA/EUR":
            assert [coverage[pair][key] for key in ("hours_unanchored", "hours_absent", "trades_absent")] == [0, 0, 0], pair


class _RaisingReader:
    @property
    def _root(self):
        raise AssertionError("read the data root")

    def read_series(self, dataset, relpath, window=None):
        raise AssertionError(f"read {relpath}")


def test_as_of_and_window_are_refused_before_any_read():
    build = subjects.SUBJECTS[SUBJECT].build
    with pytest.raises(subjects.SubjectError) as as_of:
        build(_RaisingReader(), DATASET, None, as_of="2026-10-01")
    assert str(as_of.value) == (
        "c1-maker-fill-reading evaluates a frozen l2-fills set whole, never the rolling dataset as of a day: drop --as-of"
    )
    window = ("2026-09-01 00:00:00+00:00", "2026-09-02 00:00:00+00:00")
    with pytest.raises(subjects.SubjectError) as windowed:
        build(_RaisingReader(), DATASET, window)
    assert str(windowed.value) == (
        "c1-maker-fill-reading over the window 2026-09-01 00:00:00+00:00 .. 2026-09-02 00:00:00+00:00: it reads the frozen "
        "l2-fills set whole, and the scale's trailing day reaches back past any window's first stamp; drop --window"
    )


def test_a_manifest_missing_a_pair_is_refused(tmp_path, monkeypatch):
    root = tmp_path / "missing" / "data"
    write_l2_fills_set(root, DATASET)
    shutil.rmtree(root / DATASET / "SOL" / "BTC")
    write_fills_manifest(root / DATASET, root / EMPTY_PRIMARY, None, written_at=WRITTEN_AT)
    _refused(_eval(monkeypatch, root), f"{DATASET}/manifest.json's pairs are not the twelve it reads: missing SOL/BTC, extra none")

    extra = tmp_path / "extra" / "data"
    write_l2_fills_set(extra, DATASET)
    shutil.copytree(extra / DATASET / "SOL" / "BTC", extra / DATASET / "SOL" / "USD")
    write_fills_manifest(extra / DATASET, extra / EMPTY_PRIMARY, None, written_at=WRITTEN_AT)
    _refused(_eval(monkeypatch, extra), f"{DATASET}/manifest.json's pairs are not the twelve it reads: missing none, extra SOL/USD")


def test_a_day_file_outside_the_span_is_refused(tmp_path, monkeypatch):
    for name, days, outside, inside in (
        ("before", (date(2026, 7, 31), date(2026, 8, 1)), "2026/07/31.parquet", "2026/08/01.parquet"),
        ("after", (date(2026, 10, 25), date(2026, 10, 26)), "2026/10/26.parquet", "2026/10/25.parquet"),
    ):
        root = tmp_path / name / "data"
        write_l2_fills_set(root, DATASET, days=days)
        result = _eval(monkeypatch, root)
        _refused(result, "lie outside the span [2026-08-01T00:00:00+00:00, 2026-10-26T00:00:00+00:00)")
        assert f"ADA/EUR/{outside}" in result.output and inside not in result.output, result.output


def test_an_unparseable_or_absent_manifest_ends_in_an_exit(tmp_path, monkeypatch):
    def unparseable(dataset):
        (dataset / "manifest.json").write_text("{not json")

    def absent(dataset):
        (dataset / "manifest.json").unlink()

    def without_a_pairs_records(dataset):
        manifest = json.loads((dataset / "manifest.json").read_text())
        del manifest["provenance"]["pairs"]["DOT/EUR"]
        (dataset / "manifest.json").write_text(json.dumps(manifest))

    def a_day_file_removed(dataset):
        (dataset / "ETH" / "EUR" / "2026" / "09" / "01.parquet").unlink()

    for spoil, cause in (
        (unparseable, f"{DATASET}/manifest.json cannot be read: "),
        (absent, f"{DATASET}/manifest.json cannot be read: "),
        (without_a_pairs_records, f"{DATASET}/manifest.json's provenance holds no day records for DOT/EUR"),
        (a_day_file_removed, f"{DATASET}/ETH/EUR/2026/09/01.parquet: "),
    ):
        root = tmp_path / spoil.__name__ / "data"
        write_l2_fills_set(root, DATASET)
        spoil(root / DATASET)
        _refused(_eval(monkeypatch, root), cause)


def test_the_subject_is_registered_as_a_reading():
    s = subjects.SUBJECTS[SUBJECT]
    assert (s.name, s.intervals, s.assets, s.build) == (SUBJECT, (15,), (), subjects._build_c1_maker_fill_reading)
    assert s.spec == "docs/specs/00151-c1-maker-fill-reading-design.md" and s.seeds == (42,)
    assert s.metric_keys == subjects._C1_READING_KEYS == frozenset({"fill_table", "cells", "coverage", "constants"})
    assert s.verdict is None and s.no_verdict is None and s.incumbent is None and s.family is None and s.n_trials is None


def test_the_metrics_hold_only_leaves_the_registry_stores(built):
    validate_metrics(built, "metrics")
    empty_month = {"posts": 0, "n_filled": 0, "n_unmarked_60": 0, "n_unmarked_900": 0}
    assert built["fill_table"]["ADA/EUR"]["bid|S0|H60"]["months"]["2026-10"] == empty_month
    assert built["coverage"]["ADA/EUR"]["months"]["2026-10"]["bid|S0"] == {"posts": 0, "stale_seconds_null": 0}
    no_fill = built["cells"]["ADA/EUR|th2|S0|bid"]
    assert no_fill["months"]["2026-10"] == {"n": 0} and no_fill["span"] == {"n": 0}
    assert "p" not in built["cells"]["ADA/EUR|th1|S0|bid"]["span"]
