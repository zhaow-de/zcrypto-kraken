"""The disk conformance pass: every schema-4 record's cited bytes, re-hashed against `data/` (spec 00086 D7)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pytest

from cli.ohlc.dataset import to_frame, write_parquet
from cli.registry import TrialRegistry
from cli.registry.observed import ObservedReader

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data"
_CANONICAL = _DATA_ROOT / "ohlc-full"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

_ABSENT_OK: frozenset[str] = frozenset()
"""Dataset dirs a record may legitimately cite that do not resolve on the canonical data host.

EMPTY at birth; it grows only by a reviewed PR. An UNLISTED citation that does not resolve is a
finding, so a fabricated citation either fails this suite or is itself a visible commit. The list
names DIRS, not hosts — which is why the pass is gated on the data root's presence instead: adding a
dataset here to appease a bare-checkout CI run would neuter the fence for that dataset forever.
"""

REDERIVED, ABSENT_HERE, FINDING = "rederived", "absent-here", "finding"

_STOP = (
    "the cited bytes moved under an existing dataset name — STOP: a re-freeze mints a sibling directory, "
    "so an in-place, undated dir whose files no longer hash to what a record read means the frozen data "
    "itself changed, and every figure that record registered is now unverifiable"
)


def _digest(path: Path, cache: dict) -> str:
    """sha256 of a file's bytes, memoised per `(path, size, mtime)` — one dataset is cited by many records."""
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in cache:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
        cache[key] = h.hexdigest()
    return cache[key]


@dataclass(frozen=True)
class Verdict:
    trial_id: int
    dataset: str
    verdict: str
    detail: str


def conformance(records, data_root: Path, absent_ok: frozenset[str]) -> list[Verdict]:
    """One verdict per `(record, dataset)` citation, over whatever records are handed in."""
    cache: dict = {}
    out: list[Verdict] = []
    for record in records:
        for dataset, block in sorted((record.datasets or {}).items()):
            directory = data_root / dataset
            if not directory.is_dir():
                listed = dataset in absent_ok
                out.append(
                    Verdict(
                        record.trial_id,
                        dataset,
                        ABSENT_HERE if listed else FINDING,
                        "" if listed else f"cites dataset {dataset!r}, which is not on this host and is not an allowed absence",
                    )
                )
                continue
            bad = []
            for relpath, recorded in sorted(block["files"].items()):
                path = directory / relpath
                if not path.is_file():
                    bad.append(f"{relpath}: the named file is missing")
                    continue
                found = _digest(path, cache)
                if found != recorded:
                    bad.append(f"{relpath}: sha256 {found} != recorded {recorded}")
            out.append(Verdict(record.trial_id, dataset, FINDING if bad else REDERIVED, "; ".join(bad)))
    return out


def test_every_schema_4_records_citations_still_rehash_against_this_hosts_data():
    # TWO gates, both required. Without the first, the first schema-4 record turns every bare-checkout
    # CI run permanently red; without the second the pass would be vacuous while it reads as covered.
    if not _CANONICAL.is_dir():
        pytest.skip("data/ohlc-full absent — the canonical-host marker; the disk pass runs only where the data root is")
    records = [r for r in TrialRegistry(_REGISTRY).records if r.schema_version >= 4]
    if not records:
        pytest.skip("no schema-4 records yet — nothing in the registry cites observed bytes")

    verdicts = conformance(records, _DATA_ROOT, _ABSENT_OK)
    findings = [v for v in verdicts if v.verdict == FINDING]
    assert not findings, _STOP + "\n" + "\n".join(f"  trial {v.trial_id} / {v.dataset}: {v.detail}" for v in findings)


def _rows(n: int, *, start: int = 1577836800, step: int = 86400):  # 2020-01-01, daily steps
    return [[start + i * step, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def _write(root: Path, dataset: str, relpath: str, n: int) -> None:
    write_parquet(to_frame(_rows(n)), root / dataset / relpath)


def _observed(root: Path, dataset: str, relpaths: tuple[str, ...]) -> dict:
    reader = ObservedReader(root)
    for relpath in relpaths:
        reader.read_series(dataset, relpath)
    return reader.block()


def _fabricated(dataset: str) -> dict:
    """A citation of bytes that were never read here — the shape `append()` cannot tell from a real one."""
    return {
        dataset: {
            "files": {"BTC/EUR/1440.parquet": "a" * 64},
            "rows": 10,
            "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"],
        }
    }


def _append(registry_path: Path, datasets: dict, n: int) -> None:
    TrialRegistry(registry_path).append(
        iteration="iter-000",
        family="CONFORMANCE",
        spec_hash="0" * 64,
        datasets=datasets,
        seeds=[],
        metrics={"sharpe": 1.0},
        n_trials_in_family=n,
        verdict="park",
        run_ref="cli/registry/observed.py",
    )


def test_the_pass_separates_rederived_from_absent_from_finding(tmp_path):
    root, registry_path = tmp_path / "data", tmp_path / "registry.jsonl"

    # (1) rederived — a real file, cited by the loader that read it.
    _write(root, "ds-good", "BTC/EUR/1440.parquet", 10)
    _append(registry_path, _observed(root, "ds-good", ("BTC/EUR/1440.parquet",)), 1)

    # (2) listed-absent and (3) unlisted-absent — neither dir exists; only one is named in the list.
    _append(registry_path, _fabricated("ds-elsewhere"), 2)
    _append(registry_path, _fabricated("ds-invented"), 3)

    # (4) hash mismatch — the cited file's bytes change after the record is written.
    _write(root, "ds-drifted", "BTC/EUR/1440.parquet", 10)
    _append(registry_path, _observed(root, "ds-drifted", ("BTC/EUR/1440.parquet",)), 4)
    _write(root, "ds-drifted", "BTC/EUR/1440.parquet", 11)

    # (5) named file missing from a dir that IS here.
    _write(root, "ds-partial", "BTC/EUR/1440.parquet", 10)
    _write(root, "ds-partial", "ETH/EUR/1440.parquet", 10)
    _append(registry_path, _observed(root, "ds-partial", ("BTC/EUR/1440.parquet", "ETH/EUR/1440.parquet")), 5)
    (root / "ds-partial" / "ETH/EUR/1440.parquet").unlink()

    records = TrialRegistry(registry_path).records
    assert [r.trial_id for r in records] == [1, 2, 3, 4, 5]

    seen = {v.dataset: v for v in conformance(records, root, frozenset({"ds-elsewhere"}))}
    assert len(seen) == 5
    assert seen["ds-good"].verdict == REDERIVED
    assert seen["ds-elsewhere"].verdict == ABSENT_HERE
    assert seen["ds-invented"].verdict == FINDING
    assert "not an allowed absence" in seen["ds-invented"].detail
    assert seen["ds-drifted"].verdict == FINDING
    assert "sha256" in seen["ds-drifted"].detail
    assert seen["ds-partial"].verdict == FINDING
    assert seen["ds-partial"].detail == "ETH/EUR/1440.parquet: the named file is missing"
    assert seen["ds-partial"].trial_id == 5

    with_committed_list = {v.dataset: v for v in conformance(records, root, _ABSENT_OK)}
    assert with_committed_list["ds-elsewhere"].verdict == FINDING
