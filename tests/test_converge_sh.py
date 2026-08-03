"""converge.sh: preview-first, typed-limit confirm, then the real pass (spec 00083 D1).

Every test copies the script into a scratch dir beside a FAKE run.sh that appends its argv
(one line per invocation) to invocations.log — the tests assert on what actually ran, never
only on exit codes.
"""

import os
import pty
import shutil
import stat
import subprocess
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
