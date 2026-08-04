---
status: open
ripe_when: anytime before the final go-live — picked up manually by the human, never auto-triggered (drills deliberately break production paths, so execution still needs attended maintenance windows per capture-deploys.md); flipped from "the final go-live preparation" at the 2026-07-21 grooming
---

# Go-live drill matrix and day-2 operations runbook

## Context — what

The Phase-1 exit-bar **alerting drill is passed** (owner sign-off 2026-07-16, discharged by the live `zcrypto-nas-archive-pull-stalled` firing — Loki → Grafana → Slack, fired/investigated/resolved the same evening, [[T0048]]). That proved one path, once, on the incident that happened to occur. Before live trading, run a **deliberate drill across the fleet's failure scenarios** and distill the responses into a **day-2 operations runbook** (owner directive 2026-07-16).

## Why this matters

Live money raises the cost of a missed, misrouted, or misread alert from "lost telemetry" to "unattended open positions". Today each alert path has been proven only by whichever incidents happened to fire it, and incident response lives in session memory plus scattered fragments — the [[T0048]] Alloy wedge was diagnosed from scratch live, and its runbook line exists only because the incident occurred. A scenario matrix proves the untested paths; the runbook turns response into a durable procedure a future operator (or session) can execute without rediscovery.

## Findings so far

The drill's starting inventory:

- **Paths proven by real events:** Loki log alert → Slack (the 2026-07-15/16 archive-pull-stalled incident); healthchecks.io dead-man → email (the iter-039 desync) and now native Slack (owner-configured 2026-07-15); Grafana metric rules → Slack (12 rules pinned as-code to the `metrics`/`logs` receivers, 2026-07-16).
- **Dead-men in service:** capture (primary + secondary), engine cycle (`/fail` semantics), NAS archive-pull, gate-export, and the ops-node timers (verify-replay, verified-replay, archive-pull, panel, liquidations poller).
- **Runbook fragments scattered:** ledger correction (`infra/nas/README.md`, [[T0044]]), capture-deploy canary + maintenance windows (`.claude/rules/capture-deploys.md`), Alloy tailer restart ([[T0048]]), reboot slots (spec `00050`).
- **Drill-worthy failure modes already parked:** disk-watermark ping-withhold deploy verification ([[T0032]]), WS-reconnect ride-out ([[T0035]]), phantom-splice guard ([[T0039]]), Alloy tailer death on recreate ([[T0048]]), lost-trades invisibility ([[T0043]]).

## Impact discovery and recovery of a real incident (added 2026-07-27)

The drill matrix below rehearses *inducing* faults. It had no entry for the harder half: a fault that already happened, was absorbed silently, and has to be reconstructed after the fact. One occurred on 2026-07-27 and is the worked example — [[T0101]].

**The drill matrix gains a scenario: "an alert fired for something already over."** Rehearse the reconstruction, not the induction:

1. **Bound it in time.** Query the same counter across widening windows — `increase(<metric>[1h])`, `[6h]`, `[24h]`, `[7d]`. Equal values at 6 h and 7 d mean one event, not a trend; a zero at 1 h means it has stopped. Two queries separate "degrading host" from "one bad patch", and the alert's own wording cannot.
2. **Establish loss or no loss before anything else.** Compare the *healable* counter against the *healed/minted* one. Equal ⇒ fully covered, and the incident is an observability question rather than a data question. That ordering matters: it decides whether this is urgent.
3. **Cross-check the producers against each other.** The reconciler and the capture daemon measure the same silence independently; when they disagree, the disagreement *is* the finding. A single source cannot tell you it is under-reporting.
4. **Rule out your own recent changes explicitly, with timestamps** — compare the alert's `activeAt` against every converge, restart and drill of that day. On 2026-07-27 the alert predated the morning's drills by 41 min and the Alloy bump by ~8 h; without that check the incident would have been misattributed to the deploy, which is the cheapest wrong answer available.
5. **Read the ledger for shape, not just totals.** Per-pair and per-hour records distinguish "every pair briefly" from "one pair for a long time" — different faults with the same total.

**Recovery, when the system already healed it:** confirm the mint is real (records exist, hashes verify), confirm the archive is whole, and then treat the remaining work as *measurement* — the recovery already happened. The failure mode to avoid is reacting operationally to an event that is over, on a host that is fine.

**Drill methodology proven the same day**, and reusable by the scenarios below:

- **Fault injection without touching production**: a throwaway container from the *same pinned digest* on the ops node — isolated data dir, no Loki creds, no dead-man URL — driven against the real venue, with `docker network disconnect/connect` as the fault. Validated [[T0035]]'s reconnect handling end to end, including data consistency across the fault (the spanning hour's `.parquet` hash-verified against its manifest).
- **Alert-path injection**: writing a synthetic `.prom` into the node-exporter textfile dir fires a real rule through the real transport to the real Slack channel, with no daemon involvement, and resolves when the file is removed. Validated [[T0008]]'s stuck-pair alert. **Caveat to carry into any such drill**: a brand-new series does not reproduce real latency — `min_over_time` aggregates only present samples, so an injected series fires in minutes where a real one takes the full window. A drill proves wiring, not timing.

## The runbook protocol, established 2026-07-29 (keep in mind when this topic is worked)

The day-2 runbook this topic plans **now exists and has its first two entries** — but at `infra/runbooks/README.md`, **not** the `docs/reference/day2-operations-runbook.md` path proposed below. It sits beside `infra/grafana/alerts.yaml`, which is what points at it, and `infra/` already carries operational docs. Extend that file; do not create a second one.

The pattern it established, arrived at by asking what an operator (human or model) actually does:

