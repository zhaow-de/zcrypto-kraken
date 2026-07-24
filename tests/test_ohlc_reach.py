from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from cli.ohlc.dataset import read_parquet, write_parquet
from cli.ohlc.errors import OHLCError
from cli.ohlc.reach import MIN_SEAM_OVERLAP, reach_round

# One hour in seconds; the tests use the 60-minute grid because that is the interval whose REST
# window is the first to stop reaching the canonical tail (the case this module exists for).
_HOUR = 3600
_BASE = datetime(2026, 3, 1, tzinfo=UTC)


def _rest_rows(start: datetime, n: int, *, interval_s: int = _HOUR, close: float = 100.0) -> list[list]:
    """Kraken's OHLC row shape: [ts, open, high, low, close, vwap, volume, count]."""
    rows = []
    for i in range(n):
        ts = int((start + timedelta(seconds=interval_s * i)).timestamp())
        rows.append([ts, "1.0", "2.0", "0.5", f"{close + i}", "1.5", "10.0", 3])
    return rows


def _write_canonical(root, symbol: str, interval: int, start: datetime, n: int, *, close: float = 100.0) -> None:
    frame = pl.DataFrame(
        {
            "ts": [start + timedelta(minutes=interval * i) for i in range(n)],
            "open": [1.0] * n,
            "high": [2.0] * n,
            "low": [0.5] * n,
            "close": [close + i for i in range(n)],
            "vwap": [1.5] * n,
            "volume": [10.0] * n,
            "count": [3] * n,
        }
    ).with_columns(pl.col("ts").dt.cast_time_unit("us").dt.replace_time_zone("UTC"))
    write_parquet(frame, root / symbol / "EUR" / f"{interval}.parquet")


def _no_sleep(_seconds: float) -> None:
    """Tests must never pay the real inter-call pacing."""


def _fetcher(rows_by_key: dict[str, list[list]]):
    def _fetch(pair_key: str, interval: int) -> list[list]:
        return rows_by_key[pair_key]

    return _fetch


def test_overlapping_rest_tail_merges_into_one_continuous_series(tmp_path):
    """The canonical tail and the REST window overlap -> one continuous file a normal reader globs."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    # canonical: 20 hourly bars from _BASE (so its tail is _BASE + 19h)
    _write_canonical(canonical, "BTC", 60, _BASE, 20)
    # REST: starts 10 bars in (10 shared stamps) and runs 15 bars past the canonical tail
    rest = _rest_rows(_BASE + timedelta(hours=10), 25, close=110.0)
    now = _BASE + timedelta(hours=40)

    report = reach_round(canonical, out, fetch_fn=_fetcher({"XXBTZEUR": rest}), clock=lambda: now, sleep_fn=_no_sleep)

    (entry,) = report.entries
    assert entry.status == "continuous"
    assert entry.overlap_bars == 10
    assert entry.appended == 15

    merged = read_parquet(out / "BTC" / "EUR" / "60.parquet")
    assert merged.height == 35  # 20 canonical + 15 REST-only
    assert merged["ts"].is_sorted()
    assert merged["ts"].n_unique() == merged.height
    assert not (out / "BTC" / "EUR" / "60.detached.parquet").exists()

    # An all-continuous set must report NO detached hash -- an empty string, not a hash of nothing.
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["basket_sha256"]
    assert manifest["detached_sha256"] == ""


def test_detached_tail_is_kept_but_under_a_name_canonical_readers_do_not_glob(tmp_path):
    """The REST window no longer reaches the canonical tail.

    The bars must still be written -- they expire from the endpoint as the window recedes -- but they
    must NOT land where an ohlc-full reader would splice them across the gap.
    """
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "BTC", 60, _BASE, 20)  # tail at _BASE + 19h
    # REST starts 100 h after the canonical tail: a real gap, no shared stamp
    rest_start = _BASE + timedelta(hours=119)
    rest = _rest_rows(rest_start, 30, close=500.0)
    now = rest_start + timedelta(hours=40)

    report = reach_round(canonical, out, fetch_fn=_fetcher({"XXBTZEUR": rest}), clock=lambda: now, sleep_fn=_no_sleep)

    (entry,) = report.entries
    assert entry.status == "detached"
    assert entry.overlap_bars == 0
    assert entry.gap_bars == 100  # (119 - 19) hourly stamps between the tail and the REST head

    detached = read_parquet(out / "BTC" / "EUR" / "60.detached.parquet")
    assert detached.height == 30
    # The continuous filename must be absent -- this is the structural guard, not a doc note.
    assert not (out / "BTC" / "EUR" / "60.parquet").exists()

    # Nothing was joinable, so the CONTINUOUS basket hash must be empty rather than quietly
    # hashing the detached segment -- the failure this split exists to prevent.
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["basket_sha256"] == ""
    assert manifest["detached_sha256"]


def test_seam_close_mismatch_aborts(tmp_path):
    """A shared stamp whose close disagrees means the two sources are not the same series."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "BTC", 60, _BASE, 20, close=100.0)
    # overlapping stamps, but closes are offset -> every shared stamp disagrees
    rest = _rest_rows(_BASE + timedelta(hours=10), 25, close=999.0)
    now = _BASE + timedelta(hours=40)

    with pytest.raises(OHLCError, match="seam mismatch"):
        reach_round(canonical, out, fetch_fn=_fetcher({"XXBTZEUR": rest}), clock=lambda: now, sleep_fn=_no_sleep)


