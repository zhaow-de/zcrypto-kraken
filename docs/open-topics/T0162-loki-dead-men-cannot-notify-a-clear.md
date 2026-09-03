---
status: partial
ripe_when: "both capture rows in `docs/reference/fleet-pins.md` pass `fleet-deploys.md`'s grafana-push bar: for each row's build revision, `git show <revision>:cli/capture/segment_writer.py | grep -qF 'and not self._parts_for(self._hour_dir(hour)'`"
---

# A Loki-sourced dead-man can never notify its clear

## Context — what

Every Loki-sourced alert rule pins the `logs` receiver, and `grafana-push.sh` mints that contact point with `disableResolveMessage: true`. So **no Loki rule sends a resolved notification, ever.** The setting is deliberate and its stated reason is sound for what it was written about: *"Loki alerts resolve by aging, a resolve ping is noise"* — true of the ERROR-log rules, where a burst ages out of a window and nobody needs telling.

It is not true of a **dead-man**, where the clear means *the thing that was dead is alive again*. Eight Loki rules are dead-men: `nas-archive-pull-stalled`, `engine-log-dead`, `ops-log-pipeline-dead`, `ops-poller-log-dead`, `ops-unit-parse-dead`, `ops-journal-transport-dead`, `capture-log-dead-primary`, `capture-log-dead-secondary`.

## Why this matters

An operator who was paged has no channel signal that the condition ended. They must open Grafana and read rule state — which is now written into `drills-telemetry.md`, so the gap is *survivable*, not silent. The cost is that a recovery is invisible on the surface where the failure was announced. Three of the eight watch the capture and engine LOG paths — so a missed clear costs observability of those hosts, not L2 itself.

It also cost a wrong repair. The gap was attributed on 2026-08-31 to a label mismatch making recovery a `MissingSeries` deletion; a rule was edited on that theory and a seven-rule rollout planned. Drill N's 2026-09-02 re-induction disproved it — the edited rule cleared with both arms unlabelled and still sent nothing, while `zcrypto-hcio-watchdog`, the same expression shape but on `metrics`, resolved in about a minute.

## Findings so far

- `infra/scripts/grafana-push.sh` mints `zcrypto-slack-logs` with the flag set; `docs/specs/00084-*.md` tabulates it and states the consequence outright — the resolved branch of the `logs` title template is unreachable in production.
- Measured: 12 of 12 Loki-sourced rules pin `logs`; no Prometheus rule does. Both receivers deliver to the same webhook and channel.
- Drill N, 2026-09-02: fired 21:24:40Z, cleared ~21:28Z, no resolved notice. `Gate · exporter stale` and `Fleet · healthchecks.io watchdog` both resolved to the same channel within ~1 min on `metrics`.

## Done so far

The receiver split landed on `fix/loki-dead-men-notify-clear`, in the commit `fix(obs): the eight Loki dead-men pin the receiver that can announce their clear`: the eight dead-men pin `metrics`, the four ERROR-log rules stay on `logs` where T0047's reasoning still holds. The first shape was taken — a third receiver would have bought one templating sentence for the price of a third as-code contact point threaded through two verification loops in `grafana-push.sh`.

A guard landed with it, coupling the two files rather than restating either: `tests/test_infra_alert_rules.py::test_a_rule_that_fires_on_absence_can_notify_its_clear` refuses a rule that fires on absence while pinning a receiver `grafana-push.sh` mints with `disableResolveMessage: true`, and reads that receiver set from the script, so it fails if either the pin or the flag moves. The two families are separated structurally — `lt` for a dead-man, `gt` for a burst — so a ninth dead-man added later is caught too; that case was proven by mutation rather than assumed. `test_a_burst_rule_keeps_the_receiver_that_suppresses_its_resolve` is its true positive and guards against the over-correction of moving the whole Loki family.

**Nothing is live yet.** The change is as-code only — the live stack still suppresses every Loki resolve until `grafana-push.sh` runs — so no doc describing what an operator sees was re-tensed. That flip belongs to the push.

## Suggested next steps

- **The attended push, then the induction.** When `ripe_when` clears, push from merged `develop`, then verify by induction rather than by reading config: page one of the eight (drill N's procedure in `infra/runbooks/drills-telemetry.md` is repeatable), clear it, and confirm a resolved notice arrives in `#zcrypto`.
- **Re-tense the docs in that same change.** `infra/runbooks/drills-telemetry.md` records that no resolved notice arrives for a Loki dead-man — true of the live stack until the push, false after it.

Two things a future evaluator of `ripe_when` trips on, both from `fleet-deploys.md`. A PASS counts only against a row whose `since` matches that host's current container start: a Phase-4 rollback is a hand compose re-pin that appends no deploy-log line and re-trues no pins row, so a stale row passes for a host that would fail. And the hatch that rule names — a `git revert` of the commit `fix(obs): a start-correlated counter is the one increase() cannot read`, for a rule that must ship inside the window — re-arms the hazard, making a passing trigger wrong until the revert is itself reverted.

Read 2026-09-03: both capture rows pin revision `8f4ac521`, which fails the check, as does the rollback operand `eb6a503a`; `develop` carries the narrowed predicate but no capture rollout has shipped it to the hosts. The trigger is correctly false today.

**Do not "fix" this by editing rule expressions.** That was tried and disproved; `alerts.yaml`'s comment beside `nas-archive-pull-stalled` records why, and re-deriving it from this file's git history would reach the wrong answer.
