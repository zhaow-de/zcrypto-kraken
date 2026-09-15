"""`infra/scripts/continuity.py` as the operator runs it: `<root>` holds `<base>/<quote>/<kind>/YYYY/MM/DD/HH.parquet`
segments. A tree with none prints `no segments found` at exit 1; a `--since` past every hour prints `no segments in
the requested window` at exit 1, and neither prints a verdict. A dense book stream prints its row, the TOTAL row and
ONE `EXIT BAR` verdict at exit 0; `--overlay` appends a canonical report headed as informational that carries no
verdict of its own; `--quiet` drops the per-pair rows and keeps the summary; `--kind` picks the stream."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import polars as pl

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "continuity.py"
_H = dt.datetime(2026, 7, 20, 9, tzinfo=dt.UTC)
_VERDICT = "  EXIT BAR (<0.1% gap time): PASS"


def _hour(root: Path, pair: str, kind: str, hour: dt.datetime, stamps: list[dt.datetime]) -> None:
    base, quote = pair.split("/")
    d = root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"ts": pl.Series(stamps, dtype=pl.Datetime("us", "UTC"))}).write_parquet(d / f"{hour:%H}.parquet")


def _dense(root: Path, pair: str = "BTC/EUR", kind: str = "book") -> Path:
    """Two full hours at one-second spacing, enough intervals for the derived threshold to exist."""
    for k in range(2):
        h = _H + dt.timedelta(hours=k)
        _hour(root, pair, kind, h, [h + dt.timedelta(seconds=s) for s in range(3600)])
    return root


def _run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(_SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_an_empty_tree_reports_no_segments_and_no_verdict(tmp_path):
    done = _run(tmp_path)
    assert done.returncode == 1, done.stderr
    assert done.stdout.strip() == "no segments found" and "EXIT BAR" not in done.stdout


def test_a_window_past_every_hour_reports_the_empty_window_and_no_verdict(tmp_path):
    done = _run(_dense(tmp_path), "--since", "2030-01-01")
    assert done.returncode == 1, done.stderr
    assert "no segments in the requested window" in done.stdout and "EXIT BAR" not in done.stdout


def test_a_dense_stream_prints_its_row_the_total_and_one_verdict(tmp_path):
    done = _run(_dense(tmp_path))
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert any(line.startswith("BTC/EUR ") for line in lines) and any(line.startswith("TOTAL ") for line in lines)
    assert done.stdout.count("EXIT BAR") == 1 and _VERDICT in lines
    assert "  truncated hours: 0  -- MUST be 0 after the fix" in lines


def test_the_overlay_report_is_labelled_informational_and_carries_no_verdict(tmp_path):
    overlay = tmp_path / "reconciled"
    overlay.mkdir()
    done = _run(_dense(tmp_path / "raw"), "--overlay", overlay)
    assert done.returncode == 0, done.stderr
    banner = f"=== CANONICAL VIEW (reconciled-first, healed from {overlay}) -- informational only, NOT the exit-bar instrument ==="
    assert banner in done.stdout
    assert done.stdout.count("EXIT BAR") == 1 and done.stdout.index("EXIT BAR") < done.stdout.index(banner)
    assert done.stdout.count("TOTAL ") == 2


def test_quiet_drops_the_pair_rows_and_keeps_the_summary(tmp_path):
    done = _run(_dense(tmp_path), "--quiet")
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert not any(line.startswith("BTC/EUR ") for line in lines)
    assert any(line.startswith("TOTAL ") for line in lines) and _VERDICT in lines


def test_kind_selects_the_stream(tmp_path):
    done = _run(_dense(tmp_path), "--kind", "trades")
    assert done.returncode == 1 and done.stdout.strip() == "no segments found"
