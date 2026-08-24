"""CLI tests for the `zcrypto data` sub-app (spec 00056): CliRunner with a real zcrypto.toml written
into a chdir'd tmp_path, so `load_config()`'s default relative path resolves it -- no monkeypatching
of `load_config` itself, matching the fetch/push commands' own resolution."""

from pathlib import Path

from typer.testing import CliRunner

from cli.__main__ import app

runner = CliRunner()


def _write_config(tmp_path: Path, *, nfs_mount_dir: Path, push_dest: str, authored_sets: list[str]) -> None:
    (tmp_path / "zcrypto.toml").write_text(
        f'[zcrypto]\ndata_dir = "{tmp_path / "data"}"\nnfs_mount_dir = "{nfs_mount_dir}"\n\n'
        f'[zcrypto.data]\npush_dest = "{push_dest}"\n'
        f"authored_sets = {authored_sets!r}\n"
    )


def test_fetch_happy_path_exits_zero(tmp_path, monkeypatch):
    # fetch source derives as nfs_mount_dir/hot, so the mount root is the hot dir's parent.
    # The set ships a REAL parquet and a manifest attesting it, because verification now fails
    # closed: an unattested parquet set is refused, so a placeholder byte string would exit 1 and
    # this test would be asserting the wrong thing about the CLI.
    import json

    import polars as pl

    from cli.ohlc.dataset import dataset_hash

    frame = pl.DataFrame({"ts": [1, 2], "close": [1.0, 2.0]})
    src = tmp_path / "hot" / "ohlc-full"
    src.mkdir(parents=True)
    frame.write_parquet(src / "a.parquet")
    (src / "manifest.json").write_text(json.dumps({"series": {"A": {"sha256": dataset_hash(frame)}}}))
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest="nas-hot:", authored_sets=["ohlc-full"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "fetch"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "data" / "ohlc-full" / "a.parquet").is_file()


def test_fetch_missing_hot_source_exits_nonzero(tmp_path, monkeypatch):
    # nfs_mount_dir/hot does not exist under an absent mount root.
    _write_config(tmp_path, nfs_mount_dir=tmp_path / "absent", push_dest="nas-hot:", authored_sets=[])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "fetch"])
    assert result.exit_code == 1


def test_push_respects_the_allowlist(tmp_path, monkeypatch):
    # Non-parquet payload on purpose: this pins WHICH SETS the CLI pushes. A parquet would also
    # engage the attestation check (push fails closed on an unattested set), conflating the two.
    data_dir = tmp_path / "data"
    (data_dir / "ohlc-full").mkdir(parents=True)
    (data_dir / "ohlc-full" / "a.json").write_bytes(b"A")
    (data_dir / "engine-store").mkdir(parents=True)
    (data_dir / "engine-store" / "secret.parquet").write_bytes(b"NO")
    dest = tmp_path / "dest"
    dest.mkdir()
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest=str(dest) + "/", authored_sets=["ohlc-full"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "push"])
    assert result.exit_code == 0
    assert (dest / "ohlc-full" / "a.json").read_bytes() == b"A"
    assert not (dest / "engine-store").exists()


def test_rebuild_mints_sibling_no_push(tmp_path, monkeypatch):
    from cli.data import rebuild as rebuild_module

    monkeypatch.setitem(rebuild_module.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "ok").write_text("x"))
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest="nas-hot:", authored_sets=["ohlc-full"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "rebuild", "ohlc-full", "--no-push"])
    assert result.exit_code == 0
    minted = [p for p in (tmp_path / "data").iterdir() if p.name.startswith("ohlc-full-")]
    assert len(minted) == 1
    assert (minted[0] / "ok").exists()


def test_rebuild_pushes_minted_sibling_by_default(tmp_path, monkeypatch):
    from cli.data import rebuild as rebuild_module

    monkeypatch.setitem(rebuild_module.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "ok").write_text("x"))
    dest = tmp_path / "dest"
    dest.mkdir()
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest=str(dest) + "/", authored_sets=[])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "rebuild", "ohlc-full"])
    assert result.exit_code == 0
    minted = [p for p in (tmp_path / "data").iterdir() if p.name.startswith("ohlc-full-")]
    assert (dest / minted[0].name / "ok").exists()


def test_rebuild_unknown_set_exits_nonzero(tmp_path, monkeypatch):
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest="nas-hot:", authored_sets=[])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "rebuild", "not-a-set", "--no-push"])
    assert result.exit_code == 1
