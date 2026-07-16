"""Write path for reconciled hours (spec 00050).

Mirrors `SegmentWriter`'s committed-final invariant exactly, because the overlay is verified by the
same `verify_tree`:

    `<HH>.parquet` on disk ALWAYS means "committed, complete, and manifested".

So the sidecar is minted from the temp file's bytes — which ARE the final's bytes, because the temp
file IS the final, renamed — and written BEFORE the atomic rename that publishes it. A kill anywhere
in here leaves no final at all, and the next run simply re-mints. The rename is last, always.

An existing final is never overwritten: a re-run is a no-op (`FileExistsError`), and a provisionally
residual hour is healed by a NEW mint plus a superseding ledger record, never by mutating a published
file. Nothing here decodes or re-blesses a file it did not itself write.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.reconcile import Block, Gap
from cli.capture.errors import CaptureError

# `_replace_durably` is module-private in the capture package. Importing it is a deliberate, narrow
# coupling: the overlay is verified by the same `verify_tree` as the raw mirrors, so it MUST have
# byte-identical durability semantics (fsync the data, rename, fsync the directory entry). A second
# implementation would be a second thing to get wrong.
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
    """Return the hour's EXCLUSIVE end boundary, refusing anything that is not an exact UTC hour.

    The path is formatted straight from `hour`, so a stray 09:30 would silently write the 09:00 hour's
    file — publishing half an hour under a name that promises the whole of it.
    """
    if hour.tzinfo is None or hour != hour.replace(minute=0, second=0, microsecond=0):
        raise CaptureError(f"refusing to mint {hour!r}: not an exact UTC hour boundary")
    return hour + timedelta(hours=1)


def _check_gaps(gaps: list[Gap], *, hour: datetime, hour_end: datetime, label: str) -> None:
    """Hold every gap to `Gap`'s boundary-ownership contract, against THIS hour's own bounds.

    This is the one guard that catches a caller passing `find_book_gaps` an inclusive `hour_end`
    (09:59:59.999999) where the contract says exclusive (10:00:00). Such an hour yields a tail gap
    that ends short of the boundary, and `splice_book`'s tail filter (`ts >= gaps[-1].end`) then
    admits primary rows AFTER the secondary block — rows out of block order in an unbackfillable
    archive. The bad bound is invisible in the blocks by the time they reach us; it is loud here.

    An unowned boundary (`*_is_primary_message=False`) is, by construction, an hour boundary — the
    head/tail edge, or both edges of a wholly-absent primary hour. Anything else is a malformed gap.
    """
    for gap in gaps:
        if not (hour <= gap.start <= hour_end and hour <= gap.end <= hour_end):
            raise CaptureError(f"{label} {gap.start.isoformat()}->{gap.end.isoformat()} lies outside the {hour:%H}:00 hour")
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
    """Publish `blocks` as this hour's reconciled final, atomically, with its sidecar and provenance.

    Returns the final's path. Raises `FileExistsError` if the hour is already minted (unless
    `replace=True`), and `CaptureError` if the inputs violate the hour's contract (see `_check_hour` /
    `_check_gaps`).
    """
    hour_end = _check_hour(hour)
    _check_gaps(gaps_healed, hour=hour, hour_end=hour_end, label="a healed gap")
    _check_gaps(residual_gaps, hour=hour, hour_end=hour_end, label="a residual gap")

    d = _hour_dir(root, pair, kind, hour)
    final = d / f"{hour:%H}.parquet"
    if final.exists() and not replace:
        raise FileExistsError(f"reconciled final already minted: {final}")

    if not blocks:
        # An empty final would assert "this hour is committed and complete, and holds no rows" — and
        # the reconciled-first reader would then shadow the raw primary hour with that lie.
        raise CaptureError(f"refusing to mint {final}: no blocks (there is nothing to heal)")

    frame = pl.concat([b.frame for b in blocks])  # block order; NEVER sorted (absolute quantities)
    if list(frame.schema.items()) != list(pl.Schema(schema).items()):
        # Uniformly wrong blocks (e.g. read without the schema) would otherwise concat happily and be
        # published into the archive with a dtype no consumer expects.
        raise CaptureError(f"refusing to mint {final}: block schema {frame.schema} does not match {schema}")

    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{hour:%H}.parquet.tmp"
    frame.write_parquet(tmp, compression="zstd")  # truncates a torn tmp left by a killed run

    # The sidecar comes from the temp file's bytes, which ARE the final's bytes: the digest is right
    # before the file it certifies exists, so a final can never be published unmanifested.
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
    # Extras are merged, never allowed to shadow the base record: a caller must not be able to
    # rewrite `sha256` or `hour` and make the provenance lie about the file it certifies.
    for k, v in (extra_provenance or {}).items():
        if k in provenance:
            raise CaptureError(f"extra_provenance may not override the base field {k!r}")
        provenance[k] = v
    provenance_tmp = d / f"{hour:%H}.provenance.json.tmp"
    provenance_tmp.write_text(json.dumps(provenance, indent=1, default=str) + "\n")
    _replace_durably(provenance_tmp, d / f"{hour:%H}.provenance.json")

    if final.exists() and not replace:
        # Re-checked against the entry test: `os.replace` clobbers, and everything above took real
        # time. The window is not closed (a no-clobber publish would need `os.link`, forking the
        # durability semantics this module exists to share) — but the reconciler is single-process,
        # and a racing minter is a bug we want to hear about rather than a file we want to lose.
        raise FileExistsError(f"reconciled final appeared while minting: {final}")
    _replace_durably(tmp, final)  # publish LAST
    return final
