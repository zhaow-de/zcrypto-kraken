"""Both Jinja guard branches of every compose template RENDERED here must render valid YAML, with
the metrics port and env landing on the right service (spec 00069 D10)."""

from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

CAPTURE_TEMPLATE = REPO / "infra/ansible/roles/capture/templates/compose.yaml.j2"
ENGINE_TEMPLATE = REPO / "infra/ansible/roles/engine/templates/compose.yaml.j2"
OPS_TEMPLATE = REPO / "infra/ansible/roles/ops/templates/compose.yaml.j2"
OPS_DEFAULTS = REPO / "infra/ansible/roles/ops/defaults/main.yml"
CACHE_TEMPLATE = REPO / "infra/ansible/roles/cache/templates/compose.yaml.j2"
CACHE_DEFAULTS = yaml.safe_load((REPO / "infra/ansible/roles/cache/defaults/main.yml").read_text())

# StrictUndefined is the load-bearing setting: a variable the role sets and a test omits raises here instead of rendering empty into a pin
_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

# Dummy but complete contexts: every variable each template references (outside the
# `mon_ingest_logship_password is defined` guard), so a render under StrictUndefined only ever fails on a
# genuine template bug, never a missing fixture variable.
CAPTURE_CONTEXT = {
    "capture_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "capture_image_digest": "sha256:" + "a" * 64,
    "capture_uid": 999,
    "capture_gid": 999,
    "capture_data_dir": "/var/lib/zcrypto-capture",
    "capture_depth": 100,
    "capture_pairs": ["BTC/EUR", "ETH/EUR"],
    "capture_healthcheck_url": "",
    "base_hostname": "zcrypto",
    "capture_cpu_limit": "1.5",
    "capture_memory_limit": "2g",
    "capture_log_max_size": "50m",
    "capture_log_max_file": "5",
}

ENGINE_CONTEXT = {
    "engine_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "engine_image_digest": "sha256:" + "b" * 64,
    "engine_uid": 997,
    "engine_gid": 997,
    "engine_state_dir": "/var/lib/zcrypto-engine",
    "engine_cpu_limit": "0.75",
    "engine_memory_limit": "1g",
    "engine_cpu_shares": 512,
    "engine_log_max_size": "50m",
    "engine_log_max_file": "5",
    "engine_cache_proxy_image": "haproxy",
    "engine_cache_proxy_image_digest": "sha256:" + "c" * 64,
    "engine_cache_proxy_memory_limit": "32m",
}

OPS_CONTEXT = {
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "c" * 64,
    # read from the role default the template interpolates, never re-typed: a changed default must
    # reach this render too -- test_infra_converge_guards.py pins the probe to the same variable
    "ops_liquidations_container": yaml.safe_load(OPS_DEFAULTS.read_text())["ops_liquidations_container"],
    "ops_uid": 998,
    "ops_gid": 998,
    "ops_liquidations_healthcheck_url": "",
    "coinalyze_api_key": "dummy-key",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_compose_dir": "/etc/zcrypto-ops",
}

# The paths and caps come from the role's defaults, so the render below reads the values a converge deploys.
CACHE_CONTEXT = {
    **{
        k: CACHE_DEFAULTS[k]
        for k in ("cache_image", "cache_compose_dir", "cache_state_dir", "cache_valkey_memory_limit", "cache_sentinel_memory_limit")
    },
    "cache_image_digest": "sha256:" + "d" * 64,
    "cache_uid": 996,
    "cache_gid": 996,
}

_CASES = [
    (CAPTURE_TEMPLATE, CAPTURE_CONTEXT),
    (ENGINE_TEMPLATE, ENGINE_CONTEXT),
    (OPS_TEMPLATE, OPS_CONTEXT),
    (CACHE_TEMPLATE, CACHE_CONTEXT),
]
_IDS = ["capture", "engine", "ops", "cache"]


def _render(template_path: Path, context: dict) -> dict:
    rendered = _ENV.from_string(template_path.read_text()).render(**context)
    parsed = yaml.safe_load(rendered)
    assert parsed is not None, f"{template_path}: rendered to nothing"
    return parsed


@pytest.mark.parametrize(("template", "context"), _CASES, ids=_IDS)
def test_renders_valid_yaml_without_the_nodes_logship_password(template, context):
    # The logship guard's FALSE branch (00068 D5/D7): a converge landing before the vault carries
    # the node's logship password, or a host that never gets it.
    _render(template, context)


@pytest.mark.parametrize(("template", "context"), _CASES, ids=_IDS)
def test_renders_valid_yaml_with_the_nodes_logship_password(template, context):
    # The guard's TRUE branch. It reads only that the render parses, which either branch does: the
    # guard's name is held by test_every_logship_guard_renders_its_whole_branch_on_the_nodes_password.
    _render(template, {**context, "mon_ingest_logship_password": "x"})


