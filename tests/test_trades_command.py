from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.segment_writer import TRADE_SCHEMA

runner = CliRunner()

H = datetime(2026, 7, 11, 2, tzinfo=UTC)
NOW = H + timedelta(hours=6)  # well past the settle rule, so hour H is eligible


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\x1b\[[0-9;]*m", "", s))


def _write_settled_hour(primary_root: Path, pair: str, hour: datetime, ids: list[int]) -> None:
    """A contiguous, duplicate-free trades hour -- no gap, so `backfill()` never calls `fetch()` and
    the test never risks a network call."""
    base, quote = pair.split("/")
    d = primary_root / base / quote / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
    d.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame(
        [
            {
                "ts": hour + timedelta(seconds=i),
                "symbol": pair,
                "side": "buy",
                "price": 1.0,
                "qty": 1.0,
                "ord_type": "market",
                "trade_id": t,
            }
            for i, t in enumerate(ids)
        ],
        schema=TRADE_SCHEMA,
    )
    frame.write_parquet(d / f"{hour:%H}.parquet")


def test_help_lists_the_options():
    r = runner.invoke(app, ["archive", "backfill-trades", "--help"])
    assert r.exit_code == 0
    out = _plain(r.stdout)
    assert "--pair" in out and "--detect-only" in out


def test_missing_primary_root_exits_2(tmp_path):
    r = runner.invoke(app, ["archive", "backfill-trades", str(tmp_path / "nope"), str(tmp_path / "r")])
    assert r.exit_code == 2


def test_clean_sweep_echoes_every_counter_and_exits_zero(tmp_path):
    """No gap, no duplicate: the sweep still must echo EVERY bucket -- pairs, gaps_found,
    trades_missing, duplicate_rows_found, trades_recovered, trades_unrecoverable, trades_deferred,
    trades_fetch_failed, duplicates_collapsed, duplicates_cross_hour, hours_minted, errors -- so a
    hidden bucket can never silently misreport what was found or what was healed."""
    primary_root = tmp_path / "primary"
    reconciled_root = tmp_path / "reconciled"
    _write_settled_hour(primary_root, "BTC/EUR", H, [10, 11, 12])

    # --log-level ERROR: `backfill()` logs this exact same summary via its own logger at INFO, and
    # with no `--log <path>` the default is plain-text-to-stdout (see README) -- without silencing it
    # the assertions below would pass off that duplicate line even if the CLI's own echo dropped a
    # bucket. Raising the threshold isolates the command's own `typer.echo`.
    r = runner.invoke(app, ["--log-level", "ERROR", "archive", "backfill-trades", str(primary_root), str(reconciled_root)])
    assert r.exit_code == 0
    out = _plain(r.stdout)
    assert "pairs=1" in out
    assert "gaps=0" in out
    assert "trades_missing=0" in out
    assert "duplicate_rows_found=0" in out
    assert "recovered=0" in out
    assert "unrecoverable=0" in out
    assert "deferred=0" in out
    assert "fetch_failed=0" in out  # T0078: the bucket exists even when empty
    assert "duplicates_collapsed=0" in out
    assert "duplicates_cross_hour=0" in out
    assert "hours_minted=0" in out
    assert "errors=0" in out
