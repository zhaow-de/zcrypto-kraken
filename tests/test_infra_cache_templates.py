"""The cache role's daemon-owned configs, rendered through Ansible's own templar over the role's defaults and each
node's host_vars: what a node starts from on its first render or a reset."""

import hashlib
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ROLE = ANSIBLE / "roles/cache"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
NODES = ("zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3")
PASSWORDS = {
    "cache_engine_password": "engine0pw",
    "cache_replica_password": "replica0pw",
    "cache_sentinel_password": "sentinel0pw",
    "cache_sentinel_requirepass": "requirepass0pw",
    "cache_exporter_password": "exporter0pw",
}


def _host_vars(host: str) -> dict:
    return yaml.safe_load((ANSIBLE / "host_vars" / host / "vars.yml").read_text())


def _render(name: str, host: str) -> str:
    # A default that templates another var is trusted, so it resolves over the node's vars the way the play resolves
    # it, and a changed default changes the render.
    defaults = {k: trust_as_template(v) if isinstance(v, str) and "{{" in v else v for k, v in DEFAULTS.items()}
    variables = {**defaults, **_host_vars(host), **PASSWORDS}
    text = (ROLE / "templates" / name).read_text()
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text))


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


@pytest.mark.parametrize("host", NODES)
def test_the_first_primary_renders_no_replicaof_and_every_other_node_replicates_from_it(host):
    replicaof = [line for line in _lines(_render("valkey.conf.j2", host)) if line.startswith("replicaof")]
    if _host_vars(host)["cache_link_address"] == DEFAULTS["cache_first_primary"]:
        assert replicaof == [], f"{host} is the first primary and must start as one: {replicaof}"
    else:
        assert replicaof == [f"replicaof {DEFAULTS['cache_first_primary']} 6379"], replicaof


def test_exactly_one_node_is_the_first_primary():
    firsts = [h for h in NODES if _host_vars(h)["cache_link_address"] == DEFAULTS["cache_first_primary"]]
    assert firsts == ["zcrypto-valkey1"], firsts


@pytest.mark.parametrize("name", ["valkey.conf.j2", "sentinel.conf.j2"])
@pytest.mark.parametrize("host", NODES)
def test_valkey_and_sentinel_bind_loopback_and_the_mesh_address_alone(host, name):
    binds = [line for line in _lines(_render(name, host)) if line.startswith("bind ")]
    assert binds == [f"bind 127.0.0.1 {_host_vars(host)['cache_link_address']}"], binds


def test_promotion_prefers_the_engine_region_over_the_remote_copy():
    priorities = {h: _host_vars(h)["cache_replica_priority"] for h in NODES}
    assert priorities == {"zcrypto-valkey1": 100, "zcrypto-valkey2": 100, "zcrypto-valkey3": 250}, priorities
    for host in NODES:
        assert f"replica-priority {priorities[host]}" in _lines(_render("valkey.conf.j2", host))


@pytest.mark.parametrize(
    "line",
    [
        "appendonly yes",
        "appendfsync always",
        "save 3600 1 300 100 60 10000",
        "maxmemory 128mb",
        "maxmemory-policy noeviction",
        "min-replicas-to-write 1",
        "min-replicas-max-lag 10",
        "protected-mode yes",
        "aclfile /etc/valkey/users.acl",
        "masteruser replica",
    ],
)
def test_valkey_refuses_writes_without_a_replica_and_never_evicts(line):
    assert line in _lines(_render("valkey.conf.j2", "zcrypto-valkey2"))


def test_sentinel_monitors_the_first_primary_at_quorum_two():
    lines = _lines(_render("sentinel.conf.j2", "zcrypto-valkey3"))
    for expected in (
        "sentinel monitor zcache 10.98.0.11 6379 2",
        "sentinel down-after-milliseconds zcache 5000",
        "sentinel failover-timeout zcache 60000",
        "sentinel parallel-syncs zcache 1",
        "sentinel resolve-hostnames no",
        "sentinel announce-ip 10.98.0.13",
        "sentinel auth-user zcache sentinel",
        f"sentinel auth-pass zcache {PASSWORDS['cache_sentinel_password']}",
        f"requirepass {PASSWORDS['cache_sentinel_requirepass']}",
    ):
        assert expected in lines, expected


def _acl() -> dict[str, list[str]]:
    lines = [line for line in _render("users.acl.j2", "zcrypto-valkey1").splitlines() if line.strip()]
    assert all(line.startswith("user ") for line in lines), f"Valkey's ACL file takes `user` lines alone: {lines}"
    return {line.split()[1]: line.split()[2:] for line in lines}


def test_the_acl_file_carries_password_hashes_and_never_a_password():
    acl = _acl()
    text = _render("users.acl.j2", "zcrypto-valkey1")
    for name, secret in PASSWORDS.items():
        assert secret not in text, f"{name} is in users.acl in the clear"
    for user, key in (
        ("engine", "cache_engine_password"),
        ("replica", "cache_replica_password"),
        ("sentinel", "cache_sentinel_password"),
        ("exporter", "cache_exporter_password"),
    ):
        assert "#" + hashlib.sha256(PASSWORDS[key].encode()).hexdigest() in acl[user], user


def test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous():
    acl = _acl()
    assert acl["default"] == ["off"], acl["default"]
    engine = acl["engine"]
    assert engine[0] == "on" and "~*" in engine and "+@all" in engine
    dangerous = engine.index("-@dangerous")
    assert engine.index("+keys") > dangerous and engine.index("+info") > dangerous, engine
    assert not {"+flushdb", "+flushall", "+@admin"} & set(engine), engine
    # the library's reads and writes: a category subtracted here is a cache the engine cannot use
    assert not {"-@keyspace", "-@read", "-@write"} & set(engine), engine


def test_the_replica_and_sentinel_users_carry_what_their_documented_acls_grant():
    acl = _acl()
    assert set(acl["replica"][2:]) == {"+psync", "+replconf", "+ping"}, acl["replica"]
    sentinel = {"&*", "+slaveof", "+replicaof", "+config|rewrite", "+client|kill", "+role", "+info", "+subscribe", "+publish"}
    assert sentinel <= set(acl["sentinel"]), acl["sentinel"]
    assert "-@all" in acl["exporter"] and "+@all" not in acl["exporter"], acl["exporter"]
