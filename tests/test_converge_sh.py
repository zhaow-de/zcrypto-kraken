"""converge.sh: preview-first, typed-limit confirm, then the real pass (spec 00083 D1).

Every test copies the script into a scratch dir beside a FAKE run.sh that appends its argv
(one line per invocation) to invocations.log — the tests assert on what actually ran, never
only on exit codes.
"""

import os
import pty
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "converge.sh"

FAKE_RUN_SH = """#!/usr/bin/env bash
echo "$@" >> "$(dirname "$0")/invocations.log"
exit ${FAKE_RUN_RC:-0}
"""


def make_harness(tmp_path):
    shutil.copy(SCRIPT, tmp_path / "converge.sh")
    (tmp_path / "run.sh").write_text(FAKE_RUN_SH)
    for name in ("converge.sh", "run.sh"):
        p = tmp_path / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return tmp_path / "converge.sh"


def invocations(tmp_path):
    log = tmp_path / "invocations.log"
    return log.read_text().splitlines() if log.exists() else []


def run_no_tty(script, args, env=None):
    return subprocess.run(
        ["setsid", str(script), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={**os.environ, **(env or {})},
    )


def run_with_tty(script, args, reply):
    """Run under a pty (the child's controlling terminal) and type `reply` at the confirm."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(str(script), [str(script), *args])
    out = b""
    try:
        while b"aborts:" not in out and b"converge," not in out:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
        os.write(fd, reply.encode() + b"\n")
        while True:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode(errors="replace")


def run_with_ctty_but_piped_stdin(script, args, piped_reply, deadline=3.0):
    """Controlling pty attached (so the tty gate opens) but stdin is a PIPE carrying the reply.

    The CHANNEL is the whole subject here. Every other test in this file drives the confirm through
    the pty, so a script that read `reply` from stdin instead of /dev/tty passes all of them
    (measured) -- the pty IS stdin there. This shape separates the two: the gate finds a controlling
    terminal, nobody types on it, and the answer the operator never gave arrives on a pipe.

    Returns the exit code, or None if the process was still running at the deadline (blocked on
    /dev/tty -- the correct behavior). Kills it either way.
    """
    r, w = os.pipe()
    pid, master = pty.fork()  # child: the pty slave is fd 0/1/2 AND the controlling terminal
    if pid == 0:
        try:
            os.close(w)
            os.dup2(r, 0)  # stdin becomes the pipe; the pty stays the controlling terminal
            os.close(r)
            os.execv(str(script), [str(script), *args])
        finally:
            os._exit(127)  # a failed execv must never leave a forked pytest running
    os.close(r)
    os.write(w, piped_reply.encode() + b"\n")
    os.close(w)
    status, until = None, time.monotonic() + deadline
    while time.monotonic() < until:
        wpid, st = os.waitpid(pid, os.WNOHANG)
        if wpid:
            status = st
            break
        time.sleep(0.05)
    if status is None:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    os.close(master)
    return None if status is None else os.waitstatus_to_exitcode(status)


def test_pipe_cannot_drive_the_confirm(tmp_path):
    script = make_harness(tmp_path)
    rc = run_with_ctty_but_piped_stdin(script, ["site.yml", "--limit", "zcrypto-red"], "zcrypto-red")
    # rc 3 (aborted) and None (still waiting on the silent /dev/tty) are both correct; 0 means the
    # pipe answered the confirm and the real pass ran.
    assert rc != 0
    assert len(invocations(tmp_path)) == 1  # preview only -- the real pass never ran


def test_refuses_without_limit(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml"])
    assert r.returncode == 2
    assert "--limit" in r.stderr
    assert invocations(tmp_path) == []


def test_refuses_without_playbook(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, [])
    assert r.returncode == 2
    r2 = run_no_tty(script, ["--limit", "zcrypto-red"])
    assert r2.returncode == 2
    assert invocations(tmp_path) == []


def test_preview_failure_aborts(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto-red"], env={"FAKE_RUN_RC": "1"})
    assert r.returncode == 4
    assert len(invocations(tmp_path)) == 1  # only the preview ran


def test_check_only_stops_after_preview(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--check", "--limit", "zcrypto-red"])
    assert r.returncode == 0
    inv = invocations(tmp_path)
    assert len(inv) == 1 and "--check" in inv[0] and "--diff" in inv[0]


def test_no_tty_refuses_before_real_pass(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto-red"])
    assert r.returncode == 3
    assert len(invocations(tmp_path)) == 1  # preview ran; the real pass did not


def test_wrong_confirmation_aborts(tmp_path):
    script = make_harness(tmp_path)
    rc, _out = run_with_tty(script, ["site.yml", "--limit", "zcrypto-red"], "zcrypto")
    assert rc == 3
    assert len(invocations(tmp_path)) == 1


def test_typed_limit_runs_the_real_pass(tmp_path):
    script = make_harness(tmp_path)
    rc, _out = run_with_tty(script, ["site.yml", "--limit", "zcrypto-red"], "zcrypto-red")
    assert rc == 0
    inv = invocations(tmp_path)
    assert len(inv) == 2
    assert "--check" in inv[0] and "--diff" in inv[0]
    assert "--check" not in inv[1] and "--limit zcrypto-red" in inv[1]


def test_limit_equals_form_is_parsed(tmp_path):
    script = make_harness(tmp_path)
    rc, out = run_with_tty(script, ["site.yml", "--limit=zcrypto-ops"], "zcrypto-ops")
    assert rc == 0
    assert "zcrypto-ops" in out
    assert len(invocations(tmp_path)) == 2


# --- the machine line: every real pass leaves one JSON record, the operator types none of it ----------
# The digest, the timestamp and the target of every converge used to be hand-typed into
# docs/reference/fleet-pins.md afterwards -- 15 commits on one rollout branch, and a digest written
# from memory is the one operand a rollback cannot afford to have wrong. The script knows all three
# at the moment the pass returns, so it writes them.

import json  # noqa: E402 -- the block above is the file's own section header


def run_recording(tmp_path, args, reply="zcrypto-red", env=None, run_sh=None):
    script = make_harness(tmp_path)
    if run_sh is not None:  # make_harness rewrites run.sh, so a custom fake must land AFTER it
        (tmp_path / "run.sh").write_text(run_sh)
    log = tmp_path / "deploy-log.jsonl"
    full_env = {"ZCRYPTO_DEPLOY_LOG": str(log), **(env or {})}
    for k, v in full_env.items():
        os.environ[k] = v
    try:
        rc, out = run_with_tty(script, args, reply)
    finally:
        for k in full_env:
            os.environ.pop(k, None)
    return rc, out, log


def test_a_real_pass_appends_one_machine_line(tmp_path):
    rc, _out, log = run_recording(
        tmp_path,
        [
            "site.yml",
            "--limit",
            "zcrypto-red",
            "--tags",
            "capture",
            "-e",
            "capture_image_digest=sha256:abc123",
            "-e",
            "converge_primary=true",
        ],
    )
    assert rc == 0
    lines = log.read_text().splitlines()
    assert len(lines) == 1, lines
    rec = json.loads(lines[0])
    assert rec["limit"] == "zcrypto-red" and rec["playbook"] == "site.yml" and rec["rc"] == 0
    assert rec["tags"] == "capture"
    assert rec["extra_vars"] == {"capture_image_digest": "sha256:abc123", "converge_primary": "true"}
    assert rec["ts"].endswith("Z") and "T" in rec["ts"]
    assert set(rec) >= {"ts", "playbook", "limit", "tags", "extra_vars", "revision", "dirty", "rc"}


def test_a_failed_real_pass_is_recorded_with_its_rc_and_the_rc_propagates(tmp_path):
    """A failed converge may have half-applied; the record says it happened and how it ended."""
    rc, _out, log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto-red"])
    assert rc == 0
    # The preview must succeed for the real pass to run at all, so the failure is injected on the
    # real invocation only -- the one whose args carry no --check.
    failing_real_pass = (
        '#!/usr/bin/env bash\necho "$@" >> "$(dirname "$0")/invocations.log"\n'
        'case " $* " in *" --check "*) exit 0 ;; esac\nexit 7\n'
    )
    rc, _out, log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto-red"], run_sh=failing_real_pass)
    assert rc == 7
    recs = [json.loads(ln) for ln in log.read_text().splitlines()]
    assert [r["rc"] for r in recs] == [0, 7]


def test_an_unwritable_log_is_loud_and_never_changes_the_pass_rc(tmp_path):
    """The pass already ran; its rc is the truth. A record that cannot land is printed for the
    operator to append by hand -- never a converge failure that did not happen, never silent."""
    rc, out, _log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red"],
        env={"ZCRYPTO_DEPLOY_LOG": str(tmp_path / "no-such-dir" / "deploy-log.jsonl")},
    )
    assert rc == 0
    assert "RECORD FAILED" in out and '"limit": "zcrypto-red"' in out


def test_a_preview_only_run_records_nothing(tmp_path):
    script = make_harness(tmp_path)
    log = tmp_path / "deploy-log.jsonl"
    rc = run_no_tty(script, ["site.yml", "--limit", "zcrypto-red", "--check"], env={"ZCRYPTO_DEPLOY_LOG": str(log)})
    assert rc.returncode == 0
    assert not log.exists()


def test_an_aborted_confirm_records_nothing(tmp_path):
    rc, _out, log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto-red"], reply="wrong")
    assert rc == 3
    assert not log.exists()
