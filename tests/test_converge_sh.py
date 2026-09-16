"""converge.sh: preview-first, typed-limit confirm, then the real pass (spec 00083 D1)."""

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

    Every other test drives the confirm through the pty, where the pty IS stdin, so a script that
    read `reply` from stdin instead of /dev/tty passes all of them (measured).

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


def _clear_deploy_env(monkeypatch):
    """`ZCRYPTO_DEPLOY_LOG` / `ZCRYPTO_ANSIBLE_DIR`, cleared because pty.fork() inherits pytest's
    os.environ verbatim: a developer shell exporting either would send the script's writes outside
    the fixture path the assertions read. `run_recording` sets both on `os.environ` on purpose and
    must never be routed through this helper."""
    monkeypatch.delenv("ZCRYPTO_DEPLOY_LOG", raising=False)
    monkeypatch.delenv("ZCRYPTO_ANSIBLE_DIR", raising=False)


def test_typed_limit_runs_the_real_pass(tmp_path, monkeypatch):
    _clear_deploy_env(monkeypatch)
    script = make_harness(tmp_path)
    rc, _out = run_with_tty(script, ["site.yml", "--limit", "zcrypto-red"], "zcrypto-red")
    assert rc == 0
    inv = invocations(tmp_path)
    assert len(inv) == 2
    assert "--check" in inv[0] and "--diff" in inv[0]
    assert "--check" not in inv[1] and "--limit zcrypto-red" in inv[1]


def test_limit_equals_form_is_parsed(tmp_path, monkeypatch):
    _clear_deploy_env(monkeypatch)
    script = make_harness(tmp_path)
    rc, out = run_with_tty(script, ["site.yml", "--limit=zcrypto-ops"], "zcrypto-ops")
    assert rc == 0
    assert "zcrypto-ops" in out
    assert len(invocations(tmp_path)) == 2


# --- the machine line: every real pass leaves one JSON record, the operator types none of it ----------
# A digest written from memory is the one operand a rollback cannot afford to have wrong, and the
# script knows the digest, the timestamp and the target at the moment the pass returns.

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


def test_a_json_extra_var_is_recorded_beside_the_k_equals_v_ones(tmp_path):
    """A `-e` carrying JSON lands in the row, and a JSON value holding `=` is not split on it.

    `canary_override` is a reason (`fleet-deploys.md`), and `k=v` truncates one at the first space.
    """
    reason = "rolled back: the venue answers EGeneral:Permission denied, so exec_armed=0 stands"
    rc, _out, log = run_recording(
        tmp_path,
        [
            "site.yml",
            "--limit",
            "zcrypto-red",
            "-e",
            "capture_image_digest=sha256:abc123",
            "-e",
            json.dumps({"canary_override": reason}),
        ],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"capture_image_digest": "sha256:abc123", "canary_override": reason}


def test_a_braced_operand_that_is_not_json_is_dropped_rather_than_split_into_a_key(tmp_path):
    """The safe failure for an unreadable `-e` is a SHORT row, never a populated-looking wrong one.

    Ansible YAML-loads `{`/`[`; this recorder runs under the system `python3`, which has no PyYAML,
    so a YAML-only spelling is dropped rather than split on the `=` inside the reason.
    """
    yaml_flow = '{canary_override: "rolled back, exec_armed=0 stands"}'
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red", "-e", "capture_image_digest=sha256:abc123", "-e", yaml_flow],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"capture_image_digest": "sha256:abc123"}, rec["extra_vars"]


