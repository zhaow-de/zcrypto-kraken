"""converge.sh: preview-first, typed-limit confirm, then the real pass (spec 00083 D1)."""

import importlib.util
import os
import pty
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

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


def test_pipe_cannot_drive_the_confirm(tmp_path, monkeypatch):
    # The child is killed at the confirm, so its trap never removes the record file; this keeps that file in tmp_path.
    monkeypatch.setenv("TMPDIR", str(tmp_path))
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


DIGEST = "sha256:" + "a" * 64

PUBLISHED = [
    # Every shape ~/.zsh_history, the deploy log and the skills between them record. The engine leg
    # is the four-operand maximum; `--limit=` is the one attached spelling spec 00083 commits to.
    (
        [
            "--limit",
            "zcrypto",
            "--tags",
            "capture,engine",
            "-e",
            "converge_primary=true",
            "-e",
            f"capture_image_digest={DIGEST}",
            "-e",
            f"engine_image_digest={DIGEST}",
        ],
        "zcrypto",
        "capture,engine",
        {"converge_primary": "true", "capture_image_digest": DIGEST, "engine_image_digest": DIGEST},
    ),
    (["--limit=zcrypto-red", "-e", f"capture_image_digest={DIGEST}"], "zcrypto-red", "", {"capture_image_digest": DIGEST}),
    (["--limit", "nas", "--tags", "nas", "-e", "nas_apply_compose=true"], "nas", "nas", {"nas_apply_compose": "true"}),
    (["--limit", "nas", "--tags", "alloy"], "nas", "alloy", {}),
    (["--limit", "nas", "--tags", "alloy", "-e", "nas_apply_compose=true"], "nas", "alloy", {"nas_apply_compose": "true"}),
    (
        [
            "--limit",
            "zcrypto-ops",
            "-e",
            f"ops_image_digest={DIGEST}",
            "-e",
            f"ops_alloy_digest={DIGEST}",
            "-e",
            "liquidations_decision=roll-after",
        ],
        "zcrypto-ops",
        "",
        {"ops_image_digest": DIGEST, "ops_alloy_digest": DIGEST, "liquidations_decision": "roll-after"},
    ),
    (["--limit", "zaccess", "--tags", "access"], "zaccess", "access", {}),
    (["--limit", "zaccess", "--tags", "alloy"], "zaccess", "alloy", {}),
    (["--limit", "zcrypto", "--tags", "chrony"], "zcrypto", "chrony", {}),
    (["--limit", "zcrypto-ops", "-e", "ops_reconcile_mint=false"], "zcrypto-ops", "", {"ops_reconcile_mint": "false"}),
    (
        ["--limit", "zcrypto-ops", "-e", "access_ops_agentboard_live=true"],
        "zcrypto-ops",
        "",
        {"access_ops_agentboard_live": "true"},
    ),
    (
        ["--limit", "zcrypto", "--skip-tags", "engine", "-e", f"capture_alloy_digest={DIGEST}"],
        "zcrypto",
        "",
        {"capture_alloy_digest": DIGEST},
    ),
    (
        ["--limit", "zcrypto-red", "--tags", "alloy", "-e", f"capture_alloy_digest={DIGEST}"],
        "zcrypto-red",
        "alloy",
        {"capture_alloy_digest": DIGEST},
    ),
    (
        ["--limit", "zcrypto", "--tags", "alloy", "-e", "converge_primary=true", "-e", f"capture_alloy_digest={DIGEST}"],
        "zcrypto",
        "alloy",
        {"converge_primary": "true", "capture_alloy_digest": DIGEST},
    ),
    (
        [
            "--limit",
            "zcrypto",
            "--tags",
            "alloy,engine",
            "-e",
            "converge_primary=true",
            "-e",
            f"engine_image_digest={DIGEST}",
            "-e",
            f"capture_alloy_digest={DIGEST}",
        ],
        "zcrypto",
        "alloy,engine",
        {"converge_primary": "true", "engine_image_digest": DIGEST, "capture_alloy_digest": DIGEST},
    ),
    (
        [
            "--limit",
            "zcrypto-ops",
            "--tags",
            "ops",
            "-e",
            "ops_grafana_watchdog_probe_url=https://grafana-watchdog-drill.invalid/api/health",
        ],
        "zcrypto-ops",
        "ops",
        {"ops_grafana_watchdog_probe_url": "https://grafana-watchdog-drill.invalid/api/health"},
    ),
    (
        ["--limit", "zcrypto-valkey1", "--tags", "base,hardening,firewall,fail2ban,chrony,docker", "-e", "daemon_json_ack=true"],
        "zcrypto-valkey1",
        "base,hardening,firewall,fail2ban,chrony,docker",
        {"daemon_json_ack": "true"},
    ),
    (["--limit", "zcrypto-valkey2", "--tags", "firewall,cache-link"], "zcrypto-valkey2", "firewall,cache-link", {}),
    (
        ["--limit", "zcrypto", "--tags", "firewall,cache-link", "-e", "converge_primary=true"],
        "zcrypto",
        "firewall,cache-link",
        {"converge_primary": "true"},
    ),
    (
        [
            "--limit",
            "zcrypto-valkey3",
            "--tags",
            "cache",
            "-e",
            f"cache_image_digest={DIGEST}",
            "-e",
            f"cache_alloy_digest={DIGEST}",
        ],
        "zcrypto-valkey3",
        "cache",
        {"cache_image_digest": DIGEST, "cache_alloy_digest": DIGEST},
    ),
    (
        [
            "--limit",
            "zcrypto-valkey1",
            "--tags",
            "cache",
            "-e",
            "cache_config_reset=true",
            "-e",
            f"cache_image_digest={DIGEST}",
            "-e",
            f"cache_alloy_digest={DIGEST}",
        ],
        "zcrypto-valkey1",
        "cache",
        {"cache_config_reset": "true", "cache_image_digest": DIGEST, "cache_alloy_digest": DIGEST},
    ),
    (
        ["--limit", "zcrypto-valkey2", "--tags", "cache", "-e", f"cache_alloy_digest={DIGEST}"],
        "zcrypto-valkey2",
        "cache",
        {"cache_alloy_digest": DIGEST},
    ),
    (
        [
            "--limit",
            "zcrypto-valkey1",
            "--tags",
            "cache",
            "-e",
            f"cache_image_digest={DIGEST}",
            "-e",
            f"cache_alloy_digest={DIGEST}",
            "-e",
            json.dumps({"pins_override": "a first pin, recorded after this run"}),
        ],
        "zcrypto-valkey1",
        "cache",
        {"cache_image_digest": DIGEST, "cache_alloy_digest": DIGEST, "pins_override": "a first pin, recorded after this run"},
    ),
    (
        [
            "--limit",
            "zaccess",
            "--tags",
            "alloy",
            "-e",
            "alloy_deb_version=1.20.0-1",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops journal lines on the edge, back while the owner reads it"}),
        ],
        "zaccess",
        "alloy",
        {
            "alloy_deb_version": "1.20.0-1",
            "alloy_override": "1.20.1 drops journal lines on the edge, back while the owner reads it",
        },
    ),
    (
        ["--limit", "zcrypto-ops", "--tags", "alloy", "-e", f"ops_alloy_digest={DIGEST}"],
        "zcrypto-ops",
        "alloy",
        {"ops_alloy_digest": DIGEST},
    ),
    (
        [
            "--limit",
            "zcrypto-ops",
            "--tags",
            "alloy",
            "-e",
            f"ops_alloy_digest={DIGEST}",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops the ops timers' journal lines, back while the owner reads it"}),
        ],
        "zcrypto-ops",
        "alloy",
        {"ops_alloy_digest": DIGEST, "alloy_override": "1.20.1 drops the ops timers' journal lines, back while the owner reads it"},
    ),
    (
        ["--limit", "zcrypto-valkey1", "--tags", "alloy", "-e", f"cache_alloy_digest={DIGEST}"],
        "zcrypto-valkey1",
        "alloy",
        {"cache_alloy_digest": DIGEST},
    ),
    (
        ["--limit", "zcrypto-valkey2", "--tags", "alloy", "-e", f"cache_alloy_digest={DIGEST}"],
        "zcrypto-valkey2",
        "alloy",
        {"cache_alloy_digest": DIGEST},
    ),
    (
        ["--limit", "zcrypto-valkey3", "--tags", "alloy", "-e", f"cache_alloy_digest={DIGEST}"],
        "zcrypto-valkey3",
        "alloy",
        {"cache_alloy_digest": DIGEST},
    ),
    (
        [
            "--limit",
            "zcrypto-valkey2",
            "--tags",
            "alloy",
            "-e",
            f"cache_alloy_digest={DIGEST}",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops the Sentinel scrape's series, back while the owner reads it"}),
        ],
        "zcrypto-valkey2",
        "alloy",
        {
            "cache_alloy_digest": DIGEST,
            "alloy_override": "1.20.1 drops the Sentinel scrape's series, back while the owner reads it",
        },
    ),
    (["--limit", "zcrypto-mon"], "zcrypto-mon", "", {}),
    (["--limit", "zcrypto-mon", "--tags", "alloy"], "zcrypto-mon", "alloy", {}),
    (
        [
            "--limit",
            "zcrypto-mon",
            "--tags",
            "alloy",
            "-e",
            "alloy_deb_version=1.19.2-1",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops the node's own journal lines, back while the owner reads it"}),
        ],
        "zcrypto-mon",
        "alloy",
        {
            "alloy_deb_version": "1.19.2-1",
            "alloy_override": "1.20.1 drops the node's own journal lines, back while the owner reads it",
        },
    ),
    (["--limit", "zcrypto-mon", "--tags", "mon"], "zcrypto-mon", "mon", {}),
    (
        ["--limit", "zcrypto-mon", "--tags", "mon", "-e", "mon_grafana_token_rotate=true"],
        "zcrypto-mon",
        "mon",
        {"mon_grafana_token_rotate": "true"},
    ),
    # The bump skill's one-host rollbacks of a container host, each its own line there.
    (
        [
            "--limit",
            "zcrypto-red",
            "--tags",
            "alloy",
            "-e",
            f"capture_alloy_digest={DIGEST}",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops the secondary's journal lines, back while the owner reads it"}),
        ],
        "zcrypto-red",
        "alloy",
        {
            "capture_alloy_digest": DIGEST,
            "alloy_override": "1.20.1 drops the secondary's journal lines, back while the owner reads it",
        },
    ),
    (
        [
            "--limit",
            "zcrypto",
            "--tags",
            "alloy",
            "-e",
            "converge_primary=true",
            "-e",
            f"capture_alloy_digest={DIGEST}",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops the primary's journal lines, back while the owner reads it"}),
        ],
        "zcrypto",
        "alloy",
        {
            "converge_primary": "true",
            "capture_alloy_digest": DIGEST,
            "alloy_override": "1.20.1 drops the primary's journal lines, back while the owner reads it",
        },
    ),
    (
        [
            "--limit",
            "zcrypto-valkey3",
            "--tags",
            "alloy",
            "-e",
            f"cache_alloy_digest={DIGEST}",
            "-e",
            json.dumps({"alloy_override": "1.20.1 drops the Valkey scrape's series, back while the owner reads it"}),
            "-e",
            json.dumps({"pins_override": "the node runs a digest fleet-pins.md does not yet record"}),
        ],
        "zcrypto-valkey3",
        "alloy",
        {
            "cache_alloy_digest": DIGEST,
            "alloy_override": "1.20.1 drops the Valkey scrape's series, back while the owner reads it",
            "pins_override": "the node runs a digest fleet-pins.md does not yet record",
        },
    ),
]