def test_capture_metrics_port_and_publish_land_on_the_capture_service():
    service = _render(CAPTURE_TEMPLATE, CAPTURE_CONTEXT)["services"]["capture"]
    assert service["environment"]["ZCRYPTO_METRICS_PORT"] == "9101"
    assert "127.0.0.1:9101:9101" in service["ports"]


def test_engine_metrics_port_and_publish_land_on_the_engine_service():
    service = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["engine"]
    assert service["environment"]["ZCRYPTO_METRICS_PORT"] == "9102"
    assert "127.0.0.1:9102:9102" in service["ports"]


def test_ops_metrics_port_and_publish_land_on_the_liquidations_service():
    service = _render(OPS_TEMPLATE, OPS_CONTEXT)["services"]["liquidations"]
    assert service["environment"]["ZCRYPTO_METRICS_PORT"] == "9103"
    assert "127.0.0.1:9103:9103" in service["ports"]


def test_the_cache_proxy_service_is_pinned_by_digest_root_at_start_with_its_config_read_only_and_its_metrics_on_loopback():
    service = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["cache-proxy"]
    assert service["image"] == "haproxy@sha256:" + "c" * 64
    assert (service["container_name"], service["restart"], service["user"]) == ("zcrypto-cache-proxy", "unless-stopped", "0:0")
    assert service["volumes"] == ["/opt/zcrypto-engine/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro"]
    assert service["ports"] == ["127.0.0.1:9104:9104"]
    assert service["deploy"]["resources"]["limits"] == {"memory": "32m"}
    assert service["logging"]["driver"] == "json-file"


def test_the_engine_waits_for_the_proxy_to_start_and_stops_inside_twenty_seconds():
    service = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["engine"]
    assert service["depends_on"] == {"cache-proxy": {"condition": "service_started"}}
    assert service["stop_grace_period"] == "20s"


def test_the_engine_compose_file_carries_neither_cache_secret():
    """The passwords reach the host through engine.env and haproxy.cfg, both 0600 and never diffed;
    the compose file stays diffable, so a render handed both values must not carry either."""
    context = {**ENGINE_CONTEXT, "cache_engine_password": "EnginePw12345", "cache_sentinel_requirepass": "SentinelPw12345"}
    rendered = _ENV.from_string(ENGINE_TEMPLATE.read_text()).render(**context)
    assert "EnginePw12345" not in rendered and "SentinelPw12345" not in rendered


def test_engine_logship_guard_moves_environment_and_entrypoint_together():
    without_password = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["engine"]
    with_password = _render(ENGINE_TEMPLATE, {**ENGINE_CONTEXT, "mon_ingest_logship_password": "x"})["services"]["engine"]

    assert without_password["environment"]["ZCRYPTO_METRICS_PORT"] == "9102"
    assert "ZCRYPTO_LOG_HOST" not in without_password["environment"]
    assert without_password["entrypoint"] == ["zcrypto", "engine", "run"]

    assert with_password["environment"]["ZCRYPTO_METRICS_PORT"] == "9102"
    assert with_password["environment"]["ZCRYPTO_LOG_HOST"] == "zcrypto"
    assert with_password["entrypoint"] == ["zcrypto", "--ship-logs", "engine", "run"]


# The capture service ships through its image's own ENTRYPOINT, which reads `ZCRYPTO_SHIP_LOGS` from the logship
# file, so its true branch carries no `--ship-logs` of its own.
_LOGSHIP_GUARDS = [
    (CAPTURE_TEMPLATE, CAPTURE_CONTEXT, "capture", "/opt/zcrypto-capture/logship-secrets.env", False),
    (OPS_TEMPLATE, OPS_CONTEXT, "liquidations", "/etc/zcrypto-ops/logship-secrets.env", True),
    (ENGINE_TEMPLATE, ENGINE_CONTEXT, "engine", "/opt/zcrypto-capture/logship-secrets.env", True),
]


def _env_file_paths(service: dict) -> list[str]:
    return [e["path"] if isinstance(e, dict) else e for e in service.get("env_file", [])]


def _logship_branch(service: dict, logship_file: str) -> tuple[bool, bool, bool]:
    return (
        "ZCRYPTO_LOG_HOST" in service["environment"],
        logship_file in _env_file_paths(service),
        "--ship-logs" in service.get("entrypoint", []),
    )


@pytest.mark.parametrize(
    ("template", "context", "service", "logship_file", "ships_by_entrypoint"), _LOGSHIP_GUARDS, ids=["capture", "ops", "engine"]
)
def test_every_logship_guard_renders_its_whole_branch_on_the_nodes_password(
    template, context, service, logship_file, ships_by_entrypoint
):
    on = _render(template, {**context, "mon_ingest_logship_password": "x"})["services"][service]
    off = _render(template, context)["services"][service]
    assert _logship_branch(on, logship_file) == (True, True, ships_by_entrypoint)
    assert _logship_branch(off, logship_file) == (False, False, False)
    # Compose lets `environment:` and a later `env_file` entry outrank the logship file, so each of its names reaches
    # the push from that file alone.
    names = {line.split("=", 1)[0] for line in _LOGSHIP_LINES}
    assert not names & (set(on["environment"]) | set(off["environment"]))
    assert _env_file_paths(on)[-1] == logship_file
    if not ships_by_entrypoint:
        # An `entrypoint:` override replaces the image's, the one that adds `--ship-logs`.
        assert "entrypoint" not in on and "entrypoint" not in off


