---
status: open
ripe_when: now — measured, not predicted. Every `both_streams_silent` record in the live ledger matches a "Kraken Website and API Maintenance" entry in `https://status.kraken.com/api/v2/scheduled-maintenances.json`, each published 2–6 days ahead. Nothing in this repo reads that feed. Discharged when the scheduling guidance names it and a converge has been placed using it.
---

# Every fleet-dark episode was a Kraken maintenance published days in advance

## Context — what

All four `both_streams_silent` records match a scheduled-maintenance entry Kraken published on its public status API, under the same name each time — **"Kraken Website and API Maintenance"**, components `Website, FIX, REST, WebSocket, Embed`. The WebSocket component is our capture path.

| Ledger episode | Published window | Entry created | Lead time | Our fleet-earliest gap start |
| --- | --- | --- | --- | --- |
| 2026-07-13 | `07:00:00 → 07:15:00` | 2026-07-07T10:53:24Z | **140.1 h** | `07:00:00` (head-truncated by [[T0036]]) |
| 2026-07-27 | `07:01:00 → 07:16:00` | 2026-07-21T05:54:14Z | **145.1 h** | `07:01:04.071744` |
| 2026-08-06 | `07:01:00 → 07:16:00` | 2026-08-04T06:26:34Z | **48.6 h** | `07:01:01.107346` |
| 2026-08-20 | `07:01:00 → 07:16:00` | 2026-08-18T06:19:52Z | **48.7 h** | `07:01:04.336045` |

Our capture goes dark **1.1–4.3 s** after each published start. The cadence is roughly biweekly.

## Why this matters

**The 07:01 clustering is not a signature to investigate — it is a calendar we are not reading.** [[T0101]] parked this at n=2 as "a signature worth acting on, not an established schedule", and treated 2026-07-13 and 2026-07-27 as *unannounced* WS service restarts. Both were in fact published six days ahead. The mechanism was never mysterious; nothing in the repo was looking.

Two consequences follow, and the second is the valuable one:

- **Scheduling.** A capture re-pin, engine converge or panel regeneration landing inside a maintenance window conflates two failure sources exactly where the ledger is least readable. The fleet restarts hosts on a schedule we choose, and the venue publishes its schedule days ahead — there is no reason for the two to collide.
- **Advance classification.** [[T0105]] dropped the pre-drain because the WS `effectiveTime` gave **zero** lead time, and [[T0143]]/`00096` reasoned throughout as though no advance signal existed. That reasoning was about the wrong source. A feed with 2–6 days' notice means a fleet-dark window can be *expected* rather than diagnosed — and an expected gap is a very different operational object from a surprise one.

## Findings so far

- **The feed retains history**, so it is readable both forward and backward: entries for 2026-07, 2026-08 and 2026-09 are all present in a single fetch. This also refutes, in passing, a claim `00096` and [[T0144]] made — that no retroactively readable form of venue status exists. One exists; it is a third-party HTTP surface, which is a different objection.
- Kraken's WS `status` ladder (`maintenance` → `cancel_only` → `post_only` → `online`) is the *same* event seen from a second angle, with zero lead time. The two sources agree and neither was being used for scheduling.
- Alert `activeAt` lags frame receipt by the rule's `for: 5m`, so the six 2026-08-20 instances at 07:07–07:16Z correspond to frames from ~07:02.

## Suggested next steps

- **Autonomous, and worth doing first:** fetch the feed and list every future `Website and API` entry. That is the converge-scheduling calendar, available now, and it costs one HTTP GET.
- **Add the exclusion to the scheduling guidance** in `.claude/rules/capture-deploys.md`, beside the existing "measured book-traffic trough" constraint: check `scheduled-maintenances.json` before placing a converge, and keep out of any published `Website and API` window. One clause, no machinery.
- **Then decide whether anything should poll it.** Weigh honestly against `00096` D1's ruling: a third-party HTTP feed is soft telemetry and must never gate the append-only ledger. Scheduling and operator triage are different consumers from booking, and only the first two are safe. A cheap first form is a note in the runbook, not a service.
- **Do NOT build a time-of-day alert.** It would fire on the calendar rather than on the event.
