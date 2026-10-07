"""The mon role's share of the fleet-wide `alloy` tag: a converge that lands the observability node's Alloy through the
shared apt role, and nothing of Grafana, its stores, Caddy, the tools' token, the self-check or the reboot check."""

from __future__ import annotations

import re

import pytest

from tests.alloy_part import (
    ALLOY_APT_VERBATIM,
    ARGUMENT_KEYWORDS,
    apt_admitted,
    module_entry,
    notified,
    play_selection,
    tagged,
    task_text,
    unproduced_reads,
)
from tests.test_infra_alloy_apt import ALLOY_APT_MAIN, ALLOY_APT_POSTCONDITION

CONFIG = "alloy config — the node's own metrics and journals, written to its stores on loopback"
STARTED = "alloy enabled + started"

ALLOY_PART = [*ALLOY_APT_MAIN, CONFIG, STARTED, *ALLOY_APT_POSTCONDITION]

# Bounded on letters and digits alone, never `\b`, which joins `_` to a word: the role names its stores and its token
# through `_`-joined variables, `mon_loki_dir` and `mon_token_cache` among them, and those are read as the reach they
# are. The shared role's own names, `alloy_apt_grafana_repo` among them, are blanked before the read instead.
REFUSED_NAMES = re.compile(
    r"(?<![A-Za-z0-9])(grafana|loki|prometheus|caddy|edge|token|selfcheck|reboot)(?![A-Za-z0-9])", re.IGNORECASE
)
SHARED_NAMES = re.compile(r"\balloy_apt_\w+")
# Alloy's apt source is Grafana's, the one the node's other packages install from, so its arguments name it.
GRAFANA_SOURCE = next(entry for entry in ALLOY_APT_VERBATIM if entry[0] == "ansible.builtin.deb822_repository")
MON_VERBATIM = [("ansible.builtin.systemd_service", {"name": "alloy", "enabled": True, "state": "started"})]


def _under_alloy_config_dir(path) -> bool:
    return isinstance(path, str) and path.startswith("/etc/alloy/") and ".." not in path.split("/")


def _admitted(task: dict) -> bool:
    return apt_admitted(task, {"ansible.builtin.copy"}, _under_alloy_config_dir, MON_VERBATIM)


def _reach(task: dict, gates: tuple[str, ...]) -> str | None:
    if module_entry(task) == GRAFANA_SOURCE:
        task = {key: value for key, value in task.items() if key != GRAFANA_SOURCE[0]}
    found = REFUSED_NAMES.search(SHARED_NAMES.sub("", task_text(task, gates)))
    return found.group(1).lower() if found else None


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
        assert _reach(task, gates) is None, task["name"]


@pytest.mark.parametrize(
    ("argument", "value", "word"),
    [
        ("validate", "test -d {{ mon_loki_dir }} && alloy validate %s", "loki"),
        ("validate", "curl -fsS -XPOST {{ mon_grafana_api }}/api/x && alloy validate %s", "grafana"),
        ("src", "{{ mon_token_cache }}", "token"),
    ],
    ids=["loki-dir-in-validate", "grafana-api-in-validate", "token-cache-as-src"],
)
def test_a_tagged_alloy_copy_reaching_a_store_or_the_token_through_a_role_variable_is_refused_by_the_word(argument, value, word):
    copy = {"src": "config.alloy", "dest": "/etc/alloy/extra.alloy", "validate": "alloy validate %s"} | {argument: value}
    task = {"name": "another alloy config", "ansible.builtin.copy": copy, "tags": ["alloy"]}
    assert _admitted(task) and not [key for key in ARGUMENT_KEYWORDS if key in task] and not notified(task)
    assert _reach(task, ()) == word


def test_an_alloy_run_on_the_mon_play_runs_the_alloy_part_beside_the_charter_note():
    pre_tasks, role_tasks = play_selection("mon_host")
    assert pre_tasks == [("mon_host", "note — the observability node's charter")]
    assert role_tasks == [("mon", name) for name in ALLOY_PART]
