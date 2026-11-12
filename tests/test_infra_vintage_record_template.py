"""The vintage recorder's ops wiring: its two runners, its two units and its timer, and the gated block that installs them.

The runners are read rendered and run by bash against `docker` and `curl` stubs, never re-implemented here.
"""

import io
import logging
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml
from typer.main import get_command

from cli.__main__ import app
from cli.logging.formatters import PlainTextFormatter
from cli.vintage.credential import read_key
from tests.role_render import render, resolve
from tests.test_infra_archive_pull_template import _ops_parse_regex
from tests.vintage_fixtures import BASE_TICK_START, SENTINEL_KEY
from tests.vintage_stub import run_tick

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/ops"
TEMPLATES = ROLE / "templates"
RECORD_RUNNER = TEMPLATES / "vintage-record.sh.j2"
DERIVE_RUNNER = TEMPLATES / "vintage-derive.sh.j2"
RECORD_UNIT = TEMPLATES / "vintage-record.service.j2"
RECORD_TIMER = TEMPLATES / "vintage-record.timer.j2"
DERIVE_UNIT = TEMPLATES / "vintage-derive.service.j2"
TASKS = REPO / "infra/ansible/roles/ops/tasks/main.yml"
HANDLERS = REPO / "infra/ansible/roles/ops/handlers/main.yml"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

IMAGE_REF = "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "ab" * 32
CONTEXT = {
    "ops_uid": "998",
    "ops_gid": "998",
    "ops_compose_dir": "/etc/zcrypto-ops",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_textfile_dir": "/var/lib/zcrypto-ops/textfile",
    "ops_vintages_subdir": "vintages",
    "ops_vintage_versions_subdir": "vintage-versions",
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "ab" * 32,
    "ops_vintage_record_healthcheck_url": "https://hc.invalid/ping/k/zcrypto-vintage-record",
}

RECORD_TAG = "zcrypto.vintage-record [vintage-record.sh] - "
DERIVE_TAG = "zcrypto.vintage-derive [vintage-derive.sh] - "
WITNESS = (
    "2026-11-12 07:37:41,512 INFO zcrypto.vintage.record [record.py:331] - vintage tick published "
    "tick=20261112T073700Z tick_json_sha256=" + "0123456789abcdef" * 4
)
WITNESS_63_HEX = WITNESS[:-1]
DERIVE_COMPLETE = (
    "2026-11-12 07:58:02,004 INFO zcrypto.vintage.command [command.py:294] - vintage derive complete generation=1 "
    "head=20261112T073700Z head_sha256=" + "fe" * 32 + " parts_added=1"
)
DERIVE_STOPPED = (
    "2026-11-12 07:58:02,004 INFO zcrypto.vintage.command [command.py:229] - vintage derive stopped generation=1 "
    "head=20261111T193700Z at=20261112T073700Z reason=x"
)

DOCKER_STUB = """#!/usr/bin/env bash
printf 'call\\n' >> "$STUB_DIR/calls"
printf '%s\\0' "$@" > "$STUB_DIR/argv"
readlink /proc/self/fd/0 > "$STUB_DIR/stdin_path"
cat > "$STUB_DIR/stdin_bytes"
if [ "${STUB_OUT+set}" = set ]; then printf '%s' "$STUB_OUT"; else printf '%s\\n' "$WITNESS"; fi
exit "${STUB_RC:-0}"
"""
CURL_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_DIR/curl"
exit "${CURL_RC:-0}"
"""


def _render(template: Path, **overrides) -> str:
    return _ENV.from_string(template.read_text()).render(**(CONTEXT | overrides))


def _docker_run_tokens(rendered: str) -> tuple[list[str], list[str]]:
    """The `docker run` command's argv and its redirections, its continuation lines joined."""
    lines = rendered.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("docker run "))
    joined = []
    for line in lines[start:]:
        joined.append(line.removesuffix("\\"))
        if not line.endswith("\\"):
            break
    tokens = shlex.split(" ".join(joined))
    first_redirect = next((i for i, t in enumerate(tokens) if re.match(r"^[0-9]*[<>]", t)), len(tokens))
    return tokens[:first_redirect], tokens[first_redirect:]


