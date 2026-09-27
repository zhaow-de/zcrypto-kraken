from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "review-ledger.py"
TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def _ledger(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def _git(repo: Path, *args: str, when: str = "2026-09-01T00:00:00Z") -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_AUTHOR_DATE": when}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_COMMITTER_DATE": when}
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _commit(repo: Path, text: str, message: str, when: str = "2026-09-01T00:00:00Z") -> str:
    (repo / "a.txt").write_text(text)
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", message, when=when)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, "zero\n", "base")
    return root


def _branch(repo: Path, *commits: tuple[str, str], when: str) -> str:
    """Rebuilt from `base` on every call, so a second call re-dates, re-trees or re-words the same branch."""
    _git(repo, "checkout", "-q", "--detach", "main")
    tip = ""
    for text, message in commits:
        tip = _commit(repo, text, message, when)
    return tip


def _read(report_dir: Path, tip: str, repo: Path) -> list[dict]:
    done = _ledger("read", str(report_dir), "--tip", tip, "--repo", str(repo))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_append_creates_the_ledger_and_appends_one_row_per_call(tmp_path: Path):
    for kind, tip in (("pre-review", "abcdef0"), ("review", "abcdef0123")):
        done = _ledger("append", str(tmp_path), "--kind", kind, "--range", "develop..abcdef0", "--tip", tip)
        assert done.returncode == 0 and done.stdout == "" and done.stderr == "", done
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [list(row) for row in rows] == [["kind", "range", "tip", "ts"]] * 2
    assert [(r["kind"], r["range"], r["tip"]) for r in rows] == [
        ("pre-review", "develop..abcdef0", "abcdef0"),
        ("review", "develop..abcdef0", "abcdef0123"),
    ]
    assert all(TS.match(r["ts"]) for r in rows), rows


def test_append_starts_its_row_on_a_line_of_its_own(tmp_path: Path):
    (tmp_path / "ledger.jsonl").write_text('{"kind":"task","label":"t1","range":"develop..abcdef0"}')
    assert _ledger("append", str(tmp_path), "--kind", "pre-review", "--range", "a..b", "--tip", "abcdef0").returncode == 0
    assert [json.loads(line)["kind"] for line in (tmp_path / "ledger.jsonl").read_text().splitlines()] == ["task", "pre-review"]


@pytest.mark.parametrize(
    "bad",
    [
        ["--kind", "task", "--range", "a..b", "--tip", "abcdef0"],
        ["--kind", "review", "--range", "a...b", "--tip", "abcdef0"],
        ["--kind", "review", "--range", "ab", "--tip", "abcdef0"],
        ["--kind", "review", "--range", "a..b", "--tip", "HEAD"],
        ["--kind", "review", "--range", "a..b", "--tip", "abcde"],
        ["--kind", "pre-review", "--range", "a..b", "--tip", "abcdef0", "--refutation", "f.md", "--report", "r.md"],
        ["--kind", "review", "--range", "a..b", "--tip", "abcdef0", "--report", "r.md"],
    ],
)
def test_append_refuses_what_is_not_a_row_and_writes_nothing(tmp_path: Path, bad: list[str]):
    (tmp_path / "f.md").write_text("## Refutation\n")
    done = _ledger("append", str(tmp_path), *bad)
    assert done.returncode != 0 and done.stderr, done
    assert not (tmp_path / "ledger.jsonl").exists()


def test_append_refuses_a_report_dir_that_does_not_exist(tmp_path: Path):
    done = _ledger("append", str(tmp_path / "nowhere"), "--kind", "review", "--range", "a..b", "--tip", "abcdef0")
    assert done.returncode == 1 and "not a directory" in done.stderr


