from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from cli.data.manifest import build_manifest, series_entry
from cli.derivatives.errors import DerivativesError
from cli.logging import get_logger
from cli.ohlc.dataset import dataset_hash, read_parquet, write_parquet

_logger = get_logger("derivatives.funding")

_BASE_URL = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
_TIMEOUT_SECONDS = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2.0

# Kraken spot base -> Binance USDT-M perpetual (the 10 basket assets; §8/T0023 universe).
PERP_SYMBOLS: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "ADA": "ADAUSDT",
    "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT",
    "DOT": "DOTUSDT",
    "LINK": "LINKUSDT",
    "LTC": "LTCUSDT",
    "AVAX": "AVAXUSDT",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _month_url(perp: str, year: int, month: int) -> str:
    return f"{_BASE_URL}/{perp}/{perp}-fundingRate-{year:04d}-{month:02d}.zip"


def _get_bytes(url: str, *, opener) -> bytes:
    """GET `url` with the injected opener and return the raw body bytes.

    Re-raises `urllib.error.HTTPError` unchanged (the caller inspects `.code` — a 404 is a real
    "not there", not a fault to retry). Transient transport failures (timeouts, connection resets)
    are retried up to `_MAX_RETRIES` times with linear backoff before being wrapped as
    `DerivativesError` — a bulk backfill fetches hundreds of files, so a single network blip must
    not abort the whole run.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with opener(url, timeout=_TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                _logger.warning("transient fetch error (attempt %d/%d) for %s: %s", attempt, _MAX_RETRIES, url, exc)
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise DerivativesError(f"transport error fetching {url} after {_MAX_RETRIES} attempts: {last_exc}") from last_exc


def fetch_funding_month(perp: str, year: int, month: int, *, opener=urllib.request.urlopen) -> list[list] | None:
    """Fetch + checksum-verify one monthly Binance Vision fundingRate dump for `perp`.

    GETs the monthly zip and its `.CHECKSUM` sibling, verifies the zip's sha256 against the
    checksum body (a mismatch raises `DerivativesError` — never a silent accept), unzips the
    single CSV member, and parses each data row (header skipped) into
    `[calc_time_ms, interval_hours, rate]`. Returns `None` when the month 404s (before the perp's
    listing or not yet published). Any transport or parse failure raises `DerivativesError`.
    """
    zip_url = _month_url(perp, year, month)
    try:
        zip_bytes = _get_bytes(zip_url, opener=opener)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise DerivativesError(f"HTTP {exc.code} fetching {zip_url}: {exc}") from exc

    try:
        checksum_body = _get_bytes(zip_url + ".CHECKSUM", opener=opener)
    except urllib.error.HTTPError as exc:
        raise DerivativesError(f"HTTP {exc.code} fetching checksum for {zip_url}: {exc}") from exc

    expected = checksum_body.decode("utf-8").split()[0] if checksum_body.split() else ""
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if actual != expected:
        raise DerivativesError(f"checksum mismatch for {perp} {year:04d}-{month:02d}: expected {expected!r}, got {actual!r}")

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            members = archive.namelist()
            if len(members) != 1:
                raise DerivativesError(f"expected one CSV in {perp} {year:04d}-{month:02d} zip, found {members}")
            csv_text = archive.read(members[0]).decode("utf-8")
    except zipfile.BadZipFile as exc:
        raise DerivativesError(f"corrupt zip for {perp} {year:04d}-{month:02d}: {exc}") from exc

    rows: list[list] = []
    try:
        for line in csv_text.splitlines()[1:]:  # skip the header row
            if not line.strip():
                continue
            calc_time_ms, interval_hours, rate = line.split(",")
            rows.append([int(calc_time_ms), int(interval_hours), float(rate)])
    except (ValueError, IndexError) as exc:
        raise DerivativesError(f"unparseable funding row for {perp} {year:04d}-{month:02d}: {exc}") from exc

    return rows


def _iter_months(start: tuple[int, int], end_exclusive: tuple[int, int]):
    year, month = start
    while (year, month) < end_exclusive:
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def backfill_funding(
    perp: str,
    *,
    start: tuple[int, int] = (2019, 9),
    clock=_utc_now,
    opener=urllib.request.urlopen,
) -> pl.DataFrame:
    """Backfill `perp`'s full funding-rate history from `start` to the last complete month.

    Walks months from `start` up to (but excluding) `clock()`'s own month — the current month is
    incomplete, so it is dropped. The leading run of 404s (before this perp's listing) is skipped;
    once data begins, a 404 inside the range raises `DerivativesError` (a hole in a listed series
    must not pass silently). Returns the typed frame — `ts` (aware-UTC), `funding_rate` (Float64),
    `interval_hours` (Int64) — sorted ascending and de-duplicated on `ts` (last wins).
    """
    now = clock()
    end_exclusive = (now.year, now.month)

    all_rows: list[list] = []
    data_begun = False
    for year, month in _iter_months(start, end_exclusive):
        rows = fetch_funding_month(perp, year, month, opener=opener)
        if rows is None:
            if data_begun:
                raise DerivativesError(f"404 for {perp} {year:04d}-{month:02d}: a hole inside the listed funding series")
            continue
        data_begun = True
        all_rows.extend(rows)

    schema = {"ts": pl.Datetime("us", "UTC"), "funding_rate": pl.Float64, "interval_hours": pl.Int64}
    if not all_rows:
        _logger.warning("no funding data for %s in range %s..%s", perp, start, end_exclusive)
        return pl.DataFrame(schema=schema)

    frame = (
        pl.DataFrame(all_rows, schema=["calc_time_ms", "interval_hours", "funding_rate"], orient="row")
        .with_columns(
            pl.from_epoch(pl.col("calc_time_ms"), time_unit="ms").dt.replace_time_zone("UTC").alias("ts"),
            pl.col("funding_rate").cast(pl.Float64),
            pl.col("interval_hours").cast(pl.Int64),
        )
        .select("ts", "funding_rate", "interval_hours")
        .sort("ts")
        .unique(subset="ts", keep="last", maintain_order=True)
    )
    _logger.info("backfilled %s: %d rows, %s..%s", perp, frame.height, frame["ts"].min(), frame["ts"].max())
    return frame


def build_funding_substrate(
    out_root: Path,
    *,
    perps: dict[str, str] = PERP_SYMBOLS,
    clock=_utc_now,
    opener=urllib.request.urlopen,
) -> dict:
    """Backfill each perp's funding series, write `out_root/<PERP>/funding.parquet`, and a manifest.

    Mirrors the backfill manifest shape: one `series` entry per perp (`rows`, `first_ts`, `last_ts`,
    `sha256` via `dataset_hash`), a `basket_sha256` over the sorted per-series hashes, plus `source`
    (the CDN base URL) and `fetched_at` (`clock()`). Writes `out_root/manifest.json`; returns it.
    """
    series: dict[str, dict] = {}
    for perp in perps.values():
        frame = backfill_funding(perp, clock=clock, opener=opener)
        write_parquet(frame, out_root / perp / "funding.parquet")
        relpath = f"{perp}/funding.parquet"
        series[relpath] = series_entry(frame, relpath)

    fetched_at = clock().isoformat()
    manifest = build_manifest(series, written_at=fetched_at, provenance={"fetched_at": fetched_at, "source": _BASE_URL})
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def read_funding_series(out_root: Path, perp: str) -> pl.DataFrame:
    """Read `perp`'s funding series written by `build_funding_substrate` back into a frame."""
    return read_parquet(out_root / perp / "funding.parquet")
