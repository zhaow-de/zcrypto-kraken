"""The conformance passes: every schema-4 record's cited bytes, re-hashed against `data/` (spec 00086 D7) and against the
hub's `hot/` (spec 00129 D6)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from cli.config import load_config, resolve_hot_source
from cli.data.rolling import ROLLING_SET, RollingError, verify
from cli.ohlc.dataset import to_frame, write_parquet
from cli.registry import TrialRegistry
from cli.registry.observed import ObservedReader
from tests.rolling_fixtures import write_chain
from tests.skip_gates import mount_absent, nothing_found

pytestmark = pytest.mark.data

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data"
_CANONICAL = _DATA_ROOT / "ohlc-full"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

# Dataset dirs a record may legitimately cite that do not resolve on the canonical data host. EMPTY at birth, growing only
# by a reviewed PR: an UNLISTED citation that does not resolve is a finding, so a fabricated citation either fails this
# suite or is itself a visible commit. The list names DIRS, not hosts — which is why the pass is gated on the data root's
# presence instead: adding a dataset here to appease a bare-checkout CI run would neuter the fence for that dataset forever.
_ABSENT_OK: frozenset[str] = frozenset()

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
    label: str
    dataset: str
    verdict: str
    detail: str


def conformance(cited: list[tuple[str, dict]], data_root: Path, absent_ok: frozenset[str]) -> list[Verdict]:
    """One verdict per `(label, dataset)` citation, over whatever pairs are handed in."""
    cache: dict = {}
    out: list[Verdict] = []
    for label, datasets in cited:
        for dataset, block in sorted(datasets.items()):
            directory = data_root / dataset
            if not directory.is_dir():
                listed = dataset in absent_ok
                out.append(
                    Verdict(
                        label,
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
                elif relpath.startswith("index/"):
                    try:
                        verify(directory, datetime.strptime(relpath, "index/%Y/%m/%d.json").date())
                    except RollingError as exc:
                        bad.append(f"{relpath}: {exc}")
            out.append(Verdict(label, dataset, FINDING if bad else REDERIVED, "; ".join(bad)))
    return out


def _cited(registry: Path = _REGISTRY) -> list[tuple[str, dict]]:
    cited = []
    for record in TrialRegistry(registry).records:
        if record.schema_version >= 4:
            cited.append((f"trial {record.trial_id}", record.datasets))
    return cited


def _hub_root() -> Path:
    return resolve_hot_source(load_config())


def test_every_schema_4_records_citations_still_rehash_against_this_hosts_data():
    # TWO gates, both required. Without the first, the first schema-4 record turns every bare-checkout
    # CI run permanently red; without the second the pass would be vacuous while it reads as covered.
    if not _CANONICAL.is_dir():
        pytest.skip("data/ohlc-full absent — the canonical-host marker; the disk pass runs only where the data root is")
    cited = _cited()
    if nothing_found(cited):
        pytest.skip("no schema-4 records yet — nothing in the registry cites observed bytes")

    verdicts = conformance(cited, _DATA_ROOT, _ABSENT_OK)
    findings = [v for v in verdicts if v.verdict == FINDING]
    assert not findings, _STOP + "\n" + "\n".join(f"  {v.label} / {v.dataset}: {v.detail}" for v in findings)


@pytest.mark.skipif(mount_absent("hot"), reason="hub mount absent — the hub pass reads hot/ where the NAS is mounted")
def test_the_hubs_hot_still_holds_every_byte_a_record_cites():
    findings = [v for v in conformance(_cited(), _hub_root(), frozenset()) if v.verdict == FINDING]
    assert not findings, "a set a record cites changed or left the hub's hot/:\n" + "\n".join(
        f"  {v.label} / {v.dataset}: {v.detail}" for v in findings
    )


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
        invocation={
            "subject": "conformance",
            "dataset": next(iter(datasets)),
            "window": None,
            "as_of": None,
            "accept_holes": False,
            "comparator_trial": None,
            "commit": "0" * 40,
        },
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

    cited = _cited(registry_path)
    assert [label for label, _ in cited] == ["trial 1", "trial 2", "trial 3", "trial 4", "trial 5"]

    seen = {v.dataset: v for v in conformance(cited, root, frozenset({"ds-elsewhere"}))}
    assert len(seen) == 5
    assert seen["ds-good"].verdict == REDERIVED
    assert seen["ds-elsewhere"].verdict == ABSENT_HERE
    assert seen["ds-invented"].verdict == FINDING
    assert "not an allowed absence" in seen["ds-invented"].detail
    assert seen["ds-drifted"].verdict == FINDING
    assert "sha256" in seen["ds-drifted"].detail
    assert seen["ds-partial"].verdict == FINDING
    assert seen["ds-partial"].detail == "ETH/EUR/1440.parquet: the named file is missing"
    assert seen["ds-partial"].label == "trial 5"

    with_committed_list = {v.dataset: v for v in conformance(cited, root, _ABSENT_OK)}
    assert with_committed_list["ds-elsewhere"].verdict == FINDING


def _citing_a_line(tmp_path: Path, name: str, relpath: str) -> tuple[Path, list[tuple[str, dict]]]:
    root, registry_path = tmp_path / name / "data", tmp_path / name / "registry.jsonl"
    write_chain(root / ROLLING_SET)
    digest = hashlib.sha256((root / ROLLING_SET / relpath).read_bytes()).hexdigest()
    span = ["2026-09-30 00:00:00+00:00", "2026-10-03 00:00:00+00:00"]
    _append(registry_path, {ROLLING_SET: {"files": {relpath: digest}, "rows": 4, "span": span}}, 1)
    return root, _cited(registry_path)


def _replace_a_byte(path: Path, at: int) -> None:
    data = bytearray(path.read_bytes())
    data[at] = ord("1") if data[at] == ord("0") else ord("0")
    path.write_bytes(bytes(data))


def test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding(tmp_path):
    root, cited = _citing_a_line(tmp_path, "line-changed", "index/2026/10/03.json")
    assert [v.verdict for v in conformance(cited, root, _ABSENT_OK)] == [REDERIVED]
    earlier_line = root / ROLLING_SET / "index/2026/10/01.json"
    _replace_a_byte(earlier_line, earlier_line.read_bytes().index(b'"prev":"') + len(b'"prev":"'))

    [verdict] = conformance(cited, root, _ABSENT_OK)

    assert verdict.verdict == FINDING
    assert "index/2026/10/02.json: its prev is not the sha256 of index/2026/10/01.json" in verdict.detail

    root, cited = _citing_a_line(tmp_path, "file-changed", "index/2026/10/03.json")
    assert [v.verdict for v in conformance(cited, root, _ABSENT_OK)] == [REDERIVED]
    earlier_file = root / ROLLING_SET / "days/BTC/EUR/2026/10/01.parquet"
    _replace_a_byte(earlier_file, earlier_file.stat().st_size // 2)

    [verdict] = conformance(cited, root, _ABSENT_OK)

    assert verdict.verdict == FINDING
    assert "days/BTC/EUR/2026/10/01.parquet does not hash to its listing" in verdict.detail


def test_the_hub_root_is_hot_under_the_configured_nfs_mount():
    assert _hub_root() == Path(load_config().nfs_mount_dir) / "hot"


def test_a_cited_file_whose_hub_copy_holds_other_bytes_is_rederived_on_the_node_and_a_finding_on_the_hub(tmp_path):
    node, hub, registry_path = tmp_path / "node", tmp_path / "hub", tmp_path / "registry.jsonl"
    _write(node, "ds-frozen", "BTC/EUR/1440.parquet", 10)
    _append(registry_path, _observed(node, "ds-frozen", ("BTC/EUR/1440.parquet",)), 1)
    _write(hub, "ds-frozen", "BTC/EUR/1440.parquet", 11)
    cited = _cited(registry_path)

    assert [(v.label, v.verdict) for v in conformance(cited, node, _ABSENT_OK)] == [("trial 1", REDERIVED)]
    [verdict] = conformance(cited, hub, frozenset())
    assert (verdict.label, verdict.dataset, verdict.verdict) == ("trial 1", "ds-frozen", FINDING)
    assert verdict.detail.startswith("BTC/EUR/1440.parquet: sha256 ")


def test_a_cited_line_whose_day_files_left_the_hub_is_a_finding_naming_the_absent_day_file(tmp_path):
    hub, cited = _citing_a_line(tmp_path, "hub", "index/2026/10/03.json")
    assert [v.verdict for v in conformance(cited, hub, frozenset())] == [REDERIVED]

    (hub / ROLLING_SET / "days").rename(tmp_path / "aside")

    [verdict] = conformance(cited, hub, frozenset())
    assert (verdict.label, verdict.dataset, verdict.verdict) == ("trial 1", ROLLING_SET, FINDING)
    assert verdict.detail == (
        "index/2026/10/03.json: index/2026/10/01.json: "
        f"days/BTC/EUR/2026/10/01.parquet is listed and absent from {hub / ROLLING_SET}"
    )
