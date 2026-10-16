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


def _pre_reviewed(root: Path, base: str) -> tuple[Path, str]:
    row = {"kind": "pre-review", "range": f"main..{base}", "tip": base, "ts": "t"}
    (root.parent / "reads" / "ledger.jsonl").write_text(json.dumps(row) + "\n")
    return root, base


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "reads").mkdir()
    _git(root, "init", "-q", "-b", "main")
    return _pre_reviewed(root, _commit(root, {"a.py": A_PY, "notes.md": NOTES, "b.py": "VALUE = 1\n"}, "base"))


def _fold(repo: tuple[Path, str], files: dict[str, str | None], rows: list[dict] = ROWS, range_: str | None = None):
    root, base = repo
    tip = _commit(root, files, "fold")
    (root.parent / "rows.json").write_text(json.dumps(rows))
    args = [str(root.parent / "rows.json"), "--range", range_ or f"{base[:9]}..{tip}", "--report-dir", str(root.parent / "reads")]
    done = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, env=ENV, capture_output=True, text=True)
    return done, tip


def _ledger(repo: tuple[Path, str]) -> Path:
    return repo[0].parent / "reads" / "ledger.jsonl"


def _rows(repo: tuple[Path, str]) -> list[dict]:
    return [json.loads(line) for line in _ledger(repo).read_text().splitlines()] if _ledger(repo).exists() else []


def test_a_fold_of_the_ship_texts_alone_passes_and_appends_its_row(repo):
    done, tip = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES})
    assert done.returncode == 0, done.stdout + done.stderr
    [_, row] = _rows(repo)
    assert {k: row[k] for k in ("kind", "range", "tip")} == {"kind": "fold-check", "range": f"{repo[1]}..{tip}", "tip": tip}
    assert "passed" in done.stdout and done.stderr == ""


def test_a_range_named_by_revisions_is_recorded_by_its_ids(repo):
    done, tip = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES}, range_="HEAD~1..HEAD")
    assert done.returncode == 0, done.stdout + done.stderr
    row = _rows(repo)[-1]
    assert (row["range"], row["tip"]) == (f"{repo[1]}..{tip}", tip)


def _refused(done: subprocess.CompletedProcess, repo, *says: str, kinds: tuple[str, ...] = ("pre-review",)) -> None:
    assert done.returncode == 1, done.stdout + done.stderr
    for said in says:
        assert said in done.stdout, (said, done.stdout)
    assert [row["kind"] for row in _rows(repo)] == list(kinds), "a failing fold writes nothing"


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


def test_a_byte_that_makes_the_file_binary_is_refused(repo):
    done, _ = _fold(repo, {"a.py": FOLDED_A.replace("return 1", "return 1\x00"), "notes.md": FOLDED_NOTES})
    _refused(done, repo, "a.py: a binary change, which no ship text carries")


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


@pytest.mark.parametrize(
    ("files", "rows", "says"),
    [
        (
            {
                "a.py": FOLDED_A.replace("    # The code below\n    # says the rest.\n", "").replace(
                    "    return 1\n", "    # The code below\n    # says the rest.\n"
                ),
                "notes.md": FOLDED_NOTES,
            },
            ROWS,
            ("a.py:5 [trim]: its text does not stand where its line at", "a.py:9: added at"),
        ),
        (
            {"notes.md": NOTES.replace("The second paragraph has a wrong claim in it.\n", "")},
            [
                {
                    "site": "notes.md:5",
                    "survives": "fix",
                    "correct": False,
                    "duplicateOf": "",
                    "ship": "The fourth paragraph stands too.",
                }
            ],
            ("notes.md:5 [fix]: its text does not stand where its line at",),
        ),
        (
            {"notes.md": NOTES.replace("The fourth paragraph stands too.", "The first paragraph stands as it is.")},
            [
                {
                    "site": "notes.md:3",
                    "survives": "trim",
                    "correct": True,
                    "duplicateOf": "",
                    "ship": "The first paragraph stands as it is.",
                }
            ],
            ("notes.md:9: added at",),
        ),
    ],
    ids=["replacing a line no row names", "standing elsewhere already", "added again away from the site it keeps"],
)
def test_a_ship_text_away_from_its_site_is_refused(repo, files, rows, says):
    done, _ = _fold(repo, files, rows)
    _refused(done, repo, *says)


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
    assert [row["kind"] for row in _rows(repo)] == ["pre-review"]


def test_a_report_dir_that_does_not_exist_is_refused(repo):
    root, base = repo
    tip = _commit(root, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES}, "fold")
    (root.parent / "rows.json").write_text(json.dumps(ROWS))
    args = [str(root.parent / "rows.json"), "--range", f"{base}..{tip}", "--report-dir", str(root.parent / "nowhere")]
    done = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, env=ENV, capture_output=True, text=True)
    assert done.returncode == 2 and "is not a directory" in done.stderr, done


GUARD_PY = 'def f(x):\n    # The comment the pre-review cut.\n    if x < 0:\n        raise ValueError("refused")\n    return x\n'
SH = "#!/bin/sh\n# The comment the pre-review cut.\n\nset -eu\necho hi\n"
JS = "// The comment the pre-review cut.\nconst limit = 3\nconst t = `one\n\ntwo`\n"


