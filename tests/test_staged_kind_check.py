"""`infra/scripts/staged-kind-check.sh` — the one-kind-per-commit hook, which had no test.

It is the hook the `.pre-commit-config.yaml` comment calls "the P6 trigger" (the rule was violated five times
while written down), and its merge arm was added because a merge stages both parents' kinds and the author chose
neither — the case where the documented `SKIP=staged-kind` escape was being used routinely instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "staged-kind-check.sh"


def _repo(tmp_path: Path) -> Path:
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (tmp_path / "seed.txt").write_text("seed\n")
    run("add", "seed.txt")
    run("commit", "-qm", "seed")
    return tmp_path


def _stage(repo: Path, *names: str) -> None:
    """Fixture paths stay off `.claude/skills/*/SKILL.md` and friends: `tests/test_guidance_refs_resolve.py`
    reads those as citations and a fake one dangles."""
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
        subprocess.run(["git", "-C", str(repo), "add", name], check=True, capture_output=True)


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(HOOK)], cwd=repo, capture_output=True, text=True)


@pytest.mark.parametrize(
    ("staged", "rc"),
    [
        ((".claude/fixture.txt", "cli/thing.py"), 1),  # the defect the hook is for
        (("CLAUDE.md", "tests/test_thing.py"), 1),  # CLAUDE.md is claude-kind by name, not by directory
        ((".claude/settings.json", "CLAUDE.md"), 0),  # both claude-kind
        (("cli/thing.py", "tests/test_thing.py", "docs/x.md"), 0),  # a feat/fix commit legitimately mixes these
    ],
)
def test_the_hook_refuses_only_a_mixed_kind(tmp_path, staged, rc):
    repo = _repo(tmp_path)
    _stage(repo, *staged)
    done = _run(repo)
    assert done.returncode == rc, done.stdout + done.stderr
    if rc:
        assert "split the commit" in done.stdout


def _stopped_merge(repo: Path) -> None:
    """A real divergence, so the merge's candidate set is exactly the two files the cases stage."""
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("checkout", "-q", "-b", "theirs")
    _stage(repo, ".claude/fixture.txt")
    run("commit", "-qm", "claude side")
    run("checkout", "-q", "-")
    _stage(repo, "cli/thing.py")
    run("commit", "-qm", "code side")
    theirs = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "theirs"], check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / ".git" / "MERGE_HEAD").write_text(theirs + "\n")


def test_a_merge_exempts_its_own_files(tmp_path):
    """The mixed set a merge itself stages passes: the author chose neither side, and splitting is impossible."""
    repo = _repo(tmp_path)
    _stopped_merge(repo)
    _stage(repo, ".claude/fixture.txt", "cli/thing.py")
    assert _run(repo).returncode == 0


def test_a_merge_does_not_exempt_files_neither_parent_touched(tmp_path):
    """The hole the narrowing closes: a mixed pair the merge never touched would otherwise ride the exemption."""
    repo = _repo(tmp_path)
    _stopped_merge(repo)
    _stage(repo, ".claude/fixture.txt", "cli/thing.py")  # the merge's own, excused
    _stage(repo, ".claude/other.json", "cli/unrelated.py")  # neither parent's, still judged
    done = _run(repo)
    assert done.returncode == 1
    assert "split the commit" in done.stdout
