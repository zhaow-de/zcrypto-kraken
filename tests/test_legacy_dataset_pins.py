"""The four pre-schema-4 hashes: ruled 2026-08-09 — documented, never repaired (spec 00086 D6)."""

import hashlib
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PINS = _ROOT / "docs" / "reference" / "legacy-dataset-pins.jsonl"
_REGISTRY = _ROOT / "docs" / "reference" / "trial-registry.jsonl"
_MANIFEST_15M = _ROOT / "data" / "ohlc-15m" / "manifest.json"


def _rows():
    return [json.loads(l) for l in _PINS.read_text().splitlines()]


def test_exactly_the_four_known_hashes_with_registry_true_trial_ids():
    rows = {r["hash"][:8]: r for r in _rows()}
    assert set(rows) == {"ba47e37e", "81dc9b44", "45275ebe", "cccb8d17"}
    recs = [json.loads(l) for l in _REGISTRY.read_text().splitlines()]
    for row in rows.values():
        cited = sorted(r["trial_id"] for r in recs if r["dataset_hash"] == row["hash"])
        assert row["trial_ids"] == cited, f"{row['hash'][:8]}: pins say {row['trial_ids']}, registry says {cited}"


def test_the_reproduced_recipe_executes_from_its_own_literals():
    row = next(r for r in _rows() if r["confidence"] == "reproduced")
    h4, h15 = row["evidence"]["operand_4h"], row["evidence"]["operand_15m"]
    assert hashlib.sha256(f"{h4}:{h15}".encode()).hexdigest() == row["hash"]


def test_epistemics_live_in_the_referent_value():
    for row in _rows():
        if row["confidence"] == "unrecoverable":
            assert row["referent"] is None
        elif row["confidence"] == "inferred":
            assert "INFERRED" in row["referent"] and "never recomputed" in row["referent"]
        else:  # reproduced — the row a careless reader trusts most needs the qualifier most
            assert "unrecoverable" in row["referent"]


def test_every_confidence_is_one_of_the_three_ruled_grades():
    """Deliberately narrow, and named for what it can prove. Whether a row claims more than the
    measured evidence supports is a judgement no assertion makes -- it is carried by the sibling
    tests that re-derive the recipe and cross-check trial_ids against the registry, and by review."""
    assert all(r["confidence"] in ("reproduced", "inferred", "unrecoverable") for r in _rows())


def test_the_reproduced_15m_operand_is_the_manifest_basket_on_disk():
    if not _MANIFEST_15M.exists():
        pytest.skip("data/ohlc-15m/manifest.json absent — off-workstation; the 15m byte anchor is data-gated")
    row = next(r for r in _rows() if r["confidence"] == "reproduced")
    # `basket_sha256` became `set_sha256` under the manifest contract (spec 00099). The VALUE is
    # unchanged for this set: ohlc-15m is single-interval, so ordering by path and by the legacy
    # string-sorted interval key coincide -- the byte anchor this row pins still holds.
    from cli.data.manifest import ManifestError, read_manifest

    try:
        basket = read_manifest(_MANIFEST_15M).identity_digest
    except ManifestError:
        basket = json.loads(_MANIFEST_15M.read_text())["basket_sha256"]
    assert row["evidence"]["operand_15m"] == basket