# The harness's copy of the script sits outside any repository, so an `alloy` run's walk is pointed at this checkout.
THIS_TREE = {"ZCRYPTO_REPO": str(SCRIPT.parents[3]), "ZCRYPTO_ANSIBLE_DIR": str(SCRIPT.parents[1])}


@pytest.mark.parametrize("args,limit,tags,extra", PUBLISHED)
def test_every_invocation_this_fleet_publishes_records_its_operands(tmp_path, args, limit, tags, extra):
    """The grammar is a whitelist, so its floor is every shape the fleet actually converges with.

    Drawn from the recorded runs and the published ones: the four-operand engine leg, the NAS
    render, the ops roll, the bridgehead, `--limit=`, and `--skip-tags engine`.
    """
    rc, _out, log = run_recording(tmp_path, ["site.yml", *args], reply=limit, env=THIS_TREE)
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert (rec["limit"], rec["tags"], rec["extra_vars"]) == (limit, tags, extra), rec


def _a_tree_whose_one_play_carries_no_tag(tmp_path) -> Path:
    ansible = tmp_path / "infra" / "ansible"
    (ansible / "inventory").mkdir(parents=True)
    (ansible / "inventory" / "hosts.yml").write_text(
        json.dumps({"all": {"children": {"ops_host": {"hosts": {"zcrypto-ops": {}}}}}})
    )
    play = {
        "name": "converge the ops node",
        "hosts": "ops_host",
        "tasks": [{"name": "a task", "ansible.builtin.debug": {"msg": "x"}}],
    }
    (ansible / "site.yml").write_text(json.dumps([play]))
    return ansible


