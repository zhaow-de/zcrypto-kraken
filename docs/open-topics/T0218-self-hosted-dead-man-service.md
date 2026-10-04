---
status: open
ripe_when: the spec 00122 and plan 00122 pair is committed on this branch and reviewed by zcrypto-plan-review — check `ls docs/specs/00122-* docs/plans/00122-*` lists both and the branch's PR body names the review
---

# Self-hosting the dead-man service: a tailor-made healthchecks.io replacement

## Context — what

Every dead-man check the fleet relies on lives on healthchecks.io: eleven checks (the capture pair, the engine's shadow, the ops units, the liquidations poller, the panel, the node's self-check, the Grafana watchdog), pinged from five hosts through vaulted ping URLs (`*_healthcheck_url`, seventeen names over eleven values), read by the daily pass through the v3 management API with the read-only key, scraped by the ops Alloy for `hc_checks_down_total` (the `zcrypto-hcio-watchdog` rule), and notifying Slack through healthchecks.io's own integration. The owner has read healthchecks.io's source and judged its quality, security and resilience insufficient, and has started a tailor-made clone: a dead-man ping service with near-complete API compatibility and higher security and reliability standards, intended as a drop-in replacement, with the freedom to change the fleet where the drop-in does not hold. This topic is the iteration that moves the fleet onto it, in the shape of T0217's self-hosting of the observability stack but without a dual-shipping stage: one cutover, every ping URL re-minted, which is also the rotation T0085 has carried as its last step.

## Why this matters

The dead-man checks are the fleet's last line: they page when a host, a daemon or Grafana itself is gone, and a weak service there is a silent fleet. Owning the service closes the external dependency and its security surface, and the cutover is the one time every ping URL changes.

## Findings so far

- The surface, read 2026-10-04 from the tree: pingers in `cli/capture`, `cli/engine` (the cycle's `HEALTHCHECK_URL` and the gate ping), `cli/liquidations`, the ops units' timers and the node's self-check; the management read in `infra/scripts/ops_daily.py` (`HEALTHCHECKS_API`, the read-only key in `group_vars/all/vault.yml`); the ops Alloy's `prometheus.scrape "healthchecks"` at `HC_METRICS_PATH`; the Grafana watchdog's timer on ops; the fixture `tests/fixtures/healthchecks_descriptions.json` holding the eleven checks' descriptions the daily pass checks against the runbooks.
- T0085 names the eleven ping URLs as in scope for the pre-go-live rotation and the two API keys' shapes; T0083 (archived) set the mutual watchdog between Grafana and healthchecks.io.

## Suggested next steps

- Write spec `docs/specs/00122-self-hosted-dead-man-design.md` and plan `docs/plans/00122-self-hosted-dead-man.md` on this branch, the spec carrying `## The measured basis` (the surface above, each item with its command) and the clone's own facts the owner supplies: where it runs, its storage, its API surface and the two things the fleet reads from it (the v3 checks listing, the Prometheus metrics), its notification path, and who watches it.
- Run `zcrypto-plan-review` over the pair; then the task loop, then the cutover rollout, attended.
