from __future__ import annotations

from pathlib import Path

import pytest

from tests import role_render
from tests.test_infra_converge_guards import load_tasks

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


def test_the_default_list_refuses_nothing():
    default = role_render.variables(ROLE, {})["node_common_secrets_preflight"]
    assert default == []
    role_render.assert_preflight(_preflight(), {}, {}, None, INCLUDE | {"node_common_secrets_preflight": default})