def _refusal(stderr: str) -> str:
    return next((line for line in stderr.splitlines() if line.startswith("converge.sh:")), "")


def test_an_alloy_run_on_a_host_no_play_reaches_with_an_alloy_task_is_refused_before_the_preview(tmp_path):
    script = make_harness(tmp_path)
    tree = {**THIS_TREE, "ZCRYPTO_ANSIBLE_DIR": str(_a_tree_whose_one_play_carries_no_tag(tmp_path))}
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto-ops", "--tags", "alloy"], env=tree)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert invocations(tmp_path) == []
    assert "--tags alloy on zcrypto-ops" in _refusal(r.stderr), r.stderr
    assert "no play that reaches zcrypto-ops runs an alloy-tagged task" in r.stderr, r.stderr


def test_an_alloy_run_whose_walk_cannot_run_is_refused(tmp_path):
    script = make_harness(tmp_path)
    (tmp_path / "empty").mkdir()
    r = run_no_tty(
        script,
        ["site.yml", "--limit", "zcrypto-ops", "--tags", "alloy"],
        env={**THIS_TREE, "ZCRYPTO_ANSIBLE_DIR": str(tmp_path / "empty")},
    )
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert invocations(tmp_path) == []
    assert "--tags alloy on zcrypto-ops" in _refusal(r.stderr), r.stderr


