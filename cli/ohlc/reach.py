"""REST reach-round: carry the canonical OHLC basket forward from Kraken's public OHLC endpoint.

The endpoint's window holds a fixed bar count per interval and recedes, so a basket's REST tail overlaps the canonical
tail only in part: overlapping legs are seam-checked into `<interval>.parquet`, the rest into `<interval>.detached.parquet`
-- a name no `ohlc-full` reader globs, so a gap is never silently spliced -- written rather than refused because a REST
bar is unfetchable once the window has receded past it, and promoted only once an intervening dump closes the gap.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from cli.data.manifest import build_manifest, series_entry
from cli.logging import get_logger
from cli.ohlc.dataset import dataset_hash, read_parquet, to_frame, write_parquet
from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import PAIR_KEYS, fetch_ohlc
from cli.ohlc.seam import MIN_SEAM_OVERLAP, drop_in_progress, seam_overlap

logger = get_logger("ohlc.reach")

# Intervals of the canonical basket (`cli/data/rebuild.py::_OHLC_INTERVALS`), as ints.
REACH_INTERVALS: tuple[int, ...] = (1440, 240, 60)

# Seconds between successive public-API calls -- the floor `cli/trades/rest.py` measured on this same throttled
# family (1.5 s was refused as `EGeneral:Too many requests`, T0053); never lower it without a new measurement.
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


def _canonical_symbols(canonical_root: Path, interval: int) -> list[str]:
    """Full `BASE/QUOTE` symbols carrying a canonical file for `interval`, sorted -- read off the canonical tree,
    not a hardcoded basket, so a symbol the canonical set does not carry is out of scope here rather than an error.
    """
    return sorted(f"{p.parent.parent.name}/{p.parent.name}" for p in canonical_root.glob(f"*/*/{interval}.parquet"))


def _merge_or_detach(
    canonical: pl.DataFrame,
    rest: pl.DataFrame,
    *,
    symbol: str,
    interval: int,
) -> tuple[str, pl.DataFrame, int, int]:
    """Return `(status, frame_to_write, overlap_bars, gap_bars)`; a seam that does not hold raises `OHLCError` rather
    than detaching: a failed seam is a data-integrity error, not the HONEST gap `detached` records, and detaching hides it.
    Sibling: cli/engine/store.py::_reconcile guards the same seam definition under its own policy -- a safety fix here likely applies there too.
    """
    canonical_tail = canonical["ts"].max()
    rest_head = rest["ts"].min()

    if rest_head > canonical_tail:
        gap_bars = int((rest_head - canonical_tail).total_seconds() // (interval * 60))
        return "detached", rest, 0, gap_bars

    overlap_bars, mismatches = seam_overlap(canonical, rest)
    if overlap_bars < MIN_SEAM_OVERLAP:
        raise OHLCError(
            f"reach_round: seam too thin for {symbol}@{interval} -- only {overlap_bars} shared stamp(s) "
            f"between the canonical tail and the REST window (need >= {MIN_SEAM_OVERLAP}); the REST window "
            "is receding past the canonical tail, so this series needs an intervening OHLCVT dump"
        )

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

    Writes into `out_root` only: the canonical set is immutable, and a revision mints a sibling root, never an edit.
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

            base, quote = symbol.split("/")

            canonical = read_parquet(canonical_root / base / quote / f"{interval}.parquet")
            # Pace BETWEEN calls only -- never before the first, so a single-series run pays nothing.
            if fetched:
                sleep_fn(MIN_REST_INTERVAL_SECONDS)
            fetched += 1
            rest = drop_in_progress(to_frame(fetch_fn(pair_key, interval)), interval, now)
            if rest.is_empty():
                logger.warning("reach_round: REST returned no completed bars for %s@%d", symbol, interval)
                continue

            status, frame, overlap_bars, gap_bars = _merge_or_detach(canonical, rest, symbol=symbol, interval=interval)
            name = f"{interval}.parquet" if status == "continuous" else f"{interval}.detached.parquet"
            write_parquet(frame, out_root / base / quote / name)

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
    """Record per-series provenance plus separate continuous/detached basket hashes.

    A reach set is mixed by construction, so the per-series rows -- never one set-wide claim -- say which are continuous.
    """
    series: dict[str, dict] = {}
    by_status: dict[str, list[str]] = {"continuous": [], "detached": []}
    # Seam evidence describes one build and one expiring REST window, not content, so it rides in `provenance`,
    # which no digest covers, rather than in the leaf a digest does.
    seam: dict[str, dict] = {}
    for entry in report.entries:
        name = f"{entry.interval}.parquet" if entry.status == "continuous" else f"{entry.interval}.detached.parquet"
        base, quote = entry.symbol.split("/")
        relpath = f"{base}/{quote}/{name}"
        frame = read_parquet(out_root / relpath)
        series[relpath] = series_entry(frame, relpath)
        by_status["continuous" if entry.status == "continuous" else "detached"].append(relpath)
        seam[relpath] = {**asdict(entry), "rest_first": entry.rest_first.isoformat(), "rest_last": entry.rest_last.isoformat()}

    # Declared only when populated: a digest over an empty subset is sha256("") -- a sentinel two
    # unrelated empty sets would share -- so the contract refuses it rather than emitting it.
    subsets = {name: members for name, members in by_status.items() if members}
    # A reach set's identity is its CONTINUOUS legs: folding in a segment the module just refused to join would
    # contradict the split the filenames enforce, and declaring it here spares every consumer from knowing that.
    identity = "subset:continuous" if by_status["continuous"] else "set"
    manifest = build_manifest(
        series,
        written_at=now.isoformat(),
        identity=identity,
        subsets=subsets,
        provenance={"built_at": now.isoformat(), "min_seam_overlap": MIN_SEAM_OVERLAP, "series": seam},
    )
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
