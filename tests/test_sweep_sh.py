"""`infra/scripts/sweep.sh` — the sweep that sees `.local/`, which a bare one cannot."""

from __future__ import annotations

import pathlib
import subprocess

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra" / "scripts" / "sweep.sh"


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    (repo / ".local").mkdir(parents=True)
    (repo / ".venv" / "lib").mkdir(parents=True)
    (repo / "cli").mkdir()
    (repo / ".gitignore").write_text(".venv\n.local\n")
    (repo / ".local" / ".gitignore").write_text("*\n")
    (repo / ".local" / "memo.md").write_text("NEEDLE in the memo\n")
    (repo / ".venv" / "lib" / "vendored.py").write_text("NEEDLE in a dependency\n")
    (repo / "cli" / "thing.py").write_text("NEEDLE in the tree\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "develop")
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", ".gitignore", "cli/thing.py")
    run("commit", "-qm", "tracked")
    return repo


def _sweep(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=repo, capture_output=True, text=True)


def test_the_sweep_sees_the_tracked_tree_and_local_and_not_the_ignored_rest(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "NEEDLE")
    hits = sorted(done.stdout.split())
    assert hits == [".local/memo.md", "cli/thing.py"], done.stdout + done.stderr
    assert done.returncode == 0


def test_a_pattern_nothing_holds_exits_1(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "no-such-string-anywhere")
    assert done.returncode == 1 and done.stdout == "", done.stdout + done.stderr


def test_a_hit_names_its_file_when_the_list_is_one_file(tmp_path):
    """GNU grep drops the filename when it is handed a single file, so `-H` is what makes a hit readable."""
    repo = tmp_path / "solo"
    repo.mkdir()
    (repo / "only.py").write_text("NEEDLE alone\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "develop")
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", "only.py")
    run("commit", "-qm", "one file")
    done = _sweep(repo, "NEEDLE")
    assert done.stdout == "only.py:NEEDLE alone\n", done.stdout + done.stderr


def test_it_runs_from_a_subdirectory(tmp_path):
    """The skills that call it run from wherever the session stands."""
    repo = _repo(tmp_path)
    done = subprocess.run(["bash", str(SCRIPT), "-l", "NEEDLE"], cwd=repo / "cli", capture_output=True, text=True)
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py"], done.stdout + done.stderr
