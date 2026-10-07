"""The access role's share of the fleet-wide `alloy` tag: a converge that lands the bridgehead's Alloy through the shared
apt role, after the client-certificate revocation path, and nothing of Caddy, WireGuard, the SSH relay or the probe."""

from __future__ import annotations

import re

from tests.alloy_part import ARGUMENT_KEYWORDS, ROLES, apt_admitted, notified, tagged, task_text, unproduced_reads
from tests.test_alloy_version import alloy_version
from tests.test_infra_alloy_apt import ALLOY_APT_MAIN, ALLOY_APT_POSTCONDITION
from tests.test_infra_converge_guards import find_task, load_tasks, task_index, when_conditions

ACCESS = ROLES / "access" / "tasks" / "main.yml"
HANDLERS = ROLES / "access" / "handlers" / "main.yml"

ENV = "alloy env — CONFIG_FILE + credentials (the deb's unit reads EnvironmentFile=/etc/default/alloy)"
CONFIG = (
    "alloy config — UNGATED copy; every converge ships it, so a hand edit cannot outlive the next converge. That is the"
    " whole drift remedy: the other tiers carry asserts because their copies are digest-gated and an ordinary converge"
    " skips them — this one is not."
)
STARTED = "alloy enabled + started"

ALLOY_PART = [*ALLOY_APT_MAIN, ENV, CONFIG, STARTED, *ALLOY_APT_POSTCONDITION]

PINNED_LEAVES = "pinned mTLS client leaves (a PEM's presence here IS the pin; absence is revocation)"
RELAY_FLUSH = "apply pending handlers before the relay drift gate"
RELAY_READ = "read the ssh relay's running target"

REFUSED_READS = re.compile(r"caddy|wg-quick|zaccess-ssh-proxy|zaccess-probe|pinned-leaves", re.IGNORECASE)
ACCESS_VERBATIM = [("ansible.builtin.systemd", {"name": "alloy", "enabled": True, "state": "started"})]
ACCESS_WRITERS = {"ansible.builtin.copy", "ansible.builtin.template"}


def _on_alloy_paths(path) -> bool:
    return isinstance(path, str) and (
        path == "/etc/default/alloy" or (path.startswith("/etc/alloy/") and ".." not in path.split("/"))
    )


def _admitted(task: dict) -> bool:
    return apt_admitted(task, ACCESS_WRITERS, _on_alloy_paths, ACCESS_VERBATIM)


def _imported(task: dict) -> dict | None:
    key = next((key for key in alloy_version.IMPORT_ROLE if key in task), None)
    return task[key] if key else None


def test_the_access_roles_tagged_tasks_are_exactly_its_alloy_part():
    leaves = tagged("access")
    assert [task["name"] for task, _, _ in leaves] == ALLOY_PART
    assert {handler for task, _, _ in leaves for handler in notified(task)} == {"restart alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    unproduced = unproduced_reads("access")
    assert not unproduced, unproduced
    started = find_task(load_tasks(ACCESS), STARTED)
    assert when_conditions(started) == ["not alloy_apt_previewed"]


def test_no_tagged_task_reaches_caddy_wireguard_the_relay_or_the_probe():
    for task, _, gates in tagged("access"):
        assert not [key for key in ARGUMENT_KEYWORDS if key in task], task["name"]
        assert _admitted(task), f"{task['name']}: not on the access Alloy part's allowlist"
        assert set(notified(task)) <= {"restart alloy"}, task["name"]
        assert not REFUSED_READS.search(task_text(task, gates)), task["name"]


def test_the_alloy_part_runs_after_the_revocation_path_and_before_the_relay_gate():
    tasks = load_tasks(ACCESS)
    install = next(i for i, task in enumerate(tasks) if _imported(task) == {"name": "alloy_apt"})
    postcondition = next(
        i for i, task in enumerate(tasks) if _imported(task) == {"name": "alloy_apt", "tasks_from": "postcondition"}
    )
    caddyfile = next(
        i for i, task in enumerate(tasks) if (task.get("ansible.builtin.template") or {}).get("dest") == "/etc/caddy/Caddyfile"
    )
    revocation_path = (task_index(tasks, PINNED_LEAVES), caddyfile, task_index(tasks, RELAY_FLUSH))
    assert max(revocation_path) < install < postcondition < task_index(tasks, RELAY_READ)


def test_the_access_config_is_validated_and_restarts_alloy_on_a_change():
    config = find_task(load_tasks(ACCESS), CONFIG)
    args = config["ansible.builtin.copy"]
    assert (args.get("src"), args.get("dest"), args.get("validate")) == (
        "config.alloy",
        "/etc/alloy/config.alloy",
        "alloy validate %s",
    )
    assert notified(config) == ["restart alloy"]
    handler = find_task(load_tasks(HANDLERS), "restart alloy")
    assert handler["ansible.builtin.systemd"] == {"name": "alloy", "state": "restarted"}
