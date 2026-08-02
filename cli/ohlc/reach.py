"""REST reach-round: carry the canonical OHLC basket forward from Kraken's public OHLC endpoint.

The quarterly OHLCVT dumps stop on a quarter boundary, so the canonical set trails the present by up
to a quarter. Kraken's REST OHLC endpoint serves the most recent ~720 bars per interval -- a
**receding** window whose reach depends entirely on the interval: ~720 days at the daily grid, ~120
days at 4h, but only ~30 days at 1h. So at any moment part of the basket's REST tail still overlaps
the canonical tail (and can be joined into one continuous series) while the rest does not.

That asymmetry is the whole design, and it is why this is not simply `seed_store` over a new root:

- **Overlapping** -> seam-checked and merged, written as `<interval>.parquet`, drop-in compatible
  with any `ohlc-full` reader.
- **Not overlapping** -> written as `<interval>.detached.parquet`, under a filename no `ohlc-full`
  reader globs, so a detached segment can never be silently spliced across the gap into a continuous
  series. Promotion is a later, deliberate step once an intervening dump closes the gap.

Why keep a tail that cannot be joined? A REST bar vanishes from the endpoint once the window recedes
past it, so it is retrievable only while the window still reaches it. Whether losing it would be
PERMANENT depends on whether a scheduled dump covers the same span -- and that varies, so this module
does not assume either way. For the segment this first produced (1h, 2026-06-23 onward) the Q2+Q3
dumps will cover it, making the capture a **bridge** (1h goes continuous months before Q3 lands) and
an independent REST-vs-dump cross-check, rather than a rescue. For any window no scheduled dump
covers, the same write is the only chance to hold the data at all.

Refusing to write a detached tail would throw that away; writing it as `<interval>.parquet` would
manufacture a series with an invisible hole. The split filename loses neither the data nor the truth.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from cli.logging import get_logger
from cli.ohlc.dataset import dataset_hash, read_parquet, to_frame, write_parquet
from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc

logger = get_logger("ohlc.reach")

# Intervals of the canonical basket (`cli/data/rebuild.py::_OHLC_INTERVALS`), as ints.
REACH_INTERVALS: tuple[int, ...] = (1440, 240, 60)

# Shared stamps required before a seam counts as verified. Matches the engine store's seed floor:
# below this the join rests on too few agreeing bars to distinguish "the same series" from
# "coincidentally equal at the boundary".
MIN_SEAM_OVERLAP = 6

# Seconds between successive public-API calls. A reach round makes one call per symbol x interval --
# 30 on the current basket -- and Kraken throttles this family: `cli/trades/rest.py` records 1.5 s
# being DEMONSTRABLY refused (`EGeneral:Too many requests`) on the live bulk run 2026-07-16 (T0053).
# The same measured floor is used here rather than a fresh guess.
MIN_REST_INTERVAL_SECONDS = 3.0


@dataclass(frozen=True)
class ReachEntry:
    """One symbol x interval's outcome."""

    symbol: str
    interval: int
    status: str  # "continuous" | "detached"
    rest_first: datetime
    rest_last: datetime
    overlap_bars: int  # shared stamps with the canonical tail; 0 when detached
    appended: int  # rows written beyond the canonical tail (continuous) or in total (detached)
    gap_bars: int  # whole intervals between the canonical tail and the REST head; 0 when continuous


@dataclass(frozen=True)
class ReachReport:
    entries: tuple[ReachEntry, ...]

    @property
    def detached(self) -> tuple[ReachEntry, ...]:
        return tuple(e for e in self.entries if e.status == "detached")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _drop_in_progress(frame: pl.DataFrame, interval: int, now: datetime) -> pl.DataFrame:
    """Drop any row whose interval END lies after `now`.

    Kraken's OHLC response always includes the currently-forming candle as its final row; persisting
    it would write a bar that is still changing. A row ending exactly at `now` is complete, so kept.
    """
    return frame.filter((pl.col("ts") + pl.duration(minutes=interval)) <= now)


def _canonical_symbols(canonical_root: Path, interval: int) -> list[str]:
    """Symbols carrying a canonical file for `interval`, in sorted order.

    Derived from the canonical tree rather than from a hardcoded basket, so a symbol the canonical
    set does not carry (e.g. the BTC-quoted legs, which capture holds but the dumps do not) is simply
    out of scope here instead of raising.
    """
    return sorted(p.parent.parent.name for p in canonical_root.glob(f"*/EUR/{interval}.parquet"))


