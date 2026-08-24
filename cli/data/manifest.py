"""The manifest contract (spec 00099): one shape, so no consumer needs per-set knowledge.

Five writers plus an external freeze used to emit four `series` shapes, three timestamp spellings
and two digest names. Two attempts to read that zoo generically failed nine cold-review rounds
between them, the findings moving each round because a generic reader over a zoo is a pile of
special cases discovered one review at a time. This module is the other answer: normalise the
writers, and give every consumer one reader.

The load-bearing decision is that `series` is keyed by the parquet's path RELATIVE TO THE DATASET
ROOT. The path is the key, so a consumer never derives one -- which is what makes a path-bound
verification possible at all, and what flattens all four legacy shapes into this one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import polars as pl

from cli.ohlc.dataset import dataset_hash

SCHEMA_VERSION = 1

_LEAF_FIELDS = ("sha256", "rows", "first_ts", "last_ts")


class ManifestError(Exception):
    """A manifest does not satisfy the contract. Refusing beats guessing: guessing is the zoo."""


def series_entry(frame: pl.DataFrame, relpath: str) -> dict[str, Any]:
    """One series leaf. `relpath` is accepted so a caller cannot build an entry for a key it has
    not validated -- the key and the file must be the same thing."""
    _check_key(relpath)
    return {
        "sha256": dataset_hash(frame),
        "rows": frame.height,
        # ISO-8601 T-form, which is what every writer already emits, so conversion is a no-op here.
        "first_ts": frame["ts"].min().isoformat(),
        "last_ts": frame["ts"].max().isoformat(),
    }


def set_digest(series: dict[str, Any], keys: Sequence[str] | None = None) -> str:
    """sha256 over the member hashes, in ascending lexicographic order OF THE SERIES KEY.

    Ordering by the key rather than by any part's meaning is what keeps this free of per-set
    knowledge: the legacy writers disagreed precisely here -- `backfill.py` sorted interval keys as
    strings ('1440' < '240' < '60') and `reach.py` as integers -- so no single recipe could
    reproduce both and the ordering had to become a decision.
    """
    members = list(series) if keys is None else list(keys)
    if not members:
        raise ManifestError(
            "refusing a digest over an empty series set: sha256 of nothing is a fixed sentinel, so two unrelated empty sets would compare equal"
        )
    unknown = [k for k in members if k not in series]
    if unknown:
        raise ManifestError(f"subset names {unknown[0]!r}, which is not in series")
    return hashlib.sha256("".join(series[k]["sha256"] for k in sorted(members)).encode("utf-8")).hexdigest()


def build_manifest(
    series: dict[str, Any],
    *,
    written_at: str,
    identity: str = "set",
    subsets: dict[str, Sequence[str]] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The conformant document. `provenance` never reaches any digest -- see the module docstring."""
    if not series:
        raise ManifestError("refusing a manifest with an empty series map")
    for key in series:
        _check_key(key)
        _check_leaf(key, series[key])

    subset_sha256 = {name: set_digest(series, keys=members) for name, members in (subsets or {}).items()}
    if identity != "set":
        name = identity.removeprefix("subset:")
        if identity == name or name not in subset_sha256:
            raise ManifestError(f"identity {identity!r} names no declared subset")

    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "written_at": written_at,
        "identity": identity,
        "set_sha256": set_digest(series),
        "series": series,
    }
    if subset_sha256:
        out["subset_sha256"] = subset_sha256
    out["provenance"] = provenance or {}
    return out


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    written_at: str
    identity: str
    set_sha256: str
    subset_sha256: dict[str, str]
    series: dict[str, Any]
    provenance: dict[str, Any]

    @property
    def identity_digest(self) -> str:
        """The digest that identifies this set. One accessor, so no caller carries a dataset name.

        A set whose identity is a named subset (reach's is its continuous legs) and one whose
        identity is set-wide are read identically here; without this the caller would have to know
        which is which, which is the removed special case reappearing one layer up.
        """
        if self.identity == "set":
            return self.set_sha256
        return self.subset_sha256[self.identity.removeprefix("subset:")]

    @property
    def vouched(self) -> set[str]:
        """The attested content hashes, read from `series` EXPLICITLY.

        Never by walking the document: `provenance` is free-form, so a walk would let a hash placed
        anywhere inside it attest content nothing checked.
        """
        return {leaf["sha256"] for leaf in self.series.values()}

    def hash_by_path(self) -> dict[str, str]:
        """Path -> attested hash. This is the thing a manifest could not previously give without
        per-set knowledge, and the reason a swapped pair used to be invisible."""
        return {key: leaf["sha256"] for key, leaf in self.series.items()}


def read_manifest(path: Path) -> Manifest:
    """Parse and validate. A manifest without `schema_version` is legacy and is REFUSED, not
    guessed at -- the caller decides whether to convert it."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ManifestError(f"{path}: unparseable manifest") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: manifest is not an object")

    version = raw.get("schema_version")
    if version is None:
        raise ManifestError(f"{path}: no schema_version — this is a legacy manifest, convert it rather than reading it")
    if version != SCHEMA_VERSION:
        raise ManifestError(f"{path}: schema_version {version!r} is not {SCHEMA_VERSION}")

    series = raw.get("series")
    if not isinstance(series, dict) or not series:
        raise ManifestError(f"{path}: series must be a non-empty object")
    for key, leaf in series.items():
        _check_key(key, where=str(path))
        _check_leaf(key, leaf, where=str(path))

    identity = raw.get("identity", "set")
    subset_sha256 = raw.get("subset_sha256") or {}
    if identity != "set" and identity.removeprefix("subset:") not in subset_sha256:
        raise ManifestError(f"{path}: identity {identity!r} names no declared subset")

    return Manifest(
        schema_version=version,
        written_at=raw.get("written_at", ""),
        identity=identity,
        set_sha256=raw.get("set_sha256", ""),
        subset_sha256=dict(subset_sha256),
        series=series,
        provenance=dict(raw.get("provenance") or {}),
    )


def _check_key(key: str, where: str = "") -> None:
    prefix = f"{where}: " if where else ""
    if not isinstance(key, str) or not key:
        raise ManifestError(f"{prefix}series key must be a non-empty string, got {key!r}")
    pure = PurePosixPath(key)
    if pure.is_absolute() or ".." in pure.parts:
        raise ManifestError(f"{prefix}series key {key!r} must be a path relative to the dataset root")
    if pure.suffix != ".parquet":
        raise ManifestError(f"{prefix}series key {key!r} must name a .parquet file — the key IS the path")


def _check_leaf(key: str, leaf: Any, where: str = "") -> None:
    prefix = f"{where}: " if where else ""
    if not isinstance(leaf, dict):
        raise ManifestError(f"{prefix}series[{key!r}] must be an object")
    for field in _LEAF_FIELDS:
        if field not in leaf:
            raise ManifestError(f"{prefix}series[{key!r}] is missing {field}")
    if not isinstance(leaf["rows"], int) or isinstance(leaf["rows"], bool) or leaf["rows"] < 0:
        raise ManifestError(f"{prefix}series[{key!r}].rows must be a non-negative integer")
    digest = leaf["sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ManifestError(f"{prefix}series[{key!r}].sha256 must be 64 hex characters")


def conformant_paths(root: Path) -> Iterable[Path]:
    """Every `manifest.json` under `root`'s immediate dataset directories."""
    return sorted(root.glob("*/manifest.json"))
