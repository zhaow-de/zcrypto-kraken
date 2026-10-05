from __future__ import annotations

from pathlib import Path

import pytest

from tests import role_render
from tests.test_infra_converge_guards import find_task, iter_tasks, load_tasks, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/node_common"
PREFLIGHT_NAME = "refuse a missing or misshapen secret, naming the key and never the value"
# Shaped like what a generator and the ping service write; neither is a credential.
SECRETS = {
    "probe_password": "A" * 48,
    "probe_ping_url": "https://hc-ping.com/" + "0" * 8 + "-0000-4000-8000-" + "0" * 12,
}
INCLUDE = {
    "node_common_secrets_preflight": [
        {"key": "probe_password", "shape": r"[A-Za-z0-9]{32,}\Z"},
        {"key": "probe_ping_url", "shape": r"https://hc-ping\.com/\S+\Z"},
    ],
    "node_common_secrets_preflight_file": "host_vars/probe/vault.yml",
    "node_common_secrets_preflight_runbook": "infra/runbooks/probe.md's probe-secrets procedure",
}
REBOOT_CHECK = {"node_common_reboot_check_textfile_dir": "/var/lib/probe-textfile", "node_common_role_name": "probe"}


def _preflight() -> dict:
    (task,) = load_tasks(ROLE / "tasks/secrets-preflight.yml")
    assert task["name"] == PREFLIGHT_NAME
    return task


# --- secrets-preflight: a listed key refused by name when missing or misshapen -----------------------------------
@pytest.mark.parametrize(
    ("override", "refused"),
    [
        ({}, None),
        ({"probe_password": "root"}, "probe_password"),
        ({"probe_password": "administrator"}, "probe_password"),
        ({"probe_password": None}, "probe_password"),
        ({"probe_password": "short"}, "probe_password"),
        ({"probe_password": "has a space in it, which a generator never writes"}, "probe_password"),
        ({"probe_password": "$2b$10$" + "f" * 53}, "probe_password"),
        ({"probe_password": SECRETS["probe_password"] + "\n"}, "probe_password"),
        ({"probe_ping_url": None}, "probe_ping_url"),
        ({"probe_ping_url": "https://hc-ping.invalid/abc"}, "probe_ping_url"),
        ({"probe_ping_url": "https://hc-ping.com/"}, "probe_ping_url"),
        ({"probe_ping_url": SECRETS["probe_ping_url"] + "\n"}, "probe_ping_url"),
        ({"probe_password": ""}, "probe_password"),
    ],
    ids=[
        "both",
        "a word a stranger tries",
        "a long word a stranger tries",
        "one missing",
        "too short",
        "not letters and digits",
        "a hash where a password belongs",
        "a trailing newline",
        "the ping URL missing",
        "a ping URL off the ping host",
        "a ping URL naming no check",
        "a ping URL with a trailing newline",
        "an empty value",
    ],
)
def test_a_missing_or_misshapen_secret_is_refused_by_its_key(override, refused):
    role_render.assert_preflight(_preflight(), SECRETS, override, refused, INCLUDE)


def test_every_shape_an_including_role_passes_ends_in_backslash_z():
    # `$` also matches before a trailing newline, and only some keys have a trailing-newline case to catch its loss.
    includes = [
        (path.parts[-3], task)
        for path in sorted((REPO / "infra/ansible/roles").glob("*/tasks/*.yml"))
        for task, _ in iter_tasks(load_tasks(path) or [])
        if task.get("ansible.builtin.include_role") == {"name": "node_common", "tasks_from": "secrets-preflight"}
    ]
    assert includes, "found no preflight include: the walk is broken, not the tree clean"
    for role, task in includes:
        for entry in task["vars"]["node_common_secrets_preflight"]:
            assert entry["shape"].endswith(r"\Z"), (role, entry["key"], entry["shape"])


# --- reboot-check: the capture role's program, installed and timed as its copies are -----------------------------
def _reboot_check() -> list[dict]:
    return load_tasks(ROLE / "tasks/reboot-check.yml")


def test_the_reboot_check_installs_what_its_unit_runs_and_enables_the_timer_alone():
    unit = role_render.render(ROLE, "zcrypto-reboot-check.service.j2", {}, **REBOOT_CHECK).splitlines()
    assert unit[0].startswith("# Rendered by the `probe` Ansible role at /etc/systemd/system/zcrypto-reboot-check.service;")
    binary, flag, out = next(line for line in unit if line.startswith("ExecStart=")).removeprefix("ExecStart=").split()
    assert (flag, out) == ("/run/reboot-required", "/var/lib/probe-textfile/reboot.prom")
    assert [line for line in unit if line.startswith("ReadWritePaths=")] == ["ReadWritePaths=/var/lib/probe-textfile"]
    modules = [(module, args) for task in _reboot_check() for module, args in task.items() if isinstance(args, dict)]
    for module, args in modules:
        if "src" in args:
            assert (ROLE / ("templates" if module == "ansible.builtin.template" else "files") / args["src"]).is_file(), args
    assert binary in {args.get("dest") for _, args in modules}, f"the unit runs {binary}, which the task file does not install"
    enabled = [args["name"] for module, args in modules if module == "ansible.builtin.systemd_service" and args.get("enabled")]
    assert enabled == ["zcrypto-reboot-check.timer"], enabled


@pytest.mark.parametrize(
    ("check", "changed", "runs"),
    [(True, True, False), (True, False, True), (False, True, True)],
    ids=["a first-install preview", "an established node's preview", "a real converge"],
)
def test_a_first_install_preview_skips_the_timer_it_never_wrote(check, changed, runs):
    install = find_task(_reboot_check(), "install the reboot-check systemd timer")
    enable = find_task(_reboot_check(), "enable + start the reboot-check timer")
    variables = {"ansible_check_mode": check, install["register"]: {"changed": changed}}
    assert truthy(when_conditions(enable), variables) is runs
