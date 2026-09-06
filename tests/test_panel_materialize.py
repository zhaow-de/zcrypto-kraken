"""TDD for `cli/panel/materialize.py` -- the hour materializer + watermarked sweep (spec 00052
Task 2: D3/D4/D5/D6).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from cli.capture.book import OrderBook
from cli.capture.segment_writer import BOOK_SCHEMA, verify_manifest
from cli.panel.errors import PanelError
from cli.panel.materialize import (
    load_state,
    materialize,
    materialize_hour,
    panel_watermark,
    write_hour,
    write_meta,
    write_state,
)

H = datetime(2026, 7, 16, 9, tzinfo=UTC)


def _explode(pair: str, hour: datetime, messages: list[dict]) -> pl.DataFrame:
    """Fan each WS-shaped message out into one row per price level, mirroring the capture writer's
    fan-out (tests/test_archive_replay.py::_explode)."""
    rows = []
    for msg in messages:
        ts = hour + timedelta(seconds=msg["offset"])
        for side, levels in (("bid", msg.get("bids", [])), ("ask", msg.get("asks", []))):
            for price, qty in levels:
                rows.append(
                    {
                        "ts": ts,
                        "symbol": pair,
                        "type": msg["type"],
                        "side": side,
                        "price": price,
                        "qty": qty,
                        "checksum": msg.get("checksum", 1),
                    }
                )
    return pl.DataFrame(rows, schema=BOOK_SCHEMA)


def _book(root: Path, pair: str, hour: datetime, frame: pl.DataFrame) -> Path:
    """Write a committed canonical final (+ manifest sidecar) at the archive layout (mirrors
    tests/test_archive_replay.py::_book)."""
    base, quote = pair.split("/")
    p = root / base / quote / "book" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(p, compression="zstd")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_name(p.name + ".sha256").write_text(f"{digest}  {p.name}\n")
    return p


def _messages() -> list[dict]:
    """Snapshot at :00, then updates at :00.5, :02.2, :02.7 -- the last two share a second-window
    (2, 3] and so land TOGETHER on the boundary at :03 (`ts <= T`: the smallest integer boundary
    T >= 2.7 is 3), giving that row `updates=2` while :02 itself is a quiet second (`updates=0`)."""
    return [
        {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
        {"offset": 0.5, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 2},
        {"offset": 2.2, "type": "update", "bids": [(99.0, 3.0)], "asks": [], "checksum": 3},
        {"offset": 2.7, "type": "update", "bids": [], "asks": [(102.0, 4.0)], "checksum": 4},
    ]


def _materialize(root: Path, pair: str, hour: datetime, *, depth: int = 10) -> pl.DataFrame:
    path = _book(root, pair, hour, _explode(pair, hour, _messages()))
    frame, _book_out, _lm = materialize_hour(path, pair, hour, depth=depth)
    return frame


# --- materialize_hour: the 1s-grid walk --------------------------------------------------------------


def test_materialize_hour_samples_the_1s_grid_from_the_snapshot(tmp_path: Path) -> None:
    frame = _materialize(tmp_path, "BTC/EUR", H)

    assert frame.height == 3600  # every second boundary sampled; the book never re-empties
    assert frame["ts"].to_list()[:4] == [H + timedelta(seconds=i) for i in range(4)]
    assert frame["ts"][-1] == H + timedelta(seconds=3599)

    rows = frame.rows(named=True)
    assert rows[0]["updates"] == 1  # the snapshot itself, at boundary 0
    assert rows[1]["updates"] == 1  # the :00.5 update
    assert rows[2]["updates"] == 0  # quiet: (1, 2] owns nothing -- :02.2/:02.7 are still ahead
    assert rows[3]["updates"] == 2  # (2, 3] owns BOTH :02.2 and :02.7 together

    assert rows[0]["mid"] == 100.5
    assert rows[1]["depth_qty_bid_l5"] == 2.0  # one bid level so far (qty updated 1.0 -> 2.0)
    assert rows[3]["depth_qty_bid_l5"] == 5.0  # 100@2.0 + 99@3.0, the new level landed
    assert rows[3]["depth_qty_ask_l5"] == 5.0  # 101@1.0 + 102@4.0

    # quiet tail: state and updates=0 carry unchanged all the way to the hour's last second
    assert rows[-1]["updates"] == 0
    assert rows[-1]["depth_qty_bid_l5"] == 5.0
    assert rows[-1]["depth_qty_ask_l5"] == 5.0


def test_materialize_hour_emits_no_rows_before_the_snapshot_lands(tmp_path: Path) -> None:
    # The snapshot itself lands at :01.5 -- the first boundary at-or-after it is :02; :00 and :01 have
    # an empty book on both sides (`sample_row` -> None), so the general rule alone drops them, with
    # no special-casing for "before the snapshot".
    messages = [{"offset": 1.5, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1}]
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    frame, _book_out, _lm = materialize_hour(path, "BTC/EUR", H, depth=10)

    assert frame.height == 3598  # 3600 minus the two pre-snapshot boundaries
    assert frame["ts"][0] == H + timedelta(seconds=2)


def test_materialize_hour_without_a_leading_snapshot_raises(tmp_path: Path) -> None:
    messages = _messages()[1:]  # opens with an update, never a snapshot
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    with pytest.raises(PanelError):
        materialize_hour(path, "BTC/EUR", H, depth=10)


# --- materialize_hour: state threading across hours (spec 00052 D3 correction) ------------------------


def test_materialize_hour_with_carried_book_samples_from_second_0(tmp_path: Path) -> None:
    # H opens with a snapshot: bid 100.0, ask 101.0. H+1 opens with only an update touching the bid
    # side -- the ask side (101.0) never appears in H+1's own messages, so it can be present in
    # H+1's rows ONLY via the carried book. That is the hand-checked, carry-dependent value.
    h_messages = [{"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1}]
    path_h = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, h_messages))
    frame_h, book_h, _lm = materialize_hour(path_h, "BTC/EUR", H, depth=10)
    assert frame_h.height == 3600  # both sides quotable from second 0 onward

    h1 = H + timedelta(hours=1)
    h1_messages = [{"offset": 0, "type": "update", "bids": [(99.0, 5.0)], "asks": [], "checksum": 2}]
    path_h1 = _book(tmp_path, "BTC/EUR", h1, _explode("BTC/EUR", h1, h1_messages))

    frame_h1, book_h1, _lm = materialize_hour(path_h1, "BTC/EUR", h1, depth=10, book=book_h)

    assert frame_h1.height == 3600  # the ask side is quotable ONLY because of the carried book
    first = frame_h1.row(0, named=True)
    assert first["mid"] == 100.5  # (100 carried bid + 101 carried ask) / 2 -- the ask is carry-only
    assert first["depth_qty_bid_l5"] == 6.0  # 100@1.0 (carried) + 99@5.0 (this hour's own update)
    assert book_h1.asks == {Decimal("101.0"): Decimal("1.0")}  # carried ask level survives untouched


def test_materialize_hour_snapshot_resets_a_stale_carried_book(tmp_path: Path) -> None:
    # A poisoned carry-in (garbage levels no real predecessor hour could have produced) must not
    # leak into a snapshot-opening hour -- the snapshot always builds a FRESH book.
    poisoned = OrderBook("BTC/EUR", 10)
    poisoned.bids = {Decimal("1.0"): Decimal("999.0")}
    poisoned.asks = {Decimal("2.0"): Decimal("999.0")}
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))

    frame, book_out, _lm = materialize_hour(path, "BTC/EUR", H, depth=10, book=poisoned)

    assert Decimal("1.0") not in book_out.bids  # the poisoned carry-in did not survive the reset
    assert Decimal("2.0") not in book_out.asks
    first = frame.row(0, named=True)
    assert first["mid"] == 100.5  # the snapshot's own book (100/101), not the poisoned one


# --- write_hour: atomic + manifest --------------------------------------------------------------------


def test_write_hour_is_atomic_and_manifest_verifies(tmp_path: Path) -> None:
    frame = _materialize(tmp_path / "primary", "BTC/EUR", H)
    panel_root = tmp_path / "panel"

    final = write_hour(panel_root, "BTC/EUR", H, frame)

    assert final == panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert final.exists()
    assert verify_manifest(final) is True
    assert not list(panel_root.rglob("*.tmp"))  # no tmp left behind after a clean write
    assert pl.read_parquet(final).height == frame.height


def test_write_hour_is_undisturbed_by_a_stale_tmp_from_a_killed_run(tmp_path: Path) -> None:
    # Post-review-I1 semantics: tmps are PID-suffixed, so a killed run's tmp is an INERT ORPHAN --
    # a fresh write never opens it (no shared-tmp tear), publishes a valid final regardless, and the
    # orphan is ignored by the FINAL_NAME-strict watermark. It may linger; that is harmless in a
    # regenerable tree, and cleaning foreign tmps would be exactly the cross-process touching I1 bans.
    frame = _materialize(tmp_path / "primary", "BTC/EUR", H)
    panel_root = tmp_path / "panel"
    d = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16"
    d.mkdir(parents=True)
    stale = d / "09.parquet.12345.tmp"
    stale.write_bytes(b"garbage from a killed run")

    final = write_hour(panel_root, "BTC/EUR", H, frame)

    assert verify_manifest(final) is True  # ours, untouched by the garbage
    assert stale.read_bytes() == b"garbage from a killed run"  # foreign tmp not touched
    assert pl.read_parquet(final).height == frame.height
    assert panel_watermark(panel_root, "BTC/EUR") is not None  # orphan doesn't confuse the watermark


# --- write_state / load_state: the O(1)-resume sidecar (spec 00052 D3) --------------------------------


def test_write_state_and_load_state_round_trip_decimals_exactly(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"
    book = OrderBook("BTC/EUR", 10)
    book.bids = {Decimal("100.00000000"): Decimal("1.50000000")}
    book.asks = {Decimal("101.10000000"): Decimal("2.25000000")}

    path = write_state(panel_root, "BTC/EUR", H, book, last_msg_ts=None)

    assert path == panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.state.json"
    raw = json.loads(path.read_text())
    assert raw == {
        "bids": {"100.00000000": "1.50000000"},
        "asks": {"101.10000000": "2.25000000"},
        "last_msg_ts": None,  # T0104: present, null when the caller passed no time
    }
    assert not list(panel_root.rglob("*.tmp"))  # no tmp left behind after a clean write

    loaded, _loaded_ts = load_state(panel_root, "BTC/EUR", H, depth=10)

    assert loaded is not None
    assert loaded.bids == book.bids
    assert loaded.asks == book.asks
    # exact Decimal round trip: trailing zeros preserved, not float-truncated
    assert str(next(iter(loaded.bids.values()))) == "1.50000000"


def test_load_state_returns_none_for_missing_or_corrupt_file(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"
    assert load_state(panel_root, "BTC/EUR", H, depth=10) == (None, None)  # nothing written yet -- missing

    path = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json{{{")

    assert load_state(panel_root, "BTC/EUR", H, depth=10) == (None, None)  # corrupt -- never raises


# --- panel_watermark: round trip -----------------------------------------------------------------------


def test_panel_watermark_round_trips(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"
    assert panel_watermark(panel_root, "BTC/EUR") is None  # nothing written yet

    write_hour(panel_root, "BTC/EUR", H, _materialize(tmp_path / "primary", "BTC/EUR", H))
    assert panel_watermark(panel_root, "BTC/EUR") == H

    later = H + timedelta(hours=2)
    write_hour(panel_root, "BTC/EUR", later, _materialize(tmp_path / "primary", "BTC/EUR", later))
    assert panel_watermark(panel_root, "BTC/EUR") == later  # the newest hour, not merely the latest write


def test_panel_watermark_ignores_state_sidecars(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"
    write_hour(panel_root, "BTC/EUR", H, _materialize(tmp_path / "primary", "BTC/EUR", H))

    # A stray state sidecar with no matching parquet final (e.g. an hour that materialized state but
    # never reached write_hour) must not be mistaken for a later panel hour.
    stray_book = OrderBook("BTC/EUR", 10)
    write_state(panel_root, "BTC/EUR", H + timedelta(hours=5), stray_book, last_msg_ts=None)

    assert panel_watermark(panel_root, "BTC/EUR") == H


def test_panel_watermark_ignores_an_oversized_year_directory(tmp_path: Path) -> None:
    # `int(year)` is arbitrary precision, but `datetime()` narrows the year to a C int -- so a
    # `<YYYY>` directory above 2**31-1 raises OverflowError, not the ValueError the except catches,
    # and escapes the "not ours, ignore it" promise on that very line, out of `panel_watermark` and
    # out of every sweep that calls it. Nothing this writer creates looks like that: this tree is an
    # rsync destination whose regeneration runbook has an operator deleting directories in it by hand.
    panel_root = tmp_path / "panel"
    write_hour(panel_root, "BTC/EUR", H, _materialize(tmp_path / "primary", "BTC/EUR", H))
    # 2**31 exactly: one less is the ValueError the clause already caught, so this is the boundary.
    oversized = panel_root / "BTC" / "EUR" / "panel-1s" / str(2**31) / "01" / "01" / "00.parquet"
    oversized.parent.mkdir(parents=True)
    oversized.write_bytes(b"garbage under a year directory no writer of ours can produce")

    assert panel_watermark(panel_root, "BTC/EUR") == H  # the well-formed hour beside it still wins
    assert oversized.exists()  # left alone, not deleted


# --- materialize: the watermarked sweep -----------------------------------------------------------------


def test_materialize_skips_hours_at_or_below_the_watermark(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))

    first = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))
    assert first.hours_written == 1 and first.hours_skipped == 0 and first.errors == []

    _book(primary, "BTC/EUR", H + timedelta(hours=1), _explode("BTC/EUR", H + timedelta(hours=1), _messages()))
    _book(primary, "BTC/EUR", H + timedelta(hours=2), _explode("BTC/EUR", H + timedelta(hours=2), _messages()))

    second = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))
    assert second.hours_written == 2  # only the two hours newer than the watermark
    assert second.hours_skipped == 1  # H, already <= the watermark from the first sweep
    assert second.rows == 2 * 3600


def test_materialize_defers_an_unsettled_hour_then_takes_it_once_settled(tmp_path: Path) -> None:
    # T0066 / spec 00052 D6 correction: an hour is heal-complete only after the reconciler's H+6h
    # max mint (+ a pull cycle), so `materialize` must NOT consume an hour whose settle margin has not
    # elapsed -- otherwise the monotone watermark permanently captures the un-healed primary. Inject
    # `now` to control the clock: with settle=7h and now=H+7.5h, H is settled but H+1h (only 6.5h old)
    # is not.
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))  # H: snapshot-open
    h1 = H + timedelta(hours=1)
    h1_messages = [{"offset": 0, "type": "update", "bids": [(99.0, 5.0)], "asks": [], "checksum": 2}]
    _book(primary, "BTC/EUR", h1, _explode("BTC/EUR", h1, h1_messages))  # update-open: needs H's state

    first = materialize(primary, None, panel_root, pair="BTC/EUR", now=H + timedelta(hours=7, minutes=30))
    assert first.hours_written == 1  # only H (settled: 7.5h >= 7h)
    assert first.hours_unsettled == 1  # h1 deferred (6.5h < 7h), NOT written, NOT unanchored, NOT an error
    assert first.hours_unanchored == 0 and first.errors == []
    assert panel_watermark(panel_root, "BTC/EUR") == H  # the watermark did NOT advance onto the unsettled hour

    # Later, once h1 has settled, a fresh sweep takes it -- resuming from H's state (proving deferral
    # left the threading intact, not stranded).
    second = materialize(primary, None, panel_root, pair="BTC/EUR", now=H + timedelta(hours=9))
    assert second.hours_written == 1  # h1 now settled (8h >= 7h)
    assert second.hours_skipped == 1  # H, already <= the watermark
    assert second.hours_unsettled == 0
    assert panel_watermark(panel_root, "BTC/EUR") == h1


def test_materialize_isolates_a_corrupt_hour_and_continues(tmp_path: Path) -> None:
    # The corrupt hour sorts FIRST (H before H+1h), proving a later good hour still proceeds past it.
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    corrupt = primary / "BTC" / "EUR" / "book" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H:%H}.parquet"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"not a parquet file")
    good_hour = H + timedelta(hours=1)
    _book(primary, "BTC/EUR", good_hour, _explode("BTC/EUR", good_hour, _messages()))

    result = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))

    assert result.hours_written == 1
    assert len(result.errors) == 1
    assert result.errors[0][0] == "BTC/EUR"
    assert result.errors[0][1] == H
    assert panel_watermark(panel_root, "BTC/EUR") == good_hour


def test_materialize_a_canonical_gap_is_unanchored_not_an_error(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))  # H: snapshot-open, materializes fine

    gap_hour = H + timedelta(hours=2)  # H+1 is MISSING from the archive -- a canonical gap
    gap_messages = [{"offset": 0, "type": "update", "bids": [(99.0, 1.0)], "asks": [(102.0, 1.0)], "checksum": 9}]
    _book(primary, "BTC/EUR", gap_hour, _explode("BTC/EUR", gap_hour, gap_messages))

    result = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))

    assert result.hours_written == 1  # only H
    assert result.hours_unanchored == 1  # gap_hour: update-opening, no contiguous predecessor
    assert result.errors == []
    assert panel_watermark(panel_root, "BTC/EUR") == H  # the unanchored hour published nothing


def test_materialize_resumes_across_runs_via_the_state_sidecar(tmp_path: Path) -> None:
    # Two SEPARATE `materialize()` calls -- standing in for two separate process runs -- prove the
    # resume goes through the persisted state.json sidecar, not in-process memory.
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    h_messages = [{"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1}]
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, h_messages))

    first = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))
    assert first.hours_written == 1 and first.hours_unanchored == 0 and first.errors == []

    h1 = H + timedelta(hours=1)
    h1_messages = [{"offset": 0, "type": "update", "bids": [(99.0, 5.0)], "asks": [], "checksum": 2}]
    _book(primary, "BTC/EUR", h1, _explode("BTC/EUR", h1, h1_messages))  # update-opening: needs H's state

    second = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))

    assert second.hours_written == 1  # resumed via H's state file, not unanchored
    assert second.hours_unanchored == 0
    assert second.errors == []
    final = panel_root / "BTC" / "EUR" / "panel-1s" / f"{h1:%Y}" / f"{h1:%m}" / f"{h1:%d}" / f"{h1:%H}.parquet"
    frame = pl.read_parquet(final)
    assert frame.height == 3600  # the ask side (101.0) is quotable only via H's carried state
    assert frame.row(0, named=True)["mid"] == 100.5


def test_materialize_resume_with_a_corrupt_state_file_is_unanchored_not_a_crash(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))
    first = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))
    assert first.hours_written == 1

    state_path = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.state.json"
    state_path.write_text("{ not json")  # corrupt the persisted state in place

    h1 = H + timedelta(hours=1)
    h1_messages = [{"offset": 0, "type": "update", "bids": [(99.0, 5.0)], "asks": [], "checksum": 2}]
    _book(primary, "BTC/EUR", h1, _explode("BTC/EUR", h1, h1_messages))

    second = materialize(primary, None, panel_root, pair="BTC/EUR", settle=timedelta(0))

    assert second.hours_unanchored == 1  # corrupt state -> can't resume -> unanchored, never a crash
    assert second.errors == []
    assert second.hours_written == 0


def test_materialize_uses_the_reconciled_hour_when_present(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    reconciled = tmp_path / "reconciled"
    panel_root = tmp_path / "panel"

    # The primary's snapshot has bid qty 1.0; the reconciled (healed) hour's snapshot has bid qty
    # 9.0 -- a value difference that proves WHICH hour's bytes actually got materialized.
    healed_messages = [dict(_messages()[0], bids=[(100.0, 9.0)]), *_messages()[1:]]
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))
    _book(reconciled, "BTC/EUR", H, _explode("BTC/EUR", H, healed_messages))

    result = materialize(primary, reconciled, panel_root, pair="BTC/EUR", settle=timedelta(0))

    assert result.hours_written == 1 and result.errors == []
    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert pl.read_parquet(final).row(0, named=True)["depth_qty_bid_l1"] == 9.0  # the healed value, not 1.0


# --- materialize: quote scope (T0092 spec 00085 D1 -- every quote with a ladder, not just EUR) --------


def test_the_sweep_no_longer_skips_a_btc_quoted_pair(tmp_path: Path) -> None:
    capture_root, panel_root = tmp_path / "capture", tmp_path / "panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=UTC)
    _book(capture_root, "ETH/BTC", hour, _explode("ETH/BTC", hour, _messages()))

    # THREE positionals: (primary_root, reconciled_root, panel_root). Passing two silently binds
    # panel_root to reconciled_root and raises TypeError on the missing third.
    result = materialize(capture_root, None, panel_root, settle=timedelta(0), now=hour + timedelta(hours=8))

    assert result.pairs_out_of_scope == 0
    assert result.hours_written == 1
    assert (panel_root / "ETH" / "BTC" / "panel-1s").exists()


def test_a_pair_whose_quote_has_no_ladder_is_still_counted_out_of_scope(tmp_path: Path) -> None:
    capture_root, panel_root = tmp_path / "capture", tmp_path / "panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=UTC)
    _book(capture_root, "ETH/USD", hour, _explode("ETH/USD", hour, _messages()))

    result = materialize(capture_root, None, panel_root, settle=timedelta(0), now=hour + timedelta(hours=8))

    # Skipped, not crashed, and NOT silently walked with the EUR ladder.
    assert result.pairs_out_of_scope == 1
    assert result.hours_written == 0
    assert not (panel_root / "ETH" / "USD").exists()


def test_pairs_out_of_scope_counts_distinct_pairs_not_hours(tmp_path: Path) -> None:
    """A single ladderless pair with MANY captured hours must count as ONE out-of-scope pair, not
    one per hour -- otherwise a real tree with hundreds of hours for one out-of-scope pair inflates
    this counter by the hour count, and the dedup also gates the log line (one INFO per pair, not
    one per hour shipped to Loki)."""
    capture_root, panel_root = tmp_path / "capture", tmp_path / "panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=UTC)
    for offset in range(3):
        h = hour + timedelta(hours=offset)
        _book(capture_root, "ETH/USD", h, _explode("ETH/USD", h, _messages()))

    result = materialize(capture_root, None, panel_root, settle=timedelta(0), now=hour + timedelta(hours=8))

    assert result.pairs_out_of_scope == 1  # one PAIR, not three hours
    assert result.hours_written == 0
    assert not (panel_root / "ETH" / "USD").exists()


def test_the_out_of_scope_log_line_is_deduped_per_pair_not_per_hour(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The counter dedup above is not the only thing the `skipped_pairs` set buys: it also gates the
    LOG line. A pair with hundreds of captured hours must ship ONE INFO line to Loki, not one per
    hour -- asserting only `pairs_out_of_scope` would pass even with the set kept but the log call
    moved outside the `if seg_pair not in skipped_pairs` guard."""
    capture_root, panel_root = tmp_path / "capture", tmp_path / "panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=UTC)
    for offset in range(3):
        h = hour + timedelta(hours=offset)
        _book(capture_root, "ETH/USD", h, _explode("ETH/USD", h, _messages()))

    with caplog.at_level(logging.INFO, logger="zcrypto.panel.materialize"):
        materialize(capture_root, None, panel_root, settle=timedelta(0), now=hour + timedelta(hours=8))

    skip_lines = [r for r in caplog.records if "ETH/USD" in r.message]
    assert len(skip_lines) == 1, [r.message for r in skip_lines]


