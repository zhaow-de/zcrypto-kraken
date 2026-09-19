"""CLI tests for the `zcrypto data` sub-app (spec 00056): CliRunner with a real zcrypto.toml written
into a chdir'd tmp_path, so `load_config()`'s default relative path resolves it -- no monkeypatching
of `load_config` itself, matching the fetch/push commands' own resolution."""

import functools
import importlib
import logging
from pathlib import Path

import pytest
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


@pytest.fixture
def zcrypto_log(caplog):
    """The CLI's first invocation in a process stops the "zcrypto" logger propagating, so a test selected alone
    captures nothing unless the handler sits on that logger -- `_zcrypto_caplog_attached` in
    `tests/test_engine_metrics.py:1163` is the same remedy and states the mechanism."""
    logger = logging.getLogger("zcrypto")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="zcrypto"):
            yield caplog
    finally:
        logger.removeHandler(caplog.handler)


_BUILDER_REFUSALS = [
    "cli.backfill.errors.BackfillError",
    "cli.costs.errors.CostModelError",
    "cli.data.errors.DataSyncError",
    "cli.data.manifest.ManifestError",
    "cli.derivatives.errors.DerivativesError",
    "cli.ohlc.errors.OHLCError",
    "cli.snapshot.errors.SnapshotError",
    "cli.universe.errors.UniverseError",
]


@pytest.mark.parametrize("dotted", _BUILDER_REFUSALS)
def test_rebuild_turns_a_builders_own_refusal_into_an_abort_not_a_traceback(tmp_path, monkeypatch, zcrypto_log, dotted):
    """The exit code cannot tell the two apart -- an uncaught exception also exits 1 -- so the exception is read."""
    from cli.data import rebuild as rebuild_module

    module, _, name = dotted.rpartition(".")
    refusal = getattr(importlib.import_module(module), name)

    def _refuse(ctx, out):
        raise refusal("the builder said why")

    monkeypatch.setitem(rebuild_module.REBUILDABLE, "ohlc-full", _refuse)
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest="nas-hot:", authored_sets=["ohlc-full"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "rebuild", "ohlc-full", "--no-push"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "the builder said why" in zcrypto_log.text


def test_rebuild_lets_an_error_no_builder_raises_on_purpose_through(tmp_path, monkeypatch):
    from cli.data import rebuild as rebuild_module

    def _break(ctx, out):
        raise RuntimeError("a bug, not a refusal")

    monkeypatch.setitem(rebuild_module.REBUILDABLE, "ohlc-full", _break)
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest="nas-hot:", authored_sets=["ohlc-full"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "rebuild", "ohlc-full", "--no-push"])

    assert isinstance(result.exception, RuntimeError)


def test_rebuild_ohlc_reach_aborts_naming_a_canonical_file_it_cannot_join(tmp_path, monkeypatch, zcrypto_log):
    import polars as pl

    from cli.data import rebuild as rebuild_module
    from cli.ohlc.dataset import to_frame, write_parquet
    from cli.ohlc.reach import reach_round

    def _must_not_fetch(pair_key, interval):
        raise AssertionError("the canonical frame was refused too late")

    path = tmp_path / "data" / "ohlc-full" / "BTC" / "EUR" / "60.parquet"
    rows = [[1_767_225_600 + 3600 * i, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(8)]
    write_parquet(to_frame(rows).with_columns(pl.col("ts").dt.cast_time_unit("ns")), path)
    monkeypatch.setattr(rebuild_module, "reach_round", functools.partial(reach_round, fetch_fn=_must_not_fetch))
    _write_config(tmp_path, nfs_mount_dir=tmp_path, push_dest="nas-hot:", authored_sets=["ohlc-full"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["data", "rebuild", "ohlc-reach", "--no-push"])

    assert isinstance(result.exception, SystemExit)
    assert str(path) in zcrypto_log.text
    assert [p.name for p in (tmp_path / "data").iterdir()] == ["ohlc-full"]
