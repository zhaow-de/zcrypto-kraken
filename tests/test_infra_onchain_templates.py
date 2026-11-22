"""The on-chain node's image and its ops wiring, read from the files themselves; no image is built here.

The writer's and the guard's runners are read rendered and run by bash against `docker`, `curl` and `date` stubs, never
re-implemented here.
"""

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from typer.main import get_command

from cli.__main__ import app
from cli.onchain.brk import BITVIEW_URL
from cli.onchain.chain import chain_name
from cli.vintage.gauges import HELP, LAST_OK, _sample
from cli.vintage.sources import SOURCES
from tests.test_infra_archive_pull_template import _ops_parse_regex

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
    "ops_image_digest": "sha256:" + "ab" * 32,
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


# --- the writer's and the guard's runners, run by bash ------------------------------------------------------------------
TEMPLATES = OPS_ROLE / "templates"
WRITE_RUNNER = TEMPLATES / "onchain-write.sh.j2"
WRITE_UNIT = TEMPLATES / "onchain-write.service.j2"
WRITE_TIMER = TEMPLATES / "onchain-write.timer.j2"
GUARD_RUNNER = TEMPLATES / "onchain-guard.sh.j2"
GUARD_UNIT = TEMPLATES / "onchain-guard.service.j2"
GUARD_TIMER = TEMPLATES / "onchain-guard.timer.j2"
ARCHIVE_PULL_RUNNER = TEMPLATES / "archive-pull.sh.j2"
PANEL_RUNNER = TEMPLATES / "panel-materialize.sh.j2"

WRITE_TAG = "zcrypto.onchain-write [onchain-write.sh] - "
GUARD_TAG = "zcrypto.onchain-guard [onchain-guard.sh] - "
COMPLETE = (
    "2026-11-22 10:17:41,512 INFO zcrypto.onchain.command [command.py:61] - onchain write complete "
    "chain=btc-brk1a19c5e96976-g1 head=2026-11-20 wrote=1 base=0"
)
STOPPED = (
    "2026-11-22 10:17:41,512 ERROR zcrypto.onchain.command [command.py:40] - onchain write stopped "
    "chain=btc-brk1a19c5e96976-g1 head=none reason=lock held"
)

# The guard's one clock read answers this, and every fixture is stamped against it, so no second ticking between the
# test and the guard moves an age across its bar.
NOW = 1_795_300_000
# The bars as the role's defaults render them.
BARS = {"archive-pull": 5400, "panel": 10800, "poller": 900, "recorder": 46800}
FRESH_AGES = {"archive-pull": 60, "panel": 60, "poller": 30, "recorder": 10800}
FRESH_LAST_OK = [float(NOW - 3600), float(NOW - 7200), float(NOW - 10800), 0]
STOP_BITVIEW = ["stop", "-t", "600", "zcrypto-onchain-bitview"]
STOP_BITCOIND = ["stop", "-t", "600", "zcrypto-onchain-bitcoind"]
POLLER_URL = "http://127.0.0.1:9103/metrics"

DOCKER_STUB = """#!/usr/bin/env bash
printf '%s\\0' "$@" >> "$STUB_DIR/docker"
printf '\\n' >> "$STUB_DIR/docker"
case "$1" in
    network) exit "${NETWORK_RC:-0}" ;;
    run) printf '%s' "${RUN_OUT-}"; exit "${RUN_RC:-0}" ;;
    ps) printf '%s' "${PS_OUT-0123456789ab}"; exit "${PS_RC:-0}" ;;
    stop) if [ "${!#}" = zcrypto-onchain-bitview ]; then exit "${BITVIEW_STOP_RC:-0}"; fi ;;
esac
exit 0
"""
CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_DIR/curl"
if [ -f "$CURL_BODY" ]; then cat "$CURL_BODY"; fi
exit "${CURL_RC:-0}"
"""
# Answers the guard's one clock read, `date -u +%s`, with DATE_STUB_NOW; every other call reaches the real date.
DATE_STUB = """#!/usr/bin/env bash
if [ "$*" = "-u +%s" ]; then
  echo "$DATE_STUB_NOW"
