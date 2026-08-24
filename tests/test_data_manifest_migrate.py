"""The converter: rewrite the manifest, never the data (spec 00099)."""

import hashlib
import json

import pytest

from cli.data.manifest import ManifestError, convert_dataset, read_manifest
from cli.ohlc.dataset import dataset_hash, to_frame, write_parquet


def _rows(n, start=1577836800):
    return [[start + i * 86400, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def _legacy_set(root, *, series_keys_are_bases=False, detached=False):
    """A legacy-shaped dataset. `series_keys_are_bases` reproduces the hub's reach set, whose keys
    cannot yield a path -- the case that forces the converter to walk the tree."""
    frames = {"ADA/EUR/1440.parquet": to_frame(_rows(5)), "BTC/EUR/1440.parquet": to_frame(_rows(7))}
    if detached:
        frames["ADA/EUR/60.detached.parquet"] = to_frame(_rows(3))
    for relpath, frame in frames.items():
        write_parquet(frame, root / relpath)
    legacy_series = {}
    for relpath, frame in frames.items():
        key = relpath.split("/")[0] if series_keys_are_bases else relpath
        legacy_series[key] = {"rows": frame.height, "sha256": dataset_hash(frame)}
    (root / "manifest.json").write_text(
        json.dumps({"fetched_at": "2026-07-01T00:00:00+00:00", "source": "/machine/local", "series": legacy_series})
    )
    return frames


def _tree_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*.parquet"))}


def test_conversion_rewrites_the_manifest_and_touches_no_parquet_byte(tmp_path):
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    before = _tree_hashes(root)

    result = convert_dataset(root, apply=True)

    assert result["status"] == "converted"
    assert _tree_hashes(root) == before, "the converter must rewrite the manifest, never the data"
    m = read_manifest(root / "manifest.json")
    assert set(m.series) == {"ADA/EUR/1440.parquet", "BTC/EUR/1440.parquet"}
    assert m.identity_digest == m.set_sha256


def test_relative_paths_come_from_the_tree_not_from_the_legacy_keys(tmp_path):
    # The hub's reach set keys `ADA` against `ADA/EUR/1440.parquet`. A converter that trusted keys
    # could not convert the sets that most need converting.
    root = tmp_path / "ohlc-reachlike"
    _legacy_set(root, series_keys_are_bases=True)
    convert_dataset(root, apply=True)
    assert set(read_manifest(root / "manifest.json").series) == {"ADA/EUR/1440.parquet", "BTC/EUR/1440.parquet"}


def test_a_dry_run_changes_nothing_on_disk(tmp_path):
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    before = (root / "manifest.json").read_text()
    result = convert_dataset(root)
    assert result["status"] == "would convert"
    assert (root / "manifest.json").read_text() == before


def test_content_drift_refuses_the_whole_conversion(tmp_path):
    # Without this the converter re-vouches whatever is on disk, and a re-ordered digest could no
    # longer be claimed to describe identical content.
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    write_parquet(to_frame(_rows(99)), root / "ADA/EUR/1440.parquet")  # content moved since the freeze
    with pytest.raises(ManifestError, match="no longer hash to what the legacy manifest attested"):
        convert_dataset(root, apply=True)
    assert json.loads((root / "manifest.json").read_text()).get("schema_version") is None, "refused, so unchanged"


def test_a_detached_set_declares_both_subsets_and_names_continuous_as_its_identity(tmp_path):
    root = tmp_path / "ohlc-reach-x"
    _legacy_set(root, detached=True)
    convert_dataset(root, apply=True)
    m = read_manifest(root / "manifest.json")
    assert set(m.subset_sha256) == {"continuous", "detached"}
    assert m.identity == "subset:continuous"
    assert m.identity_digest == m.subset_sha256["continuous"] != m.set_sha256


def test_legacy_fields_the_contract_does_not_name_are_preserved_verbatim(tmp_path):
    # Reach's seam evidence was computed against a REST window that has since expired, and each
    # set's original fetched_at is a freeze moment nothing else records.
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    convert_dataset(root, apply=True)
    legacy = read_manifest(root / "manifest.json").provenance["legacy"]
    assert legacy["fetched_at"] == "2026-07-01T00:00:00+00:00"
    assert legacy["source"] == "/machine/local"


def test_an_already_conformant_set_is_left_alone(tmp_path):
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    convert_dataset(root, apply=True)
    again = convert_dataset(root, apply=True)
    assert again["status"] == "already conformant"
