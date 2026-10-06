from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from tests import role_render, selfcheck_driver
from tests.test_infra_converge_guards import load_tasks

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/hc"
NODE_COMMON = REPO / "infra/ansible/roles/node_common"
SCRIPT = ROLE / "files/zcrypto-hc-selfcheck.py"
SHARED = NODE_COMMON / "files/zcrypto_selfcheck.py"
SELFCHECK_TASKS = NODE_COMMON / "tasks/selfcheck.yml"
selfcheck = selfcheck_driver.load(SCRIPT, SHARED)

STATUS = "http://127.0.0.1:8000/api/v3/status/"
HOST = "zcrypto-hc.zhaow.me"
PING = "https://zcrypto-hc.zhaow.me/ping/" + "k" * 22 + "/zcrypto-hc"
ENV = {"HC_SELFCHECK_STATUS": STATUS, "HC_SELFCHECK_HOST": HOST, "HC_SELFCHECK_HEALTHCHECK_URL": PING}


def _refused(code: int):
    def answer(request):
        raise urllib.error.HTTPError(request.full_url, code, "refused", None, io.BytesIO(f"<h1>({code})</h1>".encode()))

    return answer


# Django refuses a request whose Host is outside the clone's ALLOWED_HOSTS with a 400.
def _status(body: str = "OK"):
    def answer(request):
        return body if request.get_header("Host") == HOST else _refused(400)(request)

    return answer


def _run(*, status=None, ping="OK", env=ENV, broken=()):
    bodies = {STATUS: _status() if status is None else status, PING: ping}
    return selfcheck_driver.run(selfcheck, env, bodies, broken=broken)


def test_a_clone_whose_web_answers_pings_and_says_what_it_read():
    rc, asked, out = _run()
    assert rc == 0 and asked == [STATUS, PING]
    assert out == "selfcheck: web=ok (answered OK) -> pinged"


@pytest.mark.parametrize(
    ("fault", "said"),
    [
        ({"status": _refused(500)}, "web=FAIL (answered 500)"),
        ({"status": _status(body="Starting")}, "web=FAIL (answered 'Starting')"),
        ({"status": _status(body="")}, "web=FAIL (answered '')"),
        ({"env": {**ENV, "HC_SELFCHECK_HOST": "localhost"}}, "web=FAIL (answered 400)"),
        ({"broken": (STATUS,)}, "web=FAIL (unreadable: URLError)"),
    ],
    ids=["status 500", "status 200 not OK", "status 200 empty", "another host", "clone down"],
)
def test_a_status_read_that_fails_sends_no_ping_and_still_exits_clean(fault, said):
    rc, asked, out = _run(**fault)
    assert rc == 0, "a failing unit every five minutes would be the noise; the missing ping is the page"
    assert asked == [STATUS]
    assert out == f"selfcheck: {said} -> not pinging"


def test_with_no_ping_url_a_clone_whose_web_answers_pings_nothing():
    rc, asked, out = _run(env={**ENV, "HC_SELFCHECK_HEALTHCHECK_URL": ""})
    assert rc == 0 and asked == [STATUS] and out.endswith("-> healthy, and no ping URL is set")


def test_a_ping_the_clone_does_not_store_is_reported_and_the_unit_still_exits_clean():
    rc, asked, out = _run(ping=_refused(500))
    assert rc == 0 and asked == [STATUS, PING] and out == "selfcheck: web=ok (answered OK) -> ping failed: HTTPError"


def test_the_ping_url_never_reaches_the_output():
    for kwargs in ({}, {"ping": _refused(500)}, {"broken": (PING,)}, {"status": _refused(500)}):
        assert PING not in _run(**kwargs)[2]


def test_a_hand_run_without_the_units_pythonpath_imports_the_module_from_where_the_role_installs_it(tmp_path):
    (made,) = [task["ansible.builtin.file"]["path"] for task in load_tasks(SELFCHECK_TASKS) if "ansible.builtin.file" in task]
    (tmp_path / "copy").mkdir()
    shutil.copy(SHARED, tmp_path / "copy")
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"} | {
        "HC_SELFCHECK_STATUS": (tmp_path / "absent").as_uri(),
        "HC_SELFCHECK_HOST": HOST,
        "HC_SELFCHECK_HEALTHCHECK_URL": "",
    }
    run = subprocess.run(
        [sys.executable, "-c", selfcheck_driver.HAND_RUN, str(SCRIPT), made, str(tmp_path / "copy")],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (run.returncode, run.stdout, run.stderr) == (0, "selfcheck: web=FAIL (unreadable: URLError) -> not pinging\n", "")


# --- the unit and its environment file: node_common's, rendered through the role's include ------------------------
def _scope(**extra) -> dict:
    # The include's vars as the play resolves them: over the role's own defaults and node_common's.
    (include,) = [
        task
        for task in load_tasks(ROLE / "tasks/main.yml")
        if task.get("ansible.builtin.include_role") == {"name": "node_common", "tasks_from": "selfcheck"}
    ]
    return role_render.variables(ROLE, {}) | role_render.trusted(include["vars"]) | extra


def _render(name: str, **extra) -> str:
    return role_render.render(NODE_COMMON, name, {}, **_scope(**extra))


def test_the_unit_and_its_environment_file_set_every_name_the_script_reads():
    read = set(re.findall(r'(?:env(?:\.get\(|\[)|ping_var=)"(HC_SELFCHECK_[A-Z_]+)"', SCRIPT.read_text()))
    unit = _render("selfcheck.service.j2")
    in_unit = dict(line.removeprefix("Environment=").split("=", 1) for line in unit.splitlines() if line.startswith("Environment="))
    assert in_unit == {"HC_SELFCHECK_STATUS": STATUS, "HC_SELFCHECK_HOST": HOST, "PYTHONPATH": "/usr/local/lib/zcrypto"}
    env_file = _render("selfcheck.env.j2", hc_selfcheck_healthcheck_url=PING)
    in_file = dict(line.split("=", 1) for line in env_file.splitlines() if line and not line.startswith("#"))
    assert in_file == {"HC_SELFCHECK_HEALTHCHECK_URL": PING}
    # Python reads PYTHONPATH to import the shared loop; the script never does.
    assert read == (set(in_unit) - {"PYTHONPATH"}) | set(in_file), (
        "a name the script reads that nothing sets is a KeyError on every run"
    )