else
  exec REAL_DATE "$@"
fi
"""
_KNOBS = {"NETWORK_RC", "RUN_OUT", "RUN_RC", "PS_OUT", "PS_RC", "BITVIEW_STOP_RC", "CURL_RC"}
_NO_TMPDIR = None


class _Run:
    def __init__(self, proc: subprocess.CompletedProcess, stub: Path):
        self.rc = proc.returncode
        self.stdout = proc.stdout
        self.stderr_lines = proc.stderr.splitlines()
        calls = stub / "docker"
        self.docker = [call.split("\0") for call in calls.read_text().split("\0\n")[:-1]] if calls.exists() else []
        curl = stub / "curl"
        self.curl = curl.read_text().splitlines() if curl.exists() else []

    @property
    def stops(self) -> list[list[str]]:
        return [call for call in self.docker if call[0] == "stop"]

    def logged(self, tag: str) -> list[tuple[str, str]]:
        """Each stderr line as its level and its message after `tag`; a line the ops stage does not parse, or one
        another tag carries, stays whole beside `unparsed`."""
        out = []
        for line in self.stderr_lines:
            m = _ops_parse_regex().match(line)
            if m and m.group("rest").startswith(tag):
                out.append((m.group("level"), m.group("rest").removeprefix(tag)))
            else:
                out.append(("unparsed", line))
        return out


class _Harness:
    """A rendered runner under bash with `docker`, `curl` and `date` stubbed on PATH, the role's defaults rendered with
    the case's own data and textfile directories."""

    def __init__(self, root: Path, template: Path):
        self.bash = shutil.which("bash")
        assert self.bash, "bash is not on PATH"
        real_date = shutil.which("date")
        assert real_date, "date is not on PATH"
        root.mkdir(parents=True, exist_ok=True)
        self.bin, self.stub, self.data, self.textfile, self.tmp = (root / d for d in ("bin", "stub", "data", "textfile", "tmp"))
        for d in (self.bin, self.stub, self.data, self.textfile, self.tmp):
            d.mkdir()
        self.body = root / "metrics-body"
        for name, text in (("docker", DOCKER_STUB), ("curl", CURL_STUB), ("date", DATE_STUB.replace("REAL_DATE", real_date))):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        rendered = _ENV.from_string(template.read_text()).render(
            **(CONTEXT | {"ops_data_dir": str(self.data), "ops_textfile_dir": str(self.textfile)})
        )
        # Un-substituted, a path is the live ops node's: this host is that node.
        assert "/var/lib/" not in rendered
        self.script = root / "runner.sh"
        self.script.write_text(rendered)

    @property
    def chain(self) -> Path:
        return self.data / CONTEXT["ops_onchain_subdir"] / chain_name(CONTEXT["ops_bitview_commit"])

    def run(self, *args: str, tmpdir: Path | None = None, **knobs) -> _Run:
        for f in self.stub.iterdir():
            f.unlink()
        env = {k: v for k, v in os.environ.items() if k not in _KNOBS}
        env |= {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(tmpdir or self.tmp),
            "STUB_DIR": str(self.stub),
            "CURL_BODY": str(self.body),
            "DATE_STUB_NOW": str(NOW),
        }
        env |= {k: str(v) for k, v in knobs.items()}
        proc = subprocess.run(
            [self.bash, str(self.script), *args], stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env
        )
        return _Run(proc, self.stub)


def _render(template: Path) -> str:
    return _ENV.from_string(template.read_text()).render(**CONTEXT)


def _unit_lines(template: Path) -> list[str]:
    return [line for line in _render(template).splitlines() if line.strip() and not line.startswith("#")]


def _exec_start() -> list[str]:
    (line,) = [line for line in _unit_lines(WRITE_UNIT) if line.startswith("ExecStart=")]
    return shlex.split(line.removeprefix("ExecStart="))


