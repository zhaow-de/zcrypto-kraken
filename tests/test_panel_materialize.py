"""TDD for `cli/panel/materialize.py` -- the hour materializer + watermarked sweep (spec 00052
Task 2: D3/D4/D5/D6).

Fixture style mirrors `tests/test_archive_replay.py`'s `_book()`/`_explode()` helpers: synthetic
exploded BOOK_SCHEMA hours, fanned out one row per price level exactly as the capture writer does.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.capture.segment_writer import BOOK_SCHEMA, verify_manifest
from cli.panel.errors import PanelError
from cli.panel.materialize import materialize, materialize_hour, panel_watermark, write_hour, write_meta

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
    return materialize_hour(path, pair, hour, depth=depth)


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

    frame = materialize_hour(path, "BTC/EUR", H, depth=10)

    assert frame.height == 3598  # 3600 minus the two pre-snapshot boundaries
    assert frame["ts"][0] == H + timedelta(seconds=2)


def test_materialize_hour_without_a_leading_snapshot_raises(tmp_path: Path) -> None:
    messages = _messages()[1:]  # opens with an update, never a snapshot
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    with pytest.raises(PanelError):
        materialize_hour(path, "BTC/EUR", H, depth=10)


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


# --- panel_watermark: round trip -----------------------------------------------------------------------


def test_panel_watermark_round_trips(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"
    assert panel_watermark(panel_root, "BTC/EUR") is None  # nothing written yet

    write_hour(panel_root, "BTC/EUR", H, _materialize(tmp_path / "primary", "BTC/EUR", H))
    assert panel_watermark(panel_root, "BTC/EUR") == H

    later = H + timedelta(hours=2)
    write_hour(panel_root, "BTC/EUR", later, _materialize(tmp_path / "primary", "BTC/EUR", later))
    assert panel_watermark(panel_root, "BTC/EUR") == later  # the newest hour, not merely the latest write


# --- materialize: the watermarked sweep -----------------------------------------------------------------


def test_materialize_skips_hours_at_or_below_the_watermark(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))

    first = materialize(primary, None, panel_root, pair="BTC/EUR")
    assert first.hours_written == 1 and first.hours_skipped == 0 and first.errors == []

    _book(primary, "BTC/EUR", H + timedelta(hours=1), _explode("BTC/EUR", H + timedelta(hours=1), _messages()))
    _book(primary, "BTC/EUR", H + timedelta(hours=2), _explode("BTC/EUR", H + timedelta(hours=2), _messages()))

    second = materialize(primary, None, panel_root, pair="BTC/EUR")
    assert second.hours_written == 2  # only the two hours newer than the watermark
    assert second.hours_skipped == 1  # H, already <= the watermark from the first sweep
    assert second.rows == 2 * 3600


def test_materialize_isolates_a_corrupt_hour_and_continues(tmp_path: Path) -> None:
    # The corrupt hour sorts FIRST (H before H+1h), proving a later good hour still proceeds past it.
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    corrupt = primary / "BTC" / "EUR" / "book" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H:%H}.parquet"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"not a parquet file")
    good_hour = H + timedelta(hours=1)
    _book(primary, "BTC/EUR", good_hour, _explode("BTC/EUR", good_hour, _messages()))

    result = materialize(primary, None, panel_root, pair="BTC/EUR")

    assert result.hours_written == 1
    assert len(result.errors) == 1
    assert result.errors[0][0] == "BTC/EUR"
    assert result.errors[0][1] == H
    assert panel_watermark(panel_root, "BTC/EUR") == good_hour


def test_materialize_uses_the_reconciled_hour_when_present(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    reconciled = tmp_path / "reconciled"
    panel_root = tmp_path / "panel"

    # The primary's snapshot has bid qty 1.0; the reconciled (healed) hour's snapshot has bid qty
    # 9.0 -- a value difference that proves WHICH hour's bytes actually got materialized.
    healed_messages = [dict(_messages()[0], bids=[(100.0, 9.0)]), *_messages()[1:]]
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _messages()))
    _book(reconciled, "BTC/EUR", H, _explode("BTC/EUR", H, healed_messages))

    result = materialize(primary, reconciled, panel_root, pair="BTC/EUR")

    assert result.hours_written == 1 and result.errors == []
    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert pl.read_parquet(final).row(0, named=True)["depth_qty_bid_l1"] == 9.0  # the healed value, not 1.0


# --- write_meta: the generation manifest ------------------------------------------------------------


def test_write_meta_writes_the_generation_manifest(tmp_path: Path) -> None:
    panel_root = tmp_path / "panel"

    path = write_meta(panel_root)

    assert path == panel_root / "panel-meta.json"
    meta = json.loads(path.read_text())
    assert meta["schema_version"] == 1
    assert meta["grid"] == "1s"
    assert meta["notionals_eur"] == [100.0, 1000.0, 10000.0]
    assert meta["k_levels"] == [1, 5, 10]
    assert meta["code_ref"]  # non-empty; exact value is host-dependent


def test_meta_k_levels_match_the_primitive_depth_ladder():
    # Review M4: K_LEVELS is generation METADATA for panel-meta.json while primitives._DEPTH_LEVELS
    # is the math; two sources of truth must not drift or the meta silently lies about the columns.
    from cli.panel import primitives
    from cli.panel.materialize import K_LEVELS

    assert K_LEVELS == primitives._DEPTH_LEVELS
