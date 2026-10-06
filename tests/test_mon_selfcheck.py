from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests import role_render, selfcheck_driver
from tests.test_infra_converge_guards import find_task, load_tasks, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/mon"
NODE_COMMON = REPO / "infra/ansible/roles/node_common"
SCRIPT = ROLE / "files/zcrypto-mon-selfcheck.py"
SHARED = NODE_COMMON / "files/zcrypto_selfcheck.py"
SELFCHECK_TASKS = NODE_COMMON / "tasks/selfcheck.yml"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
selfcheck = selfcheck_driver.load(SCRIPT, SHARED)

NOW = 1_790_000_000.0
PING = "https://hc-ping.invalid/abc"
ENV = {
    "MON_SELFCHECK_GRAFANA": "http://127.0.0.1:3000",
    "MON_SELFCHECK_PROMETHEUS": "http://127.0.0.1:9090",
    "MON_SELFCHECK_LOKI": "http://127.0.0.1:3100",
    "MON_SELFCHECK_HEALTHCHECK_URL": PING,
}


def _metrics(tick_age: float | None = 4.0, scheduled: int | None = 114) -> str:
    lines = ["# TYPE grafana_alerting_ticker_last_consumed_tick_timestamp_seconds gauge"]
    if tick_age is not None:
        lines.append(f"grafana_alerting_ticker_last_consumed_tick_timestamp_seconds {NOW - tick_age!r}")
    if scheduled is not None:
        lines.append(f"grafana_alerting_schedule_alert_rules {scheduled}")
        lines.append("grafana_alerting_schedule_alert_rules_hash 1.4695981039346655e+19")
    return "\n".join(lines) + "\n"


def _fleet(hosts: int | None) -> str:
    result = [] if hosts is None else [{"metric": {}, "value": [NOW, str(hosts)]}]
    return json.dumps({"status": "success", "data": {"resultType": "vector", "result": result}})


def _run(*, metrics=None, fleet=8, loki="ready\n", refused=None, env=ENV, broken=()):
    """`refused` is Loki's own not-ready answer: a 503 whose body is the reason."""
    bodies = {
        "http://127.0.0.1:3000/metrics": _metrics() if metrics is None else metrics,
        "http://127.0.0.1:9090/api/v1/query": _fleet(fleet),
        "http://127.0.0.1:3100/ready": loki,
        PING: "OK",
    }
    refused = None if refused is None else ("http://127.0.0.1:3100/ready", refused)
    return selfcheck_driver.run(selfcheck, env, bodies, broken=broken, refused=refused, now=NOW)


def test_a_node_doing_its_job_pings_and_says_what_it_read():
    rc, asked, out = _run()
    assert rc == 0 and asked[-1] == PING
    assert out == (
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> pinged"
    )
    query = next(url for url in asked if url.startswith("http://127.0.0.1:9090/"))
    assert "query=count%28count+by+%28host%29+%28up%7Bhost%21%3D%22zcrypto-mon%22%7D%29%29" in query


