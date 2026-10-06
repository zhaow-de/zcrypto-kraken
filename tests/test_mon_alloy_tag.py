"""The mon role's share of the fleet-wide `alloy` tag: a converge that lands the observability node's Alloy through the
shared apt role, and nothing of Grafana, its stores, Caddy, the tools' token, the self-check or the reboot check."""

from __future__ import annotations

import re

from tests.alloy_part import ARGUMENT_KEYWORDS, ROLES, module_entry, notified, play_selection, tagged, task_text, unproduced_reads
from tests.test_infra_alloy_apt import ALLOY_APT_FREE, ALLOY_APT_MAIN, ALLOY_APT_POSTCONDITION, ALLOY_APT_VERBATIM

CONFIG = "alloy config — the node's own metrics and journals, written to its stores on loopback"
STARTED = "alloy enabled + started"

ALLOY_PART = [*ALLOY_APT_MAIN, CONFIG, STARTED, *ALLOY_APT_POSTCONDITION]

# Word-bounded, so a register or variable that carries one of these inside its name, `alloy_apt_grafana_repo` among
# them, is not read as a reach.
REFUSED_NAMES = re.compile(r"\b(grafana|loki|prometheus|caddy|edge|token|selfcheck|reboot)\b", re.IGNORECASE)
# Alloy's apt source is Grafana's, the one the node's other packages install from, so its arguments name it.
GRAFANA_SOURCE = next(entry for entry in ALLOY_APT_VERBATIM if entry[0] == "ansible.builtin.deb822_repository")
MON_VERBATIM = [("ansible.builtin.systemd_service", {"name": "alloy", "enabled": True, "state": "started"})]


def _under_alloy_config_dir(path) -> bool:
    return isinstance(path, str) and path.startswith("/etc/alloy/") and ".." not in path.split("/")


def _admitted(task: dict) -> bool:
    entry = module_entry(task)
    if entry is None:
        return False
    module, value = entry
    if module in ALLOY_APT_FREE or entry in ALLOY_APT_VERBATIM or entry in MON_VERBATIM:
        return True
    if module == "ansible.builtin.copy" and isinstance(value, dict):
        written = [value[key] for key in ("path", "dest", "name") if key in value]
        return bool(written) and all(_under_alloy_config_dir(path) for path in written)
    return False


def _named_text(task: dict, gates: tuple[str, ...]) -> str:
    if module_entry(task) == GRAFANA_SOURCE:
        task = {key: value for key, value in task.items() if key != GRAFANA_SOURCE[0]}
    return task_text(task, gates)


def test_the_mon_roles_tagged_tasks_are_exactly_its_alloy_part():
    leaves = tagged("mon")
    assert [task["name"] for task, _, _ in leaves] == ALLOY_PART
    assert {handler for task, _, _ in leaves for handler in notified(task)} == {"restart alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    unproduced = unproduced_reads("mon")
    assert not unproduced, unproduced


def test_no_tagged_task_reaches_grafana_its_stores_or_caddy():
    for task, _, gates in tagged("mon"):
        assert not [key for key in ARGUMENT_KEYWORDS if key in task], task["name"]
        assert _admitted(task), f"{task['name']}: not on the mon Alloy part's allowlist"
        assert set(notified(task)) <= {"restart alloy"}, task["name"]
        assert not REFUSED_NAMES.search(_named_text(task, gates)), task["name"]


def test_an_alloy_run_on_the_mon_play_runs_the_alloy_part_beside_the_charter_note():
    pre_tasks, role_tasks = play_selection("mon_host")
    assert pre_tasks == [("mon_host", "note — the observability node's charter")]
    assert role_tasks == [("mon", name) for name in ALLOY_PART]
