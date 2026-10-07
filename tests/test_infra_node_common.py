from __future__ import annotations

import configparser
import grp
import json
import os
import re
import shlex
import shutil
import signal
import sqlite3
import stat
import subprocess
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tests import role_render
from tests.test_infra_converge_guards import find_task, iter_tasks, load_tasks, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/node_common"
PREFLIGHT_NAME = "refuse a missing or misshapen secret, naming the key and never the value"
# Shaped like what a generator and the ping service write; neither is a credential.
SECRETS = {
    "probe_password": "A" * 48,
    "probe_ping_url": "https://hc-ping.com/" + "0" * 8 + "-0000-4000-8000-" + "0" * 12,
}
INCLUDE = {
    "node_common_secrets_preflight": [
        {"key": "probe_password", "shape": r"[A-Za-z0-9]{32,}\Z"},
        {"key": "probe_ping_url", "shape": r"https://hc-ping\.com/\S+\Z"},
    ],
    "node_common_secrets_preflight_file": "host_vars/probe/vault.yml",
    "node_common_secrets_preflight_runbook": "infra/runbooks/probe.md's probe-secrets procedure",
}
REBOOT_CHECK = {"node_common_reboot_check_textfile_dir": "/var/lib/probe-textfile", "node_common_role_name": "probe"}
SELFCHECK = {
    "node_common_selfcheck_name": "probe-selfcheck",
    "node_common_selfcheck_script": "probe-selfcheck.py",
    "node_common_selfcheck_description": "Ping the probe's dead-man check while its web answers",
    "node_common_selfcheck_timer_description": "Every-minute self-check of the probe",
    "node_common_selfcheck_environment": {"PROBE_SELFCHECK_WEB": "http://127.0.0.1:8000", "PROBE_SELFCHECK_HOST": "probe.invalid"},
    "node_common_selfcheck_env_var": "PROBE_SELFCHECK_HEALTHCHECK_URL",
    "node_common_selfcheck_env_value": "https://hc-ping.invalid/probe",
    "node_common_selfcheck_on_calendar": "*:0/1:07",
    "node_common_role_name": "probe",
}


def _preflight() -> dict:
    (task,) = load_tasks(ROLE / "tasks/secrets-preflight.yml")
    assert task["name"] == PREFLIGHT_NAME
    return task


# --- secrets-preflight: a listed key refused by name when missing or misshapen -----------------------------------
@pytest.mark.parametrize(
    ("override", "refused"),
    [
        ({}, None),
        ({"probe_password": "root"}, "probe_password"),
        ({"probe_password": "administrator"}, "probe_password"),
        ({"probe_password": None}, "probe_password"),
        ({"probe_password": "short"}, "probe_password"),
        ({"probe_password": "has a space in it, which a generator never writes"}, "probe_password"),
        ({"probe_password": "$2b$10$" + "f" * 53}, "probe_password"),
        ({"probe_password": SECRETS["probe_password"] + "\n"}, "probe_password"),
        ({"probe_ping_url": None}, "probe_ping_url"),
        ({"probe_ping_url": "https://hc-ping.invalid/abc"}, "probe_ping_url"),
        ({"probe_ping_url": "https://hc-ping.com/"}, "probe_ping_url"),
        ({"probe_ping_url": SECRETS["probe_ping_url"] + "\n"}, "probe_ping_url"),
        ({"probe_password": ""}, "probe_password"),
    ],
    ids=[
        "both",
        "a word a stranger tries",
        "a long word a stranger tries",
        "one missing",
        "too short",
        "not letters and digits",
        "a hash where a password belongs",
        "a trailing newline",
        "the ping URL missing",
        "a ping URL off the ping host",
        "a ping URL naming no check",
        "a ping URL with a trailing newline",
        "an empty value",
    ],
)
def test_a_missing_or_misshapen_secret_is_refused_by_its_key(override, refused):
    role_render.assert_preflight(_preflight(), SECRETS, override, refused, INCLUDE)


def test_a_refusal_printing_part_of_a_secret_through_a_default_fails_the_driver():
    task = _preflight()
    task["ansible.builtin.assert"]["fail_msg"] += " {{ (probe_password | default(''))[:6] }}"
    with pytest.raises(AssertionError, match="the refusal depends on a secret"):
        role_render.assert_preflight(task, SECRETS, {"probe_ping_url": None}, "probe_ping_url", INCLUDE)


def test_every_shape_an_including_role_passes_ends_in_backslash_z():
    # Only some keys have a trailing-newline case to catch a lost `\Z`.
    includes = [
        (path.parts[-3], task)
        for path in sorted((REPO / "infra/ansible/roles").glob("*/tasks/*.yml"))
        for task, _ in iter_tasks(load_tasks(path) or [])
        if task.get("ansible.builtin.include_role") == {"name": "node_common", "tasks_from": "secrets-preflight"}
    ]
    assert includes, "found no preflight include: the walk is broken, not the tree clean"
    for role, task in includes:
        for entry in task["vars"]["node_common_secrets_preflight"]:
            assert entry["shape"].endswith(r"\Z"), (role, entry["key"], entry["shape"])


# --- reboot-check: the capture role's program, installed and timed as its copies are -----------------------------
def _reboot_check() -> list[dict]:
    return load_tasks(ROLE / "tasks/reboot-check.yml")


