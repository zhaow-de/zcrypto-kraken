---
status: open
---

# The keep-alive runbook step says nothing about a 200, and never warns how old the reading may be

## Context — what

`infra/runbooks/observability.md` step 1 of `grafana-cloud-dark` tells an operator to read `grafana-keepalive.prom` on the ops host and routes three of the four things they can find there: a 503, a `0` with a duration at the 120 s cap, and an absent file. It says nothing about a `200`. It also never states how old the reading may be: the keep-alive runs `OnCalendar=*:37:00` while the watchdog probe that pages runs `*:0/5:41`, so the recorded status can be up to an hour behind the event that brought the operator to the page.

## Why this matters

The two gaps compound in one plausible arrival. An operator paged by the watchdog reads step 1, finds a `200`, and has no sentence telling them either what a `200` means here or that it may predate the outage by most of an hour — so the natural reading is "the keep-alive says Grafana is fine", against a page saying it is not. The section they are standing in covers a state where the live trade path runs unwatched and `zcrypto-engine-dark-with-exposure` cannot fire, so a reader who concludes the page is spurious stops in the worst place to stop.

## Findings so far

- `infra/runbooks/observability.md` step 1 routes 503, `0`-at-cap and absent-file, and stops there.
- `infra/ansible/roles/ops/templates/grafana-keepalive.timer.j2` — `OnCalendar=*:37:00`, hourly.
- `infra/ansible/roles/ops/templates/grafana-watchdog.timer.j2` — `*:0/5:41`, every five minutes. The two schedules are what make the staleness bound an hour rather than a scrape interval; it follows from them and from no decision.
- Raised during `feat/grafana-keepalive`'s reviews and deliberately not folded into it. The owner ruled `T0181` with *"let's keep it simple"* and told the coordinator to ship the branch, so adding work to it would have contradicted the ruling. Registered here rather than carried in a PR body, which `open-topics.md` forbids as a deferral's only home.

## Suggested next steps

- Add to step 1 what a `200` means for the reader's situation, and the staleness bound the two schedules imply. One clause each; it is a one-commit fix on a single surface.
- Do it in whatever branch next touches that runbook rather than on its own, unless nothing does — the file is operator-facing and every edit to it has attracted a review round.
- If the owner would rather this had been folded into the shipping branch after all, that closes this topic in one commit.
