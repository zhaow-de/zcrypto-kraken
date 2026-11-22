"""The on-chain node's image and its ops wiring, read from the files themselves; no image is built here."""

import re
import shlex
from pathlib import Path

import jinja2
import yaml

from cli.onchain.brk import BITVIEW_URL

REPO = Path(__file__).resolve().parents[1]
NODE_DOCKERFILE = REPO / "infra/docker/bitcoind/Dockerfile"
OPS_ROLE = REPO / "infra/ansible/roles/ops"
OPS_DEFAULTS = yaml.safe_load((OPS_ROLE / "defaults/main.yml").read_text())

# Ansible's template module renders with trim_blocks on and lstrip_blocks off.
_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

# The role's defaults, so each render reads the values a converge deploys, beside the facts and ids a run supplies:
# zcrypto-data's uid and gid apart, and the two local image ids apart, so a swap of either pair shows.
CONTEXT = {
    **OPS_DEFAULTS,
    "ops_uid": 997,
    "ops_gid": 995,
    "ops_bitcoind_image_id": "sha256:" + "b1" * 32,
    "ops_bitview_image_id": "sha256:" + "f7" * 32,
}

NODE_TARBALL = "bitcoin-32.1-x86_64-linux-gnu.tar.gz"
NODE_SHA256 = "61545c17c3120fb7412f896d248b11993af04ec8817aad3649c55b2afb044963"


def _instructions(path: Path) -> list[tuple[str, str]]:
    """(keyword, arguments) per instruction, comment lines dropped and continuation lines joined."""
    kept = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))
    out = []
    for line in re.sub(r"\\\n", " ", kept).splitlines():
        keyword, _, arguments = line.strip().partition(" ")
        if keyword:
            out.append((keyword.upper(), arguments.strip()))
    return out


def test_the_node_image_checks_its_pinned_sha256_before_it_extracts():
    instructions = _instructions(NODE_DOCKERFILE)
    assert [a for k, a in instructions if k == "FROM"] == ["debian:bookworm-slim"]
    args = dict(a.partition("=")[::2] for k, a in instructions if k == "ARG")
    assert {NODE_TARBALL, NODE_SHA256} <= set(args.values()), args
    runs = [a for k, a in instructions if k == "RUN"]
    assert len(runs) == 1, runs
    # `/bin/sh -c` runs without `-e`: a `;` anywhere in the chain carries the build past a failed check.
    assert ";" not in runs[0], runs[0]
    expanded = re.sub(r"\$\{(\w+)\}", lambda m: args.get(m.group(1), m.group(0)), runs[0])
    steps = [shlex.split(step) for step in expanded.split("&&")]
    check = ["echo", f"{NODE_SHA256}  {NODE_TARBALL}", "|", "sha256sum", "-c", "-"]
    assert check in steps, steps
    extracts = [i for i, step in enumerate(steps) if step[0] == "tar" and NODE_TARBALL in step]
    assert extracts, steps
    assert steps.index(check) < min(extracts), steps
    purges = [
        i
        for i, step in enumerate(steps)
        if step[:2] == ["apt-get", "purge"] and {"--auto-remove", "curl", "ca-certificates"} <= set(step)
    ]
    assert purges and min(purges) > max(extracts), steps
    # The exec form makes `bitcoind` PID 1, so the containers' stop grace reaches the node as SIGTERM.
    assert [a for k, a in instructions if k == "ENTRYPOINT"] == ['["bitcoind"]']


def _compose() -> dict:
    return yaml.safe_load(_ENV.from_string((OPS_ROLE / "templates/onchain-compose.yaml.j2").read_text()).render(**CONTEXT))


def _services() -> dict[str, dict]:
    return _compose()["services"]


