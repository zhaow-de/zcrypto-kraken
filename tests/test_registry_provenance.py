import json
from pathlib import Path

import pytest

from cli.registry.errors import RegistryError
from cli.registry.provenance import ALLOWLIST, capture_datasets

_NESTED = {
    "BTC/EUR": {
        "1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
        "240": {"rows": 60, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64},
    },
    "ETH/EUR": {
        "1440": {"rows": 7, "first_ts": "2020-01-04T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "e" * 64},
        "240": {"rows": 42, "first_ts": "2020-01-04T00:00:00+00:00", "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "f" * 64},
    },
}


def _write(root: Path, name: str, payload: dict) -> None:
    (root / name).mkdir(parents=True, exist_ok=True)
    (root / name / "manifest.json").write_text(json.dumps(payload))


def _full(root: Path) -> None:
    _write(
        root,
        "ohlc-full",
        {"basket_sha256": "a" * 64, "fetched_at": "2020-01-11T00:00:00+00:00", "source": "/machine/local/path", "series": _NESTED},
    )


def test_backfill_shape_captures_the_declared_slice(tmp_path):
    _full(tmp_path)
    got = capture_datasets({"ohlc-full": {"intervals": ["1440"], "pairs": ["BTC/EUR"]}}, tmp_path)["ohlc-full"]
    assert got["select"] == {"intervals": ["1440"], "pairs": ["BTC/EUR"]}
    assert got["set_digest"] == "a" * 64
    assert got["extent"] == {"series": 1, "rows": 10, "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]}
    assert "source" not in got and "fetched_at" not in got  # D2: no per-run, no machine-local values


def test_each_axis_is_independently_selectable_and_empty_means_all(tmp_path):
    _full(tmp_path)
    whole = capture_datasets({"ohlc-full": {}}, tmp_path)["ohlc-full"]["extent"]
    assert whole == {"series": 4, "rows": 119, "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T20:00:00+00:00"]}
    by_pair = capture_datasets({"ohlc-full": {"pairs": ["ETH/EUR"]}}, tmp_path)["ohlc-full"]["extent"]
    assert by_pair["series"] == 2 and by_pair["rows"] == 49
    by_interval = capture_datasets({"ohlc-full": {"intervals": ["240"]}}, tmp_path)["ohlc-full"]["extent"]
    assert by_interval["series"] == 2 and by_interval["rows"] == 102


def test_holdout_shape_uses_manifest_sha256_and_a_single_asset_axis(tmp_path):
    # No basket_sha256, no per-series sha256, series NOT nested by interval.
    _write(
        tmp_path,
        "ohlc-holdout-2026-07-10",
        {
            "manifest_sha256": "b" * 64,
            "pulled_at": "2026-07-10T01:30Z",
            "freeze_last_complete_day": "2026-07-09",
            "series": {
                "ADA": {
                    "rows": 5,
                    "first_ts": "2018-09-28 00:00:00+00:00",
                    "last_ts": "2026-07-09 00:00:00+00:00",
                    "overlap_bars_verified": 3,
                    "appended": 1,
                },
                "BTC": {
                    "rows": 9,
                    "first_ts": "2013-09-10 00:00:00+00:00",
                    "last_ts": "2026-07-09 00:00:00+00:00",
                    "overlap_bars_verified": 3,
                    "appended": 1,
                },
            },
        },
    )
    name = "ohlc-holdout-2026-07-10"
    got = capture_datasets({name: {"assets": ["ADA"]}}, tmp_path)[name]
    assert got["set_digest"] == "b" * 64
    assert got["extent"] == {"series": 1, "rows": 5, "span": ["2018-09-28 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]}
    with pytest.raises(RegistryError, match="intervals"):  # not an axis of this adapter
        capture_datasets({name: {"intervals": ["1440"]}}, tmp_path)


def test_select_is_resolved_so_order_duplicates_and_abbreviation_cannot_move_the_digest(tmp_path):
    _full(tmp_path)
    a = capture_datasets({"ohlc-full": {"intervals": ["240", "1440", "240"]}}, tmp_path)
    b = capture_datasets({"ohlc-full": {"intervals": ["1440", "240"]}}, tmp_path)
    # D2: an absent axis is RESOLVED to its full membership, not stored blank -- so the block states
    # which pairs were read without the manifest, and the abbreviation hashes as the slice it means.
    assert a == b
    assert a["ohlc-full"]["select"] == {"intervals": ["1440", "240"], "pairs": ["BTC/EUR", "ETH/EUR"]}
    assert capture_datasets({"ohlc-full": {}}, tmp_path) == a


def test_an_unlisted_dataset_is_refused_and_the_message_names_the_remedy(tmp_path):
    _write(tmp_path, "derivatives-funding", {"basket_sha256": "e" * 64, "fetched_at": "x", "series": {}})
    with pytest.raises(RegistryError, match="adapter"):
        capture_datasets({"derivatives-funding": {}}, tmp_path)


def test_an_absent_manifest_is_refused_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-full/manifest\.json"):
        capture_datasets({"ohlc-full": {}}, tmp_path)


@pytest.mark.parametrize("bad", [{"intervals": ["60"]}, {"pairs": ["DOGE/EUR"]}, {"grids": ["1440"]}])
def test_an_unresolvable_select_token_or_axis_is_refused(tmp_path, bad):
    _full(tmp_path)
    with pytest.raises(RegistryError):
        capture_datasets({"ohlc-full": bad}, tmp_path)


def test_an_empty_datasets_mapping_is_refused(tmp_path):
    with pytest.raises(RegistryError, match="no dataset"):
        capture_datasets({}, tmp_path)


def test_a_changed_series_shape_is_a_registry_error_not_a_traceback(tmp_path):
    """`ohlc-reach` already writes `series` as a list[dict]; a supported writer could too."""
    _write(tmp_path, "ohlc-full", {"basket_sha256": "a" * 64, "fetched_at": "x", "series": [{"symbol": "BTC/EUR", "rows": 10}]})
    with pytest.raises(RegistryError, match="series"):
        capture_datasets({"ohlc-full": {}}, tmp_path)


_DATA = Path(__file__).resolve().parent.parent / "data"

# Measured from this repo's data root 2026-08-08. Same "canonical dataset drifted -- STOP" contract as
# tests/test_crossfreq_system.py::EXTENT: a revision mints a sibling, so these never move in place.
_PINS = {
    "ohlc-full": {"series": 36, "rows": 1052322, "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T23:00:00+00:00"]},
    "ohlc-15m": {"series": 12, "rows": 3122044, "span": ["2013-09-10T23:45:00+00:00", "2026-03-31T23:45:00+00:00"]},
    "ohlc-holdout-2026-07-10": {"series": 10, "rows": 30032, "span": ["2013-09-10 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]},
}


def _listed(name: str) -> bool:
    return any(name == k or name.startswith(k + "-") for k in ALLOWLIST)


def test_every_allowlisted_dataset_on_disk_captures_and_every_other_is_refused():
    manifests = sorted(_DATA.glob("*/manifest.json"))
    if not manifests:
        pytest.skip("no dataset manifests on this host (the data root is gitignored)")
    captured = 0
    for manifest in manifests:
        name = manifest.parent.name
        if _listed(name):
            block = capture_datasets({name: {}}, _DATA)[name]
            assert block["extent"]["rows"] > 0 and len(block["set_digest"]) == 64
            captured += 1
        else:
            with pytest.raises(RegistryError, match="adapter"):
                capture_datasets({name: {}}, _DATA)
    assert captured, f"no allowlisted dataset among {[m.parent.name for m in manifests]}"


@pytest.mark.parametrize("name", sorted(_PINS))
def test_a_frozen_canonical_extent_matches_its_measured_pin(name):
    if not (_DATA / name / "manifest.json").is_file():
        pytest.skip(f"{name} absent on this host (the data root is gitignored)")
    assert capture_datasets({name: {}}, _DATA)[name]["extent"] == _PINS[name], (
        f"canonical dataset drifted — STOP: {name}'s whole-set extent moved. These sets are frozen; a "
        f"revision mints a sibling dir. Investigate before updating this pin."
    )
