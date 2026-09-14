"""`infra/scripts/sweep.sh` — the sweep that opens what a bare one does not: `.local/`, and a file not yet added."""

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
    run("add", "-f", ".gitignore", "cli/thing.py", ".local/.gitignore")
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


def test_a_worktree_sweeps_the_main_checkouts_local(tmp_path):
    """`.local/` is per-checkout, and a linked worktree's carries nothing but the tracked `.gitignore` — only the main checkout's holds the memo."""
    repo = _repo(tmp_path)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt)], check=True, capture_output=True)
    done = subprocess.run(["bash", str(SCRIPT), "-l", "NEEDLE"], cwd=wt, capture_output=True, text=True)
    assert sorted(done.stdout.split()) == [str(repo / ".local" / "memo.md"), "cli/thing.py"], done.stdout + done.stderr


def test_a_tracked_file_deleted_in_the_worktree_keeps_the_rc_contract(tmp_path):
    """`git ls-files` reads the index, and grep exits 2 over a missing path however many hits it printed."""
    repo = _repo(tmp_path)
    (repo / "cli" / "gone.py").write_text("NEEDLE in a doomed file\n")
    subprocess.run(["git", "-C", str(repo), "add", "cli/gone.py"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "doomed"], check=True, capture_output=True)
    (repo / "cli" / "gone.py").unlink()
    done = _sweep(repo, "-l", "NEEDLE")
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stderr == "" and "gone.py" not in done.stdout, done.stdout + done.stderr


def test_nothing_to_search_is_an_error_not_a_clean(tmp_path):
    """rc 1 means the pattern is absent; a sweep that opened no file at all must not say that."""
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "develop"], check=True, capture_output=True)
    done = _sweep(repo, "NEEDLE")
    assert done.returncode == 2 and "no files to search" in done.stderr, done.stdout + done.stderr


def test_a_tracked_file_under_local_is_swept_once(tmp_path):
    """This repo tracks `.local/.gitignore`, so both halves of the list would otherwise hand grep one file twice."""
    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "add", "-f", ".local/memo.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "tracked under .local"], check=True, capture_output=True)
    done = _sweep(repo, "NEEDLE")
    assert done.stdout.count(".local/memo.md:") == 1, done.stdout + done.stderr


def test_a_main_checkout_that_does_not_resolve_is_refused(tmp_path):
    """Under `--separate-git-dir` the common dir's parent is no checkout, and a sweep of the tracked tree alone is the silent clean."""
    repo = tmp_path / "sep"
    (tmp_path / "elsewhere").mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "develop", "--separate-git-dir", str(tmp_path / "elsewhere" / "sep.git"), str(repo)],
        check=True,
        capture_output=True,
    )
    (repo / "only.py").write_text("NEEDLE alone\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", "only.py")
    run("commit", "-qm", "one file")
    done = _sweep(repo, "NEEDLE")
    assert done.returncode == 2 and "no main checkout" in done.stderr, done.stdout + done.stderr


def test_an_absent_ledger_directory_says_so_on_stderr(tmp_path):
    """rc stays the pattern's answer, but a sweep that could not open `.local/` must not read like one that did."""
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
    assert done.returncode == 0 and "not in this sweep" in done.stderr, done.stdout + done.stderr


def test_an_untracked_unignored_file_is_swept(tmp_path):
    """A session writes a file before it adds it; the shell grep this script replaces opens it, so this must too."""
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "new-spec.md").write_text("NEEDLE not yet added\n")
    done = _sweep(repo, "-l", "NEEDLE")
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py", "docs/new-spec.md"], done.stdout + done.stderr


def test_no_pattern_at_all_is_an_error(tmp_path):
    """Given no pattern grep takes the first path as one and answers that accidental regex's rc — a hit or a clean, never the error this is."""
    done = _sweep(_repo(tmp_path))
    assert done.returncode == 2 and "usage" in done.stderr, done.stdout + done.stderr


def test_a_conflicted_file_is_swept_once(tmp_path):
    """During a merge conflict the index carries a path once per stage, and grep would open it once per entry."""
    repo = _repo(tmp_path)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("checkout", "-q", "-b", "other")
    (repo / "cli" / "thing.py").write_text("NEEDLE from the other branch\n")
    run("commit", "-qam", "other")
    run("checkout", "-q", "develop")
    (repo / "cli" / "thing.py").write_text("NEEDLE from develop\n")
    run("commit", "-qam", "develop")
    subprocess.run(["git", "-C", str(repo), "merge", "other"], capture_output=True)
    done = _sweep(repo, "-l", "NEEDLE")
    assert done.stdout.split().count("cli/thing.py") == 1, done.stdout + done.stderr


def test_an_untracked_nested_checkout_is_named_not_dropped(tmp_path):
    """`git ls-files --others` lists a nested repo as the bare directory, which the regular-file filter drops."""
    repo = _repo(tmp_path)
    (repo / "vendor").mkdir()
    (repo / "vendor" / "thing.py").write_text("NEEDLE in a nested checkout\n")
    subprocess.run(["git", "-C", str(repo / "vendor"), "init", "-q", "-b", "develop"], check=True, capture_output=True)
    done = _sweep(repo, "-l", "NEEDLE")
    assert "vendor" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_dangling_symlink_is_named_not_dropped(tmp_path):
    """A broken link satisfies neither the regular-file test nor the directory test, and a path still in the worktree is never dropped in silence."""
    repo = _repo(tmp_path)
    (repo / "cli" / "gone.py").symlink_to("/nonexistent/never-here.py")
    subprocess.run(["git", "-C", str(repo), "add", "cli/gone.py"], check=True, capture_output=True)
    done = _sweep(repo, "-l", "NEEDLE")
    assert "gone.py" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr
