"""Hour materializer + watermarked sweep for the 1s L2 panel (spec 00052 D3/D4/D5/D6).

Walks one canonical book hour (`canonical_segments`, reconciled-first) through an `OrderBook`,
sampling `cli.panel.primitives.sample_row` at each second boundary, then publishes the wide panel
frame as an hourly zstd Parquet final (the `cli/archive/mint.py` atomic-write pattern: tmp in the
destination dir -> `os.replace` -> fsync, sidecar minted from the tmp bytes before the publishing
rename). Per spec 00052 D3 (corrected 2026-07-15): Kraken snapshots arrive on subscribe, not once
per capture hour, so ~96% of real hours open with plain updates -- `materialize_hour` therefore
threads `OrderBook` state across hours (carry-in/carry-out) rather than rebuilding fresh every hour,
and `write_state`/`load_state` persist the end-of-hour book as a `<HH>.state.json` sidecar so a
sweep can resume in O(1) from the watermark hour's state. `materialize()` sweeps the canonical
archive, per-pair watermarked at the newest existing panel hour, isolating one bad hour into
`MaterializeResult.errors` rather than aborting the sweep -- the same isolation contract as
`cli.archive.replay.verify_replay` -- while an hour that cannot anchor to prior state (no snapshot,
no carried book) is isolated separately into `MaterializeResult.hours_unanchored`, an honest gap
rather than a failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.archive.replay import regroup_messages
from cli.archive.settle import FINAL_NAME
from cli.capture.book import OrderBook
from cli.capture.segment_writer import _replace_durably
from cli.logging import get_logger
from cli.panel.errors import PanelError
from cli.panel.primitives import NOTIONALS_EUR, PANEL_QUOTE, PANEL_SCHEMA, sample_row

logger = get_logger("panel.materialize")

SECONDS_PER_HOUR = 3600

# T0066 / spec 00052 D6 correction: an hour being "settled" (its canonical final is committed +
# hash-verified) is NOT the same as "heal-complete" (the reconciled-first view will not change). The
# reconciler mints healed book hours at H+2h..H+6h from the hour start; consuming an hour before then
# lets the panel derive from the un-healed primary, and because the panel watermark is monotone with
# no re-mint invalidation, that stale hour becomes permanent. So `materialize` waits until
# `now >= hour_start + PANEL_SETTLE` before taking an hour -- H+6h (the reconciler's max mint) plus a
# 1h pull/visibility buffer. The cost is ~7h of panel freshness, which no current consumer needs.
PANEL_SETTLE = timedelta(hours=7)

# Cumulative-depth price levels the panel reports (mirrors `primitives._DEPTH_LEVELS` -- kept as its
# own constant here since that name is module-private and this is generation metadata, not math).
K_LEVELS: tuple[int, int, int] = (1, 5, 10)

SCHEMA_VERSION = 1


def _pair_dir(root: Path, pair: str) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / "panel-1s"


def materialize_hour(
    path: Path,
    pair: str,
    hour: datetime,
    *,
    depth: int = 100,
    book: OrderBook | None = None,
    last_msg_ts: datetime | None = None,
) -> tuple[pl.DataFrame, OrderBook, datetime | None]:
    """Replay one canonical hour into the 1s-grid wide primitive panel, threading `OrderBook` state
    across hours (spec 00052 D3 correction).

    An hour opening with `type == "snapshot"` always (re)builds a FRESH `OrderBook` -- `book` (any
    carried-in state) is ignored, since the snapshot is itself a fresh anchor. An hour opening with
    an update instead continues from the carried `book`, sampling from second 0 with that state; if
    no `book` was carried (`book is None`), the hour cannot anchor and this raises `PanelError` --
    the sweep (`materialize`) categorizes that as `hours_unanchored`, an honest gap, not an error.
    Returns `(frame, book, last_msg_ts)`: the sampled frame, the end-of-hour book state, and the
    time of the last message applied -- all three for the caller to persist (`write_state`) and carry
    into the next hour. `last_msg_ts` is threaded rather than recomputed per hour because a blackout
    can span an hour boundary (the 2026-07-13 event began at 06:59:59.69), and a within-hour counter
    would silently restart at exactly the moment the number matters most (T0104).

    Samples at each second boundary `hour+0s .. hour+3599s`: the row at boundary T reflects the book
    state after applying every message with `ts <= T`, and `updates` counts the messages applied in
    that second's own window (T-1, T] -- for the first boundary, every message with `ts <= hour+0s`
    (there are none earlier in a well-formed hour, so this is the same rule, not a special case).
    `sample_row` returning None (either side empty) drops that second from the grid entirely -- an
    honest gap, never filled or extrapolated. This is also what enforces "no rows before the
    snapshot lands" (spec 00052 D3/Risks) with no special-casing: before the snapshot is ingested
    both sides are empty, so every pre-snapshot boundary is already skipped by the general rule.

    The grid is [hour+0s, hour+3599s]: the hour's final fractional second (messages after
    :59:59.0) has no boundary in this file and is deliberately unsampled -- the next hour
    re-anchors on its own snapshot or the carried state (which includes this hour's final fractional-second messages via the trailing drain), so nothing is lost; magnitude
    ~1s/3600s (review M1).
    """
    frame = pl.read_parquet(path)
    messages = regroup_messages(frame)
    if messages and messages[0]["type"] == "snapshot":
        book = OrderBook(pair, depth)  # a snapshot always resets state, carried-in or not
    elif book is None:
        raise PanelError(f"{pair} hour {hour.isoformat()} opens with an update and carries no anchoring book state: {path}")
    # else: continue on the carried `book` -- this hour's rows sample from second 0 with that state.

    rows: list[dict] = []
    msg_idx = 0
    updates = 0
    for second in range(SECONDS_PER_HOUR):
        boundary = hour + timedelta(seconds=second)
        while msg_idx < len(messages) and messages[msg_idx]["ts"] <= boundary:
            message = messages[msg_idx]
            if message["type"] == "snapshot":
                book.ingest_snapshot(message)
            else:
                book.ingest_update(message)
            last_msg_ts = message["ts"]
            updates += 1
            msg_idx += 1
        stale = (boundary - last_msg_ts).total_seconds() if last_msg_ts is not None else None
        row = sample_row(book.bids, book.asks, updates=updates, stale_seconds=stale)
        updates = 0
        if row is not None:
            row["ts"] = boundary
            rows.append(row)
    # Review C1 (critical): messages in the hour's final fractional second (ts > :59:59.0, still in
    # THIS hour's file) have no sampling boundary above -- but they MUST reach the carried-out book,
    # or every update-opening successor starts stale and the panel silently drifts from reality at
    # each boundary. Applied, never sampled, never counted into `updates` -- the grid stays [0,3599].
    while msg_idx < len(messages):
        message = messages[msg_idx]
        if message["type"] == "snapshot":
            book.ingest_snapshot(message)
        else:
            book.ingest_update(message)
        last_msg_ts = message["ts"]  # these reach the carried book, so they must reach its clock too
        msg_idx += 1
    return pl.DataFrame(rows, schema=PANEL_SCHEMA), book, last_msg_ts


def write_hour(panel_root: Path, pair: str, hour: datetime, frame: pl.DataFrame) -> Path:
    """Publish `frame` as `pair`'s hour, atomically, with a `.sha256` sidecar.

    Mirrors `cli/archive/mint.py`'s durability moves exactly: the sidecar is minted from the tmp
    file's bytes -- which ARE the final's bytes -- and written BEFORE the atomic rename that
    publishes it, so a kill anywhere in here leaves no final at all and the next run simply
    overwrites the torn tmp. On an OVERWRITE (a regeneration -- the watermarked sweep never
    overwrites) there is a brief new-sidecar/old-final window where verify_manifest fails; the
    panel is regenerable, so a regen re-run heals it (review M3).
    """
    d = _pair_dir(panel_root, pair) / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
    d.mkdir(parents=True, exist_ok=True)
    final = d / f"{hour:%H}.parquet"
    # PID-suffixed tmps (review I1): mint.py's fixed tmp names are safe only single-process; here a
    # timer run and a manual CLI run may materialize the same newest hour concurrently, and a SHARED
    # tmp lets writer A rename what writer B is mid-truncating -- publishing a torn final that the
    # watermark then skips forever. Unique tmps restore last-writer-wins of complete, identical bytes.
    tmp = d / f"{hour:%H}.parquet.{os.getpid()}.tmp"
    frame.write_parquet(tmp, compression="zstd")

    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    manifest_tmp = d / f"{hour:%H}.parquet.sha256.{os.getpid()}.tmp"
    manifest_tmp.write_text(f"{digest}  {final.name}\n")
    _replace_durably(manifest_tmp, final.with_name(final.name + ".sha256"))

    _replace_durably(tmp, final)  # publish LAST
    return final


def _state_path(panel_root: Path, pair: str, hour: datetime) -> Path:
    d = _pair_dir(panel_root, pair) / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
    return d / f"{hour:%H}.state.json"


def write_state(panel_root: Path, pair: str, hour: datetime, book: OrderBook, *, last_msg_ts: datetime | None = None) -> Path:
    """Persist `book`'s end-of-hour state as `<HH>.state.json`, next to the hour's parquet, for O(1)
    watermark resume (spec 00052 D3). `str(Decimal)` keys/values round-trip exactly -- a bare JSON
    float would silently reintroduce the precision loss `OrderBook._prune` was written to avoid
    (T0008). Atomic like `write_hour`: a PID-suffixed tmp + `_replace_durably`.
    """
    path = _state_path(panel_root, pair, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "bids": {str(price): str(qty) for price, qty in book.bids.items()},
        "asks": {str(price): str(qty) for price, qty in book.asks.items()},
        # T0104: the staleness clock crosses hours with the book, so it is persisted with it. A
        # sidecar written before this key still loads -- `load_state` returns None for the time,
        # which the panel emits as a null `stale_seconds` rather than a fabricated 0.0.
        "last_msg_ts": last_msg_ts.isoformat() if last_msg_ts is not None else None,
    }
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state))
    _replace_durably(tmp, path)
    return path


def load_state(panel_root: Path, pair: str, hour: datetime, *, depth: int = 100) -> tuple[OrderBook | None, datetime | None]:
    """Load the book state `write_state` persisted for `hour` as `(book, last_msg_ts)`, or
    `(None, None)` if the sidecar is missing or corrupt -- never raises: an unreadable state file
    simply means the resuming hour cannot anchor (the sweep then counts it `hours_unanchored`, an
    honest gap, not a crash). A sidecar predating T0104's `last_msg_ts` key yields a None time."""
    path = _state_path(panel_root, pair, hour)
    try:
        data = json.loads(path.read_text())
        book = OrderBook(pair, depth)
        book.bids = {Decimal(price): Decimal(qty) for price, qty in data["bids"].items()}
        book.asks = {Decimal(price): Decimal(qty) for price, qty in data["asks"].items()}
        raw = data.get("last_msg_ts")
        return book, (datetime.fromisoformat(raw) if raw else None)
    except Exception:  # noqa: BLE001 -- missing/corrupt state must never crash the sweep
        return None, None


def panel_watermark(panel_root: Path, pair: str) -> datetime | None:
    """The newest hour with an existing panel final for `pair`, or None if it holds none yet.

    Globs `*.parquet` and strictly matches `FINAL_NAME` -- the `<HH>.state.json` sidecar never
    matches either, so it cannot confuse the watermark.
    """
    hours = []
    for p in _pair_dir(panel_root, pair).glob("*/*/*/*.parquet"):
        match = FINAL_NAME.match(p.name)
        if match is None:
            continue
        parts = p.parts
        try:
            hours.append(datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(match.group(1)), tzinfo=UTC))
        except ValueError:  # a hand-made directory that is not a date -- not ours, ignore it
            continue
    return max(hours) if hours else None


