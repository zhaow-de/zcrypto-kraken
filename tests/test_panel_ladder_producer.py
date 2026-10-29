"""The producer half of `cli/panel/ladder.py` and its two `zcrypto panel` commands (spec 00153 D2), each case on a known
answer over the fill producer's synthetic capture tree and `write_state` seeds."""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.data.manifest import read_manifest
from cli.ohlc.dataset import dataset_hash
from cli.panel import fills
from cli.panel.errors import PanelError
from cli.panel.ladder import BOUNDARY_HOURS, RUN_RECORD, produce_ladder_pair, rows_frame, write_ladder_manifest
from cli.panel.materialize import _code_ref, _state_path
from tests.test_panel_fills_producer import HEALED_BIDS, _at, _book_hour, _copy, _roots, _seed, _segment, _sidecar, _trades_hour

PAIR = "BTC/EUR"
OTHER = "ETH/EUR"
D = datetime(2026, 9, 2, tzinfo=UTC)
NEXT = D + timedelta(days=1)
END = NEXT + timedelta(days=1)
WRITTEN_AT = "2026-10-29T00:00:00+00:00"
# A sell at the best bid at :05:00 meets its queue ahead, 1.0, then the €100 bid's 0.1 whole and 0.2 of the €1,000 bid.
FILL = (300, "sell", 1000.0, 1.2)
runner = CliRunner()


def _h(hour: int, day: datetime = D) -> datetime:
    return day + timedelta(hours=hour)


def _isos(day: datetime, hours) -> list[str]:
    return [_h(hour, day).isoformat() for hour in hours]


def _archive(root: Path, pair: str, day: datetime, hours=BOUNDARY_HOURS, *, prints=(FILL,), snapshot=True) -> None:
    for hour in hours:
        _book_hour(root, pair, _h(hour, day), snapshot=snapshot)
        if prints:
            _trades_hour(root, pair, _h(hour, day), list(prints))


def _produce(primary: Path, panel: Path, out: Path, pair: str = PAIR, *, since=D, until=NEXT, overlay=None, depth=100) -> dict:
    return produce_ladder_pair(primary, overlay, panel, out, pair, since=since, until=until, depth=depth)


def _manifest(out: Path, primary: Path, overlay: Path | None) -> Path:
    return write_ladder_manifest(out, primary, overlay, written_at=WRITTEN_AT)


def _day_path(out: Path, pair: str, day: datetime) -> Path:
    base, quote = pair.split("/")
    return out / base / quote / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"


def _record_path(out: Path, pair: str) -> Path:
    base, quote = pair.split("/")
    return out / base / quote / RUN_RECORD


def _record(out: Path, pair: str) -> dict:
    return json.loads(_record_path(out, pair).read_text())


def _edit_record(out: Path, pair: str, edit) -> None:
    record = _record(out, pair)
    edit(record)
    _record_path(out, pair).write_text(json.dumps(record))


def _row(frame: pl.DataFrame, boundary: datetime, side: str, size: int = 0) -> dict:
    [row] = frame.filter((pl.col("ts") == _at(boundary, 120)) & (pl.col("side") == side) & (pl.col("size") == size)).to_dicts()
    return row


