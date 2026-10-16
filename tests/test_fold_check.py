from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "fold-check.py"
# The diff algorithm decides where a hunk falls, so no global or system git config reaches these repositories.
ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

A_PY = """import os


def main():
    # The old comment says what the code below
    # already says, at some length, and then
    # it says it again.
    return os.getcwd()


def other():
    return 1
"""
NOTES = """# Notes

The first paragraph stands as it is.

The second paragraph has a wrong claim in it.

The third paragraph says nothing a reader acts on.

The fourth paragraph stands too.
"""
ROWS = [
    {"site": "a.py:5", "survives": "trim", "correct": True, "duplicateOf": "", "ship": "# The code below\n# says the rest."},
    {
        "site": "notes.md:5",
        "survives": "fix",
        "correct": False,
        "duplicateOf": "",
        "ship": "The second paragraph has a true claim in it.",
    },
    {"site": "notes.md:7", "survives": "cut", "correct": True, "duplicateOf": "", "ship": ""},
    {"site": "notes.md:3", "survives": "keep", "correct": True, "duplicateOf": "", "ship": "a reader needs it to find the fourth"},
]
FOLDED_A = A_PY.replace(
    "    # The old comment says what the code below\n    # already says, at some length, and then\n    # it says it again.\n",
    "    # The code below\n    # says the rest.\n",
)
FOLDED_NOTES = NOTES.replace("a wrong claim", "a true claim").replace("The third paragraph says nothing a reader acts on.\n\n", "")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args], env=ENV, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _commit(repo: Path, files: dict[str, str | None], message: str) -> str:
    for name, text in files.items():
        if text is None:
            (repo / name).unlink()
        else:
            (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "reads").mkdir()
    _git(root, "init", "-q", "-b", "main")
    return root, _commit(root, {"a.py": A_PY, "notes.md": NOTES, "b.py": "VALUE = 1\n"}, "base")


def _fold(repo: tuple[Path, str], files: dict[str, str | None], rows: list[dict] = ROWS, range_: str | None = None):
    root, base = repo
    tip = _commit(root, files, "fold")
    (root.parent / "rows.json").write_text(json.dumps(rows))
    args = [str(root.parent / "rows.json"), "--range", range_ or f"{base[:9]}..{tip}", "--report-dir", str(root.parent / "reads")]
    done = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, env=ENV, capture_output=True, text=True)
    return done, tip


def _ledger(repo: tuple[Path, str]) -> Path:
    return repo[0].parent / "reads" / "ledger.jsonl"


def test_a_fold_of_the_ship_texts_alone_passes_and_appends_its_row(repo):
    done, tip = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES})
    assert done.returncode == 0, done.stdout + done.stderr
    [row] = [json.loads(line) for line in _ledger(repo).read_text().splitlines()]
    assert {k: row[k] for k in ("kind", "range", "tip")} == {"kind": "fold-check", "range": f"{repo[1][:9]}..{tip}", "tip": tip}
    assert "passed" in done.stdout and done.stderr == ""


def test_a_tip_named_by_a_revision_is_recorded_by_its_id(repo):
    done, tip = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES}, range_="HEAD~1..HEAD")
    assert done.returncode == 0, done.stdout + done.stderr
    row = json.loads(_ledger(repo).read_text())
    assert (row["range"], row["tip"]) == ("HEAD~1..HEAD", tip)


def _refused(done: subprocess.CompletedProcess, repo, *says: str) -> None:
    assert done.returncode == 1, done.stdout + done.stderr
    for said in says:
        assert said in done.stdout, (said, done.stdout)
    assert not _ledger(repo).exists(), "a failing fold writes nothing"


@pytest.mark.parametrize(
    "a_py", [FOLDED_A.replace("says the rest", "says the whole rest"), A_PY], ids=["altered by one word", "not folded"]
)
def test_a_ship_text_not_verbatim_at_the_tip_is_refused(repo, a_py):
    done, _ = _fold(repo, {"a.py": a_py, "notes.md": FOLDED_NOTES})
    _refused(done, repo, "a.py:5 [trim]: its text is not verbatim in a.py")


def test_a_line_added_beside_the_ship_texts_is_refused(repo):
    added = FOLDED_A.replace("    # says the rest.\n", "    # says the rest.\n    # Never call it twice.\n")
    done, _ = _fold(repo, {"a.py": added, "notes.md": FOLDED_NOTES})
    _refused(done, repo, "a.py:7: added at", "Never call it twice.")


def test_a_changed_file_no_row_names_is_refused(repo):
    done, _ = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES, "b.py": "VALUE = 2\n"})
    _refused(done, repo, "b.py: changed by the range, named by no trim, fix or cut row")


