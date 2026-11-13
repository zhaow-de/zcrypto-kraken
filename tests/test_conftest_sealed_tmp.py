from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFTEST = ROOT / "tests" / "conftest.py"


def _sealing_test(outside: Path) -> str:
    return f"""\
import os


def test_seals_what_it_writes(tmp_path):
    (tmp_path / "gen-1" / "part").mkdir(parents=True)
    (tmp_path / "gen-1" / "part" / "rows").write_text("x")
    os.chmod(tmp_path / "gen-1" / "part", 0o555)
    os.chmod(tmp_path / "gen-1", 0o555)
    (tmp_path / "closed").mkdir()
    os.chmod(tmp_path / "closed", 0o000)
    (tmp_path / "no-search").mkdir()
    (tmp_path / "no-search" / "rows").write_text("x")
    os.chmod(tmp_path / "no-search", 0o600)
    os.symlink({str(outside)!r}, tmp_path / "link-to-outside")
"""


@pytest.mark.parametrize("workers", [["-p", "no:xdist"], ["-n", "2"]], ids=["serial", "xdist"])
def test_a_session_leaves_no_sealed_directory_under_its_basetemp_and_a_linked_one_keeps_its_mode(tmp_path, workers):
    tree = tmp_path / "tree"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests" / "conftest.py").write_text(CONFTEST.read_text())
    outside = tmp_path / "outside-sealed"
    (outside / "inner").mkdir(parents=True)
    (tree / "tests" / "test_seal.py").write_text(_sealing_test(outside))
    basetemp = tmp_path / "basetemp"
    outside.chmod(0o555)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *workers, "--rootdir", str(tree)]
            + ["--basetemp", str(basetemp), "tests/test_seal.py"],
            cwd=tree,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        sealed = [
            Path(top) / name
            for top, dirs, _ in os.walk(basetemp)
            for name in dirs
            if not (Path(top) / name).is_symlink() and stat.S_IMODE((Path(top) / name).stat().st_mode) & 0o700 != 0o700
        ]
        assert sealed == []
        assert any(p.name == "no-search" for p in basetemp.rglob("no-search")), "the sealing test ran under this basetemp"
        assert stat.S_IMODE(outside.stat().st_mode) == 0o555 and (outside / "inner").is_dir()
    finally:
        outside.chmod(0o755)
