"""The capturing loader: the one sanctioned way research reads frozen datasets (spec 00086 D1) — dataset identity is the sha256 of
the bytes a run actually reads. It applies any window itself and accumulates per-dataset files/rows/span from what it RETURNS, so
rows-used cannot drift from rows-recorded. A manifest is read only for `read_series`'s content cross-check, so no manifest shape
reaches the identity path."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import polars as pl

from cli.data.errors import DataSyncError
from cli.data.sync import _attestations_for_set
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
        self._by_path: dict[str, dict[str, str]] = {}

    def _attestations(self, dataset: str) -> tuple[set[str], dict[str, str]]:
        """Vouched hashes and their path bindings, from the same source the sync path uses.

        Shared deliberately: a read and a fetch that disagreed about what attests a dataset would
        leave exactly the hole this closes."""
        if dataset not in self._vouched:
            try:
                vouched, by_path = _attestations_for_set(self._root / dataset, dataset)
            except DataSyncError as exc:  # refuse in THIS surface's dialect, not the sync path's
                raise RegistryError(f"{dataset}: committed attestations are unreadable — {exc}") from exc
            except ValueError as exc:  # unparseable manifest: typed, not a raw JSONDecodeError
                raise RegistryError(
                    f"{dataset}: manifest.json is unparseable — refusing to read a dataset whose freeze record is corrupt"
                ) from exc
            self._vouched[dataset], self._by_path[dataset] = vouched, by_path
        return self._vouched[dataset], self._by_path[dataset]

    def _vouched_for(self, dataset: str) -> set[str]:
        return self._attestations(dataset)[0]

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
            # At the manifests' own grade: they vouch FRAME-CONTENT hashes (`dataset_hash`), never file-byte ones, so a
            # byte-grade test here would refuse every healthy read; and on the FULL frame, because the freeze vouched the
            # whole series. Path-BOUND where an attestation names this path -- a swap inside one set leaves the hash SET
            # unchanged; a manifest predating the path-keyed contract offers only membership (T0132, resolved).
            if (expected := self._attestations(dataset)[1].get(relpath)) is not None:
                if dataset_hash(full) != expected:
                    raise RegistryError(
                        f"{dataset}/{relpath}: frame-content hash is not what the committed attestation "
                        f"names for THAT path — the data changed since the freeze, or two series were swapped"
                    )
            elif vouched and dataset_hash(full) not in vouched:
                raise RegistryError(
                    f"{dataset}/{relpath}: frame-content hash absent from the manifest's vouched set — the data changed since the freeze"
                )
        frame = full
        if window is not None:
            # A naive or unparseable bound is a caller mistake, not a corrupt dataset, so both are refused typed: untyped, an
            # unparseable one surfaces as fromisoformat's raw ValueError and a naive one as polars' SchemaError comparing tz-aware
            # `ts` against a naive literal.
            bounds = []
            for w in window:
                try:
                    parsed = datetime.fromisoformat(w)
                except ValueError as exc:
                    raise RegistryError(f"window bound {w!r} is not an ISO-8601 timestamp: {exc}") from exc
                if parsed.tzinfo is None:
                    # Do NOT interpolate the caller's own bound into the suggestion: an offset appended to a
                    # date-only bound yields '2020-01-03+00:00', which fromisoformat reads as NAIVE (the '+' is
                    # taken as the date/time separator), looping the caller through the same refusal.
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