# --- the sources, each in its producer's whole layout -------------------------------------------------------------------
def _textfile(runner: Path, success: int, *, without_success: bool = False) -> str:
    """The textfile as `runner` prints it: its three gauges each under its HELP and TYPE lines, the exit 0, the last
    run at NOW and the last success `success`."""
    source = runner.read_text()
    block = source[source.index('tmp="$PROM.tmp"') : source.index('} > "$tmp"')]
    values = {"$rc": "0", "$now": str(NOW), "$success": str(success)}
    lines = [
        fmt.replace("%s", values[var]) if var else fmt
        for fmt, var in re.findall(r"""^    printf '(.*)\\n'(?: "(\$\w+)")?$""", block, re.M)
    ]
    assert len(lines) == 9 and lines[-1].endswith(f"_last_success_timestamp {success}"), lines
    return "\n".join(lines[:-1] if without_success else lines) + "\n"


def _vintage_prom(last_ok: list) -> str:
    """`vintage.prom` in render_prom's layout: each family's HELP and TYPE over one sample a source, the last-ok family's
    values `last_ok` and every other family's a small positive number."""
    sources = SOURCES[: len(last_ok)]
    lines = []
    for n, family in enumerate(HELP, 1):
        lines += [f"# HELP {family} {HELP[family]}", f"# TYPE {family} gauge"]
        values = last_ok if family == LAST_OK else [n] * len(sources)
        lines += [_sample(family, source, value) for source, value in zip(sources, values, strict=True)]
    return "\n".join(lines) + "\n"


def _poller_body(gauge: float | None, start: float | None) -> str:
    """The poller's /metrics as prometheus_client serves it: a `gauge` of None a gauge never set, a `start` of None no
    process start in the body."""
    registry = CollectorRegistry()
    success = Gauge("zcrypto_liquidations_last_success_timestamp_seconds", "the poller's last good cycle", registry=registry)
    if gauge is not None:
        success.set(gauge)
    if start is not None:
        Gauge("process_start_time_seconds", "the poller's process start", registry=registry).set(start)
    return generate_latest(registry).decode()


def _fresh() -> dict[str, str | None]:
    return {
        "archive_pull": _textfile(ARCHIVE_PULL_RUNNER, NOW - 60),
        "panel": _textfile(PANEL_RUNNER, NOW - 60),
        "vintage": _vintage_prom([*FRESH_LAST_OK, float(NOW - 1800)]),
        "body": _poller_body(NOW - 30.5, NOW - 86400),
    }


def _lay(h: _Harness, **sources: str | None) -> None:
    """Every source fresh, less the ones `sources` sets: a text written whole, None the source absent."""
    layout = _fresh() | sources
    paths = {
        "archive_pull": h.textfile / "ops-archive-pull.prom",
        "panel": h.textfile / "ops-panel-materialize.prom",
        "vintage": h.textfile / "vintage.prom",
        "body": h.body,
    }
    for name, path in paths.items():
        if layout[name] is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(layout[name])


def _info(ages: dict) -> str:
    ages = FRESH_AGES | ages
    return "ages in seconds: " + ", ".join(f"{read}={ages[read]} bar={bar}" for read, bar in BARS.items())


# --- the writer's runner ------------------------------------------------------------------------------------------------
def test_the_writer_runners_argv(tmp_path):
    h = _Harness(tmp_path, WRITE_RUNNER)
    result = h.run(*_exec_start()[1:], RUN_OUT=COMPLETE + "\n")
    assert (result.rc, result.stderr_lines) == (0, [])
    assert [call[0] for call in result.docker] == ["network", "run"]
    assert result.docker[0] == ["network", "inspect", "zcrypto-onchain"]
    argv = result.docker[1]
    assert argv == [
        "run", "--rm", "--pull", "never",
        "--name", "zcrypto-onchain-write",
        "--user", "997:995",
        "--network", "zcrypto-onchain",
        "-v", f"{h.data}/onchain:/data",
        "--entrypoint", "zcrypto",
        "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "ab" * 32,
        "onchain", "write",
        "--chain-root", "/data",
        "--bitview", "http://zcrypto-onchain-bitview:3110",
        "--brk-commit", "1a19c5e969761a0ce446483767da8c765e4aa895",
        "--bitview-image", "sha256:" + "f7" * 32,
        "--bitcoind-image", "sha256:" + "b1" * 32,
    ]  # fmt: skip
    assert not {"-i", "-e", "--env-file"} & set(argv)
    assert not [argv[i + 1] for i, t in enumerate(argv) if t == "-v" and argv[i + 1].startswith("/mnt/")]
    write = get_command(app).commands["onchain"].commands["write"]
    options = {opt for param in write.params for opt in param.opts}
    cli_args = argv[argv.index("write") + 1 :]
    assert [t for t in cli_args if t.startswith("--") and t not in options] == []


