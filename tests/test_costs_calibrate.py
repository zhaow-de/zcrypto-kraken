"""TDD for `cli/costs/calibrate.py` -- the committed spread-calibration query (spec 00085 D5).

Replaces the prose query at `docs/reference/captured-spread-calibration.md` with runnable code.
Task 7 restamps `cli/costs/spread.py`'s calibration constants from this module's output.
"""

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
    W_END = datetime(2026, 7, 24, 2, tzinfo=timezone.utc)
    for h in (0, 1):
        _panel_hour(panel_root, "BTC/EUR", W_START + timedelta(hours=h), mid=60_000.0, fill=1.5)
        _panel_hour(panel_root, "ETH/BTC", W_START + timedelta(hours=h), mid=0.03, fill=2.5)

    expected_mean_mid = 60_000.0
    result = calibrate(panel_root, W_START, W_END)
    assert set(result.table) == {"BTC/EUR", "ETH/BTC"}
    assert set(result.table["ETH/BTC"]) == {100, 1_000, 10_000}
    assert result.hours == 2  # hourly files PER PAIR, not 2 pairs x 2 hours
    # Joint-sampling: the doc's provenance rests on row counts agreeing across pairs. A bare
    # `min_rows > 0` would sail straight through a partial NAS pull of the two new legs.
    assert result.max_rows - result.min_rows <= 5
    # The FX reference is derived from BTC/EUR mids in the same window, not hardcoded.
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
    """Distinct from the key-absent case above: here a BTC/EUR hour FILE overlaps the window (so a
    naive `"BTC/EUR" in table` check would pass), but every row it actually holds falls outside
    [window_start, window_end] -- the archive-gap case a sub-hour window can land in. Before the fix
    this returned an unpinned table (btc_eur_reference=None, all-None cells, min_rows=0) instead of
    refusing.
    """
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

    # Overlaps the file's [HH:00, HH+1:00) hour interval (so the file is scanned) but lands
    # entirely after the last actual row -- zero rows inside the window.
    window_start = hour + timedelta(seconds=20)
    window_end = hour + timedelta(seconds=30)

    with pytest.raises(CostModelError, match="no BTC/EUR"):
        calibrate(panel_root, window_start, window_end)


def test_the_committed_script_reproduces_the_table_it_replaces():
    """The script becomes the provenance of record (spec D5), and Task 7 replaces all ten EUR rows
    in the same commit that introduces it -- so a transcription error and the window move would be
    indistinguishable in one diff. Run it over the OLD window and require the OLD table.

    Marked slow: it reads the real panel tree from the read-only NAS mount.
    """
    from cli.costs.spread import CALIBRATION_HOURS, CALIBRATION_MIN_ROWS, CALIBRATION_WINDOW, SPREAD_CALIBRATION

    panel_root = Path("/mnt/zhao-crypto/l2-panel")
    if not panel_root.exists():
        pytest.skip("panel tree not mounted")

    start, end = (datetime.fromisoformat(w.replace("Z", "+00:00")) for w in CALIBRATION_WINDOW)
    result = calibrate(panel_root, start, end)

    # The table alone is structurally blind to a one-hour window error (a BTC@1k deviation of
    # 0.00029 from an `overlap` -> `start-inside` window-rule regression sits 34x inside the table's
    # own tolerance below) -- pin the two provenance constants Task 7 restamps from these fields too.
    assert result.hours == CALIBRATION_HOURS
    assert result.min_rows == CALIBRATION_MIN_ROWS
    # Joint-sampling, now measured on the REAL tree -- the synthetic fixture's delta is 0 by
    # construction and cannot fail this. The observed real-tree delta is exactly 5 today, so this
    # assertion sits on its own boundary with zero margin: a future one-row drift fails it. That is
    # the doc's own bar ("row counts agree to within 5 rows"), not ours to loosen.
    assert result.max_rows - result.min_rows <= 5

    for base, rows in SPREAD_CALIBRATION.items():  # pre-re-key: base-keyed
        for size, expected in rows.items():
            # Exact-on-rounding, not a fixed abs-tolerance: the committed table is rounded to 3
            # decimals, so the rounding floor is 0.0005 and no threshold >= that can catch a
            # last-digit transcription error (measured: worst deviation 0.000457 bps across all 30
            # cells today, so this holds with room to spare).
            assert round(result.table[f"{base}/EUR"][size], 3) == expected