# --- write_meta: the generation manifest ------------------------------------------------------------


def test_write_meta_writes_the_generation_manifest(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"

    path = write_meta(panel_root)

    assert path == panel_root / "panel-meta.json"
    meta = json.loads(path.read_text())
    assert meta["schema_version"] == 2  # T0104 bumped it: stale_seconds is a generation change
    assert meta["grid"] == "1s"
    assert meta["notionals_by_quote"]["EUR"] == [100.0, 1000.0, 10000.0]
    assert meta["k_levels"] == [1, 5, 10]
    assert meta["code_ref"]  # non-empty; exact value is host-dependent


def test_meta_k_levels_match_the_primitive_depth_ladder():
    # Review M4: K_LEVELS is generation METADATA for panel-meta.json while primitives._DEPTH_LEVELS
    # is the math; two sources of truth must not drift or the meta silently lies about the columns.
    from cli.panel import primitives
    from cli.panel.materialize import K_LEVELS

    assert K_LEVELS == primitives._DEPTH_LEVELS


def test_final_fractional_second_messages_reach_the_carried_book(tmp_path: Path) -> None:
    """Review C1: a message at :59:59.5 has no sampling boundary in its own hour, but it MUST be in
    the carried-out state -- otherwise every update-opening successor starts stale and the panel
    silently drifts at each hour boundary."""
    primary = tmp_path / "primary"
    h2 = H + timedelta(hours=1)
    msgs_h = [
        {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
        # final fractional second: ask 101 removed, ask 150 added
        {"offset": 3599.5, "type": "update", "bids": [], "asks": [(101.0, 0.0), (150.0, 1.0)], "checksum": 2},
    ]
    msgs_h2 = [
        # deliberately NOT at offset 0: second 0 must sample the CARRIED clock (0.5 s), which a
        # message on the boundary would mask by resetting it to 0.0.
        {"offset": 5, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 3},
    ]
    path_h = _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, msgs_h))
    path_h2 = _book(primary, "BTC/EUR", h2, _explode("BTC/EUR", h2, msgs_h2))

    frame_h, book_h, last_h = materialize_hour(path_h, "BTC/EUR", H, depth=10)
    # T0104: the drained message reaches the carried BOOK, so it must reach the carried CLOCK too --
    # otherwise H+1's first rows report a 0.5 s-old book as a full hour stale (a ~3600x error, in
    # the direction that makes honest rows look fabricated and get filtered away).
    assert last_h == H + timedelta(seconds=3599.5)
    # H's own rows never saw the 3599.5s move (no boundary owns it)...
    assert frame_h["mid"][-1] == pytest.approx((100 + 101) / 2)
    # ...but the carried book did: H+1 opens on mid (100+150)/2.
    frame_h2, _, _lm2 = materialize_hour(path_h2, "BTC/EUR", h2, depth=10, book=book_h, last_msg_ts=last_h)
    # Second 0 of H+1 is 0.5 s after H's drained message -- the carried clock, not a restart.
    assert frame_h2["stale_seconds"][0] == pytest.approx(0.5)
    assert frame_h2["mid"][0] == pytest.approx((100 + 150) / 2), "final-second message lost from the carry"


