"""zcrypto-panel-regenerate: delete-and-rebuild as one refusing flow (spec 00083 D2)."""

import os
import pty
import signal
import subprocess
import time
from pathlib import Path

import pytest

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
# `is-active` mirrors REAL systemd: it prints the state and exits 0 only for active/reloading --
# `activating` prints and exits 3. That is not a detail: the materialize unit is Type=oneshot, so an
# hourly run in flight sits in `activating` for its whole duration, and a guard written as
# `systemctl is-active --quiet` (exit code only) is blind to exactly the case it exists to catch.
STUB_SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$CALL_LOG"
case "$*" in
  is-active*) s="${FAKE_UNIT_ACTIVE:-inactive}"
              echo "$s"
              case "$s" in active|reloading) exit 0 ;; *) exit 3 ;; esac ;;
  *--wait*) exit ${FAKE_UNIT_RC:-0} ;;
esac
exit 0
"""
# The stub logs to CALL_LOG alongside systemctl: `systemctl start …timer` prints nothing, so an
# ordered log covering both commands is the only place the journal read's position between the
# rebuild and the timer restart is observable.
#
# The emitted text mirrors the real completion line field-for-field (cli/panel/command.py), with the
# `-o short-iso` timestamp the script now asks for: a harness whose model of the line is wrong
# teaches the wrong shape to whoever reads it next.
# The argv goes to its OWN file, not into CALL_LOG: the ordering assertions need a stable marker,
# while the flags need pinning separately.
JOURNAL_READ = "journalctl completion-read"
STUB_JOURNALCTL = (
    "#!/usr/bin/env bash\n"
    f'echo "{JOURNAL_READ}" >> "$CALL_LOG"\n'
    'echo "$*" >> "$CALL_LOG.journalctl-argv"\n'
    'echo "2026-08-03T10:00:05+0000 ops zcrypto-panel[1] panel materialize complete pairs=10'
    " pairs_out_of_scope=2 hours_written=6370 hours_skipped=0 hours_unsettled=1"
    ' hours_unanchored=2 rows=22827108 errors=0"\n'
)
STUB_DU_SMALL = '#!/usr/bin/env bash\necho -e "1\\t$2"\n'
STUB_DU_HUGE = '#!/usr/bin/env bash\necho -e "99999999\\t$2"\n'
# A du that fails on ONE of its two inputs. The canonical tree is the NFS-side one that goes away
# when the NAS mount hangs (ro,soft -> EIO); the overlay is local. Both must refuse identically.
STUB_DU_FAIL = """#!/usr/bin/env bash
case "$2" in
  *%s) echo "du: cannot read directory '$2': Input/output error" >&2; exit 1 ;;
