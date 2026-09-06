"""Segment retention on the capture hosts (spec 00050 D8 — closes T0032's retention half).

L2 book capture is unbackfillable and a capture host's disk is the only copy until the NAS pulls it,
so the load-bearing assertions here are the NEGATIVE ones. The unit under test is the shell script
the `capture` role installs, driven with `bash`: what deletes bytes on the host is that file."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "infra/ansible/roles/capture/files/zcrypto-capture-prune.sh"
DAY = 86400.0


def _seg(root: Path, name: str, *, age_days: float) -> Path:
    """Plant one file in a realistic segment dir and age it."""
    path = root / "BTC" / "EUR" / "book" / "2026" / "07" / "01" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"segment")
    aged = time.time() - age_days * DAY
    os.utime(path, (aged, aged))
    return path


def _prune(root: Path, days: str = "14") -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), str(root), days], capture_output=True, text=True, check=False)


def test_aged_finals_and_their_sidecars_are_deleted(tmp_path):
    final = _seg(tmp_path, "09.parquet", age_days=20)
    sidecar = _seg(tmp_path, "09.parquet.sha256", age_days=20)

    result = _prune(tmp_path)

    assert result.returncode == 0, result.stderr
    assert not final.exists()
    assert not sidecar.exists()
    assert "deleted=2" in result.stdout


def test_finals_inside_the_retention_window_are_spared(tmp_path):
    fresh = _seg(tmp_path, "09.parquet", age_days=0.5)
    fresh_sidecar = _seg(tmp_path, "09.parquet.sha256", age_days=0.5)
    # The boundary: one hour short of the cutoff is still inside the window and must survive.
    edge = _seg(tmp_path, "10.parquet", age_days=14 - 1 / 24)

    result = _prune(tmp_path)

    assert result.returncode == 0, result.stderr
    assert fresh.exists()
    assert fresh_sidecar.exists()
    assert edge.exists()
    assert "deleted=0" in result.stdout


def test_the_live_hour_quarantine_and_evidence_are_never_touched_at_any_age(tmp_path):
    # Aged FAR past the retention window: every one of these is unrecoverable if deleted.
    survivors = [
        _seg(tmp_path, "09.part0003.parquet", age_days=400),  # live hour, not yet merged
        _seg(tmp_path, "09.held0000.parquet", age_days=400),  # never-confirmed rows (quarantine)
        _seg(tmp_path, "09.parquet.corrupt", age_days=400),  # evidence of a read failure
        _seg(tmp_path, "09.parquet.corrupt.1", age_days=400),  # ...and its second quarantine
        _seg(tmp_path, "10.parquet.merging", age_days=400),  # merge interrupted before the rename
    ]
    doomed = _seg(tmp_path, "11.parquet", age_days=400)  # proves the sweep DID run over this dir

    result = _prune(tmp_path)

    assert result.returncode == 0, result.stderr
    assert not doomed.exists()
    assert [p for p in survivors if not p.exists()] == []


def test_a_nonsense_retention_deletes_nothing(tmp_path):
    final = _seg(tmp_path, "09.parquet", age_days=400)

    for bad in ("0", "-1", "abc", ""):
        result = _prune(tmp_path, bad)
        assert result.returncode == 2, f"retention {bad!r} was accepted: {result.stdout}"
        assert final.exists()


def test_a_missing_data_dir_is_an_error_not_a_silent_no_op(tmp_path):
    result = _prune(tmp_path / "nope")

    assert result.returncode == 2
    assert "not found" in result.stderr


@pytest.mark.parametrize("guarded", ["/", "/var", "/var/lib"])
def test_it_refuses_to_sweep_a_system_root(guarded):
    result = _prune(Path(guarded))

    assert result.returncode == 2
    assert "refusing" in result.stderr