# --- T0104: the staleness marker -----------------------------------------------------------------
#
# The panel builds a DENSE 3600-row/hour grid from a canonical archive that can have holes. Before
# this column, a hole produced rows carrying a CARRIED-FORWARD book marked only by `updates == 0` --
# which is also the marker for a genuinely quiet second.
#
# `stale_seconds` is the distinguishing property, emitted rather than inferred: seconds from the
# last message actually applied to the book to this boundary. It is threaded across hours, because
# a blackout can begin inside the PREVIOUS hour and a within-hour counter would restart it at the
# boundary and understate it.


def _stale_messages() -> list[dict]:
    """Snapshot at :00, an update at :01, then a 10-second hole, then an update at :12."""
    return [
        {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
        {"offset": 1, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 2},
        {"offset": 12, "type": "update", "bids": [(100.0, 3.0)], "asks": [], "checksum": 3},
    ]


def test_stale_seconds_grows_across_a_hole_and_resets_on_the_next_message(tmp_path: Path) -> None:
    """The whole point: a frozen book is now self-describing. During the hole every row carries a
    growing `stale_seconds`; the second the data returns it drops back to ~0."""
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, _stale_messages()))
    frame, _book_out, _last = materialize_hour(path, "BTC/EUR", H, depth=10)

    by_sec = {int((r["ts"] - H).total_seconds()): r for r in frame.to_dicts()}
    assert by_sec[1]["stale_seconds"] == pytest.approx(0.0)  # message landed exactly on the boundary
    assert by_sec[5]["stale_seconds"] == pytest.approx(4.0)  # 4 s since the :01 update
    assert by_sec[11]["stale_seconds"] == pytest.approx(10.0)  # the hole's last second
    assert by_sec[12]["stale_seconds"] == pytest.approx(0.0)  # data returned
    # And the marker is what `updates` alone could not say: both seconds look identically quiet.
    assert by_sec[5]["updates"] == 0 and by_sec[11]["updates"] == 0