def test_both_option_names_in_both_argparse_forms_reach_the_row(tmp_path):
    """A spelling this collector misses is a var the row never mentions, which reads as absent.

    `docs/reference/drill-log.md` takes an empty `extra_vars` as proof that nothing was overridden.
    The boundary is the two option names matched exactly, in both of argparse's forms; outside it
    are the `allow_abbrev` spellings and `@file`.
    """
    reason = "secondary unreachable, incident rollback"
    rc, _out, log = run_recording(
        tmp_path,
        [
            "site.yml",
            "--limit",
            "zcrypto-red",
            "--extra-vars",
            json.dumps({"canary_override": reason}),
            "--extra-vars=capture_image_digest=sha256:abc123",
            "--extra-vars",
            "engine_window_override=incident",
            "-econverge_primary=true",
            "-e",
            "pins_override=stale nas_apply_compose=true",
            "-e",
            "@vars.json",
        ],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {
        "canary_override": reason,
        "capture_image_digest": "sha256:abc123",
        "engine_window_override": "incident",
        "converge_primary": "true",
        "pins_override": "stale",
        "nas_apply_compose": "true",
    }, rec["extra_vars"]


def test_the_word_after_an_attached_extra_vars_is_not_booked_as_a_variable(tmp_path):
    """`--extra-vars=K=V` carries its own value, so the NEXT argv word is a flag, not a var.

    A `--extra-var*` prefix arm matches the attached form too and books `--tags=…` as a variable.
    """
    rc, _out, log = run_recording(
        tmp_path,
        [
            "site.yml",
            "--limit",
            "zcrypto-red",
            "--extra-vars=capture_image_digest=sha256:abc123",
            "--tags=capture,engine",
        ],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"capture_image_digest": "sha256:abc123"}, rec["extra_vars"]
    assert rec["tags"] == "capture,engine"


def test_a_braced_operand_carrying_newlines_is_recorded_whole(tmp_path):
    """A pretty-printed `-e '{...}'` books `canary_override` exactly as the one-line form does.

    Measured against `load_extra_vars`; operands therefore travel RS-separated, not newline-joined.
    """
    reason = "rolled back, exec_armed=0 stands"
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red", "-e", json.dumps({"canary_override": reason}, indent=2)],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"canary_override": reason}, rec["extra_vars"]


def test_a_brace_behind_a_leading_space_is_not_braced_here_either(tmp_path):
    """`load_extra_vars` tests the operand's RAW first character, so a leading space is not JSON.

    Measured, this operand: ansible books a garbage key and NO `canary_override`, so the canary
    assert fires and the converge does not proceed. The row mirrors that.
    """
    rc, _out, log = run_recording(
        tmp_path,
        [
            "site.yml",
            "--limit",
            "zcrypto-red",
            "-e",
            "capture_image_digest=sha256:abc123",
            "-e",
            ' {"canary_override": "rolled back, exec_armed=0 stands"}',
        ],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {
        "capture_image_digest": "sha256:abc123",
        "rolled back, exec_armed": "0 stands}",
    }, rec["extra_vars"]
    assert "canary_override" not in rec["extra_vars"]


def test_an_equals_after_the_short_flag_is_dropped_the_way_argparse_drops_it(tmp_path):
    """`-e=K=V` is `K=V` to ansible -- argparse strips the `=` -- so the row books `K`, not `""`.

    Measured against `load_extra_vars`, which returns `{"canary_override": "x"}` for
    `-e=canary_override=x`.
    """
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red", "-e=capture_image_digest=sha256:abc123"],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"capture_image_digest": "sha256:abc123"}, rec["extra_vars"]


def test_a_tab_inside_an_operand_stays_in_the_value_and_a_newline_splits_it(tmp_path):
    """Ansible's `split_args` breaks an operand on the space and the newline, never the tab.

    Measured: `-e $'a=1\tb=2'` books `{'a': '1\tb=2'}`, `-e $'a=1\nb=2'` books both. Plain
    `shlex.split` splits on the tab too and would name a variable the pass never received.
    """
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red", "-e", "a=1\tb=2", "-e", "c=3\nd=4"],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"a": "1\tb=2", "c": "3", "d": "4"}, rec["extra_vars"]


def test_the_short_tags_spellings_reach_the_row(tmp_path):
    """Three counters read the `tags` cell, and `-t engine` is `--tags engine` to ansible.

    `count-list.sh engine-rows-outside-the-gap` is scoped by `fleet-deploys.md` to rows whose tags
    include `engine`, so a tag cell left empty drops the run out of the count that watches it.
    """
    for args, expected in (
        (["-t", "capture,engine"], "capture,engine"),
        (["-tcapture,engine"], "capture,engine"),
        (["--tags=capture,engine"], "capture,engine"),
    ):
        path = tmp_path / args[0].strip("-=,")[:6]
        path.mkdir()
        rc, _out, log = run_recording(path, ["site.yml", "--limit", "zcrypto-red", *args])
        assert rc == 0
        rec = json.loads(log.read_text().splitlines()[0])
        assert rec["tags"] == expected, (args, rec["tags"])


def test_a_spelling_the_collector_does_not_read_is_announced_not_swallowed(tmp_path):
    """A short row is read as proof nothing was overridden, so the drop cannot be silent.

    `--extra-var k=v` is a real extra var to ansible (`allow_abbrev`) and is not collected here;
    the operator sees that at the console, at the moment of the pass.
    """
    for spelling in ("--extra-var", "-ve"):
        path = tmp_path / spelling.strip("-")
        path.mkdir()
        rc, out, log = run_recording(path, ["site.yml", "--limit", "zcrypto-red", spelling, "canary_override=abcdefghij"])
        assert rc == 0
        rec = json.loads(log.read_text().splitlines()[0])
        assert rec["extra_vars"] == {}, (spelling, rec["extra_vars"])
        assert "NOT RECORDED" in out and spelling in out, (spelling, out)


def test_an_operand_that_books_nothing_is_announced_not_swallowed(tmp_path):
    """The YAML-flow dialect ansible accepts and this recorder cannot read leaves the same proof.

    It is dropped rather than split on the `=` inside it, and the drop is printed: without that,
    the row is indistinguishable from a converge that overrode nothing.
    """
    rc, out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red", "-e", '{canary_override: "rolled back, x=0"}'],
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {}, rec["extra_vars"]
    assert "NOT RECORDED" in out and "canary_override" in out


def test_two_tag_flags_join_the_cell_the_way_ansible_unions_them(tmp_path):
    """`--tags` appends in ansible: both sets run, so the cell names both.

    Overwriting kept the last flag only, and `count-list.sh engine-rows-outside-the-gap` selects
    rows whose `tags` cell names `engine` — an engine converge invoked with two tag flags dropped
    out of the count that watches it, with nothing on the console.
    """
    rc, _out, log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto-red", "-t", "engine", "--tags", "capture"])
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["tags"] == "engine,capture", rec["tags"]


def test_every_check_mode_spelling_stops_before_the_real_pass(tmp_path):
    """`-C` and `--che` are check mode to ansible, so a row for them would say a pass converged.

    The preview runs, nothing else does, and no row is appended — the same as the literal `--check`.
    """
    for flag in ("-C", "--che", "--chec", "-vC"):
        path = tmp_path / flag.strip("-")
        path.mkdir()
        script = make_harness(path)
        r = run_no_tty(script, ["site.yml", "--limit", "zcrypto-red", flag])
        assert r.returncode == 0, (flag, r.returncode, r.stderr)
        inv = invocations(path)
        assert len(inv) == 1 and "--check" in inv[0], (flag, inv)


def test_an_ordinary_attached_short_is_not_announced(tmp_path):
    """The cluster arm reads short FLAGS, never the value attached to one.

    `-ihosts.ini` overrides nothing; announcing it teaches the operator to read past the line that
    matters, which is the whole value of the announcement.
    """
    rc, out, log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto-red", "-ihosts.ini", "-e", "a=1"])
    assert rc == 0
    assert "NOT RECORDED" not in out, out
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"a": "1"}, rec["extra_vars"]


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


# --- the committed pins: a tier whose digest is a FILE must still name it in the record -------------
# The NAS pin is `nas_capture_image` in host_vars, so no `-e` carries it and the operand is
# recoverable only as revision-plus-committed-file, which defeats the point of the machine line.
# Read from the plaintext vars file, never `ansible-inventory --host`, which decrypts the vault.


def write_host_vars(tmp_path, host, body):
    d = tmp_path / "ansible" / "host_vars" / host
    d.mkdir(parents=True, exist_ok=True)
    (d / "vars.yml").write_text(body)
    return tmp_path / "ansible"


def test_a_committed_image_pin_is_recorded_even_though_no_dash_e_carries_it(tmp_path):
    ansible_dir = write_host_vars(
        tmp_path,
        "nas",
        "# a comment\n"
        "nas_capture_image: ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "9f" * 32 + "\n"
        "nas_alloy_image: grafana/alloy@sha256:" + "49" * 32 + "\n"
        "nas_stack_dir: /volume1/docker/zcrypto-archive\n",
    )
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "nas", "--tags", "nas", "-e", "nas_apply_compose=true"],
        reply="nas",
        env={"ZCRYPTO_ANSIBLE_DIR": str(ansible_dir)},
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["committed_pins"] == {
        "nas_capture_image": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "9f" * 32,
        "nas_alloy_image": "grafana/alloy@sha256:" + "49" * 32,
    }, rec["committed_pins"]
    assert "nas_stack_dir" not in rec["committed_pins"], "only digest-pinned image refs, not every var"


