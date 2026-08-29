---
status: resolved
---

# Go-live drill program

## Context — what

The Phase-1 exit-bar **alerting drill is passed** (owner sign-off 2026-07-16, discharged by the live `zcrypto-nas-archive-pull-stalled` firing — Loki → Grafana → Slack, fired/investigated/resolved the same evening, [[T0048]]). That proved one path, once, on the incident that happened to occur. Before live trading, run a **deliberate drill program across the fleet's failure scenarios**, ride the rung-1 probe window for every scenario that needs a real order, and land each drilled response as a runbook section. The day-2 runbook half this topic used to carry is [[T0157]] since 2026-08-29.

The owner's framing (2026-08-29): (1) a plan **with execution instruments** that simulates the unexpected — the capture primary rebooting while an armed engine holds live open orders and a fill lands during the downtime; a market crash where the "red button" must convert everything to EUR within minutes; (2) run the drills **during rung 1** to assess resilience; (3) dig out and validate the action plans behind the illustrated-but-untested paths — Grafana Cloud out for 12 hours, unattended open positions. The outcome is code for resilience and/or runbooks for the extreme case.

## Why this matters

Live money raises the cost of a missed, misrouted, or misread alert from "lost telemetry" to "unattended open positions". The engine has **never been armed** (`docs/reference/fleet-pins.md`, engine row), so every order-path scenario has at most harness evidence, and the go/no-go clause in `docs/research/00.master-plan.md` §12 — *ops drills passed (kill-switch, WS-loss, restart-reduce-only)* — names three drills that are each half-covered. Its artifact list names an **ops drill log** that does not exist as a document.

## Findings so far

The inventory, read from the repo on 2026-08-29 (`develop` at `48adb42c`). Blast: **C** capture data, **O** live orders/positions, **T** telemetry only.

| # | scenario | blast | evidence today |
| --- | --- | --- | --- |
| A | primary reboots with an armed engine holding resting orders; a fill lands during the downtime | O + C | never as a whole: the reboot half is the 2026-07-11 incident, the order half is harness-only (`executor._adopt_resting_orders`); [[T0027]]'s open step is exactly this |
| B | market-crash red button: everything to EUR, fast | O | **no primitive exists** — the kill switch cancels resting orders and refuses intents but closes no position; the only close path is a hand-signed probe plan with a 60-min expiry |
| C | Grafana Cloud out ~12 h — total telemetry loss | T | detected ≤ 20 min by [[T0083]]'s mutual watchdog (drilled 2026-07-21); no procedure for the duration; `delta()`/`increase()` rules blind on return; Alloy buffering unstated |
| D | unattended open positions | O | never; preventive only (`exec-armed-too-long` at 6 h); no rule reads position or drawdown; the 20 % DD floor ([[T0122]]) awaits a live signal |
| E | kill-switch drill (gate item) | O | automatic trips harness-proven; the on-host kill-file drill spec `00088` prescribes has no recorded run; gauges refresh only at start and cycle end |
| F | WS loss, capture side | C | drilled 2026-07-27 ([[T0035]]) and three real incidents since; runbooked |
| F2 | WS loss, engine side, with an order resting | O | unit-tested only |
| G | restart → reduce-only (gate item) | O | the hold latch observed at every converge; classification of a real resting order never exercised |
| H | capture daemon stopped / host down | C | drilled 2026-07-17 (primary) and the 2026-07-11 reboot |
| I | disk watermark breach | C | fix and gauge deployed; the end-to-end withheld-ping page never induced on a host |
| J | engine cycle failure / engine dead | O | 2026-07-11 incident in shadow; the `/fail` route never drilled |
| K | Alloy down / log pipeline dead | T | [[T0048]] incident; no induced Alloy kill |
| L | healthchecks.io dark / a check DOWN | T | drilled 2026-07-21 ([[T0083]]) |
| M | Kraken maintenance collides with a converge | C | four real episodes ([[T0145]]); rule in `fleet-deploys.md` |
| N | NAS archive-pull stall | C | the 2026-07-15/16 incident — the Phase-1 sign-off |
| O | ops-node timer death | T | converge drills 2026-08-04/05; no induced timer death |
| P | compose "container never created" on a capture host | C | never; the one log class no Alloy pipeline sees; the dead-man is the assumed catcher, unconfirmed |
| Q | mobile push actually arrives (human) | T | never recorded |
| R | secondary host loss | C | never — only the inverse was drilled |
| S | provider-level event | C + O | accepted as-is ([[T0088]]); its mitigations are B and C |
| T | an alert fired for something already over | T | the 2026-07-27 reconstruction ([[T0101]]) |

The drill methodology proven on 2026-07-27 — fault injection in a throwaway container from the pinned digest, alert-path injection through a synthetic textfile `.prom`, and the caveat that an injected series proves wiring but not timing — is homed in `docs/reference/fleet.md` by [[T0157]]; the attended-window gate on inducing a fault on live capture is in `.claude/rules/fleet-deploys.md`.

