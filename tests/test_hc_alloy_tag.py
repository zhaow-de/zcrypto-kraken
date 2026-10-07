"""The hc role's share of the fleet-wide `alloy` tag: the dead-man node's Alloy through the shared apt role, and nothing
else of the role."""

from __future__ import annotations

import re

import pytest

from tests.alloy_part import (
    TASK_KEYS,
    apt_admitted,
    handler_refusals,
    notified,
    off_keys,
    play_selection,
    scope_refusals,
    tagged,
    task_text,
    unproduced_reads,
)
from tests.test_infra_alloy_apt import ALLOY_APT_MAIN, ALLOY_APT_POSTCONDITION

ENV = "alloy env — the observability node's two ingest URLs and the fleet credential"
CONFIG = "alloy config — the node's metrics, its units' journals and the container's records, to the observability node"
STARTED = "alloy enabled + started"

ALLOY_PART = [*ALLOY_APT_MAIN, ENV, CONFIG, STARTED, *ALLOY_APT_POSTCONDITION]

# Never `\b`, which joins `_` to a word and so misses `hc_compose_dir`.
REFUSED_NAMES = re.compile(
    r"(?<![A-Za-z0-9])(zcrypto-hc|hc_image|compose|docker|caddy|edge|backup|sqlite|selfcheck|reboot|admin)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SHARED_NAMES = re.compile(r"\balloy_apt_\w+")
HC_VERBATIM = [("ansible.builtin.systemd_service", {"name": "alloy", "enabled": True, "state": "started"})]
HC_WRITERS = {"ansible.builtin.copy", "ansible.builtin.template"}


def _on_alloy_paths(path) -> bool:
    return isinstance(path, str) and (
        path == "/etc/default/alloy" or (path.startswith("/etc/alloy/") and ".." not in path.split("/"))
    )


def _admitted(task: dict) -> bool:
    return apt_admitted(task, HC_WRITERS, _on_alloy_paths, HC_VERBATIM)


def _reach(task: dict, gates: tuple[str, ...]) -> str | None:
    found = REFUSED_NAMES.search(SHARED_NAMES.sub("", task_text(task, gates)))
    return found.group(1).lower() if found else None


def test_the_hc_roles_tagged_tasks_are_exactly_its_alloy_part():
    leaves = tagged("hc")
    assert [task["name"] for task, _, _ in leaves] == ALLOY_PART
    assert {handler for task, _, _ in leaves for handler in notified(task)} == {"restart alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    unproduced = unproduced_reads("hc")
    assert not unproduced, unproduced


def test_no_tagged_task_reaches_the_container_caddy_the_backup_or_the_self_check():
    for task, _, gates in tagged("hc"):
        assert not (off := off_keys(task, TASK_KEYS)), (task["name"], off)
        assert _admitted(task), f"{task['name']}: not on the hc Alloy part's allowlist"
        assert set(notified(task)) <= {"restart alloy"}, task["name"]
        assert _reach(task, gates) is None, task["name"]
    assert not (refused := scope_refusals("hc")), refused
    assert not (refused := handler_refusals("hc")), refused


@pytest.mark.parametrize(
    ("argument", "value", "word"),
    [
        ("validate", "docker compose -f {{ hc_compose_dir }}/compose.yaml restart web && alloy validate %s", "docker"),
        ("validate", "systemctl start zcrypto-hc-selfcheck.service && alloy validate %s", "zcrypto-hc"),
        ("src", "{{ hc_backup_dir }}/hc.sqlite", "backup"),
    ],
    ids=["container-restart-in-validate", "selfcheck-start-in-validate", "backup-as-src"],
)
def test_a_tagged_alloy_copy_reaching_the_container_or_a_timer_through_a_role_variable_is_refused_by_the_word(
    argument, value, word
):
    copy = {"src": "config.alloy", "dest": "/etc/alloy/extra.alloy", "validate": "alloy validate %s"} | {argument: value}
    task = {"name": "another alloy config", "ansible.builtin.copy": copy, "tags": ["alloy"]}
    assert _admitted(task) and not off_keys(task, TASK_KEYS) and not notified(task)
    assert _reach(task, ()) == word


def test_an_alloy_run_on_the_hc_play_runs_the_alloy_part_beside_the_charter_note():
    pre_tasks, role_tasks = play_selection("hc_host")
    assert pre_tasks == [("hc_host", "note — the dead-man node's charter")]
    assert role_tasks == [("hc", name) for name in ALLOY_PART]
