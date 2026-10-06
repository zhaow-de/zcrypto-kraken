---
status: open
ripe_when: the spec 00122 and plan 00122 pair is committed on this branch and reviewed by zcrypto-plan-review — check `ls docs/specs/00122-* docs/plans/00122-*` lists both and the branch's PR body names the review
---

# Self-hosting the dead-man service: a tailor-made healthchecks.io replacement

## Context — what

Every dead-man check the fleet relies on lives on healthchecks.io: pinged from five hosts through vaulted ping URLs, read by the daily pass through the v3 management API, scraped by the ops Alloy for the `zcrypto-hcio-watchdog` rule, and notifying Slack through healthchecks.io's own integration. The owner has read healthchecks.io's source, judged its quality, security and resilience insufficient, and built a hard fork: a dead-man ping service with near-complete API compatibility and higher security and reliability standards, intended as a drop-in replacement, with the freedom to change the fleet where the drop-in does not hold. This topic is the iteration that moves the fleet onto it, in the shape of T0217's self-hosting of the observability stack but without a dual-shipping stage: one cutover, every ping URL re-minted, which is also the rotation T0085 has carried as its last step.

## Why this matters

The dead-man checks are the fleet's last line: they page when a host, a daemon or Grafana itself is gone, and a weak service there is a silent fleet. Owning the service closes the external dependency and its security surface, and the cutover is the one time every ping URL changes.

## Findings so far

- The surface and the command that reads each part of it are spec 00122's measured basis.
- T0085 names the eleven ping URLs as in scope for the pre-go-live rotation and the two API keys' shapes; T0083 (archived) set the mutual watchdog between Grafana and healthchecks.io.

## Suggested next steps

- The task loop over plan 00122, then its attended cutover rollout.