def _cut(site: str) -> list[dict]:
    return [{"site": site, "survives": "cut", "correct": True, "duplicateOf": "", "ship": ""}]


@pytest.mark.parametrize(
    ("base", "fold", "rows", "says"),
    [
        (
            {"g.py": GUARD_PY},
            {"g.py": "def f(x):\n    return x\n"},
            _cut("g.py:2"),
            ("g.py:3: deleted at", "g.py:4: deleted at", 'raise ValueError("refused")'),
        ),
        (
            {"g.py": GUARD_PY},
            {"g.py": "def f(x):\n    # The new comment.\n    return x\n"},
            [{"site": "g.py:2", "survives": "fix", "correct": False, "duplicateOf": "", "ship": "# The new comment."}],
            ("g.py:3: deleted at", "if x < 0:"),
        ),
        ({"s.py": 'MSG = """\n# Not a comment.\n"""\n'}, {"s.py": 'MSG = """\n"""\n'}, _cut("s.py:2"), ("s.py:2: deleted at",)),
        ({"s.sh": SH}, {"s.sh": "#!/bin/sh\necho hi\n"}, _cut("s.sh:2"), ("s.sh:4: deleted at", "set -eu")),
        ({"s.sh": SH}, {"s.sh": "\nset -eu\necho hi\n"}, _cut("s.sh:2"), ("s.sh:1: deleted at", "#!/bin/sh")),
        ({"c.yml": "# The comment.\nkey: value\n"}, {"c.yml": ""}, _cut("c.yml:1"), ("c.yml:2: deleted at", "key: value")),
        ({"j.js": JS}, {"j.js": "const t = `one\n\ntwo`\n"}, _cut("j.js:1"), ("j.js:2: deleted at", "const limit = 3")),
        ({"j.js": JS}, {"j.js": JS.replace("one\n\ntwo", "one\ntwo")}, _cut("j.js:4"), ("j.js:4: deleted at",)),
    ],
    ids=[
        "a guard cut beside a comment",
        "a guard dropped beneath a fix",
        "a line of a string that is no docstring",
        "a shell command beside a comment",
        "the #! line",
        "a YAML key",
        "a JS statement",
        "a blank line inside a JS template",
    ],
)
def test_a_fold_that_deletes_a_line_of_code_is_refused(repo, base, fold, rows, says):
    done, _ = _fold(_pre_reviewed(repo[0], _commit(repo[0], base, "base")), fold, rows)
    _refused(done, repo, *says)


@pytest.mark.parametrize(
    ("base", "fold", "rows"),
    [
        (
            {"d.py": 'def f():\n    """One line.\n\n    A paragraph the pre-review cut.\n    """\n    return 1\n'},
            {"d.py": 'def f():\n    """One line.\n    """\n    return 1\n'},
            _cut("d.py:4"),
        ),
        ({"s.sh": SH}, {"s.sh": "#!/bin/sh\nset -eu\necho hi\n"}, _cut("s.sh:2")),
        ({"c.yml": "a: 1\n# The comment.\nb: 2\n"}, {"c.yml": "a: 1\nb: 2\n"}, _cut("c.yml:2")),
        ({"j.js": "/* A block\n   the pre-review cut. */\n\nconst a = 1\n"}, {"j.js": "const a = 1\n"}, _cut("j.js:1")),
    ],
    ids=["a docstring paragraph", "a shell comment", "a YAML comment", "a JS block comment"],
)
def test_a_fold_that_deletes_prose_alone_passes(repo, base, fold, rows):
    done, _ = _fold(_pre_reviewed(repo[0], _commit(repo[0], base, "base")), fold, rows)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize(
    ("ledger", "admitted"),
    [
        (None, False),
        ([], False),
        ([("review", 40)], False),
        ([("pre-review", 5)], False),
        ([("pre-review", "fedcba9876543210")], False),
        ([("pre-review", 7)], True),
        ([("review", 40), ("pre-review", 9)], True),
    ],
    ids=[
        "no ledger",
        "an empty ledger",
        "a review row at the base",
        "a tip of five digits",
        "a pre-review at another tip",
        "a seven-digit prefix",
        "a short tip beside a review row",
    ],
)
def test_a_fold_is_checked_only_beside_a_pre_review_row_at_its_base(repo, ledger, admitted):
    base = repo[1]
    if ledger is None:
        _ledger(repo).unlink()
    else:
        rows = [
            {"kind": kind, "range": f"main..{base}", "tip": base[:tip] if isinstance(tip, int) else tip} for kind, tip in ledger
        ]
        _ledger(repo).write_text("".join(json.dumps(row) + "\n" for row in rows))
    done, _ = _fold(repo, {"a.py": FOLDED_A, "notes.md": FOLDED_NOTES})
    kinds = tuple(kind for kind, _ in ledger or [])
    if admitted:
        assert done.returncode == 0, done.stdout + done.stderr
        assert [row["kind"] for row in _rows(repo)] == [*kinds, "fold-check"]
    else:
        _refused(done, repo, "holds no pre-review row at", kinds=kinds)
