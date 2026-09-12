"""count-list.sh: one entry per count the corpus names by entry name plus the four it does not, a name filter, and a topic-only-merge arm that counts a merge only when every file it brought in is a topic file."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


def _tracked(pathspec: str) -> list[str]:
    """The index's paths, so an untracked scratch page under a judged directory never turns the suite red."""
    return subprocess.run(["git", "-C", str(REPO), "ls-files", pathspec], capture_output=True, text=True, check=True).stdout.split()


SCRIPT = REPO / "infra" / "scripts" / "count-list.sh"
FEED = REPO / "tests" / "fixtures" / "kraken_scheduled_maintenances.json"
CORPUS = (
    REPO / "CLAUDE.md",
    REPO / ".claude" / "rules" / "fleet-deploys.md",
    REPO / "docs" / "reference" / "fleet.md",
    REPO / "docs" / "reference" / "fleet-pins.md",
    REPO / ".claude" / "skills" / "zcrypto-grooming" / "references" / "memo-protocol.md",
    *sorted(REPO / p for p in _tracked("infra/runbooks/*.md") if "/" not in p[len("infra/runbooks/") :]),
)  # the always-loaded guidance, and the contracts the guard reads for universals -- every top-level runbook page among them since 2026-09-12

_ENTRY = re.compile(r'^\s*emit "([^"]+)"', re.MULTILINE)
_CORPUS_ENTRY = re.compile(r"count: `infra/scripts/count-list\.sh ([a-z0-9-]+)`")
NOT_NAMED = {"topic-only-merges", "claude-commits-since-the-round-closed", "worktrees", "ambient-bytes"}
_VALUE = re.compile(r"\d+(?: passed)?")


def _corpus_entries() -> set[str]:
    return {name for path in CORPUS for name in _CORPUS_ENTRY.findall(path.read_text())}


def _develop_resolves() -> bool:
    done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", "develop"], capture_output=True)
    return done.returncode == 0


def test_the_corpus_names_every_entry_but_the_four_the_script_carries_on_its_own():
    """A corpus count names an entry that exists, and an entry the corpus does not name is one of the four -- a universal whose count is not run here is the finding."""
    names = _ENTRY.findall(SCRIPT.read_text())
    assert len(names) == len(set(names)), f"two entries answer to one name: {sorted(names)}"
    corpus = _corpus_entries()
    inline = sum(p.read_text().count("count: ") for p in CORPUS) - sum(len(_CORPUS_ENTRY.findall(p.read_text())) for p in CORPUS)
    assert inline == 0, f"{inline} corpus count(s) carry a command inline instead of naming an entry"
    assert corpus <= set(names), f"the corpus names entries the script lacks: {sorted(corpus - set(names))}"
    assert set(names) - corpus == NOT_NAMED, f"entries the corpus does not name: {sorted(set(names) - corpus)}"


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_the_read_count_finds_its_line_anywhere_in_the_body_and_only_at_the_floor(tmp_path):
    """A Fable line on the body's third line is a read; a Haiku line at the top is not; the journal PR is left out; no line counts."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = "Read before push by: Claude Fable 5.1 at 22ac48df"
    prs = [
        {"headRefName": "feat/a", "mergedAt": stamp, "body": f"## Summary\n\n{line}\n\n- [x] done"},
        {"headRefName": "feat/b", "mergedAt": stamp, "body": "Read before push by: Claude Haiku 4.5 at 22ac48df\n"},
        {"headRefName": "ops-journal", "mergedAt": stamp, "body": "## 2026-09\n"},
        {"headRefName": "feat/c", "mergedAt": stamp, "body": "## Summary\n"},
    ]
    snapshot = tmp_path / "prs.json"
    snapshot.write_text(json.dumps(prs))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_PRS_SNAPSHOT": str(snapshot)},
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout == "merged-prs-without-a-floor-read-30d\t2\n", done.stdout + done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_a_named_entry_runs_alone_and_an_unknown_name_is_refused():
    one = subprocess.run(
        ["bash", str(SCRIPT), "markdown-directly-under-docs"], cwd=REPO, capture_output=True, text=True, timeout=120
    )
    assert one.returncode == 0 and one.stdout.splitlines() == [
        f"markdown-directly-under-docs\t{one.stdout.split(chr(9))[1].strip()}"
    ], one.stdout + one.stderr
    none = subprocess.run(["bash", str(SCRIPT), "no-such-entry"], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert none.returncode == 2 and "no entry named no-such-entry" in none.stderr, none.stdout + none.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="five counts read the develop ref by name, and this checkout has none")
def test_the_script_prints_one_shaped_line_per_entry():
    """Run against a recorded feed, so the maintenance count reaches no venue from a test."""
    done = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_FEED_SNAPSHOT": str(FEED)},
        timeout=1800,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert len(lines) == len(_ENTRY.findall(SCRIPT.read_text())), done.stdout
    for line in lines:
        name, tab, value = line.partition("\t")
        assert tab == "\t" and name, f"no name and tab: {line!r}"
        for part in value.split("; "):
            assert _VALUE.fullmatch(part), f"{name} printed no count: {value!r}"


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _merge(repo: pathlib.Path, branch: str, files: list[str]) -> None:
    _git(repo, "checkout", "-q", "-b", branch)
    for rel in files:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"{branch}\n")
        _git(repo, "add", rel)
        _git(repo, "commit", "-qm", f"add {rel}")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "-q", "--no-ff", "-m", f"Merge pull request from {branch}", branch)


def _topic_only_merges(repo: pathlib.Path) -> str:
    script = f'source "{SCRIPT}"; cd "{repo}"; count_micro_prs develop'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("base\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_the_topic_only_arm_counts_a_merge_only_when_every_file_it_brought_in_is_a_topic_file(repo):
    """One file outside `docs/open-topics/` disqualifies the whole merge, however many topic files ride with it."""
    _merge(repo, "mixed", ["docs/open-topics/T9998-parked.md", "cli/thing.py"])
    assert _topic_only_merges(repo) == "0"
    _merge(repo, "topics-only", ["docs/open-topics/T9999-parked.md", "docs/open-topics/README.md"])
    assert _topic_only_merges(repo) == "1"
