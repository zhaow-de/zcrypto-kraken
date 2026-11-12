"""The cache proxy's rendered config and the fleet's plumbing for it."""

import re
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
TEMPLATE = ANSIBLE / "roles/engine/templates/haproxy.cfg.j2"
ENGINE_DEFAULTS = yaml.safe_load((ANSIBLE / "roles/engine/defaults/main.yml").read_text())
CACHE_DEFAULTS = yaml.safe_load((ANSIBLE / "roles/cache/defaults/main.yml").read_text())
LINK_DEFAULTS = yaml.safe_load((ANSIBLE / "roles/cache_link/defaults/main.yml").read_text())
REQUIREPASS = "Sentinel12345"
FLEET = {1: "10.98.0.11", 2: "10.98.0.12", 3: "10.98.0.13"}
_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)


def _render() -> str:
    context = {
        "engine_cache_proxy_nodes": ENGINE_DEFAULTS["engine_cache_proxy_nodes"],
        "engine_cache_proxy_master_name": ENGINE_DEFAULTS["engine_cache_proxy_master_name"],
        "cache_sentinel_requirepass": REQUIREPASS,
    }
    return _ENV.from_string(TEMPLATE.read_text()).render(**context)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _ms(value: str) -> int:
    return int(value.removesuffix("ms")) if value.endswith("ms") else int(value.removesuffix("s")) * 1000


def test_the_engine_defaults_name_the_cache_roles_nodes_and_master():
    nodes = ENGINE_DEFAULTS["engine_cache_proxy_nodes"]
    peers = [p["address"] for p in LINK_DEFAULTS["cache_link_peers"] if p["name"].startswith("zcrypto-valkey")]
    assert [n["address"] for n in nodes] == peers == ["10.98.0.11", "10.98.0.12", "10.98.0.13"]
    assert [n["name"] for n in nodes] == ["node1", "node2", "node3"]
    assert ENGINE_DEFAULTS["engine_cache_proxy_master_name"] == CACHE_DEFAULTS["cache_master_name"] == "zcache"
    assert ENGINE_DEFAULTS["engine_cache_proxy_image"] == "haproxy"
    assert ENGINE_DEFAULTS["engine_cache_proxy_image_digest"] == "{{ cache_proxy_image_digest | default('') }}"
    assert ENGINE_DEFAULTS["engine_cache_proxy_memory_limit"] == "32m"


def test_a_new_session_routes_only_on_two_votes_and_an_up_route():
    rules = [f"use_backend node{n} if {{ nbsrv(votes-node{n}) ge 2 }} {{ nbsrv(node{n}) ge 1 }}" for n in (1, 2, 3)]
    assert _sections(_render())["frontend cache"] == ["bind 0.0.0.0:6379", "option tcplog", *rules]
    assert not [ln for ln in _lines(_render()) if ln.startswith("default_backend")]


def test_each_node_has_one_vote_per_sentinel_and_no_vote_cuts_a_session():
    sections = _sections(_render())
    assert [s for s in sections if s.startswith("backend ")] == [
        f"backend {kind}node{n}" for n in (1, 2, 3) for kind in ("votes-", "")
    ]
    for n in (1, 2, 3):
        servers = [ln for ln in sections[f"backend votes-node{n}"] if ln.startswith("server ")]
        assert servers == [
            f"server via-node{s} {FLEET[s]}:26379 check inter 2s fastinter 1s downinter 1s fall 2 rise 2 init-state fully-down"
            for s in (1, 2, 3)
        ]


def test_a_votes_connect_budget_holds_a_retransmitted_syn():
    sections = _sections(_render())
    (connect,) = [_ms(ln.split()[2]) for ln in sections["defaults"] if ln.startswith("timeout connect ")]
    vias = [
        ln.split()
        for name, lines in sections.items()
        if name.startswith("backend votes-")
        for ln in lines
        if ln.startswith("server ")
    ]
    assert len(vias) == 9
    for words in vias:
        assert min(connect, _ms(words[words.index("inter") + 1])) >= 2000, words
        assert _ms(words[words.index("downinter") + 1]) <= 1000, words


def test_each_node_has_one_route_server_checked_against_the_quorum_frontend():
    sections = _sections(_render())
    (port,) = [ln.rsplit(":", 1)[1] for ln in sections["frontend quorum"] if ln.startswith("bind ")]
    for n in (1, 2, 3):
        route = sections[f"backend node{n}"]
        assert route == [
            f"option httpchk GET /node{n}",
            "http-check expect status 200",
            f"server valkey {FLEET[n]}:6379 check addr 127.0.0.1 port 9105 inter 250ms fall 2 rise 1 init-state fully-down on-marked-down shutdown-sessions",
        ]
        words = route[2].split()
        assert words[words.index("port") + 1] == port


def test_only_the_route_servers_cut_sessions():
    cutters = [ln for ln in _lines(_render()) if any(word == "shutdown-sessions" for word in ln.split())]
    assert len(cutters) == 3 and all(ln.startswith("server valkey ") for ln in cutters), cutters