def test_the_reboot_check_installs_what_its_unit_runs_and_enables_the_timer_alone():
    unit = role_render.render(ROLE, "zcrypto-reboot-check.service.j2", {}, **REBOOT_CHECK).splitlines()
    assert unit[0].startswith("# Rendered by the `probe` Ansible role at /etc/systemd/system/zcrypto-reboot-check.service;")
    binary, flag, out = next(line for line in unit if line.startswith("ExecStart=")).removeprefix("ExecStart=").split()
    assert (flag, out) == ("/run/reboot-required", "/var/lib/probe-textfile/reboot.prom")
    assert [line for line in unit if line.startswith("ReadWritePaths=")] == ["ReadWritePaths=/var/lib/probe-textfile"]
    modules = [(module, args) for task in _reboot_check() for module, args in task.items() if isinstance(args, dict)]
    for module, args in modules:
        if "src" in args:
            assert (ROLE / ("templates" if module == "ansible.builtin.template" else "files") / args["src"]).is_file(), args
    assert binary in {args.get("dest") for _, args in modules}, f"the unit runs {binary}, which the task file does not install"
    enabled = [args["name"] for module, args in modules if module == "ansible.builtin.systemd_service" and args.get("enabled")]
    assert enabled == ["zcrypto-reboot-check.timer"], enabled


@pytest.mark.parametrize(
    ("check", "changed", "runs"),
    [(True, True, False), (True, False, True), (False, True, True)],
    ids=["a first-install preview", "an established node's preview", "a real converge"],
)
def test_a_first_install_preview_skips_the_timer_it_never_wrote(check, changed, runs):
    install = find_task(_reboot_check(), "install the reboot-check systemd timer")
    enable = find_task(_reboot_check(), "enable + start the reboot-check timer")
    variables = {"ansible_check_mode": check, install["register"]: {"changed": changed}}
    assert truthy(when_conditions(enable), variables) is runs


# --- selfcheck: a node's script over the shared loop, its ping URL in a root-only file, its unit and its timer -----
def _selfcheck() -> list[dict]:
    return load_tasks(ROLE / "tasks/selfcheck.yml")


def _selfcheck_render(name: str) -> list[str]:
    return role_render.render(ROLE, name, {}, **SELFCHECK).splitlines()


def _selfcheck_resolved(value):
    return role_render.resolve(ROLE, value, {}, **SELFCHECK)


def _selfcheck_service() -> dict[str, str]:
    unit = _selfcheck_render("selfcheck.service.j2")
    return dict(line.split("=", 1) for line in unit if "=" in line and not line.startswith(("#", "Environment=")))


def _selfcheck_steps() -> list[tuple[dict, str, dict]]:
    steps = []
    for task in _selfcheck():
        ((module, args),) = [(key, value) for key, value in task.items() if isinstance(value, dict)]
        steps.append((task, module, {k: _selfcheck_resolved(v) for k, v in args.items()}))
    return steps


def test_the_selfcheck_unit_sets_the_includes_environment_and_the_shared_modules_path_and_hides_no_path():
    unit = _selfcheck_render("selfcheck.service.j2")
    environment = dict(line.removeprefix("Environment=").split("=", 1) for line in unit if line.startswith("Environment="))
    assert environment == SELFCHECK["node_common_selfcheck_environment"] | {"PYTHONPATH": "/usr/local/lib/zcrypto"}
    # The module is read under ProtectSystem=strict's read-only /usr, the premise the node's first run proves; a path
    # hidden or remounted here is one that run did not prove.
    assert not [line for line in unit if line.startswith(("InaccessiblePaths=", "ReadOnlyPaths="))], unit
    service = _selfcheck_service()
    assert (service["Description"], service["Type"], service["DynamicUser"], service["ProtectSystem"]) == (
        SELFCHECK["node_common_selfcheck_description"],
        "oneshot",
        "true",
        "strict",
    )


def test_the_selfcheck_installs_what_its_unit_runs_imports_and_reads_and_enables_the_timer_alone():
    service = _selfcheck_service()
    steps = _selfcheck_steps()
    for _, module, args in steps:
        if "src" in args and args["src"] != SELFCHECK["node_common_selfcheck_script"]:
            assert (ROLE / ("templates" if module == "ansible.builtin.template" else "files") / args["src"]).is_file(), args
    by_dest = {args["dest"]: (task, args) for task, _, args in steps if "dest" in args}
    assert by_dest[service["ExecStart"].split()[1]][1]["src"] == SELFCHECK["node_common_selfcheck_script"]
    env_task, env_args = by_dest[service["EnvironmentFile"]]
    assert (env_args["mode"], env_task["no_log"], env_task["diff"]) == ("0600", True, False)
    (made,) = [index for index, (_, module, _) in enumerate(steps) if module == "ansible.builtin.file"]
    (copied,) = [index for index, (_, _, args) in enumerate(steps) if args.get("src") == "zcrypto_selfcheck.py"]
    # DynamicUser runs the script as a user that owns nothing, so the module and its directory are world-readable.
    assert (steps[made][2]["path"], steps[made][2]["mode"], steps[copied][2]["dest"], steps[copied][2]["mode"]) == (
        "/usr/local/lib/zcrypto",
        "0755",
        "/usr/local/lib/zcrypto/zcrypto_selfcheck.py",
        "0644",
    )
    assert made < copied, "copy creates no parent directory"
    enabled = [args["name"] for _, module, args in steps if module == "ansible.builtin.systemd_service" and args.get("enabled")]
    assert enabled == ["probe-selfcheck.timer"], enabled


