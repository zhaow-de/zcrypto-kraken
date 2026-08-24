"""Every manifest this repo writes conforms; the ones it does not write are named (spec 00099).

Two assertions with different reach, deliberately separated:

  * the WRITERS conform -- CI-runnable, because it drives them into a tmp tree;
  * the manifests ON DISK conform -- data-gated, because CI has no datasets.

The second is gated on a workstation MARKER rather than on `data/` existing: `data/` exists in a
fresh checkout (it carries its own `.gitignore`), so a directory-existence gate would redden every
PR, and a test that reddens every PR gets deleted -- which is worse than no test.
"""

import json
from pathlib import Path

import pytest

from cli.data.manifest import ManifestError, read_manifest

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_MARKER = _DATA / "ohlc-full" / "manifest.json"  # present only on a workstation with datasets
_SIDECAR = _ROOT / "docs" / "reference" / "vouched-dataset-hashes.jsonl"

# Sets this repo does not write, so the contract does not bind them. Named rather than skipped, so
# the list cannot quietly grow: an out-of-contract set must be attested somewhere else instead.
_OUT_OF_CONTRACT = ("ohlc-holdout-",)

# The floor: these must be conformant once migrated. A committed floor is what stops the exception
# list from absorbing a set that simply failed to convert.
_MUST_CONFORM = ("ohlc-full", "ohlc-15m", "derivatives-funding")


def _on_disk():
    return sorted(_DATA.glob("*/manifest.json"))


@pytest.mark.skipif(not _MARKER.is_file(), reason="no local datasets (CI); the writers are covered separately")
def test_every_manifest_on_disk_either_conforms_or_is_a_named_out_of_contract_set():
    found = _on_disk()
    assert found, "the marker exists, so datasets exist — an empty glob here is a broken test, not a clean bill"
    legacy = []
    for path in found:
        name = path.parent.name
        if name.startswith(_OUT_OF_CONTRACT):
            # Out of contract, so it must be attested by the committed sidecar instead.
            assert f'"{name}"' in _SIDECAR.read_text(), f"{name} is out of contract AND unattested"
            continue
        try:
            read_manifest(path)
        except ManifestError:
            legacy.append(name)
    assert not legacy, f"legacy manifests remain: {legacy} — run `zcrypto data migrate-manifests --apply`"


@pytest.mark.skipif(not _MARKER.is_file(), reason="no local datasets (CI)")
@pytest.mark.parametrize("name", _MUST_CONFORM)
def test_the_committed_floor_of_sets_is_conformant(name):
    path = _DATA / name / "manifest.json"
    if not path.is_file():
        pytest.skip(f"{name} not present on this node")
    m = read_manifest(path)
    assert m.identity_digest and m.vouched
    assert all(k.endswith(".parquet") for k in m.series)


def test_the_out_of_contract_list_names_only_sets_this_repo_does_not_write():
    # CI-runnable. The holdout freeze is produced by a process that has never lived in this repo;
    # anything else appearing here would be a set we DO write and simply failed to convert.
    assert _OUT_OF_CONTRACT == ("ohlc-holdout-",)
    assert not any(Path(p).name.startswith("holdout") for p in _ROOT.glob("cli/**/*.py"))
