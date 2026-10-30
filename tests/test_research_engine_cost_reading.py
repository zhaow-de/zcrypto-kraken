import json
import shutil
from datetime import date

import polars as pl
import pytest

from cli.alpha.c1 import PAIRS
from cli.costs.ladder import blend, cost_table
from cli.panel.ladder import write_ladder_manifest
from cli.registry.observed import ObservedReader
from cli.registry.record import validate_metrics
from cli.research import subjects
from tests.l2_fills_fixtures import DAYS, EMPTY_PRIMARY, WRITTEN_AT
from tests.l2_ladder_fixtures import STALE_PAIR, write_l2_ladder_set

pytestmark = pytest.mark.retired

SUBJECT = "engine-cost-reading"
DATASET = "l2-ladder-test"
OVER = f"{SUBJECT} over the full history: {DATASET}/manifest.json's"
# `CrossfreqSystemConfig().assets`' order.
EUR_LEGS = ("ADA/EUR", "AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR")


def _build(root):
    return subjects.SUBJECTS[SUBJECT].build(ObservedReader(root), DATASET, None)


def _refusal(root) -> str:
    with pytest.raises(subjects.SubjectError) as refused:
        _build(root)
    return str(refused.value)


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    root = tmp_path_factory.mktemp("ladder-set") / "data"
    write_l2_ladder_set(root, DATASET)
    return root


@pytest.fixture(scope="module")
def built(written):
    return _build(written)


def _frames(root) -> dict[str, pl.DataFrame]:
    """Read off the tree, never through the subject's reads."""
    return {
        pair: pl.concat([pl.read_parquet(path) for path in sorted((root / DATASET / pair).rglob("*.parquet"))]) for pair in PAIRS
    }


def _manifest(root, change) -> None:
    path = root / DATASET / "manifest.json"
    manifest = json.loads(path.read_text())
    change(manifest)
    path.write_text(json.dumps(manifest))


def test_the_build_returns_the_declared_keys(built):
    assert set(built) == {"cost_table", "blend", "coverage", "constants"}
    assert list(built["cost_table"]) == list(PAIRS) and list(built["coverage"]) == list(PAIRS)
    assert set(built["blend"]) == {"S0", "S1"}
    assert built["constants"] == {
        "maker_fee": 0.004,
        "taker_fee": 0.008,
        "registered_per_side": 0.006,
        "mean_block": 6,
        "n_resamples": 2000,
        "seed": 42,
    }


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
        "engine-cost-reading evaluates a frozen l2-ladder set whole, never the rolling dataset as of a day: drop --as-of"
    )
    window = ("2026-09-01 00:00:00+00:00", "2026-09-02 00:00:00+00:00")
    with pytest.raises(subjects.SubjectError) as windowed:
        build(_RaisingReader(), DATASET, window)
    assert str(windowed.value) == (
        "engine-cost-reading over the window 2026-09-01 00:00:00+00:00 .. 2026-09-02 00:00:00+00:00: it reads the frozen "
        "l2-ladder set whole, its span and its months fixed; drop --window"
    )


def test_a_set_missing_a_pair_is_refused(tmp_path):
    root = tmp_path / "missing" / "data"
    write_l2_ladder_set(root, DATASET)
    shutil.rmtree(root / DATASET / "SOL" / "BTC")
    write_ladder_manifest(root / DATASET, root / EMPTY_PRIMARY, None, written_at=WRITTEN_AT)
    assert _refusal(root) == f"{OVER} pairs are not the twelve it reads: missing SOL/BTC, extra none"

    extra = tmp_path / "extra" / "data"
    write_l2_ladder_set(extra, DATASET)
    shutil.copytree(extra / DATASET / "SOL" / "BTC", extra / DATASET / "SOL" / "USD")
    write_ladder_manifest(extra / DATASET, extra / EMPTY_PRIMARY, None, written_at=WRITTEN_AT)
    assert _refusal(extra) == f"{OVER} pairs are not the twelve it reads: missing none, extra SOL/USD"


def test_a_day_file_outside_the_span_is_refused(tmp_path):
    for name, days, outside, inside in (
        ("before", (date(2026, 7, 31), date(2026, 8, 1)), "2026/07/31.parquet", "2026/08/01.parquet"),
        ("after", (date(2026, 10, 25), date(2026, 10, 26)), "2026/10/26.parquet", "2026/10/25.parquet"),
    ):
        root = tmp_path / name / "data"
        write_l2_ladder_set(root, DATASET, days=days)
        refusal = _refusal(root)
        assert refusal.endswith("lie outside the span [2026-08-01T00:00:00+00:00, 2026-10-26T00:00:00+00:00)"), refusal
        assert f"AVAX/EUR/{outside}" in refusal and inside not in refusal, refusal