def test_stale_seconds_threads_across_the_hour_boundary(tmp_path: Path) -> None:
    """A blackout spanning midnight-of-the-hour must not have its clock reset. The 2026-07-13 event
    began at 06:59:59.69 -- in the previous hour -- so a within-hour counter would have reported a
    fraction of the true silence at exactly the moment the number mattered most."""
    hour_a, hour_b = H, H + timedelta(hours=1)
    # Hour A: snapshot at :00, last message at :10, then silence to the end of the hour.
    msgs_a = [
        {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
        {"offset": 10, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 2},
    ]
    path_a = _book(tmp_path, "BTC/EUR", hour_a, _explode("BTC/EUR", hour_a, msgs_a))
    _frame_a, book_a, last_a = materialize_hour(path_a, "BTC/EUR", hour_a, depth=10)
    assert last_a is not None, "the last-message time must be carried out for the next hour"

    # Hour B opens with an update (no snapshot) 5 s in -- so seconds 0..4 continue A's silence.
    msgs_b = [{"offset": 5, "type": "update", "bids": [(100.0, 4.0)], "asks": [], "checksum": 3}]
    path_b = _book(tmp_path, "BTC/EUR", hour_b, _explode("BTC/EUR", hour_b, msgs_b))
    frame_b, _book_b, _last_b = materialize_hour(path_b, "BTC/EUR", hour_b, depth=10, book=book_a, last_msg_ts=last_a)

    by_sec = {int((r["ts"] - hour_b).total_seconds()): r for r in frame_b.to_dicts()}
    # Second 0 of hour B is 3590 s after hour A's :10 message -- not 0, and not restarted.
    assert by_sec[0]["stale_seconds"] == pytest.approx(3590.0)
    assert by_sec[4]["stale_seconds"] == pytest.approx(3594.0)
    assert by_sec[5]["stale_seconds"] == pytest.approx(0.0)


def test_stale_seconds_is_null_when_the_carried_state_predates_the_column(tmp_path: Path) -> None:
    """A legacy `<HH>.state.json` has no last-message time. Emitting 0.0 there would assert
    freshness we cannot know; null says 'unknown' honestly and is filterable."""
    hour_b = H + timedelta(hours=1)
    book = OrderBook("BTC/EUR", 10)
    book.ingest_snapshot(
        {
            "bids": [{"price": Decimal("100"), "qty": Decimal("1")}],
            "asks": [{"price": Decimal("101"), "qty": Decimal("1")}],
            "checksum": 0,
        }
    )
    msgs = [{"offset": 5, "type": "update", "bids": [(100.0, 4.0)], "asks": [], "checksum": 3}]
    path = _book(tmp_path, "BTC/EUR", hour_b, _explode("BTC/EUR", hour_b, msgs))
    frame, _b, _l = materialize_hour(path, "BTC/EUR", hour_b, depth=10, book=book, last_msg_ts=None)

    by_sec = {int((r["ts"] - hour_b).total_seconds()): r for r in frame.to_dicts()}
    assert by_sec[0]["stale_seconds"] is None, "unknown staleness must be null, never 0.0"
    assert by_sec[5]["stale_seconds"] == pytest.approx(0.0), "the first real message anchors it"


def test_the_state_sidecar_round_trips_the_last_message_time(tmp_path: Path) -> None:
    """Threading only works if the sidecar carries it; and a sidecar written before this column
    must still load (returning None for the time) rather than crashing the sweep."""
    book = OrderBook("BTC/EUR", 10)
    book.ingest_snapshot(
        {
            "bids": [{"price": Decimal("100"), "qty": Decimal("1")}],
            "asks": [{"price": Decimal("101"), "qty": Decimal("1")}],
            "checksum": 0,
        }
    )
    ts = H + timedelta(seconds=42)
    write_state(tmp_path, "BTC/EUR", H, book, last_msg_ts=ts)
    loaded_book, loaded_ts = load_state(tmp_path, "BTC/EUR", H, depth=10)
    assert loaded_book is not None and loaded_ts == ts

    # A legacy sidecar (no key) loads with a None time, not an exception.
    p = tmp_path / "BTC" / "EUR" / "panel-1s" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H:%H}.state.json"
    p.write_text(json.dumps({"bids": {"100": "1"}, "asks": {"101": "1"}}))
    legacy_book, legacy_ts = load_state(tmp_path, "BTC/EUR", H, depth=10)
    assert legacy_book is not None and legacy_ts is None


