from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def test_error_string_past_the_default_schema_inference_window_round_trips(tmp_path):
    """`pl.DataFrame` infers a column's dtype from only its first 100 rows by default. `error` is the
    only nullable field: >100 leading `error=None` rows followed by a real error string previously blew
    up `pl.DataFrame([...])` with a `ComputeError` — the ~6,000-row snapshot rewritten whole on every
    flush is always past that window, so this broke on precisely the nights an error was found."""
    base = datetime(2026, 8, 1, tzinfo=UTC)
    healthy = [_row(pair="BTC/EUR", hour=base + timedelta(hours=i)) for i in range(150)]
    failing = _row(pair="ETH/EUR", error="EIO", replay_ok=False)
    save_checkpoint(tmp_path, [*healthy, failing])
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None and len(loaded) == 151
    assert loaded[("ETH/EUR", failing.hour)] == failing


def test_mkdir_failure_raises_checkpoint_write_error_not_the_raw_oserror(tmp_path):
    """A distinct failure shape from `test_unwritable_dir_raises_checkpoint_write_error` above: there,
    `state_dir` already exists (chmod 0o500 read+execute), so `mkdir(exist_ok=True)` succeeds and only
    the write fails. Here `state_dir` does not exist yet and its parent is wholly inaccessible (chmod
    000 — the ":rw mount present but inaccessible" shape) so `mkdir` itself fails. That failure must
    still surface as `CheckpointWriteError`, not an unwrapped `PermissionError` escaping from the
    cleanup path's own `tmp.unlink()` call (which cannot even stat under an inaccessible parent)."""
    parent = tmp_path / "locked"
    parent.mkdir()
    parent.chmod(0o000)
    state = parent / "nested" / "state"
    try:
        with pytest.raises(CheckpointWriteError):
            save_checkpoint(state, [_row()])
    finally:
        parent.chmod(0o700)


def test_empty_rows_is_a_noop(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    save_checkpoint(tmp_path, [])  # a no-op run must not clobber the good checkpoint
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None and len(loaded) == 1

    absent = tmp_path / "never-created"
    save_checkpoint(absent, [])  # nor conjure one where none existed
    assert not absent.exists()


def test_naive_hour_and_verified_at_are_rejected(tmp_path):
    naive_hour = datetime(2026, 8, 1, 3)  # no tzinfo
    with pytest.raises(ValueError, match="hour"):
        save_checkpoint(tmp_path, [_row(hour=naive_hour)])

    naive_verified_at = datetime(2026, 8, 1, 4)  # no tzinfo
    with pytest.raises(ValueError, match="verified_at"):
        save_checkpoint(tmp_path, [_row(verified_at=naive_verified_at)])