@dataclass(frozen=True)
class MaterializeResult:
    """One sweep's verdict: what got written, what the watermark already covered, which hours were
    deferred as not-yet-heal-complete (spec 00052 D6 / T0066), which couldn't anchor to prior state
    (honest gaps, spec 00052 D3), and which failed outright (isolated, never raised -- see
    `materialize`)."""

    hours_written: int
    hours_skipped: int
    hours_unanchored: int
    hours_unsettled: int
    rows: int
    errors: list[tuple[str, datetime, str]]
    #: pairs present in the archive but outside the panel's EUR-quoted scope (T0092). Reported so
    #: an out-of-scope stream is visible rather than an absence that looks like success. Defaulted
    #: and last so it stays after the non-default `errors` field.
    pairs_out_of_scope: int = 0


def materialize(
    primary_root: Path,
    reconciled_root: Path | None,
    panel_root: Path,
    *,
    pair: str | None = None,
    since: datetime | None = None,
    depth: int = 100,
    settle: timedelta = PANEL_SETTLE,
    now: datetime | None = None,
) -> MaterializeResult:
    """Sweep canonical book hours (reconciled-first, spec 00052 D3) into the panel, per-pair
    watermarked (D6): only hours strictly newer than `panel_watermark` are materialized, and hours
    at-or-below it are counted `hours_skipped`.

    Settle gate (spec 00052 D6 correction / T0066): an hour is only taken once `now - hour >= settle`
    (`PANEL_SETTLE`, 7h) -- long enough for the reconciler's H+6h max mint to have healed it, so the
    reconciled-first read is heal-complete. A newer, not-yet-settled hour is counted `hours_unsettled`
    and left for a future sweep; because the watermark never advances onto it, the un-healed primary is
    never permanently captured. `now` is injectable for testing (defaults to the wall clock).

    Threads `OrderBook` state across hours, per pair (D3 correction): a fresh sweep resumes a pair's
    book from `load_state` at its watermark hour; within the sweep, a hour that is NOT exactly the
    previous processed hour + 1h (a canonical gap -- an hour missing from the archive) discards any
    carried book, since it cannot be trusted to still describe the current state. An hour that then
    fails to anchor (`materialize_hour` raising `PanelError` -- an update-opening hour with no
    carried book) is isolated into `hours_unanchored`, not `errors`: an honest gap that self-heals at
    the next snapshot, logged once per contiguous run rather than per hour. A per-hour failure of any
    other kind -- a corrupt segment, a structural throw -- is isolated into `errors` and the sweep
    continues, mirroring `cli.archive.replay.verify_replay`'s isolation contract; one bad hour must
    never abort the rest.
    """
    now = now if now is not None else datetime.now(UTC)
    hours_written = 0
    hours_skipped = 0
    hours_unanchored = 0
    hours_unsettled = 0
    rows = 0
    errors: list[tuple[str, datetime, str]] = []
    watermarks: dict[str, datetime | None] = {}
    prev_hour: dict[str, datetime | None] = {}
    books: dict[str, OrderBook | None] = {}
    last_seen: dict[str, datetime | None] = {}  # T0104: the staleness clock, carried with the book
    unanchored_run: dict[str, bool] = {}  # suppresses repeat WARNING logging within one bad run

    skipped_pairs: set[str] = set()  # logged once per pair, not per hour

    for seg_pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="book"):
        if pair is not None and seg_pair != pair:
            continue
        if seg_pair.split("/")[-1] != PANEL_QUOTE:
            if seg_pair not in skipped_pairs:
                skipped_pairs.add(seg_pair)
                logger.info(
                    "panel skipping non-%s-quoted pair=%s (the notional ladder is quote-denominated)", PANEL_QUOTE, seg_pair
                )
            continue
        if since is not None and hour < since:
            continue
        if seg_pair not in watermarks:
            watermark = panel_watermark(panel_root, seg_pair)
            watermarks[seg_pair] = watermark
            prev_hour[seg_pair] = watermark
            if watermark is not None:
                books[seg_pair], last_seen[seg_pair] = load_state(panel_root, seg_pair, watermark, depth=depth)
            else:
                books[seg_pair], last_seen[seg_pair] = None, None
            unanchored_run[seg_pair] = False
        watermark = watermarks[seg_pair]
        if watermark is not None and hour <= watermark:
            hours_skipped += 1
            continue

        # Settle gate (T0066): defer an hour that is not yet heal-complete. Newer hours are also
        # unsettled, so the pair simply stops advancing here; the watermark holds and a later sweep
        # takes this hour once the reconciler has had until H+6h to heal it. Left BEFORE the gap/anchor
        # bookkeeping so a deferred hour touches none of it (it is re-processed cleanly next sweep).
        if now - hour < settle:
            hours_unsettled += 1
            continue

        if prev_hour[seg_pair] is None or hour != prev_hour[seg_pair] + timedelta(hours=1):
            books[seg_pair] = None  # a canonical gap -- any carried book can no longer be trusted
            last_seen[seg_pair] = None  # ...and its staleness clock is meaningless without it

        try:
            hour_frame, book_out, last_out = materialize_hour(
                path, seg_pair, hour, depth=depth, book=books[seg_pair], last_msg_ts=last_seen[seg_pair]
            )
        except PanelError as exc:
            if not unanchored_run[seg_pair]:
                logger.warning("panel materialize: pair=%s hour=%s unanchored: %s", seg_pair, hour.isoformat(), exc)
                unanchored_run[seg_pair] = True
            hours_unanchored += 1
            books[seg_pair] = None
            last_seen[seg_pair] = None
            prev_hour[seg_pair] = hour
            continue
        except Exception as exc:  # noqa: BLE001 -- one bad hour must not abort the sweep
            logger.exception("panel materialize failed pair=%s hour=%s", seg_pair, hour)
            errors.append((seg_pair, hour, f"{type(exc).__name__}: {exc}"))
            books[seg_pair] = None
            last_seen[seg_pair] = None
            prev_hour[seg_pair] = hour
            unanchored_run[seg_pair] = False
            continue

        # State BEFORE parquet (review M1): the watermark counts only the parquet, so a crash
        # between the writes leaves the parquet unpublished (next run re-materializes, overwriting
        # the orphan state) rather than a watermark hour whose missing sidecar would spuriously
        # unanchor its successor.
        write_state(panel_root, seg_pair, hour, book_out, last_msg_ts=last_out)
        write_hour(panel_root, seg_pair, hour, hour_frame)
        hours_written += 1
        rows += hour_frame.height
        watermarks[seg_pair] = hour  # advance in-memory so later hours in this same sweep see it
        prev_hour[seg_pair] = hour
        books[seg_pair] = book_out
        last_seen[seg_pair] = last_out
        unanchored_run[seg_pair] = False

    return MaterializeResult(hours_written, hours_skipped, hours_unanchored, hours_unsettled, rows, errors, len(skipped_pairs))


def _code_ref() -> str:
    """`git rev-parse --short HEAD` at write time -- "unknown" if this is not a git checkout (e.g.
    the deploy image, which does not ship the `.git` dir)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).parent,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001 -- metadata only; never blocks a materialize run
        return "unknown"


def write_meta(panel_root: Path) -> Path:
    """Write (or overwrite) the panel's generation manifest (spec 00052 D5): schema_version, grid,
    the notional ladder, the K-levels, and the producing code ref. This is the raw writer only --
    the "write if absent, refuse on a generation mismatch" policy belongs to the CLI (Task 3)."""
    panel_root.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "grid": "1s",
        "notionals_eur": list(NOTIONALS_EUR),
        "k_levels": list(K_LEVELS),
        "code_ref": _code_ref(),
    }
    path = panel_root / "panel-meta.json"
    # Atomic like everything else in this module (review M5): a kill mid-write must not leave a
    # truncated meta for the CLI's generation check to choke on.
    tmp = path.with_name(f"panel-meta.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(meta, indent=1) + "\n")
    _replace_durably(tmp, path)
    return path
