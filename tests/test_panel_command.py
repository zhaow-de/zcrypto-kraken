"""TDD for `cli/panel/command.py` -- the `zcrypto panel materialize` CLI (spec 00052 Task 3).

Fixture style mirrors `tests/test_panel_materialize.py`'s `_book()`/`_explode()` helpers (mirrored
here per the plan's "import or mirror" allowance, matching this repo's convention of each command
test file carrying its own tiny synthetic-archive fixtures rather than cross-importing another
test module).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.segment_writer import BOOK_SCHEMA
from cli.panel.materialize import write_meta

H = datetime(2026, 7, 16, 9, tzinfo=UTC)

runner = CliRunner()


def _explode(pair: str, hour: datetime, messages: list[dict]) -> pl.DataFrame:
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
    base, quote = pair.split("/")
    p = root / base / quote / "book" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(p, compression="zstd")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_name(p.name + ".sha256").write_text(f"{digest}  {p.name}\n")
    return p


def _messages() -> list[dict]:
    return [
        {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 1},
        {"offset": 0.5, "type": "update", "bids": [(100.0, 2.0)], "asks": [], "checksum": 2},
        {"offset": 2.2, "type": "update", "bids": [(99.0, 3.0)], "asks": [], "checksum": 3},
        {"offset": 2.7, "type": "update", "bids": [], "asks": [(102.0, 4.0)], "checksum": 4},
    ]


def _seed_primary(root: Path, pair: str, hour: datetime) -> Path:
    return _book(root, pair, hour, _explode(pair, hour, _messages()))


# --- help --------------------------------------------------------------------------------------------


def test_panel_help() -> None:
    result = runner.invoke(app, ["panel", "--help"])
    assert result.exit_code == 0, result.output
    assert "materialize" in result.output


def test_panel_materialize_help() -> None:
    result = runner.invoke(app, ["panel", "materialize", "--help"])
    assert result.exit_code == 0, result.output
    # CI's narrow no-TTY terminal makes rich wrap option names across lines with ANSI styling --
    # normalize before asserting (strip escapes, squash all whitespace) so the check is
    # terminal-agnostic.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    squashed = re.sub(r"\s+", "", plain)
    assert "--panel-root" in squashed
    assert "--since" in squashed
    assert "--allow-holes" in squashed
    assert "--settle-hours" in squashed


# --- end-to-end run + meta on first run --------------------------------------------------------------


def test_materialize_end_to_end_writes_the_panel_and_the_meta(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code == 0, result.output
    assert "pairs=1 hours_written=1 hours_skipped=0 hours_unsettled=0 hours_unanchored=0 rows=3600 errors=0" in result.output

    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert final.exists()
    assert pl.read_parquet(final).height == 3600

    meta = json.loads((panel_root / "panel-meta.json").read_text())
    assert meta["schema_version"] == 1
    assert meta["grid"] == "1s"
    assert meta["notionals_eur"] == [100.0, 1000.0, 10000.0]
    assert meta["k_levels"] == [1, 5, 10]


# --- meta-mismatch refusal -----------------------------------------------------------------------------


def test_meta_mismatch_refuses_before_writing_anything(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)
    write_meta(panel_root)
    meta_path = panel_root / "panel-meta.json"
    meta = json.loads(meta_path.read_text())
    meta["grid"] = "5s"  # a generation change that must never be silently mixed
    meta_path.write_text(json.dumps(meta))

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code != 0
    assert "generation" in result.output
    assert "5s" in result.output  # names the existing value
    assert "1s" in result.output  # names the code's value
    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert not final.exists()  # refused before writing anything


# --- the I2 --since/watermark hole guard ---------------------------------------------------------------


def test_since_newer_than_watermark_refuses_without_allow_holes(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)
    first = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])
    assert first.exit_code == 0, first.output  # seeds the BTC/EUR watermark at H

    later = H + timedelta(hours=3)
    _seed_primary(primary, "BTC/EUR", later)

    result = runner.invoke(
        app,
        [
            "panel",
            "materialize",
            str(primary),
            "--panel-root",
            str(panel_root),
            "--since",
            later.strftime("%Y-%m-%dT%H"),
        ],
    )

    assert result.exit_code != 0
    assert "BTC/EUR" in result.output
    assert "watermark" in result.output
    assert "--allow-holes" in result.output
    # nothing written for the later hour: the refusal happened before materialize ran
    later_final = panel_root / "BTC" / "EUR" / "panel-1s" / f"{later:%Y}" / f"{later:%m}" / f"{later:%d}" / f"{later:%H}.parquet"
    assert not later_final.exists()


def test_since_newer_than_watermark_proceeds_with_allow_holes(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)
    first = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])
    assert first.exit_code == 0, first.output  # seeds the BTC/EUR watermark at H

    later = H + timedelta(hours=3)
    _seed_primary(primary, "BTC/EUR", later)

    result = runner.invoke(
        app,
        [
            "panel",
            "materialize",
            str(primary),
            "--panel-root",
            str(panel_root),
            "--since",
            later.strftime("%Y-%m-%dT%H"),
            "--allow-holes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "watermark" in result.output  # the warning still fires
    later_final = panel_root / "BTC" / "EUR" / "panel-1s" / f"{later:%Y}" / f"{later:%m}" / f"{later:%d}" / f"{later:%H}.parquet"
    assert later_final.exists()


# --- hours_unanchored -> an honest gap, exit 0 (spec 00052 D3 correction) -----------------------------


def test_hours_unanchored_reported_in_summary_and_exits_zero(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)  # H: snapshot-open, materializes fine

    gap_hour = H + timedelta(hours=2)  # H+1 is missing from the archive -- a canonical gap
    gap_messages = [{"offset": 0, "type": "update", "bids": [(99.0, 1.0)], "asks": [(102.0, 1.0)], "checksum": 9}]
    _book(primary, "BTC/EUR", gap_hour, _explode("BTC/EUR", gap_hour, gap_messages))

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code == 0, result.output  # an honest gap must not fail the run
    assert "hours_unanchored=1" in result.output
    assert "errors=0" in result.output


# --- errors -> exit 1 -----------------------------------------------------------------------------------


def test_a_corrupt_hour_exits_one_but_other_hours_still_materialize(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    corrupt = primary / "BTC" / "EUR" / "book" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H:%H}.parquet"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"not a parquet file")
    good_hour = H + timedelta(hours=1)
    _seed_primary(primary, "BTC/EUR", good_hour)

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code == 1
    assert "panel hour failed pair=BTC/EUR hour=" in result.output
    good_final = (
        panel_root
        / "BTC"
        / "EUR"
        / "panel-1s"
        / f"{good_hour:%Y}"
        / f"{good_hour:%m}"
        / f"{good_hour:%d}"
        / f"{good_hour:%H}.parquet"
    )
    assert good_final.exists()


def test_hole_guard_checks_every_pair_and_the_fresh_pair_case(tmp_path):
    # Review M-2 + I-1: with several pairs, ONE offending pair must refuse the whole run; and a
    # FRESH pair (no watermark) with --since above its earliest canonical hour is the same silent
    # hole -- the earliest hour stands in for the watermark.
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    for pair in ("BTC/EUR", "ETH/EUR"):
        for offset in (0, 1, 2, 3):
            _seed_primary(primary, pair, H + timedelta(hours=offset))

    # Materialize BTC fully; ETH not at all (fresh pair).
    r = runner.invoke(
        app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--pair", "BTC/EUR", "--settle-hours", "0"]
    )
    assert r.exit_code == 0, r.output

    # --since H+2 across ALL pairs: BTC's watermark is H+3 (no hole for BTC: since < watermark),
    # but fresh ETH would strand H..H+1 -> the run must refuse without --allow-holes.
    since = (H + timedelta(hours=2)).strftime("%Y-%m-%dT%H")
    r = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--since", since])
    assert r.exit_code == 1, r.output
    eth_dir = panel_root / "ETH" / "EUR"
    assert not eth_dir.exists()  # refused before writing

    # --allow-holes proceeds and materializes ETH from `since` onward only.
    r = runner.invoke(
        app,
        [
            "panel",
            "materialize",
            str(primary),
            "--panel-root",
            str(panel_root),
            "--since",
            since,
            "--allow-holes",
            "--settle-hours",
            "0",
        ],
    )
    assert r.exit_code == 0, r.output
    eth_hours = sorted(p.name for p in eth_dir.rglob("*.parquet"))
    assert len(eth_hours) == 2  # H+2, H+3 only -- the hole was consciously accepted


def test_since_parsing_edges(tmp_path):
    # Review M-3: aware tz converting to an on-hour UTC passes; sub-hour rejected; bare date = midnight.
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)

    aware = (H + timedelta(hours=2)).astimezone(timezone(timedelta(hours=2))).isoformat()  # +02:00, on-hour in UTC
    r = runner.invoke(
        app,
        [
            "panel",
            "materialize",
            str(primary),
            "--panel-root",
            str(panel_root),
            "--since",
            aware,
            "--allow-holes",
            "--settle-hours",
            "0",
        ],
    )
    assert r.exit_code == 0, r.output

    r = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--since", "2026-07-16T09:30"])
    assert r.exit_code == 2  # BadParameter: not on an hour boundary

    r = runner.invoke(
        app,
        ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--since", H.strftime("%Y-%m-%d"), "--allow-holes"],
    )
    assert r.exit_code == 0, r.output
