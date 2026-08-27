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
import pytest
import typer
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
    assert (
        "pairs=1 pairs_out_of_scope=0 hours_written=1 hours_skipped=0 hours_unsettled=0 hours_unanchored=0 rows=3600 errors=0"
        in result.output
    )

    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert final.exists()
    assert pl.read_parquet(final).height == 3600

    meta = json.loads((panel_root / "panel-meta.json").read_text())
    assert meta["schema_version"] == 2  # T0104 bumped it: stale_seconds is a generation change
    assert meta["grid"] == "1s"
    assert meta["notionals_by_quote"]["EUR"] == [100.0, 1000.0, 10000.0]
    assert meta["k_levels"] == [1, 5, 10]


def test_the_generation_manifest_records_the_per_quote_ladder() -> None:
    from cli.panel.command import _expected_generation

    gen = _expected_generation()
    assert gen["schema_version"] == 2  # unchanged: no column moved
    assert gen["notionals_by_quote"]["EUR"] == [100.0, 1_000.0, 10_000.0]
    assert "BTC" in gen["notionals_by_quote"]
    assert "notionals_eur" not in gen


def test_a_tree_built_on_the_old_eur_only_manifest_refuses(tmp_path: Path) -> None:
    # A panel-meta.json carrying the OLD generation must abort: its columns mean something else now.
    # This is the regeneration gate doing its job, and it is what forces the rebuild.
    from cli.panel.command import _check_generation

    panel_root = tmp_path / "l2-panel"
    panel_root.mkdir(parents=True)
    (panel_root / "panel-meta.json").write_text(
        json.dumps({"schema_version": 2, "grid": "1s", "notionals_eur": [100.0, 1_000.0, 10_000.0], "k_levels": [1, 5, 10]})
    )
    # schema_version matches; the LADDER KEY does not. That alone must refuse -- which is why no
    # SCHEMA_VERSION bump is needed to force the regeneration.

    with pytest.raises(typer.Exit):
        _check_generation(panel_root)


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


def test_a_missing_meta_over_a_POPULATED_tree_refuses_instead_of_minting_a_fresh_one(tmp_path: Path) -> None:
    """The generation guard read the meta file, not the tree it describes — so `rm panel-meta.json`
    alone, which is the obvious response to its own abort message while a warning and a critical page
    are both firing, wrote a fresh meta and then appended new-generation hours onto old ones. Every
    later run read the new meta and passed. The tree is then permanently unreadable as a whole, and
    nothing anywhere detects it: `_check_generation` cannot see the mix, and the watermarked sweep
    never revisits an hour it has already written.

    An absent meta means "fresh tree" ONLY if the tree is actually fresh.
    """
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)
    # A tree with hours in it and no meta: exactly the post-`rm` state.
    stranded = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "15"
    stranded.mkdir(parents=True)
    (stranded / "09.parquet").write_bytes(b"not really parquet -- presence is what is checked")

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code != 0, result.output
    assert not (panel_root / "panel-meta.json").exists(), "a fresh meta was minted over an existing tree"
    assert "panel-meta.json" in result.output
    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert not final.exists(), "refused before writing anything"


def test_an_out_of_scope_subtree_refuses_because_no_sweep_can_ever_repair_it(tmp_path: Path) -> None:
    """The hole the manifest check could not see, and the one the planned regeneration creates. The
    sweep only covers quotes with a notional ladder (`NOTIONALS_BY_QUOTE`), so hours for a quote
    outside it are never revisited: they keep the generation that wrote them while the manifest
    claims the current one, and a whole-tree read then raises SchemaError on files nobody remembers
    exist. A matching manifest is not evidence the tree matches it — and unlike every other mixed
    state, no re-run can repair this one."""
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)
    write_meta(panel_root)  # a CURRENT, matching manifest -- the old check passed this happily
    stray = panel_root / "ETH" / "USD" / "panel-1s" / "2026" / "07" / "15"  # USD has no ladder (T0092)
    stray.mkdir(parents=True)
    (stray / "09.parquet").write_bytes(b"an hour with no notional ladder -- the sweep will never revisit it")

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code != 0, result.output
    assert "ETH" in result.output and "USD" in result.output, "the refusal must name what to delete"
    assert "NAS" in result.output, "and that deleting one side leaves the other to be pulled back"
    final = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet"
    assert not final.exists(), "refused before writing anything"