@pytest.mark.parametrize("role", ["capture", "ops"])
def test_the_logship_file_renders_on_the_nodes_password(role):
    tasks = yaml.safe_load((REPO / f"infra/ansible/roles/{role}/tasks/main.yml").read_text())
    (render,) = [t for t in tasks if t.get("name") == "render the logship secrets env file"]
    assert render["when"] == "mon_ingest_logship_password is defined"


_LOGSHIP_LINES = [
    "ZCRYPTO_LOKI_URL={{ mon_ingest_loki_url }}",
    "ZCRYPTO_LOKI_USERNAME={{ mon_ingest_logship_user }}",
    "ZCRYPTO_LOKI_PASSWORD={{ mon_ingest_logship_password }}",
    "ZCRYPTO_SHIP_LOGS=1",
]


@pytest.mark.parametrize("role", ["capture", "ops"])
def test_the_logship_files_push_to_the_nodes_loki_as_its_logship_user(role):
    text = (REPO / f"infra/ansible/roles/{role}/templates/logship-secrets.env.j2").read_text()
    assert [line for line in text.splitlines() if not line.startswith("#")] == _LOGSHIP_LINES
    assert "grafana_loki_" not in text and "logship_loki_token" not in text


def test_no_role_reads_grafana_clouds_logship_token():
    roles = REPO / "infra/ansible/roles"
    readers = sorted(str(p.relative_to(roles)) for p in roles.rglob("*") if p.is_file() and b"logship_loki_token" in p.read_bytes())
    assert readers == [], "\n".join(readers)


@pytest.mark.parametrize(
    ("service", "command", "limit"),
    [
        ("valkey", ["valkey-server", "/etc/valkey/valkey.conf"], "cache_valkey_memory_limit"),
        ("sentinel", ["valkey-sentinel", "/etc/valkey/sentinel.conf"], "cache_sentinel_memory_limit"),
    ],
)
def test_cache_valkey_and_sentinel_run_one_pinned_image_on_the_host_network(service, command, limit):
    """Both daemons log to the journal, where the node's Alloy reads them."""
    spec = _render(CACHE_TEMPLATE, CACHE_CONTEXT)["services"][service]
    assert spec["image"] == f"{CACHE_DEFAULTS['cache_image']}@{CACHE_CONTEXT['cache_image_digest']}"
    assert spec["network_mode"] == "host" and "ports" not in spec
    assert spec["command"] == command
    assert spec["user"] == "996:996"
    assert spec["logging"] == {"driver": "journald"}
    assert spec["deploy"]["resources"]["limits"]["memory"] == CACHE_DEFAULTS[limit]
    assert f"{CACHE_DEFAULTS['cache_state_dir']}/conf:/etc/valkey" in spec["volumes"]


def test_cache_data_is_mounted_into_valkey_alone():
    services = _render(CACHE_TEMPLATE, CACHE_CONTEXT)["services"]
    data = f"{CACHE_DEFAULTS['cache_state_dir']}/data:/data"
    assert data in services["valkey"]["volumes"] and data not in services["sentinel"]["volumes"]


# infra/nas/compose.yaml is not Ansible-rendered, but shares the single-file bind-mount pattern the
# assertion below refuses, so it is included anyway.
ALLOY_COMPOSE_FILES = (
    REPO / "infra/ansible/roles/capture/templates/alloy-compose.yaml.j2",
    REPO / "infra/ansible/roles/ops/templates/alloy-compose.yaml.j2",
    REPO / "infra/ansible/roles/cache/templates/alloy-compose.yaml.j2",
    REPO / "infra/nas/compose.yaml",
)


@pytest.mark.parametrize("path", ALLOY_COMPOSE_FILES, ids=lambda p: p.parent.name)
def test_the_alloy_config_is_never_bind_mounted_as_a_single_file(path):
    text = path.read_text()
    # config-selector-ok: a sweep of every non-comment line for the single-file mount, not a value selected
    offenders = [ln.strip() for ln in text.splitlines() if ":/etc/alloy/config.alloy" in ln and not ln.lstrip().startswith("#")]
    assert not offenders, (
        f"{path.name} bind-mounts the Alloy config as a single FILE: {offenders}. That binds the "
        f"inode, which Ansible's atomic write replaces, so the running container reads a file no "
        f"longer in the host tree and every later config change is a silent no-op. Mount the "
        f"directory that contains it instead."
    )