@pytest.mark.parametrize(
    ("fault", "said"),
    [
        ({"metrics": _metrics(tick_age=61.0)}, "rules=FAIL (the scheduler's last tick is 61 s old)"),
        (
            {"metrics": _metrics(tick_age=None)},
            "rules=FAIL (Grafana's /metrics carries no grafana_alerting_ticker_last_consumed_tick_timestamp_seconds)",
        ),
        ({"metrics": _metrics(scheduled=None)}, "rules=FAIL (Grafana's /metrics carries no grafana_alerting_schedule_alert_rules)"),
        ({"metrics": _metrics(scheduled=0)}, "rules=FAIL (no rule is scheduled)"),
        ({"fleet": None}, "fleet=FAIL (no fleet host has a sample in the last five minutes)"),
        ({"fleet": 0}, "fleet=FAIL (no fleet host has a sample in the last five minutes)"),
        (
            {"refused": "Ingester not ready: waiting for 15s after being ready\n"},
            "loki=FAIL (answered 503: 'Ingester not ready: waiting for 15s after being ready')",
        ),
        ({"loki": "starting\n"}, "loki=FAIL (answered 'starting')"),
        ({"broken": ("http://127.0.0.1:3000/metrics",)}, "rules=FAIL (unreadable: URLError)"),
        ({"broken": ("http://127.0.0.1:9090/api/v1/query",)}, "fleet=FAIL (unreadable: URLError)"),
        ({"broken": ("http://127.0.0.1:3100/ready",)}, "loki=FAIL (unreadable: URLError)"),
    ],
    ids=[
        "tick stale",
        "no tick",
        "no scheduled count",
        "no rules",
        "no fleet series",
        "zero fleet hosts",
        "loki not ready",
        "loki answering something else",
        "grafana down",
        "prometheus down",
        "loki down",
    ],
)
def test_one_failing_check_sends_no_ping_and_still_exits_clean(fault, said):
    rc, asked, out = _run(**fault)
    assert rc == 0, "a failing unit every five minutes would be the noise; the missing ping is the page"
    assert PING not in asked
    assert said in out and out.endswith("-> not pinging")
    assert len([url for url in asked if url != PING]) == 3, "one unreadable endpoint must not hide the other two readings"


def test_the_tick_bar_is_one_minute():
    assert selfcheck.TICK_MAX_AGE_SECONDS == 60
    assert _run(metrics=_metrics(tick_age=60.0))[1][-1] == PING


def test_with_no_ping_url_a_healthy_node_reads_everything_and_pings_nothing():
    rc, asked, out = _run(env={**ENV, "MON_SELFCHECK_HEALTHCHECK_URL": ""})
    assert rc == 0 and len(asked) == 3 and out.endswith("-> healthy, and no ping URL is set")


def test_a_ping_that_fails_is_reported_and_the_unit_still_exits_clean():
    rc, asked, out = _run(broken=(PING,))
    assert rc == 0 and asked[-1] == PING and out.endswith("-> ping failed: URLError")


def test_the_ping_url_never_reaches_the_output():
    for kwargs in ({}, {"broken": (PING,)}, {"fleet": 0}):
        assert PING not in _run(**kwargs)[2]


# The module's install directory exists on the node alone, so the run seeds that path entry with a finder over a copy of
# the module. Nothing else on the run's path holds the module, so the script's first import fails and its fallback's
# import is the one that finds it.
_HAND_RUN = """
import runpy, sys
from importlib.machinery import FileFinder, SourceFileLoader
script, installed, copy = sys.argv[1:]
sys.path_importer_cache[installed] = FileFinder(copy, (SourceFileLoader, [".py"]))
runpy.run_path(script, run_name="__main__")
"""


