"""Settle gate, watermark, heal gate and sweep isolation (spec 00087 D2/D3/D4)."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick.materialize import materialize


def _day(root: Path, pair: str, day: date, *, start_id: int, hours: list[int] | None = None) -> int:
    """One trade per present hour, trade_ids SEQUENTIAL from `start_id`; returns the next unused id.

    Ids advance only when a trade prints -- they are unrelated to the calendar. A fixture that keys
    ids off the hour number fabricates an id hole at every quiet hour and every skipped day, so the
    heal gate refuses healthy days for a reason that reads exactly like a code bug. Tests therefore
    CHAIN start_id explicitly.
    """
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


def _after(day: date, *, hours: float) -> datetime:
    """`hours` past the END of `day`."""
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1, hours=hours)


# Every fixture below gives the day under test a SUCCESSOR segment: the heal gate refuses the
# archive's newest day (live edge -- its tail id is an endpoint, not proof), and in production a
# settled day always has successors because capture keeps writing. A one-day fixture would fail
# for the wrong reason.


def test_an_unsettled_day_is_deferred_then_taken_once_settled(tmp_path):
    """D3's pre-filter: 26h past day end is the boundary, and the watermark must not move early."""
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    nid = _day(src, "BTC/EUR", d, start_id=0)
    _day(src, "BTC/EUR", d + timedelta(days=1), start_id=nid, hours=[0])

    early = materialize(src, tmp_path / "r", out, now=_after(d, hours=25))
    assert early.days_written == 0 and early.days_unsettled == 2
    assert not list(out.rglob("*.parquet"))

    late = materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    assert late.days_written == 1 and late.days_unsettled == 1  # the successor day is still young
    assert (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()


def test_a_published_day_is_skipped_not_rewritten(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    nid = _day(src, "BTC/EUR", d, start_id=0)
    _day(src, "BTC/EUR", d + timedelta(days=1), start_id=nid, hours=[0])
    materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    final = out / "BTC" / "EUR" / "2026" / "08" / "01.parquet"
    before = final.stat().st_mtime_ns
    again = materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    assert again.days_written == 0 and again.days_skipped == 1
    assert final.stat().st_mtime_ns == before


def test_a_sidecar_is_written_and_matches_the_final(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    nid = _day(src, "BTC/EUR", d, start_id=0)
    _day(src, "BTC/EUR", d + timedelta(days=1), start_id=nid, hours=[0])
    materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    final = out / "BTC" / "EUR" / "2026" / "08" / "01.parquet"
    sidecar = final.with_suffix(".parquet.sha256")
    assert sidecar.exists()
    assert sidecar.read_text().split()[0] == hashlib.sha256(final.read_bytes()).hexdigest()


def test_a_corrupt_segment_is_isolated_and_the_sweep_continues(tmp_path):
    """D4: one broken day must not cost the others. `errors` is for the EXCEPTIONAL -- a corrupt
    segment -- because an incomplete tape is `days_unhealed`, not an error."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = 0
    for d in (date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)):
        nid = _day(src, "BTC/EUR", d, start_id=nid)
    (src / "BTC" / "EUR" / "trades" / "2026" / "08" / "01" / "07.parquet").write_bytes(b"not a parquet")

    res = materialize(src, tmp_path / "r", out, now=_after(date(2026, 8, 3), hours=27))
    assert len(res.errors) == 1 and res.errors[0][0] == "BTC/EUR"
    assert res.days_written == 1  # 08-02; 08-01 errored, 08-03 is the live edge
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()
    assert (out / "BTC" / "EUR" / "2026" / "08" / "02.parquet").exists()


def test_a_quiet_hour_does_not_block_a_day(tmp_path):
    """The withdrawn 24-hour rule would refuse this forever. An absent hour file means QUIET -- no
    trade printed, so no id was consumed -- and the id stream runs contiguous straight across it."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2026, 8, 1), start_id=0)
    nid = _day(src, "BTC/EUR", date(2026, 8, 2), start_id=nid, hours=[h for h in range(24) if h != 13])
    nid = _day(src, "BTC/EUR", date(2026, 8, 3), start_id=nid)
    _day(src, "BTC/EUR", date(2026, 8, 4), start_id=nid, hours=[0])  # successor for 08-03's gate

    res = materialize(src, tmp_path / "r", out, now=_after(date(2026, 8, 3), hours=27))
    assert res.days_unhealed == 0, res
    assert res.days_written == 3
    assert (out / "BTC" / "EUR" / "2026" / "08" / "02.parquet").exists()


_EPOCH = date(2020, 1, 1)


def _holed_day(root: Path, pair: str, day: date, *, drop_hour: int | None = None) -> None:
    """A day of calendar-keyed monotone ids (24 per day), optionally with one hour's trade MISSING
    -- file and id together, a real hole.

    Unlike `_day`, ids here are keyed off the calendar so that dropping an hour leaves a genuine gap
    in the sequence. Days written with this helper must be CALENDAR-CONSECUTIVE, or the keying
    itself fabricates holes between them.
    """
    base = (day - _EPOCH).days * 24
    for h in range(24):
        if drop_hour is not None and h == drop_hour:
            continue
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
                "trade_id": [base + h],
            },
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")


def test_a_day_with_a_trade_id_hole_is_refused_then_published_once_healed(tmp_path):
    """D3, the load-bearing gate. The clock cannot see this: the day is long settled and still
    un-healed, which is exactly the state a wall-clock proxy publishes permanently."""
    src, out, overlay = tmp_path / "src", tmp_path / "out", tmp_path / "r"
    d = date(2026, 8, 1)
    _holed_day(src, "BTC/EUR", d, drop_hour=7)
    _holed_day(src, "BTC/EUR", date(2026, 8, 2))  # a successor, so d is not at the live edge

    res = materialize(src, overlay, out, now=_after(date(2026, 8, 2), hours=99))
    assert res.days_unhealed >= 1
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()

    _holed_day(src, "BTC/EUR", d)  # the healer fills the hole
    materialize(src, overlay, out, now=_after(date(2026, 8, 2), hours=99))
    assert (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists()


def test_a_hole_on_the_day_boundary_is_caught_by_the_neighbour_extension(tmp_path):
    """`detect` treats the last observed id as an endpoint, never a gap -- so over one day a hole at
    the day's TAIL reads clean and a truncated day publishes short, permanently. The extension into
    the next present segment is what makes it visible."""
    src, out, overlay = tmp_path / "src", tmp_path / "out", tmp_path / "r"
    _holed_day(src, "BTC/EUR", date(2026, 8, 1))  # complete
    _holed_day(src, "BTC/EUR", date(2026, 8, 2), drop_hour=23)  # its LAST trade missing
    _holed_day(src, "BTC/EUR", date(2026, 8, 3))  # the extension target
    res = materialize(src, overlay, out, now=_after(date(2026, 8, 3), hours=27))
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "02.parquet").exists(), "a tail hole must be seen"
    assert (out / "BTC" / "EUR" / "2026" / "08" / "01.parquet").exists(), "its intact neighbour still publishes"


def test_a_healed_day_inside_the_rescan_window_is_picked_up_later(tmp_path):
    """D4's trailing re-scan, proven in BOTH directions: a healed day outside the window stays
    unpublished, and widening the window picks it up."""
    src, out = tmp_path / "src", tmp_path / "out"
    nid = _day(src, "BTC/EUR", date(2026, 8, 1), start_id=0)
    nid = _day(src, "BTC/EUR", date(2026, 8, 5), start_id=nid)
    nid = _day(src, "BTC/EUR", date(2026, 8, 9), start_id=nid)
    _day(src, "BTC/EUR", date(2026, 8, 10), start_id=nid, hours=[0])
    hole = src / "BTC" / "EUR" / "trades" / "2026" / "08" / "05" / "07.parquet"
    kept = hole.read_bytes()
    hole.write_bytes(b"not a parquet")

    now = _after(date(2026, 8, 9), hours=27)
    first = materialize(src, tmp_path / "r", out, now=now)
    assert first.days_written == 2 and len(first.errors) == 1  # 08-01 and 08-09 publish; 08-05 errors

    hole.write_bytes(kept)  # a late overlay mint replaces the corrupt segment
    tight = materialize(src, tmp_path / "r", out, now=now, rescan_days=0)
    assert not (out / "BTC" / "EUR" / "2026" / "08" / "05.parquet").exists()
    assert tight.days_gap == 1  # the healed-but-outside-window day is a VISIBLE gap, not a vanished one

    wide = materialize(src, tmp_path / "r", out, now=now, rescan_days=9)
    assert wide.days_written == 1
    assert (out / "BTC" / "EUR" / "2026" / "08" / "05.parquet").exists()


def test_every_pair_in_the_archive_is_swept(tmp_path):
    """D4: pairs are discovered, never hardcoded -- the capture set has already changed once."""
    src, out = tmp_path / "src", tmp_path / "out"
    d = date(2026, 8, 1)
    for pair in ("BTC/EUR", "ETH/BTC"):
        nid = _day(src, pair, d, start_id=0)
        _day(src, pair, d + timedelta(days=1), start_id=nid, hours=[0])
    res = materialize(src, tmp_path / "r", out, now=_after(d, hours=27))
    assert res.days_written == 2
    assert (out / "ETH" / "BTC" / "2026" / "08" / "01.parquet").exists()
