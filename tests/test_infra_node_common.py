from __future__ import annotations

import configparser
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
SELFCHECK = {
    "node_common_selfcheck_name": "probe-selfcheck",
    "node_common_selfcheck_script": "probe-selfcheck.py",
    "node_common_selfcheck_description": "Ping the probe's dead-man check while its web answers",
    "node_common_selfcheck_timer_description": "Every-minute self-check of the probe",
    "node_common_selfcheck_environment": {"PROBE_SELFCHECK_WEB": "http://127.0.0.1:8000", "PROBE_SELFCHECK_HOST": "probe.invalid"},
    "node_common_selfcheck_env_var": "PROBE_SELFCHECK_HEALTHCHECK_URL",
    "node_common_selfcheck_env_value": "https://hc-ping.invalid/probe",
    "node_common_selfcheck_on_calendar": "*:0/1:07",
    "node_common_role_name": "probe",
}


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


# --- selfcheck: a node's script over the shared loop, its ping URL in a root-only file, its unit and its timer -----
def _selfcheck() -> list[dict]:
    return load_tasks(ROLE / "tasks/selfcheck.yml")


def _selfcheck_render(name: str) -> list[str]:
    return role_render.render(ROLE, name, {}, **SELFCHECK).splitlines()


def _selfcheck_resolved(value):
    return role_render.resolve(ROLE, value, {}, **SELFCHECK)


def _selfcheck_service() -> dict[str, str]:
    unit = _selfcheck_render("selfcheck.service.j2")
    return dict(line.split("=", 1) for line in unit if "=" in line and not line.startswith(("#", "Environment=")))


def _selfcheck_steps() -> list[tuple[dict, str, dict]]:
    # Each task, its one module, and that module's arguments resolved through the include's variables.
    steps = []
    for task in _selfcheck():
        ((module, args),) = [(key, value) for key, value in task.items() if isinstance(value, dict)]
        steps.append((task, module, {k: _selfcheck_resolved(v) for k, v in args.items()}))
    return steps


def test_the_selfcheck_unit_sets_the_includes_environment_and_the_shared_modules_path_and_hides_no_path():
    unit = _selfcheck_render("selfcheck.service.j2")
    environment = dict(line.removeprefix("Environment=").split("=", 1) for line in unit if line.startswith("Environment="))
    assert environment == SELFCHECK["node_common_selfcheck_environment"] | {"PYTHONPATH": "/usr/local/lib/zcrypto"}
    # The module is read under ProtectSystem=strict's read-only /usr, the premise the node's first run proves; a path
    # hidden or remounted here is one that run did not prove.
    assert not [line for line in unit if line.startswith(("InaccessiblePaths=", "ReadOnlyPaths="))], unit
    service = _selfcheck_service()
    assert (service["Description"], service["Type"], service["DynamicUser"], service["ProtectSystem"]) == (
        SELFCHECK["node_common_selfcheck_description"],
        "oneshot",
        "true",
        "strict",
    )


def test_the_selfcheck_installs_what_its_unit_runs_imports_and_reads_and_enables_the_timer_alone():
    service = _selfcheck_service()
    steps = _selfcheck_steps()
    for _, module, args in steps:
        if "src" in args and args["src"] != SELFCHECK["node_common_selfcheck_script"]:
            assert (ROLE / ("templates" if module == "ansible.builtin.template" else "files") / args["src"]).is_file(), args
    by_dest = {args["dest"]: (task, args) for task, _, args in steps if "dest" in args}
    assert by_dest[service["ExecStart"].split()[1]][1]["src"] == SELFCHECK["node_common_selfcheck_script"]
    env_task, env_args = by_dest[service["EnvironmentFile"]]
    assert (env_args["mode"], env_task["no_log"], env_task["diff"]) == ("0600", True, False)
    (made,) = [index for index, (_, module, _) in enumerate(steps) if module == "ansible.builtin.file"]
    (copied,) = [index for index, (_, _, args) in enumerate(steps) if args.get("src") == "zcrypto_selfcheck.py"]
    # DynamicUser runs the script as a user that owns nothing, so the module and its directory are world-readable.
    assert (steps[made][2]["path"], steps[made][2]["mode"], steps[copied][2]["dest"], steps[copied][2]["mode"]) == (
        "/usr/local/lib/zcrypto",
        "0755",
        "/usr/local/lib/zcrypto/zcrypto_selfcheck.py",
        "0644",
    )
    assert made < copied, "copy creates no parent directory"
    enabled = [args["name"] for _, module, args in steps if module == "ansible.builtin.systemd_service" and args.get("enabled")]
    assert enabled == ["probe-selfcheck.timer"], enabled


def test_the_script_lands_only_after_systemd_holds_the_unit_that_puts_its_module_on_the_path():
    # The script imports the module through the unit's PYTHONPATH: landed under a unit without it, every run fails and
    # the node's dead-man check pages, so a converge stopped between the two must leave the old script, and a fresh
    # node's timer must not start before its script exists.
    steps = _selfcheck_steps()

    def at(found) -> int:
        (index,) = [index for index, (_, module, args) in enumerate(steps) if found(module, args)]
        return index

    copied = at(lambda _, args: args.get("src") == "zcrypto_selfcheck.py")
    env_file = at(lambda _, args: args.get("src") == "selfcheck.env.j2")
    unit = at(lambda _, args: args.get("src") == "selfcheck.service.j2")
    reload = at(lambda module, args: module == "ansible.builtin.systemd_service" and args == {"daemon_reload": True})
    script = at(lambda _, args: args.get("src") == SELFCHECK["node_common_selfcheck_script"])
    enable = at(lambda module, args: module == "ansible.builtin.systemd_service" and bool(args.get("enabled")))
    assert max(copied, env_file, unit) < reload < script < enable, [task["name"] for task, _, _ in steps]
    assert "when" not in steps[reload][0], "a reload gated on the unit's change skips the one a stopped converge still owes"


def test_the_selfcheck_env_file_holds_the_ping_url_alone():
    env_file = _selfcheck_render("selfcheck.env.j2")
    assert [line for line in env_file if line and not line.startswith("#")] == [
        "PROBE_SELFCHECK_HEALTHCHECK_URL=https://hc-ping.invalid/probe"
    ]


def test_the_selfcheck_timer_runs_the_unit_on_the_includes_calendar_and_never_catches_up():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string("\n".join(_selfcheck_render("selfcheck.timer.j2")))
    assert parser["Unit"]["Description"] == SELFCHECK["node_common_selfcheck_timer_description"]
    assert parser["Timer"]["OnCalendar"] == "*:0/1:07" and "Persistent" not in parser["Timer"]
    assert parser["Timer"]["Unit"] == "probe-selfcheck.service"
