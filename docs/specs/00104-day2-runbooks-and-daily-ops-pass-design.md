# 00104 — every alert gets a runbook, and a daily pass takes the operating responsibility

Resolves [[T0157]] (split from [[T0049]] on 2026-08-29). Five components, one branch, one PR:

| # | component | what it buys |
| --- | --- | --- |
| A | the alert-requires-runbook guard, then the 53 missing sections across seven new subsystem files | no signal can page an operator without a procedure behind it |
| B | `infra/scripts/ops-daily.py` — a read-only instrument over alert states and history, Loki, the dead-men (two ways), a fleet-wide verdict, and the window's deploys | the pass has something to read; three of those reads exist nowhere today |
| C | the operations journal — Markdown, monthly files, a standing branch, autonomous rotation | a quiet day becomes distinguishable from a day nobody looked |
| D | the `/zcrypto-daily-ops` skill — the pass, the incident loop over the runbook, remediation within two tiers, the Slack summary | an agent takes the operating responsibility |
| E | T0049's principles homed on operating surfaces; two rule exceptions registered | the topic's text becomes droppable without losing a rule |

## The measured basis

Read on `develop` at `48adb42c`, 2026-08-29, from the repo alone:

| reading | value | what it settles |
| --- | --- | --- |
| rules in `infra/grafana/alerts.yaml` | **83**; **30** carry a resolving `infra/runbooks/<file>#<uid>` link, **53** do not | the gap is the majority, not the tail |
| `infra/runbooks/capture.md` | 12 sections — the README's split bar | new capture material needs a new file |
| `infra/runbooks/ops.md` / `engine.md` | 9 / 9 sections; 16 and 4 rules owed | ops needs a second file; engine crosses the bar by one |
| alert-state readers | none — `grafana-query.py` is PromQL-only and its docstring rules out `ALERTS{alertstate="firing"}` for Grafana-managed rules | the pass's first read must be built |
| Loki readers | none anywhere in `infra/`, `cli/`, `.claude/` | the second read must be built |
| dead-man readers | `hc_check_up` / `hc_checks_down_total` scraped by the ops Alloy — readable only *through* Grafana; the vaulted `healthchecks_api_key` is read by no code | the third read is blind exactly when Grafana is |
| fleet verdict | `ops-postverify.sh` — 9 checks, ops node only | capture, engine, gate, NAS, zaccess have no bundled read |
| operations journal | none; `deploy-log.jsonl` is converge-only | must be created |

## Decisions

### D1 — the guard comes first: every rule must carry a resolving runbook link

`tests/test_infra_alert_rules.py` already resolves a `Runbook: infra/runbooks/<file>#<anchor>` link *when a summary carries one*. D1 makes the link **required** on every rule. The test is landed and seen **red with exactly the 53 uids named** before any section is written, and green only when the last section lands — the proof that the guard bites on the defect it names, and the permanent bar against a rule shipping without a procedure. A section serving several uids carries one `<a name>` per uid (the `verify-replay` precedent).

### D2 — placement: seven new subsystem files, one move, no other anchor changes

| file | serves |
| --- | --- |
| `gate.md` (new) | the five gate rules |
| `nas.md` (new) | the four NAS rules |
| `hosts.md` (new) | disk-low, load-high, reboot-pending, the textfile-transport family (missing / unreadable / reboot-probe-stale / oneoff-textfile-stale as one section) |
| `observability.md` (new) | alloy-dark ×4 (one section), capture log-dead ×2 (one), logship ×2 (one), the ops log-plane four (pipeline-dead, poller-log-dead, unit-parse-dead, journal-transport-dead), node-collector-failed, hcio-watchdog |
| `capture-daemon.md` (new) | book-desync-stuck, resubscribe-rate + resubscribe-failing (one section), watermark-breached, capture-error-logs |
| `ops-node.md` (new) | the ops host's units: archive-pull ×2, verified-replay ×2, panel, trade-backfill ×2, ops-load-high, ops-error-logs |
| `ops.md` (+2) | reconcile-exporter-stale, reconcile-source-lag; and the existing healable-gap-rate section gains the link its rule lacks |
| `engine.md` (+4, −2) | cycle-stale, cycle-failed, engine-error-logs, engine-log-dead join; the two PROCEDURE sections (`engine-probe-window`, `engine-tracking-band`) move to **`engine-procedures.md`** with anchors byte-identical and every citation updated in the same commit — a paged operator and an attended probe session are different readers, and the procedures are 360 of the file's 634 lines |

