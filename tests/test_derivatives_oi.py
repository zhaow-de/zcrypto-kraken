from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.config import load_config, resolve_hot_source
from cli.derivatives.errors import DerivativesError
from cli.derivatives.funding import PERP_SYMBOLS
from cli.derivatives.oi import (
    backfill_oi,
    build_oi_substrate,
    fetch_oi_day,
    read_oi_series,
)
from cli.ohlc.dataset import write_parquet

_HEADER = (
    "create_time,symbol,sum_open_interest,sum_open_interest_value,"
    "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
    "count_long_short_ratio,sum_taker_long_short_vol_ratio"
)


def _metrics_csv(day: str, symbol: str, n: int = 3, oi0: int = 100) -> str:
    """A metrics CSV: `n` 5-minute rows on `day`, mirroring the real Binance Vision schema."""
    lines = [_HEADER]
    for i in range(n):
        hh, mm = divmod(i * 5, 60)
        oi = oi0 + i
        lines.append(f"{day} {hh:02d}:{mm:02d}:00,{symbol},{oi}.5,{oi * 1000}.0,2.1,1.2,2.0,0.94")
    return "\n".join(lines) + "\n"


def _zip_of(csv_text: str, member: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(member, csv_text)
    return buf.getvalue()


class _Opener:
    """A urlopen stand-in serving a fixed {url: bytes} map; 404s anything absent, and derives each
    `.CHECKSUM` from the real sha256 of its zip so the verify path is exercised, not bypassed."""

    def __init__(self, files: dict[str, bytes]):
        self._files = dict(files)
        for url, body in list(files.items()):
            if url.endswith(".zip"):
                digest = hashlib.sha256(body).hexdigest()
                name = url.rsplit("/", 1)[-1]
                self._files.setdefault(url + ".CHECKSUM", f"{digest}  {name}\n".encode())

    def __call__(self, url, timeout=None):
        if url not in self._files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _Resp(self._files[url])


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _day_url(perp: str, day: str) -> str:
    return f"https://data.binance.vision/data/futures/um/daily/metrics/{perp}/{perp}-metrics-{day}.zip"


def test_fetch_oi_day_verifies_checksum_and_parses_metrics(tmp_path):
    csv = _metrics_csv("2026-06-30", "BTCUSDT", n=3)
    opener = _Opener({_day_url("BTCUSDT", "2026-06-30"): _zip_of(csv, "BTCUSDT-metrics-2026-06-30.csv")})

    rows = fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=opener)

    assert rows is not None and len(rows) == 3
    first = rows[0]
    assert first[1] == 100.5  # sum_open_interest
    assert first[2] == 100000.0  # sum_open_interest_value


def test_missing_day_returns_none_not_error(tmp_path):
    opener = _Opener({})  # every URL 404s
    assert fetch_oi_day("BTCUSDT", datetime(2020, 1, 1, tzinfo=UTC), opener=opener) is None


def test_transient_5xx_is_retried_then_succeeds(tmp_path, monkeypatch):
    """data.binance.vision 503s intermittently under a long backfill, so a 5xx is retried rather
    than aborting the run."""
    monkeypatch.setattr("cli.derivatives.oi._RETRY_BACKOFF_SECONDS", 0.0)  # no real sleep in the test
    url = _day_url("BTCUSDT", "2026-06-30")
    base = _Opener({url: _zip_of(_metrics_csv("2026-06-30", "BTCUSDT"), "m.csv")})
    calls = {"zip": 0}

    def _flaky(u, timeout=None):
        if u == url:
            calls["zip"] += 1
            if calls["zip"] <= 2:  # 503 the first two zip requests, then serve for real
                raise urllib.error.HTTPError(u, 503, "Service Unavailable", {}, None)
        return base(u, timeout)

    rows = fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=_flaky)
    assert rows is not None and len(rows) == 3
    assert calls["zip"] == 3  # 2 transient failures + 1 success


def test_persistent_5xx_exhausts_retries_and_raises(tmp_path, monkeypatch):
    """A 5xx that never clears is a real outage -- retries exhaust and it fails loud, not silently."""
    monkeypatch.setattr("cli.derivatives.oi._RETRY_BACKOFF_SECONDS", 0.0)

    def _always_503(u, timeout=None):
        raise urllib.error.HTTPError(u, 503, "Service Unavailable", {}, None)

    with pytest.raises(DerivativesError, match="transport error"):
        fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=_always_503)


