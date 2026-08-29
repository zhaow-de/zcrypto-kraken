"""TDD for `infra/scripts/ops_daily.py` — the daily pass's instrument.

These are standalone scripts, not package modules, so they load via `spec_from_file_location`.
Every fixture here is shaped to what the LIVE Grafana API actually returns, measured 2026-08-29:
the rule uid is a top-level field, `labels` carry only `severity`, and no `__`-prefixed label
exists. An earlier draft of this plan invented `labels.__a_uid__`; the fixtures were shaped to the
invention, so every test passed while the pass would have matched no alert to any runbook.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
            "alerts": [{"activeAt": "2026-08-29T10:00:00Z", "labels": {"host": "zcrypto"}}],
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
    """These rules' own expr is `count(up{host="ops"}) or on() vector(0)`, so the firing instance
    carries only `severity`. Without the map the pass cannot tell an Alloy restart that is routine
    on ops from the same restart on the capture pair, which is attended -- and the two capture
    entries are what a copy-paste breaks."""
    payload = _rules(
        {
            "name": "Alloy dark",
            "uid": uid,
            "state": "firing",
            "labels": {"severity": "critical"},
            "annotations": {},
            "alerts": [{"activeAt": "2026-08-29T10:00:00Z", "labels": {"severity": "critical"}}],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].host == expected


def test_an_instance_host_label_wins_over_the_uid_map():
    payload = _rules(
        {
            "name": "Alloy dark",
            "uid": "zcrypto-alloy-dark-ops",
            "state": "firing",
            "labels": {"severity": "critical"},
            "annotations": {},
            "alerts": [{"activeAt": "2026-08-29T10:00:00Z", "labels": {"host": "nas"}}],
        }
    )
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload, _EMPTY_HISTORY))
    assert read.firing_now[0].host == "nas"


# --- Task 12: the log plane -------------------------------------------------------------------


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


# --- Task 13: the dead-men, the fleet verdict, the window's deploys ----------------------------


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


# --- Task 14: the report, the exit codes -------------------------------------------------------


def _report(**kw):
    base = dict(
        alerts=ops_daily.AlertsRead(),
        logs=ops_daily.LogsRead(),
        deadmen=ops_daily.DeadmenRead(via_prometheus=0.0, via_healthchecks=[{"name": "x"}]),
        verdict=[ops_daily.Check("capture primary up", "up{...}", ok=True, value="1")],
        deploys=[],
        now=NOW,
    )
    return ops_daily.build_report(**{**base, **kw})


def test_an_all_clear_report_exits_zero():
    r = _report()
    assert r.exit_code == 0 and r.verdict_word == "all-clear"


def test_anything_fired_exits_one():
    firing = ops_daily.AlertsRead(firing_now=[ops_daily.Alert("u", "t", "firing", None, None, "ops")])
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
        firing_now=[ops_daily.Alert("u", "t", "firing", None, None, "ops")], unreadable="history truncated"
    )
    assert _report(alerts=firing).exit_code == 2


def test_the_journal_paragraph_carries_every_labelled_clause():
    para = _report().journal_paragraph()
    for clause in ("window", "alerts", "checks", "logs", "dead-men", "deploys", "actions", "follow-ups"):
        assert clause in para, f"missing clause: {clause}"


def test_the_cli_refuses_an_unknown_subcommand():
    assert ops_daily.main([]) == 2
    assert ops_daily.main(["frobnicate"]) == 2