@pytest.mark.parametrize(
    ("layout", "level", "rc"),
    [("absent", "INFO", 0), ("empty-index", "INFO", 0), ("a-line", "ERROR", 1)],
    ids=["chain-absent", "chain-with-an-empty-index", "chain-holding-a-line"],
)
def test_the_writer_runner_before_and_after_the_base(tmp_path, layout, level, rc):
    h = _Harness(tmp_path, WRITE_RUNNER)
    if layout != "absent":
        (h.chain / "index").mkdir(parents=True)
    if layout == "a-line":
        line = h.chain / "index/2026/11/20.json"
        line.parent.mkdir(parents=True)
        line.write_text("{}\n")
    result = h.run(*_exec_start()[1:], NETWORK_RC=1)
    assert result.rc == rc
    assert [call[0] for call in result.docker] == ["network"]
    ((logged_level, message),) = result.logged(WRITE_TAG)
    assert logged_level == level
    if level == "ERROR":
        assert "zcrypto-onchain" in message


@pytest.mark.parametrize(
    ("rc", "out", "errors"),
    [
        (0, COMPLETE + "\n", 0),
        (1, STOPPED + "\n", 0),
        (0, "", 1),
        (125, "", 1),
        (137, COMPLETE + "\n", 1),
        (_NO_TMPDIR, COMPLETE + "\n", 1),
    ],
    ids=["0-complete", "1-stopped", "0-nothing", "125-nothing", "137-complete", "mktemp-fails"],
)
def test_the_writer_runner_names_an_odd_exit_or_a_missing_summary(tmp_path, rc, out, errors):
    h = _Harness(tmp_path, WRITE_RUNNER)
    if rc is _NO_TMPDIR:
        result = h.run(*_exec_start()[1:], RUN_OUT=out, tmpdir=tmp_path / "absent")
        assert [call[0] for call in result.docker] == ["network"]
        rc = 1
    else:
        result = h.run(*_exec_start()[1:], RUN_RC=rc, RUN_OUT=out)
        assert [call[0] for call in result.docker] == ["network", "run"]
        assert len(result.stderr_lines) == errors, result.stderr_lines
    assert result.rc == rc
    lines = [message for level, message in result.logged(WRITE_TAG) if level == "ERROR"]
    assert len(lines) == errors, result.stderr_lines
    if errors:
        assert f"exit {rc} " in lines[0]


def test_the_runner_names_the_writers_chain():
    chain = f"{CONTEXT['ops_data_dir']}/{CONTEXT['ops_onchain_subdir']}/{chain_name(CONTEXT['ops_bitview_commit'])}/"
    assert _render(WRITE_RUNNER).count(chain) == 1


# --- the guard's runner -------------------------------------------------------------------------------------------------
def _slipping(case: str, past: bool) -> dict:
    """Every source fresh but the one `case` names, one second past its bar when `past`, else at it."""
    match case:
        case "archive-pull":
            return {"archive_pull": _textfile(ARCHIVE_PULL_RUNNER, NOW - 5400 - int(past))}
        case "panel":
            return {"panel": _textfile(PANEL_RUNNER, NOW - 10800 - int(past))}
        case "poller":
            return {"body": _poller_body(NOW - 900 - (1.25 if past else 0.25), NOW - 86400)}
        case "poller-unset":
            return {"body": _poller_body(None, NOW - 900 - (1.25 if past else 0.25))}
        case "recorder":
            return {"vintage": _vintage_prom([*FRESH_LAST_OK, float(NOW - 46800 - int(past))])}
    raise AssertionError(case)


