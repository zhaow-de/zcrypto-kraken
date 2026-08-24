import subprocess
from pathlib import Path

import pytest

from cli.data.errors import DataSyncError
from cli.data.sync import fetch_hot, push_hot


def _mk(root: Path, rel: str, content: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_fetch_is_additive_and_idempotent(tmp_path):
    hot, data = tmp_path / "hot", tmp_path / "data"
    _mk(hot, "ohlc-full/BTC/EUR/1440.parquet", b"remote")
    r1 = fetch_hot(hot, data, verify=False)
    assert r1.new_files == ("ohlc-full/BTC/EUR/1440.parquet",)
    r2 = fetch_hot(hot, data, verify=False)
    assert r2.new_files == () and r2.skipped_existing == 1


def test_fetch_never_overwrites_a_changed_file(tmp_path):
    # The D1c contract: a content-changed remote file is structurally untransmittable.
    hot, data = tmp_path / "hot", tmp_path / "data"
    _mk(hot, "ohlc-full/x.parquet", b"remote-v2")
    local = _mk(data, "ohlc-full/x.parquet", b"local-v1")
    fetch_hot(hot, data, verify=False)
    assert local.read_bytes() == b"local-v1"


def test_fetch_missing_hot_dir_raises(tmp_path):
    with pytest.raises(DataSyncError, match="hot"):
        fetch_hot(tmp_path / "absent", tmp_path / "data", verify=False)


def test_push_only_allowlisted_sets_and_additive(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "ohlc-full/a.parquet", b"A")
    _mk(data, "engine-store/secret.parquet", b"NO")
    dest.mkdir()
    push_hot(data, ["ohlc-full"], str(dest) + "/")
    assert (dest / "ohlc-full/a.parquet").read_bytes() == b"A"
    assert not (dest / "engine-store").exists()


def test_push_refuses_missing_authored_set(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "dest").mkdir()
    with pytest.raises(DataSyncError, match="universe"):
        push_hot(tmp_path / "data", ["universe"], str(tmp_path / "dest") + "/")


def test_push_never_overwrites_dest(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "snapshots/s.json", b"local-new")
    kept = _mk(dest, "snapshots/s.json", b"dest-old")
    push_hot(data, ["snapshots"], str(dest) + "/")
    assert kept.read_bytes() == b"dest-old"


def test_push_extra_sets_pushes_minted_siblings(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "ohlc-full-20260718/a.parquet", b"A")
    dest.mkdir()
    push_hot(data, [], str(dest) + "/", extra_sets=["ohlc-full-20260718"])
    assert (dest / "ohlc-full-20260718/a.parquet").read_bytes() == b"A"


def test_a_stamped_set_is_published_via_extra_sets_beside_the_legacy_one(tmp_path):
    # The minted sibling reaches the hub under its own name; the legacy universe/ set is untouched.
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "universe-20260811/point-in-time-universe.json", b"new")
    kept = _mk(dest, "universe/point-in-time-universe.json", b"legacy")
    report = push_hot(data, [], str(dest) + "/", extra_sets=["universe-20260811"])
    assert report.new_files == ("universe-20260811/point-in-time-universe.json",)
    assert kept.read_bytes() == b"legacy"


def test_publishing_the_same_stamp_twice_creates_nothing_the_second_time(tmp_path):
    """Additive by construction: the second push's itemised output names no new files."""
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "universe-20260811/point-in-time-universe.json", b"v1")
    dest.mkdir()
    push_hot(data, [], str(dest) + "/", extra_sets=["universe-20260811"])
    report = push_hot(data, [], str(dest) + "/", extra_sets=["universe-20260811"])
    assert report.new_files == () and report.skipped_existing == 1


def test_a_new_stamp_never_modifies_a_previously_published_one(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "universe-20260811/point-in-time-universe.json", b"v1")
    dest.mkdir()
    push_hot(data, [], str(dest) + "/", extra_sets=["universe-20260811"])
    _mk(data, "universe-20260812/point-in-time-universe.json", b"v2")
    report = push_hot(data, [], str(dest) + "/", extra_sets=["universe-20260812"])
    # The itemised output names files under the NEW stamp only, and the old bytes are untouched.
    assert report.new_files and all(n.startswith("universe-20260812/") for n in report.new_files)
    assert (dest / "universe-20260811" / "point-in-time-universe.json").read_bytes() == b"v1"


