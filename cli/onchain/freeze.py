"""The frozen snapshot of the vintage chain at an as-of line (spec 00164 D8): every row the base and the day files hold
through that line, in day order, as one parquet, and a manifest naming the line, written last."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import polars as pl

from cli.data.manifest import build_manifest, series_entry
from cli.onchain.chain import ChainError, verify, walk
from cli.onchain.series import SCHEMA

SNAPSHOT_RELPATH = "BTC/onchain.parquet"


def freeze(chain: Path, as_of: date, out: Path, *, written_at: str) -> Path:
    """`chain`, the chain's own directory, verified through `as_of`'s line and frozen into `out`, a directory this call
    makes; the manifest's path. A day after the head has no line, which `verify` refuses. Every read and refusal comes
    before `out` is made. The commit and the image ids the provenance names are the as-of line's alone: a chain that
    crossed a node release names its earlier image in its earlier lines."""
    if os.path.lexists(out):
        raise ChainError(f"{out} exists; a snapshot is written only into a directory the freeze makes")
    verify(chain, as_of)
    lines = walk(chain, as_of)
    frame = pl.concat([pl.read_parquet(chain / relpath) for line in lines for relpath in line.files])
    if list(frame.schema.items()) != list(SCHEMA.items()):
        raise ChainError(f"{chain}: the rows through {as_of} are not of the day file's schema: {dict(frame.schema)}")
    as_of_line = lines[-1]
    manifest = build_manifest(
        {SNAPSHOT_RELPATH: series_entry(frame, SNAPSHOT_RELPATH)},
        written_at=written_at,
        identity="set",
        provenance={
            "producer": "zcrypto onchain freeze",
            "chain": chain.resolve().name,
            "as_of_line": {"relpath": as_of_line.relpath, "sha256": as_of_line.sha256},
            "brk_commit": as_of_line.vintage["brk_commit"],
            "bitview_image": as_of_line.vintage["bitview_image"],
            "bitcoind_image": as_of_line.vintage["bitcoind_image"],
        },
    )
    out.mkdir(parents=True)
    snapshot = out / SNAPSHOT_RELPATH
    snapshot.parent.mkdir()
    frame.write_parquet(snapshot)
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path
