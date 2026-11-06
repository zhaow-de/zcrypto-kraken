"""The ops watchdog's runner, rendered through Ansible's own `Templar` and run against a stub `curl` that records
its argv and stdin and answers per URL."""

import json
import pathlib
import re
import subprocess

import pytest
import yaml

from tests.test_infra_converge_guards import iter_tasks, load_tasks
from tests.test_infra_shell_templates_render import ansible_render, role_variables

REPO = pathlib.Path(__file__).resolve().parent.parent
ROLE = REPO / "infra/ansible/roles/ops"
TEMPLATE = ROLE / "templates/grafana-watchdog.sh.j2"
STATE = "/var/lib/zcrypto-grafana-watchdog/both-dark"
MON = "https://mon.invalid/api/health"
HC = "https://hc.invalid/api/v3/status/"
PING = "https://hc.invalid/ping/key/zcrypto-grafana-watchdog"
WEBHOOK = "https://hooks.invalid/services/not-a-real-webhook"
_CURL = r"""#!/usr/bin/env bash
# Records argv, stdin and the URL per call; exits 22, curl's -f on an HTTP error, for a URL listed in $DOWN.
set -u
id=$(printf '%04d' "$(find "$CALLS" -name '*.argv' | wc -l)")
printf '%s\n' "$@" >"$CALLS/$id.argv"
config=""; prev=""; url=""
for arg in "$@"; do
  if [ "$prev" = "-K" ] && [ "$arg" = "-" ]; then config="$(cat)"; fi
  case "$arg" in http://*|https://*) url="$arg" ;; esac
  prev="$arg"
done
printf '%s' "$config" >"$CALLS/$id.stdin"
case "$config" in 'url = "'*) url="${config#url = \"}"; url="${url%\"}" ;; esac
printf '%s' "$url" >"$CALLS/$id.url"
if grep -qxF "$url" "$DOWN"; then exit 22; fi
exit 0
"""


class _Call:
    def __init__(self, stem: pathlib.Path) -> None:
        self.argv = stem.with_suffix(".argv").read_text().splitlines()
        self.stdin = stem.with_suffix(".stdin").read_text()
        self.url = stem.with_suffix(".url").read_text()

    @property
    def text(self) -> str | None:
        """The message of a call that posts one."""
        return json.loads(self.argv[self.argv.index("-d") + 1])["text"] if "-d" in self.argv else None


