"""Write path for reconciled hours (spec 00050): `<HH>.parquet` on disk means committed, complete and
manifested — `SegmentWriter`'s invariant, verified by the same `verify_tree` — so the rename that publishes it
comes last, and by default (`replace=False`) an existing final is never overwritten: a provisionally residual
hour is healed by a NEW mint plus a superseding ledger record, never by mutating a published file."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.reconcile import Block, Gap
from cli.capture.errors import CaptureError

# Importing a module-private name is deliberate: the overlay must have the raw mirrors' durability
# semantics exactly, and a second implementation would be a second thing to get wrong.
from cli.capture.segment_writer import _replace_durably


def _hour_dir(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"


def already_minted(root: Path, pair: str, kind: str, hour: datetime) -> bool:
    """True iff this hour is already published in the overlay — and, by the invariant, complete."""
    return (_hour_dir(root, pair, kind, hour) / f"{hour:%H}.parquet").exists()


def ledger_append(root: Path, record: dict) -> None:
    """Append one JSON record to the overlay's append-only audit ledger."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / "reconcile-ledger.jsonl").open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def _check_hour(hour: datetime) -> datetime:
    """Return the hour's EXCLUSIVE end boundary, refusing anything that is not an exact UTC hour: the
    path is formatted straight from `hour`, so a stray 09:30 would publish half an hour under the
    09:00 file's name, which promises the whole of it."""
    if hour.tzinfo is None or hour != hour.replace(minute=0, second=0, microsecond=0):
        raise CaptureError(f"refusing to mint {hour!r}: not an exact UTC hour boundary")
    return hour + timedelta(hours=1)


def _check_gaps(gaps: list[Gap], *, hour: datetime, hour_end: datetime, label: str, primary_boundaries: bool) -> None:
    """Hold every gap to this hour's bounds — else the provenance record claims a hole in a neighbouring hour — and,
    for a healed gap, to `Gap`'s ownership contract. Only a residual gap may pass `primary_boundaries=False`: its
    interior edges are spliced messages, hence boundaries owning no primary message, and it drives no row filter —
    whereas relaxing it for a healed gap publishes `splice_book`'s primary rows out of block order."""
    for gap in gaps:
        if not (hour <= gap.start <= hour_end and hour <= gap.end <= hour_end):
            raise CaptureError(f"{label} {gap.start.isoformat()}->{gap.end.isoformat()} lies outside the {hour:%H}:00 hour")
        if not primary_boundaries:
            continue
        if not gap.start_is_primary_message and gap.start != hour:
            raise CaptureError(
                f"{label} starts at {gap.start.isoformat()}, which owns no primary message and is not "
                f"the hour boundary {hour.isoformat()}"
            )
        if not gap.end_is_primary_message and gap.end != hour_end:
            raise CaptureError(
                f"{label} ends at {gap.end.isoformat()}, which owns no primary message and is not the "
                f"exclusive hour boundary {hour_end.isoformat()} — `hour_end` must be the next hour, "
                f"not the last microsecond of this one"
            )


def mint_hour(
    root: Path,
    pair: str,
    kind: str,
    hour: datetime,
    blocks: list[Block],
    *,
    gaps_healed: list[Gap],
    residual_gaps: list[Gap],
    schema: dict,
    tool_version: str,
    tool: str = "zcrypto archive reconcile",
    extra_provenance: dict | None = None,
    replace: bool = False,
) -> Path:
    """Publish `blocks` as this hour's reconciled final, atomically, with its sidecar and provenance; return its path.
    `replace=True` overwrites an already-minted hour, and the caller then owns the guarantee that
    `blocks` is a superset of what it replaces (`cli/trades/backfill.py` unions the existing hour in)."""
    hour_end = _check_hour(hour)
    _check_gaps(gaps_healed, hour=hour, hour_end=hour_end, label="a healed gap", primary_boundaries=True)
    _check_gaps(residual_gaps, hour=hour, hour_end=hour_end, label="a residual gap", primary_boundaries=False)

    d = _hour_dir(root, pair, kind, hour)
    final = d / f"{hour:%H}.parquet"
    if final.exists() and not replace:
        raise FileExistsError(f"reconciled final already minted: {final}")

    if not blocks:
        # An empty final would assert that the hour is committed, complete and rowless, and the
        # reconciled-first reader would then shadow the raw primary hour with that lie.
        raise CaptureError(f"refusing to mint {final}: no blocks (there is nothing to heal)")

    frame = pl.concat([b.frame for b in blocks])  # block order; NEVER sorted (absolute quantities)
    if list(frame.schema.items()) != list(pl.Schema(schema).items()):
        # Uniformly wrong blocks would otherwise concat happily and publish a dtype no consumer expects.
        raise CaptureError(f"refusing to mint {final}: block schema {frame.schema} does not match {schema}")

    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{hour:%H}.parquet.tmp"
    frame.write_parquet(tmp, compression="zstd")  # truncates a torn tmp left by a killed run

    # The digest comes from the temp file's bytes, which ARE the final's, and lands first: no final is ever published unmanifested.
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    manifest_tmp = d / f"{hour:%H}.parquet.sha256.tmp"
    manifest_tmp.write_text(f"{digest}  {final.name}\n")
    _replace_durably(manifest_tmp, final.with_name(final.name + ".sha256"))

    provenance = {
        "pair": pair,
        "kind": kind,
        "hour": hour.isoformat(),
        "blocks": [{"source": b.source, "rows": b.frame.height, "from_ts": b.from_ts, "to_ts": b.to_ts} for b in blocks],
        "gaps_healed": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in gaps_healed],
        "residual_gaps": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in residual_gaps],
        "sha256": digest,
        "tool": tool,
        "version": tool_version,
    }
    # Extras never shadow the base record: a caller must not rewrite `sha256` or `hour` and make the provenance lie.
    for k, v in (extra_provenance or {}).items():
        if k in provenance:
            raise CaptureError(f"extra_provenance may not override the base field {k!r}")
        provenance[k] = v
    provenance_tmp = d / f"{hour:%H}.provenance.json.tmp"
    provenance_tmp.write_text(json.dumps(provenance, indent=1, default=str) + "\n")
    _replace_durably(provenance_tmp, d / f"{hour:%H}.provenance.json")

    if final.exists() and not replace:
        # Re-checked because `os.replace` clobbers and everything above took real time. The window is not closed —
        # a no-clobber publish would need `os.link`, forking the durability semantics this module exists to share —
        # but the reconciler is single-process, and a racing minter is a bug to hear about, not a file to lose.
        raise FileExistsError(f"reconciled final appeared while minting: {final}")
    _replace_durably(tmp, final)  # publish LAST
    return final
