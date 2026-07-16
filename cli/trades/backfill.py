"""Orchestration for spec 00053 Task 4: heal the canonical trade stream.

Ties together the pieces built in Tasks 1-3: read canonical trade hours, detect id gaps and
duplicates (pure, no I/O), fetch the missing ids from Kraken's public REST, union them into the
existing hour, and mint the healed hour into the reconciled overlay. Never fabricates a trade: an
id REST will not serve stays absent from the minted hour and is counted as `trades_unrecoverable`.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from cli.archive.mint import mint_hour
from cli.archive.reader import canonical_segments
from cli.archive.reconcile import Block, union_trades  # Block is DEFINED there, re-exported by mint
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.logging import get_logger
from cli.trades.errors import TradeBackfillError
from cli.trades.gaps import detect
from cli.trades.rest import fetch_trades

logger = get_logger("trades.backfill")

_SETTLE = dt.timedelta(hours=2)  # the reconciler's rule: the in-flight hour is untouchable
_TOOL = "zcrypto archive backfill-trades"
_TOOL_VERSION = "00053"


@dataclass(frozen=True)
class BackfillResult:
    pairs: int
    gaps_found: int
    trades_recovered: int
    trades_unrecoverable: int
    duplicates_collapsed: int
    hours_minted: int
    errors: list[tuple[str, str]]


def _collapse_ranges(ids: list[int]) -> list[list[int]]:
    """Collapse a list of ids into contiguous `[lo, hi]` runs — bounded size vs. one entry per id."""
    if not ids:
        return []
    ordered = sorted(ids)
    ranges: list[list[int]] = []
    lo = hi = ordered[0]
    for i in ordered[1:]:
        if i == hi + 1:
            hi = i
        else:
            ranges.append([lo, hi])
            lo = hi = i
    ranges.append([lo, hi])
    return ranges


def backfill(
    primary_root: Path,
    reconciled_root: Path,
    *,
    pair: str | None = None,
    now: dt.datetime,
    detect_only: bool = False,
    fetch=fetch_trades,
) -> BackfillResult:
    """Heal the canonical trade stream to spec 00053's invariant: contiguous AND unique trade_id."""
    hours: dict[str, list[tuple[dt.datetime, Path]]] = defaultdict(list)
    for p, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        if pair is not None and p != pair:
            continue
        if hour + _SETTLE > now:  # settle rule: the in-flight hour is untouchable
            continue
        hours[p].append((hour, path))

    gaps_found = recovered = unrecoverable = dups = minted = 0
    errors: list[tuple[str, str]] = []

    for p, segs in sorted(hours.items()):
        frames = {h: pl.read_parquet(path) for h, path in sorted(segs)}
        if not frames:
            continue
        det = detect(pl.concat(list(frames.values())))
        gaps_found += len(det.gaps)
        dups += det.rows - det.unique
        if detect_only:
            continue

        got = pl.DataFrame([], schema=TRADE_SCHEMA)
        for g in det.gaps:
            try:
                page = fetch(p, since=g.ts_lo, until=g.ts_hi)
            except TradeBackfillError as exc:  # isolate: one bad gap must not end the sweep
                logger.warning("trade backfill fetch failed pair=%s gap=%s..%s: %s", p, g.after_id, g.before_id, exc)
                errors.append((p, str(exc)))
                continue
            inside = page.filter((pl.col("trade_id") > g.after_id) & (pl.col("trade_id") < g.before_id))
            recovered += inside.height
            unrecoverable += g.missing - inside.height  # never fabricated: absent ids stay absent
            got = pl.concat([got, inside]) if got.height else inside

        # Affected hours = hours containing a recovered row UNION hours containing a duplicate id.
        touched = {h for h, f in frames.items() if f.height != f.unique(subset=["trade_id"]).height}
        for h in frames:
            if got.height and got.filter((pl.col("ts") >= h) & (pl.col("ts") < h + dt.timedelta(hours=1))).height:
                touched.add(h)

        for h in sorted(touched):
            rest_rows = (
                got.filter((pl.col("ts") >= h) & (pl.col("ts") < h + dt.timedelta(hours=1)))
                if got.height
                else pl.DataFrame([], schema=TRADE_SCHEMA)
            )
            union = union_trades(frames[h], rest_rows)
            ranges = _collapse_ranges(rest_rows["trade_id"].to_list())
            mint_hour(
                reconciled_root,
                p,
                "trades",
                h,
                [Block(source="canonical+kraken-rest", frame=union.frame, from_ts=None, to_ts=None)],
                gaps_healed=[],
                residual_gaps=[],
                schema=TRADE_SCHEMA,
                tool_version=_TOOL_VERSION,
                tool=_TOOL,
                extra_provenance={"recovered_id_ranges": ranges, "deduped_rows": union.deduped_rows},
                replace=True,
            )
            minted += 1

    logger.info(
        "trade backfill complete pairs=%d gaps=%d recovered=%d unrecoverable=%d duplicates=%d hours_minted=%d errors=%d",
        len(hours),
        gaps_found,
        recovered,
        unrecoverable,
        dups,
        minted,
        len(errors),
    )
    return BackfillResult(len(hours), gaps_found, recovered, unrecoverable, dups, minted, errors)