def test_orphan_sidecars_alone_do_not_look_like_a_populated_tree(tmp_path: Path) -> None:
    """The guard keys on `*.parquet`, deliberately: a tree holding only `.state.json`/`.sha256`
    leftovers has no hours, `panel_watermark` is None, and every hour re-materializes correctly. It
    must bootstrap, not refuse."""
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)
    orphans = panel_root / "BTC" / "EUR" / "panel-1s" / "2026" / "07" / "15"
    orphans.mkdir(parents=True)
    (orphans / "09.parquet.sha256").write_text("deadbeef  09.parquet\n")
    (orphans / "09.state.json").write_text("{}")

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code == 0, result.output
    assert (panel_root / "panel-meta.json").exists()


def test_a_missing_meta_over_an_EMPTY_tree_still_bootstraps(tmp_path: Path) -> None:
    """The first-ever run must keep working: no meta and no hours is a genuinely fresh tree."""
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "BTC/EUR", H)

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code == 0, result.output
    assert (panel_root / "panel-meta.json").exists()


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


# --- quote scope: the ladder is quote-denominated, so the panel covers only quotes with a ladder in
# NOTIONALS_BY_QUOTE (currently EUR, BTC) (T0092) ------------------------------------------------------


def test_materialize_skips_pairs_whose_quote_has_no_ladder_in_the_sweep(tmp_path: Path) -> None:
    """A quote with no entry in `NOTIONALS_BY_QUOTE` must never be materialized (T0092/spec 00085
    D1: the sweep now walks every quote that HAS a ladder -- BTC included -- so the property that
    survives is "no ladder for this quote", not "not EUR". USD has no ladder entry.
    """
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "ETH/EUR", H)
    _seed_primary(primary, "ETH/USD", H)

    result = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])

    assert result.exit_code == 0, result.output
    # only the EUR leg (the quote with a ladder) is counted and written
    assert "pairs=1 pairs_out_of_scope=1 " in result.output, result.output
    assert (panel_root / "ETH" / "EUR" / "panel-1s" / "2026" / "07" / "16" / "09.parquet").exists()
    assert not (panel_root / "ETH" / "USD").exists()


def test_materialize_refuses_an_explicit_non_eur_pair(tmp_path: Path) -> None:
    """`--pair ETH/USD` must fail loudly, not exit 0 having done nothing: USD has no notional ladder."""
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "ETH/USD", H)

    result = runner.invoke(
        app,
        ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0", "--pair", "ETH/USD"],
    )

    assert result.exit_code != 0, result.output
    assert "notional ladder" in result.output


def test_a_btc_quoted_pair_is_accepted_by_the_pair_option(tmp_path: Path) -> None:
    # Follows test_materialize_refuses_an_explicit_non_eur_pair exactly: the primary tree and
    # --panel-root are REQUIRED parameters, and Click fails on a missing one BEFORE the function body
    # runs -- so an invocation without them would pass vacuously and prove nothing.
    primary, panel_root = tmp_path / "primary", tmp_path / "panel"
    _seed_primary(primary, "ETH/BTC", H)

    ok = runner.invoke(
        app,
        ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0", "--pair", "ETH/BTC"],
    )
    assert ok.exit_code == 0, ok.output

    _seed_primary(primary, "ETH/USD", H)
    refused = runner.invoke(
        app,
        ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0", "--pair", "ETH/USD"],
    )
    assert refused.exit_code != 0, refused.output
    assert "notional ladder" in refused.output


def test_a_second_sweep_over_a_prior_btc_hour_is_counted_and_not_refused(tmp_path: Path) -> None:
    """Closes two guards neither existing test discriminates (T0092 review): `_affected_pairs`'
    `NOTIONALS_BY_QUOTE` membership check and `_check_generation`'s stray-scope check both revert to
    their old EUR-only form and every existing test still passes. `test_an_out_of_scope_subtree_...`
    never materializes a real BTC hour before checking, and `test_a_btc_quoted_pair_is_accepted_...`
    runs on a fresh tree where the stray check never executes (absent manifest -> `write_meta` and
    return) and dies at the `--pair` `BadParameter` on its second call before `_check_generation` is
    reached. Only a tree that already holds a BTC hour from a PRIOR sweep exercises both: the
    completion line's `pairs=` count on the first run, and the generation guard's stray-hour scan
    (which must not mistake that BTC hour for one the sweep will never revisit) on the second."""
    primary = tmp_path / "primary"
    panel_root = tmp_path / "panel"
    _seed_primary(primary, "ETH/EUR", H)
    _seed_primary(primary, "ETH/BTC", H)

    first = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])
    assert first.exit_code == 0, first.output
    assert "pairs=2 " in first.output, first.output  # _affected_pairs must count the BTC leg too

    second = runner.invoke(app, ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0"])
    assert second.exit_code == 0, second.output  # the BTC hour from the first sweep is not a stray