def test_a_run_without_the_tag_never_runs_the_walk(tmp_path):
    script = make_harness(tmp_path)
    (tmp_path / "empty").mkdir()
    r = run_no_tty(
        script, ["site.yml", "--limit", "zcrypto-red", "--tags", "capture"], env={"ZCRYPTO_REPO": str(tmp_path / "empty")}
    )
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert len(invocations(tmp_path)) == 1


def test_the_json_override_operand_is_recorded_whole(tmp_path):
    """A reason is prose and `k=v` truncates it at the first space, so an override travels as JSON.

    `count-list.sh canary-bypasses-on-the-primary` counts the row this operand writes.
    """
    reason = "rolled back: the venue answers EGeneral:Permission denied, so exec_armed=0 stands"
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "-e", f"capture_image_digest={DIGEST}", "-e", json.dumps({"canary_override": reason})],
        reply="zcrypto",
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["extra_vars"] == {"capture_image_digest": DIGEST, "canary_override": reason}


OUTSIDE = [
    # Two callers type this script's argv: a session, or the operator pasting the line it wrote.
    # So these are the WRONG names and stale spellings either could reach for — not malformed
    # input, which neither would type and no arm defends against.
    (["--limit", "zcrypt"], "a mistyped host", "unknown host"),
    (["--limit", "capture_host"], "an inventory group where a host belongs", "unknown host"),
    (["--limit", "zcrypto zcrypto-red"], "two hosts, which ansible reads as two and this as none", "unknown host"),
    (["--limit", "zcrypto", "--tags", "captur"], "a mistyped tag", "unknown tag"),
    (["-e", "capture_image_digest="], "an unsubstituted placeholder, which ansible reads as defined", "empty value"),
    (
        ["-e", f"capture_image_digest={DIGEST} converge_primary=true"],
        "two variables in one operand, which the row would book as one",
        "carries whitespace",
    ),
    (["--limit", "zcrypto", "--tags", "bootstrap"], "a tag no play in site.yml carries", "unknown tag"),
    (["--limit", "zcrypto", "--skip-tags", "capture"], "--skip-tags with any value but engine", "takes only engine"),
    (
        ["--limit", "zcrypto", "--skip-tags", "capture", "--skip-tags", "engine"],
        "two skip flags, which ansible appends and the cell booked as engine alone",
        "takes only engine",
    ),
    (["--limit", "zcrypto", "--tags", "capture", "--skip-tags", "engine"], "both tag flags", "--tags and --skip-tags together"),
    (
        ["-e", f"nas_capture_image_digest={DIGEST}"],
        "the key one real converge passed and no role reads",
        "not in this script's key set",
    ),
    (["-e", "ansible_user=root"], "a variable ansible reads but no converge here has passed", "not in this script's key set"),
    (["-e", "rebootstrap=true"], "a variable only a bootstrap run would carry", "not in this script's key set"),
    (["-e", "canary_override=why this cannot wait"], "an override as k=v, which truncates at the space", "an override is a reason"),
    (["-e", "alloy_override=a reason"], "the Alloy override as k=v, which truncates at the space", "an override is a reason"),
    (["-e", "alloy_deb_version=1.20.0-1"], "an apt host's Alloy version with no reason beside it", "beside"),
    (["-e", '{canary_override: "why this cannot wait"}'], "the YAML-flow dialect ansible reads and this cannot", "not JSON"),
    (["-e", '{"capture_image_digest": "sha256:a reason"}'], "a braced operand that is not an override", "is not an override name"),
    (["-e", '{"canary_override": "a b", "pins_override": "c d"}'], "two overrides in one operand", "exactly one override"),
    (["-e", "@vars.json"], "a file the confirm never shows the operator", "KEY=VALUE or a braced"),
    (["--limit", "zcrypto", "-vvv"], "a passthrough flag", "outside the grammar"),
    (["--limit", "zcrypto", "--diff"], "a flag the preview composes itself", "outside the grammar"),
    (["-ve", "canary_override=abcdefghij"], "a cluster carrying -e", "outside the grammar"),
    (["-C"], "the short check flag, which converges while the row says otherwise", "outside the grammar"),
    (["-l", "zcrypto"], "the short limit", "outside the grammar"),
    (["-t", "engine"], "the short tags", "outside the grammar"),
    (["--extra-vars", "converge_primary=true"], "the long extra-vars spelling", "outside the grammar"),
    (["--limit"], "a flag with no value", "--limit with no value"),
    (["--limit", "cache_host"], "the cache group, whose nodes converge one per run", "unknown host"),
    (["--limit", "mon_host"], "the observability group where its one host belongs", "unknown host"),
    (["--limit", "zcrypto-mon", "--tags", "grafana"], "a component of the node, which is no tag", "unknown tag"),
    (
        ["--limit", "zcrypto-mon", "-e", "mon_grafana_token=x"],
        "a token as an operand, which the row would record",
        "not in this script's key set",
    ),
]