def test_empty_ancillary_field_becomes_null_not_a_crash(tmp_path):
    """Real early metrics (e.g. BTCUSDT 2020-09-27) leave the taker ratio blank on some rows while
    the OI columns are populated. A missing auxiliary value must keep the row, not abort the run."""
    good = "2026-06-30 00:00:00,BTCUSDT,100.5,100000.0,2.1,1.2,2.0,0.94"
    blank_taker = "2026-06-30 00:05:00,BTCUSDT,101.5,101000.0,2.1,1.2,2.0,"  # trailing empty field
    csv = _HEADER + "\n" + good + "\n" + blank_taker + "\n"
    opener = _Opener({_day_url("BTCUSDT", "2026-06-30"): _zip_of(csv, "m.csv")})

    rows = fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=opener)

    assert rows is not None and len(rows) == 2
    assert rows[0][6] == 0.94  # taker ratio present on the good row
    assert rows[1][6] is None  # blank taker -> null, but the row (with valid OI) is kept
    assert rows[1][1] == 101.5  # the OI reading survives


def test_quoted_empty_ancillary_fields_become_null(tmp_path):
    """The other real absent-form: BTCUSDT 2021-12-30 carries `""` (quoted-empty) in all four ratio
    columns while OI is populated. Both absent forms must map to null, not crash."""
    row = '2026-06-30 00:00:00,BTCUSDT,72516.054,3437120278.45,"","","",""'
    csv = _HEADER + "\n" + row + "\n"
    opener = _Opener({_day_url("BTCUSDT", "2026-06-30"): _zip_of(csv, "m.csv")})

    rows = fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=opener)

    assert rows is not None and len(rows) == 1
    assert rows[0][1] == 72516.054  # OI present
    assert rows[0][2] == 3437120278.45  # OI value present
    assert rows[0][3:] == [None, None, None, None]  # all four ratios -> null


def test_non_empty_garbage_field_still_raises(tmp_path):
    """Empty is null; genuine garbage must still fail loud, not be swallowed."""
    bad = "2026-06-30 00:00:00,BTCUSDT,100.5,not_a_number,2.1,1.2,2.0,0.94"
    csv = _HEADER + "\n" + bad + "\n"
    opener = _Opener({_day_url("BTCUSDT", "2026-06-30"): _zip_of(csv, "m.csv")})
    with pytest.raises(DerivativesError, match="unparseable"):
        fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=opener)


def test_unexpected_header_is_fatal(tmp_path):
    """A silent column reorder would misalign every value -- fail loud on a wrong header."""
    reordered = "create_time,symbol,sum_open_interest_value,sum_open_interest,x,y,z,w\n"
    csv = reordered + "2026-06-30 00:00:00,BTCUSDT,1,2,3,4,5,6\n"
    opener = _Opener({_day_url("BTCUSDT", "2026-06-30"): _zip_of(csv, "m.csv")})
    with pytest.raises(DerivativesError, match="header"):
        fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=opener)


def test_early_history_double_published_rows_collapse_to_one(tmp_path):
    """2020-09..2021-05 metrics publish every row TWICE (byte-identical); dedup must collapse each
    to a single bar with the right value."""
    row = "2026-06-30 00:00:00,BTCUSDT,100.5,100000.0,2.1,1.2,2.0,0.94"
    csv = _HEADER + "\n" + row + "\n" + row + "\n"  # every row duplicated
    opener = _Opener({_day_url("BTCUSDT", "2026-06-30"): _zip_of(csv, "m.csv")})
    frame = backfill_oi(
        "BTCUSDT",
        start=datetime(2026, 6, 30, tzinfo=UTC),
        clock=lambda: datetime(2026, 7, 1, 12, tzinfo=UTC),
        opener=opener,
    )
    assert frame.height == 1
    assert frame["sum_open_interest"][0] == 100.5