esac
echo -e "1\\t$2"
"""


def render(tmp_path, du_stub, panel_subdir="l2-panel", data_dir=None):
    text = TEMPLATE.read_text()
    data = tmp_path / "data"
    nas = tmp_path / "nas"
    (data / "l2-panel").mkdir(parents=True)
    (data / "l2-panel" / "row.parquet").write_text("x")
    (data / "capture-reconciled").mkdir()
    (nas / "capture-segments").mkdir(parents=True)
    overrides = {"ops_panel_subdir": panel_subdir}
    if data_dir is not None:
        overrides["ops_data_dir"] = data_dir
    # Render through Jinja, the way Ansible does — NOT str.replace: a str.replace harness cannot
    # see a Jinja syntax error at all.
    values = {var: val.format(data=data, nas=nas) for var, val in {**VARS, **overrides}.items()}
    text = ansible_render(text, **values)
    assert "{{" not in text and "{%" not in text, "unrendered template syntax left behind"
    script = tmp_path / "zcrypto-panel-regenerate"
    script.write_text(text)
    script.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("date", STUB_DATE), ("systemctl", STUB_SYSTEMCTL), ("du", du_stub), ("journalctl", STUB_JOURNALCTL)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "CALL_LOG": str(tmp_path / "calls.log")}
    return script, env, data / "l2-panel", tmp_path / "calls.log"


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


# Step 1 is two calls, not one: the timer stop, then the in-flight check the stop does NOT cover
# (stopping a timer never touches a run already under way).
STEP1 = [
    "systemctl stop zcrypto-panel-materialize.timer",
    "systemctl is-active zcrypto-panel-materialize.service",
]
TIMER_RESTART = "systemctl start zcrypto-panel-materialize.timer"


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
    assert calls(log) == [*STEP1, TIMER_RESTART]


@pytest.mark.parametrize("boolish", ["true", "TRUE", "false", "1", "yes"])
def test_boolean_override_refused(boolish, tmp_path):
    # Parametrized because a single value pins only its own arm: dropping the false/1/yes clauses
    # left the suite green (measured), so each refusal carries its own case.
    script, env, panel, log = render(tmp_path, STUB_DU_HUGE)
    r = subprocess.run(
        ["setsid", str(script), "--override", boolish], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
    )
    assert r.returncode == 2
    assert panel.exists()
    # Argument validation precedes step 1: a refused override must not have disturbed the timer.
    assert calls(log) == []


@pytest.mark.parametrize(
    ("reason", "expect_rc"),
    [("12345678", 2), ("123456789", 3)],  # 8 chars refused; 9 accepted, so the run reaches the tty gate
)
def test_override_length_boundary_is_behavioural(reason, expect_rc, tmp_path):
    # The 8/9 boundary was pinned only by a literal string match on the guard line, so an offset
    # typo (:1, :9, :20) failed nothing but that assert. This runs the rendered script instead.
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    r = subprocess.run(
        ["setsid", str(script), "--override", reason], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
    )
    assert r.returncode == expect_rc
    assert panel.exists()


@pytest.mark.parametrize("failing", ["capture-segments", "capture-reconciled"])
def test_a_failing_du_refuses_at_the_sizing_step(failing, tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_FAIL % failing)
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode != 0
    assert panel.exists()  # nothing deleted
    # It must refuse AT the sizing step rather than wander on to the next gate. Combined into one
    # arithmetic expansion the CANONICAL-side failure is swallowed -- the assignment takes the last
    # substitution's status and the empty operand parses as unary plus -- so the ETA is computed
    # from the overlay alone and the run continues past its own central refusal (measured), exactly
    # when the NAS mount is the thing that is broken.
    assert "no controlling terminal" not in r.stderr
    # Timer deliberately left stopped: the hourly materialize must not resume against an input tree
    # this host could not even stat, and the still-armed dead-man check pages on the missed ping.
    assert calls(log) == STEP1


def test_no_tty_refuses_restarts_timer_and_deletes_nothing(tmp_path):
    # small du: the sizing gate passes, so setsid's denied /dev/tty is the ONLY refusal left --
    # this pins the no-tty path's own contract instead of inferring it from the deadline test.
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 3
    assert "no controlling terminal" in r.stderr
    assert panel.exists()  # nothing deleted
    assert calls(log) == [*STEP1, TIMER_RESTART]


@pytest.mark.parametrize("state", ["active", "activating"])
def test_an_in_flight_materialize_run_refuses_and_restarts_the_timer(state, tmp_path):
    # Step 4's `rm -rf` under a live materialize half-deletes a tree the running process believes
    # it owns.
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    env["FAKE_UNIT_ACTIVE"] = state
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 3
    assert "in flight" in r.stderr  # WHICH refusal: setsid's no-tty gate is also rc 3
    assert panel.exists()  # nothing deleted
    assert calls(log) == [*STEP1, TIMER_RESTART]


def test_empty_rendered_panel_subdir_refuses_before_touching_anything(tmp_path):
    # An empty ops_panel_subdir renders PANEL_ROOT as the ops DATA ROOT itself, and this script's
    # payload is `rm -rf` on it -- the reconciled overlay, the liquidations tree and the textfile
    # dir go with it. `set -u` cannot see it (the var IS set, to a string with an empty component)
    # and Ansible refuses only UNDEFINED vars, so the guard has to live in the script.
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL, panel_subdir="")
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 2
    assert calls(log) == []  # refused before the timer was even touched
    assert panel.exists()
    assert (panel.parent / "capture-reconciled").exists()  # the sibling tree the rm -rf would take


def test_empty_rendered_data_dir_refuses_before_touching_anything(tmp_path):
    # The OTHER half of the same rendered path. An empty ops_data_dir puts PANEL_ROOT at
    # "/<subdir>" -- a path at the FILESYSTEM root, outside anything this host's data layout owns --
    # and the subdir guard alone says nothing about it, because the subdir is perfectly non-empty.
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL, data_dir="")
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 2
    assert "empty half" in r.stderr
    assert calls(log) == []  # refused before the timer was even touched
    assert panel.exists()
    assert (panel.parent / "capture-reconciled").exists()


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


def run_with_ctty_but_piped_stdin(script, env, piped_reply, deadline=3.0):
    """Controlling pty attached (so the tty gate opens) but stdin is a PIPE carrying the reply.

    The CHANNEL is the subject. Every other pty test here drives the gate through the pty, which IS
    stdin there, so a `read reply` written without `< /dev/tty` passes all of them. Here the gate
    finds a controlling terminal, nobody types on it, and the word the operator never said arrives
    on a pipe. Returns the exit code, or None if still running at the deadline (blocked on
    /dev/tty -- the correct behavior). Kills it either way.
    """
    r, w = os.pipe()
    pid, master = pty.fork()  # child: the pty slave is fd 0/1/2 AND the controlling terminal
    if pid == 0:
        try:
            os.environ.update(env)
            os.close(w)
            os.dup2(r, 0)  # stdin becomes the pipe; the pty stays the controlling terminal
            os.close(r)
            os.execv(str(script), [str(script)])
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


def test_pipe_cannot_drive_the_paused_gate(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc = run_with_ctty_but_piped_stdin(script, env, "paused")
    assert rc != 0  # rc 3 (aborted) or None (still waiting on the silent tty); 0 means it converged
    assert panel.exists()  # the point of no return was never crossed
    assert calls(log) == STEP1  # step 1 only -- no rebuild, and no timer restart either (killed)


def test_happy_path_order_and_checklist(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc, out = run_tty(script, env, ["paused"])
    assert rc == 0
    assert not panel.exists()
    seq = calls(log)
    # The journal read must sit between the rebuild and the timer restart: the timer is
    # Persistent=true, so a restart can fire a queued catch-up tick whose numbers then win `tail -1`.
    assert seq == [
        *STEP1,
        "systemctl start --wait zcrypto-panel-materialize.service",
        JOURNAL_READ,
        TIMER_RESTART,
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


# --- what the render path itself must guarantee ----------------------------------------------
# The rule these tests enforce: render through Ansible's own engine, then check the result is
# valid bash.


def ansible_render(source, **values):
    """Render through ANSIBLE's templar, not a bare jinja2.Environment.

    Bare Jinja defaults to trim_blocks=False while Ansible sets it True, so a template can render
    perfectly here and still install broken shell on the host.
    """
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    return Templar(loader=DataLoader(), variables=values).template(trust_as_template(source))


def test_template_renders_to_valid_shell_through_ansible():
    """The ground truth this file exists to protect: what Ansible installs must be valid bash."""
    rendered = ansible_render(
        TEMPLATE.read_text(),
        ops_data_dir="/var/lib/zcrypto-ops",
        ops_panel_subdir="l2-panel",
        ops_nas_mount="/mnt/zhao-crypto",
        ops_capture_subdir="capture-segments",
        ops_reconciled_subdir="capture-reconciled",
    )
    assert "{%" not in rendered and "{{" not in rendered
    # the override length test must survive as its own statement, not welded to the next line
    assert '[ -z "${override:8}" ]' in rendered
    subprocess.run(["bash", "-n", "/dev/stdin"], input=rendered, text=True, check=True)


def test_every_ansible_template_is_parseable_jinja():
    """Repo-wide: a template that cannot parse never installs, whatever its tests say."""
    jinja2 = pytest.importorskip("jinja2")
    # Settings mirror Ansible's, though for PARSING they are inert: trim_blocks changes rendered
    # whitespace, not what parses. This sweep therefore catches the comment-tag class only — the
    # weld class needs a render, which tests/test_infra_shell_templates_render.py provides.
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=False)
    root = TEMPLATE.resolve().parent.parent.parent.parent  # infra/ansible
    templates = sorted(root.rglob("*.j2"))
    assert templates, "no templates found — the glob is wrong, not the tree"
    broken = []
    for path in templates:
        try:
            env.parse(path.read_text())
        except jinja2.TemplateSyntaxError as exc:
            broken.append(f"{path.relative_to(root)}:{exc.lineno}: {exc}")
    assert not broken, "unparseable Jinja templates: " + "; ".join(broken)


# The closing checklist is the ONLY artifact this routine leaves an operator.
def test_the_closing_checklist_is_safe_and_ordered(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc, out = run_tty(script, env, ["paused"])
    assert rc == 0

    # (c) The completion line must be captured BEFORE the timer is restarted. The timer is
    # Persistent=true, so restarting it can fire a queued catch-up tick whose numbers then win
    # `tail -1` -- the T0111 drill saw exactly that. Asserted on the CALL LOG, not on stdout:
    # `systemctl start …timer` prints nothing, so hoisting it above the journal read while leaving
    # `echo "timer restarted."` in place is invisible to a stdout-position check.
    assert "completion line" in out, "the rebuild's completion line is not printed at all"
    seq = calls(log)
    assert JOURNAL_READ in seq, "the journal was never read"
    assert seq.index(JOURNAL_READ) < seq.index(TIMER_RESTART), (
        "the timer is restarted BEFORE the journal read, so a queued catch-up tick can win `tail -1` and the operator records the wrong run's counters"
    )
    # The read must be ANCHORED to this rebuild. `systemctl start --wait` returning does not prove
    # journald committed the unit's last lines, and an unanchored `tail -1` hands back the PREVIOUS
    # run's numbers -- the wrong-run failure this block exists to prevent, in a second shape.
    argv = Path(f"{log}.journalctl-argv").read_text()
    assert "--since @" in argv, "the journal read is not anchored to this rebuild's start"
    assert "-o short-iso" in argv, "the line carries no timestamp, so it cannot be tied to a run"

    # The success branch actually ran -- without a journalctl stub this silently took the fallback.
    assert "hours_unanchored=2" in out and "hours_unsettled=1" in out, (
        "the journal line did not reach the operator; the block fell through to its fallback"
    )

    # Un-pause is the timer's only liveness signal, so it comes first; the orphan sweep can wait.
    assert out.index("Un-pause") < out.index("NAS copy"), "un-pause must precede the NAS item"

    # (a) The trigger must not claim a schema bump orphans paths -- it forces a regeneration but
    # rewrites identical paths. The path-orphaning cases are a grid rename and a departed pair.
    assert "owed ONLY when" in out
    assert "a schema bump is NOT one" in out, "the checklist still implies a schema change orphans paths"
    assert "left the archive" in out, "the departed-pair case (the one nothing else catches) is missing"

    # (b) comm needs the locale pin as much as the sorts do, or it exits 1 on C-sorted input.
    assert "LC_ALL=C comm -13" in out, "comm is not locale-pinned; it errors under a UTF-8 locale"

    # A measurement that could not be read is not a zero.
    assert "an unread count is not a zero" in out, "no safe default stated for unreadable counts"
    # The reconcile step must name an operand. `hours_unanchored` is a COUNT, never which hours, so
    # "reconcile every candidate against the counts" was itself a step naming nothing runnable --
    # the original defect one layer down. The WARNING grep is where the hours actually are.
    assert "grep unanchored" in out, "the reconcile step still names no operand"
    assert "not a map" in out, (
        "the WARNING is suppressed for repeats within a run, so it names each run's START, not every"
        " hour -- the checklist must say so or it over-promises"
    )

    # The action needs a host and a path -- its absence is what made the item unfindable.
    assert "READ-ONLY here" in out and "/volume1/ZhaoCrypto" in out, (
        "the checklist still does not say WHERE to delete, which was the original defect"
    )