@pytest.mark.parametrize("args,why,reason", OUTSIDE)
def test_every_spelling_outside_the_grammar_is_refused_before_anything_runs(tmp_path, args, why, reason):
    """Refusing is the safe failure: the operator is still at the terminal, and no host was touched.

    Each of these is honoured by ansible and would have been recorded as something it is not. Where
    the entry names a `reason`, the refusal LINE must carry it: an arm that refuses for the WRONG
    reason still exits 2, so asserting the rc alone cannot see a message regression.
    """
    script = make_harness(tmp_path)
    limited = args if any(a.startswith("--limit") for a in args) else ["--limit", "zcrypto", *args]
    r = run_no_tty(script, ["site.yml", *limited])
    assert r.returncode == 2, (why, r.returncode, r.stdout, r.stderr)
    assert invocations(tmp_path) == [], why
    refusal = next((line for line in r.stderr.splitlines() if line.startswith("converge.sh:")), "")
    assert refusal, (why, r.stderr)
    if reason:
        assert reason in refusal, (why, refusal)


def test_a_playbook_other_than_site_yml_is_refused(tmp_path):
    """`site.yml` is what this fleet converges: every deploy-log row and every published procedure.

    `bootstrap.yml` was accepted on the strength of the role's existence rather than any published
    run through this script, and its `-e ansible_user=root` is refused here in any case.
    """
    for playbook in ("other.yml", "bootstrap.yml"):
        path = tmp_path / playbook.split(".")[0]
        path.mkdir()
        r = run_no_tty(make_harness(path), [playbook, "--limit", "zcrypto"])
        assert r.returncode == 2, (playbook, r.returncode)
        assert invocations(path) == [], playbook


