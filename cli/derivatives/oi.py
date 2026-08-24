"""Open-interest substrate backfill (T0023 / B2): Binance Vision daily `metrics` dumps.

The sibling of `cli/derivatives/funding.py`. Open interest is the second free-backfillable B2 input;
its only deep free source is Binance Vision's daily `metrics` dumps
(`data.binance.vision/data/futures/um/daily/metrics/<SYM>/…`) — the SAME public CDN the funding
backfill uses, and (measured, T0023) NOT the geo-fenced surface. Coinalyze substituted only the LIVE
liquidations WS feed; it cannot serve deep OI history (its intraday retention is a ~2-3 month rolling
window), so OI history comes from Vision, exactly like funding.

Two differences from funding drive the shape here: the dumps are DAILY (`…-metrics-YYYY-MM-DD.zip`,
not monthly), and each row carries 5-minute open interest plus the free long/short and taker ratios.
The raw 5-minute series is stored as-is — resampling to the 1h/4h/8h decision grid is the B2
harness's job, so the finest native information is preserved on disk.

The fetch/checksum/unzip flow is intentionally a near-copy of funding's; that duplication is
registered as a follow-up (dedup into a shared `cli/derivatives/vision.py`) rather than refactored
here, to keep the delivered, in-use funding module untouched.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.data.manifest import build_manifest, series_entry
from cli.derivatives.errors import DerivativesError
from cli.derivatives.funding import PERP_SYMBOLS
from cli.logging import get_logger
from cli.ohlc.dataset import dataset_hash, read_parquet, write_parquet

_logger = get_logger("derivatives.oi")

_BASE_URL = "https://data.binance.vision/data/futures/um/daily/metrics"
_TIMEOUT_SECONDS = 30
# A full OI backfill fetches ~40k files sequentially, so it must ride out a transient CDN blip
# (data.binance.vision intermittently 503s under that load). More retries than funding's 3 -- 10x
# the request count means 10x the chance of hitting one, and a single unlucky file must not abort a
# multi-hour run.
_MAX_RETRIES = 5
_RETRY_BACKOFF_SECONDS = 2.0

# Metrics CSV columns (Binance Vision daily metrics), in file order.
_CSV_COLUMNS = (
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
# The numeric columns kept on disk (everything except create_time + the redundant symbol).
_FLOAT_COLUMNS = (
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
# Column -> file position, precomputed once (not per row -- the full backfill parses millions).
_COL_INDEX = {c: _CSV_COLUMNS.index(c) for c in _FLOAT_COLUMNS}

# Trailing 404s beyond this many days are NOT the publication frontier -- they are a real outage or
# a delisted symbol, and must fail loud rather than be tolerated as "not yet published". The measured
# lag is ~1 day; the slack covers an occasional multi-day publication pileup while still catching a
# symbol that has genuinely stopped publishing metrics (review 2026-07-24: the unbounded tolerance
# would otherwise silently accept an arbitrarily long tail gap).
_MAX_TRAILING_LAG_DAYS = 4


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_float(value: str) -> float | None:
    """Parse a metrics float, mapping any ABSENT form to null rather than raising.

    Early Binance Vision metrics leave ancillary ratio columns absent on some rows, in two observed
    forms: a bare empty field (BTCUSDT 2020-09-27) and a quoted-empty `""` (BTCUSDT 2021-12-30) --
    always the ratio columns, never the OI columns. A missing auxiliary value must not discard the
    row's OI reading, so any absent form parses to null. A present-but-non-numeric value still raises
    (via `float`) -- absence is null, genuine garbage fails loud.
    """
    value = value.strip().strip('"').strip()
    return float(value) if value else None


def _day_url(perp: str, day: datetime) -> str:
    return f"{_BASE_URL}/{perp}/{perp}-metrics-{day:%Y-%m-%d}.zip"


def _get_bytes(url: str, *, opener) -> bytes:
    """GET `url`, retrying transient failures (connection errors AND 5xx server errors) with backoff.

    A 4xx `HTTPError` -- including 404 -- is a definitive answer the caller must act on (404 = not
    published / not listed), so it is re-raised immediately, never retried. A 5xx is a transient
    server error (the CDN 503s intermittently under a long sequential backfill) and IS retried, as
    are connection-level `URLError`/`OSError` blips. Exhausted retries raise `DerivativesError`.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with opener(url, timeout=_TIMEOUT_SECONDS) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code is None or exc.code < 500:
                raise  # 4xx (incl 404) is definitive -- the caller distinguishes it
            last_exc = exc
            if attempt < _MAX_RETRIES:
                _logger.warning(
                    "HTTP %s (attempt %d/%d) for %s -- transient server error, retrying", exc.code, attempt, _MAX_RETRIES, url
                )
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                _logger.warning("transient fetch error (attempt %d/%d) for %s: %s", attempt, _MAX_RETRIES, url, exc)
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    raise DerivativesError(f"transport error fetching {url} after {_MAX_RETRIES} attempts: {last_exc}") from last_exc


