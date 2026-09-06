"""TDD for `infra/scripts/gap_distribution.py` — the Task-12 (spec 00050) instrument that pins
`--min-gap-seconds` from the real cross-host data.

Loaded via importlib because it is a standalone script, not a package module.
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "gap_distribution.py"
_spec = importlib.util.spec_from_file_location("gap_distribution", _SCRIPT)
gd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gd)

H = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)


def _book(root: Path, pair: str, hour: datetime, offsets_types: list[tuple[float, str]]) -> None:
    base, quote = pair.split("/")
    p = root / base / quote / "book" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=o) for o, _ in offsets_types],
            "symbol": [pair] * len(offsets_types),
            "type": [t for _, t in offsets_types],
            "side": ["bid"] * len(offsets_types),
            "price": [1.0] * len(offsets_types),
            "qty": [1.0] * len(offsets_types),
            "checksum": [0] * len(offsets_types),
        }
    ).write_parquet(p, compression="zstd")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_name(p.name + ".sha256").write_text(f"{digest}  {p.name}\n")


# --- summarize (pure) ----------------------------------------------------------------------------


def test_summarize_empty_is_honest_about_no_data() -> None:
    s = gd.summarize([])
    assert s["n"] == 0
    assert s["suggested_min_gap_seconds"] is None  # nothing to base a threshold on


def test_summarize_percentiles_and_suggestion() -> None:
    seconds = [10.0] * 90 + [float(x) for x in range(11, 21)]
    s = gd.summarize(seconds)

    assert s["n"] == 100
    assert s["p50"] == 10.0
    assert s["p90"] == 10.0
    assert s["p99"] == 19.0
    assert s["p99_9"] == 20.0
    assert s["max"] == 20.0
    # ceil(2 * max): the 2x-margin rule the current default came from, now from measured data.
    assert s["suggested_min_gap_seconds"] == 40.0


def test_summarize_suggestion_rounds_up_so_it_never_sits_below_2x_max() -> None:
    s = gd.summarize([14.78])
    assert s["max"] == 14.78
    assert s["suggested_min_gap_seconds"] == 30.0  # ceil(2 * 14.78) = 30, matching the current default


# --- observe_gaps (reads the raw mirrors) --------------------------------------------------------


def test_observe_gaps_finds_primary_silence_the_secondary_witnessed(tmp_path: Path) -> None:
    pri, sec = tmp_path / "primary", tmp_path / "secondary"
    _book(pri, "BTC/EUR", H, [(0, "update"), (120, "update"), (3599, "update")])
    _book(sec, "BTC/EUR", H, [(0, "update"), (40, "update"), (80, "update"), (120, "update"), (3599, "update")])

    obs, skipped = gd.observe_gaps(pri, sec, probe_seconds=0.0)

    assert skipped == []
    assert [pair for pair, _h, _s in obs] == ["BTC/EUR"]
    assert len(obs) == 1
    assert obs[0][2] == 120.0


def test_observe_gaps_only_uses_hours_present_in_BOTH_mirrors(tmp_path: Path) -> None:
    pri, sec = tmp_path / "primary", tmp_path / "secondary"
    # The primary has an EARLIER hour the secondary never captured (bring-up): it must be ignored,
    # or every pre-secondary hour would look like a huge primary-only "gap" and poison the threshold.
    _book(pri, "BTC/EUR", H - timedelta(hours=1), [(0, "update"), (1800, "update")])
    _book(pri, "BTC/EUR", H, [(0, "update"), (60, "update")])
    _book(sec, "BTC/EUR", H, [(0, "update"), (30, "update"), (60, "update")])

    obs, _skipped = gd.observe_gaps(pri, sec, probe_seconds=0.0)

    assert all(h == H for _p, h, _s in obs), "a pre-secondary hour leaked into the distribution"


# --- _report -------------------------------------------------------------------------------------


def test_report_surfaces_the_max_window_even_when_it_is_below_the_review_ceiling() -> None:
    obs = [("BTC/EUR", H, 12.0), ("ETH/EUR", H, 83.0)]  # max 83 s, under a 120 s ceiling

    report = gd._report(obs, review_ceiling=120.0, top=20, skipped=[])

    assert "83.00s" in report and "ETH/EUR" in report, "the max-driving window was hidden"
    assert "SUGGESTED --min-gap-seconds : 166" in report  # ceil(2 * 83)
    assert "reboot" in report.lower(), "the report must name the reboot as the canonical benign window"


def test_report_flags_skipped_hours_loudly_as_incomplete() -> None:
    obs = [("BTC/EUR", H, 12.0)]
    skipped = [("ETH/EUR", H, "CaptureError: non-monotonic ts")]

    report = gd._report(obs, review_ceiling=120.0, top=20, skipped=skipped)

    assert "SKIPPED" in report and "INCOMPLETE" in report
    assert "ETH/EUR" in report and "non-monotonic" in report


def test_observe_gaps_isolates_a_corrupt_hour_instead_of_aborting_the_run(tmp_path: Path) -> None:
    pri, sec = tmp_path / "primary", tmp_path / "secondary"
    _book(pri, "BTC/EUR", H, [(0, "update"), (120, "update")])
    _book(sec, "BTC/EUR", H, [(0, "update"), (60, "update"), (120, "update")])
    _book(pri, "BTC/EUR", H + timedelta(hours=1), [(0, "update")])
    _book(sec, "BTC/EUR", H + timedelta(hours=1), [(0, "update")])
    corrupt = pri / "BTC" / "EUR" / "book" / f"{H:%Y}" / f"{H:%m}" / f"{H:%d}" / f"{H.hour + 1:02d}.parquet"
    corrupt.write_bytes(b"not a parquet file")

    obs, skipped = gd.observe_gaps(pri, sec, probe_seconds=0.0)

    assert any(g == 120.0 for _p, _h, g in obs), "the good hour was still measured"
    assert len(skipped) == 1 and skipped[0][0] == "BTC/EUR", "the corrupt hour was recorded, not fatal"
