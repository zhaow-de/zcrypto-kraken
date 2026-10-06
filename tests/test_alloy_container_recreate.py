"""Each container role's Alloy tasks, read off its YAML and evaluated through Ansible's templar over constructed variables."""

from __future__ import annotations

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests.test_infra_converge_guards import ANSIBLE, assert_that, find_task, load_tasks, truthy, when_conditions

ROLES = ["capture"]
REFUSAL = "refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason"
ECHO = "the alloy_override's reason, on the record"
SECRETS_RENDER = "render the alloy secrets env file"
COMPOSE_RENDER = "render the alloy compose file"
RECREATE = "bring the alloy container to the digest, recreated when its secrets file changed"
READ = "read which image the running alloy container was created from"
IMAGE_ASSERT = "refuse a converge whose alloy container does not run the digest it converged"

COMMITTED = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
REASON = "the new digest drops journal lines here, back till it's read"

by_role = pytest.mark.parametrize("role", ROLES)


def _tasks(role: str) -> list[dict]:
    return load_tasks(ANSIBLE / "roles" / role / "tasks" / "main.yml")


def _alloy_block(role: str) -> list[dict]:
    return next(t["block"] for t in _tasks(role) if any(c.get("name") == COMPOSE_RENDER for c in t.get("block", [])))


def _render(text: str, variables: dict) -> str:
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text))


def _operands(role: str, operand: str, override: str | None) -> dict:
    variables = {f"{role}_alloy_digest": operand, "alloy_image_digest": COMMITTED}
    return variables if override is None else {**variables, "alloy_override": override}


@by_role
@pytest.mark.parametrize(
    ("operand", "override", "passes"),
    [
        pytest.param(COMMITTED, None, True, id="committed"),
        pytest.param(OTHER, None, False, id="other"),
        pytest.param(OTHER, REASON, True, id="other-reason"),
        pytest.param(OTHER, "true", False, id="other-true"),
        pytest.param(OTHER, "short", False, id="other-short"),
    ],
)
def test_an_operand_off_the_committed_digest_is_refused_unless_a_reasoned_override_rides_with_it(role, operand, override, passes):
    refusal = find_task(_tasks(role), REFUSAL)
    assert truthy(assert_that(refusal), _operands(role, operand, override)) is passes


@by_role
@pytest.mark.parametrize(
    ("operand", "override", "fires"),
    [
        pytest.param(OTHER, REASON, True, id="other-reason"),
        pytest.param(OTHER, None, False, id="other"),
        pytest.param(OTHER, "short", False, id="other-short"),
        pytest.param(COMMITTED, REASON, False, id="committed-reason"),
    ],
)
def test_the_override_echo_fires_only_on_an_accepted_override(role, operand, override, fires):
    tasks = _tasks(role)
    variables = _operands(role, operand, override)
    # A failed assert ends the host's run, so the echo runs only where the refusal passed.
    ran = truthy(assert_that(find_task(tasks, REFUSAL)), variables)
    assert (ran and truthy(when_conditions(find_task(tasks, ECHO)), variables)) is fires


@by_role
def test_the_recreate_forces_only_when_the_secrets_file_changed(role):
    args = find_task(_tasks(role), RECREATE)["ansible.builtin.command"]
    secrets = f"{role}_alloy_secrets"
    assert _render(args["cmd"], {secrets: {"changed": True}}) == "docker compose up -d --force-recreate"
    assert _render(args["cmd"], {secrets: {"changed": False}}) == "docker compose up -d"
    assert args["chdir"] == "{{ " + f"{role}_alloy_dir" + " }}"


@by_role
def test_the_image_read_names_one_field(role):
    read = find_task(_tasks(role), READ)["ansible.builtin.command"]
    assert _render(read, {}) == "docker inspect grafana-alloy --format '{{.Config.Image}}'"


@by_role
@pytest.mark.parametrize(
    ("running", "passes"),
    [
        pytest.param("{image}@" + COMMITTED, True, id="the-runs-digest"),
        pytest.param("{image}@" + OTHER, False, id="another-digest"),
        pytest.param("", False, id="empty"),
        pytest.param("{image}:v1.19.2@" + COMMITTED, False, id="behind-a-tag"),
    ],
)
def test_the_image_assert_admits_only_the_runs_digest(role, running, passes):
    image = yaml.safe_load((ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text())[f"{role}_alloy_image"]
    variables = {
        f"{role}_alloy_image": image,
        f"{role}_alloy_digest": COMMITTED,
        f"{role}_alloy_running_image": {"stdout": running.format(image=image)},
    }
    assert truthy(assert_that(find_task(_tasks(role), IMAGE_ASSERT)), variables) is passes


@by_role
def test_the_recreate_the_read_and_the_assert_end_the_block_and_skip_the_preview(role):
    block = _alloy_block(role)
    names = [task["name"] for task in block]
    assert names[-3:] == [RECREATE, READ, IMAGE_ASSERT]
    for task in block[-3:]:
        assert truthy(when_conditions(task), {"ansible_check_mode": False}), task["name"]
        assert not truthy(when_conditions(task), {"ansible_check_mode": True}), task["name"]
    assert max(names.index(SECRETS_RENDER), names.index(COMPOSE_RENDER)) < names.index(RECREATE)
    assert block[names.index(SECRETS_RENDER)].get("register") == f"{role}_alloy_secrets"
