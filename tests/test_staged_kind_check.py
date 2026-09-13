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
        ((".claude/skills/x/SKILL.md", "cli/thing.py"), 1),  # the defect the hook is for
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


def test_a_merge_in_progress_is_exempt(tmp_path):
    """The same staged set that fails above passes while MERGE_HEAD is present."""
    repo = _repo(tmp_path)
    _stage(repo, ".claude/skills/x/SKILL.md", "cli/thing.py")
    assert _run(repo).returncode == 1  # the control: without MERGE_HEAD this exact set is refused

    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    (repo / ".git" / "MERGE_HEAD").write_text(head + "\n")

    assert _run(repo).returncode == 0
