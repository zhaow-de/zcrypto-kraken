---
status: resolved
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

- **The rule was tested against history rather than against a manufactured converge.** Every converge and restart timestamp recorded in `docs/reference/fleet-pins.md` — 52 of them across the capture era — was checked against the four published windows. **None has ever landed inside one.** The closest approach is **99.2 minutes**: the 2026-08-20 primary capture re-pin at `05:21:51`, one hour thirty-nine before that same morning's `07:01` window. Operations does use the region of the clock this rule constrains (hours 05 and 07 both appear in the history), so the rule is prophylaxis against a near-miss that has already happened once, not a rule about a place nobody goes.

## Done so far

- **The feed was read and the finding is recorded** — all four `both_streams_silent` episodes match a published "Kraken Website and API Maintenance" entry (components include REST and WebSocket), created 48–145 h ahead, capture going dark 1.1–4.3 s after each published start. The table above is that measurement.
- **The scheduling exclusion has landed on both operating surfaces**, which was this topic's concrete payoff:
  - `.claude/rules/capture-deploys.md`, `## Deploys` — never converge inside a published window, with the component filter, the biweekly 07:01–07:16 UTC cadence, and the trap that entries appear only 2–6 days ahead so an empty feed a week out is not evidence the window is clear.
  - `docs/reference/fleet.md`, the reboot `Schedule:` line — the same exclusion, because the ~83 s reboot gap creates the identical conflation. Stated where a reboot is actually planned rather than only in the converge rule.
- **Engine converges were already immune and are left alone** — their window is the 4-hourly inter-cycle gap (00/04/08/12/16/20 UTC), so 07:01 can never fall inside one. Capture, ops and reboots had no time constraint at all; those are the real exposure.
- **Checked at the time of writing (2026-08-21T06:43Z): no upcoming `Website and API` window is published.** The last was 2026-08-20; on the biweekly cadence the next is ~2026-09-03 and should appear 2–6 days before it.

- **What has already landed on `develop` from this finding** (via the [[T0146]] PR, 2026-08-21, not this topic's own branch): the hygiene map now carries a row for **all three** in-era venue episodes — 2026-07-27 was missing until then — each naming its published window and citing this topic; and the archived [[T0146]] records that 2026-07-27 was *announced* rather than an unannounced WS restart, correcting [[T0101]]'s filing. This topic's own scheduling changes are on a separate branch and are **not** on `develop` yet — see the memo for that branch's state.
- **Discharged on the retrospective evidence, not on a manufactured converge.** The original `ripe_when` demanded "a converge has been placed using it", which made this topic hostage to unrelated work and invented a gate the repo applies to no other rule in `.claude/rules/`. What actually needed proving is that the rule is sound and non-vacuous, and all four parts are now proven without touching production: the feed is reachable and parseable, its `components` filter selects the capture path, the guidance sits in the two lists an operator actually consults, and the 99.2-minute near-miss shows it constrains a region of the schedule genuinely in use.

## Resolution

**Resolved 2026-08-21.** The scheduling exclusion is live on both operating surfaces and the finding behind it is recorded where it will be read.

**What was rejected, and why it matters.** The obvious way to close this was to schedule a converge, read the feed, and roll back. It was declined on three grounds, in ascending order: no capture re-pin is owed at all (capture and engine both run `636012cc00d9`; it is *ops* that is ahead, and `capture-deploys.md` says to match the pin to the service rather than to the repo), so it would have been production work performed for bookkeeping; the rollback is itself a second converge, doubling the exposure on the unbackfillable path to validate a scheduling guideline; and it still could not prove the only genuinely unproven part — that a human consults the rule — which is equally unproven for every other rule in this repo and gates none of them.

**What replaced it.** A retrospective test with the same evidentiary force and no production risk: 52 recorded converges, zero collisions, a 99.2-minute closest approach on an outage day. A rule that has never bound is not the same as a rule that cannot bind, and the near-miss is what separates the two.

**Accepted limitation, stated rather than deferred:** whether an operator actually reads the feed at the next converge is not proven and will not be until one happens. That is the ordinary condition of every rule here, and it is not a reason to hold a topic open — the guidance being *on `develop`* is what makes it available at that moment, which holding the branch would have prevented.

**The next converge inherits a concrete checklist**, in `capture-deploys.md`: fetch `scheduled-maintenances.json`, filter to entries whose `components` carry `WebSocket` or `REST`, and keep out of any published window — checking at planning time *and* again immediately before, since entries appear only 2–6 days ahead.
