"""Docker on the ops node waits, bounded, for a nameserver before it starts, and fails open at the bound."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLES = REPO / "infra/ansible/roles"
ROLE = ROLES / "ops"
DROP_IN_DEST = "/etc/systemd/system/docker.service.d/zcrypto-wait-for-resolver.conf"
LEASE_AFTER_DOCKER_START_S = 23
BOUND_CEILING_S = 120

_SERVICE_MODULES = ("ansible.builtin.systemd_service", "ansible.builtin.systemd", "ansible.builtin.service")
_SHELL_MODULES = ("ansible.builtin.command", "ansible.builtin.shell")
_RESTARTING_STATES = {"restarted", "reloaded", "stopped"}


def _flatten(tasks):
    for t in tasks or []:
        yield t
        for key in ("block", "rescue", "always"):
            if key in t:
                yield from _flatten(t[key])


def _ops_tasks() -> list[dict]:
    return list(_flatten(yaml.safe_load((ROLE / "tasks/main.yml").read_text())))


def _ops_handlers() -> list[dict]:
    return list(_flatten(yaml.safe_load((ROLE / "handlers/main.yml").read_text())))


def _installing(dest: str) -> tuple[int, dict]:
    found = [(i, t) for i, t in enumerate(_ops_tasks()) if (t.get("ansible.builtin.copy") or {}).get("dest") == dest]
    assert len(found) == 1, f"the ops role installs {dest} {len(found)} times, not once"
    return found[0]


def _exec_start_pre() -> list[str]:
    _, task = _installing(DROP_IN_DEST)
    text = (ROLE / "files" / task["ansible.builtin.copy"]["src"]).read_text()
    program = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    assert program[0] == "[Service]", f"ExecStartPre is read only under [Service]: {program}"
    pre = [line.removeprefix("ExecStartPre=") for line in program if line.startswith("ExecStartPre=")]
    assert len(pre) == 1, pre
    return pre[0].split()


def _restarts_docker(task: dict) -> bool:
    for module in _SERVICE_MODULES:
        args = task.get(module) or {}
        if str(args.get("name", "")).removesuffix(".service") == "docker" and args.get("state") in _RESTARTING_STATES:
            return True
    return any(
        re.search(r"\bsystemctl\s+(restart|reload|stop)\s+docker\b", str(task.get(module) or "")) for module in _SHELL_MODULES
    )


def _waiter() -> Path:
    _, task = _installing(_exec_start_pre()[0].removeprefix("-"))
    return ROLE / "files" / task["ansible.builtin.copy"]["src"]


def _wait(conf: Path, bound: int) -> tuple[subprocess.CompletedProcess, float]:
    start = time.monotonic()
    result = subprocess.run(["sh", str(_waiter()), str(conf), str(bound)], capture_output=True, text=True, timeout=60)
    return result, time.monotonic() - start


def test_a_failed_or_missing_waiter_never_holds_docker_down():
    assert _exec_start_pre()[0].startswith("-"), "without the `-` prefix a waiter that fails keeps docker from starting"


def test_the_drop_in_runs_the_waiter_the_role_installs_over_the_hosts_resolver_config():
    binary, conf, _ = _exec_start_pre()
    _, task = _installing(binary.removeprefix("-"))
    assert task["ansible.builtin.copy"]["mode"] == "0755", task
    assert conf == "/etc/resolv.conf"


def test_the_bound_outlasts_the_measured_lease_and_stays_under_the_ceiling():
    bound = int(_exec_start_pre()[2])
    assert LEASE_AFTER_DOCKER_START_S < bound <= BOUND_CEILING_S, (
        f"a {bound} s bound: it must outlast the {LEASE_AFTER_DOCKER_START_S} s the lease took after docker started, and "
        f"docker's unit sets TimeoutStartSec=0, so nothing but this bound ends the wait"
    )


@pytest.mark.parametrize("content", [None, "domain fritz.box\n# nameserver 192.168.100.1\n"], ids=["absent", "no-nameserver"])
def test_at_its_bound_the_waiter_exits_zero_and_says_so(tmp_path, content):
    conf = tmp_path / "resolv.conf"
    if content is not None:
        conf.write_text(content)
    result, elapsed = _wait(conf, 1)
    assert result.returncode == 0, result
    assert 1 <= elapsed < 8, f"returned after {elapsed:.1f} s against a 1 s bound"
    assert f"no nameserver in {conf} after 1 s" in result.stderr, result.stderr


def test_a_nameserver_already_there_returns_at_once_and_silently(tmp_path):
    conf = tmp_path / "resolv.conf"
    conf.write_text("domain fritz.box\nnameserver 192.168.100.1\n")
    result, elapsed = _wait(conf, 30)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), result
    assert elapsed < 5, elapsed


def test_a_lease_that_lands_mid_wait_ends_it(tmp_path):
    conf = tmp_path / "resolv.conf"
    conf.write_text("domain fritz.box\n")
    waiter = subprocess.Popen(["sh", str(_waiter()), str(conf), "30"], stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    assert waiter.poll() is None, "the waiter returned before any nameserver was written"
    conf.write_text("domain fritz.box\nnameserver 192.168.100.1\n")
    try:
        assert waiter.wait(timeout=5) == 0
    finally:
        waiter.kill()
    assert waiter.stderr.read() == ""


def test_the_predicate_sees_the_docker_roles_restart_handler():
    handlers = yaml.safe_load((ROLES / "docker/handlers/main.yml").read_text())
    assert any(_restarts_docker(h) for h in handlers), "the predicate below would pass over a real docker restart"


def test_nothing_in_the_ops_role_restarts_docker_directly_or_through_a_handler():
    ops = _ops_tasks() + _ops_handlers()
    assert not [t.get("name") for t in ops if _restarts_docker(t)]
    restarting = {
        name
        for handlers in ROLES.glob("*/handlers/main.yml")
        for h in _flatten(yaml.safe_load(handlers.read_text()))
        if _restarts_docker(h)
        for name in [h.get("name"), *([h["listen"]] if isinstance(h.get("listen"), str) else h.get("listen") or [])]
        if name
    }
    notified = {n for t in ops for n in ([t["notify"]] if isinstance(t.get("notify"), str) else t.get("notify") or [])}
    assert not notified & restarting, f"{sorted(notified & restarting)} restart docker, which bounces Alloy and the poller"


def test_the_drop_in_is_followed_by_a_daemon_reload_and_nothing_more():
    index, task = _installing(DROP_IN_DEST)
    register = task["register"]
    reloads = [
        (i, t)
        for i, t in enumerate(_ops_tasks())
        if "ansible.builtin.systemd_service" in t and f"{register} is changed" in str(t.get("when", ""))
    ]
    assert len(reloads) == 1, reloads
    i, reload = reloads[0]
    assert i > index, "the reload runs before the drop-in it is for is written"
    assert reload["ansible.builtin.systemd_service"] == {"daemon_reload": True}, reload