def test_the_script_lands_only_after_systemd_holds_the_unit_that_puts_its_module_on_the_path():
    steps = _selfcheck_steps()

    def at(found) -> int:
        (index,) = [index for index, (_, module, args) in enumerate(steps) if found(module, args)]
        return index

    copied = at(lambda _, args: args.get("src") == "zcrypto_selfcheck.py")
    env_file = at(lambda _, args: args.get("src") == "selfcheck.env.j2")
    unit = at(lambda _, args: args.get("src") == "selfcheck.service.j2")
    reload = at(lambda module, args: module == "ansible.builtin.systemd_service" and args == {"daemon_reload": True})
    script = at(lambda _, args: args.get("src") == SELFCHECK["node_common_selfcheck_script"])
    enable = at(lambda module, args: module == "ansible.builtin.systemd_service" and bool(args.get("enabled")))
    assert max(copied, env_file, unit) < reload < script < enable, [task["name"] for task, _, _ in steps]
    assert "when" not in steps[reload][0], "a reload gated on the unit's change skips the one a stopped converge still owes"


def test_the_selfcheck_env_file_holds_the_ping_url_alone():
    env_file = _selfcheck_render("selfcheck.env.j2")
    assert [line for line in env_file if line and not line.startswith("#")] == [
        "PROBE_SELFCHECK_HEALTHCHECK_URL=https://hc-ping.invalid/probe"
    ]


def test_the_selfcheck_timer_runs_the_unit_on_the_includes_calendar_and_never_catches_up():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string("\n".join(_selfcheck_render("selfcheck.timer.j2")))
    assert parser["Unit"]["Description"] == SELFCHECK["node_common_selfcheck_timer_description"]
    assert parser["Timer"]["OnCalendar"] == "*:0/1:07" and "Persistent" not in parser["Timer"]
    assert parser["Timer"]["Unit"] == "probe-selfcheck.service"


# --- sqlite-backup: a nightly VACUUM INTO through an optional runner, a copy out, a prune and a gauge --------------
BACKUP_SCRIPT = ROLE / "files/zcrypto-sqlite-backup.sh"
GAUGE = "zcrypto_sqlite_backup_last_success_timestamp_seconds"
BACKUP = {
    "node_common_role_name": "probe",
    "node_common_sqlite_backup_name": "probe",
    "node_common_sqlite_backup_db": "/data/probe.sqlite",
    "node_common_sqlite_backup_staging": "/data/backups",
    "node_common_sqlite_backup_dest": "/var/backups/probe",
    "node_common_sqlite_backup_runner": "docker compose -f /opt/probe/compose.yaml exec -T web",
    "node_common_sqlite_backup_copy": "docker compose -f /opt/probe/compose.yaml cp web:",
    "node_common_sqlite_backup_group": "probe-data",
    "node_common_sqlite_backup_textfile": "/var/lib/probe-textfile/sqlite-backup.prom",
}
STAMPED = re.compile(r"probe-(\d{4}-\d{2}-\d{2})T\d{6}Z\.sqlite")
# The line shape the fleet's Python logging and shell scripts write, which an Alloy parse stage levels.
ERROR_LINE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ERROR ")
PREVIOUS = f'{GAUGE}{{db="probe"}} 1\n'
# A root the host cannot hold, so what lies under it is reached through the docker stub's mapping alone.
INSIDE = "/nonexistent-probe-volume"
DOCKER_STUB = """#!/usr/bin/env python3
import json, os, shutil, sys

argv = sys.argv[1:]
with open(os.environ["DOCKER_STUB_LOG"], "a") as log:
    print(json.dumps(argv), file=log)
inside, outside = os.environ["DOCKER_STUB_INSIDE"], os.environ["DOCKER_STUB_OUTSIDE"]


def mapped(path):
    return outside + path[len(inside) :] if path.startswith(inside + "/") else path


if argv[:2] != ["compose", "-f"]:
    sys.exit(f"docker stub: not a compose call: {argv}")
if argv[3:6] == ["exec", "-T", "web"]:
    command = [mapped(arg) for arg in argv[6:]]
    os.execvp(command[0], command)
if argv[3:4] == ["cp"] and len(argv) == 6 and argv[4].startswith("web:"):
    shutil.copy(mapped(argv[4].removeprefix("web:")), argv[5])
    with open(os.environ["DOCKER_STUB_SEEN"], "w") as seen:
        json.dump(sorted(os.listdir(os.environ["DOCKER_STUB_WATCHED"])), seen)
    sys.exit(0)
sys.exit(f"docker stub: unexpected call: {argv}")
"""
# Records each call, then runs the real chgrp.
CHGRP_STUB = """#!/usr/bin/env python3
import json, os, sys

with open(os.environ["CHGRP_STUB_LOG"], "a") as log:
    print(json.dumps(sys.argv[1:]), file=log)
os.execv("REAL_CHGRP", ["REAL_CHGRP", *sys.argv[1:]])
"""
# Answers the script's one clock read, `date -u +%s`, with DATE_STUB_NOW, so a test sets the run's time; every other
# call reaches the real date.
DATE_STUB = """#!/usr/bin/env bash
if [ "$*" = "-u +%s" ]; then
  echo "$DATE_STUB_NOW"
else
  exec REAL_DATE "$@"
fi
"""
PARTIAL_COPY = """#!/usr/bin/env bash
head -c 100 -- "$1" >"$2${1##*/}"
exit 1
"""
SLOW_COPY = """#!/usr/bin/env bash
head -c 100 -- "$1" >"$2${1##*/}"
: >"$SLOW_STARTED"
until [ -e "$SLOW_RELEASE" ]; do sleep 0.05; done
exec cp -- "$@"
"""
# A copy that fails leaving a directory under the file's name, which `rm -f` cannot remove.
STUCK_COPY = """#!/usr/bin/env bash
mkdir -- "$2${1##*/}"
exit 1
"""
# sqlite3 shims, found ahead of the standard library on PYTHONPATH: a VACUUM that fails with its file and its journal on
# disk, one that holds there until it is stopped, and an import that holds there, before the VACUUM checks its name.
JOURNAL_SHIM = """def connect(*args, **kwargs):
    return Source()


class Source:
    def execute(self, sql, parameters):
        (staged,) = parameters
        for path in (staged, staged + "-journal"):
            open(path, "wb").close()
        raise OSError("the shim's VACUUM failed with its journal on disk")
"""
SLOW_SHIM = """import os, time


def connect(*args, **kwargs):
    return Source()


class Source:
    def execute(self, sql, parameters):
        (staged,) = parameters
        for path in (staged, staged + "-journal"):
            open(path, "wb").close()
        open(os.environ["SLOW_STARTED"], "wb").close()
        while True:
            time.sleep(0.05)
"""
IMPORT_SHIM = """import os, time

open(os.environ["SLOW_STARTED"], "wb").close()
while True:
    time.sleep(0.05)
"""


