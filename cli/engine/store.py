"""The live price store (spec 00041): a per-pair x grid Parquet mirror of the frozen canonical
dataset, kept warm by REST gap-fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from cli.engine.errors import EngineError
from cli.logging import get_logger
from cli.ohlc.dataset import read_parquet, to_frame, write_parquet
from cli.ohlc.fetch import PAIR_KEYS as _FETCH_PAIR_KEYS
from cli.ohlc.fetch import fetch_ohlc
from cli.ohlc.seam import MIN_SEAM_OVERLAP, drop_in_progress, seam_overlap

logger = get_logger("engine.store")

# The single committed source of truth for the engine's basket (spec 00094). DOT/EUR is kept
# despite the universe regeneration deselecting it -- an owner ruling (T0137), never an
# oversight; tests/test_basket_concordance.py pins it.
BASKET: tuple[str, ...] = (
    "ADA/EUR",
    "AVAX/EUR",
    "BTC/EUR",
    "DOGE/EUR",
    "DOT/EUR",
    "ETH/BTC",
    "ETH/EUR",
    "LINK/EUR",
    "LTC/EUR",
    "SOL/BTC",
    "SOL/EUR",
    "XRP/EUR",
)

# Symbol -> venue key, derived from the one source of truth rather than duplicated. A BASKET
# member absent from the fetch map raises KeyError here, at import -- fail loud, never narrow.
PAIR_KEYS: dict[str, str] = {s: _FETCH_PAIR_KEYS[s] for s in BASKET}

GRID_INTERVALS = (1440, 240)

_REFRESH_MIN_OVERLAP = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SeedEntry:
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
    pair: str
    interval: int
    appended: int
    tail_fresh_through: datetime


@dataclass(frozen=True)
class RefreshReport:
    entries: tuple[RefreshEntry, ...]


def _store_path(root: Path, symbol: str, interval: int) -> Path:
    base, quote = symbol.split("/")
    return root / base / quote / f"{interval}.parquet"


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
    """Returns `(overlap_bars, replaced_tail_rows, merged_frame)` positionally.

    Sibling: cli/ohlc/reach.py::_merge_or_detach guards the same seam definition under its own policy."""
    overlap_bars, mismatches = seam_overlap(store_frame, rest_frame)
    if overlap_bars < min_overlap:
        raise EngineError(
            f"{fn_name}: window shortfall for {pair}@{interval} — only {overlap_bars} shared stamp(s) between "
            f"the store tail and the REST fetch (need >= {min_overlap}); {shortfall_hint}"
        )

    absent = mismatches.filter(pl.col("close").is_null() | pl.col("close_rest").is_null())
    if absent.height:
        stamp = absent["ts"][0]
        sides = [
            name
            for name, value in (("the store tail", absent["close"][0]), ("the REST fetch", absent["close_rest"][0]))
            if value is None
        ]
        raise EngineError(
            f"{fn_name}: overlap mismatch for {pair}@{interval} at {stamp} — a shared stamp's close is absent on "
            f"{' and '.join(sides)}, and an absent close is a disagreement whatever the other side carries, so no "
            f"re-seed replaces a store close with it; {mismatch_hint}"
        )

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


def _read_frame(path: Path, pair: str, interval: int, fn_name: str) -> pl.DataFrame:
    try:
        return read_parquet(path)
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise EngineError(f"{fn_name}: cannot read {path} for {pair}@{interval} — {exc}") from exc


def _require_joinable_ts(frame: pl.DataFrame, path: Path, pair: str, interval: int, fn_name: str, *, frozen: bool) -> None:
    """Refuse a `ts` column `seam_overlap` cannot join, and a `close` no reader can take as a price, before either gets there.

    Anything but `Datetime("us", "UTC")` raises a bare `SchemaError` at the join, past `run_cycle`'s
    `except OHLCError` and both commands' `except EngineError` (T0193). The equality is exact because
    `ns`/`ms` and a non-UTC zone all survive a parquet round trip and all break the same join; `to_frame`
    writes exactly this dtype, so no frame this repo wrote is refused.

    `frozen` picks between the two recoveries below, which is why the caller says which file it handed over;
    `cli/registry/observed.py` is where a recast canonical is refused.
    """
    dtype = frame.schema.get("ts")
    if dtype == pl.Datetime("us", "UTC"):
        close = frame.schema.get("close")
        if close is None:
            raise EngineError(f"{fn_name}: {path} has no close column for {pair}@{interval}")
        if not close.is_numeric():
            raise EngineError(
                f"{fn_name}: {path} types close as {close} for {pair}@{interval}, not a number a reader can take as a price"
            )
        return
    recovery = (
        "rebuild the set (`zcrypto data rebuild ohlc-full --no-push`, then promote the verified sibling into the "
        "canonical name) rather than recast this file, whose `dataset_hash` a recast changes and nothing in this "
        "tree re-vouches"
        if frozen
        else "copy the file aside (outside the dataset root), recast the column "
        'in place (`pl.col("ts").cast(pl.Datetime("us", "UTC"))`) and re-run; a re-seed refuses this file, and '
        "one forced by deleting it drops every bar the canonical lacks unless the re-seed's seam holds -- six shared "
        "stamps into the canonical and every shared close equal"
    )
    raise EngineError(
        f"{fn_name}: {path} types ts as {dtype} for {pair}@{interval}, not the aware "
        f'`Datetime("us", "UTC")` every reader joins on -- {recovery}'
    )


def seed_store(
    store_dir: Path,
    canonical_dir: Path,
    *,
    fetch_fn=fetch_ohlc,
    clock=_utc_now,
) -> SeedReport:
    """Bootstrap or repair `store_dir` from `canonical_dir` plus a REST gap-fill, per pair x grid: the
    canonical file is copied only when the store file is absent, so a re-run is idempotent and treats a
    close mismatch as a poisoned tail to repair rather than the abort a first seed takes."""
    now = clock()
    entries = []
    for pair, pair_key in PAIR_KEYS.items():
        for interval in GRID_INTERVALS:
            store_path = _store_path(store_dir, pair, interval)
            store_existed = store_path.exists()
            canonical_path = _store_path(canonical_dir, pair, interval)
            if not store_existed:
                # The canonical is checked BEFORE it is copied: a refused copy left in the store is a file the
                # next run refuses again, naming a path the operator never broke.
                canonical_frame = _read_frame(canonical_path, pair, interval, "seed_store")
                _require_joinable_ts(canonical_frame, canonical_path, pair, interval, "seed_store", frozen=True)
                write_parquet(canonical_frame, store_path)

            store_frame = _read_frame(store_path, pair, interval, "seed_store")
            _require_joinable_ts(store_frame, store_path, pair, interval, "seed_store", frozen=False)
            rest_frame = drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)

            overlap_bars, replaced, merged = _reconcile(
                store_frame,
                rest_frame,
                fn_name="seed_store",
                pair=pair,
                interval=interval,
                min_overlap=MIN_SEAM_OVERLAP,
                allow_replace=store_existed,
                shortfall_hint="use the quarterly OHLCVT dump",
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
    """Append newly completed bars to an already-seeded `store_dir`, per pair x grid, refusing rather
    than repairing a seam that does not hold -- the recovery is a re-seed."""
    now = clock()
    entries = []
    for pair, pair_key in pairs.items():
        for interval in GRID_INTERVALS:
            store_path = _store_path(store_dir, pair, interval)
            store_frame = _read_frame(store_path, pair, interval, "refresh_store")
            # An `EngineError` rather than the loop's retried `OHLCError`: a dtype-broken file is not a
            # transport error and every retry re-reads the same column.
            _require_joinable_ts(store_frame, store_path, pair, interval, "refresh_store", frozen=False)
            rest_frame = drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)

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


def read_store_series(store_dir: Path, symbol: str, interval: int) -> tuple[list[datetime], list[float | None]]:
    """A frame this function cannot turn into a price series is refused as an `EngineError` rather than as
    whatever polars or `math` raises, so `soak-check` aborts naming the file: a store frame the engine cannot
    parse is a broken input, not a degraded metric (T0193). The column reads are inside the try for the same
    reason, and both columns are checked because the return type promises both; `to_frame` writes `close` as
    Float64 and a UTC-aware `ts` (`_require_joinable_ts` above owns the exact dtype), so no frame this repo
    wrote is refused here.

    It reads TYPES, never the stamps' values — T0201 carries what that leaves open, and
    `tests/test_engine_soak_command.py::test_soak_check_degrades_at_rc_0_on_a_store_frame_whose_stamps_are_the_wrong_instants`
    drives it.

    A non-finite close is NOT refused here. Spec 00059 D7 rules only the rebuild-unavailable case (the two
    internals metrics read `n/a` with a reason rather than voiding the run); no decision rules on a store `nan`,
    and what the code does with one is T0199's subject. What is refused is anything outside `int`/`float`, which is wider than
    "anything `math.isfinite` would raise on" — a `Decimal` has `__float__`, so `math.isfinite` takes it and
    this door does not, and the narrower rule would need a conversion this reader has no business making."""
    path = _store_path(store_dir, symbol, interval)
    try:
        frame = read_parquet(path)
        stamps, closes = frame["ts"].to_list(), frame["close"].to_list()
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise EngineError(f"read_store_series: cannot read {path} for {symbol}@{interval} — {exc}") from exc
    for k, stamp in enumerate(stamps):
        # Aware, not merely a datetime: a naive stamp satisfies `isinstance` and then dies on the canonical leg
        # in `select_model_inputs`' `sorted()`, ordered against the other legs' aware stamps -- the same site an
        # epoch int reaches. `utcoffset() is None` is the whole test, Python's own definition of naive
        # (`cli/engine/execgate.py:148-152` records the rule).
        if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
            raise EngineError(f"read_store_series: {path} ts[{k}] for {symbol}@{interval} is not an aware datetime: {stamp!r}")
    for k, close in enumerate(closes):
        if close is not None and (isinstance(close, bool) or not isinstance(close, (int, float))):
            raise EngineError(f"read_store_series: {path} close[{k}] for {symbol}@{interval} is not a number: {close!r}")
    return stamps, closes
