import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_a_tmp_path_lands_under_the_checkouts_tmp(tmp_path: Path):
    assert REPO / ".tmp" in tmp_path.resolve().parents, tmp_path


def test_a_mkdtemp_lands_under_the_checkouts_tmp():
    made = Path(tempfile.mkdtemp())
    try:
        assert REPO / ".tmp" in made.resolve().parents, made
    finally:
        made.rmdir()


def test_a_tmp_path_is_outside_any_repository_for_git(tmp_path: Path):
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0, r.stdout


def test_a_childs_tmpdir_is_the_checkouts_tmp():
    assert Path(os.environ["TMPDIR"]).resolve() == (REPO / ".tmp").resolve()