@pytest.mark.parametrize(
    ("case", "past", "bitview_stop_rc"),
    [
        pytest.param("archive-pull", True, 0, id="archive-pull-past"),
        pytest.param("archive-pull", False, 0, id="archive-pull-at"),
        pytest.param("panel", True, 0, id="panel-past"),
        pytest.param("panel", False, 0, id="panel-at"),
        pytest.param("poller", True, 0, id="poller-past"),
        pytest.param("poller", False, 0, id="poller-at"),
        pytest.param("poller-unset", True, 0, id="poller-unset-process-past"),
        pytest.param("poller-unset", False, 0, id="poller-unset-process-at"),
        pytest.param("recorder", True, 0, id="recorder-past"),
        pytest.param("recorder", False, 0, id="recorder-at"),
        pytest.param("archive-pull", True, 1, id="archive-pull-past-bitview-stop-refused"),
    ],
)
def test_the_guard_stops_both_containers_on_a_slip(tmp_path, case, past, bitview_stop_rc):
    h = _Harness(tmp_path, GUARD_RUNNER)
    _lay(h, **_slipping(case, past))
    result = h.run(BITVIEW_STOP_RC=bitview_stop_rc)
    read = case.removesuffix("-unset")
    bar = BARS[read]
    age = bar + int(past)
    expected = [("INFO", _info({read: age}))]
    if past:
        expected.append(
            (
                "ERROR",
                f"the {read} age {age}s is past its bar {bar}s: stopping zcrypto-onchain-bitview and zcrypto-onchain-bitcoind",
            )
        )
    if bitview_stop_rc:
        expected.append(("WARNING", "docker stop of zcrypto-onchain-bitview exited 1"))
    assert result.logged(GUARD_TAG) == expected
    assert result.curl == [f"-fsS -m 5 {POLLER_URL}"]
    assert result.stops == ([STOP_BITVIEW, STOP_BITCOIND] if past else [])
    assert result.rc == (1 if past else 0)


_UNREADABLE = {
    "archive-pull-absent": ("archive-pull", lambda: {"archive_pull": None}, {}),
    "panel-without-its-success-line": (
        "panel",
        lambda: {"panel": _textfile(PANEL_RUNNER, NOW - 60, without_success=True)},
        {},
    ),
    "archive-pull-success-0": ("archive-pull", lambda: {"archive_pull": _textfile(ARCHIVE_PULL_RUNNER, 0)}, {}),
    "poller-gauge-x": (
        "poller",
        lambda: {
            "body": re.sub(
                r"^(zcrypto_liquidations_last_success_timestamp_seconds) \S+$",
                r"\1 x",
                _poller_body(NOW - 30.5, NOW - 86400),
                count=1,
                flags=re.M,
            )
        },
        {},
    ),
    "vintage-absent": ("recorder", lambda: {"vintage": None}, {}),
    "vintage-every-sample-0": ("recorder", lambda: {"vintage": _vintage_prom([0] * 5)}, {}),
    "vintage-a-sample-x": ("recorder", lambda: {"vintage": _vintage_prom([*FRESH_LAST_OK, "x"])}, {}),
    "curl-fails": ("poller", lambda: {}, {"CURL_RC": 7}),
    "poller-never-set-no-process-start": ("poller", lambda: {"body": _poller_body(None, None)}, {}),
}


@pytest.mark.parametrize("variant", [*_UNREADABLE, "docker-ps-fails"])
def test_an_unreadable_age_warns_and_stops_nothing(tmp_path, variant):
    h = _Harness(tmp_path, GUARD_RUNNER)
    if variant == "docker-ps-fails":
        _lay(h)
        result = h.run(PS_RC=1, PS_OUT="")
        assert result.logged(GUARD_TAG) == [
            ("WARNING", "docker ps exited 1, so whether an on-chain container runs is unread; nothing read, nothing stopped")
        ]
        assert result.curl == []
    else:
        read, sources, knobs = _UNREADABLE[variant]
        _lay(h, **sources())
        if variant == "poller-gauge-x":
            assert "zcrypto_liquidations_last_success_timestamp_seconds x\n" in h.body.read_text()
        result = h.run(**knobs)
        where = {
            "archive-pull": f"{h.textfile}/ops-archive-pull.prom",
            "panel": f"{h.textfile}/ops-panel-materialize.prom",
            "poller": POLLER_URL,
            "recorder": f"{h.textfile}/vintage.prom",
        }[read]
        assert result.logged(GUARD_TAG) == [
            ("INFO", _info({read: "unread"})),
            ("WARNING", f"the {read} age is unread from {where}, so it stops nothing"),
        ]
    assert result.stops == []
    assert result.rc == 0


