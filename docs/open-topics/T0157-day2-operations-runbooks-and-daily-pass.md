---
status: open
---

# Day-2 operations: every alert has a runbook, and a daily pass reads the fleet

## Context — what

Split out of [[T0049]] on 2026-08-29 (owner's word), which keeps the go-live drill program. This topic is the **operating** half: the runbook tree under `infra/runbooks/` must cover every signal that can page an operator, and a **proactive daily pass** — an agent taking the operating responsibility — must read the fleet, follow the runbook for anything that fired, fix what it can, and leave a journal entry and a Slack summary.

## Why this matters

Measured on `develop` at `48adb42c`: `infra/grafana/alerts.yaml` carries **83 rules; 30 point at a resolving runbook section; 53 do not**. Every one of those 53 is read on a phone, in Slack, with nothing open — the exact situation the runbook protocol exists for. And the reactive half is all there is: nothing in the repo reads alert states or history (`grafana-query.py` is PromQL-only, and its own docstring says `ALERTS{alertstate="firing"}` is structurally empty for Grafana-managed rules), nothing reads Loki, the dead-men are readable only *through* Grafana, `ops-postverify.sh` covers the ops node alone, and there is no operations journal. A quiet day is indistinguishable from a day nobody looked.

## Findings so far

- **The 53 unrunbooked rules are pinned to their producers with drafted four-part sections** (2026-08-29 readers, scratch material for the executing plan): 5 gate, 14 engine/NAS/hcio, 16 ops-node/reconcile/backfill, 21 capture/logship/Alloy/node. Placement forces new subsystem files — `capture.md` is at the 12-section split bar, `ops.md` would reach 25, `engine.md` 13.
- **Stale prose found beside the gaps**: `zcrypto-capture-book-desync-stuck`'s comment and summary describe a single fire-and-forget resubscribe the daemon no longer does (spec `00072`'s ladder replaced it); `zcrypto-ops-journal-transport-dead` says "hourly" for a half-hourly timer; `zcrypto-capture-reboot-pending` cites `fleet-deploys.md` where the discipline lives in `docs/reference/fleet.md`; `zcrypto-capture-resubscribe-failing` drops the host label under a bare `sum()` while its summary names a host.
- **T0049's principles and their homes**: the runbook protocol (index-only README, not-a-backlog, checkable *Retire when*, split rule, file+anchor citations) is durable in `infra/runbooks/README.md` and enforced by `tests/test_infra_alert_rules.py`. Not durable anywhere: the four-part section order and the four section kinds; "drills produce sections, not reports"; the two drill recipes (throwaway container from the pinned digest; textfile `.prom` injection) and the injected-series latency caveat; the never-induce-a-fault-on-live-capture-outside-an-attended-window gate; the activeAt-vs-own-changes attribution step; the compose "container never created" log blind spot. One T0049 step is **wrong and must not be homed**: "healable equals healed proves no loss" — archived [[T0101]] records that verification as circular.
- **Design ruled 2026-08-29** (spec `00104`): a Markdown journal at `docs/reference/ops-journal/<YYYY-MM>.md`, one entry per day with the verdict in the heading, on a standing `ops-journal` branch committed daily and PR-merged autonomously at month rotation; the daily pass is the `/zcrypto-daily-ops` skill over a read-only instrument `infra/scripts/ops-daily.py` (alert states + 24 h history, the repo's first Loki reader, dead-men read both through Grafana and directly from healthchecks.io, a fleet-wide PASS/FAIL verdict, the window's deploys); for every fired alert the skill follows the runbook section and remediates within two tiers — autonomous for read-only and telemetry-only actions and for fixes off the protected paths, prepared-then-the-word for anything touching live capture, the engine, the venue account, or data.

## Suggested next steps

- Land spec `00104` and its plan; execute: the alert-requires-runbook guard, the 53 sections across the new subsystem files, the instrument, the journal, the skill, and the principle homings above.
- Register the journal branch as the second standing exception in `.claude/rules/branch-workflow.md`, beside `/zcrypto-auto-exec`.
- First real pass: run `/zcrypto-daily-ops` end to end, read the journal entry and the Slack summary, and correct the skill from what the first day shows.
