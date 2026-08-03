"""mutate-probe.sh: the guard-proving rule as executable form (spec 00082 D4)."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "mutate-probe.sh"


def run(args, cwd, env_extra=None):
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, env=env)


def make_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    target = tmp_path / "mod.py"
    target.write_text("VALUE = 1\n")
    probe = tmp_path / "probe.sh"
    probe.write_text("#!/bin/sh\ngrep -q 'VALUE = 1' mod.py\n")
    probe.chmod(0o755)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True)
    return target


def test_refuses_dirty_worktree(tmp_path):
    target = make_repo(tmp_path)
    target.write_text("VALUE = 1\n# dirty\n")
    r = run(["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", "s/VALUE/V/", "--", "./probe.sh"], tmp_path)
    assert r.returncode != 0 and "dirty" in (r.stdout + r.stderr).lower()


def test_control_mutation_must_fail_first(tmp_path):
    make_repo(tmp_path)
    # a control that CHANGES the file but does not break the probe (appends comments) => the
    # harness must abort before any real probe. (A non-matching sed would instead trip the
    # no-op guard -- that path has its own test below.)
    r = run(["--file", "mod.py", "--control", "s/$/ # c/", "--mutation", "s/VALUE = 1/VALUE = 2/", "--", "./probe.sh"], tmp_path)
    assert r.returncode != 0 and "control" in (r.stdout + r.stderr).lower()


def test_noop_mutation_aborts(tmp_path):
    make_repo(tmp_path)
    # I6b: a sed that matches nothing must abort loudly, never report SURVIVED on unmutated code
    r = run(
        ["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", "s/nonexistent/x/", "--", "./probe.sh"], tmp_path
    )
    assert r.returncode != 0 and "did not change" in (r.stdout + r.stderr)


def test_real_probe_runs_and_restores(tmp_path):
    target = make_repo(tmp_path)
    r = run(
        ["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", "s/VALUE = 1/VALUE = 2/", "--", "./probe.sh"],
        tmp_path,
    )
    assert r.returncode == 0
    assert "SURVIVED" in r.stdout or "KILLED" in r.stdout
    assert target.read_text() == "VALUE = 1\n"  # restored byte-identically


def test_sandbox_refuses_pytest(tmp_path):
    make_repo(tmp_path)
    r = run(["--sandbox", "--file", "mod.py", "--control", "s/a/b/", "--mutation", "s/c/d/", "--", "pytest", "-q"], tmp_path)
    assert r.returncode != 0 and "pytest" in (r.stdout + r.stderr).lower()
