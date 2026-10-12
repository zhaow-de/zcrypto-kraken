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
