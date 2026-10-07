"""The cache role's share of the fleet-wide `alloy` tag: a converge that lands the Alloy part on a cache node and nothing
of Valkey, Sentinel or the sysctl."""

from __future__ import annotations

import re

import pytest

from tests.alloy_part import (
    TAG,
    handler_refusals,
    notified,
    play_selection,
    refusal_of,
    scope_refusals,
    tagged,
    task_text,
    unproduced_reads,
)
from tests.test_infra_converge_guards import CACHE, assert_that, find_task, load_tasks, truthy, when_conditions

FAIL_FAST = "fail fast if an alloy run was not handed the cache node's Alloy digest"

ALLOY_PART = [
    FAIL_FAST,
    "read the deployed alloy config's checksum (drift check, never gated on the digest)",
    "read the repo's alloy config checksum (controller-side, same algorithm)",
    "assert the deployed alloy config matches the repo",
    "refuse an Alloy digest that is not a full sha256",
    "refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason",
    "the alloy_override's reason, on the record",
    "alloy pins recording — probe the Alloy digest this converge would replace",
    "alloy pins recording — read fleet-pins.md from the controller tree",
    "alloy pins recording — refuse to replace an Alloy digest fleet-pins.md does not record",
    "alloy pins recording — the accepted override's reason, on the record",
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

# Read in a task's arguments and gates alone: the Alloy secrets template renders `cache_sentinel_requirepass`, the
# credential the Sentinel scrape needs, and the Alloy compose template's comment names Valkey and Sentinel to say neither
# restarts.
REFUSED_READS = re.compile(
    r"zcrypto-valkey|zcrypto-sentinel|valkey|sentinel|sysctl|cache_image_digest|cache_config_reset", re.IGNORECASE
)


def test_the_cache_roles_tagged_tasks_are_exactly_its_alloy_part():
    leaves = tagged("cache")
    assert [task["name"] for task, _, _ in leaves] == ALLOY_PART
    assert {handler for task, _, _ in leaves for handler in notified(task)} == {"reload alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    unproduced = unproduced_reads("cache")
    assert not unproduced, unproduced


def test_no_tagged_task_reaches_valkey_sentinel_or_the_sysctl():
    for task, _, gates in tagged("cache"):
        assert (refusal := refusal_of(task, "cache")) is None, refusal
        assert set(notified(task)) <= {"reload alloy"}, task["name"]
        assert not REFUSED_READS.search(task_text(task, gates)), task["name"]
    assert not (refused := scope_refusals("cache")), refused
    assert not (refused := handler_refusals("cache")), refused


@pytest.mark.parametrize("seq", [tuple, list])
@pytest.mark.parametrize(
    ("run_tags", "digest", "engages", "passes"),
    [
        ([TAG], None, True, False),
        ([TAG], "", True, False),
        ([TAG], "sha256:" + "a" * 64, True, True),
        (["cache", TAG], None, True, False),
        (["cache"], None, False, False),
        (["all"], None, False, False),
        (["cache", "cache-link"], None, False, False),
    ],
)
def test_an_alloy_run_refuses_without_the_cache_alloy_digest_and_no_other_run_meets_that_refusal(
    seq, run_tags, digest, engages, passes
):
    task = find_task(load_tasks(CACHE), FAIL_FAST)
    assert truthy(when_conditions(task), {"ansible_run_tags": seq(run_tags)}) is engages
    assert truthy(assert_that(task), {} if digest is None else {"cache_alloy_digest": digest}) is passes


def test_an_alloy_run_on_the_cache_play_runs_the_alloy_part_beside_the_charter_note():
    pre_tasks, role_tasks = play_selection("cache_host")
    assert pre_tasks == [("cache_host", "note — the cache nodes' charter")]
    assert role_tasks == [("cache", name) for name in ALLOY_PART]
