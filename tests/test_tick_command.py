"""The `zcrypto tick materialize` surface (spec 00087 D6)."""

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick import command

runner = CliRunner()


def _day(root: Path, pair: str, day: date, *, start_id: int, hours: list[int] | None = None) -> int:
    """Same contract as tests/test_tick_sweep.py's `_day`: sequential ids, chained explicitly."""
    next_id = start_id
    for h in range(24) if hours is None else hours:
        hour = datetime(day.year, day.month, day.day, h, tzinfo=UTC)
        d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(
            {
                "ts": [hour],
                "symbol": [pair],
                "side": ["buy"],
                "price": [10.0],
                "qty": [1.0],
                "ord_type": ["limit"],
                "trade_id": [next_id],
            },
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")
        next_id += 1
    return next_id


def test_materialize_publishes_and_reports(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)  # long past -- settled against the real clock
    _day(src, "BTC/EUR", date(2020, 1, 2), start_id=nid, hours=[0])  # successor: the live-edge day never publishes
    res = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])
    assert res.exit_code == 0, res.output
    assert "days_written=1" in res.output
    assert (out / "BTC" / "EUR" / "2020" / "01" / "01.parquet").exists()


def test_a_failed_day_exits_nonzero_and_names_the_pair(tmp_path):
    """A sweep that isolated an error must not report success -- the exit code is what a timer sees.
    A CORRUPT segment is the error case; an incomplete tape is days_unhealed and exits 0."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    _day(src, "BTC/EUR", date(2020, 1, 2), start_id=nid, hours=[0])
    (src / "BTC" / "EUR" / "trades" / "2020" / "01" / "01" / "07.parquet").write_bytes(b"not a parquet")
    res = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])
    assert res.exit_code != 0
    assert "BTC/EUR" in res.output


def test_rescan_days_reaches_the_sweep(tmp_path):
    """A flag accepted and ignored is a lie in --help. The first run sweeps the WHOLE archive (no
    watermark -- bounding it would strand the backlog silently); with a watermark, a healed old day
    is retried only inside the window, and widening the window reaches it."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    nid = _day(src, "BTC/EUR", date(2020, 1, 5), start_id=nid)
    nid = _day(src, "BTC/EUR", date(2020, 1, 9), start_id=nid)
    _day(src, "BTC/EUR", date(2020, 1, 10), start_id=nid, hours=[0])
    hole = src / "BTC" / "EUR" / "trades" / "2020" / "01" / "05" / "07.parquet"
    kept = hole.read_bytes()
    hole.write_bytes(b"not a parquet")

    first = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])
    assert first.exit_code != 0  # the corrupt day is an error...
    assert (out / "BTC" / "EUR" / "2020" / "01" / "01.parquet").exists(), "...and the backlog day still published"

    hole.write_bytes(kept)
    tight = runner.invoke(
        app,
        ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r"), "--rescan-days", "0"],
    )
    assert tight.exit_code == 0
    assert not (out / "BTC" / "EUR" / "2020" / "01" / "05.parquet").exists()

    wide = runner.invoke(
        app,
        ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r"), "--rescan-days", "9"],
    )
    assert wide.exit_code == 0
    assert (out / "BTC" / "EUR" / "2020" / "01" / "05.parquet").exists()


def test_settle_hours_is_overridable(tmp_path):
    """An operator must be able to widen the gate; the default is TAPE_SETTLE."""
    src, out = tmp_path / "src", tmp_path / "out"
    _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    res = runner.invoke(
        app,
        ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r"), "--settle-hours", "999999"],
    )
    assert res.exit_code == 0
    assert "days_unsettled=1" in res.output
    assert not list(out.rglob("*.parquet"))


def test_a_refusal_reaches_the_operator_as_a_refusal_not_a_traceback(tmp_path, monkeypatch):
    """`_watermark`'s refusal is a decision: one logged ERROR naming the path, exit 1, and no traceback."""
    src, out = tmp_path / "src", tmp_path / "out"
    _day(src, "BTC/EUR", date(2020, 1, 1), start_id=0)
    stray = out / "BTC" / "EUR" / "nope" / "01" / "01.parquet"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"a path publish_day cannot have written")

    # NOT caplog: cli/logging/config.py sets `propagate = False` on the `zcrypto` logger and
    # cli/__main__.py calls configure() on every CliRunner invocation, so the record reaches pytest's
    # root handler only sometimes -- measured empty whenever this test runs on its own.
    errors: list[str] = []
    monkeypatch.setattr(command.logger, "error", lambda fmt, *a, **k: errors.append(fmt % a if a else fmt))

    res = runner.invoke(app, ["tick", "materialize", str(src), str(out), "--reconciled-root", str(tmp_path / "r")])

    assert res.exit_code == 1, res.output
    # `cli/__main__.py::run` -- the wrapper that logs "unhandled exception -- aborting" and lets the
    # traceback print -- is not in CliRunner's path, so what separates a refusal from a fault here is
    # which exception leaves the command: SystemExit out of `typer.Exit`, never the TickError itself.
    assert isinstance(res.exception, SystemExit), res.exception
    assert len(errors) == 1, errors
    assert str(stray) in errors[0], errors[0]
    assert "published path is not <YYYY>/<MM>/<DD>.parquet" in errors[0], errors[0]