- **Two entry points, one destination.** An alert lands in Slack, or a guard in the code says "read this" — either way the operator arrives already holding the anchor. Alert summaries carry `infra/runbooks/README.md#<uid>`; code comments carry `#<slug>`. Nothing has to be searched for.
- **One `##` section per trigger**, anchored on the thing the operator already has: the alert `uid`, or a stable slug.
- **Four parts, same order every time**, so a cold agent can skim: *What you are seeing* · *What it means* · *What to do* · *Retire when*.
- **Two section kinds, marked in the heading**: `— ALERT` (something fires) and `— KNOWN LIMITATION` (something an operator meets while debugging, where the right action may be "nothing"). Both are reached the same way, so both live here.
- **Every section names a checkable retirement condition** — a rule absent from `alerts.yaml`, a line no longer in the code. A condition you have to *judge* is one nobody acts on, which is the failure this protocol exists to avoid.
- **The runbook is not a backlog.** Work goes to the memo queue; decisions open a `T<NNNN>`. Without that boundary it becomes a second parking lot competing with the open-topics list.
- **Split when** it exceeds ~12 sections or gains a second subsystem's worth: move to `infra/runbooks/<subsystem>.md`, anchors byte-identical.

**Why this matters to this topic specifically.** The drill matrix below produces exactly this material — per scenario: time-to-alert, channels that fired, operator action. Each drilled scenario should land as a runbook section in that shape rather than as prose in a report, and the alert it exercises should carry the anchor. That is the difference between a drill that produced a document and a drill that produced a procedure someone will find at 03:00.

**The seam worth remembering**: `.claude/rules/operator-facing-text.md` bans `T<NNNN>` from alert summaries, so a summary can carry the runbook *path* but never the topic ID. The runbook is a repo doc and may reference topics freely. Path in the alert, topic in the runbook.

## Done so far

- **The monthly reference-data routine is DELIVERED as a runbook section — 2026-08-04, [[T0113]] resolved.** This topic registered it on 2026-07-30 as a routine the runbook owes; it now exists as `refdata-sweep-due` in `infra/runbooks/README.md`, in the established four-part shape with a checkable *Retire when*. What made it fit the runbook's own scope rule — a procedure for a signal that fires at an operator, never a backlog entry — is that it gained a real trigger: a scheduled `#zcrypto` reminder, the mechanism [[T0103]]/[[T0105]] use because a `ripe_when:` date is read by nobody at the moment it fires. The procedure itself is the `/zcrypto-refdata-sweep` skill, and the section's step 4 re-arms the next reminder, since a scheduled message fires once. The *pre-go/no-go* run is deliberately **not** here — it is an input to the decision and lives in [[T0085]].

## Suggested next steps

- Enumerate the scenario matrix (draft — extend at execution): capture daemon stopped (each host) → dead-man fires, Slack lands; disk-watermark breach → withheld ping pages; engine cycle failure → `/fail` ping routes; NAS pull stall → Loki alert (re-verify post-[[T0048]]-fix); Alloy itself down → what pages, and how fast; secondary host loss → primary unaffected, loss still visible; Grafana Cloud unreachable → the healthchecks.io independent failure domain still pages; ops-node timer failure → its dead-man; reboot-window overlap sanity (primary 21:25 / secondary 22:25 UTC); a compose-level "container never created" failure (docker-path logs never exist and the owning unit's journal is filtered on the capture hosts — the one log class no Alloy pipeline sees; registered 2026-07-19 from the iter-105 config.alloy review) → confirm the healthchecks dead-man is the catcher and time it.
- Run each scenario in an attended maintenance window, per `capture-deploys.md` discipline (never induce a failure on live capture outside a window); record per scenario: time-to-alert, channel(s) that fired, and the operator action taken.
- Extend `infra/runbooks/README.md` (created 2026-07-29, two entries) with one section per alert/dead-man in the established four-part shape, folding in the scattered fragments — ledger correction, Alloy restart, canary rule — so it becomes the single entry point. **Do not create `docs/reference/day2-operations-runbook.md`**: that path was this topic's original proposal and would now be a second, competing home.
- **(direction, 2026-07-21 grooming)** Evolve this from a one-shot drill matrix into a human-triggered **healthcheck skill**: root-cause fixes keep producing tests as today, and *additionally* each incident adds a check script/instruction here, so the skill verifies all systems/components/datasets are present and consistent (fold in [[T0039]]'s findings). The skill also fetches and analyzes historical logs + alerts — aiming, eventually, at autonomous operation.
- **The post-go-live kill criteria and revalidation routines are sections this runbook owes** *(added 2026-08-02; the topic is [[T0122]], where they are ratified and registered meanwhile)*. Two are already ratified and need only a live signal to become runbook sections: the **20 % governed-drawdown kill floor** (retire, not de-lever — the deployed ladder's terminal rung is 15 % *with re-arm*, so 20 % means the governor went flat and the book lost five further points), and the **monthly revalidation** re-run whose recording discipline mirrors [[T0113]]'s stamp bump. The underperformance criterion is registered but its bound is not derivable yet: a kill on live Sharpe provably cannot fire (±2.15 95 % half-width after a year; 8–12 years to separate the live-state baseline from zero), so the statistic is the **paired live-minus-simulation** difference and its threshold comes from 6b's first weeks of real fills. Each becomes a section here only once something fires at an operator — until then it would be backlog, which this runbook's scope bans by name.
- Human item: during the drill window, on the phone's Slack app confirm a mobile push actually arrives for one `metrics`-receiver alert and one `logs`-receiver alert (not just the desktop client); record delivery latency for both in the drill log.
