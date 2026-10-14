"""The four pre-schema-4 hashes (spec 00086 D6 as amended by spec 00130 D6)."""

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.data

_ROOT = Path(__file__).resolve().parents[1]
_PINS = _ROOT / "docs" / "reference" / "legacy-dataset-pins.jsonl"
_REGISTRY = _ROOT / "docs" / "reference" / "trial-registry.jsonl"
_MANIFEST_15M = _ROOT / "data" / "ohlc-15m" / "manifest.json"
_OHLC_FULL = _ROOT / "data" / "ohlc-full"
_LEGACY_ASSETS = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")


def _rows():
    return [json.loads(l) for l in _PINS.read_text().splitlines()]


def _legacy_manifest(interval: int) -> str:
    """The recovered trial44_write.py's manifest(interval) (git show 74080b69e:docs/reference/trial43-recovered-runners/trial44_write.py), transcribed: a weak digest, not every byte."""
    from cli.ohlc.dataset import read_parquet

    parts = []
    for asset in _LEGACY_ASSETS:
        frame = read_parquet(_OHLC_FULL / asset / "EUR" / f"{interval}.parquet")
        parts.append(f"{asset}:{len(frame)}:{frame['ts'][0]}:{frame['ts'][-1]}:{frame['close'][0]}:{frame['close'][-1]}")
    return "|".join(sorted(parts))


def test_exactly_the_four_known_hashes_with_registry_true_trial_ids():
    rows = {r["hash"][:8]: r for r in _rows()}
    assert set(rows) == {"ba47e37e", "81dc9b44", "45275ebe", "cccb8d17"}
    recs = [json.loads(l) for l in _REGISTRY.read_text().splitlines()]
    for row in rows.values():
        cited = sorted(r["trial_id"] for r in recs if r["dataset_hash"] == row["hash"])
        assert row["trial_ids"] == cited, f"{row['hash'][:8]}: pins say {row['trial_ids']}, registry says {cited}"


def test_the_reproduced_recipe_executes_from_its_own_literals():
    row = next(r for r in _rows() if "operand_4h" in r["evidence"])
    h4, h15 = row["evidence"]["operand_4h"], row["evidence"]["operand_15m"]
    assert hashlib.sha256(f"{h4}:{h15}".encode()).hexdigest() == row["hash"]


def test_epistemics_live_in_the_referent_value():
    for row in _rows():
        if row["confidence"] == "unrecoverable":
            assert row["referent"] is None
        elif row["confidence"] == "inferred":
            assert "INFERRED" in row["referent"] and "never recomputed" in row["referent"]
        else:  # reproduced: each qualifier the row's evidence carries is read in its referent
            assert "REPRODUCED" in row["referent"] and "weak digest" in row["referent"]
            if "operand_4h" in row["evidence"]:
                assert row["evidence"]["operand_4h"][:8] in row["referent"]
            if {33, 35} & set(row["trial_ids"]):  # P1 runs from scratchpad drivers: what they read is not established
                assert "scope_mismatch" in row["evidence"] and "not established" in row["referent"]


def test_every_confidence_is_one_of_the_three_ruled_grades():
    assert all(r["confidence"] in ("reproduced", "inferred", "unrecoverable") for r in _rows())


def test_the_reproduced_15m_operand_is_the_manifest_basket_on_disk():
    if not _MANIFEST_15M.exists():
        pytest.skip("data/ohlc-15m/manifest.json absent — off-workstation; the 15m byte anchor is data-gated")
    row = next(r for r in _rows() if "operand_4h" in r["evidence"])
    # `basket_sha256` became `set_sha256` under the manifest contract (spec 00099), with the same
    # value for this set: ohlc-15m is single-interval, so path order and the legacy string-sorted
    # interval order coincide, and the byte anchor this row pins holds under either key.
    from cli.data.manifest import ManifestError, read_manifest

    try:
        basket = read_manifest(_MANIFEST_15M).identity_digest
    except ManifestError:
        basket = json.loads(_MANIFEST_15M.read_text())["basket_sha256"]
    assert row["evidence"]["operand_15m"] == basket


@pytest.mark.parametrize(
    ("prefix", "intervals"),
    [("81dc9b44", (240,)), ("ba47e37e", (1440,)), ("45275ebe", (1440, 240))],
)
def test_the_legacy_digest_recomputes_from_the_files_it_names(prefix, intervals):
    if not _OHLC_FULL.is_dir():
        pytest.skip("data/ohlc-full absent — the legacy digests recompute on the data host only")
    row = next(r for r in _rows() if r["hash"].startswith(prefix))
    text = "||".join(_legacy_manifest(i) for i in intervals)
    assert hashlib.sha256(text.encode()).hexdigest() == row["hash"]
    assert row["confidence"] == "reproduced" and row["evidence"]["recipe_intervals"] == list(intervals)
