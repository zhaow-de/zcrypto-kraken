"""The producer half of `cli/panel/fills.py` and its two `zcrypto panel` commands (spec 00151 D2), each case on a known
answer over a synthetic capture tree in the segments' layout and a panel root holding `write_state` seeds."""

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
from cli.capture.book import OrderBook
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA
from cli.data.manifest import read_manifest
from cli.ohlc.dataset import dataset_hash
from cli.panel.errors import PanelError
from cli.panel.fills import RUN_RECORD, produce_pair, rows_frame, write_fills_manifest
from cli.panel.materialize import _code_ref, _state_path, write_state
from cli.registry.observed import ObservedReader

PAIR = "BTC/EUR"
OTHER = "ETH/EUR"
D = datetime(2026, 9, 2, tzinfo=UTC)
LATE = D + timedelta(hours=23)
NEXT = D + timedelta(days=1)
END = NEXT + timedelta(hours=1)
BIDS = [(1000.0, 1.0), (999.0, 1.0), (990.0, 1.0)]
ASKS = [(1001.0, 1.0), (1002.0, 1.0), (1010.0, 1.0)]
# A best bid a quarter above BIDS', so a book read from the other source moves `mid_at_post` off 1000.625.
HEALED_BIDS = [(1000.25, 1.0), (999.0, 1.0), (990.0, 1.0)]
WRITTEN_AT = "2026-10-28T00:00:00+00:00"
runner = CliRunner()


def _at(hour: datetime, seconds: float) -> datetime:
    return hour + timedelta(seconds=seconds)


def _isos(start: datetime, count: int) -> list[str]:
    return [(start + timedelta(hours=k)).isoformat() for k in range(count)]


