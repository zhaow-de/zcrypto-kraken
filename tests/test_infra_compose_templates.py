"""spec 00069 D10 / plan Task 6 Step 1 (cold-review I5): both Jinja guard branches of every
touched compose template must render valid YAML with the metrics port/env landing on the right
service -- asserted by hand during the T6/T7 review but never pinned as a test. `trim_blocks=True,
lstrip_blocks=False` mirrors Ansible's own Jinja defaults so a template edit relying on either
setting fails here rather than only at a real converge."""

from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

CAPTURE_TEMPLATE = REPO / "infra/ansible/roles/capture/templates/compose.yaml.j2"
ENGINE_TEMPLATE = REPO / "infra/ansible/roles/engine/templates/compose.yaml.j2"
OPS_TEMPLATE = REPO / "infra/ansible/roles/ops/templates/compose.yaml.j2"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

# Dummy but complete contexts: every variable each template references (outside the
# `logship_loki_token is defined` guard), so a render under StrictUndefined only ever fails on a
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
}

OPS_CONTEXT = {
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "c" * 64,
    "ops_uid": 998,
    "ops_gid": 998,
    "ops_liquidations_healthcheck_url": "",
    "coinalyze_api_key": "dummy-key",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_compose_dir": "/etc/zcrypto-ops",
}

_CASES = [
    (CAPTURE_TEMPLATE, CAPTURE_CONTEXT),
    (ENGINE_TEMPLATE, ENGINE_CONTEXT),
    (OPS_TEMPLATE, OPS_CONTEXT),
]
_IDS = ["capture", "engine", "ops"]


def _render(template_path: Path, context: dict) -> dict:
    rendered = _ENV.from_string(template_path.read_text()).render(**context)
    parsed = yaml.safe_load(rendered)
    assert parsed is not None, f"{template_path}: rendered to nothing"
    return parsed


@pytest.mark.parametrize(("template", "context"), _CASES, ids=_IDS)
def test_renders_valid_yaml_without_logship_token(template, context):
    # The `logship_loki_token is defined` guard's FALSE branch (00068 D5/D7): a converge landing
    # before the vault carries the token, or a host that never gets it.
    _render(template, context)


@pytest.mark.parametrize(("template", "context"), _CASES, ids=_IDS)
def test_renders_valid_yaml_with_logship_token(template, context):
    # The guard's TRUE branch -- exercises the un-nesting of `environment:`/`entrypoint:` out from
    # under it, this branch's riskiest edit on the trade-key host's engine template.
    _render(template, {**context, "logship_loki_token": "dummy-token"})


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


def test_engine_logship_guard_moves_environment_and_entrypoint_together():
    # The riskiest edit in the branch (cold-review I5): `environment:` un-nested out of the
    # logship guard on the TRADE-KEY host. ZCRYPTO_METRICS_PORT (spec 00069 D6, unguarded) must
    # stay present either way; --ship-logs/ZCRYPTO_LOG_HOST must appear only with the token.
    without_token = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["engine"]
    with_token = _render(ENGINE_TEMPLATE, {**ENGINE_CONTEXT, "logship_loki_token": "dummy-token"})["services"]["engine"]

    assert without_token["environment"]["ZCRYPTO_METRICS_PORT"] == "9102"
    assert "ZCRYPTO_LOG_HOST" not in without_token["environment"]
    assert without_token["entrypoint"] == ["zcrypto", "engine", "run"]

    assert with_token["environment"]["ZCRYPTO_METRICS_PORT"] == "9102"
    assert with_token["environment"]["ZCRYPTO_LOG_HOST"] == "zcrypto"
    assert with_token["entrypoint"] == ["zcrypto", "--ship-logs", "engine", "run"]
