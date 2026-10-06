"""The ops role's share of the fleet-wide `alloy` tag: a converge that lands the Alloy part on the ops host and nothing of
the liquidations poller, the timers or the NAS paths."""

from __future__ import annotations

import re

import pytest

from tests.alloy_part import (
    TAG,
    notified,
    play_selection,
    refusal_of,
    tagged,
    task_text,
    unproduced_reads,
)
from tests.test_infra_converge_guards import OPS, assert_that, find_task, load_tasks, truthy, when_conditions

FAIL_FAST = "fail fast if an alloy run was not handed the ops host's Alloy digest"

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

# Read in a task's arguments and gates alone: the Alloy compose template's comments name the poller to say an Alloy
# redeploy never restarts it.
REFUSED_READS = re.compile(r"ops_image_digest|liquidations_decision|liquidations|rrsync|watchdog|keepalive|automount")


def test_the_ops_roles_tagged_tasks_are_exactly_its_alloy_part():
    leaves = tagged("ops")
    assert [task["name"] for task, _, _ in leaves] == ALLOY_PART
    assert {handler for task, _, _ in leaves for handler in notified(task)} == {"reload alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    unproduced = unproduced_reads("ops")
    assert not unproduced, unproduced


def test_no_tagged_task_reaches_the_poller_the_timers_or_the_nas_paths():
    for task, _, gates in tagged("ops"):
        assert (refusal := refusal_of(task, "ops")) is None, refusal
        assert set(notified(task)) <= {"reload alloy"}, task["name"]
        assert not REFUSED_READS.search(task_text(task, gates)), task["name"]


@pytest.mark.parametrize("seq", [tuple, list])
@pytest.mark.parametrize(
    ("run_tags", "digest", "engages", "passes"),
    [
        ([TAG], None, True, False),
        ([TAG], "", True, False),
        ([TAG], "sha256:" + "a" * 64, True, True),
        (["ops", TAG], None, True, False),
        (["ops"], None, False, False),
        (["all"], None, False, False),
        (["ops", "access"], None, False, False),
    ],
)
def test_an_alloy_run_refuses_without_the_ops_alloy_digest_and_no_other_run_meets_that_refusal(
    seq, run_tags, digest, engages, passes
):
    task = find_task(load_tasks(OPS), FAIL_FAST)
    assert truthy(when_conditions(task), {"ansible_run_tags": seq(run_tags)}) is engages
    assert truthy(assert_that(task), {} if digest is None else {"ops_alloy_digest": digest}) is passes


def test_an_alloy_run_on_the_ops_play_runs_the_alloy_part_beside_the_charter_note():
    pre_tasks, role_tasks = play_selection("ops_host")
    assert pre_tasks == [("ops_host", "note — the ops node's charter")]
    assert role_tasks == [("ops", name) for name in ALLOY_PART]
