---
status: partial
ripe_when: the next converge or attended reboot is planned — the guidance now names the feed, so the remaining half discharges the first time a window is actually read before scheduling one. No new measurement is owed; the check is `https://status.kraken.com/api/v2/scheduled-maintenances.json` filtered to entries carrying `WebSocket` or `REST` in `components`.
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
- **The downstream cost is now measured, not assumed.** [[T0146]] counted what these windows actually do to the L2 panel: a venue-dark window is carried forward as a **frozen book** on the 1 s grid, **173.2 fabricated rows per pair** for 2026-07-27 and **852.2** for 2026-08-06. Those rows are not a hole a consumer can see — they are plausible-looking prices, and every mean computed over the window silently includes them unless the reader filters `stale_seconds > 30`. So a converge placed inside one of these windows does not merely muddy an incident: it lands during the only hours whose panel data is fabricated.
- **Advance classification.** [[T0105]] dropped the pre-drain because the WS `effectiveTime` gave **zero** lead time, and [[T0143]]/`00096` reasoned throughout as though no advance signal existed. That reasoning was about the wrong source. A feed with 2–6 days' notice means a fleet-dark window can be *expected* rather than diagnosed — and an expected gap is a very different operational object from a surprise one.

## Findings so far

- **The feed retains history**, so it is readable both forward and backward: entries for 2026-07, 2026-08 and 2026-09 are all present in a single fetch. This also refutes, in passing, a claim `00096` and [[T0144]] made — that no retroactively readable form of venue status exists. One exists; it is a third-party HTTP surface, which is a different objection.
- Kraken's WS `status` ladder (`maintenance` → `cancel_only` → `post_only` → `online`) is the *same* event seen from a second angle, with zero lead time. The two sources agree and neither was being used for scheduling.
- Alert `activeAt` lags frame receipt by the rule's `for: 5m`, so the six 2026-08-20 instances at 07:07–07:16Z correspond to frames from ~07:02.

## Done so far

- **The feed was read and the finding is recorded** — all four `both_streams_silent` episodes match a published "Kraken Website and API Maintenance" entry (components include REST and WebSocket), created 48–145 h ahead, capture going dark 1.1–4.3 s after each published start. The table above is that measurement.
- **The scheduling exclusion has landed on both operating surfaces**, which was this topic's concrete payoff:
  - `.claude/rules/capture-deploys.md`, `## Deploys` — never converge inside a published window, with the component filter, the biweekly 07:01–07:16 UTC cadence, and the trap that entries appear only 2–6 days ahead so an empty feed a week out is not evidence the window is clear.
  - `docs/reference/fleet.md`, the reboot `Schedule:` line — the same exclusion, because the ~83 s reboot gap creates the identical conflation. Stated where a reboot is actually planned rather than only in the converge rule.
- **Engine converges were already immune and are left alone** — their window is the 4-hourly inter-cycle gap (00/04/08/12/16/20 UTC), so 07:01 can never fall inside one. Capture, ops and reboots had no time constraint at all; those are the real exposure.
- **Checked at the time of writing (2026-08-21T06:43Z): no upcoming `Website and API` window is published.** The last was 2026-08-20; on the biweekly cadence the next is ~2026-09-03 and should appear 2–6 days before it.

- **What has already landed on `develop` from this finding** (via the [[T0146]] PR, 2026-08-21, not this topic's own branch): the hygiene map now carries a row for **all three** in-era venue episodes — 2026-07-27 was missing until then — each naming its published window and citing this topic; and the archived [[T0146]] records that 2026-07-27 was *announced* rather than an unannounced WS restart, correcting [[T0101]]'s filing. This topic's own scheduling changes are on a separate branch and are **not** on `develop` yet — see the memo for that branch's state.

## Suggested next steps

- **Read the feed when the next converge or reboot is scheduled.** That is the whole remainder, and it is what discharges this topic — the guidance exists, but a rule nobody has yet executed is unproven.
- **Then decide whether anything should poll it.** Weigh honestly against `00096` D1: a third-party HTTP feed is soft telemetry and must never gate the append-only ledger. Scheduling and operator triage are different consumers from booking, and only those two are safe. A note in the runbook is the cheap first form; a service is not obviously warranted for a check run a handful of times a month.
- **Do NOT build a time-of-day alert.** It would fire on the calendar rather than on the event.
