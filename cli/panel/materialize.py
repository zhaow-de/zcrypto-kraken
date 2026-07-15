"""Hour materializer + watermarked sweep for the 1s L2 panel (spec 00052 D3/D4/D5/D6).

Walks one canonical book hour (`canonical_segments`, reconciled-first) through a fresh `OrderBook`,
sampling `cli.panel.primitives.sample_row` at each second boundary, then publishes the wide panel
frame as an hourly zstd Parquet final (the `cli/archive/mint.py` atomic-write pattern: tmp in the
destination dir -> `os.replace` -> fsync, sidecar minted from the tmp bytes before the publishing
rename). `materialize()` sweeps the canonical archive, per-pair watermarked at the newest existing
panel hour, isolating one bad hour into `MaterializeResult.errors` rather than aborting the sweep --
the same isolation contract as `cli.archive.replay.verify_replay`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.archive.replay import regroup_messages
from cli.archive.settle import FINAL_NAME
from cli.capture.book import OrderBook
from cli.capture.segment_writer import _replace_durably
from cli.logging import get_logger
from cli.panel.errors import PanelError
from cli.panel.primitives import NOTIONALS_EUR, PANEL_SCHEMA, sample_row

logger = get_logger("panel.materialize")

SECONDS_PER_HOUR = 3600

# Cumulative-depth price levels the panel reports (mirrors `primitives._DEPTH_LEVELS` -- kept as its
# own constant here since that name is module-private and this is generation metadata, not math).
K_LEVELS: tuple[int, int, int] = (1, 5, 10)

SCHEMA_VERSION = 1


def _pair_dir(root: Path, pair: str) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / "panel-1s"


def materialize_hour(path: Path, pair: str, hour: datetime, *, depth: int = 100) -> pl.DataFrame:
    """Replay one canonical hour into the 1s-grid wide primitive panel.

    Samples at each second boundary `hour+0s .. hour+3599s`: the row at boundary T reflects the book
    state after applying every message with `ts <= T`, and `updates` counts the messages applied in
    that second's own window (T-1, T] -- for the first boundary, every message with `ts <= hour+0s`
    (there are none earlier in a well-formed hour, so this is the same rule, not a special case).
    `sample_row` returning None (either side empty) drops that second from the grid entirely -- an
    honest gap, never filled or extrapolated. This is also what enforces "no rows before the
    snapshot lands" (spec 00052 D3/Risks) with no special-casing: before the snapshot is ingested
    both sides are empty, so every pre-snapshot boundary is already skipped by the general rule.

    Raises `PanelError` if the hour's first message is not `type == "snapshot"` -- the canonical
    archive's snapshot-anchored invariant (spec 00051 OPS-3). This module refuses to guess at a
    malformed hour; `verify_replay` owns diagnosing it.


    The grid is [hour+0s, hour+3599s]: the hour's final fractional second (messages after
    :59:59.0) has no boundary in this file and is deliberately unsampled -- the next hour
    re-anchors on its own snapshot, so state self-heals; magnitude ~1s/3600s (review M1).
    """
    frame = pl.read_parquet(path)
    messages = regroup_messages(frame)
    if not messages or messages[0]["type"] != "snapshot":
        raise PanelError(f"{pair} hour {hour.isoformat()} does not open with a snapshot: {path}")

    book = OrderBook(pair, depth)
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
            updates += 1
            msg_idx += 1
        row = sample_row(book.bids, book.asks, updates=updates)
        updates = 0
        if row is not None:
            row["ts"] = boundary
            rows.append(row)
    return pl.DataFrame(rows, schema=PANEL_SCHEMA)


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


def panel_watermark(panel_root: Path, pair: str) -> datetime | None:
    """The newest hour with an existing panel final for `pair`, or None if it holds none yet."""
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
    """One sweep's verdict: what got written, what the watermark already covered, and which hours
    failed (isolated, never raised -- see `materialize`)."""

    hours_written: int
    hours_skipped: int
    rows: int
    errors: list[tuple[str, datetime, str]]


def materialize(
    primary_root: Path,
    reconciled_root: Path | None,
    panel_root: Path,
    *,
    pair: str | None = None,
    since: datetime | None = None,
    depth: int = 100,
) -> MaterializeResult:
    """Sweep canonical book hours (reconciled-first, spec 00052 D3) into the panel, per-pair
    watermarked (D6): only hours strictly newer than `panel_watermark` are materialized, and hours
    at-or-below it are counted `hours_skipped`. A per-hour failure -- a corrupt segment, a malformed
    (non-snapshot-anchored) hour -- is isolated into `errors` and the sweep continues, mirroring
    `cli.archive.replay.verify_replay`'s isolation contract; one bad hour must never abort the rest.
    """
    hours_written = 0
    hours_skipped = 0
    rows = 0
    errors: list[tuple[str, datetime, str]] = []
    watermarks: dict[str, datetime | None] = {}

    for seg_pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="book"):
        if pair is not None and seg_pair != pair:
            continue
        if since is not None and hour < since:
            continue
        if seg_pair not in watermarks:
            watermarks[seg_pair] = panel_watermark(panel_root, seg_pair)
        watermark = watermarks[seg_pair]
        if watermark is not None and hour <= watermark:
            hours_skipped += 1
            continue
        try:
            hour_frame = materialize_hour(path, seg_pair, hour, depth=depth)
            write_hour(panel_root, seg_pair, hour, hour_frame)
        except Exception as exc:  # noqa: BLE001 -- one bad hour must not abort the sweep
            logger.exception("panel materialize failed pair=%s hour=%s", seg_pair, hour)
            errors.append((seg_pair, hour, f"{type(exc).__name__}: {exc}"))
            continue
        hours_written += 1
        rows += hour_frame.height
        watermarks[seg_pair] = hour  # advance in-memory so later hours in this same sweep see it

    return MaterializeResult(hours_written, hours_skipped, rows, errors)


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