def test_boundary_bar_collision_keeps_the_owning_days_value(tmp_path):
    """A midnight bar appears as day N's last row and day N+1's first row, sometimes with differing
    values. The dedup must deterministically keep day N+1's (the day that owns 00:00), not day N's."""
    day1 = (
        _HEADER + "\n" + "2026-06-30 23:55:00,BTCUSDT,10.0,1.0,2,1,2,0.9\n" + "2026-07-01 00:00:00,BTCUSDT,111.0,1.0,2,1,2,0.9\n"
    )  # day1's copy of the boundary bar
    day2 = _HEADER + "\n" + "2026-07-01 00:00:00,BTCUSDT,222.0,1.0,2,1,2,0.9\n"  # day2's copy: DIFFERENT
    opener = _Opener(
        {
            _day_url("BTCUSDT", "2026-06-30"): _zip_of(day1, "a.csv"),
            _day_url("BTCUSDT", "2026-07-01"): _zip_of(day2, "b.csv"),
        }
    )
    frame = backfill_oi(
        "BTCUSDT",
        start=datetime(2026, 6, 30, tzinfo=UTC),
        clock=lambda: datetime(2026, 7, 2, 12, tzinfo=UTC),
        opener=opener,
    )
    boundary = frame.filter(pl.col("ts") == datetime(2026, 7, 1, tzinfo=UTC))
    assert boundary.height == 1
    assert boundary["sum_open_interest"][0] == 222.0  # day2 (the owning day) wins, deterministically


def test_checksum_mismatch_is_fatal(tmp_path):
    csv = _metrics_csv("2026-06-30", "BTCUSDT")
    url = _day_url("BTCUSDT", "2026-06-30")
    zip_bytes = _zip_of(csv, "BTCUSDT-metrics-2026-06-30.csv")
    opener = _Opener({url: zip_bytes, url + ".CHECKSUM": b"deadbeef  BTCUSDT-metrics-2026-06-30.zip\n"})

    with pytest.raises(DerivativesError, match="checksum mismatch"):
        fetch_oi_day("BTCUSDT", datetime(2026, 6, 30, tzinfo=UTC), opener=opener)