@dataclass(frozen=True)
class Node:
    db: Path
    staging: Path
    dest: Path
    prom: Path
    bin: Path


@pytest.fixture
def node(tmp_path):
    volume = tmp_path / "volume"
    for directory in (volume, tmp_path / "textfile", tmp_path / "bin"):
        directory.mkdir()
    live = sqlite3.connect(volume / "probe.sqlite")
    # Rows left in the -wal by a connection held open across the run, as the live service holds its own.
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("CREATE TABLE checks (name TEXT PRIMARY KEY, period INTEGER)")
    live.executemany("INSERT INTO checks VALUES (?, ?)", [(f"check-{i}", 60 * i) for i in range(12)])
    live.commit()
    yield Node(
        db=volume / "probe.sqlite",
        staging=volume / "backups",
        dest=tmp_path / "host/backups",
        prom=tmp_path / "textfile/sqlite-backup.prom",
        bin=tmp_path / "bin",
    )
    live.close()


def _argv(node: Node, *, db=None, staging=None, keep_days="14") -> list[str]:
    return ["probe", str(db or node.db), str(staging or node.staging), str(node.dest), keep_days, str(node.prom)]


def _environment(node: Node, *, runner="", copy="", group="", env=None, now=None) -> dict[str, str]:
    path = f"{node.bin}{os.pathsep}{os.environ['PATH']}"
    prefixes = {"SQLITE_BACKUP_RUNNER": runner, "SQLITE_BACKUP_COPY": copy, "SQLITE_BACKUP_GROUP": group}
    environment = os.environ | {"PATH": path} | prefixes | (env or {})
    if now is not None:
        _stub(node, "date", DATE_STUB.replace("REAL_DATE", shutil.which("date")))
        environment["DATE_STUB_NOW"] = str(now)
    return environment


