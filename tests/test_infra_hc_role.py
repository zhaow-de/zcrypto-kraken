"""The dead-man node's role, read without a host: its templates rendered through Ansible's own templar over the role's
defaults, and its task and handler conditions evaluated the same way. What only a converge can show -- the image's
start, the superuser's sign-in, the edge's certificate -- is the rollout's, not this file's."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests import role_render
from tests.alloy_part import ALLOY_APT_VERBATIM, module_entry
from tests.test_alloy_version import alloy_version
from tests.test_infra_alloy_stages import _alloy_string, _hc_match, _stage_blocks
from tests.test_infra_converge_guards import (
    assert_that,
    find_task,
    iter_tasks,
    load_tasks,
    task_index,
    truthy,
    when_conditions,
)

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ROLE = ANSIBLE / "roles/hc"
TASKS = ROLE / "tasks/main.yml"
ADMIN = ROLE / "tasks/admin.yml"
HANDLERS = ROLE / "handlers/main.yml"
NODE_COMMON = ANSIBLE / "roles/node_common"
ALLOY = ROLE / "files/config.alloy"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
TAG = "v6.1.0"
# Shaped like what the generator and SES write; none is a credential.
SECRETS = {
    "hc_secret_key": "0123456789abcdef" * 4,
    "hc_admin_password": "fedcba9876543210" * 3,
    "hc_email_host_user": "AKIA" + "Q" * 16,
    "hc_email_host_password": "S" * 44,
}
PING_URL = "https://zcrypto-hc.zhaow.me/ping/" + "k" * 22 + "/zcrypto-hc"
PLAIN = {
    "hc_email_host": "email-smtp.eu-central-1.amazonaws.com",
    "hc_email_from": "z-no-reply@example.test",
    "hc_admin_email": "owner@example.test",
    "hc_selfcheck_healthcheck_url": PING_URL,
}
VAULT_PREFLIGHT = "refuse a missing or misshapen secret, naming the key and never the value"
PLAIN_PREFLIGHT = "the plain values the env file and the self-check read, refused by shape"
# The names the clone's docker/.env.example and hc/settings.py read at v6.1.0 that this node sets.
ENV_NAMES = {
    "SECRET_KEY",
    "SITE_ROOT",
    "ALLOWED_HOSTS",
    "DEBUG",
    "DB_NAME",
    "SECURE_PROXY_SSL_HEADER",
    "LOG_FORMAT",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_USE_TLS",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "DEFAULT_FROM_EMAIL",
}
VAULTED_ENV = {
    "SECRET_KEY": "hc_secret_key",
    "EMAIL_HOST_USER": "hc_email_host_user",
    "EMAIL_HOST_PASSWORD": "hc_email_host_password",
}

# The includes as the role must carry them, in its order.
INCLUDES = yaml.safe_load(
    r"""
- name: refuse a missing or misshapen secret, naming the key and never the value
  ansible.builtin.include_role: {name: node_common, tasks_from: secrets-preflight}
  vars:
    node_common_role_name: hc
    node_common_secrets_preflight_file: host_vars/zcrypto-hc/vault.yml
    node_common_secrets_preflight_runbook: infra/runbooks/hc.md's hc-secrets procedure
    node_common_secrets_preflight:
      - {key: hc_secret_key, shape: '[0-9a-f]{64}\Z'}
      - {key: hc_admin_password, shape: '[0-9a-f]{48}\Z'}
      - {key: hc_email_host_user, shape: '[A-Z0-9]{16,}\Z'}
      - {key: hc_email_host_password, shape: '[A-Za-z0-9+/=]{40,}\Z'}
- name: the plain values the env file and the self-check read, refused by shape
  ansible.builtin.include_role: {name: node_common, tasks_from: secrets-preflight}
  vars:
    node_common_role_name: hc
    node_common_secrets_preflight_file: host_vars/zcrypto-hc/vars.yml
    node_common_secrets_preflight_runbook: infra/runbooks/hc.md's hc-secrets procedure
    node_common_secrets_preflight:
      - {key: hc_email_host, shape: 'email-smtp\.[a-z0-9-]+\.amazonaws\.com\Z'}
      - {key: hc_email_from, shape: '[^@\s]+@[^@\s]+\Z'}
      - {key: hc_admin_email, shape: '[^@\s]+@[^@\s]+\Z'}
      - {key: hc_selfcheck_healthcheck_url, shape: 'https://zcrypto-hc\.zhaow\.me/ping/[A-Za-z0-9_-]{16,}/[a-z0-9-]+\Z'}
- name: the edge in front of the service on loopback
  ansible.builtin.include_role: {name: edge}
  vars:
    edge_role_name: hc
    edge_hostname: "{{ hc_hostname }}"
    edge_acme_email: "{{ hc_acme_email }}"
    edge_basic_auth_routes: []
    edge_paths_404: []
    edge_head_paths: []
    edge_session_cookie: ""
    edge_upstream_port: "{{ hc_port }}"
- name: the reboot check
  ansible.builtin.include_role: {name: node_common, tasks_from: reboot-check}
  vars:
    node_common_role_name: hc
    node_common_reboot_check_textfile_dir: "{{ hc_textfile_dir }}"
- name: the self-check
  ansible.builtin.include_role: {name: node_common, tasks_from: selfcheck}
  vars:
    node_common_role_name: hc
    node_common_selfcheck_name: zcrypto-hc-selfcheck
    node_common_selfcheck_script: zcrypto-hc-selfcheck.py
    node_common_selfcheck_description: Ping the dead-man service's own check while its web answers and a ping is stored
    node_common_selfcheck_timer_description: Every-5-minutes self-check of the dead-man service
    node_common_selfcheck_environment:
      HC_SELFCHECK_STATUS: "http://127.0.0.1:{{ hc_port }}/api/v3/status/"
      HC_SELFCHECK_HOST: "{{ hc_hostname }}"
    node_common_selfcheck_env_var: HC_SELFCHECK_HEALTHCHECK_URL
    node_common_selfcheck_env_value: "{{ hc_selfcheck_healthcheck_url }}"
    node_common_selfcheck_on_calendar: "*:0/5:23"