## Done so far

- **The monthly reference-data routine is DELIVERED as a runbook section — 2026-08-04, [[T0113]] resolved**: `refdata-sweep-due` in `infra/runbooks/reference-data.md`, driven by a scheduled `#zcrypto` reminder, procedure `/zcrypto-refdata-sweep`. The pre-go/no-go run is an input to the decision and lives in [[T0085]].
- **The day-2 runbook half is split out as [[T0157]]** (2026-08-29): runbook coverage of every alert, the daily pass, and the homing of this topic's principles all belong there.

## Suggested next steps (superseded — every item is mapped in `## Resolution` below)

- **Define the program** — spec `00105`, written 2026-08-29: the scenario tiers — order-path drills that ride rung 1 (A, B, D, E, F2, G), telemetry drills runnable now in attended windows (C, I, K, O, P, Q, R), and incident-proven scenarios re-verified only when their code changes (F, H, J, L, M, N, T); per scenario the induction instrument, what must fire and within what bound, what the operator does, and what is recorded.
- **The red button is its own spec and PR** (owner ruling 2026-08-29, recorded in `00105` D4 — ruled whole-account, market orders): a `zcrypto engine flatten` primitive — kill file written first so nothing re-opens, cancel every resting order, close every position to EUR with a bounded taker leg, typed confirmation, journaled — on the live trade path, so Fable-floor review. Drill B runs against the rung-1 probe positions once it exists.
- **The ops drill log** the master plan names: one record per drill run — scenario, date, host, induction, time-to-alert, channels, operator action, verdict, follow-ups — and each drilled scenario lands as a runbook section, never as report prose.
- **The Grafana-out-for-hours procedure** (C) needs no event: what to rely on for the duration (the dead-man domain, the daily pass's direct healthchecks.io read, `docker logs` on hosts), which rules are blind on return, and what to re-verify by value.
- Human item, during any drill window: on the phone's Slack app, confirm a mobile push arrives for one `metrics`-receiver alert and one `logs`-receiver alert; record delivery latency for both in the drill log.

## Resolution

**Resolved 2026-08-29 by transfer: every item this topic carried now lives in a committed spec or a sibling topic, and the drills themselves execute as spec `00105`'s iteration, not as a topic.** The map, item by item, so nothing is lost:

| what T0049 carried | where it lives now |
| --- | --- |
| the scenario matrix, every row of the original draft | spec `00105` D3 (telemetry tier, executed in its iteration) and D4 (order-path tier, run at rung 1); the `/fail` route as J′; N re-run because [[T0048]]'s fix changed its path after its proof |
| "run each in an attended window; record time-to-alert, channels, action" | `00105` D1 (the seven-part section shape) and D2 (the ops drill log, `docs/reference/drill-log.md`) |
| "extend `infra/runbooks/` with one section per alert and dead-man; fold in the scattered fragments" | spec `00104` D1–D3 (the guard, the 53 sections, the dead-man map with the link in each check's description); [[T0157]] |
| the runbook protocol | already durable in `infra/runbooks/README.md`; the four-part order, the four section kinds and "drills produce sections" are homed by `00104` D7 |
| the drill methodology (throwaway container from the pinned digest; textfile `.prom` injection; the injected-series latency caveat) and the attended-window gate on inducing faults | `00104` D7 → `docs/reference/fleet.md` and `.claude/rules/fleet-deploys.md` |
| the impact-discovery steps (2026-07-27) | `00104` D7: widening-window bounding, ledger shape, activeAt-vs-own-changes, cross-checking independent producers, measurement-not-reaction when already healed — homed; **"healable equals healed proves no loss" dropped**, recorded as circular by [[T0101]] |
| the healthcheck-skill direction (2026-07-21 grooming) | it is `00104` D6 — `/zcrypto-daily-ops` |
| the kill criteria and revalidation routines this runbook "owes" | [[T0122]] owns them; they become sections when a signal fires (`infra/runbooks/README.md` scope) |
| the mobile-push human item | `00105` D3, scenario Q |
| the Grafana-out-for-hours procedure | `00105` D5 |
| the red button | ruled 2026-08-29 (whole account, market orders); spec `00106`, its own PR — registered in the memo queue |
| the reboot-window overlap check; drills for [[T0039]] / [[T0043]] | dropped with reasons in `00105` D1 |
| the go/no-go clause's three named drills and its "ops drill log" artifact | `00105` D4 (E, F2, G) and D2; RUNG 3's dependency in the memo re-pointed from this topic to the drill log |
| the refdata routine | delivered 2026-08-04 as `refdata-sweep-due` ([[T0113]]) |

The one open sibling this leaves in place: [[T0027]]'s remaining step — order-state reconciliation across a mid-order reboot — is exactly `00105`'s drills A1/A2/G, and T0027 now names them as its instrument.
