# Every shipped log line carries a level, and a WARNING or ERROR line is one an operator reads as such Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every source in the node's measured set ships its lines with a `level` set in its host's Alloy by the shape it already prints, the no-fault ERROR and WARNING shapes on the node read INFO, the node's Grafana and the cache proxy stop printing their configuration warnings, and a node rule pages the first line any host ships with no level.

**Architecture:** Each host's `loki.process "parse"` gains trailing `stage.match` blocks after its parsing blocks — `{container="<name>", level=""}` with a line filter, a `stage.static_labels` level or `action = "drop"` — and the node's gains four re-level blocks on `level=~"ERROR|WARNING"` lines (spec D1, D4, D5). One new test module models those blocks from the configs' own selector text over fixture lines taken from the measured shapes and the sources' format strings; a real-Alloy harness runs the same blocks where a binary is on PATH, which the controller supplies once (Task 10). The rule, panel, ini and HAProxy changes are each their own task with their own tests (D3, D6, D7, D9); the rollout is the owner's, host by host (D11).

**Tech Stack:** Grafana Alloy 1.21.2 (`loki.process` stages, LogQL selectors), Grafana alert-rule YAML and dashboard JSON, Loki LogQL, Jinja2 templates, Python 3.14 with pytest, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00155-fleet-log-levels-design.md`

## Global Constraints

- The spec is the authority; where it is silent this plan rules, in *Rulings* below. No source's printed text changes (D1); no config reads `__journal_priority` (D2); D10's dust warning and the nautilus warnings are out of scope, and no engine code changes.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/mon-rule-noise` (branch `fix/fleet-log-levels-and-noise`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- A selector is an Alloy string holding a LogQL selector whose string literals hold a regex, so a backslash of the regex is four in the file and a quote inside a LogQL literal is `\\\"`: write every `selector = ` line exactly as its fence gives it, never re-escaped by hand.
- Each new block is a top-level `stage.match` inside `loki.process "parse"`, after the host's last parsing block and before the component's closing `}`; its selector carries `level=""`, except the node's four re-level blocks (D5), whose selectors carry `level="ERROR"` or `level=~"ERROR|WARNING"`. A drop block carries `drop_counter_reason`. No new `stage.regex` on ops (`tests/test_error_paths_are_logged.py` holds one there) and no new drop on the cache nodes (`tests/test_infra_alloy_series.py::test_the_cache_log_pipeline_drops_the_sentinel_exporters_latency_error_and_nothing_else` holds one there): D4's drops land on the capture hosts' config and on ops's, the cache nodes' config takes no drop.
- A new comment in a config names no probe's address text — `context canceled`, `status=501`, `Missing notification reason`, `signal: terminated`, `no ping URL is set`, `uwsgi-cron`, `has no server available`, `signal-handler`, `trade backfill complete`, `verify-replay census`, `AUDIT MISMATCH`, `no journaled cycles found` — so each probe address matches one line; the comments below spell those things otherwise.
- Fixtures are the measured shapes (`.tmp/lognoise/unk-24h.txt`, `error-24h.txt`, `warning-24h.txt`), the sources' own format strings and the shapes existing tests pin, numbers filled in; an address is `192.0.2.x` or loopback, a user name `example-admin`. The fixture lines below are exact; ruff rewraps the code around them.
- A comment or docstring stays only where a reader would act differently without it, and is correct; an event goes to the PR body. Runbook text, alert summaries and dashboard text carry no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>` or `Phase <N>` token (`tests/test_internal_terms_not_operator_visible.py`). A runbook page's list item carrying *every*, *never*, *always*, *only*, *any* or *cannot* names its count or declares none (the commit-msg guidance guard reads every top-level runbook page); the runbook texts below carry none of the words in a list item. Load `zcrypto-refine-rules` before editing a page under `infra/runbooks/`, as its description asks.
- Tests per commit: `T="$(infra/scripts/consumers.sh --direct <the commit's changed paths>) <the task's test files>"`, then `[ -n "$T" ] && uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`; the gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged. Before each task's first pytest run, `mkdir -p .tmp/implementer .local/fleet-log-levels`, its own call.
- No `alloy` binary is on the workstation or in CI (`.github/workflows/test-suite.yml` installs none): the model cases are the guard in every commit, and each `test_alloy_itself_agrees_with_the_level_model` case skips until Task 10, where the controller runs it against the fleet's release binary.
- Commits: Conventional Commits, one subject per change; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call, nothing beside it; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` — the implementer's own model in place of the placeholder — and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`, `infra/scripts/tier.py`): each arm a task lists runs as its own call on the committed tree — `infra/scripts/mutate-probe.sh --file <file> --control '<control>' --mutation '<mutation>' -- uv run pytest <test file> -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` — the control `1,$d` unless the arm names another. Before each arm, `grep -c '<address or pattern>' <file>` prints `1`, and for an addressed substitution `sed -n '/<address>/p' <file> | grep -c '<the substitution's pattern>'` prints `1` (a `^` inside a pattern is written `\^`); an append arm checks its address alone, and one with none (`$a …`) rests on the script's own refusal of a no-op sed. `: > .local/fleet-log-levels/probes-task-<N>.txt` before a task's arms; after each arm its id and the script's last line are appended, `printf '%s\n' '<arm>: <that line>' >> <file>`, its own call. A task's verdicts ride an empty commit, `git commit --allow-empty -F <message file>`, subject `test(<scope>): <task> proven by infra/scripts/mutate-probe.sh`, its body the probes file whole and the trailers. A case that skips without the binary is not probed (`probe skipped: the case skips without an alloy binary`).
- No `ansible-playbook` run, converge, push, `grafana-query.py` read or network call in a task but Task 10's download; the rollout is the owner's.

## Rulings where the spec is silent, and where it cannot be implemented as written

- **D3, as amended in c695bf31a**: the canary's filter is the shape the ops regex stage ships, `|~ "^\\S+ \\[\\S+\\] - "` — the stage ends in `stage.output { source = "rest" }`, so a parsed line leaves Alloy without its timestamp, and the first draft's timestamp filter would have counted nothing and paged the critical canary (`lt 1`, `noDataState: Alerting`) for good; its one dashboard copy is refId F of panel 103, the board's other ops target being `zcrypto-ops-log-pipeline-dead`'s, which D3 leaves as it is.
- The hc backup's lines carry their own level word in the fleet's Python shape; D1's mechanism is kept — two trailing blocks, ERROR and INFO by the word — rather than a second regex stage on hc. Cost if wrong: a WARNING the script never prints today ships with no level and D9 pages it once.
- A self-check line ending `-> healthy, and no ping URL is set` is WARNING with D1's three: the dead-man pages the missing ping and the line explains it. Cost if wrong: a misconfigured node's line every five minutes reads WARNING.
- A tape-bars per-day `  ERROR <pair> <day>: …` line is ERROR: it is the source's own word and no other rule pages a single day's failure promptly (`zcrypto-ops-tapebars-not-advancing` reads staleness), as D1 rules a prune's refusal. It pages `Ops · ERROR logs` (warning, `logs`). Cost if wrong: a day the sweep heals on its next run pages once per run it recurs.
- verified-replay: `MISMATCH` and `VALIDATION-FAILED` and the runner's "journal has not caught up" or "freshness unproven" echoes are WARNING (the exit-code and staleness rules page them; the runner's own comment rules WARNING for such lines); `ok`, a `failed cycle` sidecar, the `replayed …` summary, `no journaled cycles found` and the runner's "capped at" echo are INFO. verify-replay's `AUDIT MISMATCH` lines are WARNING, the `logger.error` beside them paging. Cost if wrong: a sidecar day reads INFO in the logs view, its failure paged when the cycle ran.
- Valkey's and Sentinel's `<pid>:signal-handler (…) Received SIGTERM …` is WARNING, the level Valkey logs it at; `monotonic: … 'constant_tsc' flag not present` is INFO.
- The node's four re-level blocks select `level="ERROR"` (or `level=~"ERROR|WARNING"` for the cancelled context) and set INFO; `zcrypto-mon-grafana-error-logs` and panel 911 keep both exclusions as written, the `signal: terminated` one too (D5 names only the `context canceled` one; it stays redundant and harmless).
- D9's rule names `host=~".+"` in the `zcrypto-mon` group, which `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group` refuses; the test takes an exception beside `zcrypto-mon-ingest-dark`'s. The node rules' pattern carries a Fleet health panel, so D9's is panel 912, full width at y 144, and the `Dead-man node` row and its panels move down 8.
- D2 gets a guard: no Alloy config's live text names `__journal_priority`.
- The real-Alloy reading is the controller's (Task 10), against the release binary of the fleet's `alloy_version`, before the pull request: the harness cases skip everywhere else.
- The rule push follows the ops converge and precedes the cache nodes' and the capture pair's: D3's canary is blind from the ops converge until its push, and the cache and capture sources print unlevelled lines only at a restart or at the daily prunes (01:23Z, 03:17Z), so D9 pages nothing of a host still to converge if the wave lands within the day. Cost if wrong: one D9 page for such a source, read as its fix already in flight.
- The capture primary converges no earlier than an hour after the secondary's deploy-log row, the hour D11's no-level read waits.
- A source that prints only daily or at a restart is read by value at its next line, not within the hour; until then Task 10's harness is its proof.
- Rule titles stay: `Ops · unit log parse dead (no leveled lines)` keeps its title and its summary's "LEVEL-PARSED" wording, which D3's filter now means exactly.

## File structure

- Create `tests/test_infra_alloy_levels.py`: the level model, the fixtures, the structural guards over all five configs, the D2 guard and the real-Alloy harness.
- Modify the five configs `infra/ansible/roles/{mon,hc,ops,capture,cache}/files/config.alloy`: trailing blocks per host; hc also takes the fleet's logfmt block for its own Alloy; the capture and cache configs' comments that the change makes false.
- Modify `infra/grafana/alerts.yaml` (`zcrypto-ops-unit-parse-dead`'s expression, the new `zcrypto-mon-unlevelled-log-lines`), `infra/grafana/zcrypto-logs-dashboard.json` (refId F), `infra/grafana/fleet-health-dashboard.json` (panel 912 and the row's shift).
- Modify `infra/ansible/roles/mon/templates/grafana.ini.j2`, `infra/ansible/roles/engine/templates/haproxy.cfg.j2`.
- Modify tests `tests/test_infra_alert_rules.py`, `tests/test_infra_mon_role.py`, `tests/test_infra_cache_proxy.py`.
- Modify runbooks `infra/runbooks/mon.md`, `hc.md`, `observability.md`, `ops-node.md`. `cache.md`'s step 4 of `zcrypto-cache-proxy-no-backend` and `hosts.md`'s `zcrypto-capture-prune` paragraph stay true (the Logs board still shows the proxy's lines, the stderr copy of each state event among them; the prune's line is still in Loki under its container) and are not edited.

## Review Focus

1. A shape a source prints on a path the 24-hour read did not see — a self-check with no ping URL, a prune's refusal, a replay stopped on an unpulled journal, an `AUDIT MISMATCH` — takes the level of what it reports. Pinned by Tasks 1–5's fixtures `hc_selfcheck_no_ping_url`, `capture_prune_refused`, `engine_journal_prune_refused`, `ops_verified_replay_journal_behind`, `ops_verify_replay_audit_mismatch`.
2. A line that already carries a level reaching a trailing block — a Valkey `#` line, HAProxy's `[WARNING]` copy, a parsed ops record — is left as it is. Pinned by Task 1's `test_a_trailing_stage_sets_a_level_only_where_none_is_set` and `test_a_level_is_set_after_every_parse`, and by Tasks 3 and 5's `test_a_dropped_line_is_a_copy_its_source_ships_with_a_level`.
3. A real failure whose text resembles a no-fault shape — Loki's `err=EOF`, the quotas API at 500, a notifier line naming its receiver, a plugin killed by another signal, a stale session's `error="user token not found"` — keeps its level. Pinned by Task 1's `mon_loki_scheduler_eof`, `mon_grafana_quotas_500`, `mon_grafana_notifier_failure`, `mon_grafana_plugin_killed`, `mon_grafana_stale_session`.
4. The ops regex stage broken while the trailing blocks still level the bare echoes — the canary still reads 0 and pages. Pinned by Task 4's `test_the_unit_parse_canary_counts_the_lines_the_regex_stage_parsed`.
5. A line no stage names — a docker refusal in a runner, a text-formatter line from the clone, uWSGI's start-up banner at an hc restart — ships with no level and D9 pages it, one instance per source. Pinned by `ops_tape_bars_docker_refusal` and `hc_django_text_line` (expected `None`) and Task 7's `test_the_unlevelled_rule_pages_each_source_that_ships_a_line_with_no_level`; the banner is first classified when it first ships, by the new runbook section.

---

### Task 1: The level model, the node's stages, and the journal-priority guard (D1 on the node, D2, D5)

**Files:**
- Create: `tests/test_infra_alloy_levels.py`
- Modify: `infra/ansible/roles/mon/files/config.alloy` (inside `loki.process "parse"`, after the `{container="caddy"}` match, before the component's closing brace)
- Modify: `infra/runbooks/mon.md` (`zcrypto-mon-grafana-error-logs`, *What it means*, first paragraph)

**Interfaces:**
- Consumes: from `tests/test_infra_alloy_stages.py` `ALLOY_CONFIGS`, `_assigned`, `_blocks`, `_free_port`, `_parse_body`, `_stage_blocks`, `_unquoted`; `tests.alloy_text.live_alloy_text`; `tests.skip_gates.no_binary`.
- Produces (later tasks extend or import): `CONFIGS: dict[str, Path]`, `DROP = "DROP"`, `class Fixture(NamedTuple): id, host, labels, line, expected`, `FIXTURES: list[Fixture]` (appended to by Tasks 2, 3, 5, 6), `selector(text) -> (matchers, filters)`, `_top_blocks(host)`, `_keys_on_level(block)`, `_static_level(block)`, `level_blocks(host)`, `model(host, labels, line) -> str | None`, `_logfmt_level(line)`, `_parsed_level(host, labels, line) -> str | None`, `_run_alloy_groups(...)`.

- [ ] **Step 1: Write the failing test module** `tests/test_infra_alloy_levels.py`:

```python
"""Each host's level stages after its parse, driven over the line shapes its sources print. The model reads the
configs' own selectors; where an `alloy` binary is on PATH the same blocks also run through Alloy itself."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.alloy_text import live_alloy_text
from tests.skip_gates import no_binary
from tests.test_infra_alloy_stages import ALLOY_CONFIGS, _assigned, _blocks, _free_port, _parse_body, _stage_blocks, _unquoted

REPO = Path(__file__).resolve().parents[1]
CONFIGS = {host: REPO / f"infra/ansible/roles/{host}/files/config.alloy" for host in ("mon", "hc", "ops", "capture", "cache")}
DROP = "DROP"


class Fixture(NamedTuple):
    id: str
    host: str
    labels: dict[str, str]
    line: str
    expected: str | None


# The labels are the ones the level stages see, a level among them where the host's parse set one; numbers are filled
# in, and an address or a user name is a documentation one.
FIXTURES: list[Fixture] = [
    Fixture("mon_selfcheck_ok", "mon", {"container": "zcrypto-mon-selfcheck"}, "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> pinged", "INFO"),
    Fixture("mon_selfcheck_fail", "mon", {"container": "zcrypto-mon-selfcheck"}, "selfcheck: rules=FAIL (unreadable: URLError) fleet=FAIL (unreadable: URLError) loki=FAIL (unreadable: URLError) -> not pinging", "WARNING"),
    Fixture("mon_selfcheck_ping_failed", "mon", {"container": "zcrypto-mon-selfcheck"}, "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> ping failed: URLError", "WARNING"),
    Fixture("mon_grafana_panel_cancelled", "mon", {"container": "grafana-server", "level": "ERROR"}, r'logger=plugin.loki t=2026-11-03T16:37:12.345678901Z level=error msg="Partial data response error" dsName=Loki dsUid=grafanacloud-logs error="Get \"http://127.0.0.1:3100/loki/api/v1/query_range?direction=backward&end=1762187832000000000&query=sum%28rate%28%7Bhost%3D~%22zcrypto%22%7D%5B5m%5D%29%29&start=1762184232000000000&step=60000ms\": context canceled"', "INFO"),
    Fixture("mon_loki_mapping_cancelled", "mon", {"container": "loki", "level": "WARNING"}, r'ts=2026-11-03T16:37:30.123456789Z caller=spanlogger.go:111 middleware=QueryShard.astMapperware org_id=fake user=fake level=warn msg="failed mapping AST" err="context canceled" query="sum(rate({host=~\"zcrypto|zcrypto-red|ops\"} [5m]))"', "INFO"),
    Fixture("mon_loki_scheduler_cancelled", "mon", {"container": "loki", "level": "ERROR"}, 'level=error ts=2026-11-03T16:33:01.123456789Z caller=scheduler_processor.go:111 component=querier msg="error processing requests from scheduler" err="rpc error: code = Canceled desc = context canceled" addr=127.0.0.1:9095', "INFO"),
    Fixture("mon_loki_scheduler_eof", "mon", {"container": "loki", "level": "ERROR"}, 'level=error ts=2026-11-03T16:33:02.123456789Z caller=scheduler_processor.go:175 component=querier org_id=fake msg="error notifying scheduler about finished query" err=EOF addr=127.0.0.1:9095', "ERROR"),
    Fixture("mon_grafana_quotas_501", "mon", {"container": "grafana-server", "level": "ERROR"}, 'logger=context userId=2 orgId=1 uname=example-admin t=2026-11-03T16:32:41.123456789Z level=error msg="Request Completed" method=GET path=/apis/quotas.grafana.app/v0alpha1/namespaces/default/usage status=501 remote_addr=192.0.2.20 time_ms=1 duration=1.234567ms size=81', "INFO"),
    Fixture("mon_grafana_quotas_500", "mon", {"container": "grafana-server", "level": "ERROR"}, 'logger=context userId=2 orgId=1 uname=example-admin t=2026-11-03T16:32:41.123456789Z level=error msg="Request Completed" method=GET path=/apis/quotas.grafana.app/v0alpha1/namespaces/default/usage status=500 remote_addr=192.0.2.20 time_ms=1 duration=1.234567ms size=81', "ERROR"),
    Fixture("mon_grafana_contact_point_test", "mon", {"container": "grafana-server", "level": "ERROR"}, 'logger=ngalert.notifier t=2026-11-03T10:00:00.123456789Z level=error component=alertmanager orgID=1 receiver= integration=slack[0] version=v1 aggrGroup=slack-0a1b2c3d4e5f-6a7b8c9d0e1f msg="Missing notification reason"', "INFO"),
    Fixture("mon_grafana_notifier_failure", "mon", {"container": "grafana-server", "level": "ERROR"}, 'logger=ngalert.notifier t=2026-11-03T10:00:00.123456789Z level=error component=alertmanager orgID=1 receiver=logs integration=slack[0] version=v1 aggrGroup=slack-0a1b2c3d4e5f-6a7b8c9d0e1f msg="Missing notification reason"', "ERROR"),
    Fixture("mon_grafana_plugin_stop", "mon", {"container": "grafana-server", "level": "ERROR"}, 'logger=plugin.grafana-pyroscope-datasource t=2026-11-02T21:14:10.123456789Z level=error msg="plugin process exited" path=/usr/share/grafana/plugins-bundled/grafana-pyroscope-datasource/gpx_grafana-pyroscope-datasource_linux_amd64 pid=1234 error="signal: terminated"', "INFO"),
    Fixture("mon_grafana_plugin_killed", "mon", {"container": "grafana-server", "level": "ERROR"}, 'logger=plugin.grafana-pyroscope-datasource t=2026-11-02T21:14:10.123456789Z level=error msg="plugin process exited" path=/usr/share/grafana/plugins-bundled/grafana-pyroscope-datasource/gpx_grafana-pyroscope-datasource_linux_amd64 pid=1234 error="signal: killed"', "ERROR"),
    Fixture("mon_grafana_stale_session", "mon", {"container": "grafana-server", "level": "WARNING"}, 'logger=authn.service t=2026-11-03T09:55:01.123456789Z level=warn msg="Failed to authenticate request" client=auth.client.session error="user token not found"', "WARNING"),
]

_STRING = r'"((?:[^"\\]|\\.)*)"'
_LABEL_OPS = {
    "=": lambda value, want: value == want,
    "!=": lambda value, want: value != want,
    "=~": lambda value, want: re.fullmatch(want, value) is not None,
    "!~": lambda value, want: re.fullmatch(want, value) is None,
}
_LINE_OPS = {
    "|=": lambda line, want: want in line,
    "!=": lambda line, want: want not in line,
    "|~": lambda line, want: re.search(want, line) is not None,
    "!~": lambda line, want: re.search(want, line) is None,
}


def _unquote(literal: str) -> str:
    """A LogQL string literal's value; LogQL refuses an escape other than these two, and so does the model."""
    assert re.fullmatch(r'(?:[^\\]|\\[\\"])*', literal), f"an escape LogQL refuses: {literal!r}"
    return re.sub(r"\\(.)", r"\1", literal)


def selector(text: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """A stream selector's label matchers and the line filters after it, each value unquoted."""
    m = re.fullmatch(r"\{([^}]*)\}((?:\s*(?:\|=|\|~|!=|!~)\s*" + _STRING + r")*)\s*", text)
    assert m, f"a selector the model does not read whole: {text!r}"
    matchers = re.findall(r"(\w+)\s*(=~|!~|!=|=)\s*" + _STRING, m.group(1))
    assert ", ".join(f'{k}{op}"{v}"' for k, op, v in matchers) == m.group(1).strip(), m.group(1)
    filters = re.findall(r"(\|=|\|~|!=|!~)\s*" + _STRING, m.group(2))
    return [(k, op, _unquote(v)) for k, op, v in matchers], [(op, _unquote(v)) for op, v in filters]


def _admits(text: str, labels: dict[str, str], line: str) -> bool:
    matchers, filters = selector(text)
    return all(_LABEL_OPS[op](labels.get(k, ""), v) for k, op, v in matchers) and all(
        _LINE_OPS[op](line, v) for op, v in filters
    )


def _top_blocks(host: str) -> list[str]:
    return _blocks(_parse_body(live_alloy_text(CONFIGS[host])), "stage.match")


def _keys_on_level(block: str) -> bool:
    return any(k == "level" for k, _, _ in selector(_assigned(block, "selector"))[0])


def _static_level(block: str) -> str | None:
    m = re.search(r'stage\.static_labels \{\s*values = \{ level = "([A-Z]+)" \}', block)
    return m and m.group(1)


def level_blocks(host: str) -> list[tuple[str, str]]:
    """The host's top-level blocks that key on `level`, in pipeline order: each selector with its level or DROP."""
    out = []
    for block in _top_blocks(host):
        if not _keys_on_level(block):
            continue
        if _assigned(block, "action") == "drop":
            out.append((_assigned(block, "selector"), DROP))
            continue
        assert len(_stage_blocks(block)) == 1 and _static_level(block), f"a level-keyed block the model does not read:\n{block}"
        out.append((_assigned(block, "selector"), _static_level(block)))
    return out


def model(host: str, labels: dict[str, str], line: str) -> str | None:
    """The level the host's level-keyed blocks leave on a line, None for none, DROP for a dropped line."""
    labels = dict(labels)
    for text, action in level_blocks(host):
        if _admits(text, labels, line):
            if action == DROP:
                return DROP
            labels["level"] = action
    return labels.get("level")


def _logfmt_level(line: str) -> str | None:
    m = re.search(r"(?:^| )level=(\w+)(?: |$)", line)
    return m and {"warn": "WARNING", "fatal": "CRITICAL"}.get(m.group(1), m.group(1).upper())


def _parser(host: str, labels: dict[str, str], line: str) -> str | None:
    """The block of the host's that parsed the line: the proxy's, which strips the prefix it selects on and relabels what
    it parsed, for a `cache-proxy` line; else the first that keys on no level and admits it."""
    if labels.get("container") == "cache-proxy":
        return next(b for b in _top_blocks(host) if _assigned(b, "pipeline_name") == "cache_proxy")
    blocks = [b for b in _top_blocks(host) if not _keys_on_level(b)]
    return next((b for b in blocks if _admits(_assigned(b, "selector"), labels, line)), None)


def _parsed_level(host: str, labels: dict[str, str], line: str) -> str | None:
    """The level the host's parse leaves on a line, read through the expressions its config carries."""
    block = _parser(host, labels, line)
    if block is None:
        return None
    if "stage.logfmt" in block:
        return _logfmt_level(line)
    if _assigned(block, "pipeline_name") == "cache_proxy":
        (expression,) = [e for e in re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block) if "?P<level>" in e]
        m = re.search(_unquote(expression), line)
        return m and {"ALERT": "CRITICAL", "NOTICE": "INFO"}.get(m.group("level"), m.group("level"))
    (expression,) = re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block)
    m = re.search(_unquote(expression), line)
    if m is None:
        return None
    if "level" in m.groupdict():
        return m.group("level").upper()
    return {"#": "WARNING", ".": "DEBUG"}.get(m.group("mark"), "INFO")


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES])
def test_each_line_takes_the_level_its_source_reports(fixture):
    assert model(fixture.host, fixture.labels, fixture.line) == fixture.expected


# The dead-man node's container lines are held by tests/test_infra_alloy_stages.py's container model: a line that is no
# JSON record reaches the level stages with no level.
@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES if f.host != "hc"])
def test_each_line_reaches_the_level_stages_as_its_hosts_parse_leaves_it(fixture):
    assert _parsed_level(fixture.host, fixture.labels, fixture.line) == fixture.labels.get("level")


def test_a_level_is_set_after_every_parse():
    for host in CONFIGS:
        blocks = _top_blocks(host)
        parses = [i for i, b in enumerate(blocks) if not _keys_on_level(b)]
        levels = [i for i, b in enumerate(blocks) if _static_level(b) or ("level", "=", "") in selector(_assigned(b, "selector"))[0]]
        assert not levels or max(parses) < min(levels), f"{host}: a parse runs after a level stage, blocks {parses} and {levels}"


_RELEVELLED = {("level", "=", "ERROR"), ("level", "=~", "ERROR|WARNING")}


def test_a_trailing_stage_sets_a_level_only_where_none_is_set():
    for host in CONFIGS:
        for block in _top_blocks(host):
            if not _static_level(block):
                continue
            matchers = selector(_assigned(block, "selector"))[0]
            on_level = {m for m in matchers if m[0] == "level"}
            if on_level == {("level", "=", "")}:
                continue
            containers = [v for k, _, v in matchers if k == "container"]
            assert host == "mon" and on_level and on_level <= _RELEVELLED and _static_level(block) == "INFO", (host, block)
            assert containers and all(set(c.split("|")) <= {"grafana-server", "loki"} for c in containers), block


def test_no_alloy_config_reads_the_journal_priority():
    readers = [c.relative_to(REPO).as_posix() for c in ALLOY_CONFIGS if "__journal_priority" in live_alloy_text(c)]
    assert not readers, f"the journal's priority is no line's level: {readers}"


# --- the same blocks, through Alloy itself ---------------------------------------------------------------------------
def _echoed(out: str) -> list[tuple[str, str | None, str]]:
    """Each `loki.echo` line Alloy wrote: its file, its level label, its entry."""
    rows = []
    for line in out.splitlines():
        if "component_id=loki.echo.out" not in line:
            continue
        labels = re.search(r' labels="((?:[^"\\]|\\.)*)"', line).group(1)
        level = re.search(r'level=\\"([A-Z]+)\\"', labels)
        entry = _unquoted(re.search(r' entry="((?:[^"\\]|\\.)*)"', line).group(1))
        rows.append((re.search(r'filename=\\"([^"\\]+)\\"', labels).group(1), level and level.group(1), entry))
    return rows


def _run_alloy_groups(
    alloy: str, tmp_path: Path, groups: list[tuple[dict[str, str], list[str]]], blocks: list[str]
) -> list[list[tuple[str | None, str]]]:
    """Each group's lines in a file of its own under its labels, through `blocks` as committed, into `loki.echo`; each
    group's survivors, read off Alloy's output after a fixed window, in the order its file holds them."""
    files = [tmp_path / f"group-{i}.log" for i in range(len(groups))]
    targets = []
    for path, (labels, lines) in zip(files, groups, strict=True):
        path.write_text("".join(line + "\n" for line in lines))
        targets.append("{" + ", ".join([f'__path__ = "{path}"', *(f'{k} = "{v}"' for k, v in labels.items())]) + "}")
    (tmp_path / "harness.alloy").write_text(
        'loki.source.file "sample" {\n'
        f"  targets    = [{', '.join(targets)}]\n"
        "  forward_to = [loki.process.parse.receiver]\n"
        "}\n\n"
        'loki.process "parse" {\n'
        "  forward_to = [loki.echo.out.receiver]\n\n" + "\n".join(blocks) + "}\n\n"
        'loki.echo "out" {}\n'
    )
    cmd = [alloy, "run", "--storage.path", str(tmp_path / "storage"), "--server.http.listen-addr", f"127.0.0.1:{_free_port()}"]
    try:
        done = subprocess.run([*cmd, str(tmp_path / "harness.alloy")], capture_output=True, text=True, timeout=6, cwd=tmp_path)
        streams = [done.stdout, done.stderr]
    except subprocess.TimeoutExpired as exc:  # Alloy runs until killed; the window is the read
        streams = [exc.stdout, exc.stderr]
    rows = _echoed("".join(s.decode() if isinstance(s, bytes) else (s or "") for s in streams))
    return [[(level, entry) for name, level, entry in rows if name == str(path)] for path in files]


@pytest.mark.parametrize("host", sorted({f.host for f in FIXTURES}))
def test_alloy_itself_agrees_with_the_level_model(host, tmp_path):
    if no_binary("alloy"):
        pytest.skip("no alloy binary on PATH; the model above is the guard, this is its check against the real stage engine")
    fixtures = [f for f in FIXTURES if f.host == host]
    keys = list(dict.fromkeys(json.dumps(f.labels, sort_keys=True) for f in fixtures))
    groups = [(json.loads(k) | {"host": host}, [f.line for f in fixtures if json.dumps(f.labels, sort_keys=True) == k]) for k in keys]
    blocks = [b for b in _top_blocks(host) if _keys_on_level(b)]
    expected = [[(f.expected, f.line) for f in fixtures if json.dumps(f.labels, sort_keys=True) == k and f.expected != DROP] for k in keys]
    assert _run_alloy_groups(shutil.which("alloy"), tmp_path, groups, blocks) == expected
```

- [ ] **Step 2: Run it to see it fail** — `uv run pytest tests/test_infra_alloy_levels.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`; expected `9 failed, 22 passed, 1 skipped`: the failures are `test_each_line_takes_the_level_its_source_reports` for `mon_selfcheck_ok`, `mon_selfcheck_fail`, `mon_selfcheck_ping_failed`, `mon_grafana_panel_cancelled`, `mon_loki_mapping_cancelled`, `mon_loki_scheduler_cancelled`, `mon_grafana_quotas_501`, `mon_grafana_contact_point_test`, `mon_grafana_plugin_stop`; the five counter-fixtures and every other case pass; `[mon]` of the harness skips.

- [ ] **Step 3: Add the node's blocks** — in `infra/ansible/roles/mon/files/config.alloy`, after the `{container="caddy"}` match's closing `  }` and a blank line, before the `}` that closes `loki.process "parse"`:

```
  // Four shapes Grafana or Loki log at ERROR or WARNING that report no fault, re-levelled to INFO after the parse
  // above: an error that is a cancelled context (a panel the browser left), the dashboards page asking for the quotas
  // API this build does not serve, a contact-point test's empty receiver, and a bundled plugin stopped with Grafana.
  // Loki's EOF from the scheduler beside the cancellations keeps its level.
  stage.match {
    selector = "{container=~\"grafana-server|loki\", level=~\"ERROR|WARNING\"} |~ \"\\\\berr(or)?=\\\"(?:[^\\\"\\\\\\\\]|\\\\\\\\.)*context canceled\\\"\""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"grafana-server\", level=\"ERROR\"} |= \"msg=\\\"Request Completed\\\"\" |= \" path=/apis/quotas.grafana.app/\" |= \" status=501 \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"grafana-server\", level=\"ERROR\"} |= \"logger=ngalert.notifier \" |= \" receiver= \" |= \"msg=\\\"Missing notification reason\\\"\""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"grafana-server\", level=\"ERROR\"} |= \"msg=\\\"plugin process exited\\\"\" |= \"signal: terminated\""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  // The self-check prints one line a run and no level; levelled after every parse above, so a parsed level is never
  // overwritten. A failing probe's line explains the page its missing ping raises.
  stage.match {
    selector = "{container=\"zcrypto-mon-selfcheck\", level=\"\"} |~ \"^selfcheck: .*(=FAIL|-> not pinging|-> ping failed|-> healthy, and no ping URL is set)\""

    stage.static_labels {
      values = { level = "WARNING" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-mon-selfcheck\", level=\"\"} |~ \"^selfcheck: \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }
```

- [ ] **Step 4: Run it to see it pass** — Step 2's command; expected `31 passed, 1 skipped`.

- [ ] **Step 5: The runbook** — in `infra/runbooks/mon.md`, section `zcrypto-mon-grafana-error-logs`, *What it means*, first paragraph, replace the text from `So are a restart's plugin stops:` through `still shows it.` (the two sentences on the plugin stops and the cancelled context) with:

```
Four shapes that report no fault reach the node at INFO, re-levelled by its Alloy as it ingests them: a restart's plugin stops, each bundled datasource plugin's `plugin process exited` with `error="signal: terminated"`; a line from Grafana or Loki whose error is a cancelled context, bare or wrapped as `Get "<url>": context canceled` — a Loki panel query the browser cancelled, logged by `plugin.loki`, and a restart's `job cleanup controller failed`; the dashboards page's `Request Completed` for `path=/apis/quotas.grafana.app/` at `status=501`, an API this build does not serve; and a contact-point test's `Missing notification reason` with an empty `receiver=`. The rule's own exclusions of the first two stay as written. A plugin that dies by another signal or error pages, as do the quotas API at another status and a notifier line naming its receiver. The cost, taken on purpose, is that a real failure reporting nothing but a cancelled context does not page; step 2's read with its level matcher widened to `level=~"ERROR|CRITICAL|INFO"` shows it.
```

- [ ] **Step 6: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/mon/files/config.alloy infra/runbooks/mon.md) tests/test_infra_alloy_levels.py tests/test_infra_alloy_stages.py"`, then the Global Constraints' pytest line; expected all pass, the harness case skipped; then `uv run pre-commit run -a` until clean.

- [ ] **Step 7: Commit**

```bash
git -C /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/mon-rule-noise add tests/test_infra_alloy_levels.py infra/ansible/roles/mon/files/config.alloy infra/runbooks/mon.md
```

```bash
git -C /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/mon-rule-noise commit -F - <<'EOF'
fix(alloy): the node's lines take a level — the self-check by its verdict, four no-fault Grafana and Loki shapes at INFO

The node's parse ends in blocks keyed on level="" that level the self-check's line, WARNING on a failing
probe, and four blocks that re-level a cancelled context's error, the quotas API's 501, a contact-point
test and a plugin stopped with Grafana to INFO. tests/test_infra_alloy_levels.py models every host's
level-keyed blocks from the configs' selectors, holds that they run after each parse and set a level
only where none is set, and that no config reads the journal's priority.

<the pytest result line>

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV
EOF
```

- [ ] **Step 8: Probe** — `: > .local/fleet-log-levels/probes-task-1.txt`, then each arm; the file is `infra/ansible/roles/mon/files/config.alloy` and the test file `tests/test_infra_alloy_levels.py` unless the arm says otherwise:
  - 1a: `-k 'takes_the_level and mon_loki_mapping_cancelled'`; mutation `/context canceled/s/level=~\\"ERROR|WARNING\\"/level=~\\"CRITICAL\\"/`
  - 1b: `-k 'takes_the_level and mon_grafana_quotas_501'`; mutation `/status=501/s/level=\\"ERROR\\"/level=\\"CRITICAL\\"/`
  - 1c: `-k 'takes_the_level and mon_grafana_contact_point_test'`; mutation `/Missing notification reason/s/level=\\"ERROR\\"/level=\\"CRITICAL\\"/`
  - 1d: `-k 'takes_the_level and mon_grafana_plugin_stop'`; mutation `/signal: terminated/s/level=\\"ERROR\\"/level=\\"CRITICAL\\"/`
  - 1e: `-k 'takes_the_level and mon_selfcheck_fail'`; mutation `/no ping URL is set/s/level=\\"\\"/level=\\"X\\"/`
  - 1f: `-k 'takes_the_level and mon_selfcheck_ok'`; mutation `/selfcheck: \\""$/s/level=\\"\\"/level=\\"X\\"/`
  - 1g: `-k 'takes_the_level and mon_loki_scheduler_eof'`; mutation `/context canceled/s/ |~ .*"$/ |= \\"err\\""/`
  - 1h: `-k 'takes_the_level and mon_grafana_stale_session'`; mutation `/context canceled/s/ |~ .*"$/ |= \\"error=\\""/`
  - 1i: `-k 'takes_the_level and mon_grafana_quotas_500'`; mutation `/status=501/s/ |= \\" status=501 \\"//`
  - 1j: `-k 'takes_the_level and mon_grafana_notifier_failure'`; mutation `/Missing notification reason/s/ |= \\" receiver= \\"//`
  - 1k: `-k 'takes_the_level and mon_grafana_plugin_killed'`; mutation `/signal: terminated/s/ |= \\"signal: terminated\\"//`
  - 1l: `-k test_a_level_is_set_after_every_parse`; mutation `s/selector = "{container=~\\"grafana-server|prometheus|loki|alloy\\"}"/selector = "{container=~\\"grafana-server|prometheus|loki|alloy\\", level=\\"\\"}"/`
  - 1m: `-k test_a_trailing_stage_sets_a_level_only_where_none_is_set`; mutation `/no ping URL is set/s/, level=\\"\\"//`
  - 1n: `-k 'reaches_the_level_stages and mon_loki_scheduler_eof'`; mutation `s/grafana-server|prometheus|loki|alloy/grafana-server|prometheus|alloy/`
  - 1o: file `infra/ansible/roles/hc/files/config.alloy`, control `1i __journal_priority`; `-k test_no_alloy_config_reads_the_journal_priority`; mutation `s/source_labels = \["__journal__systemd_unit", "__journal_container_name"\]/source_labels = ["__journal__systemd_unit", "__journal_priority_keyword"]/`
  - The harness case: not probed, it skips without the binary.

- [ ] **Step 9: Record the verdicts** — the empty commit, subject `test(alloy): the node's level stages proven by infra/scripts/mutate-probe.sh`, its body `.local/fleet-log-levels/probes-task-1.txt` whole and the trailers.

### Task 2: The dead-man node's stages (D1 on `zcrypto-hc`)

**Files:**
- Modify: `infra/ansible/roles/hc/files/config.alloy` (inside `loki.process "parse"`, after the `{container="hc"}` match, before the component's closing brace)
- Modify: `tests/test_infra_alloy_levels.py` (fixtures appended to `FIXTURES`; `HC_ALLOY_LINES`, `_alloy_match`, one test)
- Modify: `infra/runbooks/hc.md` (`zcrypto-hc-service-down`, *What to do* step 3, its last sentence)

**Interfaces:**
- Consumes: Task 1's `Fixture`, `FIXTURES`, `_top_blocks`, `_stage_blocks`, `_logfmt_level`, `_assigned`.
- Produces: `HC_ALLOY_LINES`, `_alloy_match(host) -> str`.

- [ ] **Step 1: Write the failing tests** — append to `FIXTURES`:

```python
    Fixture("hc_selfcheck_ok", "hc", {"container": "zcrypto-hc-selfcheck"}, "selfcheck: web=ok (answered OK) -> pinged", "INFO"),
    Fixture("hc_selfcheck_fail", "hc", {"container": "zcrypto-hc-selfcheck"}, "selfcheck: web=FAIL (answered 500) -> not pinging", "WARNING"),
    Fixture("hc_selfcheck_ping_failed", "hc", {"container": "zcrypto-hc-selfcheck"}, "selfcheck: web=ok (answered OK) -> ping failed: HTTPError", "WARNING"),
    Fixture("hc_selfcheck_no_ping_url", "hc", {"container": "zcrypto-hc-selfcheck"}, "selfcheck: web=ok (answered OK) -> healthy, and no ping URL is set", "WARNING"),
    Fixture("hc_sqlite_backup_done", "hc", {"container": "zcrypto-sqlite-backup"}, "2026-11-03 02:47:01,234 INFO zcrypto.sqlite-backup [zcrypto-sqlite-backup.sh] - backed up /data/hc.sqlite to /data/backups/hc-2026-11-03T024701Z.sqlite and copied it into /var/backups/zcrypto-hc", "INFO"),
    Fixture("hc_sqlite_backup_failed", "hc", {"container": "zcrypto-sqlite-backup"}, "2026-11-03 02:47:01,234 ERROR zcrypto.sqlite-backup [zcrypto-sqlite-backup.sh] - VACUUM INTO /data/backups/hc-2026-11-03T024701Z.sqlite from /data/hc.sqlite failed", "ERROR"),
    Fixture("hc_uwsgi_cron_start", "hc", {"container": "hc"}, 'Tue Nov  3 03:17:01 2026 - [uwsgi-cron] running "./manage.py prune --skip-checks" (pid 4321)', "INFO"),
    Fixture("hc_uwsgi_cron_exit", "hc", {"container": "hc"}, '[uwsgi-cron] command "./manage.py prune --skip-checks" running with pid 4321 exited after 3 second(s)', "INFO"),
    Fixture("hc_prune_summary", "hc", {"container": "hc"}, "Deleted api_ping 1440, api_notification 0, api_flip 2, api_tokenbucket 0, django_session 3, django_admin_log 0; freed 12 SQLite pages, 0 left free; checkpointed 12 of 12 WAL frames", "INFO"),
    Fixture("hc_django_text_line", "hc", {"container": "hc"}, "2026-10-05 18:01:02,345 ERROR django.request Internal Server Error: /ping/REDACTED/zcrypto-capture", None),
```

and after `test_no_alloy_config_reads_the_journal_priority`:

```python
HC_ALLOY_LINES = [
    'ts=2026-11-03T15:08:01.234567891Z level=info msg="series GC completed" component_path=/ component_id=prometheus.remote_write.mon subcomponent=wal duration=1.234ms',
    'ts=2026-11-03T15:57:01.234567891Z level=info msg="usage report sent with success"',
]


def _alloy_match(host: str) -> str:
    (match,) = [b for b in _top_blocks(host) if _assigned(b, "selector") == '{container="alloy"}']
    return match


def test_the_dead_man_nodes_alloy_parses_its_logfmt_as_the_fleets_do():
    hc, fleet = ([" ".join(stage.split()) for stage in _stage_blocks(_alloy_match(host))] for host in ("hc", "cache"))
    assert hc == fleet
    assert [_logfmt_level(line) for line in HC_ALLOY_LINES] == ["INFO", "INFO"]
```

- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_infra_alloy_levels.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`; expected `10 failed, 32 passed, 2 skipped`: the nine hc fixtures but `hc_django_text_line`, and the logfmt case on `ValueError` (no `{container="alloy"}` match on hc).

- [ ] **Step 3: Add the dead-man node's blocks** — in `infra/ansible/roles/hc/files/config.alloy`, after the `{container="hc"}` match's closing `  }` and a blank line:

```
  // Alloy's own logs are logfmt with a `level` key, parsed as on the fleet's other hosts.
  stage.match {
    selector = "{container=\"alloy\"}"

    stage.logfmt {
      mapping = { "level" = "" }
    }

    stage.template {
      source   = "level"
      template = "{{ if eq .Value \"warn\" }}WARNING{{ else if eq .Value \"fatal\" }}CRITICAL{{ else }}{{ ToUpper .Value }}{{ end }}"
    }

    stage.labels {
      values = { level = "level" }
    }
  }

  // The sources that print no level, levelled by the shape they print after every parse above, so a parsed level is
  // never overwritten: the self-check's failing line explains the page its missing ping raises; the backup prints the
  // fleet's Python line shape with its own level word; uWSGI's cron lines and the prune command's summary report a run.
  stage.match {
    selector = "{container=\"zcrypto-hc-selfcheck\", level=\"\"} |~ \"^selfcheck: .*(=FAIL|-> not pinging|-> ping failed|-> healthy, and no ping URL is set)\""

    stage.static_labels {
      values = { level = "WARNING" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-hc-selfcheck\", level=\"\"} |~ \"^selfcheck: \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-sqlite-backup\", level=\"\"} |~ \"^\\\\d{4}-\\\\d{2}-\\\\d{2} \\\\d{2}:\\\\d{2}:\\\\d{2},\\\\d{3} ERROR \""

    stage.static_labels {
      values = { level = "ERROR" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-sqlite-backup\", level=\"\"} |~ \"^\\\\d{4}-\\\\d{2}-\\\\d{2} \\\\d{2}:\\\\d{2}:\\\\d{2},\\\\d{3} INFO \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"hc\", level=\"\"} |~ \"\\\\[uwsgi-cron\\\\] |^Deleted api_ping \\\\d+, \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }
```

- [ ] **Step 4: Run them to see them pass** — Step 2's command; expected `42 passed, 2 skipped`; then `uv run pytest tests/test_infra_hc_role.py tests/test_infra_alloy_stages.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` passes unchanged (the `{container="hc"}` match is still the one `_hc_match` finds, its stages `replace`, `json`, `labels`).

- [ ] **Step 5: The runbook** — in `infra/runbooks/hc.md`, `zcrypto-hc-service-down` step 3, replace `The second counts lines that are not the service's JSON records, uWSGI's own among them.` with:

```
The second counts lines that are neither the service's JSON records nor uWSGI's cron lines, which the node's Alloy levels INFO: a start-up banner or a traceback, each of which `zcrypto-mon-unlevelled-log-lines` pages from the observability node.
```

- [ ] **Step 6: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/hc/files/config.alloy infra/runbooks/hc.md) tests/test_infra_alloy_levels.py"`, the pytest line, then the gate.

- [ ] **Step 7: Commit** — the add of `tests/test_infra_alloy_levels.py infra/ansible/roles/hc/files/config.alloy infra/runbooks/hc.md`, then the commit as Task 1's fence, subject `fix(alloy): the dead-man node's lines take a level — its Alloy's logfmt, the self-check, the backup's own word, uWSGI's cron`, its body what changed and the result line.

- [ ] **Step 8: Probe** — `: > .local/fleet-log-levels/probes-task-2.txt`; the file `infra/ansible/roles/hc/files/config.alloy`:
  - 2a: `-k 'takes_the_level and hc_selfcheck_fail'`; mutation `/no ping URL is set/s/level=\\"\\"/level=\\"X\\"/`
  - 2b: `-k 'takes_the_level and hc_selfcheck_ok'`; mutation `/selfcheck: \\""$/s/level=\\"\\"/level=\\"X\\"/`
  - 2c: `-k 'takes_the_level and hc_sqlite_backup_failed'`; mutation `/ ERROR \\""$/s/level=\\"\\"/level=\\"X\\"/`
  - 2d: `-k 'takes_the_level and hc_sqlite_backup_done'`; mutation `/ INFO \\""$/s/level=\\"\\"/level=\\"X\\"/`
  - 2e: `-k 'takes_the_level and hc_uwsgi_cron_exit'`; mutation `/uwsgi-cron/s/level=\\"\\"/level=\\"X\\"/`
  - 2f: `-k 'takes_the_level and hc_django_text_line'`; mutation `/uwsgi-cron/s/ |~ .*"$/"/`
  - 2g: `-k test_the_dead_man_nodes_alloy_parses_its_logfmt_as_the_fleets_do`; mutation `/{container=\\"alloy\\"}"$/,/stage.labels/s/}}WARNING{{/}}WARN{{/`

- [ ] **Step 9: Record the verdicts** — the empty commit, subject `test(alloy): the dead-man node's level stages proven by infra/scripts/mutate-probe.sh`.

### Task 3: The ops units' stages and the echoed copies dropped (D1 and D4 on `zcrypto-ops`)

**Files:**
- Modify: `infra/ansible/roles/ops/files/config.alloy` (inside `loki.process "parse"`, after the `{container="alloy"}` match, before the component's closing brace)
- Modify: `tests/test_infra_alloy_levels.py` (fixtures; `TWINS` and one test)
- Modify: `infra/runbooks/ops-node.md` (`zcrypto-ops-error-logs`, *What it means*, the paragraph opening **Silence here is not a clean bill**)

**Interfaces:**
- Consumes: Task 1's model and `_parsed_level`.
- Produces: `TWINS: dict[str, str]` (fixture id → the levelled copy its source ships), extended by Task 5; the ops fixtures, which Task 4 reads.

- [ ] **Step 1: Write the failing tests** — append to `FIXTURES`:

```python
    Fixture("ops_tape_bars_summary", "ops", {"container": "zcrypto-tape-bars"}, "days_written=1 days_skipped=0 days_unsettled=0 days_unhealed=0 days_gap=0 rows=4320 errors=0", "INFO"),
    Fixture("ops_tape_bars_head", "ops", {"container": "zcrypto-tape-bars"}, "head=2026-11-02 days_written=1 holes=0", "INFO"),
    Fixture("ops_tape_bars_day_error", "ops", {"container": "zcrypto-tape-bars"}, "  ERROR BTC/EUR 2026-11-02: no settled trades file for the day", "ERROR"),
    Fixture("ops_tape_bars_docker_refusal", "ops", {"container": "zcrypto-tape-bars"}, 'docker: Error response from daemon: Conflict. The container name "/zcrypto-tape-bars" is already in use by container "0123abcd".', None),
    Fixture("ops_verified_replay_ok", "ops", {"container": "zcrypto-verified-replay"}, "2026-11-02T00:00:00+00:00  ok (worst |diff| 0.00e+00)", "INFO"),
    Fixture("ops_verified_replay_mismatch", "ops", {"container": "zcrypto-verified-replay"}, "2026-11-02T04:00:00+00:00  MISMATCH: worst BTC |diff| 1.20e-03", "WARNING"),
    Fixture("ops_verified_replay_invalid", "ops", {"container": "zcrypto-verified-replay"}, "2026-11-02T08:00:00+00:00  VALIDATION-FAILED: cycle record carries no final targets", "WARNING"),
    Fixture("ops_verified_replay_failed_cycle", "ops", {"container": "zcrypto-verified-replay"}, "2026-11-02T12:00:00+00:00  failed cycle (venue read failed)", "INFO"),
    Fixture("ops_verified_replay_summary", "ops", {"container": "zcrypto-verified-replay"}, "replayed 6 success record(s) via the verified path: 6 ok, 0 mismatch(es), 0 validation failure(s); 0 failed cycle(s) (sidecars)", "INFO"),
    Fixture("ops_verified_replay_none_found", "ops", {"container": "zcrypto-verified-replay"}, "no journaled cycles found", "INFO"),
    Fixture("ops_verified_replay_capped", "ops", {"container": "zcrypto-verified-replay"}, "verified-replay: capped at 30 day(s) this run; 4 day(s) still unverified, resuming tomorrow", "INFO"),
    Fixture("ops_verified_replay_journal_behind", "ops", {"container": "zcrypto-verified-replay"}, "verified-replay: journal has not caught up: /mnt/zhao-crypto/engine-journal/2026-11-02 holds no cycle artifacts; stopping without advancing the watermark (day 2026-11-02 retries next run)", "WARNING"),
    Fixture("ops_verify_replay_census", "ops", {"container": "zcrypto-verify-replay"}, "verify-replay census replayed=12 reused=8748 audited=24 mismatches=0 pending=0 evicted=0 duration_s=312", DROP),
    Fixture("ops_verify_replay_summary", "ops", {"container": "zcrypto-verify-replay"}, "replayed 8772 hour(s): 8772 ok, 0 failed", DROP),
    Fixture("ops_verify_replay_audit_mismatch", "ops", {"container": "zcrypto-verify-replay"}, "AUDIT MISMATCH  BTC/EUR 2026-11-02T13  -- the re-replayed hour disagrees with the verdict served from cache", "WARNING"),
    Fixture("ops_archive_pull_backfill_echo", "ops", {"container": "zcrypto-archive-pull"}, "trade backfill complete pairs=10 gaps=0 trades_missing=0 duplicate_rows_found=0 recovered=0 unrecoverable=0 deferred=0 fetch_failed=0 mint_failed=0 duplicates_collapsed=0 duplicates_cross_hour=0 hours_minted=0 hours_repaired_after_loss=0 errors=0", DROP),
```

and at the end of the module:

```python
# Each dropped copy beside the line its source ships levelled: the logged record on ops, HAProxy's stderr copy on the
# engine host.
TWINS = {
    "ops_verify_replay_census": "2026-11-03 02:31:07,123 INFO zcrypto.archive.command [command.py:1305] - verify-replay census replayed=12 reused=8748 audited=24 mismatches=0 pending=0 evicted=0 duration_s=312",
    "ops_verify_replay_summary": "2026-11-03 02:31:07,124 INFO zcrypto.archive.command [command.py:1331] - verify-replay complete hours=8772 ok=8772 failed=0",
    "ops_archive_pull_backfill_echo": "2026-11-03 00:14:05,123 INFO zcrypto.trades.backfill [backfill.py:300] - trade backfill complete pairs=10 gaps=0 trades_missing=0 duplicate_rows_found=0 recovered=0 unrecoverable=0 deferred=0 fetch_failed=0 mint_failed=0 duplicates_collapsed=0 duplicates_cross_hour=0 hours_minted=0 hours_repaired_after_loss=0 errors=0",
}


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES if f.expected == DROP])
def test_a_dropped_line_is_a_copy_its_source_ships_with_a_level(fixture):
    assert set(TWINS) == {f.id for f in FIXTURES if f.expected == DROP}
    assert _parsed_level(fixture.host, fixture.labels, TWINS[fixture.id]) in {"INFO", "WARNING", "CRITICAL"}
```

- [ ] **Step 2: Run them to see them fail** — the levels command; expected `15 failed, 62 passed, 3 skipped`: every ops fixture of `test_each_line_takes_the_level_its_source_reports` but `ops_tape_bars_docker_refusal`; the twins and reach cases pass (they read the parse, which this task leaves).

- [ ] **Step 3: Add the ops blocks** — in `infra/ansible/roles/ops/files/config.alloy`, after the `{container="alloy"}` match's closing `  }` and a blank line:

```
  // The runners' bare echoes, levelled by their own shape after the parse above, so a parsed level is never
  // overwritten: a day the tape-bars sweep failed is ERROR, a condition another rule pages is WARNING. An echo that
  // copies a record the CLI also logs is dropped, since the record ships levelled.
  stage.match {
    selector = "{container=\"zcrypto-tape-bars\", level=\"\"} |~ \"^  ERROR \""

    stage.static_labels {
      values = { level = "ERROR" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-tape-bars\", level=\"\"} |~ \"^(days_written|head)=\""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-verified-replay\", level=\"\"} |~ \"^\\\\S+  (MISMATCH|VALIDATION-FAILED)|^verified-replay: journal \""

    stage.static_labels {
      values = { level = "WARNING" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-verified-replay\", level=\"\"} |~ \"^\\\\S+  (ok \\\\(worst |failed cycle \\\\()|^replayed \\\\d+ success record|^no journaled cycles found$|^verified-replay: capped at \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector            = "{container=\"zcrypto-verify-replay\", level=\"\"} |~ \"^(verify-replay census |replayed \\\\d+ hour\\\\(s\\\\): )\""
    action              = "drop"
    drop_counter_reason = "typer_echo_copy"
  }

  stage.match {
    selector = "{container=\"zcrypto-verify-replay\", level=\"\"} |~ \"^AUDIT MISMATCH  \""

    stage.static_labels {
      values = { level = "WARNING" }
    }
  }

  stage.match {
    selector            = "{container=\"zcrypto-archive-pull\", level=\"\"} |~ \"^trade backfill complete \""
    action              = "drop"
    drop_counter_reason = "typer_echo_copy"
  }
```

- [ ] **Step 4: Run them to see them pass** — expected `77 passed, 3 skipped`; then `uv run pytest tests/test_error_paths_are_logged.py tests/test_infra_archive_pull_template.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` passes unchanged (one `stage.regex` on ops, the first `{container=~"zcrypto-.*"}` selector still the regex stage's).

- [ ] **Step 5: The runbook** — in `infra/runbooks/ops-node.md`, replace the paragraph opening `**Silence here is not a clean bill, and the reason is mechanical.**` with:

```
**Silence here is not a clean bill, and the reason is mechanical.** The `level` label is set by Alloy's parse stage, which matches only the Python-logging line shape (`YYYY-MM-DD HH:MM:SS,mmm LEVEL …`), and by the stages after it that level the runners' bare echoes by their own shape. `archive-pull.sh` and `verified-replay.sh` write the Python shape for their own warnings, at **WARNING**, so they show under the board's WARNING filter and never page here. Of the echoes, a tape-bars line reporting a failed day is levelled ERROR and pages here; the rest read INFO or WARNING, the echoed copies of `verify-replay`'s and the trade backfill's summaries are dropped beside their logged twins, and an echo of a shape no stage names ships with no level, which the observability node's `zcrypto-mon-unlevelled-log-lines` pages. A gate-skip streak produces no ERROR page by construction.
```

- [ ] **Step 6: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/ops/files/config.alloy infra/runbooks/ops-node.md) tests/test_infra_alloy_levels.py"`, the pytest line, the gate.

- [ ] **Step 7: Commit** — subject `fix(alloy): the ops units' echoes take a level by their shape, and the CLI's echoed copies of logged summaries are dropped`.

- [ ] **Step 8: Probe** — `: > .local/fleet-log-levels/probes-task-3.txt`; the file `infra/ansible/roles/ops/files/config.alloy`:
  - 3a: `-k 'takes_the_level and ops_tape_bars_day_error'`; mutation `/\^  ERROR /s/level=\\"\\"/level=\\"X\\"/`
  - 3b: `-k 'takes_the_level and ops_tape_bars_summary'`; mutation `/(days_written|head)=/s/level=\\"\\"/level=\\"X\\"/`
  - 3c: `-k 'takes_the_level and ops_tape_bars_docker_refusal'`; mutation `/(days_written|head)=/s/ |~ .*"$/"/`
  - 3d: `-k 'takes_the_level and ops_verified_replay_mismatch'`; mutation `/MISMATCH|VALIDATION-FAILED/s/level=\\"\\"/level=\\"X\\"/`
  - 3e: `-k 'takes_the_level and ops_verified_replay_ok'`; mutation `/no journaled cycles found/s/level=\\"\\"/level=\\"X\\"/`
  - 3f: `-k 'takes_the_level and ops_verify_replay_census'`; mutation `/verify-replay census /s/level=\\"\\"/level=\\"X\\"/`
  - 3g: `-k 'takes_the_level and ops_verify_replay_audit_mismatch'`; mutation `/AUDIT MISMATCH/s/level=\\"\\"/level=\\"X\\"/`
  - 3h: `-k 'takes_the_level and ops_archive_pull_backfill_echo'`; mutation `/trade backfill complete/s/level=\\"\\"/level=\\"X\\"/`
  - 3i: `-k 'reaches_the_level_stages and ops_tape_bars_summary'`; mutation `s/expression = "\^(?P<ts>.*$/expression = "^(?P<level>[a-z_]+)=(?P<rest>.*)$"/`
  - 3j: `-k 'is_a_copy_its_source_ships and ops_verify_replay_census'`; mutation `s/(?P<level>\[A-Z\]+)/(?P<level>[a-z]+)/`

- [ ] **Step 9: Record the verdicts** — the empty commit, subject `test(alloy): the ops units' level stages proven by infra/scripts/mutate-probe.sh`.

### Task 4: The ops parse canary counts what the regex stage parsed (D3)

**Files:**
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-ops-unit-parse-dead`: refId A's expression and the comment above it)
- Modify: `infra/grafana/zcrypto-logs-dashboard.json` (panel 103, refId F's `expr`)
- Modify: `tests/test_infra_alert_rules.py` (imports; one test after `test_the_ops_error_rule_selects_every_container_the_ops_log_plane_can_emit`)
- Modify: `infra/runbooks/observability.md` (`zcrypto-ops-log-plane`: the table's `zcrypto-ops-unit-parse-dead` row, the **Through Alloy** bullet, the **`unit-parse-dead` alone** bullet, step 4 under **For `unit-parse-dead`**)

**Interfaces:**
- Consumes: Task 3's ops fixtures (`FIXTURES`, `DROP` from `tests.test_infra_alloy_levels`); `_assigned`, `_blocks`, `_expressions`, `_parse_body` from `tests.test_infra_alloy_stages`; `cli.logging.formatters.PlainTextFormatter`.

- [ ] **Step 1: Write the failing test** — imports added to `tests/test_infra_alert_rules.py`: `import logging`, `from cli.logging.formatters import PlainTextFormatter`, `from tests.test_infra_alloy_levels import DROP, FIXTURES`, and `_assigned, _blocks, _expressions, _parse_body` beside the names already imported from `tests.test_infra_alloy_stages`; then:

```python
_PARSE_CANARY = (
    'sum by (host, container) (count_over_time({host="ops", container=~"zcrypto-.*", level=~".+"}'
    r' |~ "^\\S+ \\[\\S+\\] - " [26h])) or on() vector(0)'
)


def test_the_unit_parse_canary_counts_the_lines_the_regex_stage_parsed():
    """The trailing stages level the runners' bare echoes, so a level alone no longer proves the regex parsed: the
    canary counts the shape the stage's output ships, which no echo the trailing stages level carries."""
    assert _log_expr("zcrypto-ops-unit-parse-dead") == _PARSE_CANARY

    def panels(ps):
        for p in ps:
            yield p
            yield from panels(p.get("panels", []))

    board = json.loads((REPO / "infra/grafana/zcrypto-logs-dashboard.json").read_text())
    copies = [t["expr"] for p in panels(board["panels"]) for t in p.get("targets", []) if 'container=~"zcrypto-.*"' in t.get("expr", "")]
    assert copies == [_PARSE_CANARY]
    (shape,) = [re.sub(r"\\(.)", r"\1", s) for s in re.findall(r'\|~ "((?:[^"\\]|\\.)*)"', _PARSE_CANARY)]
    (stage,) = [b for b in _blocks(_parse_body(live_alloy_text(OPS_ALLOY)), "stage.match") if _assigned(b, "selector") == '{container=~"zcrypto-.*"}']
    assert re.search(r'stage\.output \{\s*source = "rest"\s*\}', stage), stage
    (regex,) = _expressions(stage)
    record = logging.LogRecord("zcrypto.archive.command", logging.INFO, "command.py", 1331, "verify-replay complete hours=1 ok=1 failed=0", (), None)
    shell = "2026-11-03 05:24:01,123 WARNING zcrypto.verified-replay [verified-replay.sh] - 2026-11-02 verified but its watermark could not be persisted"
    shipped = [re.match(regex, line).group("rest") for line in (PlainTextFormatter().format(record), shell)]
    assert all(re.search(shape, line) for line in shipped), shipped
    levelled = [f.line for f in FIXTURES if f.host == "ops" and f.expected not in (None, DROP)]
    assert levelled and not [line for line in levelled if re.search(shape, line)]
```

- [ ] **Step 2: Run it to see it fail** — `uv run pytest tests/test_infra_alert_rules.py -k unit_parse_canary -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected `1 failed` on the expression's equality.

- [ ] **Step 3: Change the rule and its copy** — in `infra/grafana/alerts.yaml`, `zcrypto-ops-unit-parse-dead`, refId A's `expr:` becomes:

```yaml
          expr: >-
            sum by (host, container) (count_over_time({host="ops", container=~"zcrypto-.*", level=~".+"} |~ "^\\S+ \\[\\S+\\] - " [26h])) or on() vector(0)
```

and the comment above refId A gains, after its `Level-filtered, …` paragraph:

```yaml
      # The line filter keeps what the stage.regex parsed, which its stage.output ships as
      # `<logger> [<file>] - <message>`: the stages after it level the runners' bare echoes by their own shape, and a
      # broken regex must still leave this count at 0.
```

In `infra/grafana/zcrypto-logs-dashboard.json`, panel 103 refId F's `expr` becomes:

```json
          "expr": "sum by (host, container) (count_over_time({host=\"ops\", container=~\"zcrypto-.*\", level=~\".+\"} |~ \"^\\\\S+ \\\\[\\\\S+\\\\] - \" [26h])) or on() vector(0)",
```

- [ ] **Step 4: Run it to see it pass** — Step 2's command, then `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected all pass (the red-line pairing still reads the rule and refId F as one expression).

- [ ] **Step 5: The runbook** — in `infra/runbooks/observability.md`, `zcrypto-ops-log-plane`, four edits, each old text then its replacement. The table row of `zcrypto-ops-unit-parse-dead`, its query cell:

```
| `{host="ops", container=~"zcrypto-.*", level=~".+"}` | 26 h |
```

```
| `{host="ops", container=~"zcrypto-.*", level=~".+"}`, its lines in the parse stage's output shape `^\S+ \[\S+\] - ` | 26 h |
```

The **Through Alloy** bullet's ending:

```
`{container="alloy"}` for Alloy's logfmt).
```

```
`{container="alloy"}` for Alloy's logfmt), and the scripts' bare echoes levelled after both by blocks keyed on each echo's own shape, which `unit-parse-dead`'s line filter leaves out of its count.
```

The **`unit-parse-dead` alone** bullet's opening:

```
Lines are arriving without a `level` label, which means
```

```
The units' Python-shaped lines are arriving without a `level` label — the observability node's `zcrypto-mon-unlevelled-log-lines` pages them beside it — which means
```

Step 4 under **For `unit-parse-dead` (the level label)**, whole:

```
4. Unparsed lines are **not** lost: `action_on_failure = "skip"` keeps their journal capture time; a Python-shaped line the regex misses arrives with no `level`, and the scripts' own echoes arrive levelled by their own shape, outside this rule's count.
```

- [ ] **Step 6: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/grafana/alerts.yaml infra/grafana/zcrypto-logs-dashboard.json infra/runbooks/observability.md) tests/test_infra_alert_rules.py"`, the pytest line, the gate.

- [ ] **Step 7: Commit** — subject `fix(grafana): the ops parse canary counts the regex stage's output shape, so a levelled echo cannot keep it green`.

- [ ] **Step 8: Probe** — `: > .local/fleet-log-levels/probes-task-4.txt`; the test file `tests/test_infra_alert_rules.py`, `-k test_the_unit_parse_canary_counts_the_lines_the_regex_stage_parsed` for each arm:
  - 4a: file `infra/grafana/alerts.yaml`; mutation `/container=~"zcrypto-.\*", level=~".+"}/s/} |~ .* \[26h\]/} [26h]/`
  - 4b: file `infra/grafana/zcrypto-logs-dashboard.json`; mutation `/container=~\\"zcrypto-.\*\\", level=~\\".+\\"}/s/} |~ .* \[26h\]/} [26h]/`
  - 4c: file `infra/ansible/roles/ops/files/config.alloy`; mutation `s/source = "rest"/source = "ts"/`

- [ ] **Step 9: Record the verdicts** — the empty commit, subject `test(grafana): the ops parse canary's line filter proven by infra/scripts/mutate-probe.sh`.

### Task 5: The capture hosts' stages — the prunes and the cache proxy (D1 and D4 on `zcrypto`, `zcrypto-red`)

**Files:**
- Modify: `infra/ansible/roles/capture/files/config.alloy` (inside `loki.process "parse"`, after the `{container="alloy"}` match, before the closing brace; the comment above `loki.process "parse"` and the cache-proxy block's comment)
- Modify: `tests/test_infra_alloy_levels.py` (fixtures; four `TWINS` entries)

**Interfaces:**
- Consumes: Task 1's model; Task 3's `TWINS` and twins test.

- [ ] **Step 1: Write the failing tests** — append to `FIXTURES`:

```python
    Fixture("capture_prune_done", "capture", {"container": "zcrypto-capture-prune"}, 'zcrypto-capture-prune: deleted=24 retention_days=14 cutoff="2026-10-20 03:17:01 UTC" dir=/var/lib/zcrypto-capture', "INFO"),
    Fixture("capture_prune_refused", "capture", {"container": "zcrypto-capture-prune"}, "capture data dir not found: /var/lib/zcrypto-capture", "ERROR"),
    Fixture("engine_journal_prune_done", "capture", {"container": "zcrypto-engine-journal-prune"}, 'zcrypto-engine-journal-prune: deleted=1 kept=30 retention_days=30 cutoff="2026-10-04 UTC" dir=/var/lib/zcrypto-engine/journal', "INFO"),
    Fixture("engine_journal_prune_refused", "capture", {"container": "zcrypto-engine-journal-prune"}, "engine journal dir not found: /var/lib/zcrypto-engine/journal", "ERROR"),
    Fixture("cache_proxy_server_up", "capture", {"container": "cache-proxy"}, 'Server node1/via-node1 is UP, reason: Layer7 check passed, code: 0, info: "(tcp-check)", check duration: 2ms. 3 active and 0 backup servers online. 0 sessions requeued, 0 total in queue.', DROP),
    Fixture("cache_proxy_server_down", "capture", {"container": "cache-proxy"}, 'Server node2/via-node3 is DOWN, reason: Layer4 timeout, info: " at step 1 of tcp-check (connect)", check duration: 2001ms. 2 active and 0 backup servers left. 0 sessions active, 0 requeued, 0 remaining in queue.', DROP),
    Fixture("cache_proxy_proxy_stopped", "capture", {"container": "cache-proxy"}, "Proxy node1 stopped (cumulated conns: FE: 0, BE: 12).", DROP),
    Fixture("cache_proxy_no_server", "capture", {"container": "cache-proxy"}, "backend node1 has no server available!", DROP),
    Fixture("cache_proxy_session", "capture", {"container": "cache-proxy"}, "192.0.2.10:51234 [03/Nov/2026:14:14:05.123] cache node1/via-node1 1/0/3601234 1234 -- 1/1/0/0/0 0/0", "INFO"),
    Fixture("cache_proxy_session_cut", "capture", {"container": "cache-proxy"}, "192.0.2.10:51236 [03/Nov/2026:14:19:02.456] cache node1/via-node1 1/0/1201 87 DC 2/2/1/1/0 0/0", "INFO"),
```

and to `TWINS`:

```python
    "cache_proxy_server_up": '[WARNING]  (8) : Server node1/via-node1 is UP, reason: Layer7 check passed, code: 0, info: "(tcp-check)", check duration: 2ms. 3 active and 0 backup servers online. 0 sessions requeued, 0 total in queue.',
    "cache_proxy_server_down": '[WARNING]  (8) : Server node2/via-node3 is DOWN, reason: Layer4 timeout, info: " at step 1 of tcp-check (connect)", check duration: 2001ms. 2 active and 0 backup servers left. 0 sessions active, 0 requeued, 0 remaining in queue.',
    "cache_proxy_proxy_stopped": "[WARNING]  (8) : Proxy node1 stopped (cumulated conns: FE: 0, BE: 12).",
    "cache_proxy_no_server": "[ALERT]    (8) : backend 'node1' has no server available!",
```

- [ ] **Step 2: Run them to see them fail** — the levels command; expected `10 failed, 91 passed, 4 skipped`: the ten capture fixtures of `test_each_line_takes_the_level_its_source_reports`.

- [ ] **Step 3: Add the capture blocks and correct two comments** — in `infra/ansible/roles/capture/files/config.alloy`, after the `{container="alloy"}` match's closing `  }` and a blank line:

```
  // The prunes' lines and the proxy's log-target lines, levelled by their shape after every parse above, so a parsed
  // level is never overwritten. A prune's line other than its summary is a refusal. The log target repeats each server
  // and proxy state event the proxy's stderr already shipped levelled, so its copy is dropped; a connection line has no
  // other copy.
  stage.match {
    selector = "{container=\"zcrypto-capture-prune\", level=\"\"} |~ \"^zcrypto-capture-prune: deleted=\\\\d+ \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-capture-prune\", level=\"\"}"

    stage.static_labels {
      values = { level = "ERROR" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-engine-journal-prune\", level=\"\"} |~ \"^zcrypto-engine-journal-prune: deleted=\\\\d+ \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }

  stage.match {
    selector = "{container=\"zcrypto-engine-journal-prune\", level=\"\"}"

    stage.static_labels {
      values = { level = "ERROR" }
    }
  }

  stage.match {
    selector            = "{container=\"cache-proxy\", level=\"\"} |~ \"^(Server \\\\S+ is |Proxy \\\\S+ stopped |backend \\\\S+ has no server available!)\""
    action              = "drop"
    drop_counter_reason = "haproxy_log_target_copy"
  }

  stage.match {
    selector = "{container=\"cache-proxy\", level=\"\"} |~ \"^\\\\S+:\\\\d+ \\\\[\""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }
```

The comment above `loki.process "parse"`, `// Parse ONCE, here at ingest -- never at query time. The prune and reboot-check units' bash lines` / `// fall through this component unmatched (no selector here admits them), keeping their journal` / `// capture time and no level label.`, becomes:

```
// Parse ONCE, here at ingest -- never at query time. The prune and reboot-check units' bash lines are parsed by no
// stage and keep their journal capture time; the prunes' lines take their level at the end of this component.
```

and the cache-proxy block's comment, its last three lines:

```
  // claims what is left of the unit. A traffic line and a server state line carry no level word and
  // ship with no level label: the inner match takes only a line opening with the word, since a
  // template over an absent value would label the rest "<no value>".
```

```
  // claims what is left of the unit. A traffic line and a server state line carry no level word: the
  // inner match takes only a line opening with the word, since a template over an absent value would
  // label the rest "<no value>"; the blocks at the end of this component level a traffic line and
  // drop a state line, which the proxy's stderr ships levelled.
```

- [ ] **Step 4: Run them to see them pass** — expected `101 passed, 4 skipped`; then `uv run pytest tests/test_infra_alloy_stages.py tests/test_infra_alloy_series.py tests/test_engine_journal_prune.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` passes unchanged (one nautilus stage and its drop; the proxy's block before the engine's).

- [ ] **Step 5: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/capture/files/config.alloy) tests/test_infra_alloy_levels.py"`, the pytest line, the gate.

- [ ] **Step 6: Commit** — subject `fix(alloy): the capture hosts' prunes and the cache proxy's lines take a level, the proxy's log-target copies of state events dropped`.

- [ ] **Step 7: Probe** — `: > .local/fleet-log-levels/probes-task-5.txt`; the file `infra/ansible/roles/capture/files/config.alloy`:
  - 5a: `-k 'takes_the_level and capture_prune_done'`; mutation `/zcrypto-capture-prune: deleted=/s/level=\\"\\"/level=\\"X\\"/`
  - 5b: `-k 'takes_the_level and capture_prune_refused'`; mutation `/capture-prune\\", level=\\"\\"}"$/s/level=\\"\\"/level=\\"X\\"/`
  - 5c: `-k 'takes_the_level and engine_journal_prune_done'`; mutation `/zcrypto-engine-journal-prune: deleted=/s/level=\\"\\"/level=\\"X\\"/`
  - 5d: `-k 'takes_the_level and engine_journal_prune_refused'`; mutation `/journal-prune\\", level=\\"\\"}"$/s/level=\\"\\"/level=\\"X\\"/`
  - 5e: `-k 'takes_the_level and cache_proxy_server_up'`; mutation `/has no server available/s/level=\\"\\"/level=\\"X\\"/`
  - 5f: `-k 'takes_the_level and cache_proxy_session'`; mutation `/cache-proxy\\", level=\\"\\"} |~ \\"\^\\\\\\\\S+:/s/level=\\"\\"/level=\\"X\\"/`
  - 5g: `-k 'is_a_copy_its_source_ships and cache_proxy_server_up'`; mutation `s/(?P<level>NOTICE|WARNING|ALERT|INFO)/(?P<level>NOTICE|ALERT|INFO)/`

- [ ] **Step 8: Record the verdicts** — the empty commit, subject `test(alloy): the capture hosts' level stages proven by infra/scripts/mutate-probe.sh`.

### Task 6: The cache nodes' stages (D1 on `zcrypto-valkey1`–`3`)

**Files:**
- Modify: `infra/ansible/roles/cache/files/config.alloy` (inside `loki.process "parse"`, after the `{container=~"valkey|sentinel"}` match, before the closing brace; that match's comment)
- Modify: `tests/test_infra_alloy_levels.py` (fixtures; `MEASURED` and one test)

- [ ] **Step 1: Write the failing tests** — append to `FIXTURES`:

```python
    Fixture("cache_valkey_sigterm", "cache", {"container": "valkey"}, "1:signal-handler (1762161901) Received SIGTERM scheduling shutdown...", "WARNING"),
    Fixture("cache_sentinel_sigterm", "cache", {"container": "sentinel"}, "1:signal-handler (1762161901) Received SIGTERM scheduling shutdown...", "WARNING"),
    Fixture("cache_valkey_monotonic", "cache", {"container": "valkey"}, "monotonic: x86 linux, 'constant_tsc' flag not present", "INFO"),
    Fixture("cache_sentinel_monotonic", "cache", {"container": "sentinel"}, "monotonic: x86 linux, 'constant_tsc' flag not present", "INFO"),
```

and at the end of the module:

```python
# The sources the node's read found shipping lines with no level, by host and container.
MEASURED = {
    ("mon", "zcrypto-mon-selfcheck"),
    ("hc", "zcrypto-hc-selfcheck"),
    ("hc", "zcrypto-sqlite-backup"),
    ("hc", "hc"),
    ("ops", "zcrypto-tape-bars"),
    ("ops", "zcrypto-verified-replay"),
    ("ops", "zcrypto-verify-replay"),
    ("ops", "zcrypto-archive-pull"),
    ("capture", "zcrypto-capture-prune"),
    ("capture", "zcrypto-engine-journal-prune"),
    ("capture", "cache-proxy"),
    ("cache", "valkey"),
    ("cache", "sentinel"),
}


def test_every_source_the_read_found_without_a_level_has_its_shapes_here():
    covered = {(f.host, f.labels["container"]) for f in FIXTURES if "level" not in f.labels}
    assert sorted(MEASURED - covered) == []
```

(the hc Alloy's own lines, the fourteenth source, are `HC_ALLOY_LINES`.)

- [ ] **Step 2: Run them to see them fail** — expected `4 failed, 106 passed, 5 skipped`: the four cache fixtures.

- [ ] **Step 3: Add the cache blocks and correct the comment** — after the `{container=~"valkey|sentinel"}` match's closing `  }` and a blank line:

```
  // Two shapes Valkey and Sentinel print outside the line format above: the signal handler's, at the warning level
  // Valkey logs it at, and the clock notice at start.
  stage.match {
    selector = "{container=~\"valkey|sentinel\", level=\"\"} |~ \"^\\\\d+:signal-handler \\\\(\""

    stage.static_labels {
      values = { level = "WARNING" }
    }
  }

  stage.match {
    selector = "{container=~\"valkey|sentinel\", level=\"\"} |~ \"^monotonic: \""

    stage.static_labels {
      values = { level = "INFO" }
    }
  }
```

and the comment above the `{container=~"valkey|sentinel"}` match, its last sentence:

```
  // mark `#` for a warning, `*` for a notice, `-` verbose and `.` debug. A line of another shape
  // renders an empty level, which the labels stage drops, so it ships with no `level` label.
```

```
  // mark `#` for a warning, `*` for a notice, `-` verbose and `.` debug. A line of another shape
  // renders an empty level, which the labels stage drops; the blocks at the end of this component
  // level the two such shapes the containers print.
```

- [ ] **Step 4: Run them to see them pass** — expected `110 passed, 5 skipped`; then `uv run pytest tests/test_infra_alloy_series.py -k cache -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` passes (one drop stage in the cache pipeline).

- [ ] **Step 5: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/cache/files/config.alloy) tests/test_infra_alloy_levels.py"`, the pytest line, the gate.

- [ ] **Step 6: Commit** — subject `fix(alloy): Valkey's and Sentinel's two lines outside their format take a level`.

- [ ] **Step 7: Probe** — `: > .local/fleet-log-levels/probes-task-6.txt`:
  - 6a: file `infra/ansible/roles/cache/files/config.alloy`; `-k 'takes_the_level and cache_valkey_sigterm'`; mutation `/signal-handler/s/level=\\"\\"/level=\\"X\\"/`
  - 6b: same file; `-k 'takes_the_level and cache_valkey_monotonic'`; mutation `/\^monotonic: /s/level=\\"\\"/level=\\"X\\"/`
  - 6c: same file; `-k 'reaches_the_level_stages and cache_valkey_sigterm'`; mutation `s/expression = "\^\\\\d+:\[XCSM\].*$/expression = "^(?P<mark>\\\\d)"/`
  - 6d: file `tests/test_infra_alloy_levels.py`, control `s/^MEASURED = {$/MEASURED_GONE = {/`; `-k test_every_source_the_read_found_without_a_level_has_its_shapes_here`; mutation `s/^MEASURED = {$/MEASURED = {("ops", "zcrypto-panel-materialize"),/`

- [ ] **Step 8: Record the verdicts** — the empty commit, subject `test(alloy): the cache nodes' level stages proven by infra/scripts/mutate-probe.sh`.

### Task 7: The node rule for lines with no level, its panel and its runbook section (D9)

**Files:**
- Modify: `infra/grafana/alerts.yaml` (a rule appended to the `zcrypto-mon` group, after `zcrypto-mon-grafana-error-logs`, before the `# ---- zcrypto-hc` comment)
- Modify: `infra/grafana/fleet-health-dashboard.json` (panel 912 after panel 911; row 920 and panels 921–926 down 8)
- Modify: `tests/test_infra_alert_rules.py` (`_MON_RULES`; the node-group membership case; one test)
- Modify: `infra/runbooks/mon.md` (a section appended after `zcrypto-mon-grafana-error-logs`)

- [ ] **Step 1: Write the failing tests** — in `tests/test_infra_alert_rules.py`, `_MON_RULES` takes `"zcrypto-mon-unlevelled-log-lines": ("warning", "912"),`; in `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group`, after the `zcrypto-mon-ingest-dark` branch:

```python
        if rule["uid"] == "zcrypto-mon-unlevelled-log-lines":
            # It reads each host's lines the node holds, the two nodes' own among them.
            assert matchers == [("=~", ".+")], matchers
            continue
```

and after `test_the_grafana_error_rule_and_its_panel_leave_out_a_context_canceled_line`:

```python
_UNLEVELLED = 'topk(5, sum by (host, container) (count_over_time({host=~".+", level=""} [15m])))'


def test_the_unlevelled_rule_pages_each_source_that_ships_a_line_with_no_level():
    rule = _rule("zcrypto-mon-unlevelled-log-lines")
    assert (rule["title"], rule["ruleGroup"]) == ("Fleet · log lines with no level", "zcrypto-mon")
    assert _log_expr(rule["uid"]) == _UNLEVELLED
    assert rule["data"][0]["relativeTimeRange"] == {"from": 900, "to": 0}
    assert _evaluator(rule) == {"type": "gt", "params": [0]}
    assert (rule["for"], rule["noDataState"], rule["execErrState"]) == ("0s", "OK", "Alerting")
    assert (rule["labels"]["severity"], rule["notification_settings"]["receiver"]) == ("warning", "logs")
    board = json.loads((REPO / "infra/grafana/fleet-health-dashboard.json").read_text())
    (panel,) = [p for p in board["panels"] if p.get("id") == 912]
    assert [t["expr"] for t in panel["targets"]] == [_UNLEVELLED]
```

- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_infra_alert_rules.py -k "unlevelled or node_group or nodes_group" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected the new test and `test_a_node_group_is_its_rules_each_with_its_own_section_and_panel[zcrypto-mon]` fail.

- [ ] **Step 3: The rule** — appended to the `zcrypto-mon` group in `infra/grafana/alerts.yaml`:

```yaml
  - uid: zcrypto-mon-unlevelled-log-lines
    title: "Fleet · log lines with no level"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      # Each host that ships its logs to the node, the node and the dead-man node among them: a line no stage of its
      # host's Alloy levelled is a source to classify, one instance per source.
      - refId: A
        queryType: instant
        relativeTimeRange: {from: 900, to: 0}
        datasourceUid: "${GRAFANA_LOKI_DS_UID}"
        model:
          expr: >-
            topk(5, sum by (host, container) (count_over_time({host=~".+", level=""} [15m])))
          queryType: instant
          refId: A
      - refId: B
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: reduce
          reducer: last
          expression: "A"
          refId: B
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "B"
          refId: C
          conditions:
            - evaluator: {type: gt, params: [0]}
    noDataState: OK  # a window with no such line returns no series, the healthy state
    execErrState: Alerting
    for: 0s
    annotations:
      summary: "A host shipped a log line with no level to the observability node in the last 15 minutes: a source whose line shape no stage of that host's Alloy names, so the logs view draws it as level unknown and no ERROR rule reads it. One alert instance per host and container, at most 5. Read the line, then level its shape in that host's config.alloy. Runbook: infra/runbooks/mon.md#zcrypto-mon-unlevelled-log-lines"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "912"
      unit: "lines with no level in the last 15 minutes"
    labels:
      severity: warning
    notification_settings:
      receiver: logs
```

- [ ] **Step 4: The panel** — in `infra/grafana/fleet-health-dashboard.json`, after panel 911, a panel in 911's shape and the file's formatting, with `"id": 912`, `"type": "timeseries"`, `"title": "Monitor — log lines with no level"`, `"description": "Is every line the fleet ships given a level? One line per host and container that shipped a line with no level in the fifteen minutes before each point, at most five. The alert pages on the first one. A source shows here when its host's Alloy names no stage for the shape it printed — a new script, a changed line, a parse that broke — and Grafana's logs view draws its lines as level unknown. No line at all is the healthy state."`, `"gridPos": {"h": 8, "w": 24, "x": 0, "y": 144}`, 911's `datasource`, `fieldConfig` (unit `short`, the line threshold style, green then red at 1) and `options`, and one target:

```json
        {
          "datasource": {
            "type": "loki",
            "uid": "grafanacloud-logs"
          },
          "expr": "topk(5, sum by (host, container) (count_over_time({host=~\".+\", level=\"\"} [15m])))",
          "refId": "A",
          "legendFormat": "{{host}} {{container}}"
        }
```

Then the `Dead-man node` row moves down 8: panel 920's `y` 144 → 152, panels 921–924's `y` 145 → 153, panels 925 and 926's `y` 153 → 161.

- [ ] **Step 5: The runbook section** — appended to `infra/runbooks/mon.md` after `zcrypto-mon-grafana-error-logs`'s *Retire when* paragraph: a blank line, the page's separator line `______________________________________________________________________`, a blank line, then:

```markdown
<a name="zcrypto-mon-unlevelled-log-lines"></a>

## zcrypto-mon-unlevelled-log-lines — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Fleet · log lines with no level`, on the `logs` receiver, `for: 0s`, `noDataState: OK`: a host shipped a log line with no `level` label to the node in the last fifteen minutes. Each instance names the `host` and the `container` the line came from, at most five of them; Grafana's logs view draws such a line as level unknown. The Fleet health board's *Monitor — log lines with no level* panel (912) draws the count per host and container.

### What it means

Each host's Alloy gives a line its `level` in its `loki.process "parse"` block, in `infra/ansible/roles/<role>/files/config.alloy`: a parsing stage per source reads the level a line carries, and for a source that prints none a trailing `stage.match` on `{container="<name>", level=""}`, its line filter keyed on the shape the source prints, sets it by `stage.static_labels`. A line no stage names ships with no `level`, and the ERROR rules' `level=~"ERROR|CRITICAL"` does not read it: a new script or unit, a source whose printed line changed, or a parse stage that broke. The line is not lost, only unclassified. A burst — a crash's traceback, a service's start-up banner — is one instance with its count.

### What to do

1. **Read the lines**, from the workstation, the day's set with each line's first 200 characters: `uv run python infra/scripts/grafana-query.py --stack mon --loki 'topk(20, sum by (host, container, msg) (count_over_time({host=~".+", level=""} | regexp "^(?P<msg>.{1,200})" [24h])))'`.
2. **Find the source's stage** in its host's config: `config.alloy` under `infra/ansible/roles/mon`, `hc`, `ops`, `capture` (both capture hosts and the engine's cache proxy) or `cache`, or the NAS's `infra/nas/config.alloy`, and the trailing `stage.match` blocks at the end of its `loki.process "parse"`. A container with no such block is a source the config has not classified; a container with one printed a shape it does not name. A source whose whole stream lost its level is a parse stage that broke: `git log -5 --` that config and the source's own file, and for the ops units `observability.md`'s `zcrypto-ops-log-plane`.
3. **Classify the shape by what the line reports**, in a branch: INFO for a run that did its job; WARNING for a failure another rule pages, which the line explains; ERROR for a failure no other rule pages; a line that repeats one its source already ships with a level is dropped, `action = "drop"`, rather than levelled. The block goes after the host's parsing blocks with `level=""` in its selector, its fixture line in `tests/test_infra_alloy_levels.py`; the source's printed text stays as it is, since rules, tests and runbooks read it.
4. **Ship it** by that host's converge as `.claude/skills/zcrypto-bump-alloy/SKILL.md`'s *What this is* gives a `config.alloy` edit, and **confirm by value**: `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (host, container) (count_over_time({host="<host>", level=""} [1h]))'` reads `(no series)` once an hour of the source's lines has passed, and the rule is back to **Normal**.

### Retire when

`zcrypto-mon-unlevelled-log-lines` is absent from `infra/grafana/alerts.yaml`.
```

- [ ] **Step 6: Run them to see them pass** — Step 2's command, then `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py tests/test_internal_terms_not_operator_visible.py tests/test_ops_daily.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected all pass (the red-line pairing reads panel 912's bar at 1 against `gt 0`; the rule names no single host, so `_UID_HOST` takes no entry).

- [ ] **Step 7: Run the commit's tests and the gate** — `T="$(infra/scripts/consumers.sh --direct infra/grafana/alerts.yaml infra/grafana/fleet-health-dashboard.json infra/runbooks/mon.md) tests/test_infra_alert_rules.py"`, the pytest line, the gate.

- [ ] **Step 8: Commit** — subject `feat(grafana): a node rule pages the first line any host ships with no level, its panel and its runbook section`.

- [ ] **Step 9: Probe** — `: > .local/fleet-log-levels/probes-task-7.txt`; the test file `tests/test_infra_alert_rules.py`:
  - 7a: file `infra/grafana/alerts.yaml`; `-k test_the_unlevelled_rule_pages_each_source_that_ships_a_line_with_no_level`; mutation `s/level=""} \[15m\]/level="x"} [15m]/`
  - 7b: same file and `-k`; mutation `/uid: zcrypto-mon-unlevelled-log-lines/,/receiver: logs/s/receiver: logs/receiver: metrics/`
  - 7c: file `infra/grafana/fleet-health-dashboard.json`, same `-k`; mutation `s/level=\\"\\"} \[15m\]/level=\\"x\\"} [15m]/`
  - 7d: file `infra/grafana/alerts.yaml`; `-k test_a_node_group_is_its_rules_each_with_its_own_section_and_panel`; mutation `s/__panelId__: "912"/__panelId__: "913"/`
  - 7e: file `infra/grafana/alerts.yaml`; `-k test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group`; mutation `s/{host=~".+", level=""}/{host=~"zcrypto-.+", level=""}/`

- [ ] **Step 10: Record the verdicts** — the empty commit, subject `test(grafana): the unlevelled-lines rule proven by infra/scripts/mutate-probe.sh`.

### Task 8: The node Grafana's configuration noise (D6)

**Files:**
- Modify: `infra/ansible/roles/mon/templates/grafana.ini.j2` (`[security]`, `[log]`)
- Modify: `tests/test_infra_mon_role.py` (`test_grafana_logs_warnings_and_above_in_every_mode_with_no_logger_filter` replaced; one test)

- [ ] **Step 1: Write the failing tests** — replace `test_grafana_logs_warnings_and_above_in_every_mode_with_no_logger_filter` with:

```python
def test_grafana_logs_warnings_and_above_and_a_filter_only_raises_a_logger():
    ini = _ini()
    assert ini.get("log", "level", fallback=None) == "warn"
    assert ini.get("log", "filters", fallback=None) == "search-manifest-watcher:error"
    for section in [s for s in ini.sections() if s == "log" or s.startswith("log.")]:
        level = (ini.get(section, "level", fallback="") or "warn").lower()
        assert level in ("warn", "error", "critical"), f"[{section}] level = {level}"
        for entry in ini.get(section, "filters", fallback="").split():
            logger, _, floor = entry.partition(":")
            assert logger and floor.lower() in ("error", "critical"), f"[{section}] filters {entry!r} lowers a logger below warn"


def test_the_ini_turns_off_the_header_browsers_dropped():
    assert _ini().get("security", "x_xss_protection", fallback=None) == "false"
```

- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_infra_mon_role.py -k "filter_only_raises or header_browsers" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected `2 failed`.

- [ ] **Step 3: The ini** — in `[security]`, after `disable_brute_force_login_protection = false`:

```
# Browsers dropped the header this setting sends; Grafana announces the setting as deprecated at each start.
x_xss_protection = false
```

and in `[log]`, after `level = warn`:

```
# The manifest watcher logs two warnings a minute about an empty search manifest it keeps; its errors still log.
filters = search-manifest-watcher:error
```

- [ ] **Step 4: Run them to see them pass** — Step 2's command, then `uv run pytest tests/test_infra_mon_role.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`, all pass.

- [ ] **Step 5: Commit** — after `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/mon/templates/grafana.ini.j2) tests/test_infra_mon_role.py"`, the pytest line and the gate; subject `fix(mon): grafana.ini leaves the manifest watcher's warnings out and turns off the dropped X-XSS header`.

- [ ] **Step 6: Probe** — `: > .local/fleet-log-levels/probes-task-8.txt`; the file `infra/ansible/roles/mon/templates/grafana.ini.j2`, the test file `tests/test_infra_mon_role.py`:
  - 8a: `-k test_grafana_logs_warnings_and_above_and_a_filter_only_raises_a_logger`; mutation `s/^filters = search-manifest-watcher:error$/filters = search-manifest-watcher:info/`
  - 8b: same `-k`; mutation `$a [log.console]\nfilters = ngalert:debug`
  - 8c: `-k test_the_ini_turns_off_the_header_browsers_dropped`; mutation `/^x_xss_protection = false$/d`

- [ ] **Step 7: Record the verdicts** — the empty commit, subject `test(mon): the ini's log filter and header setting proven by infra/scripts/mutate-probe.sh`.

### Task 9: HAProxy's start-up warnings (D7)

**Files:**
- Modify: `infra/ansible/roles/engine/templates/haproxy.cfg.j2` (`global`, `defaults`, `frontend cache`)
- Modify: `tests/test_infra_cache_proxy.py` (one helper, one test)

The file reaches `zcrypto` only with an engine converge, inside the inter-cycle gap: it rides the next one, the nautilus bump the owner named for half a day before rung 3's entry (spec D7), and this plan adds no converge for it.

- [ ] **Step 1: Write the failing test** — in `tests/test_infra_cache_proxy.py`, after `test_the_timeouts_the_logging_and_the_metrics_endpoint`:

```python
def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: list[str] = []
    for line in _lines(text):
        if line.split()[0] in ("global", "defaults", "frontend", "backend"):
            current = out.setdefault(line, [])
        else:
            current.append(line)
    return out


def test_haproxy_chroots_and_logs_connections_on_the_cache_frontend_alone():
    sections = _sections(_render())
    assert "chroot /var/lib/haproxy" in sections["global"] and "user haproxy" in sections["global"]
    assert [name for name, lines in sections.items() if "option tcplog" in lines] == ["frontend cache"]
    assert "no log" in sections["frontend metrics"]
```

- [ ] **Step 2: Run it to see it fail** — `uv run pytest tests/test_infra_cache_proxy.py -k chroots -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected `1 failed`.

- [ ] **Step 3: The config** — `global`'s comment and lines become:

```
    # The container starts as root so this 0600 file is readable, then chroots into the image's empty
    # /var/lib/haproxy and drops to the image's user.
    chroot /var/lib/haproxy
    user haproxy
    group haproxy
```

`defaults` loses `    option tcplog`; `frontend cache` takes it after its `bind`:

```
frontend cache
    bind 0.0.0.0:6379
    # The one frontend that logs takes the connection format; set in defaults, `metrics`, which logs nothing,
    # would inherit a format it warns about at each start.
    option tcplog
```

- [ ] **Step 4: Run it to see it pass** — `uv run pytest tests/test_infra_cache_proxy.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`, all pass (`log stdout format raw local0 info`, `user haproxy`, `group haproxy` still pinned).

- [ ] **Step 5: Commit** — after `T="$(infra/scripts/consumers.sh --direct infra/ansible/roles/engine/templates/haproxy.cfg.j2) tests/test_infra_cache_proxy.py"`, the pytest line and the gate; subject `fix(engine): the cache proxy chroots and logs connections on its cache frontend alone, its two start-up warnings answered`.

- [ ] **Step 6: Probe** — `: > .local/fleet-log-levels/probes-task-9.txt`; the file `infra/ansible/roles/engine/templates/haproxy.cfg.j2`, `-k test_haproxy_chroots_and_logs_connections_on_the_cache_frontend_alone` for each arm:
  - 9a: mutation `/^    chroot \/var\/lib\/haproxy$/d`
  - 9b: mutation `/^    log global$/a\    option tcplog`
  - 9c: mutation `/^    no log$/a\    option tcplog`

- [ ] **Step 7: Record the verdicts** — the empty commit, subject `test(engine): the proxy's chroot and log format proven by infra/scripts/mutate-probe.sh`.

### Task 10 (the controller): the real-Alloy reading, D10's offer, the reads and the pull request

- [ ] **Step 1: The fleet's release binary** — `grep '^alloy_version:' infra/ansible/group_vars/observed/alloy.yml` prints `alloy_version: "1.21.2"` (a later value is used in its place); then, each its own call, `mkdir -p .tmp/alloy-dry`, `curl -fsSL --max-time 120 -o .tmp/alloy-dry/alloy.zip https://github.com/grafana/alloy/releases/download/v1.21.2/alloy-linux-amd64.zip`, `unzip -o .tmp/alloy-dry/alloy.zip -d .tmp/alloy-dry`, `chmod +x .tmp/alloy-dry/alloy-linux-amd64`, `ln -sf alloy-linux-amd64 .tmp/alloy-dry/alloy`, and `.tmp/alloy-dry/alloy --version` printing `v1.21.2`.
- [ ] **Step 2: Each changed config loads** — `.tmp/alloy-dry/alloy validate infra/ansible/roles/<host>/files/config.alloy` for `mon`, `hc`, `ops`, `capture`, `cache`, each its own call, exit 0. A refusal naming the syntax holds the branch: the fix is a commit on it and Tasks' tests re-run; a refusal naming an environment read or a host path, not the syntax, is recorded and Step 3 is the check.
- [ ] **Step 3: The harness runs** — `PATH="$PWD/.tmp/alloy-dry:$PATH" uv run pytest tests/test_infra_alloy_levels.py tests/test_infra_alloy_stages.py -q -rs -p no:cacheprovider --basetemp=.tmp/controller/pt`; expected every case passes and `-rs` names no skip. A disagreement between Alloy and the model is fixed on the branch, its own commit — the config where Alloy's reading is the spec's, the model where the model misread a selector — and the run repeated.
- [ ] **Step 4: Clean up** — `ls -la .tmp/alloy-dry .tmp/controller` read first; then `rm -rf .tmp/alloy-dry .tmp/controller`.
- [ ] **Step 5: D10 to the owner** — put to the owner in the session, by value: the engine warns at each start that the venue holds a 1e-08-scale SOL/EUR and ETH/EUR balance the Cache reads as 0; silencing it is engine code, a dust threshold read from the instrument, an image and an engine converge; unanswered, it stays as it is. The answer, or none, goes to the PR body verbatim.
- [ ] **Step 6: The reads and the pull request** — the branch's whole read by a different agent through `pre-review`, `review` and `re-review` as the repository's skills run them; the consumer union once before the push, `uv run pytest $(infra/scripts/consumers.sh <every path the branch changes>) -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/controller/pt-union`; then `open-pr`, the body carrying Steps 2–3's readings by value (the version, each validate's exit, the harness's result line), Step 5's offer and answer, and this plan's *Rulings* by reference, D3's flagged first.

### Task 11: Decisions log

- [ ] **Decisions log: none** — the branch is telemetry engineering on the owner's direction, "investigate **ALL* the WARN, ERROR, and UNK log entries, eliminate them if applicable, especially the UNK ones", not a ruling on its design; `iteration-closeout` logs the fleet infrastructure under phase 6 only when the owner rules its design, and skips engineering that touches none of a phase's subjects. An answer to Task 10 Step 5 that rules the engine's dust warning is a phase-6 decision on the engine's behaviour and takes its entry through `iteration-closeout` on the branch that carries it.

## Rollout — the owner's, from merged `develop`, host by host (D11)

The converges and the pushes are the owner's; the reads by value are taken from the workstation in the same sitting. `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`: let it run, or background the whole invocation. Each converge's preview (`--check --diff`) is read before its `--limit` is typed; a preview naming a file or task outside the host's Alloy part (and, on the node, `grafana.ini`) holds the host for the owner. Before each venue-facing host — `zcrypto-ops`, `zcrypto-red`, `zcrypto` — Kraken's maintenance feed is read whole at planning and again immediately before, `curl -fsS --max-time 30 https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, judged by `.claude/rules/fleet-deploys.md`'s test; a window over the converge is waited out, and a read that timed out is no evidence.

**R1. The operands.** From the main checkout at merged `develop`: `git status --porcelain` prints nothing; `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version` prints `0` (no Alloy wave is open); `grep -E '^alloy_(version|image_digest):' infra/ansible/group_vars/observed/alloy.yml` gives `<alloy_image_digest>`, the full `sha256:<64 hex>`; `date -u +%Y-%m-%dT%H:%M:%SZ` stamps the wave's start; the Kraken feed's planning read. While rung 2's box holds (`infra/runbooks/engine-procedures.md`'s `engine-rung-2-box`), a cache node's converge runs outside the day's window and away from an engine restart, and the primary's outside the day's window too.

**R2. The node, `zcrypto-mon`** — the Alloy config and `grafana.ini` in one converge of the role's own tag:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' https://apt.zaccess.zhaow.me/dists/any-version/Release   # 200
ssh mon 'systemctl show -p ActiveEnterTimestamp --value prometheus loki caddy'
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon
ssh mon 'systemctl show -p ActiveEnterTimestamp --value prometheus loki caddy'   # the same three lines
```

The preview names `/etc/grafana/grafana.ini` (the `x_xss_protection` and `filters` lines) and `/etc/alloy/config.alloy`; the real pass restarts `grafana-server` and `alloy`. Verify by value, `uv run python infra/scripts/grafana-query.py --stack mon --loki '<q>'` for each:
- fifteen minutes after the restart, `sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "logger=search-manifest-watcher" [15m]))` reads `(no series)`, and `sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "x_xss_protection" [15m]))` over the restart reads `(no series)`;
- `sum by (level) (count_over_time({host="zcrypto-mon", container="zcrypto-mon-selfcheck"} [15m]))` reads `{level="INFO"}` about 3;
- an hour after, `sum by (host, container) (count_over_time({host="zcrypto-mon", level=""} [1h]))` reads `(no series)`;
- the no-fault shapes at their next line — the Logs board opened on the node and left before its panels load logs cancellations — `sum by (level) (count_over_time({host="zcrypto-mon", container=~"grafana-server|loki"} |= "context canceled" [1h]))` reads `level="INFO"` rows and no ERROR or WARNING row.

**R3. The dead-man node, `zcrypto-hc`:**

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' https://apt.zaccess.zhaow.me/dists/any-version/Release   # 200
ssh hc "sudo docker inspect zcrypto-hc --format '{{.RestartCount}} {{.State.StartedAt}}'; systemctl show -p ActiveEnterTimestamp --value caddy"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags alloy
ssh hc "sudo docker inspect zcrypto-hc --format '{{.RestartCount}} {{.State.StartedAt}}'; systemctl show -p ActiveEnterTimestamp --value caddy"   # the same two lines
```

Verify: an hour after, `sum by (host, container) (count_over_time({host="zcrypto-hc", level=""} [1h]))` reads `(no series)`, and `sum by (container, level) (count_over_time({host="zcrypto-hc", container=~"alloy|zcrypto-hc-selfcheck"} [1h]))` reads INFO rows (WARNING beside them only for a failing self-check); after the next nightly runs (the backup about 02:47Z, uWSGI's prune about 03:17Z), `sum by (container, level) (count_over_time({host="zcrypto-hc", container=~"zcrypto-sqlite-backup|hc"} |~ "backed up|uwsgi-cron|Deleted api_ping" [24h]))` reads INFO rows.

**R4. Ops, `zcrypto-ops`** — the Kraken feed read immediately before:

```bash
ssh hp "sudo docker inspect zcrypto-ops-liquidations --format '{{.RestartCount}} {{.State.StartedAt}}'"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags alloy -e ops_alloy_digest=<alloy_image_digest>
ssh hp "sudo docker inspect zcrypto-ops-liquidations --format '{{.RestartCount}} {{.State.StartedAt}}'"   # the same line
```

The preview names files under `/etc/zcrypto-ops/alloy` alone, the config; the run reloads Alloy and recreates nothing. Verify: an hour after (tape-bars runs hourly), `sum by (host, container) (count_over_time({host="ops", level=""} [1h]))` reads `(no series)` and `sum by (level) (count_over_time({host="ops", container="zcrypto-tape-bars"} [1h]))` reads INFO rows; after the next daily runs, `sum by (container, level) (count_over_time({host="ops", container=~"zcrypto-verified-replay|zcrypto-verify-replay|zcrypto-archive-pull"} [24h]))` reads no level-less row, and `sum(count_over_time({host="ops", container="zcrypto-archive-pull"} |= "trade backfill complete" [24h]))` reads 1, the logged copy alone.

**R5. The push, both stacks** — after R4 reads green, before the cache nodes, by `.claude/skills/zcrypto-grafana-push/SKILL.md`: Step 2's freshness test; Step 1's preflight — `zcrypto-ops-unit-parse-dead`'s expression less its `or on() vector(0)` reads a row per ops unit at 1 or more on Grafana Cloud and with `--stack mon`; `zcrypto-mon-unlevelled-log-lines`' expression with `--stack mon` reads `(no series)`, which is this burst rule's healthy state and holds nothing; then Step 0's Grafana Cloud push and `infra/runbooks/mon.md`'s `mon-push` step 1 for the node, in one sitting. Verify by Step 3: both rules **Normal**, `zcrypto-ops-unit-parse-dead`'s value 1 or more on each stack; panel 912 and the Logs board's panel 103 rendered. No prune: no rule leaves.

**R6. The cache nodes, one per run** — `zcrypto-valkey1`, then `2`, then `3`:

```bash
ssh db<N> "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<alloy_image_digest>
ssh db<N> "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"   # the same two lines
```

The preview names files under `/opt/zcrypto-cache/alloy` alone. Verify: `sum by (host, container) (count_over_time({host="zcrypto-valkey<N>", level=""} [1h]))` reads `(no series)`; the two shapes print only at a container restart and are read at the next one, `sum by (container, level) (count_over_time({host="zcrypto-valkey<N>", container=~"valkey|sentinel"} |~ "signal-handler|monotonic: " [24h]))` reading WARNING and INFO rows.

**R7. The capture secondary, `zcrypto-red`** — the Kraken feed read immediately before:

```bash
ssh red "sudo docker inspect zcrypto-capture --format '{{.RestartCount}} {{.State.StartedAt}}'"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red --tags alloy -e capture_alloy_digest=<alloy_image_digest>
ssh red "sudo docker inspect zcrypto-capture --format '{{.RestartCount}} {{.State.StartedAt}}'"   # the same line
```

The preview names files under `/etc/zcrypto-capture/alloy` and nothing under `/opt/zcrypto-capture`. Verify: `ssh red 'sudo systemctl start zcrypto-capture-prune.service'` (the daily prune, run now as the rollout skill's bake does), then `sum by (level) (count_over_time({host="zcrypto-red", container="zcrypto-capture-prune"} [15m]))` reads `{level="INFO"}` 1; an hour after, `sum by (host, container) (count_over_time({host="zcrypto-red", level=""} [1h]))` reads `(no series)`.

**R8. The capture primary, `zcrypto`** — attended, away from a 4-hourly boundary and from an engine restart, no earlier than an hour after R7's deploy-log row, the Kraken feed read immediately before:

```bash
ssh zcrypto "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=<alloy_image_digest>
ssh zcrypto "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine"   # the same two lines
```

Verify: an hour after, `sum by (host, container) (count_over_time({host="zcrypto", level=""} [1h]))` reads `(no series)`; after the next prunes (01:23Z and 03:17Z), `sum by (container, level) (count_over_time({host="zcrypto", container=~"zcrypto-capture-prune|zcrypto-engine-journal-prune"} [24h]))` reads INFO rows; at the proxy's next event, `sum by (level) (count_over_time({host="zcrypto", container="cache-proxy"} [24h]))` reads no level-less row.

**R9. The record.** The converges' `docs/reference/deploy-log.jsonl` lines ride a recording commit on a fresh branch from `develop`, through `open-pr` and `merge-pr`, its body naming R5's two pushes under `## Grafana push`; no `fleet-pins.md` row moves (no digest or version changed). Then `infra/scripts/count-list.sh converges-inside-a-kraken-window` reads as it did before the wave.

**R10. D7, with the next engine converge** — not this wave's: the nautilus bump's engine converge, in the inter-cycle gap under `.claude/rules/fleet-deploys.md`, carries `haproxy.cfg`. After it, `sudo docker inspect zcrypto-cache-proxy --format '{{.State.Status}} {{.RestartCount}}'` on `zcrypto` reads `running 0`, and `sum(count_over_time({host="zcrypto", container="cache-proxy"} |~ "chroot|log format ignored" [1h]))` reads `(no series)`; that converge's own record carries the read.