- name: the nightly backup
  ansible.builtin.include_role: {name: node_common, tasks_from: sqlite-backup}
  vars:
    node_common_role_name: hc
    node_common_sqlite_backup_name: hc
    node_common_sqlite_backup_db: /data/hc.sqlite
    node_common_sqlite_backup_staging: /data/backups
    node_common_sqlite_backup_dest: "{{ hc_backup_dir }}"
    node_common_sqlite_backup_keep_days: "{{ hc_backup_keep_days }}"
    node_common_sqlite_backup_runner: "docker compose -f {{ hc_compose_dir }}/compose.yaml exec -T web"
    node_common_sqlite_backup_copy: "docker compose -f {{ hc_compose_dir }}/compose.yaml cp web:"
    node_common_sqlite_backup_group: "{{ hc_data_user }}"
    node_common_sqlite_backup_textfile: "{{ hc_textfile_dir }}/sqlite-backup.prom"
"""
)


def _render(name: str, **extra) -> str:
    return role_render.render(ROLE, name, SECRETS, **(PLAIN | {"hc_image_tag": TAG} | extra))


def _tasks() -> list[dict]:
    return load_tasks(TASKS)


def _handlers() -> dict[str, dict]:
    return {handler["name"]: handler for handler in load_tasks(HANDLERS)}


def _env_lines(text: str) -> dict[str, str]:
    pairs = [line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#")]
    names = [name for name, _ in pairs]
    assert len(names) == len(set(names)), f"a name set twice: {names}"
    return dict(pairs)


def _include(name: str) -> dict:
    return find_task(_tasks(), name)


# --- the play and the includes ------------------------------------------------------------------------------------
def test_the_play_runs_seven_roles_each_under_its_own_tag():
    (play,) = [p for p in load_tasks(ANSIBLE / "site.yml") if p["hosts"] == "hc_host"]
    assert [(role["role"], role["tags"]) for role in play["roles"]] == [
        ("base", ["base"]),
        ("hardening", ["hardening"]),
        ("firewall", ["firewall"]),
        ("fail2ban", ["fail2ban"]),
        ("chrony", ["chrony"]),
        ("docker", ["docker"]),
        ("hc", ["hc"]),
    ]


def test_the_shared_includes_run_in_the_roles_order_with_exactly_their_variables():
    includes = [task for task in _tasks() if "ansible.builtin.include_role" in task]
    assert [(t["name"], t["ansible.builtin.include_role"], t["vars"]) for t in includes] == [
        (t["name"], t["ansible.builtin.include_role"], t["vars"]) for t in INCLUDES
    ]
    assert [task["name"] for task in _tasks()[:2]] == [VAULT_PREFLIGHT, PLAIN_PREFLIGHT], "a no_log task would run first"


# --- the two preflights: refused by name when missing or misshapen ------------------------------------------------
def _preflight() -> dict:
    (task,) = load_tasks(NODE_COMMON / "tasks/secrets-preflight.yml")
    return task


@pytest.mark.parametrize(
    ("override", "refused"),
    [
        ({}, None),
        ({"hc_secret_key": None}, "hc_secret_key"),
        ({"hc_secret_key": SECRETS["hc_secret_key"] + "\n"}, "hc_secret_key"),
        ({"hc_secret_key": SECRETS["hc_secret_key"].upper()}, "hc_secret_key"),
        ({"hc_secret_key": SECRETS["hc_secret_key"][:-1]}, "hc_secret_key"),
        ({"hc_secret_key": "$" + SECRETS["hc_secret_key"][1:]}, "hc_secret_key"),
        ({"hc_admin_password": SECRETS["hc_admin_password"] + "0" * 16}, "hc_admin_password"),
        ({"hc_admin_password": ""}, "hc_admin_password"),
        ({"hc_email_host_user": SECRETS["hc_email_host_user"].lower()}, "hc_email_host_user"),
        ({"hc_email_host_user": "AKIA" + "Q" * 11}, "hc_email_host_user"),
        ({"hc_email_host_password": "S" * 39}, "hc_email_host_password"),
        ({"hc_email_host_password": "S" * 43 + " "}, "hc_email_host_password"),
        ({"hc_email_host_password": SECRETS["hc_email_host_password"] + "\n"}, "hc_email_host_password"),
    ],
    ids=[
        "all four",
        "the secret key missing",
        "the secret key with a trailing newline",
        "the secret key in capitals",
        "the secret key a character short",
        "a dollar compose would interpolate",
        "the password too long",
        "the password empty",
        "the SMTP user in lowercase",
        "the SMTP user too short",
        "the SMTP password too short",
        "the SMTP password with a space",
        "the SMTP password with a trailing newline",
    ],
)
def test_a_missing_or_misshapen_vaulted_value_is_refused_by_its_key(override, refused):
    role_render.assert_preflight(_preflight(), SECRETS, override, refused, _include(VAULT_PREFLIGHT)["vars"])


@pytest.mark.parametrize(
    ("override", "refused"),
    [
        ({}, None),
        ({"hc_selfcheck_healthcheck_url": ""}, "hc_selfcheck_healthcheck_url"),
        ({"hc_email_host": ""}, "hc_email_host"),
        ({"hc_email_host": None}, "hc_email_host"),
        ({"hc_email_host": "smtp.example.test"}, "hc_email_host"),
        ({"hc_email_host": PLAIN["hc_email_host"] + ".example.test"}, "hc_email_host"),
        ({"hc_email_host": PLAIN["hc_email_host"] + "\n"}, "hc_email_host"),
        ({"hc_email_from": "no-at-sign"}, "hc_email_from"),
        ({"hc_email_from": "a@b@c"}, "hc_email_from"),
        ({"hc_admin_email": ""}, "hc_admin_email"),
        ({"hc_admin_email": "owner @example.test"}, "hc_admin_email"),
        (
            {"hc_selfcheck_healthcheck_url": "https://hc-ping.com/" + "0" * 8 + "-0000-4000-8000-" + "0" * 12},
            "hc_selfcheck_healthcheck_url",
        ),
        ({"hc_selfcheck_healthcheck_url": PING_URL.removesuffix("/zcrypto-hc")}, "hc_selfcheck_healthcheck_url"),
        ({"hc_selfcheck_healthcheck_url": PING_URL.replace("/zcrypto-hc", "/Zcrypto-hc")}, "hc_selfcheck_healthcheck_url"),
        ({"hc_selfcheck_healthcheck_url": PING_URL + "\n"}, "hc_selfcheck_healthcheck_url"),
    ],
    ids=[
        "all four",
        "the ping URL empty",
        "the SES endpoint not yet written",
        "the SES endpoint missing",
        "an SMTP host off SES",
        "an SES name with a suffix",
        "the SES endpoint with a trailing newline",
        "a sender with no at-sign",
        "a sender with two",
        "the superuser's email empty",
        "the superuser's email with a space",
        "a ping URL off the clone",
        "a ping URL naming no check",
        "a ping URL whose slug is not lowercase",
        "a ping URL with a trailing newline",
    ],
)
def test_a_missing_or_misshapen_plain_value_is_refused_by_its_key(override, refused):
    role_render.assert_preflight(_preflight(), PLAIN, override, refused, _include(PLAIN_PREFLIGHT)["vars"])


# --- the pinned image: a version tag, pulled, and the running one recorded ---------------------------------------
TAG_SHAPE = "refuse an hc_image_tag that is not a version tag"
PULLED_PROBE = "probe — is the pinned tag already on this host"
PREFLIGHT = "preflight — refuse a tag the host has not pulled"
RUNNING_PROBE = "probe — the currently-running tag this converge would replace (pins recording)"
PINS_READ = "read fleet-pins.md from the controller tree"
PINS = "pins recording — refuse to replace a tag fleet-pins.md does not record"
PINS_ECHO = "pins override accepted — the reason, on the record"
RUNNING = {"hc_running_tag_probe": {"rc": 0, "stdout": f"ghcr.io/zhaow-de/healthchecks:{TAG}"}}
PINS_WITH = f"| hc | zcrypto-hc | `{TAG}` | 2026-10-07 10:00:00 | first pin |"
PINS_WITHOUT = "| hc | zcrypto-hc | `v6.1.10` | 2026-10-07 10:00:00 | first pin |"
PINS_REASON = "first pin recorded right after this converge"


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        (TAG, True),
        ("v10.0.12", True),
        ("", False),
        ("6.1.0", False),
        ("v6.1", False),
        ("latest", False),
        ("v6.1.0-rc1", False),
        ("v6x1.0", False),
        (TAG + "\n", False),
        ("sha256:" + "c" * 64, False),
    ],
)
def test_the_tag_must_be_a_version_tag(tag, expected):
    assert truthy(assert_that(find_task(_tasks(), TAG_SHAPE)), {"hc_image_tag": tag}) is expected


def test_a_converge_naming_no_tag_is_refused_and_the_role_holds_no_default():
    assert not truthy(assert_that(find_task(_tasks(), TAG_SHAPE)), {})
    assert not {"hc_image_tag"} & DEFAULTS.keys()
    assert not when_conditions(find_task(_tasks(), TAG_SHAPE)), "a gated refusal lets a converge without the tag through"


def test_an_unpulled_tag_is_refused_before_anything_renders():
    probe = find_task(_tasks(), PULLED_PROBE)
    assert probe["ansible.builtin.command"] == 'docker image inspect "{{ hc_image }}:{{ hc_image_tag }}"'
    task = find_task(_tasks(), PREFLIGHT)
    assert not truthy(assert_that(task), {probe["register"]: {"rc": 1}})
    assert truthy(assert_that(task), {probe["register"]: {"rc": 0}})


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (PINS_WITH, "", True),
        (PINS_WITHOUT, "", False),
        (PINS_WITHOUT, "true", False),
        (PINS_WITHOUT, "short", False),
        (PINS_WITHOUT, PINS_REASON, True),
    ],
)
def test_the_pins_recording_semantics(pins_text, override, expected):
    variables = {**RUNNING, "hc_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(find_task(_tasks(), PINS)), variables) is expected


@pytest.mark.parametrize("stdout", ["", "ghcr.io/zhaow-de/healthchecks:latest", "ghcr.io/zhaow-de/healthchecks@sha256:" + "c" * 64])
def test_a_running_image_named_by_no_version_tag_fails_closed(stdout):
    variables = {"hc_running_tag_probe": {"rc": 0, "stdout": stdout}, "hc_fleet_pins_text": PINS_WITH + " ``", "pins_override": ""}
    assert not truthy(assert_that(find_task(_tasks(), PINS)), variables)


def test_the_pins_refusal_and_its_read_stand_down_when_no_container_runs():
    stopped = {"hc_running_tag_probe": {"rc": 1, "stdout": ""}}
    assert not truthy(when_conditions(find_task(_tasks(), PINS_READ)), stopped)
    assert not truthy(when_conditions(find_task(_tasks(), PINS)), stopped)
    assert truthy(when_conditions(find_task(_tasks(), PINS)), {**RUNNING, "hc_fleet_pins_text": PINS_WITH})


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [(PINS_WITHOUT, PINS_REASON, True), (PINS_WITHOUT, "", False), (PINS_WITHOUT, "short", False), (PINS_WITH, PINS_REASON, False)],
)
def test_the_pins_override_echo_fires_only_on_an_accepted_override(pins_text, override, expected):
    variables = {**RUNNING, "hc_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(when_conditions(find_task(_tasks(), PINS_ECHO)), variables) is expected


def test_the_probes_read_the_container_the_compose_file_names_and_never_fail_change_or_skip_under_check():
    container = yaml.safe_load(_render("compose.yaml.j2"))["services"]["web"]["container_name"]
    running = find_task(_tasks(), RUNNING_PROBE)["ansible.builtin.command"]
    assert running == 'docker inspect --format \'{{ "{{" }}.Config.Image{{ "}}" }}\' ' + container
    for name in (PULLED_PROBE, RUNNING_PROBE):
        probe = find_task(_tasks(), name)
        assert (probe.get("failed_when"), probe.get("changed_when"), probe.get("check_mode")) == (False, False, False), name


def test_the_guards_run_in_order_before_the_first_render():
    order = [
        TAG_SHAPE,
        PULLED_PROBE,
        PREFLIGHT,
        RUNNING_PROBE,
        PINS_READ,
        PINS,
        PINS_ECHO,
        ENV_RENDER,
        COMPOSE_RENDER,
        UNIT_RENDER,
        START,
        ADMIN_INCLUDE,
    ]
    assert [task_index(_tasks(), name) for name in order] == sorted(task_index(_tasks(), name) for name in order)


# --- the env file, the compose file and the unit ------------------------------------------------------------------
ENV_RENDER = "render the clone's env file, read by compose alone"
COMPOSE_RENDER = "render the compose file"
UNIT_RENDER = "render the dead-man service's systemd unit"
START = "enable + start the dead-man service (boot resume)"


def test_the_env_file_sets_the_names_the_clone_reads_and_logs_json():
    env = _env_lines(_render("hc.env.j2"))
    assert set(env) == ENV_NAMES
    assert env["LOG_FORMAT"] == "json"
    assert (env["SITE_ROOT"], env["ALLOWED_HOSTS"]) == (f"https://{DEFAULTS['hc_hostname']}", DEFAULTS["hc_hostname"])
    assert (env["DEBUG"], env["EMAIL_USE_TLS"], env["EMAIL_PORT"]) == ("False", "True", "587")
    assert env["SECURE_PROXY_SSL_HEADER"] == "HTTP_X_FORWARDED_PROTO,https"
    assert (env["EMAIL_HOST"], env["DEFAULT_FROM_EMAIL"]) == (PLAIN["hc_email_host"], PLAIN["hc_email_from"])
    (backup,) = [t for t in _tasks() if t.get("ansible.builtin.include_role", {}).get("tasks_from") == "sqlite-backup"]
    assert env["DB_NAME"] == backup["vars"]["node_common_sqlite_backup_db"], "the backup would read another database"


def test_each_vaulted_value_reaches_the_env_file_once_under_its_own_name_and_the_template_carries_none():
    rendered = _render("hc.env.j2")
    env = _env_lines(rendered)
    for name, key in VAULTED_ENV.items():
        assert env[name] == SECRETS[key], name
        assert rendered.count(SECRETS[key]) == 1, key
    assert rendered.count(SECRETS["hc_admin_password"]) == 0, "the superuser's password travels on admin.yml's stdin alone"
    template = _env_lines((ROLE / "templates/hc.env.j2").read_text())
    assert {name: template[name] for name in VAULTED_ENV} == {name: "{{ " + key + " }}" for name, key in VAULTED_ENV.items()}


def test_the_env_file_is_rendered_root_only_and_never_logged_or_diffed():
    task = find_task(_tasks(), ENV_RENDER)
    template = task["ansible.builtin.template"]
    assert (template["owner"], template["group"], template["mode"]) == ("root", "root", "0600")
    assert task["no_log"] is True and task["diff"] is False, "a preview's diff would print the secret key"
    assert task["notify"] == "restart hc service"
    compose = yaml.safe_load(_render("compose.yaml.j2"))
    (env_file,) = compose["services"]["web"]["env_file"]
    assert template["dest"] == "{{ hc_compose_dir }}/" + env_file.removeprefix("./")


def test_the_compose_file_runs_the_pinned_tag_on_loopback_and_never_pulls():
    assert yaml.safe_load(_render("compose.yaml.j2")) == {
        "services": {
            "web": {
                "image": f"ghcr.io/zhaow-de/healthchecks:{TAG}",
                "container_name": "zcrypto-hc",
                "restart": "unless-stopped",
                "pull_policy": "never",
                "ports": ["127.0.0.1:8000:8000"],
                "env_file": ["./hc.env"],
                "volumes": ["hc-data:/data"],
                "logging": {"driver": "journald"},
            }
        },
        "volumes": {"hc-data": {}},
    }
    task = find_task(_tasks(), COMPOSE_RENDER)
    assert (
        task["ansible.builtin.template"]["dest"] == "{{ hc_compose_dir }}/compose.yaml" and task["notify"] == "restart hc service"
    )


def test_the_unit_runs_the_compose_project_and_never_pulls():
    lines = _render("zcrypto-hc.service.j2").splitlines()
    settings = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    compose = f"{DEFAULTS['hc_compose_dir']}/compose.yaml"
    assert settings["ExecStart"] == f"/usr/bin/docker compose -f {compose} up"
    assert settings["ExecStop"] == f"/usr/bin/docker compose -f {compose} down"
    assert (settings["Restart"], settings["WorkingDirectory"]) == ("always", DEFAULTS["hc_compose_dir"])
    assert [line for line in lines if re.search(r"\bpull\b", line)] == []
    task = find_task(_tasks(), UNIT_RENDER)
    assert task["ansible.builtin.template"]["dest"] == "/etc/systemd/system/zcrypto-hc.service"
    assert task["notify"] == "restart hc service"


# --- the preview gates ----------------------------------------------------------------------------------------------
_CHANGED, _UNCHANGED = {"changed": True}, {"changed": False}


@pytest.mark.parametrize(
    ("check", "unit", "expected"),
    [(True, _CHANGED, False), (True, _UNCHANGED, True), (False, _CHANGED, True)],
    ids=["a first-install preview", "an established node's preview", "a real converge"],
)
def test_the_service_starts_except_on_a_preview_that_never_wrote_its_unit(check, unit, expected):
    start = find_task(_tasks(), START)
    assert start["ansible.builtin.systemd_service"] == {
        "name": "zcrypto-hc.service",
        "daemon_reload": True,
        "enabled": True,
        "state": "started",
    }
    variables = {"ansible_check_mode": check, find_task(_tasks(), UNIT_RENDER)["register"]: unit}
    assert truthy(when_conditions(start), variables) is expected


@pytest.mark.parametrize(
    ("check", "unit_changed", "active_before", "expected"),
    [
        (True, True, None, False),
        (True, False, "active", True),
        (False, True, "inactive", False),
        (False, False, "active", True),
        (False, False, "inactive", False),
    ],
    ids=[
        "first-install preview",
        "preview of an edit",
        "first install",
        "edit on a running node",
        "a stopped node this run started",
    ],
)
def test_the_restart_stands_down_on_a_first_install_preview_and_after_a_start_this_converge_made(
    check, unit_changed, active_before, expected
):
    handler = _handlers()["restart hc service"]
    assert handler["ansible.builtin.systemd_service"] == {"name": "zcrypto-hc.service", "daemon_reload": True, "state": "restarted"}
    start = (
        {"changed": False, "skipped": True}
        if active_before is None
        else {"changed": True, "status": {"ActiveState": active_before}}
    )
    variables = {
        "ansible_check_mode": check,
        find_task(_tasks(), UNIT_RENDER)["register"]: {"changed": unit_changed},
        find_task(_tasks(), START)["register"]: start,
    }
    assert truthy(when_conditions(handler), variables) is expected


def _shared(module: str) -> tuple[str, object]:
    (entry,) = [entry for entry in ALLOY_APT_VERBATIM if entry[0] == module]
    return entry


def test_alloy_is_installed_held_and_pinned_by_the_shared_role_alone_and_its_unit_skips_the_preview_that_has_none():
    entries = [module_entry(task) for task, _, _ in alloy_version.role_leaves("hc", frozenset())]
    packages = [entry for entry in entries if entry[0] in ("ansible.builtin.apt", "ansible.builtin.dpkg_selections")]
    rsync = module_entry(find_task(_tasks(), RSYNC))
    assert packages == [rsync, _shared("ansible.builtin.apt"), _shared("ansible.builtin.dpkg_selections")], packages
    pins = [entry for entry in entries if "/etc/apt/preferences.d/" in str(entry[1])]
    assert pins == [_shared("ansible.builtin.copy")], pins
    alloy = find_task(_tasks(), "alloy enabled + started")
    assert alloy["ansible.builtin.systemd_service"] == {"name": "alloy", "enabled": True, "state": "started"}
    assert when_conditions(alloy) == ["not alloy_apt_previewed"]
    restart = _handlers()["restart alloy"]
    assert restart["ansible.builtin.systemd_service"] == {"name": "alloy", "state": "restarted"}
    assert when_conditions(restart) == ["not alloy_apt_previewed"]


# --- the superuser --------------------------------------------------------------------------------------------------
ADMIN_INCLUDE = "the superuser, created or reset from the vault"
HEALTH_WAIT = "wait for the image's own health check to read healthy"
ADMIN_PROBE = "probe — whether the superuser exists with the vaulted password"
ADMIN_WRITE = "create the superuser, or set its password to the vaulted one"
VERDICTS = ["absent", "ok", "drifted"]


def _admin(name: str) -> dict:
    return find_task(load_tasks(ADMIN), name)


def _program(task: dict) -> ast.Module:
    argv = task["ansible.builtin.command"]["argv"]
    assert argv[-2] == "-c" and "\n" not in argv[-1], argv
    return ast.parse(argv[-1])


def test_the_superuser_is_left_alone_by_a_preview():
    include = find_task(_tasks(), ADMIN_INCLUDE)
    assert include["ansible.builtin.include_tasks"] == "admin.yml"
    assert when_conditions(include) == ["not ansible_check_mode"]


def test_the_superuser_waits_first_for_the_images_own_health_check():
    first = load_tasks(ADMIN)[0]
    assert first["name"] == HEALTH_WAIT
    command = role_render.resolve(ROLE, first["ansible.builtin.command"], {})
    assert command == "docker inspect zcrypto-hc --format '{{.State.Health.Status}}'"
    assert (first["retries"], first["delay"], first["changed_when"]) == (60, 5, False)
    for status, done in (("healthy", True), ("starting", False), ("unhealthy", False), ("", False)):
        assert truthy(first["until"], {first["register"]: {"stdout": status}}) is done, status


@pytest.mark.parametrize("name", [ADMIN_PROBE, ADMIN_WRITE])
def test_the_superusers_two_values_travel_on_stdin_and_nowhere_else(name):
    task = _admin(name)
    assert task["no_log"] is True
    assert not {"environment"} & task.keys(), "Ansible prepends environment: to the remote command, where sudo logs it"
    command = task["ansible.builtin.command"]
    assert re.findall(r"\{\{\s*(\w+)\s*\}\}", command["stdin"]) == ["hc_admin_email", "hc_admin_password"]
    assert role_render.resolve(ROLE, command["stdin"], {}, hc_admin_email="e", hc_admin_password="p") == "e\np"
    argv = command["argv"]
    assert argv[: argv.index("-c")] == [
        "docker",
        "compose",
        "-f",
        "{{ hc_compose_dir }}/compose.yaml",
        "exec",
        "-T",
        "web",
        "./manage.py",
        "shell",
        "--no-imports",
    ]
    assert {found for arg in argv for found in re.findall(r"\{\{\s*(\w+)", arg)} == {"hc_compose_dir"}, (
        "a value on the command line"
    )


@pytest.mark.parametrize(("name", "literals"), [(ADMIN_PROBE, set(VERDICTS)), (ADMIN_WRITE, set())])
def test_each_program_reads_its_values_from_stdin_imports_user_itself_and_carries_no_literal(name, literals):
    tree = _program(_admin(name))
    reads = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and ast.unparse(node) == "sys.stdin.read"]
    assert len(reads) == 1
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert [(node.module, [alias.name for alias in node.names]) for node in imports] == [("django.contrib.auth.models", ["User"])]
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert strings == literals


@pytest.mark.parametrize(
    ("stdout", "rc", "fails"),
    [
        ("absent", 0, False),
        ("ok", 0, False),
        ("drifted", 0, False),
        ("6 objects imported automatically (use -v 2 for details).\n\nabsent", 0, True),
        ("", 0, True),
        ("ok", 1, True),
    ],
)
def test_the_probe_admits_its_one_word_and_nothing_else(stdout, rc, fails):
    task = _admin(ADMIN_PROBE)
    assert task["changed_when"] is False
    assert truthy(task["failed_when"], {task["register"]: {"stdout": stdout, "rc": rc}}) is fails


@pytest.mark.parametrize(("verdict", "writes"), [("absent", True), ("drifted", True), ("ok", False)])
def test_the_write_runs_on_a_missing_user_or_a_drifted_password_and_reports_changed(verdict, writes):
    probe, write = _admin(ADMIN_PROBE), _admin(ADMIN_WRITE)
    assert truthy(when_conditions(write), {probe["register"]: {"stdout": verdict}}) is writes
    assert write["changed_when"] is True
    calls = {
        node.func.attr for node in ast.walk(_program(write)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert {"create_superuser", "set_password", "save"} <= calls
    assert "check_password" in {
        node.func.attr for node in ast.walk(_program(probe)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


# --- the node's Alloy -----------------------------------------------------------------------------------------------
ALLOY_ENV = "alloy env — the observability node's two ingest URLs and the fleet credential"
ALLOY_CONFIG = "alloy config — the node's metrics, its units' journals and the container's records, to the observability node"


def _alloy_blocks() -> dict[str, list]:
    lines = [line for line in ALLOY.read_text().splitlines() if not line.strip().startswith("//")]
    return dict(role_render.blocks(lines))


def _assigned(block: list, key: str) -> str:
    (value,) = [line.split("=", 1)[1].strip() for line, _ in block if line.split("=")[0].strip() == key]
    return value


def test_the_alloy_env_render_is_never_logged_or_diffed_and_both_renders_restart_alloy():
    env = find_task(_tasks(), ALLOY_ENV)
    assert (
        env["ansible.builtin.template"]["src"] == "alloy-env.j2" and env["ansible.builtin.template"]["dest"] == "/etc/default/alloy"
    )
    assert env["no_log"] is True and env["diff"] is False, "a preview's diff would print the fleet credential"
    config = find_task(_tasks(), ALLOY_CONFIG)
    assert config["ansible.builtin.copy"]["validate"] == "alloy validate %s"
    assert (env["notify"], config["notify"]) == ("restart alloy", "restart alloy")


def test_the_node_labels_every_series_and_stream_with_its_own_name():
    blocks = _alloy_blocks()
    assert dict(blocks['prometheus.remote_write "mon"'])["external_labels ="] == [('host = "zcrypto-hc",', [])]
    relabel = blocks['loki.relabel "journal_units"']
    assert [('target_label = "host"', []), ('replacement  = "zcrypto-hc"', [])] in [
        rule for line, rule in relabel if line == "rule"
    ]


def test_each_plane_has_one_endpoint_reading_the_three_names_of_its_plane():
    blocks = _alloy_blocks()
    assert [name for name in blocks if name.startswith(("prometheus.remote_write ", "loki.write "))] == [
        'prometheus.remote_write "mon"',
        'loki.write "mon"',
    ]
    for name, plane in (('prometheus.remote_write "mon"', "PROM"), ('loki.write "mon"', "LOKI")):
        (endpoint,) = [children for line, children in blocks[name] if line == "endpoint"]
        assert _assigned(endpoint, "url") == f'sys.env("MON_{plane}_URL")'
        (auth,) = [children for line, children in endpoint if line == "basic_auth"]
        assert (_assigned(auth, "username"), _assigned(auth, "password")) == (
            f'sys.env("MON_{plane}_USERNAME")',
            f'sys.env("MON_{plane}_PASSWORD")',
        )


def _keep_regex() -> str:
    relabel = _alloy_blocks()['loki.relabel "journal_units"']
    (keep,) = [rule for line, rule in relabel if line == "rule" and ('action        = "keep"', []) in rule]
    assert _alloy_string(_assigned(keep, "separator").strip('"')) == ";"
    return _alloy_string(_assigned(keep, "regex").strip('"'))


def test_the_journal_keeps_the_four_units_and_the_container_by_name_and_neither_caddy_nor_the_unit_that_copies_it():
    regex = _keep_regex()
    selfcheck = _include("the self-check")["vars"]["node_common_selfcheck_name"]
    for unit in ("alloy", selfcheck, "zcrypto-sqlite-backup", "zcrypto-reboot-check"):
        assert re.fullmatch(regex, f"{unit}.service;"), unit
    assert re.fullmatch(regex, "docker.service;zcrypto-hc"), "the container's own stream"
    for refused in ("caddy.service;", "zcrypto-hc.service;", "docker.service;", "docker.service;zcrypto-hc-other"):
        assert not re.fullmatch(regex, refused), refused


def test_the_container_stream_is_relabelled_hc_after_the_unit_rule():
    relabel = _alloy_blocks()['loki.relabel "journal_units"']
    rules = [dict(line.split("=", 1) for line, _ in rule) for line, rule in relabel if line == "rule"]
    rules = [{k.strip(): v.strip() for k, v in rule.items()} for rule in rules]
    by_container = [r for r in rules if r.get("source_labels") == '["__journal_container_name"]']
    assert by_container == [
        {
            "source_labels": '["__journal_container_name"]',
            "regex": '"zcrypto-hc"',
            "target_label": '"container"',
            "replacement": '"hc"',
        }
    ]
    by_unit = [i for i, r in enumerate(rules) if r.get("source_labels") == '["__journal__systemd_unit"]']
    assert by_unit and by_unit[0] < rules.index(by_container[0]), "the unit rule would overwrite the container's label"


def test_the_containers_match_replaces_the_ping_path_then_parses_json_then_lifts_level():
    stages = _stage_blocks(_hc_match())
    assert [stage.split("{", 1)[0].strip() for stage in stages] == ["stage.replace", "stage.json", "stage.labels"]
    assert re.search(r'^\s*values\s*=\s*\{\s*level\s*=\s*"level"\s*\}\s*$', stages[2], re.M), stages[2]


def test_the_reboot_check_writes_into_the_directory_the_nodes_alloy_reads():
    include = _include("the reboot check")
    node = role_render.variables(ROLE, {})
    unit = role_render.render(NODE_COMMON, "zcrypto-reboot-check.service.j2", {}, **node, **role_render.trusted(include["vars"]))
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    written = str(Path(exec_start.split()[-1]).parent)
    unix = _alloy_blocks()['prometheus.exporter.unix "host"']
    assert "textfile" in json.loads(_assigned(unix, "set_collectors"))
    assert dict(unix)["textfile"] == [(f'directory = "{written}"', [])]
    assert written == DEFAULTS["hc_textfile_dir"]


# --- the NAS's pull of the backups ---------------------------------------------------------------------------------
RSYNC = "install rsync, which ships /usr/bin/rrsync, the forced command of the NAS's backup pull"
RRSYNC_SHELL = "install the rrsync-only login shell for zcrypto-data"
DATA_USER = "create zcrypto-data, the account the NAS's backup pull logs in as (no password; the rrsync-only shell)"
PULL_KEY = "install the NAS's backup pull key (rrsync -ro) on zcrypto-data"
BACKUP = "the nightly backup"


def _resolved(value):
    return role_render.resolve(ROLE, value, {})


def test_the_pull_key_runs_rrsync_read_only_pinned_to_the_backup_directory():
    key = find_task(_tasks(), PULL_KEY)["ansible.posix.authorized_key"]
    assert _resolved(key["key_options"]) == f'command="/usr/bin/rrsync -ro {DEFAULTS["hc_backup_dir"]}",restrict'
    assert (key["key"], key["exclusive"]) == ("{{ hc_sync_backup_authorized_key }}", False)
    host_vars = yaml.safe_load((ANSIBLE / "host_vars/zcrypto-hc/vars.yml").read_text())
    assert host_vars["hc_sync_backup_authorized_key"] == "{{ lookup('file', playbook_dir ~ '/files/sync_hc_backup_ed25519.pub') }}"
    assert (ANSIBLE / "files/sync_hc_backup_ed25519.pub").read_text().startswith("ssh-ed25519 ")


def test_the_pull_keys_user_is_created_before_it_with_the_wrapper_the_role_installs_as_its_shell():
    tasks = _tasks()
    shell = find_task(tasks, RRSYNC_SHELL)["ansible.builtin.copy"]
    creation = find_task(tasks, DATA_USER)
    user = creation["ansible.builtin.user"]
    key = find_task(tasks, PULL_KEY)["ansible.posix.authorized_key"]
    assert _resolved(user["name"]) == _resolved(key["user"]) == DEFAULTS["hc_data_user"] == "zcrypto-data"
    assert _resolved(user["shell"]) == _resolved(shell["dest"]) == DEFAULTS["hc_rrsync_shell"]
    assert shell["src"] == "{{ playbook_dir }}/files/rrsync-shell" and (ANSIBLE / "files/rrsync-shell").is_file()
    assert (shell["owner"], shell["mode"]) == ("root", "0755")
    assert (user["system"], user["create_home"], "password" in user) == (True, True, False)
    assert creation["register"] == "hc_data_user_install"
    rsync = find_task(tasks, RSYNC)["ansible.builtin.apt"]
    assert (rsync["name"], rsync["state"]) == ("rsync", "present")
    order = [task_index(tasks, name) for name in (RSYNC, RRSYNC_SHELL, DATA_USER, PULL_KEY, BACKUP)]
    assert order == sorted(order), [task["name"] for task in tasks]


def test_the_backup_hands_its_files_to_the_pull_users_group():
    group = find_task(_tasks(), BACKUP)["vars"]["node_common_sqlite_backup_group"]
    assert _resolved(group) == _resolved(find_task(_tasks(), DATA_USER)["ansible.builtin.user"]["name"])


def test_the_hardening_role_leaves_the_pull_users_shell_alone():
    ignored = yaml.safe_load((ANSIBLE / "group_vars/hc_host/vars.yml").read_text())["os_ignore_users"]
    # config-selector-ok: the parsed YAML list, so `in` is membership of a name, not a substring of the file
    assert DEFAULTS["hc_data_user"] in ignored


# --- the fleet's ping URLs: one vaulted project key, one base, each check's slug ----------------------------------
OBSERVED_VARS = ANSIBLE / "group_vars/observed/vars.yml"
FIXTURE = REPO / "tests/fixtures/healthchecks_descriptions.json"
# Shaped like the minted key; not a credential.
DUMMY_PING_KEY = "aB3_-" * 4 + "x9"
OPS_CHECKS = ("liquidations", "verify_replay", "verified_replay", "archive_pull", "panel", "grafana_watchdog")
SLUGS = {
    ("group_vars/capture_host/vars.yml", "capture_healthcheck_url"): "zcrypto-capture",
    ("host_vars/zcrypto-red/vars.yml", "capture_healthcheck_url"): "zcrypto-capture-red",
    ("group_vars/engine_host/vars.yml", "engine_healthcheck_url"): "zcrypto-engine-shadow",
    ("host_vars/nas/vars.yml", "nas_gate_healthcheck_url"): "zcrypto-gate-verify",
    ("host_vars/zcrypto-mon/vars.yml", "mon_selfcheck_healthcheck_url"): "zcrypto-mon",
    ("host_vars/zcrypto-hc/vars.yml", "hc_selfcheck_healthcheck_url"): "zcrypto-hc",
    **{("host_vars/zcrypto-ops/vars.yml", f"ops_{x}_healthcheck_url"): "zcrypto-" + x.replace("_", "-") for x in OPS_CHECKS},
}
# A row a rollback in the sitting points back at its healthchecks.io value: (file, variable) -> the name its vars line
# reads, e.g. "hcio_capture_healthcheck_url". The row's slug stays in the set.
ROLLED_BACK: dict[tuple[str, str], str] = {}


def _var_files(name: str) -> list[Path]:
    return sorted([*ANSIBLE.glob(f"group_vars/*/{name}"), *ANSIBLE.glob(f"host_vars/*/{name}")])


def _ping_url_vars() -> dict[tuple[str, str], str]:
    found = {}
    for path in _var_files("vars.yml"):
        for key, value in (yaml.safe_load(path.read_text()) or {}).items():
            if key.endswith("_healthcheck_url"):
                found[(str(path.relative_to(ANSIBLE)), key)] = value
    return found


def _vault_keys(path: Path) -> set[str]:
    # Key lines alone: a value line is indented ciphertext and is never read into a message.
    return set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*):", path.read_text(), re.M))


def _vaulted() -> set[str]:
    return set().union(*(_vault_keys(path) for path in _var_files("vault.yml")))


def _assert_rolled_back(value: str, name: str) -> None:
    assert value == "{{ " + name + " }}"
    assert name in _vaulted(), f"{name} is no vault key: the rolled-back line would render undefined at the converge"


def _clone_shape() -> str:
    (entry,) = [
        e for e in _include(PLAIN_PREFLIGHT)["vars"]["node_common_secrets_preflight"] if e["key"] == "hc_selfcheck_healthcheck_url"
    ]
    return entry["shape"]


def test_the_mon_roles_ping_url_shape_is_this_roles():
    mon = find_task(load_tasks(ANSIBLE / "roles/mon/tasks/main.yml"), "the self-check's ping URL, refused by shape")
    (entry,) = mon["vars"]["node_common_secrets_preflight"]
    assert (entry["key"], entry["shape"]) == ("mon_selfcheck_healthcheck_url", _clone_shape())


def test_a_rolled_back_row_names_a_vaulted_key_and_its_line_reads_it():
    _assert_rolled_back("{{ hcio_capture_healthcheck_url }}", "hcio_capture_healthcheck_url")
    with pytest.raises(AssertionError, match="no vault key"):
        _assert_rolled_back("{{ hcio_capture_healthcheck_uri }}", "hcio_capture_healthcheck_uri")
    with pytest.raises(AssertionError):
        _assert_rolled_back("{{ hc_ping_base }}/zcrypto-capture", "hcio_capture_healthcheck_url")


def test_the_ping_url_variables_are_the_twelve_rows_and_their_slugs_the_fixtures_names_with_zcrypto_hc():
    assert set(_ping_url_vars()) == set(SLUGS)
    names = {check["name"] for check in json.loads(FIXTURE.read_text())}
    assert set(SLUGS.values()) == names | {"zcrypto-hc"}
    assert len(set(SLUGS.values())) == len(SLUGS) == 12


@pytest.mark.parametrize("row", sorted(SLUGS), ids=lambda row: f"{row[0]}:{row[1]}")
def test_each_ping_url_renders_from_the_project_key_to_its_own_checks_slug(row):
    value = _ping_url_vars()[row]
    if row in ROLLED_BACK:
        _assert_rolled_back(value, ROLLED_BACK[row])
        return
    observed = role_render.trusted(yaml.safe_load(OBSERVED_VARS.read_text()))
    rendered = Templar(loader=DataLoader(), variables={**observed, "hc_ping_key": DUMMY_PING_KEY}).template(
        trust_as_template(value)
    )
    assert re.match(_clone_shape(), rendered), f"{row}: off the clone's shape"
    assert rendered.rsplit("/", 1)[1] == SLUGS[row]
    assert rendered.startswith(f"https://{DEFAULTS['hc_hostname']}/ping/{DUMMY_PING_KEY}/")


def test_no_ping_url_name_is_a_key_of_both_a_vars_file_and_a_vault_file():
    # A directory's vault.yml loads after its vars.yml and wins, so a shared name would render the vaulted value.
    shadowed = sorted({key for _, key in _ping_url_vars()} & _vaulted())
    assert shadowed == [], f"vaulted under the name a vars file renders: {shadowed}"


def test_the_pingers_hostname_is_the_roles_own():
    assert yaml.safe_load(OBSERVED_VARS.read_text())["hc_hostname"] == DEFAULTS["hc_hostname"]


PING_NAMES = re.compile(r"\b\w+_healthcheck_url\b|\bnode_common_selfcheck_env_value\b|\bhc_ping_base\b|\bhc_ping_key\b")
PING_RENDERS = {
    ("capture", "render the capture compose file"),
    ("engine", "render the engine secrets env file (0600 root-only; never logged, never diffed)"),
    ("nas", "render the stack .env (image pins, pull sources, the vaulted gate dead-man URL)"),
    ("ops", "render the ops compose file (liquidations poller)"),
    ("ops", "install the archive-pull runner script"),
    ("ops", "install the replay + panel + tape-bars runner scripts"),
    ("ops", "install the grafana-watchdog runner script"),
    ("node_common", "render the self-check's ping URL, read by systemd alone"),
}
PAIR_LIST_PROBES = {
    ("capture", "probe — this host's own deployed pair list (does this converge ADD a pair?)"),
    ("capture", "probe — the primary's deployed pair list (pair-add order; fail-CLOSED on unreachable, a new pair is the hazard)"),
}


def _role_tasks() -> list[tuple[Path, dict, dict]]:
    out = []
    for path in sorted((ANSIBLE / "roles").glob("*/tasks/*.yml")):
        role_dir = path.parents[1]
        variables = role_render.variables(role_dir, {}) if (role_dir / "defaults/main.yml").exists() else {}
        out.extend((role_dir, task, variables) for task, _ in iter_tasks(load_tasks(path) or []))
    return out


def _templated(value, variables: dict):
    try:
        return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(value))
    except Exception:
        return value


def _expanded(task: dict, field: str, module: dict, variables: dict) -> set[str]:
    loop = task.get("loop", [None])
    items = _templated(loop, variables) if isinstance(loop, str) else loop
    return {_templated(module[field], variables | {"item": item}) for item in items}


def _ping_renders() -> list[tuple[str, dict, set[str]]]:
    found = []
    for role_dir, task, variables in _role_tasks():
        module = task.get("ansible.builtin.template")
        if module is None:
            continue
        sources = _expanded(task, "src", module, variables)
        if any(PING_NAMES.search((role_dir / "templates" / src).read_text()) for src in sources):
            found.append((role_dir.name, task, _expanded(task, "dest", module, variables)))
    return found


def test_every_render_that_carries_a_ping_url_is_never_logged_never_diffed_and_read_by_its_owner_alone():
    renders = _ping_renders()
    assert {(role, task["name"]) for role, task, _ in renders} == PING_RENDERS
    for role, task, _ in renders:
        mode = int(task["ansible.builtin.template"]["mode"], 8)
        assert (task.get("no_log"), task.get("diff"), mode & 0o077) == (True, False, 0), (role, task["name"])


def test_every_slurp_of_a_rendered_ping_url_is_never_logged():
    dests = set().union(*(dest for _, _, dest in _ping_renders()))
    slurps = [
        (role_dir.name, task)
        for role_dir, task, variables in _role_tasks()
        if "ansible.builtin.slurp" in task and _templated(task["ansible.builtin.slurp"]["src"], variables) in dests
    ]
    assert {(role, task["name"]) for role, task in slurps} == PAIR_LIST_PROBES
    for role, task in slurps:
        assert task.get("no_log") is True, (role, task["name"])