def test_fetch_verifies_manifest_and_fails_on_corruption(tmp_path):
    import json

    import polars as pl

    from cli.ohlc.dataset import dataset_hash

    hot, data = tmp_path / "hot", tmp_path / "data"
    # REAL hot-set manifest shape: series is a NESTED dict (symbol -> grid -> {sha256, ...}), NOT a
    # list of {path, sha256}; the parquet lives at <symbol>/<grid>.parquet (funding: series[symbol]).
    good = pl.DataFrame({"ts": [1, 2], "close": [1.0, 2.0]})
    f = hot / "ohlc-test/BTC/EUR/1440.parquet"
    f.parent.mkdir(parents=True)
    good.write_parquet(f)
    (hot / "ohlc-test/manifest.json").write_text(
        json.dumps({"series": {"BTC/EUR": {"1440": {"rows": 2, "sha256": dataset_hash(good)}}}})
    )
    r = fetch_hot(hot, data)  # verify=True is the default
    assert "ohlc-test/BTC/EUR/1440.parquet" in r.new_files

    # A corrupted parquet: its content hash is attested by nothing in the manifest -> raises.
    bad = hot / "ohlc-bad/BTC/EUR/1440.parquet"
    bad.parent.mkdir(parents=True)
    pl.DataFrame({"ts": [9]}).write_parquet(bad)
    (hot / "ohlc-bad/manifest.json").write_text(json.dumps({"series": {"BTC/EUR": {"1440": {"sha256": "0" * 64}}}}))
    with pytest.raises(DataSyncError, match="not attested"):
        fetch_hot(hot, data)


def test_fetch_verifies_flat_funding_shape_manifest(tmp_path):
    # derivatives-funding manifest is FLAT: series[symbol] = {sha256, ...}, parquet at <symbol>/funding.parquet.
    import json

    import polars as pl

    from cli.ohlc.dataset import dataset_hash

    hot, data = tmp_path / "hot", tmp_path / "data"
    good = pl.DataFrame({"ts": [1, 2], "rate": [0.01, 0.02]})
    f = hot / "derivatives-funding/BTCUSDT/funding.parquet"
    f.parent.mkdir(parents=True)
    good.write_parquet(f)
    (hot / "derivatives-funding/manifest.json").write_text(
        json.dumps({"series": {"BTCUSDT": {"rows": 2, "sha256": dataset_hash(good)}}})
    )
    r = fetch_hot(hot, data)  # verify=True default
    assert "derivatives-funding/BTCUSDT/funding.parquet" in r.new_files


def test_fetch_refuses_a_parquet_set_whose_manifest_vouches_nothing(tmp_path):
    # Holdout-style manifest: metadata + a manifest-level manifest_sha256, but no per-parquet
    # sha256. This used to warn and continue -- which is how the real holdout went unverified.
    # It now fails closed: an unattested set is refused, never accepted quietly.
    import json

    import polars as pl

    hot, data = tmp_path / "hot", tmp_path / "data"
    f = hot / "ohlc-holdout/ADA/1440.parquet"
    f.parent.mkdir(parents=True)
    pl.DataFrame({"ts": [1]}).write_parquet(f)
    (hot / "ohlc-holdout/manifest.json").write_text(json.dumps({"series": {"ADA": {"rows": 1}}, "manifest_sha256": "a" * 64}))
    with pytest.raises(DataSyncError, match="attested by neither"):
        fetch_hot(hot, data)  # verify=True default
    # The escape is explicit rather than silent. Against a FRESH destination, because a fetch
    # verifies after rsync, so the refused bytes are already on disk in `data`.
    r = fetch_hot(hot, tmp_path / "data2", verify=False)
    assert "ohlc-holdout/ADA/1440.parquet" in r.new_files


def test_fetch_refuses_a_parquet_set_with_no_manifest_at_all(tmp_path):
    # A set shipping parquet with nothing attesting it is the same hole by another route.
    import polars as pl

    hot, data = tmp_path / "hot", tmp_path / "data"
    f = hot / "universe/u.parquet"
    f.parent.mkdir(parents=True)
    pl.DataFrame({"x": [1]}).write_parquet(f)
    with pytest.raises(DataSyncError, match="attested by neither"):
        fetch_hot(hot, data)  # verify=True default


def test_fetch_ignores_a_set_that_ships_no_parquet(tmp_path):
    # The TRUE POSITIVE for the refusal above: universe/snapshots ship JSON, never enter the
    # parquet loop, and must stay unaffected -- otherwise fail-closed would break every fetch.
    hot, data = tmp_path / "hot", tmp_path / "data"
    f = hot / "universe/selection.json"
    f.parent.mkdir(parents=True)
    f.write_text("{}")
    r = fetch_hot(hot, data)  # verify=True default -- must not raise
    assert "universe/selection.json" in r.new_files
