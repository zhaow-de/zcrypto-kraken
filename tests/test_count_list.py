"""count-list.sh: one line per count command the corpus names, and a topic-only-merge arm that counts a merge only when every file it brought in is a topic file."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "scripts" / "count-list.sh"
FEED = REPO / "tests" / "fixtures" / "kraken_scheduled_maintenances.json"
CORPUS = (REPO / "CLAUDE.md", REPO / ".claude" / "rules" / "fleet-deploys.md")

_ENTRY = re.compile(r'^\s*emit "([^"]+)"', re.MULTILINE)
_VALUE = re.compile(r"\d+(?: passed)?")


def _corpus_count_commands() -> int:
    return sum(path.read_text().count("count:") for path in CORPUS)


def _develop_resolves() -> bool:
    done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", "develop"], capture_output=True)
    return done.returncode == 0


def test_one_entry_per_corpus_count_command_plus_the_topic_only_merge_count():
    """The corpus's own count commands are the entry list -- a universal whose command is not run here is the finding."""
    names = _ENTRY.findall(SCRIPT.read_text())
    assert len(names) == len(set(names)), f"two entries answer to one name: {sorted(names)}"
    assert len(names) == _corpus_count_commands() + 1, (
        f"{len(names)} entries against {_corpus_count_commands()} count commands + 1: {names}"
    )


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
    assert len(lines) == _corpus_count_commands() + 1, done.stdout
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
