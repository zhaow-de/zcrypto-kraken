"""The live price store (spec 00041 SS the live price store): a per-pair x grid Parquet mirror of
the frozen canonical dataset, kept warm by REST gap-fills. `seed_store` bootstraps/repairs the
store from the canonical dataset plus a REST fetch; `refresh_store` appends newly completed bars
each cycle. Both apply the same "drop the in-progress candle" rule to REST rows (Kraken's OHLC
response always includes the currently-forming candle as its last row) before reconciling against
the store's own tail -- the two distinct seam guards (window shortfall, overlap equality) are
never skipped, and a seed re-run is the documented repair for a poisoned store tail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from cli.engine.errors import EngineError
from cli.logging import get_logger
from cli.ohlc.dataset import read_parquet, to_frame, write_parquet
from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc

logger = get_logger("engine.store")

GRID_INTERVALS = (1440, 240)

_SEED_MIN_OVERLAP = 6
_REFRESH_MIN_OVERLAP = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SeedEntry:
    """One pair x grid's seeding outcome."""

    pair: str
    interval: int
    overlap_bars: int
    appended: int
    replaced_tail_rows: int


@dataclass(frozen=True)
class SeedReport:
    entries: tuple[SeedEntry, ...]


@dataclass(frozen=True)
class RefreshEntry:
    """One pair x grid's refresh outcome."""

    pair: str
    interval: int
    appended: int
    tail_fresh_through: datetime


@dataclass(frozen=True)
class RefreshReport:
    entries: tuple[RefreshEntry, ...]


def _store_path(root: Path, asset: str, interval: int) -> Path:
    return root / asset / "EUR" / f"{interval}.parquet"


def _drop_in_progress(frame: pl.DataFrame, interval: int, now: datetime) -> pl.DataFrame:
    """Drop any row whose interval end (stamp + interval minutes) lies after `now` -- Kraken's OHLC
    response always includes the currently-forming candle as its last row. A row ending exactly at
    `now` is kept."""
    return frame.filter((pl.col("ts") + pl.duration(minutes=interval)) <= now)


def _reconcile(
    store_frame: pl.DataFrame,
    rest_frame: pl.DataFrame,
    *,
    fn_name: str,
    pair: str,
    interval: int,
    min_overlap: int,
    allow_replace: bool,
    shortfall_hint: str,
    mismatch_hint: str,
) -> tuple[int, int, pl.DataFrame]:
    """Join `store_frame` and `rest_frame` on `ts`, enforce the seam guards, and return
    `(overlap_bars, replaced_tail_rows, merged_frame)`.

    Guard (i): `overlap_bars >= min_overlap`, else `EngineError` naming the shortfall + `shortfall_hint`.
    Guard (ii): closes must match exactly on every shared stamp. When `allow_replace` is False, any
    mismatch raises `EngineError` naming the mismatched stamp + `mismatch_hint`. When True, mismatched
    shared rows are replaced with the REST version (the poisoned-tail repair) and counted in the
    returned replaced count.

    `merged_frame` keeps every store row whose `ts` isn't a replaced mismatch, swaps in the REST
    row for each replaced mismatch, and appends REST rows whose `ts` isn't in the store at all.
    """
    shared = store_frame.join(rest_frame, on="ts", how="inner", suffix="_rest")
    overlap_bars = shared.height
    if overlap_bars < min_overlap:
        raise EngineError(
            f"{fn_name}: window shortfall for {pair}@{interval} — only {overlap_bars} shared stamp(s) between "
            f"the store tail and the REST fetch (need >= {min_overlap}); {shortfall_hint}"
        )

    mismatches = shared.filter(pl.col("close") != pl.col("close_rest"))
    if mismatches.height and not allow_replace:
        stamp = mismatches["ts"][0]
        raise EngineError(
            f"{fn_name}: overlap mismatch for {pair}@{interval} at {stamp} — a shared stamp's close disagrees "
            f"between the store tail and the REST fetch; {mismatch_hint}"
        )

    replaced_ts = set(mismatches["ts"].to_list())
    store_ts = set(store_frame["ts"].to_list())
    store_kept = store_frame.filter(~pl.col("ts").is_in(replaced_ts))
    replaced_rows = rest_frame.filter(pl.col("ts").is_in(replaced_ts))
    rest_only = rest_frame.filter(~pl.col("ts").is_in(store_ts))
    merged = pl.concat([store_kept, replaced_rows, rest_only]).sort("ts")
    return overlap_bars, len(replaced_ts), merged