def test_a_review_s_refutation_follows_each_report_after_a_blank_line(tmp_path: Path):
    block = "## Refutation\n\n| # | severity | site | verdict |\n| --- | --- | --- | --- |\n| 1 | Important | `a.py:1` | REFUTED — `x` \\| y |\n"
    (tmp_path / "refutation.md").write_text(block)
    (tmp_path / "behaviour.md").write_text("## Verdict\n\nv\n")
    (tmp_path / "guards.md").write_text("## Verdict\n\nno newline")
    reports = [tmp_path / name for name in ("behaviour.md", "guards.md", "missing.md")]
    args = ["--kind", "review", "--range", "a..b", "--tip", "abcdef0", "--refutation", str(tmp_path / "refutation.md")]
    done = _ledger("append", str(tmp_path), *args, *(a for r in reports for a in ("--report", str(r))))
    assert done.returncode == 0, done.stderr
    assert (tmp_path / "behaviour.md").read_text() == "## Verdict\n\nv\n\n" + block
    assert (tmp_path / "guards.md").read_text() == "## Verdict\n\nno newline\n\n" + block
    assert (tmp_path / "missing.md").read_text() == block
    assert done.stderr.count("review-ledger: ") == 1 and "missing.md did not exist" in done.stderr
    assert json.loads((tmp_path / "ledger.jsonl").read_text())["kind"] == "review"


def test_read_prints_the_entries_and_a_missing_ledger_is_none(tmp_path: Path, repo: Path):
    tip = _branch(repo, ("one\n", "feat: one"), when="2026-09-01T00:00:00Z")
    assert _read(tmp_path, tip, repo) == []
    rows = [
        {"kind": "task", "label": "t1", "range": "main..x"},
        {"kind": "pre-review", "range": "main..x", "tip": tip, "ts": "t"},
        {"kind": "review", "range": "main..x", "tip": "0ancestor", "ts": "t"},
    ]
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "\n")
    assert _read(tmp_path, tip, repo) == rows, "an entry at this tip, and any other kind, is printed as it stands"


def test_a_malformed_line_is_refused_by_its_number(tmp_path: Path, repo: Path):
    (tmp_path / "ledger.jsonl").write_text('{"kind":"review"}\n["not", "an", "object"]\n')
    done = _ledger("read", str(tmp_path), "--tip", "abcdef0", "--repo", str(repo))
    assert done.returncode == 1 and "ledger.jsonl:2 is not a JSON object" in done.stderr and done.stdout == ""


def test_a_pre_review_of_a_re_dated_branch_covers_its_tip(tmp_path: Path, repo: Path):
    commits = (("one\n", "feat: one"), ("two\n", "feat: two"))
    read_tip = _branch(repo, *commits, when="2026-09-01T00:00:00Z")
    tip = _branch(repo, *commits, when="2026-09-02T00:00:00Z")
    assert tip != read_tip
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"kind": "pre-review", "range": "main..x", "tip": read_tip, "ts": "t"}) + "\n"
    )
    [entry] = _read(tmp_path, tip, repo)
    assert entry["sameTreeAndMessages"] is True and entry["against"] == tip


@pytest.mark.parametrize(
    "rebuilt",
    [
        (("one\n", "feat: one"), ("three\n", "feat: two")),
        (("one\n", "feat: one"), ("two\n", "feat: two, reworded")),
        (("one\n", "feat: one, reworded"), ("two\n", "feat: two")),
    ],
    ids=["tree changed", "tip message changed", "an earlier message changed"],
)
def test_a_pre_review_of_another_tree_or_other_messages_does_not(tmp_path: Path, repo: Path, rebuilt):
    read_tip = _branch(repo, ("one\n", "feat: one"), ("two\n", "feat: two"), when="2026-09-01T00:00:00Z")
    tip = _branch(repo, *rebuilt, when="2026-09-02T00:00:00Z")
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"kind": "pre-review", "range": "main..x", "tip": read_tip, "ts": "t"}) + "\n"
    )
    [entry] = _read(tmp_path, tip, repo)
    assert entry["sameTreeAndMessages"] is False and entry["against"] == tip


@pytest.mark.parametrize("theirs", ["0ancestor", "deadbeefdeadbeef", None], ids=["not hex", "no such commit", "no tip"])
def test_a_pre_review_whose_tip_git_cannot_resolve_covers_nothing(tmp_path: Path, repo: Path, theirs):
    tip = _branch(repo, ("one\n", "feat: one"), when="2026-09-01T00:00:00Z")
    entry = {"kind": "pre-review", "range": "main..x", "ts": "t"} | ({"tip": theirs} if theirs else {})
    (tmp_path / "ledger.jsonl").write_text(json.dumps(entry) + "\n")
    [read] = _read(tmp_path, tip, repo)
    assert read["sameTreeAndMessages"] is False