def _merge_or_detach(
    canonical: pl.DataFrame,
    rest: pl.DataFrame,
    *,
    symbol: str,
    interval: int,
) -> tuple[str, pl.DataFrame, int, int]:
    """Return `(status, frame_to_write, overlap_bars, gap_bars)`.

    Raises `OHLCError` when the two frames overlap but the seam does not hold -- a thin overlap or a
    disagreeing close. Both are refusals to publish an unverified join, never a reason to fall back
    to `detached`: a detached write is for an HONEST gap, and quietly detaching a *failed* seam would
    turn a data-integrity error into a silently truncated series.
    """
    canonical_tail = canonical["ts"].max()
    rest_head = rest["ts"].min()

    if rest_head > canonical_tail:
        gap_bars = int((rest_head - canonical_tail).total_seconds() // (interval * 60))
        return "detached", rest, 0, gap_bars

    shared = canonical.join(rest, on="ts", how="inner", suffix="_rest")
    overlap_bars = shared.height
    if overlap_bars < MIN_SEAM_OVERLAP:
        raise OHLCError(
            f"reach_round: seam too thin for {symbol}@{interval} -- only {overlap_bars} shared stamp(s) "
            f"between the canonical tail and the REST window (need >= {MIN_SEAM_OVERLAP}); the REST window "
            "is receding past the canonical tail, so this series needs an intervening OHLCVT dump"
        )

    mismatches = shared.filter(pl.col("close") != pl.col("close_rest"))
    if mismatches.height:
        stamp = mismatches["ts"][0]
        raise OHLCError(
            f"reach_round: seam mismatch for {symbol}@{interval} at {stamp} -- a shared stamp's close "
            f"disagrees between the canonical set and the REST window ({mismatches['close'][0]} vs "
            f"{mismatches['close_rest'][0]}); the canonical set is authoritative, so this is a data-integrity "
            "error, not a seam to paper over"
        )

    rest_only = rest.filter(~pl.col("ts").is_in(set(canonical["ts"].to_list())))
    merged = pl.concat([canonical, rest_only]).sort("ts")
    return "continuous", merged, overlap_bars, 0


def reach_round(
    canonical_root: Path,
    out_root: Path,
    *,
    intervals: tuple[int, ...] = REACH_INTERVALS,
    fetch_fn=fetch_ohlc,
    clock=_utc_now,
    sleep_fn=time.sleep,
) -> ReachReport:
    """Extend every canonical symbol x interval forward with Kraken's REST OHLC window.

    Writes into `out_root` only -- `canonical_root` is read-only, so the canonical set stays
    immutable (the standing rule; a revision mints a sibling). Each series lands as either
    `<interval>.parquet` (seam-verified continuous) or `<interval>.detached.parquet` (an honest gap,
    kept because the bars expire), and `manifest.json` records the status per series alongside the
    basket hash.
    """
    now = clock()
    entries: list[ReachEntry] = []
    fetched = 0

    for interval in intervals:
        for symbol in _canonical_symbols(canonical_root, interval):
            pair_key = PAIR_KEYS.get(symbol)
            if pair_key is None:
                logger.warning("reach_round: no REST pair key for %s -- skipping", symbol)
                continue

            canonical = read_parquet(canonical_root / symbol / "EUR" / f"{interval}.parquet")
            # Pace BETWEEN calls only -- never before the first, so a single-series run pays nothing.
            if fetched:
                sleep_fn(MIN_REST_INTERVAL_SECONDS)
            fetched += 1
            rest = _drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)
            if rest.is_empty():
                logger.warning("reach_round: REST returned no completed bars for %s@%d", symbol, interval)
                continue

            status, frame, overlap_bars, gap_bars = _merge_or_detach(canonical, rest, symbol=symbol, interval=interval)
            name = f"{interval}.parquet" if status == "continuous" else f"{interval}.detached.parquet"
            write_parquet(frame, out_root / symbol / "EUR" / name)

            appended = frame.height - canonical.height if status == "continuous" else frame.height
            entries.append(
                ReachEntry(
                    symbol=symbol,
                    interval=interval,
                    status=status,
                    rest_first=rest["ts"].min(),
                    rest_last=rest["ts"].max(),
                    overlap_bars=overlap_bars,
                    appended=appended,
                    gap_bars=gap_bars,
                )
            )

    report = ReachReport(entries=tuple(entries))
    _write_manifest(out_root, report, now)
    return report


def _write_manifest(out_root: Path, report: ReachReport, now: datetime) -> None:
    """Record per-series provenance plus SEPARATE continuous/detached basket hashes.

    Two things this deliberately does not do. It does not emit one set-wide continuity claim -- a
    reach set is mixed by construction, so the per-series rows are how a consumer learns which files
    it may treat as continuous. And it does not fold detached series into `basket_sha256`: that hash
    names the joinable basket, and mixing in a segment the module just refused to join would
    contradict the split the filenames exist to enforce. Detached content gets its own hash instead.

    The hash-of-hashes shape (per-series sha256, concatenated in sorted order) matches
    `cli/backfill/backfill.py::backfill_basket`, so a reach manifest is comparable with the canonical
    set's and is independent of any cross-series row ordering.
    """
    series: list[dict] = []
    for entry in report.entries:
        name = f"{entry.interval}.parquet" if entry.status == "continuous" else f"{entry.interval}.detached.parquet"
        frame = read_parquet(out_root / entry.symbol / "EUR" / name)
        series.append(
            {
                **asdict(entry),
                "rest_first": entry.rest_first.isoformat(),
                "rest_last": entry.rest_last.isoformat(),
                "rows": frame.height,
                "first_ts": frame["ts"].min().isoformat(),
                "last_ts": frame["ts"].max().isoformat(),
                "sha256": dataset_hash(frame),
            }
        )

    def _basket(status: str) -> str:
        digests = [r["sha256"] for r in sorted(series, key=lambda r: (r["symbol"], r["interval"])) if r["status"] == status]
        return hashlib.sha256("".join(digests).encode()).hexdigest() if digests else ""

    manifest = {
        "built_at": now.isoformat(),
        "basket_sha256": _basket("continuous"),
        "detached_sha256": _basket("detached"),
        "min_seam_overlap": MIN_SEAM_OVERLAP,
        "series": series,
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