def test_backfill_skips_leading_404s_then_a_hole_is_fatal(tmp_path):
    # data begins 2026-06-30; 06-29 is a leading 404 (before listing) -> skipped;
    # a 404 AFTER data begins is a hole in a listed series -> fatal.
    good = {
        _day_url("BTCUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "BTCUSDT"), "a.csv"),
        # 07-01 missing on purpose
        _day_url("BTCUSDT", "2026-07-02"): _zip_of(_metrics_csv("2026-07-02", "BTCUSDT"), "b.csv"),
    }
    opener = _Opener(good)
    # clock at 2026-07-03 -> walk 06-29..07-02 inclusive (07-03 is the incomplete current day, dropped)
    with pytest.raises(DerivativesError, match="hole"):
        backfill_oi(
            "BTCUSDT",
            start=datetime(2026, 6, 29, tzinfo=UTC),
            clock=lambda: datetime(2026, 7, 3, 12, tzinfo=UTC),
            opener=opener,
        )


def test_trailing_404_frontier_is_tolerated_not_fatal(tmp_path):
    """Binance publishes each day's metrics with a ~1-2 day lag, so the most recent day(s) 404.
    Those trailing 404s are the unpublished frontier, NOT a hole -- take what's published and stop."""
    files = {
        _day_url("BTCUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "BTCUSDT"), "a.csv"),
        _day_url("BTCUSDT", "2026-07-01"): _zip_of(_metrics_csv("2026-07-01", "BTCUSDT"), "b.csv"),
        # 07-02 and 07-03 deliberately absent -> 404 -> the unpublished frontier
    }
    opener = _Opener(files)
    frame = backfill_oi(
        "BTCUSDT",
        start=datetime(2026, 6, 30, tzinfo=UTC),
        clock=lambda: datetime(2026, 7, 4, 12, tzinfo=UTC),  # walks 06-30..07-03
        opener=opener,
    )
    assert frame.height == 6  # only the 2 published days survive
    assert frame["ts"].max().date() == date(2026, 7, 1)  # stopped at the last published day, no error


def test_trailing_gap_beyond_the_lag_tolerance_is_fatal(tmp_path):
    """A trailing gap longer than the publication-lag tolerance is a real outage / delisted symbol,
    not the unpublished frontier -- it must fail loud, not be swallowed as 'not yet published'."""
    from cli.derivatives.oi import _MAX_TRAILING_LAG_DAYS

    files = {_day_url("BTCUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "BTCUSDT"), "a.csv")}
    opener = _Opener(files)
    far = 2 + _MAX_TRAILING_LAG_DAYS  # e.g. 6 days of trailing 404
    with pytest.raises(DerivativesError, match="exceeds the .* publication-lag tolerance"):
        backfill_oi(
            "BTCUSDT",
            start=datetime(2026, 6, 30, tzinfo=UTC),
            clock=lambda: datetime(2026, 7, 1 + far, 12, tzinfo=UTC),
            opener=opener,
        )


def test_interior_hole_still_fatal_when_data_resumes_after_the_gap(tmp_path):
    """The trailing tolerance must NOT weaken interior-hole detection: a 404 with published data on
    BOTH sides is a real gap and must still raise."""
    files = {
        _day_url("BTCUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "BTCUSDT"), "a.csv"),
        # 07-01 missing (the hole)
        _day_url("BTCUSDT", "2026-07-02"): _zip_of(_metrics_csv("2026-07-02", "BTCUSDT"), "b.csv"),
    }
    opener = _Opener(files)
    with pytest.raises(DerivativesError, match="hole inside"):
        backfill_oi(
            "BTCUSDT",
            start=datetime(2026, 6, 30, tzinfo=UTC),
            clock=lambda: datetime(2026, 7, 4, 12, tzinfo=UTC),  # 07-02 has data AFTER the 07-01 gap
            opener=opener,
        )


def test_resume_reuses_existing_perp_files_and_only_fetches_the_missing(tmp_path):
    """resume=True must not re-fetch a perp whose oi.parquet already exists -- an interrupted backfill
    finishes by building only the missing symbols, then regenerates the manifest over the full set."""
    existing = pl.DataFrame(
        {
            "ts": [datetime(2026, 6, 30, tzinfo=UTC)],
            **{c: [1.0] for c in ("sum_open_interest", "sum_open_interest_value")},
            **{
                c: [2.0]
                for c in (
                    "count_toptrader_long_short_ratio",
                    "sum_toptrader_long_short_ratio",
                    "count_long_short_ratio",
                    "sum_taker_long_short_vol_ratio",
                )
            },
        }
    ).with_columns(pl.col("ts").dt.cast_time_unit("us").dt.replace_time_zone("UTC"))
    write_parquet(existing, tmp_path / "BTCUSDT" / "oi.parquet")

    fetched: list[str] = []
    base = _Opener({_day_url("ETHUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "ETHUSDT"), "e.csv")})

    def _tracking(url, timeout=None):
        fetched.append(url)
        return base(url, timeout)

    manifest = build_oi_substrate(
        tmp_path,
        perps={"BTC": "BTCUSDT", "ETH": "ETHUSDT"},
        start=datetime(2026, 6, 30, tzinfo=UTC),
        clock=lambda: datetime(2026, 7, 1, 12, tzinfo=UTC),
        opener=_tracking,
        resume=True,
    )
    assert not any("BTCUSDT" in u for u in fetched), "resume must NOT re-fetch the completed BTCUSDT"
    assert any("ETHUSDT" in u for u in fetched), "the missing ETHUSDT must be fetched"
    assert set(manifest["series"]) == {"BTCUSDT/oi.parquet", "ETHUSDT/oi.parquet"}
    assert manifest["series"]["BTCUSDT/oi.parquet"]["rows"] == 1  # the reused frame


def test_backfill_returns_sorted_deduped_typed_frame(tmp_path):
    files = {
        _day_url("BTCUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "BTCUSDT", n=3, oi0=100), "a.csv"),
        _day_url("BTCUSDT", "2026-07-01"): _zip_of(_metrics_csv("2026-07-01", "BTCUSDT", n=3, oi0=200), "b.csv"),
    }
    opener = _Opener(files)
    frame = backfill_oi(
        "BTCUSDT",
        start=datetime(2026, 6, 30, tzinfo=UTC),
        clock=lambda: datetime(2026, 7, 2, 12, tzinfo=UTC),
        opener=opener,
    )
    assert frame.height == 6
    assert frame["ts"].is_sorted()
    assert frame["ts"].n_unique() == frame.height
    assert frame.schema["ts"] == pl.Datetime("us", "UTC")
    assert frame.schema["sum_open_interest"] == pl.Float64
    diffs = frame.filter(pl.col("ts") < datetime(2026, 7, 1, tzinfo=UTC))["ts"].diff().drop_nulls()
    assert (diffs == timedelta(minutes=5)).all()


def test_build_substrate_writes_per_perp_files_and_a_manifest(tmp_path):
    files = {
        _day_url("BTCUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "BTCUSDT"), "a.csv"),
        _day_url("ETHUSDT", "2026-06-30"): _zip_of(_metrics_csv("2026-06-30", "ETHUSDT"), "b.csv"),
    }
    opener = _Opener(files)
    manifest = build_oi_substrate(
        tmp_path,
        perps={"BTC": "BTCUSDT", "ETH": "ETHUSDT"},
        start=datetime(2026, 6, 30, tzinfo=UTC),
        clock=lambda: datetime(2026, 7, 1, 12, tzinfo=UTC),
        opener=opener,
    )
    assert (tmp_path / "BTCUSDT" / "oi.parquet").exists()
    assert (tmp_path / "ETHUSDT" / "oi.parquet").exists()
    assert manifest["set_sha256"]
    assert set(manifest["series"]) == {"BTCUSDT/oi.parquet", "ETHUSDT/oi.parquet"}
    assert manifest["provenance"]["source"].endswith("daily/metrics")
    got = read_oi_series(tmp_path, "BTCUSDT")
    assert got.height == 3
    m2 = json.loads((tmp_path / "manifest.json").read_text())
    assert m2["set_sha256"] == manifest["set_sha256"]


def _substrate_root(name: str) -> Path:
    """The canonical root of a derivatives substrate: the NFS hot mount, else a promoted local copy.

    `data/` is per-checkout and a worktree's is empty, so gating on `Path("data/<name>")` alone skips
    wherever this suite runs from a worktree — a skip on the only machine holding the substrate,
    recorded as coverage."""
    hot = resolve_hot_source(load_config()) / name
    return hot if hot.is_dir() else Path("data") / name


_OI_ROOT = _substrate_root("derivatives-oi")

# A closed past window. A forward refresh extends the substrate beyond it and cannot move a count
# taken over it; every population pinned below sits entirely inside it.
_CLOSED_WINDOW_END = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def oi_panel() -> dict[str, pl.DataFrame]:
    """The ten perps' OI series, read once for the assertions below (~5M rows over NFS), keyed on
    `PERP_SYMBOLS` rather than on whatever the directory holds, so a missing leg raises instead of
    quietly shrinking the panel the counts are taken over."""
    return {perp: read_oi_series(_OI_ROOT, perp) for perp in sorted(PERP_SYMBOLS.values())}


@pytest.mark.skipif(not _OI_ROOT.is_dir(), reason="derivatives-oi substrate absent")
def test_the_balanced_oi_panel_starts_2021_12_01(oi_panel):
    """Spec 00110 D4's balanced start is the LATEST first stamp, not BTC's: BTCUSDT reaches
    2020-09-01 and the other nine begin 2021-12-01. A coverage extension moving either date moves
    the panel every cross-sectional B2 feature is computed over."""
    firsts = {perp: frame["ts"].min() for perp, frame in oi_panel.items()}
    assert firsts["BTCUSDT"] == datetime(2020, 9, 1, tzinfo=UTC)
    assert set(firsts.values()) == {datetime(2020, 9, 1, tzinfo=UTC), datetime(2021, 12, 1, tzinfo=UTC)}
    assert max(firsts.values()) == datetime(2021, 12, 1, tzinfo=UTC)


@pytest.mark.skipif(not _OI_ROOT.is_dir(), reason="derivatives-oi substrate absent")
def test_both_oi_level_columns_carry_no_nulls(oi_panel):
    """Spec 00110 D5's density claim is about BOTH level columns. A single-column guard would let a
    re-fetch put holes in the other one silently — the same reason the zero counts below assert
    both."""
    nulls = {
        column: sum(frame[column].null_count() for frame in oi_panel.values())
        for column in ("sum_open_interest", "sum_open_interest_value")
    }
    assert nulls == {"sum_open_interest": 0, "sum_open_interest_value": 0}


@pytest.mark.skipif(not _OI_ROOT.is_dir(), reason="derivatives-oi substrate absent")
def test_the_oi_zero_populations_hold_over_a_closed_window(oi_panel):
    """Spec 00110 D5's venue-hole counts, pinned so a substrate re-fetch cannot move them silently.

    The two OI zero sets NEST rather than coincide — 101 rows read a zero notional against a healthy
    positive `sum_open_interest` — so a guard on the first column alone is blind to the second's
    count moving. `sum_taker_long_short_vol_ratio == 0.0` is the opposite case, a real all-sell bar
    D5 rules must be ACCEPTED."""
    window = {perp: frame.filter(pl.col("ts") < _CLOSED_WINDOW_END) for perp, frame in oi_panel.items()}
    assert sum(frame.height for frame in window.values()) == 4_426_251
    zeros = {
        column: sum(frame.filter(pl.col(column) == 0.0).height for frame in window.values())
        for column in ("sum_open_interest", "sum_open_interest_value", "sum_taker_long_short_vol_ratio")
    }
    assert zeros == {
        "sum_open_interest": 2_329,
        "sum_open_interest_value": 2_430,
        "sum_taker_long_short_vol_ratio": 45,
    }
