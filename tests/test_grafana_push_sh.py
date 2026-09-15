"""`infra/scripts/grafana-push.sh` against a recording `curl` stub, from a copy in a scratch tree so the
`infra/grafana/` it reads is the test's. It requires `GRAFANA_SA_TOKEN` and a `python3` that imports PyYAML before
any call; pushes every `*-dashboard.json` by its own uid into the folder; PUTs each notification template and refuses
one that does not read back byte-identical, before any rule is touched; without a webhook it requires both receivers
live and referencing the templates, with one it upserts them by uid (PUT when the uid exists, POST otherwise), routes
the default policy to `metrics` and deletes the legacy integration last; upserts each rule with the placeholders
substituted (PUT on a 200, POST otherwise); reads every rule back and fails on a datasource that is neither the
Prometheus nor the Loki uid; and names an orphan only inside the folder, deleting it only under `GRAFANA_PRUNE=1`."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "grafana-push.sh"
_URL = "https://stub.invalid"
_TEMPLATE = 'hello {{ template "x" . }}\nsecond line\n'
_ALERTS = """rules:
  - uid: r1
    title: one
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    data:
      - refId: A
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
      - refId: C
        datasourceUid: __expr__
  - uid: r2
    title: two
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    data:
      - refId: A
        datasourceUid: "${GRAFANA_LOKI_DS_UID}"
      - refId: C
        datasourceUid: __expr__
"""
_CURL = r"""#!/usr/bin/env bash
# Records METHOD URL then the -d payload per call; answers from $STUB_DIR by method and path.
set -u
method=GET; url=""; code=0; payload=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    -X) method="${args[i + 1]}"; i=$((i + 1)) ;;
    -w) code=1; i=$((i + 1)) ;;
    -d) payload="${args[i + 1]}"; i=$((i + 1)) ;;
    -H|-o) i=$((i + 1)) ;;
    http://*|https://*) url="${args[i]}" ;;
  esac
done
[ "$payload" = "@-" ] && payload="$(cat)"
n=$(find "$CALL_DIR" -type f | wc -l)
printf '%s %s\n%s' "$method" "$url" "$payload" > "$CALL_DIR/$(printf '%04d' "$n")"
path="${url#*://*/}"
if [ "$code" = 1 ]; then
  if [ -e "$STUB_DIR/exists/${path##*/}" ]; then printf 200; else printf 404; fi
  exit 0