class _Watchdog:
    def __init__(self, tmp_path: pathlib.Path, *, ping: str = PING, webhook: str | None = WEBHOOK) -> None:
        self.webhook = webhook
        self.calls = tmp_path / "calls"
        self.calls.mkdir()
        self.down = tmp_path / "down"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "curl").write_text(_CURL)
        (self.bin / "curl").chmod(0o755)
        variables = role_variables(TEMPLATE) | {
            "ops_grafana_watchdog_healthcheck_url": ping,
            "ops_grafana_watchdog_probe_url": MON,
            "ops_grafana_watchdog_hc_probe_url": HC,
        }
        rendered = ansible_render(TEMPLATE.read_text(), variables)
        assert rendered.count(STATE) == 1, "the state path moved: this harness would write outside the test's tmp dir"
        self.script = tmp_path / "watchdog.sh"
        self.script.write_text(rendered.replace(STATE, str(tmp_path / "both-dark")))
        self.script.chmod(0o755)

    def run(self, *down: str) -> list[_Call]:
        """One run with these URLs failing; the calls it made."""
        self.down.write_text("".join(f"{url}\n" for url in down))
        before = {path.stem for path in self.calls.glob("*.argv")}
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "CALLS": str(self.calls), "DOWN": str(self.down)}
        if self.webhook is not None:
            env["ZCRYPTO_SLACK_WEBHOOK_URL"] = self.webhook
        done = subprocess.run([str(self.script)], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return [_Call(self.calls / stem) for stem in sorted({path.stem for path in self.calls.glob("*.argv")} - before)]


def _posted(calls: list[_Call]) -> list[str]:
    return [call.text for call in calls if call.text is not None]


def _pings(calls: list[_Call]) -> list[str]:
    return [call.url for call in calls if call.url.startswith(PING)]


def test_the_third_run_with_both_down_posts_once_naming_both_hosts_and_the_runbook(tmp_path):
    watchdog = _Watchdog(tmp_path)
    assert _posted(watchdog.run(MON, HC)) == []
    assert _posted(watchdog.run(MON, HC)) == []
    (page,) = _posted(watchdog.run(MON, HC))
    assert "zcrypto-mon" in page and "zcrypto-hc" in page and "Runbook: infra/runbooks/observability.md#both-nodes-dark" in page
    assert _posted(watchdog.run(MON, HC)) == []


@pytest.mark.parametrize("still_down", [MON, HC], ids=["the dead-man service answers", "the Grafana answers"])
def test_a_run_with_either_up_starts_the_count_again(tmp_path, still_down):
    watchdog = _Watchdog(tmp_path)
    runs = [(MON, HC), (MON, HC), (still_down,), (MON, HC), (MON, HC)]
    assert [_posted(watchdog.run(*down)) for down in runs] == [[]] * 5


def test_only_the_grafana_down_pings_fail_and_posts_nothing(tmp_path):
    watchdog = _Watchdog(tmp_path)
    for _ in range(4):
        calls = watchdog.run(MON)
        assert _pings(calls) == [f"{PING}/fail"] and _posted(calls) == []


def test_only_the_dead_man_service_down_pings_plain_and_posts_nothing(tmp_path):
    watchdog = _Watchdog(tmp_path)
    for _ in range(4):
        calls = watchdog.run(HC)
        assert _pings(calls) == [PING] and _posted(calls) == []


def test_a_failed_post_is_retried_on_the_next_run_and_only_one_succeeds(tmp_path):
    watchdog = _Watchdog(tmp_path)
    watchdog.run(MON, HC)
    watchdog.run(MON, HC)
    assert len(_posted(watchdog.run(MON, HC, WEBHOOK))) == 1, "the third run tries, and the webhook refuses"
    assert len(_posted(watchdog.run(MON, HC))) == 1, "the fourth tries again, and it lands"
    assert _posted(watchdog.run(MON, HC)) == []


def _paged(tmp_path) -> _Watchdog:
    watchdog = _Watchdog(tmp_path)
    for _ in range(3):
        watchdog.run(MON, HC)
    return watchdog


def test_after_a_page_a_run_with_either_up_posts_one_recovery_and_both_up_posts_nothing(tmp_path):
    watchdog = _paged(tmp_path)
    (recovery,) = _posted(watchdog.run(HC))
    assert "mon up, hc down" in recovery and "Runbook: infra/runbooks/observability.md#both-nodes-dark" in recovery
    assert _posted(watchdog.run()) == []


def test_a_failed_recovery_post_is_retried_on_the_next_run(tmp_path):
    watchdog = _paged(tmp_path)
    assert len(_posted(watchdog.run(WEBHOOK))) == 1, "the recovery tries, and the webhook refuses"
    assert len(_posted(watchdog.run())) == 1, "the next run tries again, and it lands"
    assert _posted(watchdog.run()) == []


def test_an_empty_ping_url_still_runs_the_both_dark_logic_and_pings_nothing(tmp_path):
    watchdog = _Watchdog(tmp_path, ping="")
    runs = [watchdog.run(MON, HC) for _ in range(3)]
    assert [len(_posted(calls)) for calls in runs] == [0, 0, 1]
    assert all({call.url for call in calls if call.text is None} == {MON, HC} for calls in runs), "only the two probes"


def test_an_unset_webhook_posts_nothing_and_the_run_still_exits_0(tmp_path):
    watchdog = _Watchdog(tmp_path, webhook=None)
    for _ in range(4):
        assert _posted(watchdog.run(MON, HC)) == []


def test_the_webhook_is_never_in_a_recorded_argv_and_is_in_the_stubs_stdin(tmp_path):
    watchdog = _paged(tmp_path)
    watchdog.run()
    calls = [_Call(path.with_suffix("")) for path in sorted(watchdog.calls.glob("*.argv"))]
    assert not any(WEBHOOK in arg for call in calls for arg in call.argv)
    assert [call.stdin for call in calls if call.text is not None] == [f'url = "{WEBHOOK}"'] * 2


def _unit_value(key: str) -> str:
    lines = (ROLE / "templates/grafana-watchdog.service.j2").read_text().splitlines()
    (line,) = [line for line in lines if line.startswith(f"{key}=")]
    return line.removeprefix(f"{key}=")


def test_the_unit_makes_the_state_directory_and_sources_the_file_the_role_renders_0600():
    assert _unit_value("StateDirectory") == pathlib.PurePosixPath(STATE).parent.name
    (task,) = [
        task
        for task, _ in iter_tasks(load_tasks(ROLE / "tasks/main.yml"))
        if task.get("name") == "render the grafana-watchdog secrets env file"
    ]
    module = task["ansible.builtin.template"]
    assert _unit_value("EnvironmentFile") == f"-{module['dest']}"
    assert (module["src"], module["mode"], task["no_log"], task["diff"]) == ("grafana-watchdog-secrets.env.j2", "0600", True, False)


def test_the_runbook_the_message_names_resolves_to_its_anchor(tmp_path):
    watchdog = _Watchdog(tmp_path)
    watchdog.run(MON, HC)
    watchdog.run(MON, HC)
    (page,) = _posted(watchdog.run(MON, HC))
    path, anchor = page.rsplit("Runbook: ", 1)[1].split("#")
    assert f'<a name="{anchor}"></a>' in (REPO / path).read_text(encoding="utf-8")


def test_the_drill_fence_replaces_exactly_the_urls_the_runner_probes():
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    observed = yaml.safe_load((REPO / "infra/ansible/group_vars/observed/vars.yml").read_text())
    hc_probe = ansible_render(defaults["ops_grafana_watchdog_hc_probe_url"], {"hc_hostname": observed["hc_hostname"]})
    variables = role_variables(TEMPLATE) | {"ops_grafana_watchdog_hc_probe_url": hc_probe}
    probed = re.findall(r'^probe "(.+)" \|\|', ansible_render(TEMPLATE.read_text(), variables), re.MULTILINE)

    drill = (REPO / "infra/runbooks/drills-telemetry.md").read_text(encoding="utf-8")
    fence = drill.split('<a name="drill-w5"></a>')[1].split('<a name="')[0]
    replaced = re.findall(r"-e 's\|(https://[^|]+)\|https://both-dark-drill\.invalid/\|'", fence)

    assert len(probed) == 2 and sorted(replaced) == sorted(probed)


def test_the_secrets_file_carries_the_name_the_runner_reads():
    secrets = (ROLE / "templates/grafana-watchdog-secrets.env.j2").read_text()
    (name,) = re.findall(
        r"^([A-Z_]+)=https://hooks\.invalid/x$",
        ansible_render(secrets, {"slack_webhook_url": "https://hooks.invalid/x"}),
        re.MULTILINE,
    )
    assert f'"${name}"' in TEMPLATE.read_text()


def test_the_drill_fence_blanks_the_runners_ping_and_reads_the_file_the_role_renders():
    (task,) = [
        task
        for task, _ in iter_tasks(load_tasks(ROLE / "tasks/main.yml"))
        if task.get("name") == "render the grafana-watchdog secrets env file"
    ]
    dest = ansible_render(task["ansible.builtin.template"]["dest"], role_variables(TEMPLATE))
    drill = (REPO / "infra/runbooks/drills-telemetry.md").read_text(encoding="utf-8")
    fence = drill.split('<a name="drill-w5"></a>')[1].split('<a name="')[0]
    assert "-e 's|^URL=.*|URL=\"\"|'" in fence and re.search(r"^URL=", TEMPLATE.read_text(), re.MULTILINE)
    assert f"-p EnvironmentFile={dest} " in fence