def test_the_guard_reads_nothing_when_neither_container_runs(tmp_path):
    h = _Harness(tmp_path, GUARD_RUNNER)
    _lay(h)
    result = h.run(PS_OUT="")
    assert (result.rc, result.stderr_lines, result.stdout) == (0, [], "")
    assert result.docker == [["ps", "-q", "--filter", "name=^zcrypto-onchain-(bitcoind|bitview)$"]]
    assert result.curl == []


def test_every_line_the_runners_print_is_parse_shaped(tmp_path):
    guard = _Harness(tmp_path / "guard", GUARD_RUNNER)
    _lay(guard, archive_pull=_textfile(ARCHIVE_PULL_RUNNER, NOW - 5401), panel=None)
    writer = _Harness(tmp_path / "writer", WRITE_RUNNER)
    before = writer.run(*_exec_start()[1:], NETWORK_RC=1)
    (writer.chain / "index/2026/11").mkdir(parents=True)
    (writer.chain / "index/2026/11/20.json").write_text("{}\n")
    after = writer.run(*_exec_start()[1:], NETWORK_RC=1)
    odd = writer.run(*_exec_start()[1:], RUN_RC=125, RUN_OUT="")
    for result, tag, levels in (
        (guard.run(BITVIEW_STOP_RC=1), GUARD_TAG, ["INFO", "ERROR", "WARNING", "WARNING"]),
        (before, WRITE_TAG, ["INFO"]),
        (after, WRITE_TAG, ["ERROR"]),
        (odd, WRITE_TAG, ["ERROR"]),
    ):
        seen = []
        for line in result.stderr_lines:
            m = _ops_parse_regex().match(line)
            assert m, f"the runner's line does not parse through the ops stage: {line!r}"
            assert m.group("rest").startswith(tag), line
            seen.append(m.group("level"))
        assert seen == levels, result.stderr_lines


# --- the units and the timers -------------------------------------------------------------------------------------------
def test_the_units_and_timers():
    write = _unit_lines(WRITE_UNIT)
    for line in ("Type=oneshot", "Requires=docker.service", "After=docker.service"):
        assert line in write, line
    assert _exec_start() == [
        "/usr/local/sbin/zcrypto-onchain-write",
        "--bitview-image",
        CONTEXT["ops_bitview_image_id"],
        "--bitcoind-image",
        CONTEXT["ops_bitcoind_image_id"],
    ]
    write_timer = _unit_lines(WRITE_TIMER)
    assert [line for line in write_timer if line.startswith("OnCalendar=")] == ["OnCalendar=*-*-* *:17:00"]
    assert "Persistent=true" in write_timer
    assert "Unit=zcrypto-onchain-write.service" in write_timer
    assert write_timer[write_timer.index("[Install]") + 1 :] == ["WantedBy=timers.target"]

    guard = _unit_lines(GUARD_UNIT)
    assert "Type=oneshot" in guard
    assert [line for line in guard if line.startswith("ExecStart=")] == ["ExecStart=/usr/local/sbin/zcrypto-onchain-guard"]
    assert not [line for line in guard if line.startswith("TimeoutStartSec")]
    guard_timer = _unit_lines(GUARD_TIMER)
    intervals = [line for line in guard_timer if line.startswith(("OnBootSec=", "OnUnitActiveSec=", "OnCalendar="))]
    assert intervals == ["OnBootSec=2min", "OnUnitActiveSec=5min"]
    assert "Unit=zcrypto-onchain-guard.service" in guard_timer
    assert guard_timer[guard_timer.index("[Install]") + 1 :] == ["WantedBy=timers.target"]