**The dead-men get the same treatment.** D1's guard covers Grafana rules; the ten healthchecks.io checks (`capture`, `capture-redundant`, `engine`, `engine-shadow`, `nas`, `gate-verify`, the five ops checks, and `grafana-watchdog`) page through their own native Slack integration with no runbook link at all. Each maps to the section that owns its daemon — the map lives in `observability.md#zcrypto-hcio-watchdog` as a table, and every check's healthchecks.io **description** carries `Runbook: infra/runbooks/<file>#<anchor>` so the native page itself names the procedure — set through the management API in an attended step at closeout ([[T0083]]'s retag precedent), read back and verified.

Each section is in the established four-part shape and cites concrete commands. The content basis is the reader drafts in the plan's scratch material; every command, path, unit name and metric in a section is **verified against the repo by the implementer before it lands** — a draft is a starting point, never a citation. `infra/runbooks/README.md` gains one index heading per new file listing every uid served.

### D3 — rule prose is fixed where the summary is rewritten; one expression changes

Every one of the 53 summaries is rewritten to carry its link, so stale wording beside it is fixed in the same edit: `zcrypto-capture-book-desync-stuck` describes a single fire-and-forget resubscribe where the daemon runs spec `00072`'s ladder; `zcrypto-ops-journal-transport-dead` says "hourly" for a half-hourly timer; `zcrypto-capture-reboot-pending` cites `fleet-deploys.md` for a discipline that lives in `docs/reference/fleet.md`; `zcrypto-ops-load-high`'s comment counts four timers. The one expression change: `zcrypto-capture-resubscribe-failing` aggregates with a bare `sum()` and so cannot name the host its summary promises — it gains `by (host)`. Pushed with the other rules; its first sample is verified by value after the push (`fleet-deploys.md`'s lifecycle).

### D4 — the instrument: `infra/scripts/ops-daily.py`, read-only, five reads, one report

`ops-daily.py report --since 24h [--journal-entry]` prints a Markdown report and, with the flag, the day's journal paragraph. It never writes to a host, a venue, or Grafana.

- **Auth.** The vault-token resolver in `grafana-query.py` moves to an importable sibling, `infra/scripts/grafana_auth.py`, that both scripts use; the docstring's two decrypt footguns move with it. `grafana-query.py`'s behaviour and tests are unchanged.
- **Alerts.** Current state of every rule from `GET /api/prometheus/grafana/api/v1/rules` (state, and each instance's `activeAt` and labels). Transitions in the window from the alert-state-history API `GET /api/v1/rules/history?from=&to=&limit=`, **read in chunks small enough that no chunk reaches the page limit, and the count checked against the limit** — the truncation trap already documented beside the silence rules. Output: every uid that was firing at any point in the window, with fired/resolved times and the rule's runbook link.
- **Logs.** The repo's first Loki reader. The Loki datasource uid is resolved at run time from `GET /api/datasources` by type, never hard-coded (the rules carry a placeholder substituted at push). Two queries through the datasource proxy's `query_range`: `sum by (host, container, level) (count_over_time({host=~".+", level=~"WARNING|ERROR|CRITICAL"}[<window>]))`, and per container the top ERROR/CRITICAL messages using the four log-rules' own selectors at the window's width. Output: a counts table and the top messages.
- **Dead-men, two ways.** `hc_check_up` and `hc_checks_down_total` through Prometheus, **and** the check list directly from `GET https://healthchecks.io/api/v3/checks/` with the vaulted **read-only** key. The direct read is what keeps the dead-man domain visible while Grafana is dark — the domain's whole reason to exist. The plan verifies which key the vault holds; if only a full key, a read-only one is minted attended and vaulted beside it.
- **Fleet verdict.** PASS/FAIL checks in `ops-postverify.sh`'s pattern, `(no series)` a FAIL, extended fleet-wide. The set is **presence and freshness**, which the rules cannot give (their absence states are `OK` by design): every host's `up`; each capture host's newest book-message age; the engine's newest cycle age and its seven envelope gauges present; the gate's `status`/`streak`/`mismatch` present and fresh; the NAS pull lag; zaccess tunnel handshake age and certificate days; every `zcrypto_logship_dropped_lines_total` at 0. The exact series and bounds are pinned in the plan from the rules' own expressions so the verdict and the rules cannot disagree about what fresh means.
- **Deploys.** The window's lines from `docs/reference/deploy-log.jsonl`, so a `daemon-restarted` after a converge is reported as expected rather than as a finding.
- **Exit code.** 0 all-clear, 1 attention (anything fired, failed, or errored), 2 the instrument itself could not read a source — and the report names which; a source it cannot reach is a finding about that source, never a silent gap.
- **Tests.** Unit tests on fixture responses for every parser (rules, history chunks incl. an at-limit chunk, Loki, healthchecks.io, deploy-log window). The live paths run only under an explicit opt-in env var, per `CLAUDE.md` — a network-gated test is never a reachability-gated one.

### D5 — the journal: Markdown, monthly, on a standing branch, rotated autonomously

- **Where.** `docs/reference/ops-journal/<YYYY-MM>.md`. Rotation is a new file; nothing is renamed, so a month's PR adds one file and cannot conflict with anything.
- **Shape.** One entry per pass: `## <YYYY-MM-DD> — <all-clear | attention | incident>`, then one paragraph with labelled clauses — *window* · *alerts* (uid → disposition) · *checks* · *logs* · *dead-men* · *deploys in window* · *actions* (each with its tier, D6) · *follow-ups*. `tests/test_ops_journal.py` asserts only that every `##` heading is a date with one of the three verdicts and that dates within a file strictly increase — greppable, not a schema.
- **Branch.** A standing branch named `ops-journal`, cut from `develop`. The skill commits after every pass. On the first pass of a new month it opens the PR for the finished month, **merges it on CI green without review or the user's word**, deletes the branch, and re-cuts `ops-journal` from the then-current `develop`. The Slack summary is the entry's paragraph.
- **Exceptions registered (E).** `branch-workflow.md`: the journal branch is the second standing exception to the attended PR-open gate, beside `/zcrypto-auto-exec`. `commit-messages.md`: journal commits and the monthly PR are the fourth review exemption. CI stays — `develop`'s protection requires the `Full test suite` check, so a PR without it cannot merge at all.

### D6 — the skill: `/zcrypto-daily-ops` is the pass, and the incident loop is its core

1. Run the instrument; read the report.
2. **For every alert that fired in the window, follow its runbook section** — *What you are seeing* → *What it means* → execute *What to do* as the investigation — and classify: **expected** (a deploy in the window explains it), **transient** (self-resolved, cause identified), **needs a fix**, **needs a human**.
3. Remediate within two tiers. **Autonomous**: everything read-only; runbook steps that touch telemetry only (restart Alloy, clear a stale cache, re-arm a timer on ops or the NAS); a code fix taken the normal way — fix branch, tests, the mandatory subagent review, PR — **merged on CI green when the fix is off the protected paths**. **Prepared, then the user's word**: any restart or converge of a capture daemon or the engine; anything touching the venue account (the arm file, the kill file, orders); deleting data; a fix landing on the capture write path, the live trade path, or canonical data — the PR waits; and deploying *any* fix to a host is a converge, always attended (`fleet-deploys.md` stands unchanged).
4. Read the dashboards' verdict tiles **numerically** — the same PromQL the tiles carry, through the instrument's verdict; no pixels.
5. Evaluate the runbook's SCHEDULED REMINDER sections that are due.
6. Append the journal entry, commit on `ops-journal`, rotate if the month changed (D5).
7. Post the summary to `#zcrypto` through the Slack tool — agent-side, no repo secret.
8. Re-arm tomorrow's reminder (`slack_schedule_message`; a scheduled message fires once — the `refdata-sweep` pattern).

The skill's dispatch text carries the host-touching rule: every ssh/sudo step runs in the main loop, never in a subagent.

### D7 — T0049's principles are homed, and one is dropped

| principle | home |
| --- | --- |
| the four parts in fixed order; the four section kinds (ALERT, KNOWN LIMITATION, PROCEDURE, SCHEDULED REMINDER); drills produce sections, not reports | `infra/runbooks/README.md` scope |
| the two drill recipes (throwaway container from the pinned digest with `docker network disconnect/connect`; a synthetic `.prom` in the textfile dir fires the real rule through the real transport) and the caveat that an injected series proves wiring, never timing; the compose "container never created" log blind spot | `docs/reference/fleet.md` |
| inducing a fault on live capture is a gated, attended-window action | `.claude/rules/fleet-deploys.md` invariants (protected file — the edit is shown to the user) |
| rule out your own changes with timestamps: an alert's `activeAt` against every converge, restart and drill of the day | `.claude/rules/agent-ops.md`, one clause on the attribution bullet |
| widening-window bounding (`increase()` at 1h/6h/24h/7d) and reading the ledger for shape; when the system already healed the event, the remaining work is measurement — confirm the mint and the archive, never react operationally on a healthy host | the `ops.md` gap sections' *What to do* |
| two producers measuring the same silence independently — when they disagree, the disagreement is the finding; a single source cannot report its own under-reporting | `.claude/rules/agent-ops.md`, one clause beside the empty-query bullet |
| **"healable equals healed proves no loss" — dropped**, recorded as circular by archived [[T0101]] | nowhere |

## Verification

- **D1**: the tightened test fails on the branch's base naming exactly 53 uids; passes at the end. A mutation probe (`mutate-probe.sh`) removes one link and sees the test bite.
- **D2/D3**: every section's commands resolve (paths, units, metrics grep-verified); the runbook index lists every uid; `grafana-push.sh` pushes the rules, and `resubscribe-failing`'s first sample is read by value.
- **D4**: fixture tests green; one attended live run under the opt-in var produces a report whose alert list matches Grafana's own state page for the same window.
- **D5/D6**: the first real pass — the acceptance test of the whole spec — runs end to end: journal entry committed on `ops-journal`, Slack summary posted, reminder armed; what the first day shows corrects the skill before closeout.

## Out of scope

- The drill program and the drill log — [[T0049]].
- The red button (`zcrypto engine flatten`) — its own spec and PR, ruled 2026-08-29.
- Evaluating open topics' `ripe_when` triggers inside the daily pass — dropped for this spec; that sweep belongs to grooming, and a pass that also groomed would be two routines.