def test_the_quorum_frontend_answers_503_only_on_a_contradiction():
    assert _sections(_render())["frontend quorum"] == [
        "mode http",
        "bind 127.0.0.1:9105",
        "no log",
        "http-request return status 503 if { path /node1 } { nbsrv(votes-node1) eq 0 }",
        "http-request return status 503 if { path /node1 } { nbsrv(votes-node2) ge 2 }",
        "http-request return status 503 if { path /node1 } { nbsrv(votes-node3) ge 2 }",
        "http-request return status 200 if { path /node1 }",
        "http-request return status 503 if { path /node2 } { nbsrv(votes-node2) eq 0 }",
        "http-request return status 503 if { path /node2 } { nbsrv(votes-node1) ge 2 }",
        "http-request return status 503 if { path /node2 } { nbsrv(votes-node3) ge 2 }",
        "http-request return status 200 if { path /node2 }",
        "http-request return status 503 if { path /node3 } { nbsrv(votes-node3) eq 0 }",
        "http-request return status 503 if { path /node3 } { nbsrv(votes-node1) ge 2 }",
        "http-request return status 503 if { path /node3 } { nbsrv(votes-node2) ge 2 }",
        "http-request return status 200 if { path /node3 }",
        "http-request return status 404",
    ]


def test_the_check_authenticates_pings_and_expects_the_anchored_master_reply_with_no_quit():
    text = _render()
    lines = _lines(text)
    assert lines.count(f'tcp-check send "AUTH {REQUIREPASS}\\r\\n"') == 3
    assert lines.count("tcp-check expect string +OK") == 3 and lines.count("tcp-check expect string +PONG") == 3
    assert lines.count('tcp-check send "SENTINEL master zcache\\r\\n"') == 3
    for address in ("10.98.0.11", "10.98.0.12", "10.98.0.13"):
        assert f'tcp-check expect string "\\$2\\r\\nip\\r\\n\\$10\\r\\n{address}\\r\\n"' in lines
    assert "QUIT" not in text
    # An unescaped `$` inside a double-quoted argument is an environment variable to haproxy -c.
    assert not re.search(r'"[^"]*(?<!\\)\$[^"]*"', text), "an unescaped $ inside a quoted argument"


def test_the_timeouts_the_logging_and_the_metrics_endpoint():
    lines = _lines(_render())
    assert "timeout check 2s" in lines and "timeout connect 2s" in lines
    assert "maxconn 256" in lines
    assert "timeout client 24d" in lines and "timeout server 24d" in lines
    assert "log stdout format raw local0 info" in lines
    assert "user haproxy" in lines and "group haproxy" in lines
    assert "bind 0.0.0.0:9104" in lines and "http-request use-service prometheus-exporter if { path /metrics }" in lines
    assert "bind 0.0.0.0:6379" in lines


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: list[str] = []
    for line in _lines(text):
        if line.split()[0] in ("global", "defaults", "frontend", "backend"):
            current = out.setdefault(line, [])
        else:
            current.append(line)
    return out


def test_haproxy_chroots_and_logs_connections_on_the_cache_frontend_alone():
    sections = _sections(_render())
    assert "chroot /var/lib/haproxy" in sections["global"] and "user haproxy" in sections["global"]
    assert [name for name, lines in sections.items() if "option tcplog" in lines] == ["frontend cache"]
    assert "no log" in sections["frontend metrics"]
    assert "no log" in sections["frontend quorum"]
    stateful = [ln for ln in _lines(_render()) if ln.split()[:2] == ["stats", "socket"]]
    stateful += [ln for ln in _lines(_render()) if ln.split()[0] in ("server-state-file", "load-server-state-from-file")]
    assert not stateful


def test_converge_sh_admits_the_proxy_digest_as_an_extra_var():
    text = (ANSIBLE / "scripts/converge.sh").read_text()
    evkeys = re.search(r'^EVKEYS="([^"]*)"', text, re.M | re.S).group(1).replace("\\\n", " ").split()
    assert "cache_proxy_image_digest" in evkeys


def test_the_engine_env_file_carries_the_cache_password_under_the_no_log_render():
    env = (ANSIBLE / "roles/engine/templates/engine.env.j2").read_text().splitlines()
    assert [ln for ln in env if ln.startswith("ZCRYPTO_CACHE_PASSWORD=")] == ["ZCRYPTO_CACHE_PASSWORD={{ cache_engine_password }}"]
    tasks = yaml.safe_load((ANSIBLE / "roles/engine/tasks/main.yml").read_text())
    render = next(t for t in tasks if t.get("name", "").startswith("render the engine secrets env file"))
    assert render["no_log"] is True and render["diff"] is False and render["ansible.builtin.template"]["mode"] == "0600"


def test_the_two_secrets_the_engine_host_renders_live_in_the_all_groups_vault():
    """Names only, never values: the engine play reads group_vars/all, not the cache group's file."""
    all_keys = re.findall(r"^([a-z_]+): !vault \|", (ANSIBLE / "group_vars/all/vault.yml").read_text(), re.M)
    cache_keys = re.findall(r"^([a-z_]+): !vault \|", (ANSIBLE / "group_vars/cache_host/vault.yml").read_text(), re.M)
    for key in ("cache_engine_password", "cache_sentinel_requirepass"):
        # config-selector-ok: the two lists are the regex's captures of each entry's own key, so membership is exact
        assert key in all_keys and key not in cache_keys, key
    for key in ("cache_replica_password", "cache_sentinel_password", "cache_exporter_password"):
        # config-selector-ok: the same two lists
        assert key in cache_keys and key not in all_keys, key