def test_a_limit_with_no_host_vars_records_an_empty_pin_map_not_a_missing_key(tmp_path):
    """A group limit, or a host whose pins are all extra-vars, must still produce the key -- a reader
    that has to distinguish 'absent' from 'none' cannot tell a new script from an old one."""
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto-red"],
        env={"ZCRYPTO_ANSIBLE_DIR": str(tmp_path / "ansible")},
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["committed_pins"] == {}


# --- `dirty` must describe the TREE ANSIBLE RENDERS, not the log this script just wrote ------------
# The flag means "revision does not fully describe what was deployed", which ansible rendering from
# the working tree makes real; the recorder's own appended line cannot affect that.


def make_repo_harness(tmp_path, monkeypatch):
    """A real git repo laid out as the script expects: <repo>/infra/ansible/scripts/converge.sh."""
    _clear_deploy_env(monkeypatch)
    repo = tmp_path / "repo"
    scripts = repo / "infra" / "ansible" / "scripts"
    scripts.mkdir(parents=True)
    (repo / "docs" / "reference").mkdir(parents=True)
    shutil.copy(SCRIPT, scripts / "converge.sh")
    (scripts / "run.sh").write_text(FAKE_RUN_SH)
    for name in ("converge.sh", "run.sh"):
        p = scripts / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    (repo / "docs" / "reference" / "deploy-log.jsonl").write_text("")
    # The fake run.sh writes invocations.log INSIDE the fixture repo, so without this the harness
    # dirties the very tree these tests measure -- and the script would look broken while being right.
    (repo / ".gitignore").write_text("invocations.log\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env, capture_output=True)
    return repo, scripts / "converge.sh"


def _dirty_of_last_record(repo):
    log = repo / "docs" / "reference" / "deploy-log.jsonl"
    return json.loads(log.read_text().splitlines()[-1])["dirty"]


def test_the_logs_own_append_does_not_make_the_next_converge_read_dirty(tmp_path, monkeypatch):
    repo, script = make_repo_harness(tmp_path, monkeypatch)
    rc, _ = run_with_tty(script, ["site.yml", "--limit", "nas"], "nas")
    assert rc == 0 and _dirty_of_last_record(repo) is False, "clean tree, first converge"
    # the line just written is now uncommitted -- the exact state that produced the false positive
    rc, _ = run_with_tty(script, ["site.yml", "--limit", "nas"], "nas")
    assert rc == 0
    assert _dirty_of_last_record(repo) is False, "the recorder's own line is not a dirty working tree"


def test_a_real_uncommitted_change_still_reads_dirty(tmp_path, monkeypatch):
    """The signal that matters must survive the fix -- ansible renders from the working tree, so a
    modified role really does mean `revision` understates what was deployed."""
    repo, script = make_repo_harness(tmp_path, monkeypatch)
    (repo / "infra" / "ansible" / "somerole.yml").write_text("- name: a task\n")
    rc, _ = run_with_tty(script, ["site.yml", "--limit", "nas"], "nas")
    assert rc == 0
    assert _dirty_of_last_record(repo) is True, "an uncommitted role change must still read dirty"