def _run(node: Node, argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    environment = _environment(node, **kwargs)
    return subprocess.run(["bash", str(BACKUP_SCRIPT), *argv], capture_output=True, text=True, env=environment, check=False)


@pytest.fixture
def background():
    runs: list[subprocess.Popen[str]] = []
    yield runs
    for run in runs:
        if run.poll() is None:
            os.killpg(run.pid, signal.SIGKILL)
            run.wait()


def _start(node: Node, background: list, **kwargs) -> subprocess.Popen[str]:
    # A session of its own, so a signal reaches the script and its children together, as a unit's stop does.
    run = subprocess.Popen(
        ["bash", str(BACKUP_SCRIPT), *_argv(node)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_environment(node, **kwargs),
        start_new_session=True,
    )
    background.append(run)
    return run


def _wait_for(path: Path, run: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while not path.exists():
        assert run.poll() is None, run.communicate()
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.02)


def _backup(node: Node, *, db=None, staging=None, keep_days="14", **kwargs) -> subprocess.CompletedProcess[str]:
    return _run(node, _argv(node, db=db, staging=staging, keep_days=keep_days), **kwargs)


def _content(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",), path
        return list(connection.iterdump())


def _stub(node: Node, name: str, text: str) -> None:
    stub = node.bin / name
    stub.write_text(text)
    stub.chmod(0o755)


def _shim(node: Node, name: str, text: str) -> Path:
    shim = node.bin.parent / name
    shim.mkdir()
    (shim / "sqlite3.py").write_text(text)
    return shim


def _today() -> date:
    return datetime.now(UTC).date()


def _noon(today: date) -> int:
    return int(datetime(today.year, today.month, today.day, 12, tzinfo=UTC).timestamp())


def _named(today: date, days: int, name: str = "probe") -> str:
    return f"{name}-{today - timedelta(days=days):%Y-%m-%d}T024700Z.sqlite"


def _written_by_the_run(directory: Path, seeded=frozenset()) -> list[Path]:
    return sorted(p for p in directory.iterdir() if STAMPED.fullmatch(p.name) and p.name not in seeded)


def _through_docker(node: Node) -> list[list[str]]:
    _stub(node, "docker", DOCKER_STUB)
    env = {
        "DOCKER_STUB_LOG": str(node.bin / "docker.log"),
        "DOCKER_STUB_INSIDE": INSIDE,
        "DOCKER_STUB_OUTSIDE": str(node.db.parent),
        "DOCKER_STUB_WATCHED": str(node.dest),
        "DOCKER_STUB_SEEN": str(node.bin / "seen.json"),
    }
    result = _backup(
        node,
        db=f"{INSIDE}/probe.sqlite",
        staging=f"{INSIDE}/backups",
        runner=BACKUP["node_common_sqlite_backup_runner"],
        copy=BACKUP["node_common_sqlite_backup_copy"],
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in (node.bin / "docker.log").read_text().splitlines()]


def _execs(calls: list[list[str]]) -> list[list[str]]:
    return [call[6:] for call in calls if call[3:6] == ["exec", "-T", "web"]]


def test_a_backup_is_a_valid_copy_of_the_source_staged_and_copied_into_a_new_0700_destination(node):
    assert not node.staging.exists() and not node.dest.exists()
    result = _backup(node)
    assert result.returncode == 0, result.stderr
    (staged,) = node.staging.iterdir()
    assert _written_by_the_run(node.staging) == [staged], staged.name
    assert [p.name for p in node.dest.iterdir()] == [staged.name]
    assert _content(staged) == _content(node.db) == _content(node.dest / staged.name)
    assert len(_content(staged)) > 12, "the rows the live connection left in the -wal are missing"
    assert stat.S_IMODE(node.dest.stat().st_mode) == 0o700


def test_a_group_holds_the_destination_at_0750_and_every_file_in_it_at_0640_an_earlier_runs_among_them(node):
    gid = os.getgid()
    group = grp.getgrgid(gid).gr_name
    _stub(node, "chgrp", CHGRP_STUB.replace("REAL_CHGRP", shutil.which("chgrp")))
    node.dest.mkdir(parents=True)
    node.dest.chmod(0o700)
    earlier = node.dest / _named(_today(), 1)
    earlier.write_bytes(b"")
    earlier.chmod(0o600)
    result = _backup(node, group=group, env={"CHGRP_STUB_LOG": str(node.bin / "chgrp.log")})
    assert result.returncode == 0, result.stderr
    (written,) = _written_by_the_run(node.dest, {earlier.name})
    assert (stat.S_IMODE(node.dest.stat().st_mode), node.dest.stat().st_gid) == (0o750, gid)
    held = {path.name: (stat.S_IMODE(path.stat().st_mode), path.stat().st_gid) for path in node.dest.iterdir()}
    assert held == {earlier.name: (0o640, gid), written.name: (0o640, gid)}
    # The files already carry the test user's group, so the gids above hold without a chgrp: its calls are the proof.
    calls = [json.loads(line) for line in (node.bin / "chgrp.log").read_text().splitlines()]
    assert all(call[:2] == ["--", group] for call in calls), calls
    paths = [path for call in calls for path in call[2:]]
    assert paths[0] == f"{node.dest}.incoming/{written.name}" and paths[-1] == str(node.dest), paths
    assert sorted(paths[1:-1]) == sorted([str(earlier), str(node.dest / written.name)]), paths


def test_the_prune_reads_the_date_in_the_name_and_keeps_the_keep_days_in_both_directories(node):
    today = _today()
    seeded = {_named(today, 15), _named(today, 14), _named(today, 13), _named(today, 15, name="other")}
    old = time.time() - 30 * 86400
    for directory in (node.staging, node.dest):
        directory.mkdir(parents=True)
        for name in seeded:
            (directory / name).write_bytes(b"")
        # An mtime past the keep-days on a file whose name is inside them.
        os.utime(directory / _named(today, 13), (old, old))
    # The run's clock is the seeded names' date, so the boundary file stays fourteen days old across midnight UTC.
    result = _backup(node, now=_noon(today))
    assert result.returncode == 0, result.stderr
    for directory in (node.staging, node.dest):
        assert [p.name for p in _written_by_the_run(directory, seeded)] == [f"probe-{today:%Y-%m-%d}T120000Z.sqlite"]
        left = {p.name for p in directory.iterdir()} & seeded
        assert left == {_named(today, 14), _named(today, 13), _named(today, 15, name="other")}, directory


def test_the_prune_removes_a_file_past_the_keep_days_left_in_the_sibling(node):
    today = _today()
    incoming = Path(f"{node.dest}.incoming")
    incoming.mkdir(parents=True)
    for days in (15, 13):
        (incoming / _named(today, days)).write_bytes(b"")
    result = _backup(node, now=_noon(today))
    assert result.returncode == 0, result.stderr
    assert [p.name for p in incoming.iterdir()] == [_named(today, 13)]


def test_the_gauge_carries_the_backups_time_under_its_name(node):
    before = int(time.time())
    assert _backup(node).returncode == 0
    lines = node.prom.read_text().splitlines()
    assert f"# TYPE {GAUGE} gauge" in lines
    ((series, value),) = [line.rsplit(" ", 1) for line in lines if not line.startswith("#")]
    assert series == f'{GAUGE}{{db="probe"}}'
    assert before <= int(value) <= time.time()


def test_the_gauge_is_renamed_into_place_and_leaves_no_temporary(node):
    node.prom.write_text(PREVIOUS)
    first = node.prom.stat().st_ino
    assert _backup(node).returncode == 0
    assert node.prom.stat().st_ino != first, "the gauge was rewritten in place, so the collector can read half a file"
    assert sorted(p.name for p in node.prom.parent.iterdir()) == [node.prom.name, "zcrypto-sqlite-backup-probe.lock"]


def test_the_gauge_is_readable_by_the_non_root_collector(node):
    assert _backup(node).returncode == 0
    assert stat.S_IMODE(node.prom.stat().st_mode) == 0o644


def test_a_runner_that_fails_leaves_the_gauge_and_exits_non_zero(node):
    node.prom.write_text(PREVIOUS)
    result = _backup(node, runner="false")
    assert result.returncode != 0
    assert node.prom.read_text() == PREVIOUS
    assert any(ERROR_LINE.match(line) for line in result.stderr.splitlines()), result.stderr


def test_a_copy_that_fails_part_way_after_a_clean_vacuum_leaves_the_gauge_and_no_file_in_the_destination(node):
    _stub(node, "partial-cp", PARTIAL_COPY)
    node.prom.write_text(PREVIOUS)
    result = _backup(node, copy="partial-cp ")
    assert result.returncode != 0
    (staged,) = _written_by_the_run(node.staging)
    assert _content(staged) == _content(node.db)
    assert list(node.dest.iterdir()) == [] and list(Path(f"{node.dest}.incoming").iterdir()) == []
    assert node.prom.read_text() == PREVIOUS
    assert any(ERROR_LINE.match(line) for line in result.stderr.splitlines()), result.stderr


def test_a_database_path_naming_no_file_fails_and_creates_none(node):
    missing = node.db.parent / "missing.sqlite"
    result = _backup(node, db=missing)
    assert result.returncode != 0
    assert not missing.exists(), "the backup created an empty database where it looked for one"
    assert not node.prom.exists()
    assert any(ERROR_LINE.match(line) for line in result.stderr.splitlines()), result.stderr


def test_a_vacuum_that_fails_part_way_leaves_no_file_under_a_backups_name(node):
    broken = node.db.parent / "broken.sqlite"
    with closing(sqlite3.connect(broken)) as connection:
        connection.execute("CREATE TABLE pages (body TEXT)")
        connection.executemany("INSERT INTO pages VALUES (?)", [("x" * 200,) for _ in range(400)])
        connection.commit()
    # A page past the schema overwritten, so the VACUUM fails on reading it after it has created its file.
    with broken.open("r+b") as handle:
        handle.seek(4 * 4096)
        handle.write(b"\xff" * 4096)
    node.prom.write_text(PREVIOUS)
    result = _backup(node, db=broken)
    assert result.returncode != 0
    assert "database disk image is malformed" in result.stderr, result.stderr
    assert list(node.staging.iterdir()) == []
    assert node.prom.read_text() == PREVIOUS


def test_a_vacuum_that_fails_with_its_journal_on_disk_leaves_neither(node):
    shim = _shim(node, "journal-shim", JOURNAL_SHIM)
    result = _backup(node, runner=f"env PYTHONPATH={shim}")
    assert result.returncode == 1, result.stderr
    assert "the shim's VACUUM failed with its journal on disk" in result.stderr, result.stderr
    assert list(node.staging.iterdir()) == []


def test_a_copy_whose_file_cannot_be_removed_still_fails_at_error(node):
    _stub(node, "stuck-cp", STUCK_COPY)
    result = _backup(node, copy="stuck-cp ")
    assert result.returncode == 1, result.stderr
    assert any(ERROR_LINE.match(line) and "copying " in line for line in result.stderr.splitlines()), result.stderr


def test_a_run_while_another_holds_the_lock_fails_and_touches_nothing(node, background):
    _stub(node, "slow-cp", SLOW_COPY)
    started, release = node.bin / "started", node.bin / "release"
    today = _today()
    first = _start(
        node,
        background,
        copy="slow-cp ",
        env={"SLOW_STARTED": str(started), "SLOW_RELEASE": str(release)},
        now=_noon(today),
    )
    _wait_for(started, first)
    second = _backup(node, now=_noon(today) + 1)
    release.touch()
    _, first_stderr = first.communicate(timeout=30)
    assert first.returncode == 0, first_stderr
    assert second.returncode == 1, second.stderr
    assert any(ERROR_LINE.match(line) and " holds " in line for line in second.stderr.splitlines()), second.stderr
    expected = [f"probe-{today:%Y-%m-%d}T120000Z.sqlite"]
    assert [p.name for p in _written_by_the_run(node.staging)] == [p.name for p in node.dest.iterdir()] == expected
    assert _content(node.dest / expected[0]) == _content(node.db)


STOPS = pytest.mark.parametrize(("signum", "rc"), [(signal.SIGTERM, 143), (signal.SIGINT, 130)], ids=["SIGTERM", "SIGINT"])


def _stopped_part_way(node: Node, run: subprocess.Popen[str], started: Path, signum: signal.Signals, rc: int) -> None:
    _wait_for(started, run)
    os.killpg(run.pid, signum)
    _, stderr = run.communicate(timeout=30)
    assert run.returncode == rc, stderr
    assert any(ERROR_LINE.match(line) and f"stopped by {signum.name}" in line for line in stderr.splitlines()), stderr
    for directory in (node.staging, node.dest, Path(f"{node.dest}.incoming")):
        left = sorted(p.name for p in directory.iterdir()) if directory.exists() else []
        assert not [name for name in left if STAMPED.fullmatch(name) or name.endswith("-journal")], (directory, left)
    assert node.prom.read_text() == PREVIOUS


@STOPS
def test_a_run_stopped_during_a_slow_copy_leaves_no_file_under_a_backups_name(node, background, signum, rc):
    _stub(node, "slow-cp", SLOW_COPY)
    started = node.bin / "started"
    node.prom.write_text(PREVIOUS)
    env = {"SLOW_STARTED": str(started), "SLOW_RELEASE": str(node.bin / "never")}
    _stopped_part_way(node, _start(node, background, copy="slow-cp ", env=env), started, signum, rc)


@STOPS
def test_a_run_stopped_during_a_slow_vacuum_leaves_no_file_under_a_backups_name(node, background, signum, rc):
    shim = _shim(node, "slow-shim", SLOW_SHIM)
    started = node.bin / "started"
    node.prom.write_text(PREVIOUS)
    env = {"SLOW_STARTED": str(started), "PYTHONPATH": str(shim)}
    _stopped_part_way(node, _start(node, background, env=env), started, signum, rc)


@pytest.mark.parametrize("taken", ["staged", "journal", "sibling"])
def test_a_name_an_earlier_run_of_the_same_second_left_fails_the_run_before_a_stop_could_remove_it(node, background, taken):
    today = _today()
    name = f"probe-{today:%Y-%m-%d}T120000Z.sqlite"
    incoming = Path(f"{node.dest}.incoming")
    earlier = {"staged": node.staging / name, "journal": node.staging / f"{name}-journal", "sibling": incoming / name}[taken]
    earlier.parent.mkdir(parents=True)
    earlier.write_bytes(b"an earlier run's")
    started = node.bin / "started"
    env = {"SLOW_STARTED": str(started), "PYTHONPATH": str(_shim(node, "import-shim", IMPORT_SHIM))}
    run = _start(node, background, env=env, now=_noon(today))
    deadline = time.monotonic() + 30
    while run.poll() is None and not started.exists():
        assert time.monotonic() < deadline, "the run neither ended nor reached its VACUUM"
        time.sleep(0.02)
    if run.poll() is None:
        os.killpg(run.pid, signal.SIGTERM)
    _, stderr = run.communicate(timeout=30)
    assert earlier.read_bytes() == b"an earlier run's"
    assert (run.returncode, started.exists()) == (1, False), stderr
    assert any(ERROR_LINE.match(line) and f"{earlier} already exists" in line for line in stderr.splitlines()), stderr


def test_a_file_already_under_the_runs_name_fails_the_run_and_stays(node):
    today = _today()
    node.staging.mkdir()
    earlier = node.staging / f"probe-{today:%Y-%m-%d}T120000Z.sqlite"
    earlier.write_bytes(b"a backup this run did not write")
    result = _backup(node, now=_noon(today))
    assert result.returncode != 0
    assert earlier.read_bytes() == b"a backup this run did not write"


def test_two_runs_on_one_date_write_two_files(node):
    noon = _noon(_today())
    for now in (noon, noon + 1):
        result = _backup(node, now=now)
        assert result.returncode == 0, result.stderr
    staged = [p.name for p in _written_by_the_run(node.staging)]
    assert len(staged) == 2 and len({STAMPED.fullmatch(name).group(1) for name in staged}) == 1, staged
    assert sorted(p.name for p in node.dest.iterdir()) == staged


def test_a_staging_path_carrying_a_quote_is_backed_up_as_any_other(node):
    staging = node.db.parent / "o'clock"
    result = _backup(node, staging=staging)
    assert result.returncode == 0, result.stderr
    (staged,) = _written_by_the_run(staging)
    assert _content(staged) == _content(node.db) == _content(node.dest / staged.name)


def test_the_runner_runs_the_vacuum_with_both_paths_as_arguments_and_neither_in_its_program(node):
    calls = _through_docker(node)
    (staged,) = _written_by_the_run(node.staging)
    ((interpreter, flag, program, *paths),) = [args for args in _execs(calls) if f"{INSIDE}/probe.sqlite" in args]
    assert (interpreter, flag, paths) == ("python3", "-c", [f"{INSIDE}/probe.sqlite", f"{INSIDE}/backups/{staged.name}"])
    assert INSIDE not in program
    assert _content(staged) == _content(node.db)


def test_the_staging_prune_runs_through_the_runner(node):
    # A day either side of the boundary, so a run across midnight UTC prunes and keeps the same two.
    today = _today()
    node.staging.mkdir()
    for days in (15, 13):
        (node.staging / _named(today, days)).write_bytes(b"")
    calls = _through_docker(node)
    assert not (node.staging / _named(today, 15)).exists()
    assert (node.staging / _named(today, 13)).exists()
    assert len([args for args in _execs(calls) if f"{INSIDE}/backups" in args]) == 1, calls


def test_the_copy_prefix_takes_the_staged_path_on_its_last_word(node):
    calls = _through_docker(node)
    (staged,) = _written_by_the_run(node.staging)
    (copy,) = [call for call in calls if call[3:4] == ["cp"]]
    assert copy[3:] == ["cp", f"web:{INSIDE}/backups/{staged.name}", f"{node.dest}.incoming/"]
    assert _content(node.dest / staged.name) == _content(node.db)


def test_the_copy_is_written_beside_the_destination_and_renamed_into_it_whole(node):
    calls = _through_docker(node)
    (staged,) = _written_by_the_run(node.staging)
    (copy,) = [call for call in calls if call[3:4] == ["cp"]]
    incoming = Path(f"{node.dest}.incoming")
    assert copy[5] == f"{incoming}/"
    assert json.loads((node.bin / "seen.json").read_text()) == [], "the destination listed the run's file while it was written"
    assert [p.name for p in node.dest.iterdir()] == [staged.name] and list(incoming.iterdir()) == []


@pytest.mark.parametrize(
    "malform",
    [
        lambda argv: argv[:5],
        lambda argv: [*argv, "surplus"],
        lambda argv: ["../probe", *argv[1:]],
        lambda argv: [*argv[:2], "", *argv[3:]],
        lambda argv: [*argv[:4], "fourteen", argv[5]],
        lambda argv: [*argv[:4], "-1", argv[5]],
    ],
    ids=[
        "an argument missing",
        "one too many",
        "a name that is not one word",
        "an empty path",
        "keep-days a word",
        "keep-days negative",
    ],
)
def test_a_malformed_invocation_is_refused_before_anything_is_written(node, malform):
    result = _run(node, malform(_argv(node)))
    assert result.returncode == 2, result.stderr
    (line,) = result.stderr.splitlines()
    assert ERROR_LINE.match(line) and "- usage: zcrypto-sqlite-backup <name> " in line, line
    assert not node.staging.exists() and not node.dest.exists() and not node.prom.exists()


def _backup_render(name: str) -> list[str]:
    return role_render.render(ROLE, name, {}, **BACKUP).splitlines()


def _unit_environment(unit: list[str]) -> dict[str, str]:
    assignments = [shlex.split(line.removeprefix("Environment=")) for line in unit if line.startswith("Environment=")]
    assert all(len(words) == 1 for words in assignments), f"an Environment= line not quoted whole splits at its spaces: {unit}"
    return dict(words[0].split("=", 1) for words in assignments)


def test_the_backup_unit_runs_the_script_as_root_over_the_includes_arguments_its_two_prefixes_and_its_group():
    unit = _backup_render("sqlite-backup.service.j2")
    assert unit[0].startswith("# Rendered by the `probe` Ansible role at /etc/systemd/system/zcrypto-sqlite-backup.service;")
    (exec_start,) = [line.removeprefix("ExecStart=").split() for line in unit if line.startswith("ExecStart=")]
    assert exec_start == [
        "/usr/local/sbin/zcrypto-sqlite-backup",
        "probe",
        "/data/probe.sqlite",
        "/data/backups",
        "/var/backups/probe",
        "14",
        "/var/lib/probe-textfile/sqlite-backup.prom",
    ]
    assert _unit_environment(unit) == {
        "SQLITE_BACKUP_RUNNER": BACKUP["node_common_sqlite_backup_runner"],
        "SQLITE_BACKUP_COPY": BACKUP["node_common_sqlite_backup_copy"],
        "SQLITE_BACKUP_GROUP": BACKUP["node_common_sqlite_backup_group"],
    }
    ungrouped = {k: v for k, v in BACKUP.items() if k != "node_common_sqlite_backup_group"}
    default = role_render.render(ROLE, "sqlite-backup.service.j2", {}, **ungrouped).splitlines()
    assert _unit_environment(default)["SQLITE_BACKUP_GROUP"] == "", "an include naming no group holds its copies root-only"
    keys = {line.split("=", 1)[0] for line in unit if "=" in line and not line.startswith("#")}
    assert not keys & {"User", "DynamicUser", "ProtectSystem"}, keys


def test_the_backup_timer_runs_the_unit_nightly_on_the_default_calendar_and_never_catches_up():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string("\n".join(_backup_render("sqlite-backup.timer.j2")))
    assert parser["Timer"]["OnCalendar"] == "*-*-* 02:47:00" and "Persistent" not in parser["Timer"]
    assert parser["Timer"]["Unit"] == "zcrypto-sqlite-backup.service"
    assert parser["Install"]["WantedBy"] == "timers.target"


def _backup_steps() -> list[tuple[dict, str, dict]]:
    steps = []
    for task in load_tasks(ROLE / "tasks/sqlite-backup.yml"):
        ((module, args),) = [(key, value) for key, value in task.items() if isinstance(value, dict)]
        steps.append((task, module, {k: role_render.resolve(ROLE, v, {}, **BACKUP) for k, v in args.items()}))
    return steps


def test_the_backup_installs_what_its_unit_runs_executable_and_enables_the_timer_alone():
    unit = _backup_render("sqlite-backup.service.j2")
    (binary,) = [line.removeprefix("ExecStart=").split()[0] for line in unit if line.startswith("ExecStart=")]
    steps = _backup_steps()
    for _, module, args in steps:
        if "src" in args:
            assert (ROLE / ("templates" if module == "ansible.builtin.template" else "files") / args["src"]).is_file(), args
    by_dest = {args["dest"]: args for _, _, args in steps if "dest" in args}
    assert (by_dest[binary]["src"], by_dest[binary]["mode"]) == ("zcrypto-sqlite-backup.sh", "0755")
    assert by_dest["/etc/systemd/system/zcrypto-sqlite-backup.service"]["src"] == "sqlite-backup.service.j2"
    assert by_dest["/etc/systemd/system/zcrypto-sqlite-backup.timer"]["src"] == "sqlite-backup.timer.j2"
    enabled = [args["name"] for _, module, args in steps if module == "ansible.builtin.systemd_service" and args.get("enabled")]
    assert enabled == ["zcrypto-sqlite-backup.timer"], enabled


def test_the_backup_script_lands_only_after_systemd_holds_the_unit_that_passes_its_arguments():
    steps = _backup_steps()

    def at(found) -> int:
        (index,) = [index for index, (_, module, args) in enumerate(steps) if found(module, args)]
        return index

    unit = at(lambda _, args: args.get("src") == "sqlite-backup.service.j2")
    reload = at(lambda module, args: module == "ansible.builtin.systemd_service" and args == {"daemon_reload": True})
    script = at(lambda _, args: args.get("src") == "zcrypto-sqlite-backup.sh")
    timer = at(lambda _, args: args.get("src") == "sqlite-backup.timer.j2")
    enable = at(lambda module, args: module == "ansible.builtin.systemd_service" and bool(args.get("enabled")))
    assert unit < reload < script < enable and timer < enable, [task["name"] for task, _, _ in steps]
    assert "when" not in steps[reload][0], "a reload gated on the unit's change skips the one a stopped converge still owes"


@pytest.mark.parametrize(
    ("check", "changed", "runs"),
    [(True, True, False), (True, False, True), (False, True, True)],
    ids=["a first-install preview", "an established node's preview", "a real converge"],
)
def test_a_first_install_preview_skips_the_backup_timer_it_never_wrote(check, changed, runs):
    steps = _backup_steps()
    (install,) = [task for task, _, args in steps if args.get("src") == "sqlite-backup.timer.j2"]
    (enable,) = [task for task, module, args in steps if module == "ansible.builtin.systemd_service" and args.get("enabled")]
    variables = {"ansible_check_mode": check, install["register"]: {"changed": changed}}
    assert truthy(when_conditions(enable), variables) is runs
