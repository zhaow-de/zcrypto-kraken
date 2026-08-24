import hashlib
import io
import json
import urllib.error
import zipfile
from datetime import UTC, datetime

import polars as pl
import pytest

from cli.derivatives.errors import DerivativesError
from cli.derivatives.funding import (
    _BASE_URL,
    PERP_SYMBOLS,
    backfill_funding,
    build_funding_substrate,
    fetch_funding_month,
    read_funding_series,
)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _make_zip(rows: list[list]) -> bytes:
    """Build an in-memory Binance-Vision-shaped fundingRate zip (one CSV member, real header)."""
    lines = ["calc_time,funding_interval_hours,last_funding_rate"]
    for calc_time_ms, interval_hours, rate in rows:
        lines.append(f"{calc_time_ms},{interval_hours},{rate}")
    body = ("\n".join(lines) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("member-fundingRate.csv", body)
    return buf.getvalue()


def _fake_opener(zip_map: dict, *, corrupt_checksum: bool = False):
    """A urllib.urlopen stand-in over an in-memory (perp, year, month) -> zip-bytes map.

    A key absent from the map raises HTTP 404 (mimics a pre-listing / unpublished month). The
    `.CHECKSUM` sibling returns the real sha256 of the mapped zip unless `corrupt_checksum`.
    """

    def _open(url, timeout=None):
        is_checksum = url.endswith(".CHECKSUM")
        zip_url = url[: -len(".CHECKSUM")] if is_checksum else url
        fname = zip_url.rsplit("/", 1)[-1]  # PERP-fundingRate-YYYY-MM.zip
        stem = fname[: -len(".zip")]  # PERP-fundingRate-YYYY-MM
        perp, _, ym = stem.partition("-fundingRate-")
        year, month = ym.split("-")
        key = (perp, int(year), int(month))
        if key not in zip_map:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        zip_bytes = zip_map[key]
        if is_checksum:
            digest = "0" * 64 if corrupt_checksum else hashlib.sha256(zip_bytes).hexdigest()
            return io.BytesIO(f"{digest}  {fname}\n".encode("utf-8"))
        return io.BytesIO(zip_bytes)

    return _open


# --- fetch_funding_month ---------------------------------------------------


def test_fetch_parses_three_rows():
    rows = [
        [1577836800000, 8, -0.00012359],
        [1577865600000, 8, 0.0001],
        [1577894400000, 8, 0.00005],
    ]
    out = fetch_funding_month("BTCUSDT", 2020, 1, opener=_fake_opener({("BTCUSDT", 2020, 1): _make_zip(rows)}))
    assert out == rows


def test_fetch_checksum_mismatch_raises():
    zm = {("BTCUSDT", 2020, 1): _make_zip([[1577836800000, 8, 0.0]])}
    with pytest.raises(DerivativesError):
        fetch_funding_month("BTCUSDT", 2020, 1, opener=_fake_opener(zm, corrupt_checksum=True))


def test_fetch_404_returns_none():
    def _open(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    assert fetch_funding_month("BTCUSDT", 2019, 1, opener=_open) is None


def test_fetch_transport_error_raises(monkeypatch):
    monkeypatch.setattr("cli.derivatives.funding.time.sleep", lambda _s: None)

    def _open(url, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(DerivativesError):
        fetch_funding_month("BTCUSDT", 2020, 1, opener=_open)


def test_fetch_non_404_http_error_raises():
    def _open(url, timeout=None):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)

    with pytest.raises(DerivativesError):
        fetch_funding_month("BTCUSDT", 2020, 1, opener=_open)


def test_fetch_retries_transient_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("cli.derivatives.funding.time.sleep", lambda _s: None)
    rows = [[_ms(datetime(2020, 1, 1, tzinfo=UTC)), 8, "-0.00012359"]]
    base = _fake_opener({("BTCUSDT", 2020, 1): _make_zip(rows)})
    calls = {"n": 0}

    def _flaky(url, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:  # first attempt on the zip GET times out, retry succeeds
            raise urllib.error.URLError("handshake timed out")
        return base(url, timeout=timeout)

    out = fetch_funding_month("BTCUSDT", 2020, 1, opener=_flaky)
    assert out == [[_ms(datetime(2020, 1, 1, tzinfo=UTC)), 8, -0.00012359]]
    assert calls["n"] >= 2  # the transient failure was retried, not fatal


def test_fetch_transport_error_raises_after_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr("cli.derivatives.funding.time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def _always_fail(url, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError("boom")

    with pytest.raises(DerivativesError):
        fetch_funding_month("BTCUSDT", 2020, 1, opener=_always_fail)
    assert calls["n"] == 3  # _MAX_RETRIES attempts before giving up
    assert sleeps == [2.0, 4.0]  # linear backoff between the three attempts


# --- backfill_funding ------------------------------------------------------


def test_backfill_skips_leading_404_and_starts_at_first_data_month():
    zm = {
        ("BTCUSDT", 2020, 3): _make_zip([[_ms(datetime(2020, 3, 1, tzinfo=UTC)), 8, 0.0001]]),
        ("BTCUSDT", 2020, 4): _make_zip([[_ms(datetime(2020, 4, 1, tzinfo=UTC)), 8, 0.0002]]),
    }
    clock = lambda: datetime(2020, 5, 15, tzinfo=UTC)  # noqa: E731
    df = backfill_funding("BTCUSDT", start=(2020, 1), clock=clock, opener=_fake_opener(zm))
    assert df.select(pl.col("ts").dt.month()).to_series().to_list() == [3, 4]


def test_backfill_404_inside_range_raises():
    zm = {
        ("BTCUSDT", 2020, 3): _make_zip([[_ms(datetime(2020, 3, 1, tzinfo=UTC)), 8, 0.0001]]),
        # 2020-04 absent -> a hole inside a listed series
        ("BTCUSDT", 2020, 5): _make_zip([[_ms(datetime(2020, 5, 1, tzinfo=UTC)), 8, 0.0002]]),
    }
    clock = lambda: datetime(2020, 6, 15, tzinfo=UTC)  # noqa: E731
    with pytest.raises(DerivativesError):
        backfill_funding("BTCUSDT", start=(2020, 1), clock=clock, opener=_fake_opener(zm))


def test_backfill_excludes_current_incomplete_month():
    zm = {
        ("BTCUSDT", 2020, 1): _make_zip([[_ms(datetime(2020, 1, 1, tzinfo=UTC)), 8, 0.0001]]),
        ("BTCUSDT", 2020, 2): _make_zip([[_ms(datetime(2020, 2, 1, tzinfo=UTC)), 8, 0.0002]]),
        ("BTCUSDT", 2020, 3): _make_zip([[_ms(datetime(2020, 3, 1, tzinfo=UTC)), 8, 0.0003]]),
    }
    clock = lambda: datetime(2020, 3, 15, tzinfo=UTC)  # noqa: E731
    df = backfill_funding("BTCUSDT", start=(2020, 1), clock=clock, opener=_fake_opener(zm))
    assert df.select(pl.col("ts").dt.month()).to_series().to_list() == [1, 2]


def test_backfill_sorted_deduped_aware_utc_schema():
    t0 = _ms(datetime(2020, 1, 1, 0, tzinfo=UTC))
    t1 = _ms(datetime(2020, 1, 1, 8, tzinfo=UTC))
    zm = {("BTCUSDT", 2020, 1): _make_zip([[t1, 8, 0.2], [t0, 8, 0.1], [t0, 8, 0.1]])}
    clock = lambda: datetime(2020, 2, 15, tzinfo=UTC)  # noqa: E731
    df = backfill_funding("BTCUSDT", start=(2020, 1), clock=clock, opener=_fake_opener(zm))
    assert df.height == 2  # exact-duplicate row collapsed
    assert df["ts"].is_sorted()
    assert df.schema["ts"] == pl.Datetime("us", "UTC")
    assert df.schema["funding_rate"] == pl.Float64
    assert df.schema["interval_hours"] == pl.Int64


# --- build_funding_substrate + read_funding_series -------------------------


def test_build_writes_parquet_manifest_and_roundtrips(tmp_path):
    perps = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
    zm = {
        ("BTCUSDT", 2020, 1): _make_zip(
            [
                [_ms(datetime(2020, 1, 1, 0, tzinfo=UTC)), 8, 0.0001],
                [_ms(datetime(2020, 1, 1, 8, tzinfo=UTC)), 8, 0.0002],
            ]
        ),
        ("ETHUSDT", 2020, 1): _make_zip([[_ms(datetime(2020, 1, 1, 0, tzinfo=UTC)), 8, 0.0003]]),
    }
    clock = lambda: datetime(2020, 2, 15, tzinfo=UTC)  # noqa: E731
    manifest = build_funding_substrate(tmp_path, perps=perps, clock=clock, opener=_fake_opener(zm))

    assert (tmp_path / "BTCUSDT" / "funding.parquet").exists()
    assert (tmp_path / "ETHUSDT" / "funding.parquet").exists()
    assert (tmp_path / "manifest.json").exists()

    assert set(manifest["series"]) == {"BTCUSDT/funding.parquet", "ETHUSDT/funding.parquet"}
    assert manifest["series"]["BTCUSDT/funding.parquet"]["rows"] == 2
    assert manifest["series"]["ETHUSDT/funding.parquet"]["rows"] == 1
    for key in ("rows", "first_ts", "last_ts", "sha256"):
        assert key in manifest["series"]["BTCUSDT/funding.parquet"]
    # `source` is a fixed URL and `fetched_at` a wall clock: both quarantined, outside the digest.
    assert manifest["provenance"]["source"] == _BASE_URL
    assert manifest["provenance"]["fetched_at"] == clock().isoformat()

    expected_basket = hashlib.sha256(
        "".join(manifest["series"][p]["sha256"] for p in sorted(manifest["series"])).encode()
    ).hexdigest()
    assert manifest["set_sha256"] == expected_basket

    # manifest.json on disk mirrors the returned dict
    assert json.loads((tmp_path / "manifest.json").read_text())["set_sha256"] == expected_basket

    # round-trip read
    df = read_funding_series(tmp_path, "BTCUSDT")
    assert df.height == 2
    assert df.schema["ts"] == pl.Datetime("us", "UTC")


def test_perp_symbols_maps_ten_basket_assets():
    assert PERP_SYMBOLS["BTC"] == "BTCUSDT"
    assert PERP_SYMBOLS["AVAX"] == "AVAXUSDT"
    assert len(PERP_SYMBOLS) == 10
    assert all(v.endswith("USDT") for v in PERP_SYMBOLS.values())