def test_a_mode_change_beside_the_ship_texts_is_refused(repo):
    (repo[0] / "a.py").chmod(0o755)
    done, _ = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES})
    _refused(done, repo, "a.py: a mode change, which no ship text carries")


def test_a_file_deleted_by_a_cut_is_refused(repo):
    rows = [{"site": "b.py:1", "survives": "cut", "correct": True, "duplicateOf": "", "ship": ""}]
    done, _ = _fold(repo, {"b.py": None}, rows)
    _refused(done, repo, "b.py: the file is deleted, which no ship text carries")


@pytest.mark.parametrize(
    ("notes", "ship", "says"),
    [
        (FOLDED_NOTES, "The third paragraph says nothing a reader acts on.", "notes.md:7 [cut]: a cut ships nothing"),
        (NOTES.replace("a wrong claim", "a true claim"), "", "notes.md:7 [cut]: the cut is not made"),
        (FOLDED_NOTES.replace("The fourth", "A line the cut left.\n\nThe fourth"), "", "notes.md:7: added at"),
    ],
    ids=["a cut carrying text", "a cut not made", "a line added by the cut"],
)
def test_a_cut_row_licenses_no_text(repo, notes, ship, says):
    rows = [dict(row, ship=ship) if row["survives"] == "cut" else row for row in ROWS]
    done, _ = _fold(repo, {"a.py": FOLDED_A, "notes.md": notes}, rows)
    _refused(done, repo, says)


def test_an_old_site_kept_beside_its_ship_text_is_refused(repo):
    kept = A_PY.replace("    # The old comment", "    # The code below\n    # says the rest.\n    # The old comment")
    done, _ = _fold(repo, {"a.py": kept, "notes.md": FOLDED_NOTES})
    _refused(done, repo, "a.py:5 [trim]: its line at", "outside its text")


def test_a_deletion_away_from_every_row_is_refused(repo):
    done, _ = _fold(repo, {"a.py": FOLDED_A.replace("    return 1\n", ""), "notes.md": FOLDED_NOTES})
    _refused(done, repo, "a.py: the hunk at", "touches no row's site or text")


def test_a_paragraph_dropped_past_a_blank_line_touches_the_text_it_follows(repo):
    # git deletes the second paragraph with the blank line after it, so the hunk opens below the blank line the
    # unchanged first paragraph keeps.
    rows = [
        {
            "site": "notes.md:3",
            "survives": "trim",
            "correct": True,
            "duplicateOf": "",
            "ship": "The first paragraph stands as it is.",
        }
    ]
    done, _ = _fold(repo, {"notes.md": NOTES.replace("The second paragraph has a wrong claim in it.\n\n", "")}, rows)
    assert done.returncode == 0, done.stdout + done.stderr


def test_rows_read_at_another_tip_are_refused(repo):
    rows = [dict(row, site="notes.md:70") if row["survives"] == "cut" else row for row in ROWS]
    done, _ = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES}, rows)
    _refused(done, repo, "notes.md:70 [cut]: notes.md has 9 lines at")


def test_a_range_that_changes_nothing_is_refused(repo):
    done, _ = _fold(repo, {})
    _refused(done, repo, "the range changes no file")


@pytest.mark.parametrize(
    ("rows", "range_"),
    [
        ({"prose": ROWS}, None),
        ([{"site": "a.py:5", "survives": "trim"}], None),
        ([{"site": "a.py:5", "survives": "shorten", "ship": "x"}], None),
        ([{"site": "a.py", "survives": "cut", "ship": ""}], None),
        (ROWS, "HEAD~1...HEAD"),
        (ROWS, "nowhere..HEAD"),
        (ROWS, "HEAD..HEAD~1"),
    ],
    ids=[
        "not an array",
        "no ship",
        "an unknown survives",
        "a site with no line",
        "three dots",
        "no such revision",
        "base after tip",
    ],
)
def test_usage_and_git_refusals_exit_2_and_write_nothing(repo, rows, range_):
    done, _ = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES}, rows, range_)
    assert done.returncode == 2 and done.stderr, done
    assert not _ledger(repo).exists()


def test_a_report_dir_that_does_not_exist_is_refused(repo):
    root, base = repo
    tip = _commit(root, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES}, "fold")
    (root.parent / "rows.json").write_text(json.dumps(ROWS))
    args = [str(root.parent / "rows.json"), "--range", f"{base}..{tip}", "--report-dir", str(root.parent / "nowhere")]
    done = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, env=ENV, capture_output=True, text=True)
    assert done.returncode == 2 and "is not a directory" in done.stderr, done