def test_the_compose_project_has_two_capped_services_and_no_port_or_secret():
    compose = _compose()
    assert compose["name"] == "zcrypto-onchain"
    services = compose["services"]
    assert {name: s["container_name"] for name, s in services.items()} == {
        "bitcoind": "zcrypto-onchain-bitcoind",
        "bitview": "zcrypto-onchain-bitview",
    }
    limits = {"bitcoind": {"cpus": "4", "memory": "8g"}, "bitview": {"cpus": "8", "memory": "16g"}}
    for name, service in services.items():
        assert service["user"] == f"{CONTEXT['ops_uid']}:{CONTEXT['ops_gid']}", name
        assert service["restart"] == "unless-stopped", name
        assert service["cpu_shares"] == 256, name
        assert service["deploy"]["resources"]["limits"] == limits[name], name
        assert service["blkio_config"] == {
            "device_read_bps": [{"path": CONTEXT["ops_onchain_io_device"], "rate": "400mb"}],
            "device_write_bps": [{"path": CONTEXT["ops_onchain_io_device"], "rate": "200mb"}],
        }, name
        assert service["logging"] == {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}, name
        assert not {"ports", "environment", "env_file"} & set(service), name
    assert CONTEXT["ops_onchain_io_device"] == "/dev/nvme0n1"


def test_both_services_join_the_network_named_zcrypto_onchain():
    compose = _compose()
    (key,) = [k for k, network in compose["networks"].items() if network["name"] == "zcrypto-onchain"]
    for name, service in compose["services"].items():
        assert list(service["networks"]) == [key], name
    command = compose["services"]["bitview"]["command"]
    assert command[command.index("--rpcconnect") + 1] == compose["services"]["bitcoind"]["container_name"]


def test_the_node_mount_is_read_only_into_bitview():
    services = _services()
    root = CONTEXT["ops_onchain_root"]
    assert services["bitcoind"]["volumes"] == [f"{root}/bitcoin:/bitcoin"]
    assert services["bitcoind"]["command"] == ["-datadir=/bitcoin", "-conf=/bitcoin/bitcoin.conf"]
    assert services["bitview"]["volumes"] == [f"{root}/bitcoin:/bitcoin:ro", f"{root}/bitview:/bitview"]


def test_bitview_keeps_its_data_and_working_directory_at_bitview():
    bitview = _services()["bitview"]
    assert bitview["working_dir"] == "/bitview"
    command = bitview["command"]
    assert command[command.index("--bitviewdir") + 1] == "/bitview"
    targets = {volume.split(":")[1]: volume for volume in bitview["volumes"]}
    assert targets["/bitview"] == f"{CONTEXT['ops_onchain_root']}/bitview:/bitview"


def test_bitview_runs_brks_arguments_under_the_images_entrypoint():
    services = _services()
    assert services["bitview"]["command"] == [
        "--bitcoindir",
        "/bitcoin",
        "--blocksdir",
        "/bitcoin/blocks",
        "--bitviewdir",
        "/bitview",
        "--rpcconnect",
        "zcrypto-onchain-bitcoind",
    ]
    assert [name for name, service in services.items() if "entrypoint" in service] == []


def test_both_services_stop_with_a_600s_grace():
    assert CONTEXT["ops_onchain_stop_grace"] == 600
    assert {name: s.get("stop_grace_period") for name, s in _services().items()} == {"bitcoind": "600s", "bitview": "600s"}


def test_both_images_are_named_by_their_ids():
    services = _services()
    assert services["bitcoind"]["image"] == CONTEXT["ops_bitcoind_image_id"]
    assert services["bitview"]["image"] == CONTEXT["ops_bitview_image_id"]


def test_the_node_configuration_lines():
    rendered = _ENV.from_string((OPS_ROLE / "templates/bitcoin.conf.j2").read_text()).render(**CONTEXT)
    lines = [line for line in rendered.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    assert lines == ["server=1", "listen=0", "dbcache=4096", "rpcbind=0.0.0.0", "rpcallowip=0.0.0.0/0"]


def test_the_bitview_url_default_is_the_clients():
    assert OPS_DEFAULTS["ops_bitview_url"] == BITVIEW_URL
