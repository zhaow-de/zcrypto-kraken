"""The observability node's token tasks, read without a host: one Editor service account holding one token, cached
vault-encrypted on the controller, with every condition evaluated through Ansible's own templar."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from ansible.errors import AnsibleTemplateError
from ansible.parsing.vault import EncryptedString

from tests.test_infra_converge_guards import assert_that, find_task, iter_tasks, load_tasks, set_facts, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/mon"
TOKEN = ROLE / "tasks/token.yml"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
PATTERN = DEFAULTS["mon_token_pattern"]
# Assembled, never spelled: no tracked file carries a token-shaped literal, this one included.
WELL_SHAPED = "glsa_" + "a" * 32 + "_" + "0" * 8
# No vault secret is in reach of a test, so a vaulted value here is one that cannot be decrypted.
UNDECRYPTABLE = EncryptedString(ciphertext="a ciphertext no vault secret opens")
SECRET_NAMES = ("mon_grafana_admin_password", "mon_session", "mon_token_candidate", "mon_token_cached", "mon_token_minted")
# The admin's name is a secret too, matched where a task templates it: the lockout refusal's message names the key.
ADMIN_NAME_TEMPLATED = re.compile(r"\{\{[^}]*\bmon_grafana_admin_user\b")


def _tasks() -> list[tuple[dict, tuple[str, ...]]]:
    return iter_tasks(load_tasks(TOKEN))


def _uri(task: dict) -> dict:
    return task.get("ansible.builtin.uri", {})


def _candidate(variables: dict) -> dict:
    # Ansible's own order: a task of the block that fails hands over to the rescue, and a vaulted value that cannot
    # be decrypted fails the task that first uses it, which is the shape check and not the read.
    (cache,) = [task for task in load_tasks(TOKEN) if "rescue" in task]
    read, check = cache["block"]
    assert (read["name"], check["name"]) == ("read the token cache", "keep the cached token only when it has a token's shape")
    try:
        return set_facts(check, variables)
    except AnsibleTemplateError as refused:
        assert "undecryptable" in str(refused), "only a value that cannot be decrypted may fail the shape check"
        (rescue,) = cache["rescue"]
        return set_facts(rescue, variables)


def test_the_token_tasks_run_only_outside_check_mode():
    include = find_task(load_tasks(ROLE / "tasks/main.yml"), "the tools' service account and its one token")
    assert include["ansible.builtin.include_tasks"] == "token.yml"
    assert when_conditions(include) == ["not ansible_check_mode"]
    apis = [task["name"] for task, _ in iter_tasks(load_tasks(ROLE / "tasks/main.yml")) if "ansible.builtin.uri" in task]
    assert apis == [], f"a call to Grafana's API outside the token tasks would run in a preview: {apis}"


def test_every_call_goes_to_grafana_on_loopback():
    assert DEFAULTS["mon_grafana_api"] == "http://127.0.0.1:{{ mon_grafana_port }}"
    urls = [_uri(task)["url"] for task, _ in _tasks() if _uri(task)]
    assert len(urls) >= 10 and all(url.startswith("{{ mon_grafana_api }}/") for url in urls), urls


@pytest.mark.parametrize(
    ("cached", "kept"),
    [
        (WELL_SHAPED, WELL_SHAPED),
        (WELL_SHAPED + "\n", ""),
        (" " + WELL_SHAPED, ""),
        (WELL_SHAPED.replace("glsa_", "glsa-"), ""),
        (WELL_SHAPED + "0", ""),
        ("", ""),
        (None, ""),
        (UNDECRYPTABLE, ""),
    ],
    ids=["a token", "a trailing newline", "a leading space", "another prefix", "too long", "empty", "no cache", "undecryptable"],
)
def test_a_cached_value_reaches_a_header_only_in_a_tokens_shape(cached, kept):
    variables = {"mon_token_var": DEFAULTS["mon_token_var"], "mon_token_pattern": PATTERN}
    if cached is not None:
        variables["mon_token_cached"] = {DEFAULTS["mon_token_var"]: cached}
    assert _candidate(variables) == {"mon_token_candidate": kept}
    probe = find_task(load_tasks(TOKEN), "ask grafana whose token the cached one is")
    assert _uri(probe)["headers"] == {"Authorization": "Bearer {{ mon_token_candidate }}"}
    assert when_conditions(probe) == ["mon_token_candidate | length > 0"]
    bearers = [task["name"] for task, _ in _tasks() if "Bearer" in str(_uri(task).get("headers", ""))]
    assert bearers == [probe["name"]], "only the checked value is ever placed in an Authorization header"


def test_the_pattern_ends_where_the_string_ends():
    """`$` also matches before a trailing newline."""
    assert PATTERN.endswith("\\Z") and "$" not in PATTERN, PATTERN
    assert re.match(PATTERN, WELL_SHAPED) and not re.match(PATTERN, WELL_SHAPED + "\n")


def test_a_minted_token_is_held_to_the_shape_before_it_is_written_with_no_newline_added():
    names = [task["name"] for task, _ in _tasks()]
    mint, check, encrypt, write = (
        "mint the tools' token",
        "refuse a minted token of another shape before it is written",
        "encrypt the minted token under the repo's vault password",
        "write the token cache on the controller",
    )
    assert names.index(mint) < names.index(check) < names.index(encrypt) < names.index(write)
    refusal = find_task(load_tasks(TOKEN), check)
    for key, admitted in ((WELL_SHAPED, True), (WELL_SHAPED + "\n", False), ("", False)):
        variables = {"mon_token_pattern": PATTERN, "mon_token_minted": {"json": {"key": key}}}
        assert truthy(assert_that(refusal), variables) is admitted, repr(key)
    command = find_task(load_tasks(TOKEN), encrypt)["ansible.builtin.command"]
    assert command["argv"] == ["ansible-vault", "encrypt_string", "--stdin-name", "{{ mon_token_var }}"]
    assert command["stdin"] == "{{ mon_token_minted.json.key }}" and command["stdin_add_newline"] is False
    copy = find_task(load_tasks(TOKEN), write)["ansible.builtin.copy"]
    assert (copy["dest"], copy["mode"]) == ("{{ mon_token_cache }}", "0600")


def test_the_token_never_lands_on_the_node():
    """Whatever reads or writes the cache runs on the controller, as the operator and not as root."""
    # include_vars is an action that reads on the controller whatever the task's host; every other task naming the
    # cache's path, and the one that encrypts for it, is delegated there.
    names_the_cache = re.compile(r"\bmon_token_cache\b")
    controller = [
        task
        for task, _ in _tasks()
        if (names_the_cache.search(str(task)) and "ansible.builtin.include_vars" not in task)
        or task.get("register") == "mon_token_encrypted"
    ]
    assert len(controller) == 4, [task["name"] for task in controller]
    for task in controller:
        assert task.get("delegate_to") == "localhost" and task.get("become") is False, task["name"]
    delegated = [task for task, _ in _tasks() if "delegate_to" in task]
    assert all(task["become"] is False for task in delegated), (
        "a delegated task under the play's become runs sudo on the workstation"
    )
    assert "ansible.builtin.env" in DEFAULTS["mon_token_cache"] and "/.config/zcrypto/" in DEFAULTS["mon_token_cache"]


@pytest.mark.parametrize(
    ("variables", "minted"),
    [
        ({}, False),
        ({"mon_grafana_token_rotate": "true"}, True),
        ({"mon_token_candidate": ""}, True),
        ({"mon_token_probe": {"status": 401, "json": {"message": "Invalid API key"}}}, True),
        ({"mon_token_probe": {"status": 200, "json": {"login": "sa-1-another"}}}, True),
        ({"mon_sa_tokens": {"json": [{"id": 1}, {"id": 2}]}}, True),
        ({"mon_sa_tokens": {"json": []}}, True),
    ],
    ids=["steady", "rotation asked", "no usable cache", "refused", "another account's", "not the only token", "no token"],
)
def test_a_token_is_minted_exactly_when_the_cached_one_cannot_be_kept(variables, minted):
    steady = {
        "mon_token_candidate": WELL_SHAPED,
        "mon_token_probe": {"status": 200, "json": {"login": "sa-1-zcrypto-tools"}},
        "mon_sa": {"id": 2, "login": "sa-1-zcrypto-tools"},
        "mon_sa_tokens": {"json": [{"id": 1}]},
    }
    task = find_task(load_tasks(TOKEN), "decide whether a token is minted")
    assert bool(set_facts(task, {**steady, **variables})["mon_token_mint"]) is minted
    for name in ("mint the tools' token", "write the token cache on the controller"):
        assert when_conditions(find_task(load_tasks(TOKEN), name)) == ["mon_token_mint"]
    delete = find_task(load_tasks(TOKEN), "delete every token the mint superseded")
    assert delete["loop"] == "{{ mon_sa_tokens.json if mon_token_mint else [] }}", "a kept token must never be deleted"


def test_the_one_service_account_is_an_editor_and_no_other_is_created():
    creates = [
        task for task, _ in _tasks() if _uri(task).get("method") == "POST" and _uri(task)["url"].endswith("/api/serviceaccounts")
    ]
    assert len(creates) == 1, [task["name"] for task in creates]
    body = _uri(creates[0])["body"]
    assert body == {"name": "{{ mon_service_account }}", "role": "Editor", "isDisabled": False}
    assert DEFAULTS["mon_service_account"] == "zcrypto-tools"
    roles = [_uri(task)["body"]["role"] for task, _ in _tasks() if "role" in (_uri(task).get("body") or {})]
    assert roles == ["Editor", "Editor"], f"the account is created an Editor and returned to one, never more: {roles}"
    drift = find_task(load_tasks(TOKEN), "return a drifted service account to an enabled Editor")
    for account, corrected in (
        ({"role": "Editor", "isDisabled": False}, False),
        ({"role": "Admin", "isDisabled": False}, True),
        ({"role": "Viewer", "isDisabled": False}, True),
        ({"role": "Editor", "isDisabled": True}, True),
    ):
        assert truthy(when_conditions(drift), {"mon_sa": account}) is corrected, account


def test_a_refused_sign_in_is_repaired_once_from_the_vault_and_never_retried():
    sign_ins = [task for task, _ in _tasks() if _uri(task).get("url", "").endswith("/login")]
    assert [task["name"] for task in sign_ins] == [
        "sign in on loopback with the vaulted admin password",
        "sign in again after the reset",
    ]
    for task in sign_ins:
        assert _uri(task)["status_code"] == [200, 401] and "retries" not in task and "until" not in task, task["name"]
        assert _uri(task)["body"] == {"user": "{{ mon_grafana_admin_user }}", "password": "{{ mon_grafana_admin_password }}"}
    reset = find_task(load_tasks(TOKEN), "reset the admin password from the vault")
    command = reset["ansible.builtin.command"]
    assert command["argv"][:5] == ["runuser", "-u", "grafana", "--", "/usr/share/grafana/bin/grafana"]
    override = command["argv"].index("--configOverrides")
    assert command["argv"][override + 1] == "cfg:default.paths.data=/var/lib/grafana"
    assert command["argv"][-3:] == ["admin", "reset-admin-password", "--password-from-stdin"]
    assert command["stdin"] == "{{ mon_grafana_admin_password }}" and command["stdin_add_newline"] is False
    assert when_conditions(reset) == when_conditions(sign_ins[1]) == ["mon_login.status == 401"]
    refusal = find_task(load_tasks(TOKEN), "refuse to go on when the vaulted password is still refused")
    for first, second, admitted in ((200, None, True), (401, 200, True), (401, 401, False)):
        variables = {"mon_login": {"status": first}, "mon_login_again": {"status": second} if second else {"skipped": True}}
        assert truthy(assert_that(refusal), variables) is admitted, (first, second)
    said = refusal["ansible.builtin.assert"]["fail_msg"]
    assert "lockout" in said and "mon_grafana_admin_user" in said, "a second refusal has two causes, and the message names both"


def test_every_task_that_carries_a_secret_is_silent_and_the_session_is_always_ended():
    for task, _ in _tasks():
        text = yaml.safe_dump({k: v for k, v in task.items() if k not in ("name", "when", "register")})
        if any(name in text for name in SECRET_NAMES) or ADMIN_NAME_TEMPLATED.search(text):
            assert task.get("no_log") is True, f"{task['name']} carries a secret and would print it on failure"
    (session,) = [task for task in load_tasks(TOKEN) if "always" in task]
    assert [task["name"] for task in session["always"]] == ["end the admin session"]
    assert _uri(session["always"][0])["url"] == "{{ mon_grafana_api }}/logout"


def test_no_tracked_file_carries_a_token_shaped_literal():
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout.split(
        "\0"
    )
    assert len(tracked) > 500, "the walk is broken, not the tree clean"
    shaped = re.compile(rb"glsa_[A-Za-z0-9]{32}_[0-9a-f]{8}")
    found = [path for path in tracked if path and (REPO / path).is_file() and shaped.search((REPO / path).read_bytes())]
    assert found == [], f"a Grafana service-account token, or a literal shaped like one, is tracked in: {found}"