def _params(since: datetime, until: datetime) -> dict:
    return {
        "post_offset_s": 120,
        "box_s": 900,
        "boundary_hours": [0, 4, 8, 12, 16, 20],
        "size_rungs": [0, 1],
        "stale_s": 30,
        "depth": 100,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


def _entry(**overrides) -> dict:
    lists = ("hours_unanchored", "hours_absent", "trades_absent", "book_reconciled", "trades_reconciled")
    return {"hours": 6, "posts": 24, "skipped_no_quote": 0, "skipped_stale": 0, **{name: [] for name in lists}, **overrides}


def _counts(**overrides) -> dict:
    absent = {"hours_unanchored": 0, "hours_absent": 0, "trades_absent": 0}
    return {"hours": 6, "posts": 24, "skipped_no_quote": 0, "skipped_stale": 0, **absent, "days_written": 1, **overrides}


def _without_seconds(counts: dict) -> dict:
    assert list(counts)[-1] == "seconds" and isinstance(counts["seconds"], float) and counts["seconds"] >= 0
    return {name: value for name, value in counts.items() if name != "seconds"}


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    """Two pairs over D and NEXT, read through an empty overlay. BTC/EUR: every boundary hour opens with a snapshot and
    has `FILL`; ETH/EUR: D's boundary hours open with an update and have no seed, so they are unanchored, NEXT's open
    with a snapshot; no trades hour."""
    tmp = tmp_path_factory.mktemp("produced")
    primary, overlay, panel = _roots(tmp)
    for day in (D, NEXT):
        _archive(primary, PAIR, day)
    _archive(primary, OTHER, D, prints=(), snapshot=False)
    _archive(primary, OTHER, NEXT, prints=())
    out = tmp / "l2-ladder-test"
    counts = {pair: _produce(primary, panel, out, pair, until=END, overlay=overlay) for pair in (PAIR, OTHER)}
    return primary, overlay, out, counts


def test_a_days_six_episodes_land_in_one_day_file_with_its_sidecar_and_record(produced):
    _, _, out, counts = produced
    assert _without_seconds(counts[PAIR]) == _counts(hours=12, posts=48, days_written=2)
    assert _without_seconds(counts[OTHER]) == _counts(hours_unanchored=6, trades_absent=12)
    path = _day_path(out, PAIR, D)
    frame = pl.read_parquet(path)
    assert frame.schema == rows_frame([]).schema
    assert frame.height == 24 and sorted(set(frame["ts"])) == [_at(_h(hour), 120) for hour in BOUNDARY_HOURS]
    small, large = _row(frame, _h(16), "bid"), _row(frame, _h(16), "bid", 1)
    outcome = ("filled", "time_to_fill_s", "fill_price", "box_end_touch_price", "box_end_touch_qty")
    assert [small[name] for name in outcome] == [True, 180.0, 1000.0, 1001.0, 1.0]
    assert (large["filled"], large["met_qty"]) == (False, pytest.approx(0.2))
    assert _sidecar(path).read_text() == f"{dataset_hash(frame)}  02.parquet\n"
    assert _record(out, PAIR) == {
        "params": _params(D, END),
        "code_ref": _code_ref(),
        "days": {"2026-09-02": _entry(), "2026-09-03": _entry()},
    }
    assert not (_record_path(out, PAIR).parent / fills.RUN_RECORD).exists()
    assert _record(out, OTHER)["days"]["2026-09-02"] == _entry(
        hours=0, posts=0, hours_unanchored=_isos(D, BOUNDARY_HOURS), trades_absent=_isos(D, BOUNDARY_HOURS)
    )
    assert not _day_path(out, OTHER, D).exists()


def test_an_episode_is_seeded_from_the_panels_state_of_the_hour_before(tmp_path):
    primary, _, panel = _roots(tmp_path)
    boundary = _h(12)
    _book_hour(primary, PAIR, boundary, snapshot=False)
    _seed(panel, PAIR, boundary - timedelta(hours=1), bids=HEALED_BIDS)
    out = tmp_path / "out"
    counts = _produce(primary, panel, out, since=boundary, until=_h(13))
    assert _without_seconds(counts) == _counts(hours=1, posts=4, trades_absent=1)
    assert _record(out, PAIR)["days"]["2026-09-02"]["hours_unanchored"] == []
    bid = _row(pl.read_parquet(_day_path(out, PAIR, D)), boundary, "bid")
    assert (bid["price"], bid["mid_at_post"]) == (1000.25, 1000.625)


def test_without_a_state_an_episode_opens_on_its_snapshot_or_is_counted_unanchored(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, _h(0))
    _book_hour(primary, PAIR, _h(4), snapshot=False)
    out = tmp_path / "out"
    counts = _produce(primary, panel, out, until=_h(8))
    assert _without_seconds(counts) == _counts(hours=1, posts=4, hours_unanchored=1, trades_absent=2)
    assert _record(out, PAIR)["days"]["2026-09-02"] == _entry(
        hours=1, posts=4, hours_unanchored=[_h(4).isoformat()], trades_absent=_isos(D, (0, 4))
    )
    assert set(pl.read_parquet(_day_path(out, PAIR, D))["ts"]) == {_at(_h(0), 120)}


def test_an_unreadable_or_bookless_state_refuses_the_run_by_name(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _archive(primary, PAIR, D, (0, 4), prints=())
    state = _state_path(panel, PAIR, _h(3))
    state.parent.mkdir(parents=True)
    state.symlink_to(state.name)
    looped = tmp_path / "looped"
    with pytest.raises(PanelError, match=re.escape(str(state))):
        _produce(primary, panel, looped)
    assert not list(looped.rglob("*.parquet"))
    state.unlink()
    state.write_text("{}")
    bookless = tmp_path / "bookless"
    with pytest.raises(PanelError, match=re.escape(str(state))):
        _produce(primary, panel, bookless)
    assert not list(bookless.rglob("*.parquet"))


def test_a_root_the_run_cannot_read_as_a_directory_refuses_it(tmp_path, monkeypatch):
    primary, overlay, panel = _roots(tmp_path)
    _archive(primary, PAIR, D, (0,))
    missing = tmp_path / "missing"
    cases = {"primary": (missing, overlay, panel), "overlay": (primary, missing, panel), "panel": (primary, overlay, missing)}
    for name, (primary_root, reconciled_root, panel_root) in cases.items():
        out = tmp_path / f"out-{name}"
        with pytest.raises(PanelError, match=re.escape(str(missing))):
            produce_ladder_pair(primary_root, reconciled_root, panel_root, out, PAIR, since=D, until=NEXT)
        assert not list(out.rglob("*.parquet"))

    listdir = os.listdir

    def unscannable(path="."):
        if os.fspath(path) == os.fspath(overlay):
            raise OSError(errno.EIO, os.strerror(errno.EIO), os.fspath(path))
        return listdir(path)

    monkeypatch.setattr(os, "listdir", unscannable)
    out = tmp_path / "out-unscannable"
    with pytest.raises(PanelError, match=re.escape(str(overlay))):
        produce_ladder_pair(primary, overlay, panel, out, PAIR, since=D, until=NEXT)
    assert not list(out.rglob("*.parquet"))


def test_an_absent_book_hour_is_a_skipped_episode_counted(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    skipped, replayed = _h(8), (0, 4, 12, 16, 20)
    _archive(primary, PAIR, D, replayed, prints=())
    _trades_hour(overlay, PAIR, skipped, [FILL])
    out = tmp_path / "out"
    counts = _produce(primary, panel, out, overlay=overlay)
    assert _without_seconds(counts) == _counts(hours=5, posts=20, hours_absent=1, trades_absent=5)
    assert _record(out, PAIR)["days"]["2026-09-02"] == _entry(
        hours=5,
        posts=20,
        hours_absent=[skipped.isoformat()],
        trades_absent=_isos(D, replayed),
        trades_reconciled=[skipped.isoformat()],
    )
    assert _at(skipped, 120) not in set(pl.read_parquet(_day_path(out, PAIR, D))["ts"])
    _manifest(out, primary, overlay)
    assert read_manifest(out / "manifest.json").provenance["pairs"][PAIR]["2026-09-02"]["hours_absent"] == [skipped.isoformat()]


def test_a_boundary_hour_without_its_trades_hour_is_replayed_with_no_print_and_listed(tmp_path):
    primary, _, panel = _roots(tmp_path)
    quiet = _h(4)
    _archive(primary, PAIR, D, (0,))
    _book_hour(primary, PAIR, quiet)
    out = tmp_path / "out"
    assert _without_seconds(_produce(primary, panel, out, until=_h(8))) == _counts(hours=2, posts=8, trades_absent=1)
    assert _record(out, PAIR)["days"]["2026-09-02"]["trades_absent"] == [quiet.isoformat()]
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert _row(frame, _h(0), "bid")["filled"]
    replayed = frame.filter(pl.col("ts") == _at(quiet, 120))
    assert replayed.height == 4 and not replayed["filled"].any()


def test_a_run_resumes_after_its_newest_day_file(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    written = _day_path(out, PAIR, D)
    before = (written.stat().st_ino, written.read_bytes())
    resumed = _day_path(out, PAIR, NEXT)
    resumed.unlink()
    _sidecar(resumed).unlink()
    panel = tmp_path / "panel"
    panel.mkdir()
    assert _without_seconds(_produce(primary, panel, out, until=END, overlay=overlay)) == _counts()
    assert (written.stat().st_ino, written.read_bytes()) == before
    assert pl.read_parquet(resumed).height == 24


def test_boundary_hours_outside_since_until_are_not_read(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _archive(primary, PAIR, D, prints=())
    _book_hour(primary, PAIR, NEXT)
    out = tmp_path / "out"
    assert _without_seconds(_produce(primary, panel, out, since=_h(4))) == _counts(hours=5, posts=20, trades_absent=5)
    assert list(_record(out, PAIR)["days"]) == ["2026-09-02"]
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert (frame["ts"].min(), frame["ts"].max()) == (_at(_h(4), 120), _at(_h(20), 120))


def test_a_run_into_a_set_holding_a_manifest_is_refused_and_left_unmarked(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    _manifest(out, primary, overlay)
    panel = tmp_path / "panel"
    panel.mkdir()
    with pytest.raises(PanelError, match=re.escape(f"{PAIR}: {out / 'manifest.json'} is present")):
        _produce(primary, panel, out, until=END, overlay=overlay)
    assert not (out / fills.PRODUCING_MARKER).exists()


def test_a_run_marks_the_set_and_the_manifest_lifts_the_mark(produced, tmp_path):
    primary, overlay, source, _ = produced
    assert (source / fills.PRODUCING_MARKER).is_file()
    out = _copy(source, tmp_path / "out")
    assert _manifest(out, primary, overlay) == out / "manifest.json"
    assert not (out / fills.PRODUCING_MARKER).exists()
    manifest = read_manifest(out / "manifest.json")
    assert sorted(manifest.series) == ["BTC/EUR/2026/09/02.parquet", "BTC/EUR/2026/09/03.parquet", "ETH/EUR/2026/09/03.parquet"]
    provenance = manifest.provenance
    assert (provenance["producer"], provenance["code_ref"], provenance["params"]) == (
        "zcrypto panel ladder",
        _code_ref(),
        _params(D, END),
    )
    assert provenance["pairs"] == {pair: _record(out, pair)["days"] for pair in (PAIR, OTHER)}


def test_each_day_a_run_lands_refreshes_the_mark(tmp_path, monkeypatch):
    primary, _, panel = _roots(tmp_path)
    _archive(primary, PAIR, D, (0,))
    _archive(primary, PAIR, NEXT, (0,))
    touch, touched = Path.touch, []

    def counted(self, *args, **kwargs):
        if self.name == fills.PRODUCING_MARKER:
            touched.append(self)
        return touch(self, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", counted)
    out = tmp_path / "out"
    _produce(primary, panel, out, until=_h(1, NEXT))
    assert len(_record(out, PAIR)["days"]) == 2
    assert len(touched) == 3


def test_a_record_with_other_params_is_refused_by_name(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    panel = tmp_path / "panel"
    panel.mkdir()
    record = _record_path(out, PAIR)
    code = _record(out, PAIR)["code_ref"]
    _edit_record(out, PAIR, lambda held: held.update(code_ref="0000000"))
    with pytest.raises(PanelError, match=re.escape(str(record)) + f".*0000000.*{code}"):
        _produce(primary, panel, out, until=END, overlay=overlay)
    _edit_record(out, PAIR, lambda held: held.update(code_ref=code))
    with pytest.raises(PanelError, match=re.escape(str(record)) + ".*'depth': 100.*'depth': 50"):
        _produce(primary, panel, out, until=END, overlay=overlay, depth=50)
    _edit_record(out, PAIR, lambda held: held["params"].update(box_s=600))
    with pytest.raises(PanelError, match=re.escape(str(record)) + ".*'box_s': 600.*'box_s': 900"):
        _produce(primary, panel, out, until=END, overlay=overlay)
    record.unlink()
    with pytest.raises(PanelError, match=re.escape(f"and no {RUN_RECORD}")):
        _produce(primary, panel, out, until=END, overlay=overlay)


def test_the_manifest_refuses_a_day_whose_counts_do_not_add_up(produced, tmp_path):
    primary, overlay, source, _ = produced
    partial = tmp_path / "partial"
    partial.mkdir()
    partial_primary, _, partial_panel = _roots(partial)
    _archive(partial_primary, PAIR, D, (4, 8))
    _produce(partial_primary, partial_panel, partial / "out", since=_h(4), until=_h(12))
    _manifest(partial / "out", partial_primary, None)
    skipped = _copy(source, tmp_path / "skipped")
    _edit_record(skipped, PAIR, lambda record: record["days"]["2026-09-02"].update(skipped_stale=4))
    unanchored = _copy(source, tmp_path / "unanchored")
    _edit_record(unanchored, PAIR, lambda record: record["days"]["2026-09-03"]["hours_unanchored"].append(_h(1, NEXT).isoformat()))
    for out, day in ((skipped, "2026-09-02"), (unanchored, "2026-09-03")):
        with pytest.raises(PanelError, match=re.escape(f"{PAIR} {day}:")):
            _manifest(out, primary, overlay)
        assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_day_whose_rows_differ_from_its_record(produced, tmp_path):
    primary, overlay, source, _ = produced
    short = _copy(source, tmp_path / "short")
    path = _day_path(short, PAIR, D)
    frame = pl.read_parquet(path).head(23)
    frame.write_parquet(path)
    _sidecar(path).write_text(f"{dataset_hash(frame)}  02.parquet\n")
    unlisted = _copy(source, tmp_path / "unlisted")
    stray = _day_path(unlisted, PAIR, D + timedelta(days=5))
    shutil.copy(_day_path(unlisted, PAIR, D), stray)
    shutil.copy(_sidecar(_day_path(unlisted, PAIR, D)), _sidecar(stray))
    fileless = _copy(source, tmp_path / "fileless")
    _day_path(fileless, PAIR, NEXT).unlink()
    _sidecar(_day_path(fileless, PAIR, NEXT)).unlink()
    for out, day in ((short, "2026-09-02"), (unlisted, "2026-09-07"), (fileless, "2026-09-03")):
        with pytest.raises(PanelError, match=re.escape(f"{PAIR} {day}:")):
            _manifest(out, primary, overlay)
        assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_sidecar_that_disagrees(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    sidecar = _sidecar(_day_path(out, PAIR, D))
    sidecar.write_text(f"{'0' * 64}  02.parquet\n")
    with pytest.raises(PanelError, match=re.escape(str(sidecar))):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_records_that_disagree_across_pairs(produced, tmp_path):
    primary, overlay, source, _ = produced
    edits = {"code": lambda record: record.update(code_ref="0000000"), "depth": lambda record: record["params"].update(depth=50)}
    for name, edit in edits.items():
        out = _copy(source, tmp_path / name)
        _edit_record(out, OTHER, edit)
        with pytest.raises(PanelError) as refused:
            _manifest(out, primary, overlay)
        assert str(_record_path(out, PAIR)) in str(refused.value) and str(_record_path(out, OTHER)) in str(refused.value)
        assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_boundary_hour_listed_from_another_root_than_the_runs(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    early, healed = _h(4), _h(12)
    _archive(primary, PAIR, D, (4, 12))
    _book_hour(overlay, PAIR, healed, bids=HEALED_BIDS)
    _trades_hour(overlay, PAIR, healed, [FILL, (301, "sell", 1000.25, 0.25)])
    aside = tmp_path / "aside"

    def run(out: Path, without: Path | None = None) -> None:
        if without is not None:
            without.rename(aside)
        _produce(primary, panel, out, since=early, until=_h(13), overlay=overlay)
        if without is not None:
            aside.rename(without)

    whole = tmp_path / "whole"
    run(whole)
    _manifest(whole, primary, overlay)
    entry = _record(whole, PAIR)["days"]["2026-09-02"]
    assert (entry["book_reconciled"], entry["trades_reconciled"]) == ([healed.isoformat()], [healed.isoformat()])

    for kind in ("book", "trades"):
        out = tmp_path / f"{kind}-aside"
        run(out, without=_segment(overlay, PAIR, kind, healed).parent)
        with pytest.raises(
            PanelError, match=re.escape(f"{PAIR} {kind} {healed.isoformat()}: run primary, second listing reconciled")
        ):
            _manifest(out, primary, overlay)
        assert not (out / "manifest.json").exists()

    out = tmp_path / "book-absent"
    run(out, without=_segment(primary, PAIR, "book", early))
    with pytest.raises(PanelError, match=re.escape(f"{PAIR} book {early.isoformat()}: run absent, second listing primary")):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_run_stopped_before_a_listed_boundary_hours_day_landed(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    _edit_record(out, PAIR, lambda record: record["days"].pop("2026-09-03"))
    _day_path(out, PAIR, NEXT).unlink()
    _sidecar(_day_path(out, PAIR, NEXT)).unlink()
    with pytest.raises(PanelError) as refused:
        _manifest(out, primary, overlay)
    for kind in ("book", "trades"):
        for hour in BOUNDARY_HOURS:
            assert f"{PAIR} {kind} {_h(hour, NEXT).isoformat()}: run no entry, second listing primary" in str(refused.value)
    assert not (out / "manifest.json").exists()


def test_the_manifest_compares_no_hour_off_the_boundaries(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    _archive(primary, PAIR, D, prints=())
    for root in (primary, overlay):
        _book_hour(root, PAIR, _h(1))
    _book_hour(overlay, PAIR, _h(4), bids=HEALED_BIDS)
    out = tmp_path / "out"
    _produce(primary, panel, out, overlay=overlay)
    record = _record(out, PAIR)
    assert record["days"]["2026-09-02"]["book_reconciled"] == [_h(4).isoformat()]
    assert _row(pl.read_parquet(_day_path(out, PAIR, D)), _h(4), "bid")["price"] == 1000.25
    assert fills._relisting_disputes({PAIR: record}, primary, overlay) == [
        f"{PAIR} book {_h(1).isoformat()}: run primary, second listing reconciled"
    ]
    _manifest(out, primary, overlay)
    assert (out / "manifest.json").is_file()


def test_the_ladder_commands_exit_codes_and_json_line(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    _archive(primary, PAIR, D, (0,))
    out = tmp_path / "data" / "l2-ladder-set"
    roots = [str(primary), str(out), "--reconciled-root", str(overlay), "--panel-root", str(panel)]
    hours = ["--since", "2026-09-02T00:00:00Z", "--until", "2026-09-02T04:00:00Z"]
    result = runner.invoke(app, ["panel", "ladder", *roots, "--pair", PAIR, *hours])
    assert result.exit_code == 0, result.output
    [line] = [line for line in result.output.splitlines() if line.startswith("{")]
    assert _without_seconds(json.loads(line)) == _counts(hours=1, posts=4)
    assert _row(pl.read_parquet(_day_path(out, PAIR, D)), _h(0), "bid")["filled"]
    manifest = runner.invoke(app, ["panel", "ladder-manifest", str(primary), str(out), "--reconciled-root", str(overlay)])
    assert manifest.exit_code == 0, manifest.output
    assert manifest.output.splitlines()[-1] == str(out / "manifest.json")
    assert runner.invoke(app, ["panel", "ladder", *roots, "--pair", PAIR, *hours]).exit_code == 1
    assert runner.invoke(app, ["panel", "ladder-manifest", str(tmp_path / "missing"), str(out)]).exit_code == 1
    assert runner.invoke(app, ["panel", "ladder", *roots, "--pair", "BTC/USD", *hours]).exit_code == 2
