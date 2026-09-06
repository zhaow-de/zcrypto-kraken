"""TDD for `cli/costs/calibrate.py` -- the committed spread-calibration query (spec 00085 D5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from cli.costs.calibrate import calibrate


def _panel_hour(root: Path, pair: str, hour: datetime, *, mid: float, fill: float) -> None:
    base, quote = pair.split("/")
    p = root / base / quote / "panel-1s" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 3600
    pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=i) for i in range(n)],
            "mid": [mid] * n,
            **{f"fill_bps_{side}_{sfx}": [fill] * n for side in ("bid", "ask") for sfx in ("100", "1k", "10k")},
        }
    ).write_parquet(p)


def test_calibrate_produces_full_symbol_keys_and_provenance(tmp_path: Path) -> None:
    panel_root = tmp_path / "l2-panel"
    W_START = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    W_END = datetime(2026, 7, 24, 3, tzinfo=timezone.utc)
    for h in (0, 1, 2):
        _panel_hour(panel_root, "BTC/EUR", W_START + timedelta(hours=h), mid=60_000.0, fill=1.5)
    for h in (0, 1):  # one hour short of BTC/EUR -- models a partial NAS pull of this leg
        _panel_hour(panel_root, "ETH/BTC", W_START + timedelta(hours=h), mid=0.03, fill=2.5)

    expected_mean_mid = 60_000.0
    result = calibrate(panel_root, W_START, W_END)
    assert set(result.table) == {"BTC/EUR", "ETH/BTC"}
    assert set(result.table["ETH/BTC"]) == {100, 1_000, 10_000}
    # hourly files PER PAIR: the MIN across pairs (BTC/EUR has 3, ETH/BTC has 2) -- not the max (3)
    # and not the sum (5), either of which a summed- or max-reading restamp would silently produce.
    assert result.hours == 2
    # Joint sampling on UNEQUAL coverage: a fixture where every pair matches is degenerate here, and
    # the nonzero row-count spread is what a partial NAS pull of one leg looks like.
    assert result.min_rows == 7_200  # ETH/BTC: 2 hours x 3600 rows/hour
    assert result.max_rows == 10_800  # BTC/EUR: 3 hours x 3600 rows/hour
    assert result.btc_eur_reference == pytest.approx(expected_mean_mid, rel=1e-9)


def test_calibrate_refuses_a_window_with_no_btc_eur_data(tmp_path: Path) -> None:
    # The FX reference has no source without BTC/EUR -- refuse rather than emit an unpinned table.
    from cli.costs.errors import CostModelError  # check the real module; spread.py imports it too

    panel_root = tmp_path / "l2-panel"
    W_START = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    W_END = datetime(2026, 7, 24, 2, tzinfo=timezone.utc)
    for h in (0, 1):
        _panel_hour(panel_root, "ETH/BTC", W_START + timedelta(hours=h), mid=0.03, fill=2.5)

    with pytest.raises(CostModelError, match="no BTC/EUR"):
        calibrate(panel_root, W_START, W_END)


def test_calibrate_refuses_when_the_only_btc_eur_rows_fall_outside_the_window(tmp_path: Path) -> None:
    """A BTC/EUR hour FILE overlaps the window -- so a naive `"BTC/EUR" in table` check passes --
    while every row it holds falls outside [window_start, window_end], the archive-gap case a
    sub-hour window can land in. It must refuse."""
    from cli.costs.errors import CostModelError

    panel_root = tmp_path / "l2-panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    p = panel_root / "BTC" / "EUR" / "panel-1s" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 10  # only the first 10 seconds of the hour have data -- a real archive gap for the rest
    pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=i) for i in range(n)],
            "mid": [60_000.0] * n,
            **{f"fill_bps_{side}_{sfx}": [1.5] * n for side in ("bid", "ask") for sfx in ("100", "1k", "10k")},
        }
    ).write_parquet(p)

    window_start = hour + timedelta(seconds=20)
    window_end = hour + timedelta(seconds=30)

    with pytest.raises(CostModelError, match="no BTC/EUR"):
        calibrate(panel_root, window_start, window_end)


def test_calibrate_ignores_a_year_directory_that_is_not_a_date(tmp_path: Path) -> None:
    # Both arms leave `_hourly_files_in_window`, and `calibrate` with it, if the guard names one:
    # `int("nope")` raises ValueError, while `datetime()` narrows the year to a C int, so a `<YYYY>`
    # directory at 2**31 exactly raises OverflowError instead.
    panel_root = tmp_path / "l2-panel"
    W_START = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    W_END = datetime(2026, 7, 24, 2, tzinfo=timezone.utc)
    for h in (0, 1):
        _panel_hour(panel_root, "BTC/EUR", W_START + timedelta(hours=h), mid=60_000.0, fill=1.5)
    for year in (str(2**31), "nope"):
        stray = panel_root / "BTC" / "EUR" / "panel-1s" / year / "01" / "01" / "00.parquet"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"garbage under a year directory no writer of ours can produce")

    result = calibrate(panel_root, W_START, W_END)

    # Exactly the two well-formed hours: neither stray contributes one, and neither takes one with it.
    assert result.hours == 2
    assert result.min_rows == result.max_rows == 7_200
    assert result.table["BTC/EUR"][100] == pytest.approx(1.5)


def test_the_committed_script_reproduces_the_table_it_replaces():
    """The committed script (spec 00085 D5) over the SUPERSEDED window must still reproduce the
    SUPERSEDED table and provenance: the standing control that attributes a restamp's move to the
    WINDOW rather than to the calibration path. Window, provenance and table are LITERALS, not imports --
    importing the module's now-current constants would make the control follow the restamp it checks."""
    superseded_window = ("2026-07-08T13:47:33Z", "2026-07-23T05:59:59Z")
    superseded_hours = 353
    superseded_min_rows = 1_260_309
    superseded_table = {
        "BTC": {100: 0.260, 1_000: 0.386, 10_000: 0.625},
        "ETH": {100: 0.420, 1_000: 0.486, 10_000: 0.686},
        "XRP": {100: 0.758, 1_000: 1.116, 10_000: 2.071},
        "SOL": {100: 0.922, 1_000: 1.029, 10_000: 1.822},
        "DOGE": {100: 1.721, 1_000: 1.853, 10_000: 3.741},
        "LINK": {100: 2.207, 1_000: 2.367, 10_000: 3.704},
        "LTC": {100: 2.036, 1_000: 3.022, 10_000: 5.237},
        "ADA": {100: 2.180, 1_000: 2.459, 10_000: 5.365},
        "AVAX": {100: 2.408, 1_000: 2.858, 10_000: 5.863},
        "DOT": {100: 3.579, 1_000: 5.405, 10_000: 12.223},
    }

    panel_root = Path("/mnt/zhao-crypto/l2-panel")
    if not panel_root.exists():
        pytest.skip("panel tree not mounted")

    start, end = (datetime.fromisoformat(w.replace("Z", "+00:00")) for w in superseded_window)
    result = calibrate(panel_root, start, end)

    # The table alone is structurally blind to a one-hour window error -- pin the two provenance
    # constants restamped from these fields too.
    assert result.hours == superseded_hours
    assert result.min_rows == superseded_min_rows
    # Joint sampling, measured on the REAL tree: the synthetic fixture's delta is 0 by construction
    # and cannot fail this. The 5-row bound is spec 00066's joint-sampling figure, not ours to loosen.
    assert result.max_rows - result.min_rows <= 5

    for base, rows in superseded_table.items():  # base-keyed, as the table was before the re-key
        for size, expected in rows.items():
            # Exact-on-rounding, not a fixed abs-tolerance: the table is rounded to 3 decimals, so
            # any tolerance at or above the 0.0005 rounding floor is blind to a last-digit
            # transcription error.
            assert round(result.table[f"{base}/EUR"][size], 3) == expected
