"""The capturing loader: dataset identity computed from the bytes a run actually reads.

The one sanctioned way research reads frozen datasets (spec 00086 D1). Hashes every file it opens,
applies any window itself, and accumulates per-dataset files/rows/span from what it RETURNS -- so
rows-used cannot drift from rows-recorded by construction. It imports nothing from manifests: no
manifest shape can reach the identity path. Where a manifest vouches per-series hashes, a computed
hash absent from a non-empty vouched set means the file changed since the manifest was written --
fitting on disputed bytes is exactly what should stop a run, so `read_series` refuses.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import polars as pl

from cli.data.sync import _manifest_sha256s, sidecar_hashes
from cli.ohlc.dataset import dataset_hash, read_parquet
from cli.registry.errors import RegistryError

_TS_FORMAT = "%Y-%m-%d %H:%M:%S%z"  # matches the frozen manifests' stamp style: space, not 'T'


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _stamp(value: datetime) -> str:
    s = value.strftime(_TS_FORMAT)
    return s[:-2] + ":" + s[-2:]  # +0000 -> +00:00


class ObservedReader:
    def __init__(self, data_root: Path) -> None:
        self._root = Path(data_root)
        self._files: dict[str, dict[str, str]] = {}
        self._reads: dict[tuple[str, str], tuple[str, str] | None] = {}  # (dataset, relpath) -> window
        self._rows: dict[str, int] = {}
        self._span: dict[str, tuple[datetime, datetime]] = {}  # dataset -> (first_ts, last_ts)
        self._vouched: dict[str, set[str]] = {}

    def _vouched_for(self, dataset: str) -> set[str]:
        if dataset not in self._vouched:
            manifest = self._root / dataset / "manifest.json"
            if not manifest.exists():
                self._vouched[dataset] = sidecar_hashes(dataset)
            else:
                try:
                    self._vouched[dataset] = _manifest_sha256s(json.loads(manifest.read_text())) | sidecar_hashes(dataset)
                except ValueError as exc:  # unparseable manifest: refuse typed, not with a raw JSONDecodeError
                    raise RegistryError(
                        f"{dataset}: manifest.json is unparseable — refusing to read a dataset whose freeze record is corrupt: {exc}"
                    ) from exc
        return self._vouched[dataset]

    def vouched_status(self) -> dict[str, str]:
        return {
            d: (f"checked ({len(v)} vouched hashes)" if v else "inert (0 vouched hashes)")
            for d, v in ((d, self._vouched_for(d)) for d in self._files)
        }

    def read_series(self, dataset: str, relpath: str, window: tuple[str, str] | None = None) -> pl.DataFrame:
        key = (dataset, relpath)
        if key in self._reads and self._reads[key] != window:
            raise RegistryError(
                f"{dataset}/{relpath}: already read with window {self._reads[key]!r}; one record, one read discipline"
            )
        path = self._root / dataset / relpath
        full = read_parquet(path)
        if key not in self._reads:
            digest = _sha256_file(path)  # the IDENTITY: file bytes as on disk
            vouched = self._vouched_for(dataset)
            # The cross-check runs at the manifests' own grade: the frozen manifests vouch FRAME-CONTENT
            # hashes (dataset_hash = sha256 of canonical CSV), never file-byte hashes -- a byte-grade
            # membership test here refuses every healthy read of ohlc-full/ohlc-15m (the round-1 blocker).
            # Checked on the FULL frame, before windowing: the freeze vouched the whole series.
            if vouched and dataset_hash(full) not in vouched:
                raise RegistryError(
                    f"{dataset}/{relpath}: frame-content hash absent from the manifest's vouched set — the data changed since the freeze"
                )
        frame = full
        if window is not None:
            # A naive or unparseable bound is a caller mistake, not a corrupt dataset: refuse it
            # typed, or polars raises a SchemaError comparing tz-aware `ts` against a naive literal
            # and the paved door dies with a traceback on its most natural spelling.
            bounds = []
            for w in window:
                try:
                    parsed = datetime.fromisoformat(w)
                except ValueError as exc:
                    raise RegistryError(f"window bound {w!r} is not an ISO-8601 timestamp: {exc}") from exc
                if parsed.tzinfo is None:
                    # Do NOT interpolate the caller's own string into the suggestion: appending an
                    # offset to a date-only bound yields '2020-01-03+00:00', which fromisoformat
                    # reads as NAIVE (the '+' is taken as the date/time separator), so the advice
                    # would loop the caller through the same refusal. Name a spelling that works.
                    raise RegistryError(
                        f"window bound {w!r} has no timezone — bounds need an explicit offset, e.g. '2020-01-03 00:00:00+00:00'"
                    )
                bounds.append(parsed)
            start, end = bounds
            frame = frame.filter((pl.col("ts") >= start) & (pl.col("ts") <= end))
        if frame.height == 0:
            raise RegistryError(f"{dataset}/{relpath}: zero rows after windowing — a block that says nothing is refused")
        if key not in self._reads:
            self._reads[key] = window
            self._files.setdefault(dataset, {})[relpath] = digest
            self._rows[dataset] = self._rows.get(dataset, 0) + frame.height
            first, last = frame["ts"][0], frame["ts"][-1]
            lo, hi = self._span.get(dataset, (first, last))
            self._span[dataset] = (min(lo, first), max(hi, last))
        return frame

    def block(self) -> dict:
        if not self._files:
            raise RegistryError("ObservedReader accumulated nothing — a block that says nothing is refused")
        return {
            d: {
                "files": dict(sorted(self._files[d].items())),
                "rows": self._rows[d],
                "span": [_stamp(self._span[d][0]), _stamp(self._span[d][1])],
            }
            for d in sorted(self._files)
        }