def test_an_unknown_key_is_refused_by_naming_the_whitelist_not_the_role(tmp_path):
    """`capture_retention_days` IS read by the capture role; it is this script's set that is short.

    The whitelist going short is the refusal an operator meets on a legitimate converge, so the
    message has to send them to the set rather than to a role that reads the key perfectly well.
    """
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto", "-e", "capture_retention_days=9"])
    assert r.returncode == 2
    refusal = next(line for line in r.stderr.splitlines() if line.startswith("converge.sh:"))
    assert "is not in this script's key set" in refusal, refusal
    assert "no role reads" not in refusal, refusal


def test_a_skip_tags_run_is_not_booked_as_an_un_tagged_one(tmp_path):
    """`--skip-tags engine` is infra/README.md's published primary form, and it is not un-tagged.

    `count-list.sh un-tagged-primary-runs` counts the rule "never run site.yml un-tagged on the
    primary" over rows whose tags cell is empty; the skip goes in its own cell so that count stays
    the violations it is named for.
    """
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "--skip-tags", "engine", "-e", f"capture_alloy_digest={DIGEST}"],
        reply="zcrypto",
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["skip_tags"] == "engine" and rec["tags"] == "", rec


def test_an_override_passed_as_k_equals_v_is_told_where_to_put_it(tmp_path):
    """The refusal names the fix, because the key IS read — it just cannot travel as `k=v`."""
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto", "-e", "canary_override=whatever"])
    assert r.returncode == 2
    assert "an override is a reason" in r.stderr, r.stderr
    assert "no role reads" not in r.stderr, r.stderr


def test_a_refused_override_operand_prints_a_reason_not_a_traceback(tmp_path):
    """A traceback at the terminal reads as a crash, and sends the operator to the wrong question."""
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto", "-e", '{canary_override: "a reason here"}'])
    assert r.returncode == 2
    assert "Traceback" not in r.stderr, r.stderr
    # On the refusal LINE, not merely somewhere on stderr: the checker writes its reason to stderr
    # either way, so a capture that reads stdout leaves the refusal itself saying nothing.
    refusal = next(line for line in r.stderr.splitlines() if line.startswith("converge.sh:"))
    assert "not JSON" in refusal, refusal


