import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
COVERAGE = WORKFLOWS / "coverage.yml"
WARMER = WORKFLOWS / "uv-cache.yml"
# setup-uv folds each of these into its cache key (`computeKeys` in its src/cache/restore-cache.ts),
# with the runner's OS and the action's own version: one differing input splits the two workflows
# onto keys neither ever restores from the other.
KEY_INPUTS = ("python-version", "cache-dependency-glob", "prune-cache", "cache-python", "cache-suffix")
SAVE_WHEN_THE_LOCK_CHANGED = "${{ steps.lock.outputs.changed == 'true' }}"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _only_job(workflow: dict) -> dict:
    (job,) = workflow["jobs"].values()
    return job


def _setup_uv(job: dict) -> dict:
    (step,) = [s for s in job["steps"] if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")]
    return step


def test_the_warmer_and_the_suite_compute_the_same_cache_key():
    coverage, warmer = _only_job(_load(COVERAGE)), _only_job(_load(WARMER))
    assert coverage["runs-on"] == warmer["runs-on"]
    suite, warm = _setup_uv(coverage), _setup_uv(warmer)
    assert suite["uses"] == warm["uses"]
    for name in KEY_INPUTS:
        assert suite.get("with", {}).get(name) == warm.get("with", {}).get(name), name
    assert suite["with"]["cache-dependency-glob"] == "uv.lock"


def _lock_step_output(tmp_path: Path, *, lockfile_changed: bool) -> str:
    (lock,) = [s for s in _only_job(_load(COVERAGE))["steps"] if s.get("id") == "lock"]
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    (repo / "uv.lock").write_text("base\n")
    git("add", "uv.lock")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    git("update-ref", "refs/remotes/origin/develop", "HEAD")
    if lockfile_changed:
        (repo / "uv.lock").write_text("changed\n")
    output = tmp_path / "github_output"
    # GitHub's own `run:` shell.
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", lock["run"]],
        cwd=repo,
        check=True,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
    )
    return output.read_text()


def test_a_pull_request_saves_the_cache_only_when_it_changes_the_lockfile(tmp_path):
    job = _only_job(_load(COVERAGE))
    step = _setup_uv(job)
    assert step["with"].get("save-cache") == SAVE_WHEN_THE_LOCK_CHANGED
    (lock,) = [s for s in job["steps"] if s.get("id") == "lock"]
    assert job["steps"].index(lock) < job["steps"].index(step)
    assert _lock_step_output(tmp_path / "same", lockfile_changed=False) == "changed=false\n"
    assert _lock_step_output(tmp_path / "moved", lockfile_changed=True) == "changed=true\n"


def test_the_warmer_seeds_develop_on_a_lockfile_change_and_a_schedule_and_runs_no_suite():
    warmer = _load(WARMER)
    triggers = warmer.get("on", warmer.get(True))
    assert triggers["push"]["branches"] == ["develop"]
    assert "uv.lock" in triggers["push"]["paths"]
    assert triggers["schedule"]
    assert not any("pytest" in str(s.get("run", "")) for s in _only_job(warmer)["steps"])
