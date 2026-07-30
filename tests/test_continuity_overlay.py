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
import pytest

from cli.archive.settle import hour_path

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "continuity.py"
_spec = importlib.util.spec_from_file_location("continuity", _SCRIPT)
continuity = importlib.util.module_from_spec(_spec)
# Registered in sys.modules before exec: continuity.py's `from __future__ import annotations` makes
# dataclass field annotations strings, and `dataclasses` resolves those against
# `sys.modules[cls.__module__]` -- unregistered, that lookup is None and StreamTimeline's
# decoration crashes (see tests/test_infra_continuity.py's `_load()`, same fix).
sys.modules[_spec.name] = continuity
_spec.loader.exec_module(continuity)

H = datetime(2026, 7, 20, 9, tzinfo=UTC)


def _write_hour(root: Path, pair: str, kind: str, hour: datetime, *, stamps: list[datetime]) -> None:
    path = hour_path(root, pair, kind, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"ts": stamps}).write_parquet(path)


def _dense_stream(root: Path, pair: str, kind: str = "book") -> None:
    """Two full hours at 1 s spacing -- comfortably clears D6's MIN_POOL (5,002 pooled intervals)
    without asserting a specific threshold value, unlike `_two_streams` below."""
    _write_hour(root, pair, kind, H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 1)])
    h1 = H + timedelta(hours=1)
    _write_hour(root, pair, kind, h1, stamps=[h1 + timedelta(seconds=s) for s in range(0, 3600, 1)])


def test_continuity_overlay_is_off_by_default():
    a = argparse.ArgumentParser()
    continuity.add_args(a)
    assert a.parse_args(["/tmp/root"]).overlay is None  # exit-bar isolation


def test_default_invocation_has_no_canonical_section(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw"
    _dense_stream(raw, "BTC/EUR")
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw)])

    rc = continuity.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "CANONICAL" not in out
    assert out.count("EXIT BAR") == 1


def test_overlay_mode_adds_a_separate_canonical_section_without_the_exit_bar_verdict(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw"
    overlay = tmp_path / "overlay"
    _dense_stream(raw, "BTC/EUR")
    # ETH/EUR exists ONLY in the overlay -- a primary hour healed wholesale from the secondary. Left
    # sparse (120 rows/hour, under MIN_POOL): the canonical view reports it UNMEASURED, but the pair
    # name still prints on its row -- this test only checks presence, not a measured threshold.
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


def test_an_empty_raw_tree_still_prints_the_canonical_section(tmp_path, capsys, monkeypatch):
    # The raw mirror being empty is exactly when the overlay's healed hours matter most; the raw
    # report's own failure (rc 1, "no segments found") must not swallow the canonical view.
    raw = tmp_path / "raw"
    raw.mkdir()
    overlay = tmp_path / "overlay"
    _write_hour(overlay, "ETH/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 30)])
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw), "--overlay", str(overlay)])

    rc = continuity.main()
    out = capsys.readouterr().out

    assert rc == 1  # the raw report's verdict is still the exit status
    assert "CANONICAL" in out
    assert "ETH/EUR" in out


# --- the report's two blind spots (T0097) ---------------------------------------------------------


def test_a_window_with_no_data_reports_it_instead_of_dividing_by_zero(tmp_path, capsys, monkeypatch):
    """`--since` filters per stream, well after the empty-tree guard, so a window that excludes every
    hour leaves `totals` empty and the TOTAL row divides by zero. Reproduced: the operator got a
    traceback where a plain "nothing in this window" belongs -- and a traceback from a verification
    tool reads as "the tool is broken", not as "you asked about a window with no data"."""
    raw = tmp_path / "raw"
    _write_hour(raw, "BTC/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 30)])
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw), "--since", "2026-07-25"])

    rc = continuity.main()
    out = capsys.readouterr().out

    assert rc != 0, "an answer about no data is not a PASS"
    assert "no segments" in out
    assert "EXIT BAR" not in out, "nothing was measured, so nothing may bank a verdict"