def test_two_tag_flags_book_both_because_ansible_runs_both(tmp_path):
    """`--tags` is `action="append"` to ansible, so a second flag adds rather than replaces.

    Booking the last one alone left the row describing a pass that did not happen, and
    `count-list.sh engine-rows-outside-the-gap` selects rows whose `tags` cell names `engine`.
    """
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "--tags", "capture", "--tags", "engine"],
        reply="zcrypto",
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["tags"] == "capture,engine", rec["tags"]


def test_the_row_carries_the_argv_verbatim(tmp_path):
    """Whatever a later reader asks of a pass, argv answers it without a parser.

    The parsed cells are ansible's reading of these words; this is the words.
    """
    args = ["site.yml", "--limit", "zcrypto-red", "-e", "capture_image_digest=sha256:abc123"]
    rc, _out, log = run_recording(tmp_path, args)
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["argv"] == args, rec["argv"]


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


# --- the engine window's record: the wrapper names a file for the play, which writes the floor its window assert
# admitted the run on, and the row carries it as `window`; the file is the wrapper's, gone however it exits.

import re  # noqa: E402 -- the block above is the file's own section header

WINDOW = {"at": 1785744500, "floor": 1785744408, "arm": "journal", "override": False}


def _booked_as_the_audit_reads(rec):
    assert rec["window"] == WINDOW, rec
    assert {key: type(value) for key, value in rec["window"].items()} == {"at": int, "floor": int, "arm": str, "override": bool}
    spec = importlib.util.spec_from_file_location("deploy_log_audit_booked", SCRIPT.parents[2] / "scripts" / "deploy-log-audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    assert audit.carries_the_record(rec), rec


# The play's record task, as a fake: on the real pass only, it writes $FAKE_WINDOW into the file the wrapper named,
# from `ansible/` as run.sh plays from infra/ansible, and fails the play as the copy task does when it cannot write.
WRITES_THE_RECORD = r"""#!/usr/bin/env bash
echo "$@" >> "$(dirname "$0")/invocations.log"
case " $* " in *" --check "*) exit 0 ;; esac
f="$(printf '%s\n' "$*" | sed -n 's/.*"zcrypto_window_record": "\([^"]*\)".*/\1/p')"
mkdir -p "$(dirname "$0")/ansible" && cd "$(dirname "$0")/ansible"
if [ -n "$f" ]; then printf '%s' "$FAKE_WINDOW" > "$f" || exit 2; fi
exit ${FAKE_RUN_RC:-0}
"""


def _record_files(tmp_path) -> list[str]:
    return [m for line in invocations(tmp_path) for m in re.findall(r'"zcrypto_window_record": "([^"]+)"', line)]


def test_every_run_is_handed_one_record_file_that_is_gone_when_the_wrapper_exits(tmp_path):
    rc, _out, _log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto", "--tags", "engine"], reply="zcrypto")
    assert rc == 0
    files = _record_files(tmp_path)
    assert len(files) == 2 and len(set(files)) == 1, invocations(tmp_path)
    assert not os.path.exists(files[0])


def test_the_record_the_play_wrote_lands_in_the_row_as_window(tmp_path):
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "--tags", "engine", "-e", "converge_primary=true"],
        reply="zcrypto",
        env={"FAKE_WINDOW": json.dumps(WINDOW)},
        run_sh=WRITES_THE_RECORD,
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    _booked_as_the_audit_reads(rec)
    assert rec["extra_vars"] == {"converge_primary": "true"}, "the wrapper's own operand is not the operator's"


