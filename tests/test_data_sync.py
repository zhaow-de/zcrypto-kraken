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


def test_fetch_verifies_manifest_and_fails_on_corruption(tmp_path):
    import json

    import polars as pl

    from cli.ohlc.dataset import dataset_hash

    hot, data = tmp_path / "hot", tmp_path / "data"
    f = hot / "ohlc-test/BTC/EUR/1440.parquet"
    f.parent.mkdir(parents=True)
    good = pl.DataFrame({"ts": [1, 2], "close": [1.0, 2.0]})
    good.write_parquet(f)
    manifest = {"series": [{"path": "BTC/EUR/1440.parquet", "sha256": dataset_hash(good)}]}
    (hot / "ohlc-test/manifest.json").write_text(json.dumps(manifest))
    r = fetch_hot(hot, data)  # verify=True is the default
    assert "ohlc-test/BTC/EUR/1440.parquet" in r.new_files

    bad = hot / "ohlc-bad/x.parquet"
    bad.parent.mkdir(parents=True)
    pl.DataFrame({"ts": [9]}).write_parquet(bad)
    (hot / "ohlc-bad/manifest.json").write_text(json.dumps({"series": [{"path": "x.parquet", "sha256": "0" * 64}]}))
    with pytest.raises(DataSyncError, match="manifest"):
        fetch_hot(hot, data)
