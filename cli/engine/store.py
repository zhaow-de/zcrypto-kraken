"""The live price store (spec 00041): a per-pair x grid Parquet mirror of the frozen canonical
dataset, kept warm by REST gap-fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from cli.engine.errors import EngineError
from cli.logging import get_logger
from cli.ohlc.dataset import FRAME_SCHEMA, read_parquet, to_frame, write_parquet
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
    absent_store_hint: str,
    absent_rest_hint: str,
) -> tuple[int, int, pl.DataFrame]:
    """Returns `(overlap_bars, replaced_tail_rows, merged_frame)` positionally. An absent close at a shared stamp is
    refused whatever `allow_replace` is; the hint follows the side that holds the null ALONE, because a null the fetch
    also holds at that stamp would be refilled from this same fetch by the re-seed a store repair prescribes. Each side
    is read over all the absent rows and carries its own first absent stamp: the first row's side and stamp are that
    row's alone.

    Sibling: cli/ohlc/reach.py::_merge_or_detach guards the same seam definition under its own policy."""
    overlap_bars, mismatches = seam_overlap(store_frame, rest_frame)
    if overlap_bars < min_overlap:
        raise EngineError(
            f"{fn_name}: window shortfall for {pair}@{interval} — only {overlap_bars} shared stamp(s) between "
            f"the store tail and the REST fetch (need >= {min_overlap}); {shortfall_hint}"
        )

    absent = mismatches.filter(pl.col("close").is_null() | pl.col("close_rest").is_null())
    if absent.height:
        sides = [
            f"{name} (first at {absent.filter(pl.col(column).is_null())['ts'][0]})"
            for name, column in (("the store tail", "close"), ("the REST fetch", "close_rest"))
            if absent[column].null_count()
        ]
        store_only = absent.filter(pl.col("close").is_null() & pl.col("close_rest").is_not_null())
        hint = absent_store_hint if store_only.height else absent_rest_hint
        raise EngineError(
            f"{fn_name}: overlap mismatch for {pair}@{interval} — a shared stamp's close is absent on "
            f"{' and '.join(sides)}, and an absent close is a disagreement whatever the other side carries, so no "
            f"re-seed replaces a store close with it; {hint}"
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


_HOST_REDELIVERY = (
    "on the engine host the store is re-delivered, not seeded: infra/runbooks/engine.md's zcrypto-engine-cycle-stale "
    "section holds the procedure, and `zcrypto engine seed` is the workstation's command"
)
_STORE_RECOVERY = (
    "on the workstation move this leg aside (outside the store) and run `zcrypto engine seed`, which copies the "
    "canonical for the absent file and fills the gap from REST; what is lost is any bar past the canonical's tail that "
    "REST no longer reaches, and when the canonical's tail is itself outside the REST window the seed refuses on its own "
    f"shortfall until the next quarterly ingest is minted; {_HOST_REDELIVERY}"
)
_REBUILD_THE_SET = (
    "rebuild the set (`zcrypto data rebuild ohlc-full --no-push` mints the newer stamped sibling the next seed reads "
    "once it is whole)"
)
_CANONICAL_RECOVERY = (
    f"nothing was copied to the store; a canonical is the data pipeline's to republish: {_REBUILD_THE_SET} rather "
    "than recast this file, whose `dataset_hash` a recast changes and nothing in this tree re-vouches"
)
_REST_REFUSED = (
    "nothing from this fetch is written, so there is no store repair: the store holds what it held before the fetch, "
    "the next run fetches again, and a row that returns is the venue's to answer, not the store's"
)
_ABSENT_REST_HINT = (
    "the REST fetch carries the absent close, so there is no store repair: the next run fetches again, and a fetch "
    "that returns it again is the venue's row to read, not the store's"
)
_EMPTY_REST_HINT = (
    "the REST fetch carries no completed bar, so there is no store repair: the next run fetches again, and a fetch "
    "that returns none again is the venue's to answer, not the store's"
)
_FRESH_COPY = "this is a fresh canonical copy, so a disagreement with REST is a data-integrity error"
_RESEED_REFUSED = "the re-seed replaced nothing, because the seam refused before the replace"

_SEAM_REACHED = (
    "the REST fetch's oldest stamp is the store's last stamp or earlier, so the window still reaches the tail and a "
    "receded window is refuted"
)
_FIRST_SEED_LEG_LANDED = (
    "the leg is the canonical's, copied into the store by this seed, and a seed over a present file never reads the canonical again"
)
_FIRST_SEED_LEG_ASIDE = f"{_FIRST_SEED_LEG_LANDED}, so move this leg aside (outside the store) and"
_FIRST_SEED_REBUILD = f"{_FIRST_SEED_LEG_ASIDE} {_REBUILD_THE_SET}"
_DISJOINT_CANONICAL_DUMP = f"{_FIRST_SEED_LEG_ASIDE} use the quarterly OHLCVT dump"


def _seam_holes_hint(store_side_repair: str) -> str:
    """Called only once the short-leg arm has passed and `rest_head <= store_tail` holds: both claims the text opens
    with are the caller's routing, not this function's."""
    return (
        f"{_SEAM_REACHED}, and the store leg carries enough rows to clear the floor on its own: the shared stamps still "
        "fall short of the floor, so the stamps the seam needs are missing on one side or the other -- absent from the "
        "fetch's answer, or absent from the store leg, whose own gaps can fall exactly where the fetch covers -- and "
        "nothing here measures whose they are; read the two sides' stamps across the span they both cover, a store leg "
        "whole across it putting the holes in the fetch's answer and a gapped one putting them in the store, and if the "
        "fetch is the side with the holes there is no store repair -- the next run fetches again, and an answer short of "
        "the floor again is the venue's to explain, not the store's; and if the store leg is the holed side, "
        f"{store_side_repair}"
    )


def _short_leg_shortfall_hint(store_height: int, min_overlap: int, store_side_repair: str) -> str:
    """The one arm the store leg settles alone, which is why it is read before the fetch is weighed at all: the
    shared stamps are a subset of the leg's own, so a leg holding fewer rows than the floor cannot clear it whatever
    the venue sends, an empty answer included, and the fetch is then neither read nor spoken of."""
    return (
        f"the store leg carries {store_height} row(s) against a floor of {min_overlap}, so no answer the venue could "
        f"send clears it and the store side is the cause: {store_side_repair}"
    )


def _disjoint_shortfall_hint(
    store_frame: pl.DataFrame,
    rest_frame: pl.DataFrame,
    *,
    store_predates_this_run: bool,
    store_side_repair: str,
) -> str:
    """Called only once the caller has ruled out `rest_head <= store_tail`: the two sides then share no stamp by
    construction, so the overlap is zero and proves nothing about which side receded -- read as a store fault
    regardless, it would send an operator to repair a leg that was never behind."""
    store_tail = store_frame["ts"].max()
    rest_head = rest_frame["ts"].min()
    store_side = (
        "the store fell behind the REST window's reach before this run started"
        if store_predates_this_run
        else "the canonical this run copied into the store was already behind the REST window's reach"
    )
    return (
        f"the REST fetch's oldest stamp ({rest_head}) is newer than the store's own last stamp ({store_tail}), so the "
        f"two sides share no stamp by construction; the {rest_frame.height} completed row(s) the fetch carries cannot "
        f"say on their own whether the venue answered with a shorter history than the seam needs, or {store_side} -- read "
        "the store's last stamp against how far behind now it sits to tell them apart, close behind pointing at the "
        "venue's own answer and far behind at the store; if the venue is the cause there is no store repair and the "
        f"next run fetches again, and if the store is the cause, {store_side_repair}"
    )


def _shortfall_hint(
    store_frame: pl.DataFrame,
    rest_frame: pl.DataFrame,
    *,
    min_overlap: int,
    store_predates_this_run: bool,
    disjoint_store_side_repair: str,
) -> str:
    """`_reconcile`'s `shortfall_hint`. The leg's own repair, which the short-leg and holes arms share, is its
    provenance alone -- which `store_predates_this_run` already carries -- so no caller passes one for an arm it may
    not even reach."""
    leg_repair = _STORE_RECOVERY if store_predates_this_run else _FIRST_SEED_REBUILD
    if store_frame.height < min_overlap:
        return _short_leg_shortfall_hint(store_frame.height, min_overlap, leg_repair)
    if rest_frame.is_empty():
        if store_predates_this_run:
            return _EMPTY_REST_HINT
        return f"{_EMPTY_REST_HINT}; {_FIRST_SEED_LEG_LANDED}"
    if rest_frame["ts"].min() <= store_frame["ts"].max():
        return _seam_holes_hint(leg_repair)
    return _disjoint_shortfall_hint(
        store_frame,
        rest_frame,
        store_predates_this_run=store_predates_this_run,
        store_side_repair=disjoint_store_side_repair,
    )


def _frame_differences(frame: pl.DataFrame, interval: int) -> list[str]:
    """The first failing arm's differences, the arms ordered so a later one may presume the earlier; `None` is an
    absent bar, not an unusable close. Empty when `frame` is the frame the store readers join."""
    differs = [
        f"{column} is {frame.schema[column]}, not {dtype}" if column in frame.schema else f"{column} is absent"
        for column, dtype in FRAME_SCHEMA.items()
        if frame.schema.get(column) != dtype
    ]
    differs += [f"{column} is not a column of it" for column in frame.schema if column not in FRAME_SCHEMA]
    if differs:
        return differs
    if frame.columns != list(FRAME_SCHEMA):
        return [f"the columns are in another order ({', '.join(frame.columns)})"]
    if frame.is_empty():
        return ["it has no rows"]
    stamps = frame["ts"]
    if stamps.null_count():
        return [f"ts is null in {stamps.null_count()} row(s)"]
    if stamps.n_unique() != frame.height:
        return [f"{frame.height - stamps.n_unique()} row(s) repeat a stamp another row carries"]
    # Microseconds, not seconds: `ts` is `Datetime("us", "UTC")` and `epoch("s")` floors a sub-second offset to a
    # zero remainder, admitting at this door a stamp `cli/engine/soak.py::_on_grid` refuses at the same instant.
    off_grid = frame.filter(pl.col("ts").dt.epoch("us") % (interval * 60 * 1_000_000) != 0)
    if off_grid.height:
        return [f"{off_grid.height} stamp(s) are off the {interval}-minute grid, the first {off_grid['ts'][0].isoformat()}"]
    unusable = frame.with_row_index().filter(
        pl.col("close").is_not_null() & (pl.col("close").is_nan() | pl.col("close").is_infinite() | (pl.col("close") <= 0))
    )
    if unusable.height:
        k, stamp, close = unusable["index"][0], unusable["ts"][0], unusable["close"][0]
        return [f"close[{k}] at {stamp.isoformat()} is {close!r}, not a finite positive number ({unusable.height} such close(s))"]
    return []


def _require_store_frame(frame: pl.DataFrame, path: Path, pair: str, interval: int, fn_name: str, *, frozen: bool) -> None:
    """Refuse a frame the store readers cannot join, merge or price, before the seam, the concat or the snapshot write
    gets it: `_frame_differences` is the check, and `frozen` picks the recovery, which is why the caller says which file
    it handed over. `seed_store` runs this over the canonical BEFORE the copy, so a refused canonical leaves no store
    file for the next run to refuse under the store's recovery; `to_frame` writes exactly this schema, so no schema or
    order arm refuses a frame this tree wrote. Sibling: `cli/ohlc/reach.py::_read_canonical` holds a canonical the same
    way for the reach."""
    differs = _frame_differences(frame, interval)
    if differs:
        raise EngineError(
            f"{fn_name}: {path} is not the frame the store readers join for {pair}@{interval} -- {'; '.join(differs)}; "
            f"{_CANONICAL_RECOVERY if frozen else _STORE_RECOVERY}"
        )


def _require_rest_frame(frame: pl.DataFrame, pair: str, interval: int, fn_name: str) -> None:
    """Hold the REST fetch to the store frame's width before the merge makes one of its rows resident: a row the door
    refuses, once in the store, is refused at every later boundary and written back by every re-seed from this same
    window. The refusal is the venue's, so it names the fetch rather than a file. `seed_store` runs it BEFORE the
    canonical copy lands, so a refused fetch leaves no store file. The schema, order and repeated-stamp arms cannot
    fire on a frame `to_frame` wrote, and a null stamp, which it does admit, `drop_in_progress` removes before this
    call, so what fires here is the grid arm and the value arm; an empty fetch is left to the seam's shortfall."""
    if frame.is_empty():
        return
    differs = _frame_differences(frame, interval)
    if differs:
        raise EngineError(
            f"{fn_name}: the REST fetch for {pair}@{interval} is not the frame the store readers join -- "
            f"{'; '.join(differs)}; {_REST_REFUSED}"
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
            rest_frame = drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)
            _require_rest_frame(rest_frame, pair, interval, "seed_store")
            if not store_existed:
                # The canonical is checked BEFORE it is copied: a refused copy left in the store is a file the
                # next run refuses again, naming a path the operator never broke.
                canonical_frame = _read_frame(canonical_path, pair, interval, "seed_store")
                _require_store_frame(canonical_frame, canonical_path, pair, interval, "seed_store", frozen=True)
                write_parquet(canonical_frame, store_path)

            store_frame = _read_frame(store_path, pair, interval, "seed_store")
            _require_store_frame(store_frame, store_path, pair, interval, "seed_store", frozen=False)

            overlap_bars, replaced, merged = _reconcile(
                store_frame,
                rest_frame,
                fn_name="seed_store",
                pair=pair,
                interval=interval,
                min_overlap=MIN_SEAM_OVERLAP,
                allow_replace=store_existed,
                shortfall_hint=_shortfall_hint(
                    store_frame,
                    rest_frame,
                    min_overlap=MIN_SEAM_OVERLAP,
                    store_predates_this_run=store_existed,
                    disjoint_store_side_repair=_STORE_RECOVERY if store_existed else _DISJOINT_CANONICAL_DUMP,
                ),
                mismatch_hint=_FRESH_COPY,
                absent_store_hint=(
                    f"{_FRESH_COPY} in the canonical, whose copy already landed: move this leg aside (outside the store) "
                    f"and {_REBUILD_THE_SET}"
                    if not store_existed
                    else f"{_RESEED_REFUSED}, and a re-seed over this file refuses the same absent close -- {_STORE_RECOVERY}"
                ),
                absent_rest_hint=f"{_FRESH_COPY if not store_existed else _RESEED_REFUSED}; {_ABSENT_REST_HINT}",
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
    than repairing a seam that does not hold."""
    now = clock()
    entries = []
    for pair, pair_key in pairs.items():
        for interval in GRID_INTERVALS:
            store_path = _store_path(store_dir, pair, interval)
            store_frame = _read_frame(store_path, pair, interval, "refresh_store")
            # An `EngineError` rather than the loop's retried `OHLCError`: a dtype-broken file is not a
            # transport error and every retry re-reads the same column.
            _require_store_frame(store_frame, store_path, pair, interval, "refresh_store", frozen=False)
            rest_frame = drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)
            _require_rest_frame(rest_frame, pair, interval, "refresh_store")

            _, _, merged = _reconcile(
                store_frame,
                rest_frame,
                fn_name="refresh_store",
                pair=pair,
                interval=interval,
                min_overlap=_REFRESH_MIN_OVERLAP,
                allow_replace=False,
                # The store file was read above, so it predates this run; the short-leg arm is unreachable here,
                # `_REFRESH_MIN_OVERLAP` being 1 and `_require_store_frame` refusing a frame with no rows.
                shortfall_hint=_shortfall_hint(
                    store_frame,
                    rest_frame,
                    min_overlap=_REFRESH_MIN_OVERLAP,
                    store_predates_this_run=True,
                    disjoint_store_side_repair=_STORE_RECOVERY,
                ),
                mismatch_hint=(
                    "the store tail may be poisoned -- on the workstation run `zcrypto engine seed`, whose re-seed over "
                    f"an existing file replaces the disagreeing tail inside the REST window; {_HOST_REDELIVERY}"
                ),
                absent_store_hint=(
                    f"the store tail holds the absent close, which a re-seed over this file refuses again -- {_STORE_RECOVERY}"
                ),
                absent_rest_hint=_ABSENT_REST_HINT,
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
    parse is a broken input, not a degraded metric. The column reads are inside the try for the same reason, and
    both columns are checked because the return type promises both; `to_frame` writes `close` as Float64 and a
    UTC-aware `ts` (`_require_store_frame` above owns the exact dtype), so no frame this repo wrote is refused here.

    It reads TYPES, never the stamps' values: an off-grid stamp passes here and is refused at the door above, and in
    `realized_series` (`cli/engine/soak.py`) for the daily row's scratch store, which no door of this module reads.

    A non-finite close is NOT refused here either: the door above refuses it in a store file, and `realized_series`
    drops the cycle it would score and names the bar and the value on the report's `dropped_tail` line. What is
    refused here is anything outside `int`/`float`, which
    is wider than "anything `math.isfinite` would raise on" -- a `Decimal` has `__float__`, so `math.isfinite`
    takes it and this door does not, and the narrower rule would need a conversion this reader has no business
    making."""
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
