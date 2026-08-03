"""Spec 00082: converge guards evaluated through Ansible's own templar.

The test boundary is the guard's REAL condition expression fed constructed probe outcomes --
never a re-implementation of the logic. `load_task` reads the committed YAML; a guard whose
expression is edited drifts here immediately.
"""

from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra" / "ansible"


def load_tasks(path: Path) -> list[dict]:
    # play lists (site.yml/bootstrap.yml) and role task lists parse identically; find_task recurses
    # into block/pre_tasks/tasks either way.
    return yaml.safe_load(path.read_text())


def find_task(tasks: list[dict], name: str) -> dict:
    for t in tasks:
        if t.get("name") == name:
            return t
        for key in ("block", "pre_tasks", "tasks"):
            if key in t:
                try:
                    return find_task(t[key], name)
                except KeyError:
                    continue
    raise KeyError(name)


def truthy(expr, variables: dict) -> bool:
    # ansible-core 2.19+ Data-Tagging: a plain str is UNTRUSTED and comes back unrendered -- bool()
    # of the unrendered template string would be True for every fixture, making every test vacuous.
    # trust_as_template is mandatory (measured on the locked 2.21.2; cold review C1). Never
    # re-implement guard logic in Python instead -- the committed expression is the test subject.
    from ansible.template import trust_as_template

    t = Templar(loader=DataLoader(), variables=variables)
    if isinstance(expr, list):
        return all(truthy(e, variables) for e in expr)
    return bool(t.template(trust_as_template("{{ (" + expr + ") | bool }}")))


def assert_that(task: dict) -> list[str]:
    that = task["ansible.builtin.assert"]["that"]
    return that if isinstance(that, list) else [that]


CAPTURE = ANSIBLE / "roles" / "capture" / "tasks" / "main.yml"

DIGEST_OK = {"capture_digest_probe": {"rc": 0}}
DIGEST_MISSING = {"capture_digest_probe": {"rc": 1}}


def test_capture_digest_preflight_refuses_unpulled_digest():
    task = find_task(load_tasks(CAPTURE), "preflight — refuse a digest the host has not pulled")
    assert not truthy(assert_that(task), DIGEST_MISSING)
    assert truthy(assert_that(task), DIGEST_OK)


PAIR_BASE = {"capture_pairs": ["BTC/EUR", "ETH/EUR", "XRP/BTC"]}


def test_pair_add_order_refuses_a_pair_the_primary_lacks():
    task = find_task(load_tasks(CAPTURE), "pair-add order — refuse a pair the primary does not already carry")
    refuse = {**PAIR_BASE, "capture_primary_pairs": ["BTC/EUR", "ETH/EUR"]}
    ok = {**PAIR_BASE, "capture_primary_pairs": ["BTC/EUR", "ETH/EUR", "XRP/BTC"]}
    assert not truthy(assert_that(task), refuse)
    assert truthy(assert_that(task), ok)


CANARY_BASE = {
    "capture_image_digest": "sha256:" + "c" * 64,
    "capture_secondary_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64},
}


@pytest.mark.parametrize(
    ("override", "expected"),
    [("", False), ("true", False), ("yes", False), ("short", False), ("secondary down, rolling back after incident", True)],
)
def test_canary_parity_override_semantics(override, expected):
    task = find_task(load_tasks(CAPTURE), "canary parity — refuse a primary re-pin the secondary has not baked")
    variables = {**CANARY_BASE, "canary_override": override}
    assert truthy(assert_that(task), variables) is expected


def test_canary_parity_passes_when_secondary_runs_the_candidate():
    task = find_task(load_tasks(CAPTURE), "canary parity — refuse a primary re-pin the secondary has not baked")
    ok = {
        "capture_image_digest": "sha256:" + "c" * 64,
        "capture_secondary_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "c" * 64},
        "canary_override": "",
    }
    assert truthy(assert_that(task), ok)


PINS_BASE = {"capture_running_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "a" * 64}}
PINS_FILE_WITH = "| capture | zcrypto | `" + "a" * 12 + "` | 2026-08-02 | prior |"
PINS_FILE_WITHOUT = "| capture | zcrypto | `" + "b" * 12 + "` | 2026-08-02 | prior |"


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (PINS_FILE_WITH, "", True),
        (PINS_FILE_WITHOUT, "", False),
        (PINS_FILE_WITHOUT, "true", False),
        (PINS_FILE_WITHOUT, "emergency: pins file unreachable, recorded after", True),
    ],
)
def test_pins_recording_semantics(pins_text, override, expected):
    task = find_task(load_tasks(CAPTURE), "pins recording — refuse to replace a digest fleet-pins.md does not record")
    variables = {**PINS_BASE, "capture_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected
