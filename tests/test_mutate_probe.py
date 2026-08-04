"""mutate-probe.sh: the guard-proving rule as executable form (spec 00082 D4)."""

import os
import re
import signal
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "mutate-probe.sh"


def run(args, cwd, env_extra=None, script=SCRIPT):
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([str(script), *args], cwd=cwd, capture_output=True, text=True, env=env)


def make_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
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


# I6b: a sed that matches nothing must abort loudly, never report SURVIVED on unmutated code -- and
# the abort must name WHICH sed no-oped, or the operator re-reads both expressions to find out.
def test_noop_control_names_the_control(tmp_path):
    target = make_repo(tmp_path)
    r = run(
        ["--file", "mod.py", "--control", "s/NO-MATCH/x/", "--mutation", "s/VALUE = 1/VALUE = 9/", "--", "./probe.sh"], cwd=tmp_path
    )
    assert r.returncode == 6
    assert "control sed" in r.stderr


def test_noop_mutation_names_the_mutation(tmp_path):
    target = make_repo(tmp_path)
    r = run(
        ["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 2/", "--mutation", "s/NO-MATCH/x/", "--", "./probe.sh"], cwd=tmp_path
    )
    assert r.returncode == 6
    assert "mutation sed" in r.stderr


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


def test_seeding_failure_is_rc8_not_usage(tmp_path):
    """A repo with no commits makes `git archive HEAD` fail — that must be rc 8, distinct from
    usage (rc 2), and must not leave a temp dir behind."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    target = tmp_path / "mod.py"
    target.write_text("VALUE = 1\n")
    # no commit at all — HEAD is unborn
    r = run(
        ["--sandbox", "--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 2/", "--mutation", "s/1/3/", "--", "true"],
        cwd=tmp_path,
    )
    assert r.returncode == 8
    assert "seeding" in r.stderr.lower()


def test_baseline_failure_refuses_before_anything_is_mutated(tmp_path):
    """A probe that cannot pass on unmutated code makes every verdict below it meaningless.

    Without this gate an always-failing probe command sails through the control phase (the control
    "failed", as required) and then scores every real mutation KILLED with "control proven" attached
    -- the one-directional hole the control check alone leaves open.
    """
    target = make_repo(tmp_path)
    before = target.read_text()
    r = run(
        # a control sed that matches NOTHING: reaching the control phase at all would exit 6, so the
        # 7 below is positive proof the refusal landed before any mutation was applied
        ["--file", "mod.py", "--control", "s/nonexistent/x/", "--mutation", "s/VALUE = 1/VALUE = 2/", "--", "false"],
        tmp_path,
    )
    assert r.returncode == 7, f"expected the baseline refusal, got {r.returncode}: {r.stdout}{r.stderr}"
    assert "baseline" in (r.stdout + r.stderr).lower()
    assert target.read_text() == before
    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert status == "", f"worktree touched despite the pre-mutation refusal: {status!r}"


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

    # cp -a would seed the DIRTY `VALUE = 9`, so the probe cannot even pass on the seeded tree and the
    # baseline gate refuses -- this is the mutation the property exists to kill
    # swap the seeding command inside its own rc-8 guard, so the mutant stays valid bash and differs
    # from the real script in exactly one thing: where the sandbox's contents come from
    cp_a = mutated_script(tmp_path, 's|^  if ! git archive HEAD .*|  if ! cp -a . "$work"; then|')
    r2 = run(args, repo, script=cp_a)
    assert r2.returncode == 7, f"cp -a seeding must be caught: {r2.returncode} {r2.stdout}{r2.stderr}"
    assert "baseline" in (r2.stdout + r2.stderr).lower()


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

    # with the export removed the probe sees the inherited 0 and fails -- on the very first (baseline)
    # run, which is the earliest point the missing property is observable
    no_export = mutated_script(tmp_path, "s|^export PYTHONDONTWRITEBYTECODE=1$|export MUTPROBE_UNSET=1|")
    r2 = run(args, repo, env_extra=env, script=no_export)
    assert r2.returncode == 7, f"{r2.returncode} {r2.stdout}{r2.stderr}"
    assert "baseline" in (r2.stdout + r2.stderr).lower()


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

    # purge runs before the baseline probe and again inside apply(): the dir is gone, both probes
    # succeed, and the control therefore cannot fail -- that abort is the proof the purge happened
    r = run(args, repo)
    assert r.returncode == 5, f"expected the control-did-not-fail abort: {r.returncode} {r.stdout}{r.stderr}"
    assert not cache.exists()

    # restore the stale dir byte-identically (so the worktree is clean again) and empty out purge()
    cache.mkdir()
    (cache / "mod.cpython-314.pyc").write_bytes(b"stale")
    no_purge = mutated_script(tmp_path, "s|^purge() { find . -name __pycache__.*$|purge() { :; }|")
    r2 = run(args, repo, script=no_purge)
    # the stale dir survives, so the probe fails on the FIRST run -- the baseline gate is where the
    # missing purge now surfaces
    assert r2.returncode == 7, f"{r2.returncode} {r2.stdout}{r2.stderr}"
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


def _signal_mid_probe(script, repo, target, tmpdir, args, before, marker, sig=signal.SIGTERM):
    """Start a cycle, wait until the probe is genuinely running, then signal the whole process group.

    Two things here are load-bearing against flakiness, both found by running this 20x:

    * Wait on a marker the PROBE itself writes, not merely on the mutated content. The mutation is
      visible on disk while `apply` is still finishing, before the probe is spawned at all.
    * Re-send the signal until the process actually exits. Group delivery is what an interactive
      Ctrl-C does, but bash defers a *trapped* signal until the running foreground command returns --
      so a signal landing just before `sleep` spawns leaves bash blocked for the probe's full
      duration. Re-signalling reaches the now-existing child. Safe because `cleanup` is idempotent.
    """
    marker.unlink(missing_ok=True)
    env = {**os.environ, "TMPDIR": str(tmpdir)}
    p = subprocess.Popen(
        [str(script), *args],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if marker.exists():
            break
        time.sleep(0.02)
    else:
        p.kill()
        p.wait(timeout=10)
        pytest.fail("the probe never started -- nothing to signal mid-probe")
    assert target.read_bytes() != before, "the probe ran without the mutation applied"

    while time.monotonic() < deadline:
        try:
            os.killpg(os.getpgid(p.pid), sig)
        except ProcessLookupError:
            break
        try:
            return p.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            continue
    pytest.fail("the script never exited after repeated signals")


def test_signal_during_probe_restores_the_target_before_cleaning(tmp_path):
    """A signal lands with the mutation applied; cleaning first would delete the only way back."""
    repo = tmp_path / "repo"
    target = make_repo(repo)
    before = target.read_bytes()
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    # the marker lives OUTSIDE the repo and outside TMPDIR, so it disturbs neither the worktree-clean
    # assertion nor the temp-leak one
    marker = tmp_path / "probe-started"
    slow = repo / "slow-probe.sh"
    # The baseline probe must return fast and WITHOUT the marker, or the wait below would fire on the
    # unmutated baseline run and signal a cycle with nothing applied. Only a mutated file goes slow.
    slow.write_text(f"#!/bin/sh\ngrep -q 'VALUE = 1' mod.py && exit 0\ntouch {marker}\nsleep 30\n")
    slow.chmod(0o755)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "slow probe"], check=True)
    args = [
        "--file",
        "mod.py",
        "--control",
        "s/VALUE = 1/VALUE = 9/",
        "--mutation",
        "s/VALUE = 1/VALUE = 2/",
        "--",
        "./slow-probe.sh",
    ]

    rc = _signal_mid_probe(SCRIPT, repo, target, tmpdir, args, before, marker)
    assert rc == 143, f"expected the TERM handler's exit code, got {rc}"
    assert target.read_bytes() == before, "the target was left MUTATED on disk after a signal"
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert status == "", f"worktree left dirty after a signal: {status!r}"
    assert not list(tmpdir.iterdir()), "temporaries leaked on the signal path"

    # an interactive Ctrl-C must take the same path -- same restoration, its own exit code
    rc_int = _signal_mid_probe(SCRIPT, repo, target, tmpdir, args, before, marker, sig=signal.SIGINT)
    assert rc_int == 130, f"expected the INT handler's exit code, got {rc_int}"
    assert target.read_bytes() == before, "the target was left MUTATED on disk after Ctrl-C"

    # bite: neutralise the restoring cp -- the clean below it still runs, so the same signal strands
    # the mutation on disk AND deletes the pristine copy that was the only way back
    no_restore = mutated_script(tmp_path, "s|^    if ! cp .*|    if ! true; then|")
    _signal_mid_probe(no_restore, repo, target, tmpdir, args, before, marker)
    assert target.read_bytes() != before, "restore-on-signal removed but the file came back -- unproven"


def test_cleanup_cp_failure_is_rc9_and_keeps_pristine(tmp_path):
    """Signal mid-mutation with the TARGET FILE read-only, so the cleanup cp fails: rc must be 9,
    the stderr must say KEPT, and the pristine copy must SURVIVE (it is the only way back).

    Built on wave-1's slow-probe idiom (cold-review C2): fast on pristine/control content, marker +
    sleep only on the MUTATED content, so the kill window is unambiguous. `chmod 0444` goes on the
    FILE — overwriting needs write permission on the file, not its directory. killpg + re-send,
    exactly like the wave-1 signal test (bash defers trapped signals during foreground commands).
    Assumes a non-root test run (root ignores file modes)."""
    # The repo is nested one level down so the marker and the captured stderr live OUTSIDE it: both
    # are created before the script starts, and an untracked file in the repo trips the dirty-worktree
    # refusal (rc 3) before anything is ever mutated. Same reason wave-1's signal test nests its repo.
    repo = tmp_path / "repo"
    target = make_repo(repo)
    marker = tmp_path / "mutated-seen"
    probe = repo / "probe.sh"
    probe.write_text(f"#!/bin/sh\nif grep -q 'VALUE = 9' mod.py; then touch {marker}; sleep 30; fi\ngrep -q 'VALUE = 1' mod.py\n")
    probe.chmod(0o755)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "slow"], check=True)
    stderr_file = tmp_path / "stderr.txt"
    with stderr_file.open("w") as err:
        proc = subprocess.Popen(
            [
                str(SCRIPT),
                "--file",
                "mod.py",
                "--control",
                "s/VALUE = 1/VALUE = 2/",
                "--mutation",
                "s/VALUE = 1/VALUE = 9/",
                "--",
                "./probe.sh",
            ],
            cwd=repo,
            stderr=err,
            start_new_session=True,
        )
        for _ in range(200):
            if marker.exists():
                break
            time.sleep(0.05)
        else:
            proc.kill()
            raise AssertionError("mutation phase never observed")
        os.chmod(target, 0o444)  # the cleanup cp to $file now fails
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    break
                os.killpg(proc.pid, signal.SIGTERM)
                time.sleep(0.05)
            rc = proc.wait(timeout=5)
        finally:
            os.chmod(target, 0o644)
    assert rc == 9
    err_text = stderr_file.read_text()
    assert "KEPT" in err_text
    kept = re.search(r"KEPT at (\S+)", err_text)
    assert kept and Path(kept.group(1)).exists()  # the pristine copy genuinely survived
    Path(kept.group(1)).unlink()  # leave no temp behind
