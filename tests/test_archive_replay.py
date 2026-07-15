"""TDD for `cli/archive/replay.py` — the canonical book continuity-replay driver (spec 00051 OPS-3).

Scope (finalized 2026-07-15, T0045): the archive stores price/qty as Float64, so the Kraken CRC is
NOT byte-exact re-derivable — the stored `checksum` column is trusted as capture-time ground truth
and is never compared against a re-derived one, and no "structural desync" heuristic exists (for a
depth-bounded book a legitimate out-of-window update is indistinguishable from corruption without
the CRC). What IS proven, per canonical hour: it opens with a snapshot, rows are ts-ordered, every
message carries a checksum attestation, and the rows regroup + replay through `OrderBook` without a
structural throw.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.archive.replay import regroup_messages, replay_segment, verify_replay
from cli.capture.segment_writer import BOOK_SCHEMA

H = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)


def _explode(pair: str, hour: datetime, messages: list[dict]) -> pl.DataFrame:
    """Fan each WS-shaped message out into one row per price level, exactly as the capture writer
    does (cli/capture/command.py:146-158): bids first, then asks, all rows sharing the message's
    `(ts, type, checksum)`."""
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
    """Write a committed canonical final (+ manifest sidecar) at the archive layout."""
    base, quote = pair.split("/")
    p = root / base / quote / "book" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(p, compression="zstd")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_name(p.name + ".sha256").write_text(f"{digest}  {p.name}\n")
    return p


def _coherent_messages() -> list[dict]:
    """One snapshot then three coherent updates — a replayable hour."""
    return [
        {
            "offset": 0,
            "type": "snapshot",
            "bids": [(100.0, 1.0), (99.0, 2.0)],
            "asks": [(101.0, 1.0), (102.0, 2.0)],
            "checksum": 11,
        },
        {"offset": 10, "type": "update", "bids": [(100.0, 0.5)], "asks": [], "checksum": 12},
        {"offset": 20, "type": "update", "bids": [], "asks": [(101.0, 0.0)], "checksum": 13},
        {"offset": 30, "type": "update", "bids": [(98.0, 3.0)], "asks": [(103.0, 1.5)], "checksum": 14},
    ]


# --- regroup: the exact inverse of the capture writer's per-level fan-out -------------------------


def test_regroup_reconstructs_ws_messages_in_order() -> None:
    frame = _explode(
        "BTC/EUR",
        H,
        [
            {"offset": 0, "type": "snapshot", "bids": [(100.0, 1.0), (99.0, 2.0)], "asks": [(101.0, 3.0)], "checksum": 7},
            {"offset": 5, "type": "update", "bids": [(100.0, 0.0)], "asks": [], "checksum": 8},
        ],
    )

    messages = regroup_messages(frame)

    assert len(messages) == 2
    first, second = messages
    assert first["type"] == "snapshot"
    assert first["checksum"] == 7
    assert first["bids"] == [{"price": 100.0, "qty": 1.0}, {"price": 99.0, "qty": 2.0}]
    assert first["asks"] == [{"price": 101.0, "qty": 3.0}]
    assert second["type"] == "update"
    assert second["checksum"] == 8
    assert second["bids"] == [{"price": 100.0, "qty": 0.0}]
    assert second["asks"] == []


# --- replay_segment: happy path --------------------------------------------------------------------


def test_replay_segment_happy_path(tmp_path: Path) -> None:
    frame = _explode("BTC/EUR", H, _coherent_messages())
    path = _book(tmp_path, "BTC/EUR", H, frame)

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.pair == "BTC/EUR"
    assert result.hour == H
    assert result.rows == frame.height
    assert result.messages == 4
    assert result.snapshot_anchored is True
    assert result.ts_ordered is True
    assert result.checksum_present is True
    assert result.replay_ok is True
    assert result.error is None


# --- replay_segment: anomalies ----------------------------------------------------------------------


def test_missing_leading_snapshot_is_flagged(tmp_path: Path) -> None:
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.snapshot_anchored is False
    # anchoring is its own verdict: updates onto an empty book are structurally fine
    assert result.replay_ok is True
    assert result.error is None


def test_unreadable_parquet_is_isolated_not_raised(tmp_path: Path) -> None:
    path = tmp_path / "BTC" / "EUR" / "book" / "2026" / "07" / "14" / "02.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a parquet file")

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.error is not None
    assert result.replay_ok is False


def test_out_of_order_ts_is_flagged(tmp_path: Path) -> None:
    messages = [
        {"offset": 10, "type": "snapshot", "bids": [(100.0, 1.0)], "asks": [(101.0, 1.0)], "checksum": 11},
        {"offset": 5, "type": "update", "bids": [(100.0, 0.5)], "asks": [], "checksum": 12},
    ]
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.ts_ordered is False
    assert result.snapshot_anchored is True  # the first message is still a snapshot


def test_null_checksum_is_flagged(tmp_path: Path) -> None:
    messages = _coherent_messages()
    messages[2]["checksum"] = None
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.checksum_present is False
    # a missing attestation is not a structural failure: the replay itself still runs
    assert result.replay_ok is True


def test_structural_ingest_throw_fails_replay(tmp_path: Path) -> None:
    messages = _coherent_messages()
    messages[1]["bids"] = [(None, 0.5)]  # a null price level: OrderBook's level parse raises
    path = _book(tmp_path, "BTC/EUR", H, _explode("BTC/EUR", H, messages))

    result = replay_segment(path, "BTC/EUR", depth=10)

    assert result.replay_ok is False
    assert result.error is not None
    assert result.snapshot_anchored is True  # the independent checks still report honestly


# --- verify_replay: the sweep -----------------------------------------------------------------------


def test_verify_replay_isolates_a_bad_hour_and_continues(tmp_path: Path) -> None:
    # The corrupt hour comes FIRST in the (pair, hour)-sorted sweep, so this proves a later good
    # hour still proceeds past it — not merely that the sweep survives a bad hour at the end.
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H + timedelta(hours=1), _explode("BTC/EUR", H + timedelta(hours=1), _coherent_messages()))
    corrupt = primary / "BTC" / "EUR" / "book" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H.hour:02d}.parquet"
    corrupt.write_bytes(b"junk")

    results = verify_replay(primary, None, depth=10)

    assert len(results) == 2
    by_hour = {r.hour: r for r in results}
    assert by_hour[H].error is not None
    assert by_hour[H + timedelta(hours=1)].error is None and by_hour[H + timedelta(hours=1)].replay_ok is True


def test_verify_replay_filters_pair_and_since(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    for pair in ("BTC/EUR", "ETH/EUR"):
        for hour in (H, H + timedelta(hours=1)):
            _book(primary, pair, hour, _explode(pair, hour, _coherent_messages()))

    only_btc = verify_replay(primary, None, pair="BTC/EUR", depth=10)
    assert {r.pair for r in only_btc} == {"BTC/EUR"} and len(only_btc) == 2

    only_late = verify_replay(primary, None, since=H + timedelta(hours=1), depth=10)
    assert {r.hour for r in only_late} == {H + timedelta(hours=1)} and len(only_late) == 2


def test_verify_replay_reads_reconciled_first(tmp_path: Path) -> None:
    primary, reconciled = tmp_path / "primary", tmp_path / "reconciled"
    # the primary's hour is NOT snapshot-anchored; the reconciled overlay's healed hour is
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))
    _book(reconciled, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    results = verify_replay(primary, reconciled, depth=10)

    assert len(results) == 1
    assert results[0].snapshot_anchored is True  # the overlay hour won, reconciled-first


# --- the CLI command ---------------------------------------------------------------------------------


def test_cli_verify_replay_clean_tree_exits_zero(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()))

    result = CliRunner().invoke(app, ["archive", "verify-replay", str(primary)])

    assert result.exit_code == 0, result.output
    assert "1 ok, 0 failed" in result.output


def test_cli_verify_replay_failing_hour_exits_nonzero(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _book(primary, "BTC/EUR", H, _explode("BTC/EUR", H, _coherent_messages()[1:]))  # not anchored

    result = CliRunner().invoke(app, ["archive", "verify-replay", str(primary)])

    assert result.exit_code == 1, result.output
    assert "FAILED" in result.output
