"""TDD for `infra/scripts/continuity.py`'s `--overlay` mode (spec 00050).

`continuity.py` is a standalone script, not a package module, so it is loaded here via
`importlib.util.spec_from_file_location` rather than a normal import.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.settle import hour_path

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "continuity.py"
_spec = importlib.util.spec_from_file_location("continuity", _SCRIPT)
continuity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(continuity)

H = datetime(2026, 7, 20, 9, tzinfo=UTC)


def _write_hour(root: Path, pair: str, kind: str, hour: datetime, *, stamps: list[datetime]) -> None:
    path = hour_path(root, pair, kind, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"ts": stamps}).write_parquet(path)


def test_continuity_overlay_is_off_by_default():
    a = argparse.ArgumentParser()
    continuity.add_args(a)
    assert a.parse_args(["/tmp/root"]).overlay is None  # exit-bar isolation


def test_default_invocation_has_no_canonical_section(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw"
    _write_hour(raw, "BTC/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 30)])
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw)])

    rc = continuity.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "CANONICAL" not in out
    assert out.count("EXIT BAR") == 1


def test_overlay_mode_adds_a_separate_canonical_section_without_the_exit_bar_verdict(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw"
    overlay = tmp_path / "overlay"
    _write_hour(raw, "BTC/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 30)])
    # ETH/EUR exists ONLY in the overlay -- a primary hour healed wholesale from the secondary.
    _write_hour(overlay, "ETH/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 30)])
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw), "--overlay", str(overlay)])

    rc = continuity.main()
    out = capsys.readouterr().out
    raw_section, _, canonical_section = out.partition("CANONICAL")

    assert rc == 0
    assert canonical_section  # the overlay section printed at all
    assert "BTC/EUR" in raw_section
    assert "ETH/EUR" not in raw_section  # raw report untouched by the overlay
    assert "ETH/EUR" in canonical_section  # canonical view picks up the healed-only hour
    assert raw_section.count("EXIT BAR") == 1  # only the raw report is the T0003 instrument
    assert "EXIT BAR" not in canonical_section