def test_thin_overlap_aborts_rather_than_joining_on_one_bar(tmp_path):
    """An overlap below the floor is an unverified seam: refuse, don't guess."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "BTC", 60, _BASE, 20)  # tail at _BASE + 19h
    # start so that only 2 stamps are shared (< MIN_SEAM_OVERLAP)
    rest = _rest_rows(_BASE + timedelta(hours=18), 20, close=118.0)
    now = _BASE + timedelta(hours=45)

    assert MIN_SEAM_OVERLAP > 2
    with pytest.raises(OHLCError, match="seam too thin"):
        reach_round(canonical, out, fetch_fn=_fetcher({"XXBTZEUR": rest}), clock=lambda: now, sleep_fn=_no_sleep)


def test_in_progress_candle_is_dropped(tmp_path):
    """Kraken's last row is the currently-forming candle; it must never be persisted."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "BTC", 60, _BASE, 20)
    rest = _rest_rows(_BASE + timedelta(hours=10), 25, close=110.0)
    # `now` sits mid-way through the final REST bar, so that bar has not closed yet
    now = _BASE + timedelta(hours=34, minutes=30)

    report = reach_round(canonical, out, fetch_fn=_fetcher({"XXBTZEUR": rest}), clock=lambda: now, sleep_fn=_no_sleep)

    (entry,) = report.entries
    merged = read_parquet(out / "BTC" / "EUR" / "60.parquet")
    # the last REST stamp is _BASE+34h and closes at _BASE+35h > now -> excluded
    assert merged["ts"].max() == _BASE + timedelta(hours=33)
    assert entry.rest_last == _BASE + timedelta(hours=33)


def test_manifest_records_per_series_status_so_a_mixed_set_cannot_be_read_as_uniform(tmp_path):
    """A reach set is routinely mixed -- some intervals continuous, some detached. The manifest is
    where a consumer learns which, so it must carry the status per series, not one set-wide claim."""
    canonical, out = tmp_path / "canon", tmp_path / "out"
    _write_canonical(canonical, "BTC", 60, _BASE, 20)
    _write_canonical(canonical, "BTC", 240, _BASE, 20)
    now = _BASE + timedelta(days=30)

    def _fetch(pair_key: str, interval: int) -> list[list]:
        if interval == 240:  # overlaps the canonical tail -> continuous
            return _rest_rows(_BASE + timedelta(minutes=240 * 10), 25, interval_s=240 * 60, close=110.0)
        # 60m: starts well past the canonical tail -> detached
        return _rest_rows(_BASE + timedelta(hours=200), 30, close=500.0)

    report = reach_round(canonical, out, fetch_fn=_fetch, clock=lambda: now, sleep_fn=_no_sleep)

    manifest = json.loads((out / "manifest.json").read_text())
    # The continuous basket hash must NOT absorb the detached segment -- that split is the point.
    assert manifest["basket_sha256"]
    assert manifest["detached_sha256"]
    assert manifest["basket_sha256"] != manifest["detached_sha256"]
    assert all("sha256" in e and e["rows"] for e in manifest["series"])
    by_key = {(e["symbol"], e["interval"]): e for e in manifest["series"]}
    assert by_key[("BTC", 240)]["status"] == "continuous"
    assert by_key[("BTC", 60)]["status"] == "detached"
    assert {e.status for e in report.entries} == {"continuous", "detached"}
