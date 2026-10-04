from __future__ import annotations

import configparser
import io
import json
import re
import types
import urllib.error
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests.test_infra_converge_guards import find_task, load_tasks, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/mon"
SCRIPT = ROLE / "files/zcrypto-mon-selfcheck.py"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
# Compiled from its text, never imported by path: an import writes a bytecode cache beside the script, inside a
# role's files/, and the cache names the checkout's own path, which tests/test_deploy_log_audit.py walks the role for.
selfcheck = types.ModuleType("mon_selfcheck")
exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), selfcheck.__dict__)

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


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run(capsys, *, metrics=None, fleet=8, loki="ready\n", refused=None, env=ENV, broken=()):
    """`refused` is Loki's own not-ready answer: a 503 whose body is the reason."""
    asked: list[str] = []
    bodies = {
        "http://127.0.0.1:3000/metrics": _metrics() if metrics is None else metrics,
        "http://127.0.0.1:9090/api/v1/query": _fleet(fleet),
        "http://127.0.0.1:3100/ready": loki,
        PING: "OK",
    }

    def opener(request, timeout):
        url = request.full_url
        asked.append(url)
        base = url.split("?")[0]
        if base in broken:
            raise urllib.error.URLError("connection refused")
        if refused is not None and base == "http://127.0.0.1:3100/ready":
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, io.BytesIO(refused.encode()))
        return _Response(bodies[base].encode())

    rc = selfcheck.main(env, opener=opener, now=lambda: NOW)
    return rc, asked, capsys.readouterr().out.strip()


def test_a_node_doing_its_job_pings_and_says_what_it_read(capsys):
    rc, asked, out = _run(capsys)
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
def test_one_failing_check_sends_no_ping_and_still_exits_clean(capsys, fault, said):
    rc, asked, out = _run(capsys, **fault)
    assert rc == 0, "a failing unit every five minutes would be the noise; the missing ping is the page"
    assert PING not in asked
    assert said in out and out.endswith("-> not pinging")
    assert len([url for url in asked if url != PING]) == 3, "one unreadable endpoint must not hide the other two readings"


def test_the_tick_bar_is_one_minute(capsys):
    assert selfcheck.TICK_MAX_AGE_SECONDS == 60
    assert _run(capsys, metrics=_metrics(tick_age=60.0))[1][-1] == PING


def test_with_no_ping_url_a_healthy_node_reads_everything_and_pings_nothing(capsys):
    rc, asked, out = _run(capsys, env={**ENV, "MON_SELFCHECK_HEALTHCHECK_URL": ""})
    assert rc == 0 and len(asked) == 3 and out.endswith("-> healthy, and no ping URL is set")


def test_a_ping_that_fails_is_reported_and_the_unit_still_exits_clean(capsys):
    rc, asked, out = _run(capsys, broken=(PING,))
    assert rc == 0 and asked[-1] == PING and out.endswith("-> ping failed: URLError")


def test_the_ping_url_never_reaches_the_output(capsys):
    for kwargs in ({}, {"broken": (PING,)}, {"fleet": 0}):
        assert PING not in _run(capsys, **kwargs)[2]


# --- the unit, its environment file and its timer ----------------------------------------------------------------
def _render(name: str, **extra) -> str:
    variables = {k: v for k, v in DEFAULTS.items() if k != "mon_token_cache"} | extra
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template((ROLE / "templates" / name).read_text()))


def test_the_unit_and_its_environment_file_set_every_name_the_script_reads():
    read = set(re.findall(r'env(?:\.get\(|\[)"(MON_SELFCHECK_[A-Z_]+)"', SCRIPT.read_text()))
    unit = _render("zcrypto-mon-selfcheck.service.j2")
    in_unit = dict(line.removeprefix("Environment=").split("=", 1) for line in unit.splitlines() if line.startswith("Environment="))
    assert in_unit == {
        "MON_SELFCHECK_GRAFANA": "http://127.0.0.1:3000",
        "MON_SELFCHECK_PROMETHEUS": "http://127.0.0.1:9090",
        "MON_SELFCHECK_LOKI": "http://127.0.0.1:3100",
    }
    env_file = _render("zcrypto-mon-selfcheck.env.j2", mon_selfcheck_healthcheck_url=PING)
    in_file = dict(line.split("=", 1) for line in env_file.splitlines() if line and not line.startswith("#"))
    assert in_file == {"MON_SELFCHECK_HEALTHCHECK_URL": PING}
    assert read == set(in_unit) | set(in_file), "a name the script reads that nothing sets is a KeyError on every run"
    assert DEFAULTS["mon_selfcheck_healthcheck_url"] == "", "the check is not minted at node-up, so the default pings nothing"


def test_the_unit_runs_what_the_role_installs_as_no_standing_user_and_reads_the_url_from_a_root_only_file():
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.optionxform = str
    unit = _render("zcrypto-mon-selfcheck.service.j2")
    parser.read_string("\n".join(line for line in unit.splitlines() if not line.startswith("Environment=")))
    service = parser["Service"]
    assert service["ExecStart"] == "/usr/bin/python3 /usr/local/sbin/zcrypto-mon-selfcheck"
    assert (service["Type"], service["DynamicUser"], service["EnvironmentFile"]) == (
        "oneshot",
        "true",
        "/etc/default/zcrypto-mon-selfcheck",
    )
    tasks = load_tasks(ROLE / "tasks/main.yml")
    script = find_task(tasks, "install the self-check script")["ansible.builtin.copy"]
    assert (script["src"], script["dest"]) == ("zcrypto-mon-selfcheck.py", "/usr/local/sbin/zcrypto-mon-selfcheck")
    env = find_task(tasks, "render the self-check's ping URL, read by systemd alone")
    assert env["ansible.builtin.template"]["dest"] == service["EnvironmentFile"]
    assert (env["ansible.builtin.template"]["mode"], env["no_log"], env["diff"]) == ("0600", True, False)


def test_the_timer_runs_every_five_minutes_and_is_what_the_role_enables():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string((ROLE / "files/zcrypto-mon-selfcheck.timer").read_text())
    assert parser["Timer"]["OnCalendar"] == "*:0/5:23" and "Persistent" not in parser["Timer"]
    assert parser["Timer"]["Unit"] == "zcrypto-mon-selfcheck.service"
    enable = find_task(load_tasks(ROLE / "tasks/main.yml"), "enable + start the self-check timer")
    assert enable["ansible.builtin.systemd_service"] == {
        "name": "zcrypto-mon-selfcheck.timer",
        "daemon_reload": True,
        "enabled": True,
        "state": "started",
    }
    assert when_conditions(enable) == ["not (ansible_check_mode and mon_selfcheck_timer_install is changed)"]
