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


def test_per_series_legacy_evidence_survives_conversion(tmp_path):
    """Reach records its seam evidence PER ROW, so conversion must carry every row across."""
    root = tmp_path / "ohlc-reachlike"
    frames = {"ADA/EUR/1440.parquet": to_frame(_rows(5)), "ADA/EUR/60.detached.parquet": to_frame(_rows(3))}
    for relpath, frame in frames.items():
        write_parquet(frame, root / relpath)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "built_at": "2026-08-13T03:00:00+00:00",
                "min_seam_overlap": 600,
                "series": [
                    {
                        "symbol": "ADA",
                        "interval": 1440,
                        "status": "continuous",
                        "sha256": dataset_hash(frames["ADA/EUR/1440.parquet"]),
                        "rest_first": "2026-08-01T00:00:00+00:00",
                        "rest_last": "2026-08-13T00:00:00+00:00",
                        "overlap_bars": 607,
                        "gap_bars": 0,
                        "appended": 113,
                    },
                    {
                        "symbol": "ADA",
                        "interval": 60,
                        "status": "detached",
                        "sha256": dataset_hash(frames["ADA/EUR/60.detached.parquet"]),
                        "rest_first": "2026-08-01T00:00:00+00:00",
                        "rest_last": "2026-08-13T00:00:00+00:00",
                        "overlap_bars": 0,
                        "gap_bars": 42,
                        "appended": 3,
                    },
                ],
            }
        )
    )

    convert_dataset(root, apply=True)

    rows = read_manifest(root / "manifest.json").provenance["legacy"]["series"]
    assert len(rows) == 2, "the per-series legacy rows must survive, not just the top-level keys"
    cont = next(r for r in rows if r["status"] == "continuous")
    # These seam fields describe a REST window that expires: once dropped they are recoverable from nothing.
    assert cont["rest_first"] == "2026-08-01T00:00:00+00:00"
    assert cont["rest_last"] == "2026-08-13T00:00:00+00:00"
    assert cont["overlap_bars"] == 607 and cont["gap_bars"] == 0 and cont["appended"] == 113


def test_legacy_fields_the_contract_does_not_name_are_preserved_verbatim(tmp_path):
    # Each set's original fetched_at is a freeze moment nothing else records.
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    convert_dataset(root, apply=True)
    legacy = read_manifest(root / "manifest.json").provenance["legacy"]
    assert legacy["fetched_at"] == "2026-07-01T00:00:00+00:00"
    assert legacy["source"] == "/machine/local"


def test_a_legacy_manifest_attesting_nothing_is_refused_rather_than_vouched_blind(tmp_path):
    """Refusing is the only honest option when a legacy manifest attests no content hash at all:
    there is nothing to prove the conversion against."""
    root = tmp_path / "ohlc-thing"
    write_parquet(to_frame(_rows(5)), root / "ADA/EUR/1440.parquet")
    (root / "manifest.json").write_text(json.dumps({"fetched_at": "2026-07-01T00:00:00+00:00", "series": {"ADA": {"rows": 5}}}))
    with pytest.raises(ManifestError, match="attests no content hash at all"):
        convert_dataset(root, apply=True)


def test_the_v0_dataset_hash_spelling_still_proves_the_conversion(tmp_path):
    # v0 wrote its content hash under `dataset_hash`, so a `sha256`-only walk sees nothing to prove against.
    root = tmp_path / "ohlc"
    frame = to_frame(_rows(5))
    write_parquet(frame, root / "ADA/1440.parquet")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "fetched_at": "2026-07-01T00:00:00+00:00",
                "series": [{"symbol": "ADA", "interval": 1440, "dataset_hash": dataset_hash(frame)}],
            }
        )
    )
    convert_dataset(root, apply=True)
    assert read_manifest(root / "manifest.json").series["ADA/1440.parquet"]["sha256"] == dataset_hash(frame)

    root2 = tmp_path / "ohlc2"
    write_parquet(to_frame(_rows(5)), root2 / "ADA/1440.parquet")
    (root2 / "manifest.json").write_text(
        json.dumps(
            {
                "fetched_at": "2026-07-01T00:00:00+00:00",
                "series": [{"symbol": "ADA", "interval": 1440, "dataset_hash": "a" * 64}],
            }
        )
    )
    with pytest.raises(ManifestError, match="no longer hash to what the legacy manifest attested"):
        convert_dataset(root2, apply=True)


def test_an_already_conformant_set_is_left_alone(tmp_path):
    root = tmp_path / "ohlc-thing"
    _legacy_set(root)
    convert_dataset(root, apply=True)
    again = convert_dataset(root, apply=True)
    assert again["status"] == "already conformant"