def _cli_options(*path: str) -> set[str]:
    command = get_command(app)
    for name in path:
        command = command.commands[name]
    return {opt for param in command.params for opt in param.opts}


def _unit_lines(template: Path) -> list[str]:
    return [line for line in _render(template).splitlines() if line.strip() and not line.startswith("#")]


class _Run:
    def __init__(self, proc: subprocess.CompletedProcess, stub_dir: Path):
        self.rc = proc.returncode
        self.stdout = proc.stdout
        self.stderr_lines = proc.stderr.splitlines()
        calls = stub_dir / "calls"
        self.docker_calls = len(calls.read_text().splitlines()) if calls.exists() else 0
        argv = stub_dir / "argv"
        self.argv = argv.read_bytes().decode().split("\0")[:-1] if argv.exists() else []
        stdin_path = stub_dir / "stdin_path"
        self.stdin_path = stdin_path.read_text().strip() if stdin_path.exists() else None
        stdin_bytes = stub_dir / "stdin_bytes"
        self.stdin_bytes = stdin_bytes.read_bytes() if stdin_bytes.exists() else None
        curl = stub_dir / "curl"
        self.curl_calls = curl.read_text().splitlines() if curl.exists() else []

    def runner_lines(self, tag: str, level: str | None = None) -> list[str]:
        out = []
        for line in self.stderr_lines:
            m = _ops_parse_regex().match(line)
            if m and m.group("rest").startswith(tag) and level in (None, m.group("level")):
                out.append(line)
        return out