def seed_store(
    store_dir: Path,
    canonical_dir: Path,
    *,
    fetch_fn=fetch_ohlc,
    clock=_utc_now,
) -> SeedReport:
    """Bootstrap/repair `store_dir` from `canonical_dir` plus a REST gap-fill, per pair x grid.

    The canonical file is copied into the store only if the store file is absent (idempotent). The
    REST fetch is then reconciled against the store's tail with two guards: an overlap of fewer
    than 6 shared stamps is a window shortfall (`EngineError`); a close mismatch on a shared stamp
    aborts (`EngineError`) UNLESS the store file already existed before this call, in which case the
    mismatched rows are treated as a poisoned tail and replaced with the REST version (recorded in
    `SeedEntry.replaced_tail_rows` and logged). Only new completed bars beyond the store's tail are
    appended.
    """
    now = clock()
    entries = []
    for pair, pair_key in PAIR_KEYS.items():
        for interval in GRID_INTERVALS:
            store_path = _store_path(store_dir, pair, interval)
            store_existed = store_path.exists()
            if not store_existed:
                canonical_path = _store_path(canonical_dir, pair, interval)
                write_parquet(read_parquet(canonical_path), store_path)

            store_frame = read_parquet(store_path)
            rest_frame = _drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)

            overlap_bars, replaced, merged = _reconcile(
                store_frame,
                rest_frame,
                fn_name="seed_store",
                pair=pair,
                interval=interval,
                min_overlap=_SEED_MIN_OVERLAP,
                allow_replace=store_existed,
                shortfall_hint="REST window no longer reaches the tail — use the quarterly OHLCVT dump",
                mismatch_hint="this is a fresh canonical copy, so a disagreement with REST is a data-integrity error",
            )
            appended = merged.height - store_frame.height
            if replaced or appended:
                write_parquet(merged, store_path)
            if replaced:
                logger.warning(
                    "seed_store: replaced %d divergent tail row(s) for %s@%d (poisoned-tail repair)",
                    replaced,
                    pair,
                    interval,
                )
            entries.append(
                SeedEntry(pair=pair, interval=interval, overlap_bars=overlap_bars, appended=appended, replaced_tail_rows=replaced)
            )
    return SeedReport(entries=tuple(entries))


def refresh_store(
    store_dir: Path,
    *,
    pairs: dict[str, str] = PAIR_KEYS,
    fetch_fn=fetch_ohlc,
    clock=_utc_now,
) -> RefreshReport:
    """Append newly completed bars to an already-seeded `store_dir`, per pair x grid.

    The REST fetch's in-progress candle is dropped first, then reconciled against the store's tail
    requiring >= 1 shared stamp (a zero-overlap refresh means the store is catastrophically stale --
    a distinct `EngineError`) and exact close equality on every shared stamp (a mismatch is a
    poisoned tail -- a distinct `EngineError` naming `zcrypto engine seed` as the recovery). Only new
    completed bars beyond the store's tail are appended.
    """
    now = clock()
    entries = []
    for pair, pair_key in pairs.items():
        for interval in GRID_INTERVALS:
            store_path = _store_path(store_dir, pair, interval)
            store_frame = read_parquet(store_path)
            rest_frame = _drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)

            _, _, merged = _reconcile(
                store_frame,
                rest_frame,
                fn_name="refresh_store",
                pair=pair,
                interval=interval,
                min_overlap=_REFRESH_MIN_OVERLAP,
                allow_replace=False,
                shortfall_hint="the store is catastrophically stale, run `zcrypto engine seed` to re-seed it",
                mismatch_hint="the store tail may be poisoned, run `zcrypto engine seed` to repair it",
            )
            appended = merged.height - store_frame.height
            if appended:
                write_parquet(merged, store_path)
                logger.info("refresh_store: appended %d bar(s) for %s@%d", appended, pair, interval)
            entries.append(RefreshEntry(pair=pair, interval=interval, appended=appended, tail_fresh_through=merged["ts"].max()))
    return RefreshReport(entries=tuple(entries))


def read_store_series(store_dir: Path, asset: str, interval: int) -> tuple[list[datetime], list[float | None]]:
    """Read `asset`'s full-history `(ts, close)` series for `interval` from the store."""
    frame = read_parquet(_store_path(store_dir, asset, interval))
    return frame["ts"].to_list(), frame["close"].to_list()