def _segment(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"


def _write(path: Path, frame: pl.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def _book_hour(root: Path, pair: str, hour: datetime, *, bids=BIDS, asks=ASKS, snapshot=True, messages=(), last=3600) -> None:
    """`pair`'s book hour under `root`: a snapshot of `bids` and `asks` at :00 unless the hour continues the one before,
    the deepest bid restated every 5 s before the `last` second, and the planted `messages` -- `(offset, bids, asks)`, a
    level of qty 0 removing it."""
    planned = [(0.0, "snapshot", bids, asks)] if snapshot else []
    planned += [(float(s), "update", [min(bids)], []) for s in range(5 if snapshot else 0, last, 5)]
    planned += [(float(offset), "update", b, a) for offset, b, a in messages]
    planned.sort(key=lambda message: message[0])
    rows = [
        {"ts": _at(hour, offset), "symbol": pair, "type": kind, "side": side, "price": price, "qty": qty, "checksum": n}
        for n, (offset, kind, b, a) in enumerate(planned)
        for side, levels in (("bid", b), ("ask", a))
        for price, qty in levels
    ]
    _write(_segment(root, pair, "book", hour), pl.DataFrame(rows, schema=BOOK_SCHEMA))


def _trades_hour(root: Path, pair: str, hour: datetime, prints: list[tuple]) -> None:
    rows = [
        {"ts": _at(hour, offset), "symbol": pair, "side": side, "price": price, "qty": qty, "ord_type": "limit", "trade_id": n}
        for n, (offset, side, price, qty) in enumerate(prints)
    ]
    _write(_segment(root, pair, "trades", hour), pl.DataFrame(rows, schema=TRADE_SCHEMA))


def _seed(panel: Path, pair: str, hour: datetime, *, bids=BIDS, asks=ASKS) -> None:
    """The panel's state at the end of `hour`, its last message a second before the next hour."""
    book = OrderBook(pair, 100)
    levels = {
        side: [{"price": price, "qty": qty} for price, qty in side_levels] for side, side_levels in (("bids", bids), ("asks", asks))
    }
    book.ingest_snapshot({**levels, "checksum": 0})
    write_state(panel, pair, hour, book, last_msg_ts=_at(hour, 3599))


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    roots = tuple(tmp_path / name for name in ("primary", "overlay", "panel"))
    for root in roots:
        root.mkdir()
    return roots


def _produce(primary: Path, panel: Path, out: Path, pair: str = PAIR, *, since=LATE, until=NEXT, overlay=None, depth=100) -> dict:
    return produce_pair(primary, overlay, panel, out, pair, since=since, until=until, depth=depth)


def _copy(source: Path, out: Path) -> Path:
    shutil.copytree(source, out)
    return out


def _day_path(out: Path, pair: str, day: datetime) -> Path:
    base, quote = pair.split("/")
    return out / base / quote / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"


def _sidecar(path: Path) -> Path:
    return path.with_name(f"{path.name}.sha256")


def _record_path(out: Path, pair: str) -> Path:
    base, quote = pair.split("/")
    return out / base / quote / RUN_RECORD


def _record(out: Path, pair: str) -> dict:
    return json.loads(_record_path(out, pair).read_text())


def _edit_record(out: Path, pair: str, edit) -> None:
    record = _record(out, pair)
    edit(record)
    _record_path(out, pair).write_text(json.dumps(record))


def _row(frame: pl.DataFrame, hour: datetime, seconds: int, side: str, size: int = 0) -> dict:
    [row] = frame.filter((pl.col("ts") == _at(hour, seconds)) & (pl.col("side") == side) & (pl.col("size") == size)).to_dicts()
    return row


def _params(since: datetime, until: datetime) -> dict:
    return {
        "grid_s": 15,
        "horizon_s": 900,
        "cancel_after_s": 5,
        "stale_s": 30,
        "size_rungs": [0, 1],
        "mid_offsets_s": [60, 900, 3600],
        "depth": 100,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


def _entry(**overrides) -> dict:
    lists = ("hours_unanchored", "hours_absent", "trades_absent", "book_reconciled", "trades_reconciled")
    return {"hours": 1, "posts": 960, "skipped_no_quote": 0, "skipped_stale": 0, **{name: [] for name in lists}, **overrides}


def _counts(**overrides) -> dict:
    absent = {"hours_unanchored": 0, "hours_absent": 0, "trades_absent": 0}
    return {"hours": 1, **absent, "posts": 960, "skipped_no_quote": 0, "skipped_stale": 0, "days_written": 1, **overrides}


def _without_seconds(counts: dict) -> dict:
    assert list(counts)[-1] == "seconds" and isinstance(counts["seconds"], float) and counts["seconds"] >= 0
    return {name: value for name, value in counts.items() if name != "seconds"}


def _manifest(out: Path, primary: Path, overlay: Path | None) -> Path:
    return write_fills_manifest(out, primary, overlay, written_at=WRITTEN_AT)


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    """Two pairs across D's last hour and D+1's first, read through an empty overlay. BTC/EUR: 23Z opens with a snapshot
    and a sell print at :07 fills its first bid; 00Z opens with an update -- the book threaded across the day boundary --
    fills the bids still resting at 1000.0 with a sell print at :10 and removes the best ask at :30:00. ETH/EUR: 23Z
    opens with an update and has no seed, so it is unanchored; 00Z opens with a snapshot; no trades file."""
    tmp = tmp_path_factory.mktemp("produced")
    primary, overlay, panel = _roots(tmp)
    _book_hour(primary, PAIR, LATE)
    _trades_hour(primary, PAIR, LATE, [(7, "sell", 1000.0, 1.2)])
    _book_hour(primary, PAIR, NEXT, snapshot=False, messages=[(1800, [], [(1001.0, 0.0)])])
    _trades_hour(primary, PAIR, NEXT, [(10, "sell", 1000.0, 1.2)])
    _book_hour(primary, OTHER, LATE, snapshot=False)
    _book_hour(primary, OTHER, NEXT)
    out = tmp / "l2-fills-test"
    counts = {pair: _produce(primary, panel, out, pair, until=END, overlay=overlay) for pair in (PAIR, OTHER)}
    return primary, overlay, out, counts


def test_produce_pair_writes_a_day_file_with_the_schema_a_sidecar_and_its_record(produced):
    _, _, out, counts = produced
    assert _without_seconds(counts[PAIR]) == _counts(hours=2, posts=1920, days_written=2)
    assert _without_seconds(counts[OTHER]) == _counts(hours_unanchored=1, trades_absent=2)
    path = _day_path(out, PAIR, D)
    frame = pl.read_parquet(path)
    assert frame.schema == rows_frame([]).schema
    assert frame.height == 960
    first = _row(frame, LATE, 0, "bid")
    assert (first["filled"], first["time_to_fill_s"], first["fill_price"]) == (True, 7.0, 1000.0)
    assert _sidecar(path).read_text() == f"{dataset_hash(frame)}  02.parquet\n"
    assert _record(out, PAIR) == {
        "params": _params(LATE, END),
        "code_ref": _code_ref(),
        "days": {"2026-09-02": _entry(), "2026-09-03": _entry()},
    }


def test_the_first_hour_is_seeded_from_the_panels_state_of_the_hour_before(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE, snapshot=False)
    _trades_hour(primary, PAIR, LATE, [(40, "buy", 1001.0, 0.2)])
    _seed(panel, PAIR, LATE - timedelta(hours=1))
    out = tmp_path / "out"
    assert _without_seconds(_produce(primary, panel, out)) == _counts()
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert frame.height == 960 and frame["ts"].min() == LATE
    assert _row(frame, LATE, 0, "bid")["mid_at_post"] == 1000.5


def test_without_a_seed_the_hours_before_the_first_snapshot_are_skipped_and_counted(tmp_path):
    primary, _, panel = _roots(tmp_path)
    since = LATE - timedelta(hours=2)
    _book_hour(primary, PAIR, since, snapshot=False)
    _book_hour(primary, PAIR, since + timedelta(hours=1), snapshot=False)
    _book_hour(primary, PAIR, LATE)
    out = tmp_path / "out"
    assert _without_seconds(_produce(primary, panel, out, since=since)) == _counts(hours_unanchored=2, trades_absent=3)
    assert _record(out, PAIR)["days"]["2026-09-02"] == _entry(hours_unanchored=_isos(since, 2), trades_absent=_isos(since, 3))
    assert pl.read_parquet(_day_path(out, PAIR, D))["ts"].min() == LATE


def test_an_unreadable_seed_refuses_the_run_and_writes_no_day(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE)
    state = _state_path(panel, PAIR, LATE - timedelta(hours=1))
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


def test_the_book_threads_across_consecutive_hours(produced):
    _, _, out, _ = produced
    last = _row(pl.read_parquet(_day_path(out, PAIR, D)), LATE, 3585, "bid")
    assert (last["filled"], last["time_to_fill_s"], last["cancelled_s"]) == (True, 25.0, None)


def test_a_book_hour_without_its_trades_hour_is_posted_on_and_fills_nothing(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE, snapshot=False)
    _seed(panel, PAIR, LATE - timedelta(hours=1))
    out = tmp_path / "out"
    assert _without_seconds(_produce(primary, panel, out)) == _counts(trades_absent=1)
    assert _record(out, PAIR)["days"]["2026-09-02"] == _entry(trades_absent=[LATE.isoformat()])
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert frame.height == 960 and not frame["filled"].any()


def test_a_days_last_hour_lands_in_its_own_file_with_mids_from_the_next_day(produced):
    _, _, out, _ = produced
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert frame.height == 960
    assert (frame["ts"].min(), frame["ts"].max()) == (LATE, _at(LATE, 3585))
    last = _row(frame, LATE, 3585, "bid")
    assert (last["mid_at_post"], last["mid_at_post_plus_3600s"]) == (1000.5, 1001.0)
    assert pl.read_parquet(_day_path(out, PAIR, NEXT))["ts"].min() == NEXT


def test_a_day_waits_for_the_mids_of_its_last_posts_a_stale_next_hour_defers(tmp_path):
    primary, _, panel = _roots(tmp_path)
    after = NEXT + timedelta(hours=1)
    _book_hour(primary, PAIR, LATE)
    _book_hour(primary, PAIR, NEXT, snapshot=False, last=3500)
    _book_hour(primary, PAIR, after, snapshot=False)
    out = tmp_path / "out"
    _produce(primary, panel, out, until=after + timedelta(hours=1))
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert frame.height == 960
    assert _row(frame, LATE, 3585, "bid")["mid_at_post_plus_3600s"] == 1000.5


def test_the_data_end_flushes_the_last_day_with_its_unreached_mids_null(produced):
    _, _, out, _ = produced
    frame = pl.read_parquet(_day_path(out, PAIR, NEXT))
    assert frame.height == 960
    assert frame["mid_at_post_plus_3600s"].null_count() == 960
    assert frame.filter(pl.col("ts") < _at(NEXT, 2700))["mid_at_post_plus_900s"].null_count() == 0
    assert frame.filter(pl.col("ts") >= _at(NEXT, 2700))["mid_at_post_plus_900s"].null_count() == 240
    open_at_end = _row(frame, NEXT, 3585, "bid")
    censored = ("filled", "time_to_fill_s", "cancelled_s", "fill_price")
    assert [open_at_end[name] for name in censored] == [False, None, None, None]


def test_a_gap_flushes_the_carried_orders_and_counts_the_absent_hours(tmp_path):
    primary, _, panel = _roots(tmp_path)
    before, missing = LATE - timedelta(hours=2), LATE - timedelta(hours=1)
    _book_hour(primary, PAIR, before)
    _book_hour(primary, PAIR, LATE, bids=HEALED_BIDS, snapshot=False)
    _seed(panel, PAIR, missing, bids=HEALED_BIDS)
    out = tmp_path / "out"
    counts = _produce(primary, panel, out, since=before)
    assert _without_seconds(counts) == _counts(hours=2, hours_absent=1, trades_absent=3, posts=1920)
    assert _record(out, PAIR)["days"]["2026-09-02"]["hours_absent"] == [missing.isoformat()]
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    flushed = frame.filter(pl.col("ts") < missing)
    assert flushed.height == 960 and flushed["mid_at_post_plus_3600s"].null_count() == 960
    assert _row(frame, LATE, 0, "bid")["mid_at_post"] == 1000.625

    quiet_day = tmp_path / "primary-quiet-day"
    after = NEXT + timedelta(days=1)
    _book_hour(quiet_day, PAIR, LATE)
    _book_hour(quiet_day, PAIR, after)
    empty_panel = tmp_path / "panel-empty"
    empty_panel.mkdir()
    out = tmp_path / "out-quiet-day"
    counts = _produce(quiet_day, empty_panel, out, until=after + timedelta(hours=1))
    assert _without_seconds(counts) == _counts(hours=2, hours_absent=24, trades_absent=26, posts=1920, days_written=2)
    assert _record(out, PAIR)["days"]["2026-09-03"] == _entry(
        hours=0, posts=0, hours_absent=_isos(NEXT, 24), trades_absent=_isos(NEXT, 24)
    )


def test_a_present_day_file_is_not_rewritten_and_the_run_resumes_after_it(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    written = _day_path(out, PAIR, D)
    before = (written.stat().st_ino, written.read_bytes())
    resumed = _day_path(out, PAIR, NEXT)
    resumed.unlink()
    _sidecar(resumed).unlink()
    panel = tmp_path / "panel"
    panel.mkdir()
    _seed(panel, PAIR, LATE, bids=HEALED_BIDS)
    assert _without_seconds(_produce(primary, panel, out, until=END, overlay=overlay)) == _counts()
    assert (written.stat().st_ino, written.read_bytes()) == before
    assert _row(pl.read_parquet(resumed), NEXT, 0, "bid")["mid_at_post"] == 1000.625


def test_hours_outside_since_until_are_not_read(tmp_path):
    primary, _, panel = _roots(tmp_path)
    for hour in (LATE - timedelta(hours=1), LATE, NEXT):
        _book_hour(primary, PAIR, hour)
    out = tmp_path / "out"
    assert _without_seconds(_produce(primary, panel, out)) == _counts(trades_absent=1)
    assert list(_record(out, PAIR)["days"]) == ["2026-09-02"]
    frame = pl.read_parquet(_day_path(out, PAIR, D))
    assert (frame["ts"].min(), frame["ts"].max()) == (LATE, _at(LATE, 3585))


def test_a_run_whose_params_or_code_differ_from_the_record_is_refused(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    panel = tmp_path / "panel"
    panel.mkdir()
    code = _record(out, PAIR)["code_ref"]
    _edit_record(out, PAIR, lambda record: record.update(code_ref="0000000"))
    with pytest.raises(PanelError, match=f"0000000.*{code}"):
        _produce(primary, panel, out, until=END, overlay=overlay)
    _edit_record(out, PAIR, lambda record: record.update(code_ref=code))
    with pytest.raises(PanelError, match="'depth': 100.*'depth': 50"):
        _produce(primary, panel, out, until=END, overlay=overlay, depth=50)
    _record_path(out, PAIR).unlink()
    with pytest.raises(PanelError, match=re.escape(RUN_RECORD)):
        _produce(primary, panel, out, until=END, overlay=overlay)


def test_an_unreadable_book_or_trades_hour_refuses_the_run_naming_it(tmp_path):
    for kind in ("book", "trades"):
        (tmp_path / kind).mkdir()
        primary, _, panel = _roots(tmp_path / kind)
        _book_hour(primary, PAIR, LATE)
        _trades_hour(primary, PAIR, LATE, [(7, "sell", 1000.0, 1.2)])
        path = _segment(primary, PAIR, kind, LATE)
        path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])
        with pytest.raises(PanelError, match=re.escape(f"{PAIR} {LATE.isoformat()}: {path} cannot be read")):
            _produce(primary, panel, tmp_path / kind / "out")


def test_a_run_record_it_cannot_read_refuses_the_run_and_the_manifest(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    record = _record_path(out, PAIR)
    record.unlink()
    record.symlink_to(record.name)
    with pytest.raises(PanelError, match=re.escape(f"{record} cannot be read")):
        _manifest(out, primary, overlay)
    panel = tmp_path / "panel"
    panel.mkdir()
    with pytest.raises(PanelError, match=re.escape(f"{record} cannot be read")):
        _produce(primary, panel, out, until=END, overlay=overlay)


def test_a_run_record_or_sidecar_it_cannot_parse_refuses_by_name(produced, tmp_path, monkeypatch):
    primary, overlay, source, _ = produced
    day = D.date().isoformat()

    def entry_edit(edit):
        return lambda record: (edit(record["days"][day]), record)[1]

    spoils = (
        ("a-list", lambda record: [], "not an object"),
        ("no-params", lambda record: {**record, "params": None}, "lacks its params"),
        ("no-code-ref", lambda record: {**record, "code_ref": None}, "lacks its params, code_ref or days"),
        ("no-days", lambda record: {**record, "days": None}, "lacks its params, code_ref or days"),
        ("a-bad-since", lambda record: (record["params"].update(since="soon"), record)[1], "ValueError"),
        ("no-since", lambda record: (record["params"].pop("since"), record)[1], "KeyError"),
        ("a-number-since", lambda record: (record["params"].update(since=5), record)[1], "TypeError"),
        (
            "a-naive-since",
            lambda record: (record["params"].update(since="2026-09-02T23:00:00"), record)[1],
            "its since carries no UTC offset",
        ),
        ("no-posts", entry_edit(lambda entry: entry.pop("posts")), f"the day {day}'s entry is not four integer counts"),
        ("a-text-count", entry_edit(lambda entry: entry.update(posts="960")), f"the day {day}'s entry is not four integer counts"),
        (
            "a-text-list",
            entry_edit(lambda entry: entry.update(hours_absent="22")),
            f"the day {day}'s entry is not four integer counts",
        ),
        (
            "a-number-in-a-list",
            entry_edit(lambda entry: entry.update(hours_absent=[5])),
            f"the day {day}'s entry is not four integer counts",
        ),
        (
            "a-number-entry",
            lambda record: (record["days"].update({day: 5}), record)[1],
            f"the day {day}'s entry is not four integer counts",
        ),
        ("a-bad-day", lambda record: (record["days"].update({"not-a-day": record["days"].pop(day)}), record)[1], "ValueError"),
    )
    for name, spoil, fault in spoils:
        out = _copy(source, tmp_path / name)
        record = _record_path(out, PAIR)
        record.write_text(json.dumps(spoil(json.loads(record.read_text()))))
        with pytest.raises(PanelError, match=re.escape(f"{record} is not a run record: ") + ".*" + re.escape(fault)):
            _manifest(out, primary, overlay)
    out = _copy(source, tmp_path / "not-json")
    record = _record_path(out, PAIR)
    record.write_text("{not json")
    with pytest.raises(PanelError, match=re.escape(f"{record} is not a run record: Expecting")):
        _manifest(out, primary, overlay)
    out = _copy(source, tmp_path / "too-deep")
    record = _record_path(out, PAIR)

    def too_deep(text):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array from a unicode string")

    with monkeypatch.context() as patch:
        patch.setattr("cli.panel.fills.json.loads", too_deep)
        with pytest.raises(PanelError, match=re.escape(f"{record} is not a run record: maximum recursion depth exceeded")):
            _manifest(out, primary, overlay)
    panel = tmp_path / "panel"
    panel.mkdir()
    with pytest.raises(PanelError, match=re.escape(f"{_record_path(tmp_path / 'a-list', PAIR)} is not a run record")):
        _produce(primary, panel, tmp_path / "a-list", until=END, overlay=overlay)
    out = _copy(source, tmp_path / "sidecar")
    sidecar = _sidecar(_day_path(out, PAIR, D))
    sidecar.write_bytes(b"\xff\xfe")
    with pytest.raises(PanelError, match=re.escape(f"the sidecar {sidecar} cannot be read")):
        _manifest(out, primary, overlay)


def test_an_out_root_or_a_day_it_cannot_write_refuses_the_run(tmp_path, monkeypatch):
    primary, _, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE)
    blocked = tmp_path / "blocked"
    blocked.write_text("")
    with pytest.raises(PanelError, match=re.escape(f"the out root {blocked} cannot be created")):
        _produce(primary, panel, blocked)

    def eio(source, destination):
        raise OSError(errno.EIO, "Input/output error", str(destination))

    monkeypatch.setattr("cli.panel.fills._replace_durably", eio)
    out = tmp_path / "out"
    with pytest.raises(PanelError, match=re.escape(f"{PAIR} {D.date()}: the day cannot be written under {out / 'BTC' / 'EUR'}")):
        _produce(primary, panel, out)


def test_the_manifest_refuses_a_manifest_it_cannot_write(produced, tmp_path, monkeypatch):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")

    def eio(source, destination):
        raise OSError(errno.EIO, "Input/output error", str(destination))

    monkeypatch.setattr("cli.panel.fills._replace_durably", eio)
    with pytest.raises(PanelError, match=re.escape(f"{out / 'manifest.json'} cannot be written")):
        _manifest(out, primary, overlay)


def test_a_pair_left_with_no_day_file_is_refused(tmp_path):
    primary, _, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE, snapshot=False)
    with pytest.raises(PanelError, match=re.escape(f"{OTHER}: the run left no day file")):
        _produce(primary, panel, tmp_path / "not-held", OTHER)
    with pytest.raises(PanelError, match=re.escape(f"{PAIR}: the run left no day file")):
        _produce(primary, panel, tmp_path / "unanchored")


def test_the_manifest_is_conformant_and_carries_the_span_the_code_and_each_days_record(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "l2-fills-test")
    assert _manifest(out, primary, overlay) == out / "manifest.json"
    manifest = read_manifest(out / "manifest.json")
    sidecars = {
        path.relative_to(out).as_posix().removesuffix(".sha256"): path.read_text().split()[0] for path in out.rglob("*.sha256")
    }
    assert sorted(sidecars) == ["BTC/EUR/2026/09/02.parquet", "BTC/EUR/2026/09/03.parquet", "ETH/EUR/2026/09/03.parquet"]
    assert manifest.hash_by_path() == sidecars
    relpath = "BTC/EUR/2026/09/02.parquet"
    assert ObservedReader(tmp_path).read_series(out.name, relpath).equals(pl.read_parquet(out / relpath))
    provenance = manifest.provenance
    assert (provenance["producer"], provenance["code_ref"]) == ("zcrypto panel fills", _code_ref())
    assert provenance["params"] == _params(LATE, END)
    assert provenance["pairs"] == {pair: _record(out, pair)["days"] for pair in (PAIR, OTHER)}
    assert provenance["pairs"][OTHER]["2026-09-02"]["hours_unanchored"] == [LATE.isoformat()]


def test_the_manifest_refuses_a_sidecar_that_disagrees(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    sidecar = _sidecar(_day_path(out, PAIR, D))
    sidecar.write_text(f"{'0' * 64}  02.parquet\n")
    with pytest.raises(PanelError, match=re.escape(str(sidecar))):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_day_file_or_sidecar_it_cannot_read(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "truncated")
    path = _day_path(out, PAIR, D)
    path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])
    with pytest.raises(PanelError, match=re.escape(f"{PAIR} {D.date()}: {path} cannot be read")):
        _manifest(out, primary, overlay)
    out = _copy(source, tmp_path / "no-sidecar")
    sidecar = _sidecar(_day_path(out, PAIR, D))
    sidecar.unlink()
    with pytest.raises(PanelError, match=re.escape(f"the sidecar {sidecar} cannot be read")):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_day_whose_rows_differ_from_its_record(produced, tmp_path):
    primary, overlay, source, _ = produced
    short = _copy(source, tmp_path / "short")
    path = _day_path(short, PAIR, D)
    frame = pl.read_parquet(path).head(959)
    frame.write_parquet(path)
    _sidecar(path).write_text(f"{dataset_hash(frame)}  02.parquet\n")
    unlisted = _copy(source, tmp_path / "unlisted")
    stray = _day_path(unlisted, PAIR, D + timedelta(days=5))
    shutil.copy(_day_path(unlisted, PAIR, D), stray)
    shutil.copy(_sidecar(_day_path(unlisted, PAIR, D)), _sidecar(stray))
    recordless = _copy(source, tmp_path / "recordless")
    _record_path(recordless, PAIR).unlink()
    fileless = _copy(source, tmp_path / "fileless")
    _day_path(fileless, PAIR, NEXT).unlink()
    _sidecar(_day_path(fileless, PAIR, NEXT)).unlink()
    for out, day in ((short, "2026-09-02"), (unlisted, "2026-09-07"), (recordless, "2026-09-02"), (fileless, "2026-09-03")):
        with pytest.raises(PanelError, match=re.escape(f"{PAIR} {day}:")):
            _manifest(out, primary, overlay)
        assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_a_day_whose_hours_do_not_add_up(produced, tmp_path):
    primary, overlay, source, _ = produced
    skipped = _copy(source, tmp_path / "skipped")
    _edit_record(skipped, PAIR, lambda record: record["days"]["2026-09-02"].update(skipped_no_quote=1))
    unanchored = _copy(source, tmp_path / "unanchored")
    _edit_record(unanchored, PAIR, lambda record: record["days"]["2026-09-03"]["hours_unanchored"].append(_isos(NEXT, 6)[-1]))
    for out, day in ((skipped, "2026-09-02"), (unanchored, "2026-09-03")):
        with pytest.raises(PanelError, match=re.escape(f"{PAIR} {day}:")):
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


def test_the_manifest_refuses_a_tree_with_no_day_file(tmp_path):
    primary, overlay, _ = _roots(tmp_path)
    out = tmp_path / "out"
    _record_path(out, PAIR).parent.mkdir(parents=True)
    _record_path(out, PAIR).write_text(json.dumps({"params": _params(LATE, NEXT), "code_ref": "0000000", "days": {}}))
    with pytest.raises(PanelError, match="no day file"):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_an_hour_absent_at_the_run_and_present_at_the_relisting(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    for hour in (LATE, NEXT):
        _book_hour(primary, PAIR, hour)
        _trades_hour(primary, PAIR, hour, [(7, "sell", 1000.0, 0.5)])
    aside = tmp_path / "aside.parquet"

    def run_without(segment: Path, out: Path) -> None:
        segment.rename(aside)
        _produce(primary, panel, out, until=END, overlay=overlay)
        aside.rename(segment)

    book = _segment(primary, PAIR, "book", NEXT)
    out = tmp_path / "book-absent"
    run_without(book, out)
    with pytest.raises(PanelError, match=re.escape(f"{PAIR} book {NEXT.isoformat()}: run absent, second listing primary")):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()

    trades = _segment(primary, PAIR, "trades", LATE)
    out = tmp_path / "trades-absent"
    run_without(trades, out)
    with pytest.raises(PanelError, match=re.escape(f"{PAIR} trades {LATE.isoformat()}: run absent, second listing primary")):
        _manifest(out, primary, overlay)
    assert not (out / "manifest.json").exists()

    trades.rename(aside)
    _manifest(out, primary, overlay)
    assert read_manifest(out / "manifest.json").provenance["pairs"][PAIR]["2026-09-02"]["trades_absent"] == [LATE.isoformat()]

    (out / "manifest.json").unlink()
    _edit_record(out, PAIR, lambda record: record["days"].pop("2026-09-03"))
    _day_path(out, PAIR, NEXT).unlink()
    _sidecar(_day_path(out, PAIR, NEXT)).unlink()
    with pytest.raises(PanelError) as refused:
        _manifest(out, primary, overlay)
    for kind in ("book", "trades"):
        assert f"{PAIR} {kind} {NEXT.isoformat()}: run no entry, second listing primary" in str(refused.value)
    assert not (out / "manifest.json").exists()


def test_the_manifest_refuses_an_hour_listed_from_another_root_than_the_runs(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE)
    _trades_hour(primary, PAIR, LATE, [(7, "sell", 1000.0, 0.5)])
    _book_hour(overlay, PAIR, LATE, bids=HEALED_BIDS)
    _trades_hour(overlay, PAIR, LATE, [(7, "sell", 1000.0, 0.5), (8, "sell", 1000.25, 0.25)])
    aside = tmp_path / "aside"

    def run(out: Path, without: Path | None = None) -> None:
        if without is not None:
            without.rename(aside)
        _produce(primary, panel, out, overlay=overlay)
        if without is not None:
            aside.rename(without)

    whole = tmp_path / "whole"
    run(whole)
    _manifest(whole, primary, overlay)
    entry = _record(whole, PAIR)["days"]["2026-09-02"]
    assert (entry["book_reconciled"], entry["trades_reconciled"]) == ([LATE.isoformat()], [LATE.isoformat()])

    for kind in ("book", "trades"):
        out = tmp_path / f"{kind}-aside"
        run(out, without=_segment(overlay, PAIR, kind, LATE).parent)
        with pytest.raises(
            PanelError, match=re.escape(f"{PAIR} {kind} {LATE.isoformat()}: run primary, second listing reconciled")
        ):
            _manifest(out, primary, overlay)
        assert not (out / "manifest.json").exists()

    out = tmp_path / "overlay-gone"
    run(out)
    overlay.rename(tmp_path / "overlay-aside")
    with pytest.raises(PanelError, match=re.escape(str(overlay))) as refused:
        _manifest(out, primary, overlay)
    assert LATE.isoformat() not in str(refused.value)
    assert not (out / "manifest.json").exists()


def test_a_root_the_run_cannot_read_as_a_directory_refuses_it(tmp_path, monkeypatch):
    primary, overlay, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE)
    missing = tmp_path / "missing"
    cases = {"primary": (missing, overlay, panel), "overlay": (primary, missing, panel), "panel": (primary, overlay, missing)}
    for name, (primary_root, reconciled_root, panel_root) in cases.items():
        out = tmp_path / f"out-{name}"
        with pytest.raises(PanelError, match=re.escape(str(missing))):
            produce_pair(primary_root, reconciled_root, panel_root, out, PAIR, since=LATE, until=NEXT)
        assert not list(out.rglob("*.parquet"))

    listdir = os.listdir

    def unscannable(path="."):
        if os.fspath(path) == os.fspath(overlay):
            raise OSError(errno.EIO, os.strerror(errno.EIO), os.fspath(path))
        return listdir(path)

    monkeypatch.setattr(os, "listdir", unscannable)
    out = tmp_path / "out-unscannable"
    with pytest.raises(PanelError, match=re.escape(str(overlay))):
        produce_pair(primary, overlay, panel, out, PAIR, since=LATE, until=NEXT)
    assert not list(out.rglob("*.parquet"))


def test_the_fills_command_reads_the_healed_overlay_and_prints_the_counts(tmp_path):
    primary, overlay, panel = _roots(tmp_path)
    _book_hour(primary, PAIR, LATE)
    _trades_hour(primary, PAIR, LATE, [(3, "sell", 1000.25, 0.5)])
    _book_hour(overlay, PAIR, LATE, bids=HEALED_BIDS)
    _trades_hour(overlay, PAIR, LATE, [(3, "sell", 1000.25, 0.5), (7, "sell", 1000.25, 0.7)])
    out = tmp_path / "data" / "l2-fills-set"
    args = ["panel", "fills", str(primary), str(out), "--reconciled-root", str(overlay), "--panel-root", str(panel)]
    args += ["--pair", PAIR, "--since", "2026-09-02T23:00:00Z", "--until", "2026-09-03T00:00:00Z"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    [line] = [line for line in result.output.splitlines() if line.startswith("{")]
    assert _without_seconds(json.loads(line)) == _counts()
    first = _row(pl.read_parquet(_day_path(out, PAIR, D)), LATE, 0, "bid")
    assert (first["mid_at_post"], first["filled"], first["time_to_fill_s"]) == (1000.625, True, 7.0)


def test_the_fills_command_refuses_a_bad_pair_or_hour_by_its_own_flag(tmp_path):
    primary, overlay, panel = _roots(tmp_path)

    def invoke(*, pair=PAIR, since="2026-08-01T00:00:00Z", until="2026-10-26T00:00:00Z"):
        args = [
            "panel",
            "fills",
            str(primary),
            str(tmp_path / "out"),
            "--reconciled-root",
            str(overlay),
            "--panel-root",
            str(panel),
        ]
        return runner.invoke(app, [*args, "--pair", pair, "--since", since, "--until", until])

    for pair in ("A/B/EUR", "BTC/USD"):
        assert invoke(pair=pair).exit_code == 2
    refusals = {"--since": invoke(since="2026-08-01T00:30:00Z"), "--until": invoke(until="2026-10-26T00:30:00Z")}
    for flag, result in refusals.items():
        squashed = re.sub(r"[\s│]+", "", re.sub(r"\x1b\[[0-9;]*m", "", result.output))
        assert result.exit_code == 2
        assert flag in squashed and ({"--since", "--until"} - {flag}).pop() not in squashed


def test_the_fills_manifest_command_writes_the_manifest(produced, tmp_path):
    primary, overlay, source, _ = produced
    out = _copy(source, tmp_path / "out")
    result = runner.invoke(app, ["panel", "fills-manifest", str(primary), str(out), "--reconciled-root", str(overlay)])
    assert result.exit_code == 0, result.output
    manifest = read_manifest(out / "manifest.json")
    assert sorted(manifest.series) == ["BTC/EUR/2026/09/02.parquet", "BTC/EUR/2026/09/03.parquet", "ETH/EUR/2026/09/03.parquet"]