def test_stale_seconds_is_in_the_schema_and_the_written_hour(tmp_path: Path) -> None:
    """A column nothing writes is the T0100 defect in another costume."""
    from cli.panel.primitives import PANEL_SCHEMA

    assert "stale_seconds" in PANEL_SCHEMA
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, _stale_messages()))
    frame, _b, _l = materialize_hour(path, "BTC/EUR", H, depth=10)
    out = write_hour(tmp_path / "panel", "BTC/EUR", H, frame)
    assert "stale_seconds" in pl.read_parquet(out).columns


def test_the_sweep_threads_the_clock_across_a_resumed_run(tmp_path: Path) -> None:
    """Production takes the resume path on EVERY run -- the hourly timer is a fresh process resuming
    from the watermark -- so it is the SWEEP's own `last_msg_ts` wiring that carries the clock, and a
    test driving `materialize_hour` directly leaves that wiring unexercised.
    """
    primary = tmp_path / "primary"
    reconciled = tmp_path / "reconciled"
    panel = tmp_path / "panel"
    h2 = H + timedelta(hours=1)
    # Hour H: snapshot at :00, last message at :10, silence to the end.
    _book(
        primary,
        "BTC/EUR",
        H,
        _explode(
            "BTC/EUR",
            H,
            [
                {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
                {"offset": 10, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 2},
            ],
        ),
    )
    # Hour H+1 opens with an update 5 s in, so seconds 0..4 continue H's silence.
    _book(
        primary,
        "BTC/EUR",
        h2,
        _explode(
            "BTC/EUR",
            h2,
            [
                {"offset": 5, "type": "update", "bids": [(100.0, 4.0)], "asks": [], "checksum": 3},
            ],
        ),
    )

    # TWO sweeps, deliberately: a single call carries the clock in memory and would pass even with
    # the sidecar wiring cut. The hourly timer is a FRESH PROCESS every run, so only a real resume
    # -- sweep 2 reading sweep 1's sidecar -- exercises what production does.
    settle = timedelta(hours=1)
    materialize(primary, reconciled, panel, depth=10, settle=settle, now=H + timedelta(hours=1, minutes=30), since=H)
    assert not (panel / "BTC" / "EUR" / "panel-1s" / f"{h2:%Y}" / f"{h2:%m}" / f"{h2:%d}" / f"{h2:%H}.parquet").exists(), (
        "hour H+1 must still be unsettled after sweep 1, or this test never resumes"
    )
    materialize(primary, reconciled, panel, depth=10, settle=settle, now=h2 + timedelta(hours=12), since=H)
    frame = pl.read_parquet(panel / "BTC" / "EUR" / "panel-1s" / f"{h2:%Y}" / f"{h2:%m}" / f"{h2:%d}" / f"{h2:%H}.parquet")
    first = frame.sort("ts").row(0, named=True)
    assert first["stale_seconds"] == pytest.approx(3590.0), (
        f"hour H+1 second 0 reports {first['stale_seconds']} -- the clock did not cross the boundary"
    )


def test_the_sweep_carries_the_clock_between_hours_of_a_SINGLE_run(tmp_path: Path) -> None:
    """The gap the resumed-run test above cannot see. That one crosses hours in SEPARATE processes,
    so the clock travels through the state sidecar. Within ONE sweep it travels through the
    in-memory `last_seen` dict instead — a different line — and deleting that carry-forward leaves
    the whole suite green while every hour after the first reads `stale_seconds = null` at its head.

    That matters beyond the hourly timer: the panel REGENERATION is one sweep over every hour of
    every pair, so this line is what carries staleness across every hour boundary in it. Nulls are
    the worst possible failure here, because a `> 30` filter drops them from BOTH sides.
    """
    primary = tmp_path / "primary"
    panel = tmp_path / "panel"
    h2 = H + timedelta(hours=1)
    # H: snapshot at :00, last message at :10, then silence to the boundary.
    _book(
        primary,
        "BTC/EUR",
        H,
        _explode(
            "BTC/EUR",
            H,
            [
                {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
                {"offset": 10, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 2},
            ],
        ),
    )
    # H+1 opens with an update 30 s in, so its first 30 seconds continue H's silence.
    _book(
        primary,
        "BTC/EUR",
        h2,
        _explode("BTC/EUR", h2, [{"offset": 30, "type": "update", "bids": [(100.0, 3.0)], "asks": [], "checksum": 3}]),
    )

    # ONE call spanning both hours: the clock can only reach H+1 through `last_seen`.
    materialize(primary, None, panel, settle=timedelta(hours=1), now=h2 + timedelta(hours=2))

    second = pl.read_parquet(panel / "BTC" / "EUR" / "panel-1s" / f"{h2:%Y}" / f"{h2:%m}" / f"{h2:%d}" / f"{h2:%H}.parquet")
    head = second["stale_seconds"][0]
    assert head is not None, "hour H+1 opened with 'staleness unknown'; the in-run carry-forward was lost"
    # H's last message was at :10, so H+1 second 0 is 3600 - 10 = 3590 s stale.
    assert head == pytest.approx(3590.0), f"expected 3590 s carried from H's last message, got {head}"
    assert second["stale_seconds"][29] == pytest.approx(3619.0), "and it keeps climbing until the first real message"
    assert second["stale_seconds"][30] == pytest.approx(0.0), "which resets it"