def fetch_oi_day(perp: str, day: datetime, *, opener=urllib.request.urlopen) -> list[list] | None:
    """Fetch + checksum-verify one daily Binance Vision metrics dump for `perp` on `day`.

    Returns `None` when the day 404s (before the perp's metrics listing, or not yet published). A
    checksum mismatch or any parse failure raises `DerivativesError` — never a silent accept. Each
    data row becomes `[create_time_ms, sum_open_interest, sum_open_interest_value,
    count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio,
    sum_taker_long_short_vol_ratio]`.
    """
    zip_url = _day_url(perp, day)
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
        raise DerivativesError(f"checksum mismatch for {perp} {day:%Y-%m-%d}: expected {expected!r}, got {actual!r}")

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            members = archive.namelist()
            if len(members) != 1:
                raise DerivativesError(f"expected one CSV in {perp} {day:%Y-%m-%d} zip, found {members}")
            csv_text = archive.read(members[0]).decode("utf-8")
    except zipfile.BadZipFile as exc:
        raise DerivativesError(f"corrupt zip for {perp} {day:%Y-%m-%d}: {exc}") from exc

    lines = csv_text.splitlines()
    header = lines[0].split(",") if lines else []
    if header != list(_CSV_COLUMNS):
        # A silent column reorder would misalign every value; fail loud instead (early metrics have
        # already proven the wire is messier than the docs -- see the empty-field handling below).
        raise DerivativesError(f"unexpected metrics header for {perp} {day:%Y-%m-%d}: {header}")

    rows: list[list] = []
    try:
        for line in lines[1:]:
            if not line.strip():
                continue
            fields = line.split(",")
            if len(fields) != len(_CSV_COLUMNS):
                raise DerivativesError(f"expected {len(_CSV_COLUMNS)} metrics fields, got {len(fields)}: {line!r}")
            create_time = datetime.strptime(fields[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            create_time_ms = int(create_time.timestamp() * 1000)
            # Empty ancillary fields are a REAL early-history pattern (e.g. BTCUSDT 2020-09-27 carries
            # a blank sum_taker_long_short_vol_ratio while its OI columns are populated). A missing
            # auxiliary ratio must not discard a valid OI reading -- parse it to null, keep the row.
            floats = [_parse_float(fields[_COL_INDEX[c]]) for c in _FLOAT_COLUMNS]
            rows.append([create_time_ms, *floats])
    except (ValueError, IndexError) as exc:
        raise DerivativesError(f"unparseable metrics row for {perp} {day:%Y-%m-%d}: {exc}") from exc

    return rows


def _iter_days(start: datetime, end_exclusive: datetime):
    day = start
    while day < end_exclusive:
        yield day
        day += timedelta(days=1)


def backfill_oi(
    perp: str,
    *,
    start: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    now: datetime | None = None,
    clock=_utc_now,
    opener=urllib.request.urlopen,
) -> pl.DataFrame:
    """Backfill `perp`'s full OI-metrics history from `start` up to (excluding) `now`'s day.

    `now` (default `clock()`) fixes the end boundary; a caller building many symbols passes one shared
    value so a run that crosses midnight does not give different symbols different last days. Today's
    file is incomplete, so the day of `now` is dropped.

    Three 404 regimes are distinguished, because Binance's daily `metrics` dumps both start unevenly
    per symbol AND publish with a ~1-2 day lag:
      - LEADING 404s (before this perp's metrics listing) are skipped.
      - an INTERIOR 404 (a gap with published data on BOTH sides) raises `DerivativesError` — a real
        hole in a listed series must not pass silently.
      - TRAILING 404s (the not-yet-published frontier, after the last published day) are tolerated:
        take what is published and stop there. Treating the unpublished frontier as a hole is the
        2026-07-24 bug this replaced — a midnight-crossing run hit the not-yet-published 07-23 file.

    Returns the typed frame — `ts` (aware-UTC, 5-minute), the six metrics floats — sorted ascending
    and de-duplicated on `ts` (last wins).
    """
    now = now or clock()
    end_exclusive = datetime(now.year, now.month, now.day, tzinfo=UTC)

    all_rows: list[list] = []
    data_begun = False
    pending_gap: list[datetime] = []  # 404s seen after data began; interior-vs-trailing not yet known
    for day in _iter_days(start, end_exclusive):
        rows = fetch_oi_day(perp, day, opener=opener)
        if rows is None:
            if data_begun:
                pending_gap.append(day)
            continue
        if pending_gap:
            # data resumed after a run of 404s -> those were an INTERIOR hole, not the frontier.
            raise DerivativesError(
                f"404 hole inside the listed OI series for {perp}: "
                f"{pending_gap[0]:%Y-%m-%d}..{pending_gap[-1]:%Y-%m-%d} (data resumes {day:%Y-%m-%d})"
            )
        data_begun = True
        all_rows.extend(rows)

    if pending_gap:
        if len(pending_gap) > _MAX_TRAILING_LAG_DAYS:
            # Too long to be the ~1-day publication frontier -- a real outage or a delisted symbol.
            raise DerivativesError(
                f"trailing gap of {len(pending_gap)} days for {perp} ({pending_gap[0]:%Y-%m-%d}.."
                f"{pending_gap[-1]:%Y-%m-%d}) exceeds the {_MAX_TRAILING_LAG_DAYS}-day publication-lag "
                "tolerance -- this is an outage or a delisted symbol, not the unpublished frontier"
            )
        _logger.warning(
            "backfill OI %s: %d trailing day(s) %s..%s not yet published (Binance metrics lag) -- stopping at the last published day",
            perp,
            len(pending_gap),
            pending_gap[0].date(),
            pending_gap[-1].date(),
        )

    schema = {"ts": pl.Datetime("us", "UTC"), **{c: pl.Float64 for c in _FLOAT_COLUMNS}}
    if not all_rows:
        _logger.warning("no OI data for %s in range %s..%s", perp, start.date(), end_exclusive.date())
        return pl.DataFrame(schema=schema)

    frame = (
        pl.DataFrame(all_rows, schema=["create_time_ms", *_FLOAT_COLUMNS], orient="row")
        .with_columns(
            pl.from_epoch(pl.col("create_time_ms"), time_unit="ms").dt.replace_time_zone("UTC").alias("ts"),
            *[pl.col(c).cast(pl.Float64) for c in _FLOAT_COLUMNS],
        )
        .select("ts", *_FLOAT_COLUMNS)
        # maintain_order so the tie-break is deterministic: a midnight boundary bar appears as both
        # day N's last row and day N+1's first row, sometimes with differing values; keep="last"
        # over the day-ordered rows then makes day N+1's version (the day that owns that bar) win.
        .sort("ts", maintain_order=True)
        .unique(subset="ts", keep="last", maintain_order=True)
    )
    _logger.info("backfilled OI %s: %d rows, %s..%s", perp, frame.height, frame["ts"].min(), frame["ts"].max())
    return frame


def build_oi_substrate(
    out_root: Path,
    *,
    perps: dict[str, str] = PERP_SYMBOLS,
    start: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    clock=_utc_now,
    opener=urllib.request.urlopen,
    resume: bool = False,
) -> dict:
    """Backfill each perp's OI series, write `out_root/<PERP>/oi.parquet`, and a manifest.

    Mirrors the funding manifest shape: one `series` entry per perp (`rows`, `first_ts`, `last_ts`,
    `sha256` via `dataset_hash`), a `basket_sha256` over the sorted per-series hashes, plus `source`
    (the CDN base URL) and `fetched_at`. The end boundary `now` is read ONCE and shared by every
    symbol, so a long run crossing midnight still gives all symbols the same last day.

    `resume=True` reuses any per-perp `oi.parquet` already present in `out_root` instead of re-fetching
    it -- so an interrupted multi-thousand-file backfill can be finished without re-downloading the
    symbols that already completed. The manifest is always regenerated over the full set.
    """
    now = clock()
    end_boundary = datetime(now.year, now.month, now.day, tzinfo=UTC)
    series: dict[str, dict] = {}
    for perp in perps.values():
        target = out_root / perp / "oi.parquet"
        if resume and target.exists():
            frame = read_parquet(target)
            # Log the reused file's tail against this run's boundary so a stale reuse is visible
            # (resume trusts the file as complete; a gap already baked into it is not re-checked).
            reused_last = frame["ts"].max() if frame.height else None
            _logger.info(
                "build OI: reusing existing %s (%d rows, last_ts %s; boundary %s) [resume]",
                perp,
                frame.height,
                reused_last,
                end_boundary.date(),
            )
        else:
            frame = backfill_oi(perp, start=start, now=now, opener=opener)
            write_parquet(frame, target)
        relpath = f"{perp}/oi.parquet"
        series[relpath] = series_entry(frame, relpath)

    fetched_at = now.isoformat()
    manifest = build_manifest(series, written_at=fetched_at, provenance={"fetched_at": fetched_at, "source": _BASE_URL})
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def read_oi_series(out_root: Path, perp: str) -> pl.DataFrame:
    """Read `perp`'s OI series written by `build_oi_substrate` back into a frame."""
    return read_parquet(out_root / perp / "oi.parquet")
