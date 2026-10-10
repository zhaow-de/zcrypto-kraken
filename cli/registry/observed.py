"""The capturing loader: the one sanctioned way research reads frozen datasets and the rolling canonical (spec 00086 D1). A
frozen dataset's identity is the sha256 of the bytes a run actually reads; the rolling canonical's is the sha256 of its as-of
index line, which commits through its chain to every byte a read opens. It applies any window itself and accumulates
per-dataset files/rows/span from what it RETURNS, so rows-used cannot drift from rows-recorded. A manifest is read only for
`read_series`'s content cross-check, so no manifest shape reaches the identity path."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import polars as pl

from cli.data import rolling
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


def _bounds(window: tuple[str, str]) -> tuple[datetime, datetime]:
    # A naive or unparseable bound is a caller mistake, not a corrupt dataset, so both are refused typed: untyped, an
    # unparseable one surfaces as fromisoformat's raw ValueError and a naive one as a raw error comparing it against a
    # tz-aware time.
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
    return start, end


class ObservedReader:
    def __init__(self, data_root: Path) -> None:
        self._root = Path(data_root)
        self._files: dict[str, dict[str, str]] = {}
        self._reads: dict[tuple[str, str], tuple[str, str] | None] = {}  # (dataset, relpath) -> window
        self._rolling_reads: dict[tuple[str, str, int], tuple[str, str] | None] = {}  # (dataset, pair, interval) -> window
        self._lines: dict[str, rolling.Line] = {}  # dataset -> the as-of line its rolling reads record
        self._holes: dict[str, list[str]] = {}
        self._rows: dict[str, int] = {}
        self._span: dict[str, tuple[datetime, datetime]] = {}  # dataset -> (first_ts, last_ts)
        self._vouched: dict[str, set[str]] = {}
        self._by_path: dict[str, dict[str, str]] = {}

    def _attestations(self, dataset: str) -> tuple[set[str], dict[str, str]]:
        """Vouched hashes and their path bindings, from the same source the sync path's manifest arm uses.

        Shared deliberately: a read and a fetch that disagreed about what attests a dataset would
        leave exactly the hole this closes. A set the index attests has none: `read_rolling` checks it
        against its lines, as the fetch's chained arm does, and never asks here."""
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
        status = {}
        for d in self._files:
            if d in self._lines:
                status[d] = f"chained (as of {self._lines[d].day}, line {self._lines[d].sha256[:12]})"
            elif v := self._vouched_for(d):
                status[d] = f"checked ({len(v)} vouched hashes)"
            else:
                status[d] = "inert (0 vouched hashes)"
        return status

    def holes(self) -> dict[str, list[str]]:
        return {d: list(h) for d, h in sorted(self._holes.items())}

    def _one_way(self, dataset: str, *, chained: bool) -> None:
        if dataset in self._files and (dataset in self._lines) != chained:
            how = "through its index" if dataset in self._lines else "file by file"
            raise RegistryError(f"{dataset}: already read {how}; a record reads one dataset one way")

    def _accumulate(self, dataset: str, frame: pl.DataFrame) -> None:
        self._rows[dataset] = self._rows.get(dataset, 0) + frame.height
        first, last = frame["ts"][0], frame["ts"][-1]
        lo, hi = self._span.get(dataset, (first, last))
        self._span[dataset] = (min(lo, first), max(hi, last))

    def read_series(self, dataset: str, relpath: str, window: tuple[str, str] | None = None) -> pl.DataFrame:
        self._one_way(dataset, chained=False)
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
            # unchanged; a manifest predating the path-keyed contract offers only membership (T0132).
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
            start, end = _bounds(window)
            frame = frame.filter((pl.col("ts") >= start) & (pl.col("ts") <= end))
        if frame.height == 0:
            raise RegistryError(f"{dataset}/{relpath}: zero rows after windowing — a block that says nothing is refused")
        if key not in self._reads:
            self._reads[key] = window
            self._files.setdefault(dataset, {})[relpath] = digest
            self._accumulate(dataset, frame)
        return frame

    def read_rolling(
        self,
        dataset: str,
        pair: str,
        interval: int,
        as_of: str,
        window: tuple[str, str] | None = None,
        accept_holes: bool = False,
    ) -> pl.DataFrame:
        """`pair`'s bars at `interval` from the chained set `dataset` as of the `YYYY-MM-DD` day `as_of`. The dataset's
        `files` record that day's index line alone, whatever pairs and grids are read; `rows` and `span` accumulate once
        per pair and grid. Each hole `accept_holes` lets through is listed by `holes`."""
        try:
            day = datetime.strptime(as_of, "%Y-%m-%d").date()
        except ValueError as exc:
            raise RegistryError(f"{dataset}: as-of {as_of!r} is not a YYYY-MM-DD date") from exc
        bounds = None if window is None else _bounds(window)
        self._one_way(dataset, chained=True)
        if dataset in self._lines and self._lines[dataset].day != day:
            raise RegistryError(f"{dataset}: already read as of {self._lines[dataset].day}; one record, one as-of")
        key = (dataset, pair, interval)
        if key in self._rolling_reads and self._rolling_reads[key] != window:
            raise RegistryError(
                f"{dataset} {pair} at {interval} minutes: already read with window {self._rolling_reads[key]!r}; "
                "one record, one read discipline"
            )
        try:
            read = rolling.read_rolling(self._root / dataset, pair, interval, day, window=bounds, accept_holes=accept_holes)
        except rolling.RollingError as exc:
            raise RegistryError(f"{dataset}: {exc}") from exc
        frame = read.frame
        if frame.height == 0:
            raise RegistryError(
                f"{dataset} {pair} at {interval} minutes as of {day}: zero rows after windowing — a block that says nothing is refused"
            )
        if key not in self._rolling_reads:
            self._rolling_reads[key] = window
            self._lines[dataset] = read.line
            self._files[dataset] = {read.line.relpath: read.line.sha256}
            self._accumulate(dataset, frame)
            for hole_day in read.holes:
                if (hole := f"{pair} {hole_day}") not in self._holes.setdefault(dataset, []):
                    self._holes[dataset].append(hole)
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