fi
key="${method}_${path//\//_}"
if [ -e "$STUB_DIR/$key.json" ]; then cat "$STUB_DIR/$key.json"; else echo '{}'; fi
"""


def _receiver(uid: str, name: str, *, templated: bool = True) -> dict:
    return {
        "uid": uid,
        "name": name,
        "type": "slack",
        "settings": {
            "title": f'{{{{ template "zcrypto.slack.title.{name}" . }}}}',
            "text": f'{{{{ template "zcrypto.slack.body.{name}" . }}}}',
        }
        if templated
        else {"title": "stock"},
    }


class _Stack:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        scripts = tmp_path / "infra" / "scripts"
        scripts.mkdir(parents=True)
        self.script = scripts / _SCRIPT.name
        shutil.copy(_SCRIPT, self.script)
        grafana = tmp_path / "infra" / "grafana"
        (grafana / "notification-templates").mkdir(parents=True)
        (grafana / "a-dashboard.json").write_text(json.dumps({"uid": "dash-a", "title": "A"}), encoding="utf-8")
        (grafana / "notification-templates" / "t1.tmpl").write_text(_TEMPLATE, encoding="utf-8")
        (grafana / "alerts.yaml").write_text(_ALERTS, encoding="utf-8")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "curl").write_text(_CURL, encoding="utf-8")
        (self.bin / "curl").chmod(0o755)
        self.stub = tmp_path / "stub"
        (self.stub / "exists").mkdir(parents=True)
        self.calls = tmp_path / "calls"
        self.calls.mkdir()
        self.respond("GET", "api/v1/provisioning/templates/t1", {"template": _TEMPLATE})
        self.respond(
            "GET",
            "api/v1/provisioning/contact-points",
            [_receiver("zcrypto-slack-metrics", "metrics"), _receiver("zcrypto-slack-logs", "logs")],
        )
        (self.stub / "exists" / "r1").touch()
        self.respond(
            "GET",
            "api/v1/provisioning/alert-rules/r1",
            {"uid": "r1", "data": [{"datasourceUid": "prom-x"}, {"datasourceUid": "__expr__"}]},
        )
        self.respond(
            "GET",
            "api/v1/provisioning/alert-rules/r2",
            {"uid": "r2", "data": [{"datasourceUid": "loki-x"}, {"datasourceUid": "__expr__"}]},
        )
        self.respond(
            "GET",
            "api/v1/provisioning/alert-rules",
            [
                {"uid": "r1", "folderUID": "fold-x"},
                {"uid": "r2", "folderUID": "fold-x"},
                {"uid": "old", "folderUID": "fold-x"},
                {"uid": "other", "folderUID": "elsewhere"},
            ],
        )
        self.respond("GET", "api/v1/provisioning/policies", {"receiver": "email", "routes": []})

    def respond(self, method: str, path: str, body: object) -> None:
        (self.stub / f"{method}_{path.replace('/', '_')}.json").write_text(json.dumps(body), encoding="utf-8")

    def run(self, **env: str) -> subprocess.CompletedProcess[str]:
        base = {
            "PATH": f"{self.bin}:{Path(sys.executable).parent}:/usr/bin:/bin",
            "HOME": str(self.root),
            "CALL_DIR": str(self.calls),
            "STUB_DIR": str(self.stub),
            "GRAFANA_SA_TOKEN": "tok-fixture",
            "GRAFANA_URL": _URL,
            "GRAFANA_PROM_DS_UID": "prom-x",
            "GRAFANA_LOKI_DS_UID": "loki-x",
            "GRAFANA_ALERT_FOLDER_UID": "fold-x",
        }
        return subprocess.run([str(self.script)], capture_output=True, text=True, env={**base, **env})

    def recorded(self) -> list[tuple[str, str, str]]:
        """(method, path, payload) per call, in order."""
        out = []
        for f in sorted(self.calls.iterdir()):
            head, _, payload = f.read_text(encoding="utf-8").partition("\n")
            method, url = head.split(" ", 1)
            out.append((method, url.removeprefix(f"{_URL}/"), payload))
        return out


@pytest.fixture
def stack(tmp_path):
    return _Stack(tmp_path)


def test_the_token_and_pyyaml_are_required_before_any_call(stack):
    done = stack.run(GRAFANA_SA_TOKEN="")
    assert done.returncode != 0 and "GRAFANA_SA_TOKEN is required" in done.stderr
    (stack.bin / "python3").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    (stack.bin / "python3").chmod(stat.S_IRWXU)
    done = stack.run()
    assert done.returncode == 1 and "PyYAML module is required" in done.stderr
    assert stack.recorded() == []


def test_a_webhook_less_run_pushes_in_order_and_names_only_the_folders_orphan(stack):
    done = stack.run()
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == "grafana-push: done"
    calls = stack.recorded()
    assert [(m, p) for m, p, _ in calls] == [
        ("POST", "api/dashboards/db"),
        ("PUT", "api/v1/provisioning/templates/t1"),
        ("GET", "api/v1/provisioning/templates/t1"),
        ("GET", "api/v1/provisioning/contact-points"),
        ("GET", "api/v1/provisioning/alert-rules/r1"),
        ("PUT", "api/v1/provisioning/alert-rules/r1"),
        ("GET", "api/v1/provisioning/alert-rules/r2"),
        ("POST", "api/v1/provisioning/alert-rules"),
        ("GET", "api/v1/provisioning/alert-rules/r1"),
        ("GET", "api/v1/provisioning/alert-rules/r2"),
        ("GET", "api/v1/provisioning/alert-rules"),
    ]
    assert json.loads(calls[0][2]) == {"dashboard": {"uid": "dash-a", "title": "A"}, "folderUid": "fold-x", "overwrite": True}
    assert json.loads(calls[1][2]) == {"name": "t1", "template": _TEMPLATE}
    r1, r2 = json.loads(calls[5][2]), json.loads(calls[7][2])
    assert (r1["uid"], r1["folderUID"], r1["data"][0]["datasourceUid"]) == ("r1", "fold-x", "prom-x")
    assert (r2["uid"], r2["folderUID"], r2["data"][0]["datasourceUid"]) == ("r2", "fold-x", "loki-x")
    assert "${" not in calls[5][2] + calls[7][2]
    orphan_lines = [line for line in done.stderr.splitlines() if "ORPHAN" in line]
    assert orphan_lines == ["grafana-push: ORPHAN (live but not in alerts.yaml): old  — re-run with GRAFANA_PRUNE=1 to delete"]
    assert "receivers metrics+logs already live, skipping Slack upserts" in done.stderr


def test_prune_deletes_the_folders_orphan_and_nothing_elsewhere(stack):
    done = stack.run(GRAFANA_PRUNE="1")
    assert done.returncode == 0, done.stderr
    deletes = [p for m, p, _ in stack.recorded() if m == "DELETE"]
    assert deletes == ["api/v1/provisioning/alert-rules/old"]
    assert "grafana-push: DELETED orphaned rule old" in done.stderr


def test_a_template_that_does_not_read_back_identical_stops_before_the_rules(stack):
    stack.respond("GET", "api/v1/provisioning/templates/t1", {"template": _TEMPLATE.replace("second", "other")})
    done = stack.run()
    assert done.returncode == 1 and "notification template t1 did NOT read back byte-identical" in done.stderr
    assert not any("alert-rules" in p for _, p, _ in stack.recorded())


@pytest.mark.parametrize(
    ("receivers", "message"),
    [
        ([_receiver("zcrypto-slack-metrics", "metrics")], "receiver 'logs' does not exist on the stack"),
        (
            [_receiver("zcrypto-slack-metrics", "metrics"), _receiver("zcrypto-slack-logs", "logs", templated=False)],
            "receiver 'logs' is live but no longer references the notification template",
        ),
    ],
)
def test_without_a_webhook_both_receivers_must_be_live_and_templated(stack, receivers, message):
    stack.respond("GET", "api/v1/provisioning/contact-points", receivers)
    done = stack.run()
    assert done.returncode == 1 and message in done.stderr
    assert not any("alert-rules" in p for _, p, _ in stack.recorded())


def test_a_rule_reading_back_with_a_foreign_datasource_fails_before_the_orphan_check(stack):
    stack.respond(
        "GET",
        "api/v1/provisioning/alert-rules/r2",
        {"uid": "r2", "data": [{"datasourceUid": "usage-ds"}, {"datasourceUid": "__expr__"}]},
    )
    done = stack.run()
    assert done.returncode == 1
    assert "!! r2 points at an UNEXPECTED datasource: usage-ds" in done.stderr and "datasource check FAILED" in done.stderr
    assert ("GET", "api/v1/provisioning/alert-rules") not in [(m, p) for m, p, _ in stack.recorded()]


def test_with_a_webhook_the_receivers_are_upserted_by_uid_the_policy_routed_and_the_legacy_integration_deleted_last(stack):
    stack.respond(
        "GET",
        "api/v1/provisioning/contact-points",
        [
            _receiver("zcrypto-slack-metrics", "metrics"),
            _receiver("zcrypto-slack-logs", "logs"),
            {"uid": "zcrypto-slack-webhook", "name": "email", "type": "slack"},
        ],
    )
    done = stack.run(GRAFANA_SLACK_WEBHOOK_URL="https://hooks.invalid/x")
    assert done.returncode == 0, done.stderr
    calls = stack.recorded()
    by_path = {(m, p): json.loads(d) for m, p, d in calls if d}
    metrics = by_path[("PUT", "api/v1/provisioning/contact-points/zcrypto-slack-metrics")]
    logs = by_path[("PUT", "api/v1/provisioning/contact-points/zcrypto-slack-logs")]
    assert (metrics["name"], metrics["disableResolveMessage"], metrics["settings"]["url"]) == (
        "metrics",
        False,
        "https://hooks.invalid/x",
    )
    assert (logs["name"], logs["disableResolveMessage"]) == ("logs", True)
    assert '{{ template "zcrypto.slack.title.metrics" . }}' == metrics["settings"]["title"]
    assert by_path[("PUT", "api/v1/provisioning/policies")] == {"receiver": "metrics", "routes": []}
    assert [(m, p) for m, p, _ in calls if m == "DELETE"] == [
        ("DELETE", "api/v1/provisioning/contact-points/zcrypto-slack-webhook")
    ]
    assert calls[-1][:2] == ("DELETE", "api/v1/provisioning/contact-points/zcrypto-slack-webhook")
    assert "notification-policy default route -> metrics" in done.stderr


def test_with_a_webhook_a_receiver_absent_by_uid_is_posted_and_then_verified(stack):
    stack.respond("GET", "api/v1/provisioning/contact-points", [_receiver("zcrypto-slack-metrics", "metrics")])
    done = stack.run(GRAFANA_SLACK_WEBHOOK_URL="https://hooks.invalid/x")
    posted = [json.loads(d)["uid"] for m, p, d in stack.recorded() if (m, p) == ("POST", "api/v1/provisioning/contact-points")]
    assert posted == ["zcrypto-slack-logs"]
    assert done.returncode == 1 and "Slack integration verification FAILED for uid=zcrypto-slack-logs name=logs" in done.stderr
