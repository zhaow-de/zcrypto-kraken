from __future__ import annotations

import polars as pl
import pytest

from cli.archive.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointRow,
    CheckpointWriteError,
    load_checkpoint,
    save_checkpoint,
)


def _row(pair="BTC/EUR", hour=None, **kw):
    from datetime import UTC, datetime

    base = dict(
        pair=pair,
        hour=hour or datetime(2026, 8, 1, 3, tzinfo=UTC),
        byte_hash="ab" * 32,
        verifier_version=1,
        opens_with_snapshot=True,
        ts_ordered=True,
        checksum_present=True,
        replay_ok=True,
        error=None,
        rows=10,
        messages=3,
        polars_version=pl.__version__,
        depth=10,
        verified_at=datetime(2026, 8, 1, 4, tzinfo=UTC),
    )
    base.update(kw)
    return CheckpointRow(**base)


def test_round_trip_preserves_every_field(tmp_path):
    rows = [_row(), _row(pair="ETH/EUR", error="EIO", replay_ok=False)]
    save_checkpoint(tmp_path, rows)
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None and len(loaded) == 2
    assert loaded[("BTC/EUR", rows[0].hour)] == rows[0]
    assert loaded[("ETH/EUR", rows[1].hour)] == rows[1]  # error survives as a string, None stays None


def test_absent_state_dir_loads_none(tmp_path):
    assert load_checkpoint(tmp_path / "never-created") is None


def test_corrupt_file_loads_none_not_raise(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    (tmp_path / "checkpoint.parquet").write_bytes(b"not parquet")
    assert load_checkpoint(tmp_path) is None


def test_wrong_schema_version_loads_none(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    frame = pl.read_parquet(tmp_path / "checkpoint.parquet")
    frame = frame.with_columns(pl.lit(CHECKPOINT_SCHEMA_VERSION + 1).alias("schema_version"))
    frame.write_parquet(tmp_path / "checkpoint.parquet")
    assert load_checkpoint(tmp_path) is None


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    save_checkpoint(tmp_path, [_row(), _row(pair="ETH/EUR")])
    assert [p.name for p in tmp_path.iterdir()] == ["checkpoint.parquet"]


def test_failed_write_never_corrupts_the_final_or_leaves_a_tmp_file(tmp_path, monkeypatch):
    """`test_save_is_atomic_no_tmp_left_behind` (above) passes even against a save_checkpoint that
    writes straight to `checkpoint.parquet` with no `.tmp` involved at all — two successful calls in a
    row leave no `.tmp` litter either way, so it never actually exercises the tmp+replace idiom. This
    test forces the SECOND save to fail after real bytes have already landed on disk (a torn write —
    ENOSPC, EIO, a killed process) and checks the property that idiom actually buys: the previously
    published checkpoint must survive a failed write untouched, and no `.tmp` may be left behind.

    Against a direct-write implementation, `write_parquet` targets `checkpoint.parquet` itself, so the
    injected failure overwrites the prior good content before raising — this test then fails on the
    final-content assertion, where the un-strengthened version above would not have caught it.
    """
    good = _row()
    save_checkpoint(tmp_path, [good])

    orig_write_parquet = pl.DataFrame.write_parquet

    def _torn_write(self, path, *a, **kw):
        orig_write_parquet(self, path, *a, **kw)  # real bytes land on disk...
        raise OSError("ENOSPC (simulated)")  # ...then the write is interrupted

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _torn_write)
    with pytest.raises(CheckpointWriteError):
        save_checkpoint(tmp_path, [_row(pair="ETH/EUR")])
    monkeypatch.undo()

    assert [p.name for p in tmp_path.iterdir()] == ["checkpoint.parquet"]  # no `.tmp` litter
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None and loaded[("BTC/EUR", good.hour)] == good  # final untouched


def test_unwritable_dir_raises_checkpoint_write_error(tmp_path):
    state = tmp_path / "ro"
    state.mkdir()
    state.chmod(0o500)
    try:
        with pytest.raises(CheckpointWriteError):
            save_checkpoint(state, [_row()])
    finally:
        state.chmod(0o700)
