"""mutate-probe.sh: the guard-proving rule as executable form (spec 00082 D4)."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "mutate-probe.sh"


def run(args, cwd, env_extra=None, script=SCRIPT):
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([str(script), *args], cwd=cwd, capture_output=True, text=True, env=env)


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


# --------------------------------------------------------------------------------------------------
# The three properties the tests above leave unproven: sandbox seeding, the bytecode export, and the
# __pycache__ purge each SURVIVED mutation of the script. Each test below asserts BOTH directions --
# the real script, and a copy with that one guard mutated -- so the guard is proven to bite rather
# than merely proven present. The script must satisfy its own rule.
#
# Two of them assert rc 5 ("control did not fail") as the PASS condition, the same inversion as
# test_control_mutation_must_fail_first: their probe reads the property rather than the mutated file,
# so a working guard makes the probe SUCCEED, which is exactly what the control phase must refuse.
# --------------------------------------------------------------------------------------------------


def mutated_script(tmp_path, sed_expr):
    """A copy of the script with one guard mutated.

    Lives OUTSIDE the scratch repo: a copy inside it would dirty the worktree and trip the refusal
    before the guard under test is ever reached.
    """
    copy = tmp_path / "mutated-probe.sh"
    before = SCRIPT.read_text()
    copy.write_text(before)
    subprocess.run(["sed", "-i", sed_expr, str(copy)], check=True)
    assert copy.read_text() != before, f"mutation {sed_expr!r} was a no-op -- it would prove nothing"
    copy.chmod(0o755)
    return copy


def test_sandbox_seeds_from_committed_head_not_the_worktree(tmp_path):
    repo = tmp_path / "repo"
    target = make_repo(repo)
    target.write_text("VALUE = 9\n")  # dirty and UNCOMMITTED -- absent from `git archive HEAD`
    args = [
        "--sandbox",
        "--file",
        "mod.py",
        "--control",
        "s/VALUE = 1/VALUE = 8/",
        "--mutation",
        "s/VALUE = 1/VALUE = 2/",
        "--",
        "./probe.sh",
    ]

    # seeded from HEAD, so `VALUE = 1` is present and both seds match -> the cycle reaches a verdict
    r = run(args, repo)
    assert r.returncode == 0, f"git archive seeding should reach a verdict: {r.returncode} {r.stdout}{r.stderr}"
    assert "KILLED" in r.stdout or "SURVIVED" in r.stdout
    assert target.read_text() == "VALUE = 9\n"  # the real worktree is never written

    # cp -a would seed the DIRTY `VALUE = 9`, so the control sed matches nothing and the no-op guard
    # fires -- this is the mutation the property exists to kill
    cp_a = mutated_script(tmp_path, 's|^  git archive HEAD .*|  cp -a . "$work"|')
    r2 = run(args, repo, script=cp_a)
    assert r2.returncode == 6, f"cp -a seeding must be caught: {r2.returncode} {r2.stdout}{r2.stderr}"
    assert "did not change" in (r2.stdout + r2.stderr)


def test_probe_runs_with_bytecode_writing_disabled(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    probe = repo / "env-probe.sh"
    probe.write_text('#!/bin/sh\ntest "$PYTHONDONTWRITEBYTECODE" = 1\n')
    probe.chmod(0o755)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "env probe"], check=True)
    args = [
        "--file",
        "mod.py",
        "--control",
        "s/VALUE = 1/VALUE = 9/",
        "--mutation",
        "s/VALUE = 1/VALUE = 2/",
        "--",
        "./env-probe.sh",
    ]
    # inherit an explicit 0 so the assertion measures the SCRIPT's export, not the ambient environment
    env = {"PYTHONDONTWRITEBYTECODE": "0"}

    # the probe succeeds (the var reached it as 1), so the control cannot fail and the harness aborts
    r = run(args, repo, env_extra=env)
    assert r.returncode == 5, f"expected the control-did-not-fail abort: {r.returncode} {r.stdout}{r.stderr}"
    assert "control" in (r.stdout + r.stderr).lower()

    # with the export removed the probe sees the inherited 0, fails, and the cycle runs to a verdict
    no_export = mutated_script(tmp_path, "s|^export PYTHONDONTWRITEBYTECODE=1$|export MUTPROBE_UNSET=1|")
    r2 = run(args, repo, env_extra=env, script=no_export)
    assert r2.returncode == 0 and "KILLED" in r2.stdout, f"{r2.returncode} {r2.stdout}{r2.stderr}"


def test_purge_removes_a_pre_existing_pycache(tmp_path):
    repo = tmp_path / "repo"
    make_repo(repo)
    cache = repo / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-314.pyc").write_bytes(b"stale")
    probe = repo / "cache-probe.sh"
    probe.write_text("#!/bin/sh\ntest ! -d __pycache__\n")
    probe.chmod(0o755)
    # -f: a global core.excludesFile would otherwise skip __pycache__, leaving the tree "clean" for
    # the wrong reason
    subprocess.run(["git", "-C", str(repo), "add", "-f", "__pycache__", "cache-probe.sh"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "stale cache"], check=True)
    args = [
        "--file",
        "mod.py",
        "--control",
        "s/VALUE = 1/VALUE = 9/",
        "--mutation",
        "s/VALUE = 1/VALUE = 2/",
        "--",
        "./cache-probe.sh",
    ]

    # purge runs inside apply(), before the probe: the dir is gone, the probe succeeds, and the
    # control therefore cannot fail -- that abort is the proof the purge happened
    r = run(args, repo)
    assert r.returncode == 5, f"expected the control-did-not-fail abort: {r.returncode} {r.stdout}{r.stderr}"
    assert not cache.exists()

    # restore the stale dir byte-identically (so the worktree is clean again) and empty out purge()
    cache.mkdir()
    (cache / "mod.cpython-314.pyc").write_bytes(b"stale")
    no_purge = mutated_script(tmp_path, "s|^purge() { find . -name __pycache__.*$|purge() { :; }|")
    r2 = run(args, repo, script=no_purge)
    assert r2.returncode == 0 and "KILLED" in r2.stdout, f"{r2.returncode} {r2.stdout}{r2.stderr}"
    assert cache.exists()  # survived, as the mutation intends


def test_temporaries_are_removed_on_every_exit_path(tmp_path):
    """Both mktemp'd paths are trapped, on the verdict paths AND on an abort."""
    repo = tmp_path / "repo"
    make_repo(repo)
    tmpdir = tmp_path / "tmp"  # mktemp honours TMPDIR, so the whole leak surface is observable here
    tmpdir.mkdir()
    env = {"TMPDIR": str(tmpdir)}
    cases = [
        (["--sandbox"], "s/VALUE = 1/VALUE = 2/"),  # sandbox dir + pristine copy
        ([], "s/VALUE = 1/VALUE = 2/"),  # pristine copy, verdict path
        ([], "s/nomatch/x/"),  # pristine copy, exit-6 abort path
    ]
    for mode, mutation in cases:
        run(
            [*mode, "--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", mutation, "--", "./probe.sh"],
            repo,
            env_extra=env,
        )
        leaked = [p.name for p in tmpdir.iterdir()]
        assert not leaked, f"{mode or ['in-repo']} + {mutation} leaked {leaked}"
