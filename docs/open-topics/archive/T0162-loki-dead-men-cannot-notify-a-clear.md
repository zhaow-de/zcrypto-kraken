---
status: resolved
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

**The push ran on 2026-09-04** (`grafana-push.sh` from merged `develop` `efa9d098`, on the owner's word, after both capture rows passed `fleet-deploys.md`'s bar on revision `4925e060`) and was verified by value against the live stack: all eight dead-men pin `metrics` live as in `alerts.yaml`, every one inactive at the read, no orphaned rule. The receiver that can announce a clear is now the one the live rules use. The runbook sentence that says a Loki dead-man never sends a resolved notice became false at the push; it is re-tensed in the same change as the induction below, whose reading is the proof.

**The induction ran 2026-09-05** (drill N, `docs/reference/drill-log.md`): the dead-man fired at 23:20:40Z on 2026-09-04, cleared at 00:04:40Z after the restore, and its RESOLVED notice reached `#zcrypto` at 00:06:11Z, 91 s after the clear — the reading the 2026-09-02 run could not produce on `logs`. `infra/runbooks/drills-telemetry.md`'s standing rule and the runbooks' receiver claims for the two dead-men are re-tensed in the same change.

## Suggested next steps

_(none — resolved.)_ **Do not "fix" a silent clear by editing rule expressions.** That was tried and disproved — the attribution and the reading that killed it are in `## Why this matters` above. The receiver, not the expression, decides whether a clear is announced: `alerts.yaml`'s comment beside `nas-archive-pull-stalled` now points at `zcrypto-engine-log-dead`, where that mechanism sits beside the test enforcing it.
