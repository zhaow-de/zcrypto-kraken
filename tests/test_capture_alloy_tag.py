"""The capture role's share of the fleet-wide `alloy` tag: a converge that lands the Alloy part on a capture host and nothing
of the capture daemon, read off the YAML the way Ansible selects by tag -- a block's tags reach its children, a role entry's
reach every task of the role, and `always` runs whatever was asked."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.alloy_part import (
    ROLES,
    SITE,
    TAG,
    module_and_args,
    notified,
    play_selection,
    read_text,
    refusal_of,
    tagged,
    unproduced_reads,
)
from tests.test_alloy_version import alloy_version
from tests.test_infra_converge_guards import ANSIBLE, CAPTURE, assert_that, find_task, load_tasks, truthy, when_conditions

FAIL_FAST = "fail fast if an alloy run was not handed the capture host's Alloy digest"

ALLOY_PART = [
    FAIL_FAST,
    "remove the pre-conf layout's stale alloy config",
    "read the deployed alloy config's checksum (drift check — never gated on the digest)",
    "read the repo's alloy config checksum (controller-side, same algorithm)",
    "assert the deployed alloy config matches the repo",
    "refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason",
    "the alloy_override's reason, on the record",
    "create the zcrypto-alloy system user (nologin, non-key-owning, dedicated to Alloy)",
    "look up the zcrypto-alloy account",
    "derive the zcrypto-alloy uid/gid for the container user mapping",
    "look up the systemd-journal group (Alloy's journal-read group_add needs its numeric gid)",
    "derive the systemd-journal group's numeric gid for the alloy container's group_add",
    "ensure the alloy project directory exists",
    "ensure the alloy data directory exists, owned by the dedicated Alloy user",
    "ensure the alloy config directory exists",
    "install the alloy pipeline config",
    "render the alloy secrets env file",
    "render the alloy compose file",
    "bring the alloy container to the digest, recreated when its secrets file changed",
    "read which image the running alloy container was created from",
    "refuse a converge whose alloy container does not run the digest it converged",
]

# The pre_tasks a `--tags alloy` run executes on the capture and engine plays: every one tagged `always`.
ALWAYS_PRE_TASKS = [
    ("capture_host", "refuse to converge the live primary unless explicitly asked"),
    ("capture_host", "refuse an un-tagged run on the live primary"),
    ("capture_host", "note — assumes bootstrap.yml already ran"),
    ("engine_host", "note — engine_host is deliberately narrower than capture_host"),
]


def test_the_capture_roles_tagged_tasks_are_exactly_its_alloy_part():
    leaves = tagged("capture")
    assert [task["name"] for task, _, _ in leaves] == ALLOY_PART
    assert {handler for task, _, _ in leaves for handler in notified(task)} == {"reload alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    unproduced = unproduced_reads("capture")
    assert not unproduced, unproduced


CAPTURE_DAEMON_FILES = {"/opt/zcrypto-capture/compose.yaml", "/etc/systemd/system/zcrypto-capture.service"}
CAPTURE_DAEMON_SOURCES = {"compose.yaml.j2", "zcrypto-capture.service"}


def test_no_tagged_task_reaches_the_capture_daemon():
    for task, _, gates in tagged("capture"):
        assert (refusal := refusal_of(task, "capture")) is None, refusal
        module, args = module_and_args(task)
        assert "restart capture service" not in notified(task), task["name"]
        assert args.get("dest") not in CAPTURE_DAEMON_FILES and args.get("src") not in CAPTURE_DAEMON_SOURCES, task["name"]
        assert not module.endswith(("systemd", "systemd_service", "service")), task["name"]
        assert "capture_image_digest" not in read_text("capture", task, gates), task["name"]


@pytest.mark.parametrize(
    ("name", "keyword", "value"),
    [
        pytest.param(
            "remove the pre-conf layout's stale alloy config",
            "args",
            {"dest": "/opt/zcrypto-capture/compose.yaml"},
            id="args",
        ),
        pytest.param(
            "bring the alloy container to the digest, recreated when its secrets file changed",
            "environment",
            {"COMPOSE_FILE": "/opt/zcrypto-capture/compose.yaml"},
            id="environment",
        ),
    ],
)
def test_a_tagged_task_carrying_args_or_environment_is_refused_by_the_keyword(name, keyword, value):
    refusal = refusal_of({**find_task(load_tasks(CAPTURE), name), keyword: value}, "capture")
    assert refusal is not None and keyword in refusal and name in refusal, refusal


def _role_yaml() -> list[Path]:
    return sorted(p for d in ("tasks", "handlers") for p in ROLES.glob(f"*/{d}/*.yml"))


def _every_tag(node) -> set[str]:
    if isinstance(node, list):
        return set().union(set(), *(_every_tag(item) for item in node))
    if isinstance(node, dict):
        return alloy_version.tags_of(node).union(*(_every_tag(value) for value in node.values()))
    return set()


def test_only_the_roles_that_joined_the_tag_carry_it_and_no_play_does():
    """The tag is shared by name, so another role joins it deliberately, with its own guards beside these: this list
    widens in that change."""
    carriers = [p for p in [*_role_yaml(), SITE, ANSIBLE / "bootstrap.yml"] if TAG in _every_tag(load_tasks(p))]
    assert carriers == [CAPTURE, ROLES / "nas" / "tasks" / "main.yml", ROLES / "ops" / "tasks" / "main.yml"], carriers


def test_an_alloy_run_on_the_capture_and_engine_plays_runs_the_alloy_part_beside_the_always_pre_tasks():
    """Ansible's selection over every play that reaches a capture host: an `always` task in any of their roles would
    run on the primary beside the Alloy part, and only the four pre_tasks below may."""
    pre_tasks, role_tasks = play_selection("capture_host", "engine_host")
    assert pre_tasks == ALWAYS_PRE_TASKS
    assert role_tasks == [("capture", name) for name in ALLOY_PART]


def test_the_narrow_run_still_takes_the_primarys_explicit_yes():
    tasks = load_tasks(SITE)
    on_primary = {"inventory_hostname": "zcrypto", "groups": {"engine_host": ["zcrypto"]}}
    refusal = find_task(tasks, "refuse to converge the live primary unless explicitly asked")
    assert truthy(when_conditions(refusal), on_primary)
    assert not truthy(assert_that(refusal), {})
    assert truthy(assert_that(refusal), {"converge_primary": "true"})
    untagged = find_task(tasks, "refuse an un-tagged run on the live primary")
    assert truthy(assert_that(untagged), {"ansible_run_tags": [TAG], "ansible_skip_tags": []})


@pytest.mark.parametrize("seq", [tuple, list])
@pytest.mark.parametrize(
    ("run_tags", "digest", "engages", "passes"),
    [
        ([TAG], None, True, False),
        ([TAG], "", True, False),
        ([TAG], "sha256:" + "a" * 64, True, True),
        (["capture", TAG], None, True, False),
        (["capture"], None, False, False),
        (["all"], None, False, False),
        (["capture", "engine"], None, False, False),
    ],
)
def test_an_alloy_run_refuses_without_the_capture_alloy_digest_and_no_other_run_meets_that_refusal(
    seq, run_tags, digest, engages, passes
):
    task = find_task(load_tasks(CAPTURE), FAIL_FAST)
    assert truthy(when_conditions(task), {"ansible_run_tags": seq(run_tags)}) is engages
    assert truthy(assert_that(task), {} if digest is None else {"capture_alloy_digest": digest}) is passes
