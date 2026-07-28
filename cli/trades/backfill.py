"""Orchestration for spec 00053 Task 4: heal the canonical trade stream.

Ties together the pieces built in Tasks 1-3: read canonical trade hours, detect id gaps and
duplicates (pure, no I/O), fetch the missing ids from Kraken's public REST, union them into the
existing hour (minting a fresh hour from REST alone when none existed), and mint the healed hour
into the reconciled overlay. Never fabricates a trade: an id REST will not serve stays absent from
the minted hour and is counted as `trades_unrecoverable`; a row REST serves but whose hour hasn't
settled yet is counted as `trades_deferred`, never minted and never silently dropped. The healing
counters (`trades_recovered`, `duplicates_collapsed`, ...) are derived from what actually landed
(D9): after minting, the pair's canonical view is re-read from disk and re-checked against the
invariant. `trades_missing` / `duplicate_rows_found` are a separate pair of counters answering a
different question -- what the detector FOUND, independent of what was healed -- and are populated
in both `--mint` and `--detect-only` modes, since they describe the archive as found, not as healed.
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
from cli.capture.errors import CaptureError
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
    trades_missing: int
    duplicate_rows_found: int
    trades_recovered: int
    trades_unrecoverable: int
    trades_deferred: int
    trades_fetch_failed: int  # ids in gaps whose fetch itself raised (T0078) -- totalled, never dropped
    trades_mint_failed: int  # rows REST served for an hour whose mint raised (T0087) -- retryable, never subtracted
    hours_repaired_after_loss: int  # settled hours with a book final but NO trades final that this run minted (T0043)
    duplicates_collapsed: int
    duplicates_cross_hour: int
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


def _floor_hour(ts: dt.datetime) -> dt.datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


# A book final's mere EXISTENCE proves only that at least one book event landed somewhere in the
# hour -- which a capture restart at :45 produces too, and our own image converges restart capture.
# A witness for "the stream was connected while the trades file should have been written" therefore
# has to SPAN the hour. At depth 100 the book ticks continuously, so 60 s of slack at each edge
# tolerates ordinary quiet while excluding a restart or a mid-hour death that cost minutes.
_BOOK_WITNESS_SLACK = dt.timedelta(seconds=60)


def _book_witnesses_hour(path: Path, hour: dt.datetime) -> bool:
    """True iff `path`'s book final spans `hour` end to end (see `_BOOK_WITNESS_SLACK`).

    False on an unreadable or empty final: the question is whether we can PROVE the stream was
    connected, and an answer we cannot read is not a proof. Silence is the safe direction here --
    this witness only ever promotes an absence into a reported loss event.
    """
    try:
        ts = pl.read_parquet(path, columns=["ts"])["ts"]
    except Exception:  # noqa: BLE001 -- an unreadable witness witnesses nothing
        return False
    if ts.len() == 0:
        return False
    return ts.min() <= hour + _BOOK_WITNESS_SLACK and ts.max() >= hour + dt.timedelta(hours=1) - _BOOK_WITNESS_SLACK


def _read_pair_settled(primary_root: Path, reconciled_root: Path, pair: str, now: dt.datetime) -> dict[dt.datetime, pl.DataFrame]:
    """Re-read one pair's settled canonical hours from disk — the D9 post-mint invariant re-check
    needs the ACTUAL published state, never the in-memory frames the mint calls were built from."""
    out = {}
    for p2, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        if p2 != pair or hour + _SETTLE > now:
            continue
        out[hour] = pl.read_parquet(path)
    return out


def backfill(
    primary_root: Path,
    reconciled_root: Path,
    *,
    pair: str | None = None,
    now: dt.datetime,
    detect_only: bool = False,
    fetch=fetch_trades,
) -> BackfillResult:
    """Heal the canonical trade stream to spec 00053's invariant: contiguous AND unique trade_id.

    D9: the manifest is not the check. After minting a pair's touched hours, the pair's canonical
    view is re-read from disk and `detect` re-run against it; any residual gap or duplicate NOT
    explained by `trades_unrecoverable` / `trades_deferred` / `duplicates_cross_hour` is a finding —
    logged loudly and recorded in `errors` — rather than a silently self-reported success.
    """
    hours: dict[str, list[tuple[dt.datetime, Path]]] = defaultdict(list)
    for p, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        if pair is not None and p != pair:
            continue
        if hour + _SETTLE > now:  # settle rule: the in-flight hour is untouchable
            continue
        hours[p].append((hour, path))

    gaps_found = recovered = unrecoverable = deferred = fetch_failed = mint_failed = 0
    duplicates_collapsed = duplicates_cross_hour = minted = repaired_after_loss = 0
    trades_missing = duplicate_rows_found = 0
    errors: list[tuple[str, str]] = []

    # The book sibling of a trades hour: the witness that the stream was CONNECTED while that hour's
    # trades file should have been written. `is_total_loss` cannot tell "nobody traded" (ordinary for
    # a quiet pair -- an hour with no events writes no file at all) from a genuinely lost file, so it
    # calls both "nobody traded", and this sweep then repairs the second one SILENTLY.
    #
    # Skipped in detect-only, which never reaches the mint loop that reads it, and narrowed to the
    # requested pair. The narrowing bounds what is RETAINED, not the scan: `canonical_segments` takes
    # no pair argument and still globs `*/*/book/*/*/*/*.parquet` across the whole tree, and book is
    # the dominant volume of the archive -- so if this ever becomes the cost, the glob is where to
    # look, not this filter.
    book_finals: dict[str, dict[dt.datetime, Path]] = {}
    if not detect_only:
        for p2, hour, path in canonical_segments(primary_root, reconciled_root, kind="book"):
            if pair is None or p2 == pair:
                book_finals.setdefault(p2, {})[hour] = path

    for p, segs in sorted(hours.items()):
        try:
            frames = {h: pl.read_parquet(path) for h, path in sorted(segs)}
        except Exception as exc:  # noqa: BLE001 -- any unreadable segment is an integrity fact
            logger.warning("trade backfill read failed pair=%s: %s", p, exc)
            errors.append((p, str(exc)))
            continue
        if not frames:
            continue
        det = detect(pl.concat(list(frames.values())))
        gaps_found += len(det.gaps)
        # Found, independent of healed: what the detector found in THIS pair, populated in both
        # --mint and --detect-only, since it describes the archive as found, never as fixed.
        trades_missing += det.missing

        # Duplicates: split the pair-span total between what a per-hour mint CAN collapse (a
        # duplicate id repeated inside one hour's own frame) and what it structurally cannot (the
        # same id split across two hour files, the T0026 reconnect-overwrite signature) — the
        # latter is a residual finding, never a completed collapse.
        total_dup_rows = det.rows - det.unique
        duplicate_rows_found += total_dup_rows
        intra_dup_rows = sum(f.height - f.unique(subset=["trade_id"]).height for f in frames.values())
        cross_hour_dup_rows = total_dup_rows - intra_dup_rows
        duplicates_cross_hour += cross_hour_dup_rows
        if cross_hour_dup_rows:
            logger.warning(
                "trade backfill pair=%s: %d duplicate row(s) span an hour boundary; union_trades "
                "mints per-hour and cannot collapse them — residual finding, not a collapse",
                p,
                cross_hour_dup_rows,
            )

        if detect_only:
            continue

        got = pl.DataFrame([], schema=TRADE_SCHEMA)
        pair_unrecoverable = 0
        pair_fetch_error_missing = 0  # ids in a gap whose fetch itself raised -- already an error
        for g in det.gaps:
            try:
                page = fetch(p, since=g.ts_lo, until=g.ts_hi)
            except TradeBackfillError as exc:  # isolate: one bad gap must not end the sweep
                logger.warning("trade backfill fetch failed pair=%s gap=%s..%s: %s", p, g.after_id, g.before_id, exc)
                errors.append((p, str(exc)))
                pair_fetch_error_missing += g.missing
                continue
            inside = page.filter((pl.col("trade_id") > g.after_id) & (pl.col("trade_id") < g.before_id))
            pair_unrecoverable += g.missing - inside.height  # never fabricated: absent ids stay absent
            got = pl.concat([got, inside]) if got.height else inside
        unrecoverable += pair_unrecoverable
        fetch_failed += pair_fetch_error_missing

        # Group recovered rows by hour, INCLUDING hours with no existing canonical file at all —
        # a wholly-missing hour is exactly a capture outage's primary scenario, and its rows must
        # not be counted as recovered and then thrown away for lack of a `frames[h]` entry.
        got_by_hour: dict[dt.datetime, pl.DataFrame] = {}
        if got.height:
            for h in sorted({_floor_hour(t) for t in got["ts"].to_list()}):
                got_by_hour[h] = got.filter((pl.col("ts") >= h) & (pl.col("ts") < h + dt.timedelta(hours=1)))

        # Affected hours = hours with an existing intra-hour duplicate UNION hours holding a
        # recovered row (existing or newly-minted from REST alone).
        existing_dup_hours = {h for h, f in frames.items() if f.height != f.unique(subset=["trade_id"]).height}
        touched = existing_dup_hours | set(got_by_hour)

        pair_recovered = pair_deferred = pair_dup_collapsed = pair_minted = 0
        pair_mint_failed = pair_repaired_after_loss = 0
        pair_repaired_hours: list[dt.datetime] = []
        for h in sorted(touched):
            rest_rows = got_by_hour.get(h, pl.DataFrame([], schema=TRADE_SCHEMA))
            if h + _SETTLE > now:
                # Fetched and inside the gap, but the hour hasn't settled yet: never mint (the
                # settle rule stays) and never silently drop — a later run lands it once it settles.
                pair_deferred += rest_rows.height
                continue
            existing = frames.get(h, pl.DataFrame([], schema=TRADE_SCHEMA))  # empty: mint fresh from REST alone
            union = union_trades(existing, rest_rows)
            ranges = _collapse_ranges(rest_rows["trade_id"].to_list())
            try:
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
            except (CaptureError, OSError) as exc:  # isolate: one bad mint must not end the sweep
                logger.warning("trade backfill mint failed pair=%s hour=%s: %s", p, h.isoformat(), exc)
                errors.append((p, str(exc)))
                # The rows REST really served for this hour, which the mint then dropped. Reported --
                # never subtracted in D9 below. A fetched-but-unminted row is RETRYABLE (the next run
                # re-detects the gap and re-fetches it), so booking it as an explained absence would
                # make the strongest check in the sweep go quiet on exactly the failure it exists for.
                pair_mint_failed += union.added_from_secondary
                continue
            # Counted from the UNION result, not the fetch: only rows that actually landed count.
            pair_recovered += union.added_from_secondary
            pair_dup_collapsed += union.deduped_rows
            pair_minted += 1
            # No trades final for a settled hour, and a book final that SPANS it: the signature of a
            # real loss that was just repaired. Absent the witness it is an ordinary quiet hour or a
            # capture outage, and the counter stays 0 rather than inventing an incident. (Rows on the
            # REST tape are implied, not tested: `h not in frames` excludes `existing_dup_hours`, so
            # reaching here means `h` came from `got_by_hour`, whose buckets are non-empty.)
            witness = book_finals.get(p, {}).get(h)
            if h not in frames and witness is not None and _book_witnesses_hour(witness, h):
                pair_repaired_after_loss += 1
                pair_repaired_hours.append(h)

        recovered += pair_recovered
        deferred += pair_deferred
        duplicates_collapsed += pair_dup_collapsed
        minted += pair_minted
        mint_failed += pair_mint_failed
        repaired_after_loss += pair_repaired_after_loss
        if pair_repaired_after_loss:
            logger.warning(
                "trade backfill pair=%s: %d settled hour(s) had no trades final while a book final "
                "spanning the same hour did -- a lost trades segment, repaired from the REST tape; "
                "the archive is whole again but the loss event itself is real. hours=%s",
                p,
                pair_repaired_after_loss,
                ",".join(h.isoformat() for h in pair_repaired_hours),
            )

        # D9 — the manifest is not the check. Re-read this pair's settled canonical view off disk
        # and re-run detect(); every remaining gap/duplicate must be explained by a known bucket.
        resettled = _read_pair_settled(primary_root, reconciled_root, p, now)
        det2 = detect(pl.concat(list(resettled.values()))) if resettled else detect(pl.DataFrame([], schema=TRADE_SCHEMA))
        residual_missing = det2.missing - (pair_unrecoverable + pair_deferred + pair_fetch_error_missing)
        residual_dup_rows = (det2.rows - det2.unique) - cross_hour_dup_rows
        if residual_missing != 0 or residual_dup_rows != 0:
            msg = (
                # The full-attribution accounting invariant is D9 in the spec vocabulary.
                f"trade backfill accounting invariant violated for pair={p}: post-mint missing={det2.missing} "
                f"(unrecoverable={pair_unrecoverable} deferred={pair_deferred} "
                f"fetch_errors={pair_fetch_error_missing} unaccounted={residual_missing}), "
                f"post-mint duplicate_rows={det2.rows - det2.unique} "
                f"(cross_hour={cross_hour_dup_rows} unaccounted={residual_dup_rows})"
            )
            logger.error(msg)
            errors.append((p, msg))

    logger.info(
        "trade backfill complete pairs=%d gaps=%d trades_missing=%d duplicate_rows_found=%d "
        "recovered=%d unrecoverable=%d deferred=%d fetch_failed=%d mint_failed=%d "
        "duplicates_collapsed=%d duplicates_cross_hour=%d hours_minted=%d "
        "hours_repaired_after_loss=%d errors=%d",
        len(hours),
        gaps_found,
        trades_missing,
        duplicate_rows_found,
        recovered,
        unrecoverable,
        deferred,
        fetch_failed,
        mint_failed,
        duplicates_collapsed,
        duplicates_cross_hour,
        minted,
        repaired_after_loss,
        len(errors),
    )
    return BackfillResult(
        len(hours),
        gaps_found,
        trades_missing,
        duplicate_rows_found,
        recovered,
        unrecoverable,
        deferred,
        fetch_failed,
        mint_failed,
        repaired_after_loss,
        duplicates_collapsed,
        duplicates_cross_hour,
        minted,
        errors,
    )
