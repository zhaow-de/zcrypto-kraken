"""zcrypto-panel-regenerate: delete-and-rebuild as one refusing flow (spec 00083 D2).

The template renders with fixed test vars; systemctl/du/date are PATH stubs writing a call
log, so ordering claims ("nothing deleted before the typed gate") are asserted against what
actually ran. /dev/tty gates run under a pty.
"""

import os
import pty
import subprocess
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "roles" / "ops" / "templates" / "panel-regenerate.sh.j2"

VARS = {
    "ops_data_dir": "{data}",
    "ops_panel_subdir": "l2-panel",
    "ops_nas_mount": "{nas}",
    "ops_capture_subdir": "capture-segments",
    "ops_reconciled_subdir": "capture-reconciled",
}

# Stubs: date is pinned to 2026-08-03 10:00:00 UTC (epoch 1785751200), far from 02:25.
STUB_DATE = """#!/usr/bin/env bash
case "$*" in
  "-u +%s") echo 1785751200 ;;
  "-u +%F") echo 2026-08-03 ;;
  *-d*) exec /bin/date "$@" ;;
esac
"""
STUB_SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$CALL_LOG"
case "$*" in *--wait*) exit ${FAKE_UNIT_RC:-0} ;; esac
exit 0
"""
STUB_DU_SMALL = '#!/usr/bin/env bash\necho -e "1\\t$2"\n'
STUB_DU_HUGE = '#!/usr/bin/env bash\necho -e "99999999\\t$2"\n'


def render(tmp_path, du_stub):
    text = TEMPLATE.read_text()
    data = tmp_path / "data"
    nas = tmp_path / "nas"
    (data / "l2-panel").mkdir(parents=True)
    (data / "l2-panel" / "row.parquet").write_text("x")
    (data / "capture-reconciled").mkdir()
    (nas / "capture-segments").mkdir(parents=True)
    for var, val in VARS.items():
        text = text.replace("{{ %s }}" % var, val.format(data=data, nas=nas))
    assert "{{" not in text, "unrendered template var left behind"
    script = tmp_path / "zcrypto-panel-regenerate"
    script.write_text(text)
    script.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("date", STUB_DATE), ("systemctl", STUB_SYSTEMCTL), ("du", du_stub)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "CALL_LOG": str(tmp_path / "calls.log")}
    return script, env, data / "l2-panel", tmp_path / "calls.log"


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


def run_tty(script, env, replies, args=()):
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(env)
        os.execv(str(script), [str(script), *args])
    out = b""
    replies = list(replies)
    try:
        while True:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
            if b"to continue" in out and replies:
                os.write(fd, replies.pop(0).encode() + b"\n")
                out = out.replace(b"to continue", b"to-continue-consumed")
    except OSError:
        pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode(errors="replace")


def test_eta_over_deadline_refuses_and_restarts_timer(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_HUGE)
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 3
    # WHICH refusal fired, not just that one did: setsid also denies /dev/tty, and that gate's
    # refusal is rc 3 with the same [stop, start] call log and the same intact tree. Without this
    # the deadline comparison can be deleted outright and the test still passes (measured).
    assert "02:25 UTC auto-reboot" in r.stderr
    assert panel.exists()  # nothing deleted
    assert calls(log) == [
        "systemctl stop zcrypto-panel-materialize.timer",
        "systemctl start zcrypto-panel-materialize.timer",
    ]


def test_boolean_override_refused(tmp_path):
    script, env, panel, _log = render(tmp_path, STUB_DU_HUGE)
    r = subprocess.run(
        ["setsid", str(script), "--override", "true"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
    )
    assert r.returncode == 2
    assert panel.exists()


def test_reason_override_crosses_the_deadline(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_HUGE)
    rc, out = run_tty(script, env, ["paused"], args=("--override", "rebuild must land before the audit window"))
    assert rc == 0
    assert "override accepted" in out
    assert not panel.exists()
    assert "systemctl start --wait zcrypto-panel-materialize.service" in calls(log)


def test_abort_at_pause_gate_deletes_nothing(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc, _out = run_tty(script, env, ["nope"])
    assert rc == 3
    assert panel.exists()
    assert "systemctl start zcrypto-panel-materialize.timer" in calls(log)  # resumed


def test_happy_path_order_and_checklist(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc, out = run_tty(script, env, ["paused"])
    assert rc == 0
    assert not panel.exists()
    seq = calls(log)
    assert seq == [
        "systemctl stop zcrypto-panel-materialize.timer",
        "systemctl start --wait zcrypto-panel-materialize.service",
        "systemctl start zcrypto-panel-materialize.timer",
    ]
    assert "NAS" in out and "Un-pause" in out and "ops_panel_timer_hold" in out


def test_failed_rebuild_leaves_timer_stopped(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    env["FAKE_UNIT_RC"] = "1"
    rc, out = run_tty(script, env, ["paused"])
    assert rc == 4
    seq = calls(log)
    assert "systemctl start zcrypto-panel-materialize.timer" not in seq  # stays stopped
    assert "investigate" in out