def _column(out: str, prefix: str, field: str) -> str:
    """The value under `field` on the row starting with `prefix`, located via the HEADER rather than
    a fixed index -- so a column reorder is a test failure instead of a silently-passing assertion
    about whatever now sits in slot N."""
    lines = out.splitlines()
    header = next(line for line in lines if field in line)
    row = next(line for line in lines if line.startswith(prefix))
    return row.split()[header.split().index(field)]


def _two_streams(raw):
    """BTC/EUR: 1 s spacing, hour H packed full plus 2,400 rows of H+1 -- 5,999 pooled intervals, all
    1.0 s apart, so p99.99 == 1.0 and the derived threshold is 10.0. ADA/EUR: 2 s spacing, three FULL
    hours -- 5,399 pooled intervals, all 2.0 s apart, threshold 20.0. Both clear D6's MIN_POOL (5,002)
    with margin; the two streams' different spacings are what makes their derived thresholds differ,
    which is the property this fixture exists to demonstrate."""
    h1 = H + timedelta(hours=1)
    h2 = H + timedelta(hours=2)
    _write_hour(raw, "BTC/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 1)])
    _write_hour(raw, "BTC/EUR", "book", h1, stamps=[h1 + timedelta(seconds=s) for s in range(0, 2400, 1)])
    _write_hour(raw, "ADA/EUR", "book", H, stamps=[H + timedelta(seconds=s) for s in range(0, 3600, 2)])
    _write_hour(raw, "ADA/EUR", "book", h1, stamps=[h1 + timedelta(seconds=s) for s in range(0, 3600, 2)])
    _write_hour(raw, "ADA/EUR", "book", h2, stamps=[h2 + timedelta(seconds=s) for s in range(0, 3600, 2)])


def test_the_table_prints_the_threshold_that_produced_each_gap(tmp_path, capsys, monkeypatch):
    """The silence threshold is derived per pair from that pair's own spacing, so a `0.0000%` can
    mean "no silence" or "the threshold is so wide nothing counts as silence". Printing the number
    beside the percentage it produced is what lets an operator disbelieve the zero.

    The EXACT derived values are asserted, not "some number above 100": this topic's own failure
    mode is a threshold so wide that silence stops being detectable, and a `> 100` assertion passes
    happily with the 5 s floor raised to 5000. These two streams also demonstrate the spread the
    column exists to show -- same tool, 2x apart on spacing alone, thresholds 2x apart to match.
    """
    raw = tmp_path / "raw"
    _two_streams(raw)
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw)])

    rc = continuity.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "thresh_s" in out
    assert float(_column(out, "BTC/EUR", "thresh_s")) == pytest.approx(10.0)  # 1 s spacing
    assert float(_column(out, "ADA/EUR", "thresh_s")) == pytest.approx(20.0)  # 2 s spacing


def test_the_total_row_never_fabricates_a_threshold(tmp_path, capsys, monkeypatch):
    """The threshold is per pair. Averaging them into the TOTAL row would invent a number that
    describes no stream -- the same "statistic nobody can disbelieve" shape this column exists to
    remove -- so that one slot stays blank while every other total is real."""
    raw = tmp_path / "raw"
    _two_streams(raw)
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw)])

    continuity.main()
    out = capsys.readouterr().out
    lines = out.splitlines()
    header = next(line for line in lines if "thresh_s" in line)
    total = next(line for line in lines if line.startswith("TOTAL"))
    lo = header.index("thresh_s")

    assert total[lo : lo + len("thresh_s")].strip() == "", f"the TOTAL row printed a threshold: {total!r}"


def test_quiet_mode_drops_the_per_pair_rows_and_keeps_the_total(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw"
    _dense_stream(raw, "BTC/EUR")
    monkeypatch.setattr(sys, "argv", ["continuity.py", str(raw), "--quiet"])

    rc = continuity.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert not any(line.startswith("BTC/EUR") for line in out.splitlines())
    assert "TOTAL" in out