def test_a_hand_run_without_the_units_pythonpath_imports_the_module_from_where_the_role_installs_it(tmp_path):
    (made,) = [task["ansible.builtin.file"]["path"] for task in load_tasks(SELFCHECK_TASKS) if "ansible.builtin.file" in task]
    (tmp_path / "copy").mkdir()
    shutil.copy(SHARED, tmp_path / "copy")
    unreadable = (tmp_path / "absent").as_uri()
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"} | {
        "MON_SELFCHECK_GRAFANA": unreadable,
        "MON_SELFCHECK_PROMETHEUS": unreadable,
        "MON_SELFCHECK_LOKI": unreadable,
        "MON_SELFCHECK_HEALTHCHECK_URL": "",
    }
    run = subprocess.run(
        [sys.executable, "-c", _HAND_RUN, str(SCRIPT), made, str(tmp_path / "copy")],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (run.returncode, run.stdout, run.stderr) == (
        0,
        "selfcheck: rules=FAIL (unreadable: URLError) fleet=FAIL (unreadable: URLError) loki=FAIL (unreadable: URLError)"
        " -> not pinging\n",
        "",
    )


# --- the unit, its environment file and its timer: node_common's, rendered through the role's include -------------
def _scope(**extra) -> dict:
    # The include's vars as the play resolves them: over the role's own defaults and node_common's.
    (include,) = [
        task
        for task in load_tasks(ROLE / "tasks/main.yml")
        if task.get("ansible.builtin.include_role") == {"name": "node_common", "tasks_from": "selfcheck"}
    ]
    node = role_render.variables(ROLE, {}, exclude=("mon_token_cache",))
    return node | role_render.trusted(include["vars"]) | extra


def _render(name: str, **extra) -> str:
    return role_render.render(NODE_COMMON, name, {}, **_scope(**extra))


def _resolved(value):
    return role_render.resolve(NODE_COMMON, value, {}, **_scope())


def test_the_unit_and_its_environment_file_set_every_name_the_script_reads():
    read = set(re.findall(r'(?:env(?:\.get\(|\[)|ping_var=)"(MON_SELFCHECK_[A-Z_]+)"', SCRIPT.read_text()))
    unit = _render("selfcheck.service.j2")
    in_unit = dict(line.removeprefix("Environment=").split("=", 1) for line in unit.splitlines() if line.startswith("Environment="))
    assert in_unit == {
        "MON_SELFCHECK_GRAFANA": "http://127.0.0.1:3000",
        "MON_SELFCHECK_PROMETHEUS": "http://127.0.0.1:9090",
        "MON_SELFCHECK_LOKI": "http://127.0.0.1:3100",
        "PYTHONPATH": "/usr/local/lib/zcrypto",
    }
    env_file = _render("selfcheck.env.j2", mon_selfcheck_healthcheck_url=PING)
    in_file = dict(line.split("=", 1) for line in env_file.splitlines() if line and not line.startswith("#"))
    assert in_file == {"MON_SELFCHECK_HEALTHCHECK_URL": PING}
    # Python reads PYTHONPATH to import the shared loop; the script never does.
    assert read == (set(in_unit) - {"PYTHONPATH"}) | set(in_file), (
        "a name the script reads that nothing sets is a KeyError on every run"
    )
    assert DEFAULTS["mon_selfcheck_healthcheck_url"] == "", "the check is not minted at node-up, so the default pings nothing"


def test_the_unit_runs_what_the_role_installs_as_no_standing_user_and_reads_the_url_from_a_root_only_file():
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.optionxform = str
    unit = _render("selfcheck.service.j2")
    parser.read_string("\n".join(line for line in unit.splitlines() if not line.startswith("Environment=")))
    service = parser["Service"]
    assert service["ExecStart"] == "/usr/bin/python3 /usr/local/sbin/zcrypto-mon-selfcheck"
    assert (service["Type"], service["DynamicUser"], service["EnvironmentFile"]) == (
        "oneshot",
        "true",
        "/etc/default/zcrypto-mon-selfcheck",
    )
    tasks = load_tasks(SELFCHECK_TASKS)
    script = find_task(tasks, "install the self-check script")["ansible.builtin.copy"]
    assert (_resolved(script["src"]), _resolved(script["dest"])) == (
        "zcrypto-mon-selfcheck.py",
        "/usr/local/sbin/zcrypto-mon-selfcheck",
    )
    env = find_task(tasks, "render the self-check's ping URL, read by systemd alone")
    assert _resolved(env["ansible.builtin.template"]["dest"]) == service["EnvironmentFile"]
    assert (env["ansible.builtin.template"]["mode"], env["no_log"], env["diff"]) == ("0600", True, False)


def test_the_timer_runs_every_five_minutes_and_is_what_the_role_enables():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(_render("selfcheck.timer.j2"))
    assert parser["Timer"]["OnCalendar"] == "*:0/5:23" and "Persistent" not in parser["Timer"]
    assert parser["Timer"]["Unit"] == "zcrypto-mon-selfcheck.service"
    tasks = load_tasks(SELFCHECK_TASKS)
    enable = find_task(tasks, "enable + start the self-check timer")
    assert {k: _resolved(v) for k, v in enable["ansible.builtin.systemd_service"].items()} == {
        "name": "zcrypto-mon-selfcheck.timer",
        "daemon_reload": True,
        "enabled": True,
        "state": "started",
    }
    install = find_task(tasks, "render the self-check systemd timer")
    assert when_conditions(enable) == [f"not (ansible_check_mode and {install['register']} is changed)"]