# The params the set is written with, each moved alone.
_PARAMS = {
    "post_offset_s": (120, 150),
    "box_s": (900, 600),
    "boundary_hours": ([0, 4, 8, 12, 16, 20], [1, 5, 9, 13, 17, 21]),
    "size_rungs": ([0, 1], [0]),
    "stale_s": (30, 15),
    "depth": (100, 10),
}


@pytest.mark.parametrize("key", list(_PARAMS))
def test_a_set_written_with_other_params_is_refused(tmp_path, key):
    root = tmp_path / "data"
    write_l2_ladder_set(root, DATASET)
    held, moved = _PARAMS[key]

    def move(manifest):
        assert manifest["provenance"]["params"][key] == held
        manifest["provenance"]["params"][key] = moved

    _manifest(root, move)
    assert _refusal(root) == f"{OVER} params are not the ladder's: {key} {moved!r}, not {held!r}"


def test_the_cost_table_and_the_blend_are_the_cost_functions_over_the_set(built, written):
    frames = _frames(written)

    assert built["cost_table"] == {pair: cost_table(frames[pair]) for pair in PAIRS}
    tables = list(built["cost_table"].values())
    assert all(a != b for i, a in enumerate(tables) for b in tables[i + 1 :])
    assert built["blend"] == blend(frames, EUR_LEGS)
    assert built["blend"] != blend(frames, PAIRS)


def test_the_coverage_reads_the_counts_from_the_records(tmp_path):
    root = tmp_path / "data"
    write_l2_ladder_set(root, DATASET)

    # The fixture's records hold no skip for want of a quote and no unanchored or absent hour; each is planted at its own
    # count, so a leaf summed from another's key reads wrong.
    def plant(manifest):
        for records in manifest["provenance"]["pairs"].values():
            first, last = (records[day.isoformat()] for day in DAYS)
            first["skipped_no_quote"] += 2
            last["skipped_no_quote"] += 3
            last["hours_unanchored"].append(f"{DAYS[-1].isoformat()}T04:00:00+00:00")
            first["hours_absent"].append(f"{DAYS[0].isoformat()}T08:00:00+00:00")
            last["hours_absent"] += [f"{DAYS[-1].isoformat()}T12:00:00+00:00", f"{DAYS[-1].isoformat()}T16:00:00+00:00"]

    _manifest(root, plant)
    coverage = _build(root)["coverage"]

    assert _frames(root)[STALE_PAIR]["ts"].dt.date().n_unique() == 1
    # Six episodes a day over two days, four orders each; the stale pair's last day entered with every order skipped stale
    # and no row; pair k's first k boundary hours replayed with no trades hour.
    stale = {"posts": 24, "skipped_stale": 24}
    expected = {
        pair: {
            "days": 2,
            "episodes": 12,
            "posts": 48,
            "skipped_no_quote": 5,
            "skipped_stale": 0,
            "hours_unanchored": 1,
            "hours_absent": 3,
            "trades_absent": k,
        }
        | (stale if pair == STALE_PAIR else {})
        for k, pair in enumerate(PAIRS, start=1)
    }
    assert coverage == expected
    coverages = list(coverage.values())
    assert all(a != b for i, a in enumerate(coverages) for b in coverages[i + 1 :])


def test_the_metrics_hold_only_leaves_the_registry_stores(built):
    validate_metrics(built, "metrics")
    assert built["cost_table"]["ADA/EUR"]["bid|S0"]["2026-10"] == {"posts": 0, "unpriced": 0}


def test_the_subject_is_registered_as_a_reading():
    s = subjects.SUBJECTS[SUBJECT]
    assert (s.name, s.intervals, s.assets, s.build) == (SUBJECT, (15,), (), subjects._build_engine_cost_reading)
    assert s.spec == "docs/specs/00153-engine-execution-cost-design.md" and s.seeds == (42,)
    assert s.metric_keys == frozenset({"cost_table", "blend", "coverage", "constants"})
    assert s.verdict is None and s.no_verdict is None and s.incumbent is None and s.family is None and s.n_trials is None