def _bash_harness(tmp_path: Path, template: Path = RECORD_RUNNER, **overrides):
    """Return `(run, token)`: `run(*args, rc=, out=, curl_rc=, tmpdir=)` executes the rendered runner under bash with
    `docker` and `curl` stubbed on PATH, and `token` is the key file's path, which the case creates or leaves absent."""
    bash = shutil.which("bash")
    assert bash, "bash is not on PATH"
    bin_dir, compose, stub_dir, tmp = (tmp_path / d for d in ("bin", "compose", "stub", "tmp"))
    for d in (bin_dir, compose, stub_dir, tmp):
        d.mkdir()
    for name, body in (("docker", DOCKER_STUB), ("curl", CURL_STUB)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    script = tmp_path / "runner.sh"
    script.write_text(_render(template, ops_compose_dir=str(compose), **overrides))
    runner_stdin = tmp_path / "runner-stdin"
    runner_stdin.write_text("RUNNER_STDIN\n")

    def run(*args: str, rc: int = 0, out: str | None = None, curl_rc: int = 0, tmpdir: Path = tmp) -> _Run:
        for f in stub_dir.iterdir():
            f.unlink()
        env = {k: v for k, v in os.environ.items() if k != "STUB_OUT"}
        env |= {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "TMPDIR": str(tmpdir),
            "STUB_DIR": str(stub_dir),
            "STUB_RC": str(rc),
            "CURL_RC": str(curl_rc),
            "WITNESS": WITNESS,
        }
        if out is not None:
            env["STUB_OUT"] = out
        with runner_stdin.open("rb") as stdin:
            proc = subprocess.run([bash, str(script), *args], stdin=stdin, capture_output=True, text=True, env=env)
        return _Run(proc, stub_dir)

    return run, compose / "vintage-bgeometrics.token"


# --- the record runner's argv -------------------------------------------------------------------------------------------
def test_the_record_runners_argv():
    argv, redirects = _docker_run_tokens(_render(RECORD_RUNNER))
    assert argv == [
        "docker", "run", "--rm", "-i", "--pull", "never",
        "--name", "zcrypto-vintage-record",
        "--user", "998:998",
        "-v", "/var/lib/zcrypto-ops/vintages:/data",
        "-v", "/var/lib/zcrypto-ops/textfile:/textfile",
        "--entrypoint", "zcrypto",
        IMAGE_REF,
        "vintage", "record",
        "--data-dir", "/data", "--textfile", "/textfile/vintage.prom", "--clock-prom", "/textfile/clock-offset.prom",
        "--bgeometrics-key-stdin", "$@",
    ]  # fmt: skip
    assert redirects == ["<&3", ">", "$out", "2>&1"]
    assert [t for t in redirects if t.startswith("<")] == ["<&3"]
    assert not {"-e", "--env-file", "--network"} & set(argv)
    assert not [t for t in argv if t.startswith("/mnt/")]
    record_options = _cli_options("vintage", "record")
    cli_args = argv[argv.index("record") + 1 :]
    assert [t for t in cli_args if t.startswith("--") and t not in record_options] == []


def test_the_runners_own_arguments_follow_the_clis(tmp_path):
    run, token = _bash_harness(tmp_path)
    token.write_text("")
    named = run("--source", "cm-eth", "--source", "fng")
    assert named.docker_calls == 1
    assert named.argv[-5:] == ["--bgeometrics-key-stdin", "--source", "cm-eth", "--source", "fng"]
    bare = run()
    assert bare.docker_calls == 1
    assert bare.argv[-1] == "--bgeometrics-key-stdin"


# --- the derive runner's argv -------------------------------------------------------------------------------------------
def test_the_derive_runners_argv():
    argv, redirects = _docker_run_tokens(_render(DERIVE_RUNNER))
    assert argv == [
        "docker", "run", "--rm", "--pull", "never",
        "--name", "zcrypto-vintage-derive",
        "--user", "998:998",
        "--network", "none",
        "-v", "/var/lib/zcrypto-ops/vintages/record:/vintages/record:ro",
        "-v", "/var/lib/zcrypto-ops/vintage-versions:/versions",
        "-v", "/var/lib/zcrypto-ops/textfile:/textfile",
        "--entrypoint", "zcrypto",
        IMAGE_REF,
        "vintage", "derive",
        "--record", "/vintages/record", "--table", "/versions", "--textfile", "/textfile/vintage-derive.prom",
    ]  # fmt: skip
    assert redirects == [">", "$out", "2>&1"]
    assert "-i" not in argv and not [t for t in redirects if t.startswith("<")]
    assert not {"-e", "--env-file"} & set(argv)
    assert not [t for t in argv if t.startswith("/mnt/")]
    derive_options = _cli_options("vintage", "derive")
    cli_args = argv[argv.index("derive") + 1 :]
    assert [t for t in cli_args if t.startswith("--") and t not in derive_options] == []


def test_the_derive_mounts_the_record_read_only_at_the_hosts_shape():
    argv, _ = _docker_run_tokens(_render(DERIVE_RUNNER))
    mounts = [argv[i + 1] for i, t in enumerate(argv) if t == "-v"]
    assert "/var/lib/zcrypto-ops/vintages/record:/vintages/record:ro" in mounts
    assert argv[argv.index("--record") + 1] == "/vintages/record"


# --- the units and the timer --------------------------------------------------------------------------------------------
def test_the_record_unit():
    lines = _unit_lines(RECORD_UNIT)
    for line in (
        "Type=oneshot",
        "Requires=docker.service",
        "Wants=network-online.target",
        "Wants=zcrypto-vintage-derive.service",
        "After=docker.service network-online.target",
        "ExecStart=/usr/local/sbin/zcrypto-vintage-record",
    ):
        assert line in lines, line
    assert not [line for line in lines if line.startswith("RequiresMountsFor")]


def test_the_timer_fires_at_0737_and_1937_and_catches_up_once():
    lines = _unit_lines(RECORD_TIMER)
    assert [line for line in lines if line.startswith("OnCalendar=")] == ["OnCalendar=*-*-* 07:37:00", "OnCalendar=*-*-* 19:37:00"]
    assert "Persistent=true" in lines
    assert "Unit=zcrypto-vintage-record.service" in lines
    assert not [line for line in lines if line.startswith(("RandomizedDelaySec", "TimeoutStartSec"))]


def test_the_timer_is_wanted_by_timers_target():
    lines = _unit_lines(RECORD_TIMER)
    assert lines[lines.index("[Install]") + 1 :] == ["WantedBy=timers.target"]


def test_the_derive_unit_runs_after_the_recorder():
    lines = _unit_lines(DERIVE_UNIT)
    assert "After=docker.service zcrypto-vintage-record.service" in lines
    assert "ExecStart=/usr/local/sbin/zcrypto-vintage-derive" in lines


def test_the_derive_unit_has_no_install_section():
    assert [line for line in _unit_lines(DERIVE_UNIT) if line.startswith("[")] == ["[Unit]", "[Service]"]


@pytest.mark.parametrize("unit", [RECORD_UNIT, DERIVE_UNIT], ids=lambda p: p.name)
def test_the_units_run_under_umask_0022(unit):
    lines = _unit_lines(unit)
    service = lines[lines.index("[Service]") + 1 :]
    assert [line for line in service if line.startswith("UMask=")] == ["UMask=0022"]


# --- the gated block ----------------------------------------------------------------------------------------------------
_BLOCK = "install the vintage recorder and its versions-table refresh (needs the pinned image digest)"
_SYSTEMD_OR_SHELL = {
    "ansible.builtin.systemd_service",
    "ansible.builtin.systemd",
    "ansible.builtin.service",
    "ansible.builtin.command",
    "ansible.builtin.shell",
    "systemd_service",
    "systemd",
    "service",
    "command",
    "shell",
}


def _leaves(tasks: list[dict]) -> list[dict]:
    out = []
    for task in tasks:
        if "block" in task:
            out.extend(_leaves(task["block"]))
        else:
            out.append(task)
    return out


def test_the_block_is_gated_on_the_digest_and_enables_the_timer_alone():
    tasks = yaml.safe_load(TASKS.read_text())
    names = [t.get("name") for t in tasks]
    block = tasks[names.index(_BLOCK)]
    assert block.get("when") == "ops_image_digest is defined"
    assert names.index(_BLOCK) > names.index("derive the zcrypto-data uid/gid for the container user mapping")
    inner = {t["name"]: t for t in block["block"]}

    record = inner["install the vintage recorder runner script"]
    assert record["ansible.builtin.template"] == {
        "src": "vintage-record.sh.j2",
        "dest": "/usr/local/sbin/zcrypto-vintage-record",
        "owner": "root",
        "group": "root",
        "mode": "0700",
    }
    assert (record.get("no_log"), record.get("diff")) == (True, False)
    derive = inner["install the versions-table refresh runner script"]
    assert derive["ansible.builtin.template"] == {
        "src": "vintage-derive.sh.j2",
        "dest": "/usr/local/sbin/zcrypto-vintage-derive",
        "owner": "root",
        "group": "root",
        "mode": "0700",
    }
    units = inner["render the vintage recorder and refresh units and the recorder timer"]
    assert set(units["loop"]) == {"vintage-record.service", "vintage-record.timer", "vintage-derive.service"}
    assert units["ansible.builtin.template"]["mode"] == "0644"

    enables = [t for t in block["block"] if "ansible.builtin.systemd_service" in t]
    assert len(enables) == 1
    (enable,) = enables
    assert enable["ansible.builtin.systemd_service"]["name"] == "zcrypto-vintage-record.timer"
    assert enable.get("when") == "not (ansible_check_mode and ops_vintage_unit_install is changed)"

    starters = [
        t.get("name")
        for t in _leaves(tasks + yaml.safe_load(HANDLERS.read_text()))
        if _SYSTEMD_OR_SHELL & set(t) and re.search(r"vintage-(record|derive)\.service", yaml.safe_dump(t))
    ]
    assert starters == []


# --- the key file -------------------------------------------------------------------------------------------------------
_KEY_FILE = "render the BGeometrics key file (root-only; never logged, never diffed)"
_KEY_TEMPLATE = "vintage-bgeometrics.token.j2"


def test_the_key_file_renders_root_only_outside_every_mount():
    tasks = yaml.safe_load(TASKS.read_text())
    names = [t.get("name") for t in tasks]
    index = names.index(_KEY_FILE)
    first_gated_block = next(i for i, t in enumerate(tasks) if "block" in t and "digest is defined" in str(t.get("when", "")))
    assert names.index("ensure the ops compose project directory exists") < index < first_gated_block
    task = tasks[index]
    assert "when" not in task
    assert task["ansible.builtin.template"] == {
        "src": _KEY_TEMPLATE,
        "dest": "{{ ops_compose_dir }}/vintage-bgeometrics.token",
        "owner": "root",
        "group": "root",
        "mode": "0600",
    }
    assert (task.get("no_log"), task.get("diff")) == (True, False)

    dest = Path(resolve(ROLE, task["ansible.builtin.template"]["dest"], {}))
    options = [
        resolve(ROLE, t["ansible.posix.authorized_key"]["key_options"], {})
        for t in _leaves(tasks)
        if "ansible.posix.authorized_key" in t
    ]
    roots = [Path(re.fullmatch(r'command="/usr/bin/rrsync -ro (\S+)",restrict', o)[1]) for o in options]
    assert roots
    for root in (Path(resolve(ROLE, "{{ ops_data_dir }}", {})), *roots):
        assert not dest.is_relative_to(root), root

    unset = render(ROLE, _KEY_TEMPLATE, {})
    assert unset == "\n"
    assert read_key(io.BytesIO(unset.encode())) == (None, "no credential")
    rendered = render(ROLE, _KEY_TEMPLATE, {"bgeometrics_api_key": SENTINEL_KEY})
    assert rendered == f"{SENTINEL_KEY}\n"
    key, reason = read_key(io.BytesIO(rendered.encode()))
    assert (key.reveal(), reason) == (SENTINEL_KEY, None)


# --- the record runner run by bash: the dead-man, the runner's own lines, the token -------------------------------------
_URL = CONTEXT["ops_vintage_record_healthcheck_url"]


@pytest.mark.parametrize(
    ("out", "rc", "url", "pings"),
    [
        (None, 0, _URL, True),
        (None, 1, _URL, True),
        ("", 1, _URL, False),
        (None, 2, _URL, False),
        (None, 125, _URL, False),
        (WITNESS_63_HEX + "\n", 0, _URL, False),
        (None, 0, "", False),
    ],
    ids=["witness-0", "witness-1", "no-witness-1", "witness-2", "witness-125", "witness-63-hex-0", "witness-0-no-url"],
)
def test_the_dead_man_pings_only_on_a_published_tick(tmp_path, out, rc, url, pings):
    run, token = _bash_harness(tmp_path, ops_vintage_record_healthcheck_url=url)
    token.write_text("")
    result = run(rc=rc, out=out)
    assert result.docker_calls == 1
    assert result.rc == rc
    assert result.curl_calls == ([f"-fsS -m 10 -o /dev/null {_URL}"] if pings else [])
    if not url:
        assert result.stderr_lines == []


_NO_TMPDIR = None


@pytest.mark.parametrize(
    ("rc", "out", "errors"),
    [
        (0, None, 0),
        (1, None, 0),
        (0, "", 1),
        (1, "", 1),
        (2, "", 1),
        (125, "", 1),
        (137, None, 1),
        (_NO_TMPDIR, None, 1),
    ],
    ids=["0-witness", "1-witness", "0-nothing", "1-nothing", "2-nothing", "125-nothing", "137-witness", "mktemp-fails"],
)
def test_a_run_with_no_witness_or_an_exit_past_1_logs_one_runner_error(tmp_path, rc, out, errors):
    run, token = _bash_harness(tmp_path)
    token.write_text(f"{SENTINEL_KEY}\n")
    if rc is _NO_TMPDIR:
        result = run(out=out, tmpdir=tmp_path / "absent")
        assert result.docker_calls == 0
        rc = 1
    else:
        result = run(rc=rc, out=out)
        assert len(result.stderr_lines) == errors, result.stderr_lines
    assert result.rc == rc
    lines = result.runner_lines(RECORD_TAG, "ERROR")
    assert len(lines) == errors, result.stderr_lines
    if errors:
        assert f"exit {rc} " in lines[0]


def _assert_dev_null_and_one_error(result: _Run, token: Path, secret: bytes = b""):
    assert result.docker_calls == 1
    assert result.stdin_path == "/dev/null"
    assert result.stdin_bytes == b""
    (line,) = result.stderr_lines
    assert line in result.runner_lines(RECORD_TAG, "ERROR")
    assert str(token) in line
    if secret:
        assert secret.decode() not in line


def test_an_absent_token_file_gives_dev_null_and_one_error(tmp_path):
    run, token = _bash_harness(tmp_path)
    _assert_dev_null_and_one_error(run(), token)


def test_a_directory_token_path_gives_dev_null_and_one_error(tmp_path):
    run, token = _bash_harness(tmp_path)
    token.mkdir()
    _assert_dev_null_and_one_error(run(), token)


def test_an_unreadable_token_file_gives_dev_null_and_one_error(tmp_path):
    if os.geteuid() == 0:
        pytest.fail("run as a non-root uid: root reads a 0000 file")
    run, token = _bash_harness(tmp_path)
    token.write_text(f"{SENTINEL_KEY}\n")
    token.chmod(0o000)
    try:
        _assert_dev_null_and_one_error(run(), token, SENTINEL_KEY.encode())
    finally:
        token.chmod(0o600)


def test_an_empty_token_file_gives_empty_stdin_and_no_error(tmp_path):
    run, token = _bash_harness(tmp_path)
    token.write_text("")
    result = run()
    assert result.docker_calls == 1
    assert (result.stdin_path, result.stdin_bytes) == (str(token), b"")
    assert result.stderr_lines == []


def test_a_token_file_reaches_stdin_whole(tmp_path):
    run, token = _bash_harness(tmp_path)
    token.write_text(f"{SENTINEL_KEY}\n")
    result = run()
    assert result.docker_calls == 1
    assert (result.stdin_path, result.stdin_bytes) == (str(token), f"{SENTINEL_KEY}\n".encode())
    assert result.stderr_lines == []


def test_every_line_the_runner_prints_is_parse_shaped(tmp_path):
    run, _ = _bash_harness(tmp_path)
    result = run(curl_rc=22)
    assert len(result.stderr_lines) == 2, result.stderr_lines
    levels = []
    for line in result.stderr_lines:
        m = _ops_parse_regex().match(line)
        assert m, f"the runner's line does not parse through the ops stage: {line!r}"
        assert m.group("rest").startswith(RECORD_TAG), line
        levels.append(m.group("level"))
    assert levels == ["ERROR", "WARNING"]


# --- the derive runner run by bash --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("rc", "out", "errors"),
    [
        (0, DERIVE_COMPLETE + "\n", 0),
        (1, DERIVE_STOPPED + "\n", 0),
        (0, "", 1),
        (125, "", 1),
        (137, DERIVE_COMPLETE + "\n", 1),
        (_NO_TMPDIR, DERIVE_COMPLETE + "\n", 1),
    ],
    ids=["0-complete", "1-stopped", "0-nothing", "125-nothing", "137-complete", "mktemp-fails"],
)
def test_the_derive_runner_names_an_odd_exit_or_a_missing_summary(tmp_path, rc, out, errors):
    run, _ = _bash_harness(tmp_path, DERIVE_RUNNER)
    if rc is _NO_TMPDIR:
        result = run(out=out, tmpdir=tmp_path / "absent")
        assert result.docker_calls == 0
        rc = 1
    else:
        result = run(rc=rc, out=out)
        assert result.docker_calls == 1
        assert len(result.stderr_lines) == errors, result.stderr_lines
    assert result.rc == rc
    lines = result.runner_lines(DERIVE_TAG, "ERROR")
    assert len(lines) == errors, result.stderr_lines
    if errors:
        assert f"exit {rc} " in lines[0]


# --- the witness pattern against the line the recorder really logs ------------------------------------------------------
def test_the_witness_pattern_matches_the_line_the_recorder_logs(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    run_tick(tmp_path / "data", BASE_TICK_START)
    (record,) = [r for r in caplog.records if r.getMessage().startswith("vintage tick published tick=")]
    line = PlainTextFormatter().format(record)
    pattern = re.search(r"""^witness=\$\(grep -cE '([^']*)' "\$out"\)$""", _render(RECORD_RUNNER), re.M).group(1)
    proc = subprocess.run(["grep", "-cE", pattern], input=line + "\n", capture_output=True, text=True)
    assert proc.stdout == "1\n", (pattern, line)