def test_a_failed_pass_keeps_the_record_its_play_wrote_before_failing(tmp_path):
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "--tags", "engine"],
        reply="zcrypto",
        env={"FAKE_WINDOW": json.dumps(WINDOW), "FAKE_RUN_RC": "2"},
        run_sh=WRITES_THE_RECORD,
    )
    assert rc == 2
    _booked_as_the_audit_reads(json.loads(log.read_text().splitlines()[0]))


def test_a_pass_whose_play_wrote_no_record_books_no_window(tmp_path):
    rc, _out, log = run_recording(tmp_path, ["site.yml", "--limit", "zcrypto", "--tags", "capture"], reply="zcrypto")
    assert rc == 0
    assert len(_record_files(tmp_path)) == 2, invocations(tmp_path)
    assert "window" not in json.loads(log.read_text().splitlines()[0])


def test_an_unreadable_record_is_loud_and_still_books_the_row(tmp_path):
    rc, out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "--tags", "engine"],
        reply="zcrypto",
        env={"FAKE_WINDOW": "{not json"},
        run_sh=WRITES_THE_RECORD,
    )
    assert rc == 0
    rec = json.loads(log.read_text().splitlines()[0])
    assert "window" not in rec and rec["rc"] == 0
    assert "WINDOW RECORD UNREADABLE" in out


@pytest.mark.parametrize("beside_the_playbook_too", [False, True])
def test_a_relative_tmpdir_still_books_the_window_and_leaves_no_file(tmp_path, monkeypatch, beside_the_playbook_too):
    (tmp_path / "rel").mkdir()
    if beside_the_playbook_too:
        (tmp_path / "ansible" / "rel").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TMPDIR", "rel")
    rc, _out, log = run_recording(
        tmp_path,
        ["site.yml", "--limit", "zcrypto", "--tags", "engine"],
        reply="zcrypto",
        env={"FAKE_WINDOW": json.dumps(WINDOW)},
        run_sh=WRITES_THE_RECORD,
    )
    assert rc == 0
    _booked_as_the_audit_reads(json.loads(log.read_text().splitlines()[0]))
    assert list(tmp_path.rglob("zcrypto-window.*")) == []


@pytest.mark.parametrize(
    ("args", "reply", "env", "rc"),
    [
        (["--check"], None, {}, 0),
        ([], None, {"FAKE_RUN_RC": "1"}, 4),
        ([], None, {}, 3),
        ([], "zcrypto-ops", {}, 3),
        ([], "zcrypto", {"FAKE_RUN_RC_REAL": "7"}, 7),
    ],
)
def test_the_record_file_is_removed_on_every_exit_path(tmp_path, args, reply, env, rc):
    fails_the_real_pass = (
        '#!/usr/bin/env bash\necho "$@" >> "$(dirname "$0")/invocations.log"\n'
        'case " $* " in *" --check "*) exit ${FAKE_RUN_RC:-0} ;; esac\nexit ${FAKE_RUN_RC_REAL:-0}\n'
    )
    if reply is None:
        script = make_harness(tmp_path)
        (tmp_path / "run.sh").write_text(fails_the_real_pass)
        got = run_no_tty(script, ["site.yml", "--limit", "zcrypto", *args], env=env).returncode
    else:
        got, _out, _log = run_recording(
            tmp_path, ["site.yml", "--limit", "zcrypto", *args], reply=reply, env=env, run_sh=fails_the_real_pass
        )
    assert got == rc
    files = _record_files(tmp_path)
    assert files and not any(os.path.exists(f) for f in files), (files, invocations(tmp_path))


@pytest.mark.parametrize(
    "operand",
    ["zcrypto_window_record=/tmp/elsewhere", json.dumps({"zcrypto_window_record": "/tmp/elsewhere"})],
)
def test_an_operator_cannot_name_the_record_file(tmp_path, operand):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto", "-e", operand])
    assert r.returncode == 2
    assert invocations(tmp_path) == []
    refusal = next(line for line in r.stderr.splitlines() if line.startswith("converge.sh:"))
    assert "zcrypto_window_record is this script's own" in refusal, refusal
