"""The observability node's role, read without a host: its templates rendered through Ansible's own templar over
the role's defaults, and its task and handler conditions evaluated the same way. What only a converge can show --
a package's first start, certificate issuance, the edge's answers -- is the node's acceptance, not this file."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests.test_infra_converge_guards import assert_that, find_task, iter_tasks, load_tasks, set_facts, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ROLE = ANSIBLE / "roles/mon"
TASKS = ROLE / "tasks/main.yml"
HANDLERS = ROLE / "handlers/main.yml"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
PUSH = REPO / "infra/scripts/grafana-push.sh"
# Shaped like what the generator writes; none is a credential.
SECRETS = {
    "mon_grafana_admin_user": "u" + "0123456789abcdef",
    "mon_grafana_admin_password": "A" * 48,
    "mon_grafana_secret_key": "B" * 48,
    "mon_ingest_fleet_password_hash": "$2b$10$" + "f" * 53,
    "mon_ingest_logship_password_hash": "$2b$10$" + "l" * 53,
}


def _variables(**extra) -> dict:
    # A default that templates another variable is trusted, so it resolves the way the play resolves it; the one
    # that looks up the controller's environment is left out, since no template here reads it.
    defaults = {
        k: trust_as_template(v) if isinstance(v, str) and "{{" in v else v for k, v in DEFAULTS.items() if k != "mon_token_cache"
    }
    return {**defaults, **SECRETS, **extra}


def _render(name: str, **extra) -> str:
    text = (ROLE / "templates" / name).read_text()
    return Templar(loader=DataLoader(), variables=_variables(**extra)).template(trust_as_template(text))


def _ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(_render("grafana.ini.j2"))
    return parser


# --- grafana.ini: the settings a public login rests on -----------------------------------------------------------
@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("server", "http_addr", "127.0.0.1"),
        ("server", "root_url", "https://zcrypto-mon.zhaow.me/"),
        ("security", "admin_user", "$__file{/etc/grafana/admin_user}"),
        ("security", "admin_password", "$__file{/etc/grafana/admin_password}"),
        ("security", "secret_key", "$__file{/etc/grafana/secret_key}"),
        ("security", "cookie_secure", "true"),
        ("security", "cookie_samesite", "strict"),
        ("security", "disable_brute_force_login_protection", "false"),
        ("auth", "disable_login_form", "false"),
        ("auth.basic", "enabled", "false"),
        ("auth.anonymous", "enabled", "false"),
        ("auth.anonymous", "hide_version", "true"),
        ("auth.proxy", "enabled", "false"),
        ("auth.jwt", "enabled", "false"),
        ("users", "allow_sign_up", "false"),
        ("users", "allow_org_create", "false"),
        ("snapshots", "enabled", "false"),
        ("snapshots", "external_enabled", "false"),
        ("public_dashboards", "enabled", "false"),
        ("plugins", "plugin_admin_enabled", "false"),
        ("plugins", "preinstall_disabled", "true"),
        ("feature_toggles", "sqlExpressions", "false"),
        ("database", "wal", "true"),
        ("unified_alerting.state_history", "backend", "loki"),
        ("unified_alerting.state_history", "loki_remote_url", "http://127.0.0.1:3100"),
        ("analytics", "reporting_enabled", "false"),
        ("analytics", "check_for_updates", "false"),
        ("analytics", "check_for_plugin_updates", "false"),
    ],
)
def test_the_ini_carries_what_the_public_login_rests_on(section, key, value):
    ini = _ini()
    assert ini.has_option(section, key), f"[{section}] {key} is not set, so Grafana's own default stands"
    assert ini.get(section, key) == value


def test_the_ini_names_the_secret_files_and_carries_none_of_their_values():
    rendered = _render("grafana.ini.j2")
    for name in ("mon_grafana_admin_user", "mon_grafana_admin_password", "mon_grafana_secret_key"):
        assert SECRETS[name] not in rendered, f"{name} is rendered into grafana.ini"
    files = find_task(load_tasks(TASKS), "grafana's admin name and two secrets, each a file read through $__file{}")
    copy = files["ansible.builtin.copy"]
    assert (copy["owner"], copy["group"], copy["mode"]) == ("root", "grafana", "0640"), copy
    assert files["no_log"] is True
    assert {(item["file"], item["value"]) for item in files["loop"]} == {
        ("admin_user", "{{ mon_grafana_admin_user }}"),
        ("admin_password", "{{ mon_grafana_admin_password }}"),
        ("secret_key", "{{ mon_grafana_secret_key }}"),
    }
    assert copy["dest"] == "/etc/grafana/{{ item.file }}"


# --- the Caddyfile: one public name, two authenticated ingest paths, two refusals --------------------------------
def _blocks(lines: list[str]) -> list[tuple[str, list]]:
    """A Caddyfile body as (line, children) pairs: a line ending in `{` opens a block its `}` closes."""
    out: list[tuple[str, list]] = []
    stack = [out]
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "}":
            stack.pop()
        elif line.endswith("{"):
            children: list = []
            stack[-1].append((line[:-1].strip(), children))
            stack.append(children)
        else:
            stack[-1].append((line, []))
    assert len(stack) == 1, "unbalanced braces"
    return out


def _caddyfile() -> dict[str, list]:
    return dict(_blocks(_render("Caddyfile.j2").splitlines()))


def _site() -> dict[str, list]:
    caddyfile = _caddyfile()
    assert set(caddyfile) == {"", DEFAULTS["mon_hostname"]}, f"one global block and one site: {sorted(caddyfile)}"
    return dict(caddyfile[DEFAULTS["mon_hostname"]])


def _users(handle: list) -> list[str]:
    (auth,) = [children for line, children in handle if line == "basic_auth"]
    for _user, children in auth:
        assert children == []
    users = [line.split() for line, _ in auth]
    for user, hashed in users:
        assert re.fullmatch(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}", hashed), f"{user} carries something that is not a bcrypt hash"
    return [user for user, _ in users]


def _upstream(handle: list) -> str:
    (proxy,) = [line for line, _ in handle if line.startswith("reverse_proxy ")]
    return proxy.split()[1]


def test_remote_write_takes_the_fleet_user_alone_and_reaches_prometheus():
    handle = _site()["handle /api/v1/write"]
    assert _users(handle) == ["fleet"]
    assert _upstream(handle) == "127.0.0.1:9090"


def test_the_loki_push_takes_both_ingest_users_and_reaches_loki():
    handle = _site()["handle /loki/api/v1/push"]
    assert _users(handle) == ["fleet", "logship"]
    assert _upstream(handle) == "127.0.0.1:3100"


def test_the_two_paths_grafana_serves_without_a_login_answer_404_at_the_edge():
    site = _site()
    matchers = {line: None for line in site if line.startswith("@")}
    assert list(matchers) == ["@served_without_a_login path /metrics /metrics/* /swagger*"], list(matchers)
    assert site["handle @served_without_a_login"] == [("respond 404", [])]


def test_everything_else_goes_to_grafana_with_no_credential_added():
    site = _site()
    assert site["handle"] == [("reverse_proxy 127.0.0.1:3000", [])]
    handles = [line for line in site if line.startswith("handle")]
    assert handles == ["handle /api/v1/write", "handle /loki/api/v1/push", "handle @served_without_a_login", "handle"], handles


def test_the_edge_listens_on_443_alone_and_takes_its_certificate_there():
    caddyfile = _caddyfile()
    assert ("auto_https disable_redirects", []) in caddyfile[""], "the redirect listener would bind port 80"
    assert dict(_site())["tls"] == [("issuer acme", [("disable_http_challenge", [])])]
    assert not re.search(r"(?m)^\s*(http://|:80\b)", _render("Caddyfile.j2"))


def test_the_caddyfile_is_validated_before_it_replaces_the_live_one_and_never_shown():
    task = find_task(
        load_tasks(TASKS), "Caddyfile — the two ingest paths behind basic auth, two refusals, everything else to grafana"
    )
    template = task["ansible.builtin.template"]
    assert template["validate"] == "caddy validate --adapter caddyfile --config %s"
    assert (template["owner"], template["group"], template["mode"]) == ("root", "caddy", "0640")
    assert task["no_log"] is True and task["diff"] is False, "the diff of a preview would print the hashes"


# --- the stores: loopback, the retention, no scrape job ----------------------------------------------------------
def test_prometheus_is_a_loopback_receiver_kept_ninety_days():
    (args,) = re.findall(r'^ARGS="(.*)"$', _render("prometheus.default.j2"), re.M)
    assert args.split() == [
        "--web.listen-address=127.0.0.1:9090",
        "--web.enable-remote-write-receiver",
        "--storage.tsdb.retention.time=90d",
        "--storage.tsdb.retention.size=16GB",
    ]
    config = yaml.safe_load(_render("prometheus.yml.j2"))
    assert config == {"storage": {"tsdb": {"out_of_order_time_window": "8h"}}}, config


def test_loki_is_a_loopback_single_binary_whose_compactor_enforces_the_same_retention():
    config = yaml.safe_load(_render("loki-config.yml.j2"))
    server = config["server"]
    assert (server["http_listen_address"], server["grpc_listen_address"]) == ("127.0.0.1", "127.0.0.1")
    assert (server["http_listen_port"], config["auth_enabled"]) == (3100, False)
    assert config["common"]["path_prefix"] == "/var/lib/loki"
    assert config["common"]["storage"]["filesystem"]["chunks_directory"] == "/var/lib/loki/chunks"
    (schema,) = config["schema_config"]["configs"]
    assert (schema["store"], schema["object_store"], schema["schema"], schema["index"]["period"]) == (
        "tsdb",
        "filesystem",
        "v13",
        "24h",
    )
    compactor = config["compactor"]
    assert compactor["retention_enabled"] is True and compactor["delete_request_store"] == "filesystem"
    assert config["limits_config"]["retention_period"] == f"{DEFAULTS['mon_retention_days'] * 24}h" == "2160h"
    assert config["analytics"]["reporting_enabled"] is False


@pytest.mark.parametrize(
    ("name", "validate"),
    [
        ("prometheus config — no scrape job, the out-of-order window", "promtool check config %s"),
        ("loki config — loopback, filesystem storage, the compactor's retention", "loki -verify-config -config.file %s"),
    ],
)
def test_a_store_config_is_validated_by_the_installed_binary_before_it_lands(name, validate):
    assert find_task(load_tasks(TASKS), name)["ansible.builtin.template"]["validate"] == validate


# --- the evaluator never starts ahead of its stores --------------------------------------------------------------
def test_grafana_starts_after_its_stores_and_waits_for_both_to_be_ready():
    unit = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    unit.optionxform = str
    dropin = _render("grafana-server.dropin.conf.j2")
    unit.read_string("\n".join(line for line in dropin.splitlines() if not line.startswith("ExecStartPre=")))
    assert unit.get("Unit", "After").split() == ["prometheus.service", "loki.service"]
    waits = [line.removeprefix("ExecStartPre=") for line in dropin.splitlines() if line.startswith("ExecStartPre=")]
    assert [wait.split()[-1] for wait in waits] == ["http://127.0.0.1:9090/-/ready", "http://127.0.0.1:3100/ready"]
    for wait in waits:
        assert wait.split()[:2] == ["/usr/bin/curl", "-fsS"] and "--retry-all-errors" in wait.split(), wait
    assert int(unit.get("Service", "OOMScoreAdjust")) < 0, "the stores keep the default of 0, and Grafana must rank below them"
    install = find_task(load_tasks(TASKS), "prometheus present, from Debian main, without the node exporter it recommends")
    assert "curl" in install["ansible.builtin.apt"]["name"], "the drop-in's wait runs a curl the role never installed"


def test_a_store_is_restarted_with_grafana_stopped_around_it():
    handlers = yaml.safe_load(HANDLERS.read_text())
    names = [handler["name"] for handler in handlers]
    order = ["stop grafana around a store restart", "restart prometheus", "restart loki", "restart grafana"]
    assert [name for name in names if name in order] == order, names
    by_name = {handler["name"]: handler for handler in handlers}
    for name, state in (("stop grafana around a store restart", "stopped"), ("restart grafana", "restarted")):
        handler = by_name[name]
        assert handler["ansible.builtin.systemd_service"] == {"name": "grafana-server", "state": state} | (
            {"daemon_reload": True} if state == "restarted" else {}
        )
        assert handler["listen"] == ["restart prometheus", "restart loki"], handler
    assert names.index("reload systemd") < names.index("restart grafana"), "the drop-in would be restarted into unread"


def test_the_stores_are_running_their_rendered_configs_before_grafana_is_started():
    tasks = load_tasks(TASKS)
    names = [task.get("name") for task in tasks]
    flush = names.index("apply the pending store and grafana restarts")
    assert tasks[flush] == {"name": names[flush], "ansible.builtin.meta": "flush_handlers"}
    assert names.index("prometheus and loki enabled + started") < flush < names.index("grafana-server enabled + started")
    rendered_before = [
        "prometheus flags — loopback, the receiver, the retention",
        "loki config — loopback, filesystem storage, the compactor's retention",
        "grafana.ini",
        "grafana's admin name and two secrets, each a file read through $__file{}",
        "the two datasources, file-provisioned read-only under the uids the rule file names",
        "the folder the push writes into, anchored under its uid",
        "grafana-server drop-in — after its stores, waiting for both to be ready",
    ]
    assert all(names.index(name) < flush for name in rendered_before)


# --- provisioning: the uids the push, the dashboards and the tools already name ----------------------------------
def _push_default(name: str) -> str:
    (value,) = re.findall(rf'^export {name}="\$\{{{name}:-([^}}]+)\}}"$', PUSH.read_text(), re.M)
    return value


def test_the_two_datasources_are_read_only_under_the_uids_the_push_defaults_to():
    provisioned = yaml.safe_load(_render("datasources.yml.j2"))
    assert provisioned["prune"] is True
    by_uid = {source["uid"]: source for source in provisioned["datasources"]}
    assert set(by_uid) == {_push_default("GRAFANA_PROM_DS_UID"), _push_default("GRAFANA_LOKI_DS_UID")}
    prom, loki = by_uid[_push_default("GRAFANA_PROM_DS_UID")], by_uid[_push_default("GRAFANA_LOKI_DS_UID")]
    assert (prom["type"], prom["url"], prom["editable"]) == ("prometheus", "http://127.0.0.1:9090", False)
    assert (loki["type"], loki["url"], loki["editable"]) == ("loki", "http://127.0.0.1:3100", False)


def test_the_folder_is_anchored_under_the_uid_the_push_defaults_to_and_nothing_is_provisioned_into_it():
    (provider,) = yaml.safe_load(_render("folder-anchor.yml.j2"))["providers"]
    assert provider["folderUid"] == _push_default("GRAFANA_ALERT_FOLDER_UID")
    assert provider["options"]["path"] == DEFAULTS["mon_folder_anchor_dir"]
    assert sorted(p.name for p in (ROLE / "templates").iterdir() if "dashboard" in p.name or "alert" in p.name) == []
    assert not (ROLE / "files").exists() or not list((ROLE / "files").glob("*.json"))


# --- packages: followed from apt, loki from Grafana's repository alone -------------------------------------------
_POLICY_GRAFANA = """loki:
  Installed: (none)
  Candidate: 3.7.8
  Version table:
     3.7.8 500
        500 https://apt.grafana.com stable/main amd64 Packages
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""
_POLICY_INSTALLED = """loki:
  Installed: 3.7.8
  Candidate: 3.7.8
  Version table:
 *** 3.7.8 500
        500 https://apt.grafana.com stable/main amd64 Packages
        100 /var/lib/dpkg/status
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""
_POLICY_DEBIAN = """loki:
  Installed: (none)
  Candidate: 2.4.7.4-12
  Version table:
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""
_POLICY_DEBIAN_PINNED = """loki:
  Installed: (none)
  Candidate: 2.4.7.4-12
  Version table:
     3.7.8 100
        100 https://apt.grafana.com stable/main amd64 Packages
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""


@pytest.mark.parametrize(
    ("policy", "admitted"),
    [(_POLICY_GRAFANA, True), (_POLICY_INSTALLED, True), (_POLICY_DEBIAN, False), (_POLICY_DEBIAN_PINNED, False), ("", False)],
    ids=["grafana's", "installed", "debian's", "debian's by priority", "no output"],
)
def test_loki_is_installed_only_when_apts_candidate_is_grafanas(policy, admitted):
    task = find_task(load_tasks(TASKS), "refuse a loki candidate that does not come from apt.grafana.com")
    variables = {**{k: trust_as_template(v) for k, v in task["vars"].items()}, "mon_loki_policy": {"stdout": policy}}
    assert truthy(assert_that(task), variables) is admitted


def test_no_package_is_forced_held_or_pinned_to_a_version():
    installs = [task["ansible.builtin.apt"] for task, _ in iter_tasks(load_tasks(TASKS)) if "ansible.builtin.apt" in task]
    names = sorted(name for task, _ in iter_tasks(load_tasks(TASKS)) for name in _apt_names(task))
    assert names == ["alloy", "caddy", "curl", "grafana", "loki", "prometheus"], names
    for apt in installs:
        assert apt.get("state", "present") == "present" and "allow_downgrade" not in apt and "force" not in apt, apt
    assert all("=" not in name for name in names)
    modules = {key for task, _ in iter_tasks(load_tasks(TASKS)) for key in task}
    assert "ansible.builtin.dpkg_selections" not in modules, "a hold makes `apt upgrade` skip a package silently"
    recommends = find_task(load_tasks(TASKS), "prometheus present, from Debian main, without the node exporter it recommends")
    assert recommends["ansible.builtin.apt"]["install_recommends"] is False


# --- the preview on a node that has nothing yet ------------------------------------------------------------------
_CHANGED, _UNCHANGED, _SKIPPED = {"changed": True}, {"changed": False}, {"changed": False, "skipped": True}


# Each disjunct of the two facts has a case in which it alone is true.
@pytest.mark.parametrize(
    ("check", "grafana_repo", "caddy_repo", "debian", "grafana", "caddy", "expected"),
    [
        (True, _CHANGED, _CHANGED, _CHANGED, _SKIPPED, _SKIPPED, (True, True)),  # a fresh node's preview
        (True, _CHANGED, _UNCHANGED, _UNCHANGED, _SKIPPED, _SKIPPED, (True, True)),  # Grafana's repository alone still to write
        (True, _UNCHANGED, _CHANGED, _UNCHANGED, _SKIPPED, _SKIPPED, (True, True)),  # Caddy's repository alone still to write
        (True, _UNCHANGED, _UNCHANGED, _CHANGED, _UNCHANGED, _UNCHANGED, (False, True)),  # prometheus alone still to install
        (True, _UNCHANGED, _UNCHANGED, _UNCHANGED, _CHANGED, _UNCHANGED, (False, True)),  # a Grafana package alone
        (True, _UNCHANGED, _UNCHANGED, _UNCHANGED, _UNCHANGED, _CHANGED, (False, True)),  # caddy alone
        (True, _UNCHANGED, _UNCHANGED, _UNCHANGED, _UNCHANGED, _UNCHANGED, (False, False)),  # an established node's preview
        (False, _CHANGED, _CHANGED, _CHANGED, _CHANGED, _CHANGED, (False, False)),  # the real first converge
    ],
)
def test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find(
    check, grafana_repo, caddy_repo, debian, grafana, caddy, expected
):
    tasks = load_tasks(TASKS)
    variables = {"ansible_check_mode": check, "mon_grafana_repo": grafana_repo, "mon_caddy_repo": caddy_repo}
    first = set_facts(find_task(tasks, "note a preview that runs before the repositories exist"), variables)
    variables |= first | {"mon_debian_install": debian, "mon_grafana_install": grafana, "mon_caddy_install": caddy}
    second = set_facts(find_task(tasks, "note a preview that runs before the packages are installed"), variables)
    assert (bool(first["mon_repos_previewed"]), bool(second["mon_units_previewed"])) == expected


def _apt_names(task: dict) -> set[str]:
    name = task.get("ansible.builtin.apt", {}).get("name", [])
    return {name} if isinstance(name, str) else set(name)


def test_what_needs_a_repository_or_a_unit_skips_the_preview_that_has_neither():
    tasks = iter_tasks(load_tasks(TASKS))
    units = [(task["name"], gates) for task, gates in tasks if "ansible.builtin.systemd_service" in task]
    assert len(units) >= 3, units
    for name, gates in units:
        # Held whole: an inverted gate names the fact too, and it would skip every real converge.
        timer = len(gates) == 1 and re.fullmatch(r"not \(ansible_check_mode and mon_[a-z_]+_timer_install is changed\)", gates[0])
        assert gates == ("not mon_units_previewed",) or timer, (name, gates)
    third_party = [gates for task, gates in tasks if _apt_names(task) & {"grafana", "loki", "alloy", "caddy"}]
    assert len(third_party) == 2 and all(gates == ("not mon_repos_previewed",) for gates in third_party), third_party
    origin = find_task(load_tasks(TASKS), "refuse a loki candidate that does not come from apt.grafana.com")
    assert when_conditions(origin) == ["not mon_repos_previewed"]
    for handler in yaml.safe_load(HANDLERS.read_text()):
        if "name" in handler.get("ansible.builtin.systemd_service", {}):
            assert when_conditions(handler) == ["not mon_units_previewed"], handler["name"]


# --- the vaulted secrets: refused by name when missing or misshapen ----------------------------------------------
@pytest.mark.parametrize(
    ("override", "refused"),
    [
        ({}, None),
        ({"mon_grafana_admin_user": "root"}, "mon_grafana_admin_user"),
        ({"mon_grafana_admin_user": "administrator"}, "mon_grafana_admin_user"),
        ({"mon_grafana_admin_password": None}, "mon_grafana_admin_password"),
        ({"mon_grafana_admin_password": "short"}, "mon_grafana_admin_password"),
        ({"mon_grafana_secret_key": "has a space in it, which a generator never writes"}, "mon_grafana_secret_key"),
        ({"mon_ingest_fleet_password_hash": "A" * 48}, "mon_ingest_fleet_password_hash"),
        (
            {"mon_ingest_logship_password_hash": SECRETS["mon_ingest_logship_password_hash"] + "\n"},
            "mon_ingest_logship_password_hash",
        ),
    ],
    ids=[
        "all five",
        "a name a stranger tries",
        "a long name a stranger tries",
        "one missing",
        "too short",
        "not letters and digits",
        "a password where a hash belongs",
        "a trailing newline",
    ],
)
def test_a_missing_or_misshapen_secret_is_refused_by_its_key(override, refused):
    task = load_tasks(TASKS)[0]
    assert task["name"] == "refuse a missing or misshapen secret, naming the key and never the value"
    values = {k: v for k, v in {**SECRETS, **override}.items() if v is not None}
    templar = Templar(loader=DataLoader(), variables=values)
    faults = templar.template(trust_as_template(task["vars"]["mon_secret_faults"]))
    assert faults == ([refused] if refused else [])
    assert truthy(assert_that(task), {"mon_secret_faults": faults}) is (refused is None)
    rendered = Templar(loader=DataLoader(), variables={"mon_secret_faults": faults}).template(
        trust_as_template(task["ansible.builtin.assert"]["fail_msg"])
    )
    assert all(str(value) not in rendered for value in values.values()), "the refusal printed a value"
    assert (refused or "") in rendered


def test_the_play_runs_the_role_under_its_own_tag_with_no_container_runtime():
    plays = load_tasks(ANSIBLE / "site.yml")
    (play,) = [p for p in plays if p["hosts"] == "mon_host"]
    assert [(role["role"], role["tags"]) for role in play["roles"]] == [
        ("base", ["base"]),
        ("hardening", ["hardening"]),
        ("firewall", ["firewall"]),
        ("fail2ban", ["fail2ban"]),
        ("chrony", ["chrony"]),
        ("mon", ["mon"]),
    ]


# --- the node's own Alloy: on loopback, with no credential and no filter -----------------------------------------
ALLOY = ROLE / "files/config.alloy"


def _alloy_blocks() -> dict[str, list]:
    lines = [line for line in ALLOY.read_text().splitlines() if not line.strip().startswith("//")]
    return dict(_blocks(lines))


def _assigned(block: list, key: str) -> str:
    (value,) = [line.split("=", 1)[1].strip() for line, _ in block if line.split("=")[0].strip() == key]
    return value


def test_the_node_ships_to_its_own_stores_on_loopback_with_no_credential_and_no_filter():
    blocks = _alloy_blocks()
    remote = blocks['prometheus.remote_write "mon"']
    endpoint = dict(remote)["endpoint"]
    assert endpoint == [(f'url = "http://127.0.0.1:{DEFAULTS["mon_prometheus_port"]}/api/v1/write"', [])], endpoint
    assert dict(remote)["external_labels ="] == [('host = "zcrypto-mon",', [])]
    assert dict(blocks['loki.write "mon"'])["endpoint"] == [
        (f'url = "http://127.0.0.1:{DEFAULTS["mon_loki_port"]}/loki/api/v1/push"', [])
    ]
    kinds = {line.split()[0] for line in blocks}
    assert not kinds & {"prometheus.relabel", "write_relabel_config"}, "the node's leg carries no keep or drop list"


def test_the_node_scrapes_its_host_itself_and_its_three_services():
    blocks = _alloy_blocks()
    unix = blocks['prometheus.exporter.unix "host"']
    assert _assigned(unix, "set_collectors") == '["cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"]'
    assert dict(unix)["textfile"] == [(f'directory = "{DEFAULTS["mon_textfile_dir"]}"', [])]
    assert 'prometheus.exporter.self "alloy"' in {line.removesuffix(" {}") for line in blocks}
    ports = {"grafana": "mon_grafana_port", "prometheus": "mon_prometheus_port", "loki": "mon_loki_port"}
    for job, port in ports.items():
        scrape = blocks[f'prometheus.scrape "{job}"']
        assert _assigned(scrape, "targets") == f'[{{"__address__" = "127.0.0.1:{DEFAULTS[port]}"}}]', job
        assert _assigned(scrape, "job_name") == f'"{job}"'
    for name, block in blocks.items():
        if name.startswith("prometheus.scrape "):
            assert _assigned(block, "forward_to") == "[prometheus.remote_write.mon.receiver]", name
            assert _assigned(block, "scrape_interval") == '"60s"', name


def test_the_journal_keep_rule_names_the_units_this_role_runs():
    relabel = _alloy_blocks()['loki.relabel "journal_units"']
    (keep,) = [rule for line, rule in relabel if line == "rule" and ('action        = "keep"', []) in rule]
    (pattern,) = re.findall(r'^"\((.*)\)\\\\\.service"$', _assigned(keep, "regex"))
    timers = {p.name.removesuffix(".timer") for p in (ROLE / "files").glob("*.timer")}
    assert set(pattern.split("|")) == {"grafana-server", "prometheus", "loki", "caddy", "alloy"} | timers
    assert ('replacement  = "zcrypto-mon"', []) in [entry for line, rule in relabel if line == "rule" for entry in rule]


def test_the_alloy_config_is_validated_and_alloy_restarted_on_a_change():
    tasks = load_tasks(TASKS)
    copy = find_task(tasks, "alloy config — the node's own metrics and journals, written to its stores on loopback")
    assert copy["ansible.builtin.copy"]["validate"] == "alloy validate %s" and copy["notify"] == "restart alloy"
    (handler,) = [h for h in yaml.safe_load(HANDLERS.read_text()) if h["name"] == "restart alloy"]
    assert handler["ansible.builtin.systemd_service"] == {"name": "alloy", "state": "restarted"}
