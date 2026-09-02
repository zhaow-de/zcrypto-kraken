---
status: open
ripe_when: 'the next attended Grafana push, since the change is a receiver edit that ships through `grafana-push.sh` and cannot be verified without one'
---

# A Loki-sourced dead-man can never notify its clear, and three of them guard unbackfillable data

## Context — what

Every Loki-sourced alert rule pins the `logs` receiver, and `grafana-push.sh` mints that contact point with `disableResolveMessage: true`. So **no Loki rule sends a resolved notification, ever.** The setting is deliberate and its stated reason is sound for what it was written about: *"Loki alerts resolve by aging, a resolve ping is noise"* — true of the ERROR-log rules, where a burst ages out of a window and nobody needs telling.

It is not true of a **dead-man**, where the clear means *the thing that was dead is alive again*. Eight Loki rules are dead-men: `nas-archive-pull-stalled`, `engine-log-dead`, `ops-log-pipeline-dead`, `ops-poller-log-dead`, `ops-unit-parse-dead`, `ops-journal-transport-dead`, `capture-log-dead-primary`, `capture-log-dead-secondary`.

## Why this matters

An operator who was paged has no channel signal that the condition ended. They must open Grafana and read rule state — which is now written into `drills-telemetry.md`, so the gap is *survivable*, not silent. The cost is that a recovery is invisible on the surface where the failure was announced, and three of the eight watch the capture and engine log paths, where the underlying data is unbackfillable.

It also cost a wrong repair. The gap was attributed on 2026-08-31 to a label mismatch making recovery a `MissingSeries` deletion; a rule was edited on that theory and a seven-rule rollout planned. Drill N's 2026-09-02 re-induction disproved it — the edited rule cleared with both arms unlabelled and still sent nothing, while `zcrypto-hcio-watchdog`, the same expression shape but on `metrics`, resolved in about a minute.

## Findings so far

- `infra/scripts/grafana-push.sh` mints `zcrypto-slack-logs` with the flag set; `docs/specs/00084-*.md` tabulates it and states the consequence outright — the resolved branch of the `logs` title template is unreachable in production.
- Measured: 12 of 12 Loki-sourced rules pin `logs`; no Prometheus rule does. Both receivers deliver to the same webhook and channel.
- Drill N, 2026-09-02: fired 21:24:40Z, cleared ~21:28Z, no resolved notice. `Gate · exporter stale` and `Fleet · healthchecks.io watchdog` both resolved to the same channel within ~1 min on `metrics`.

## Suggested next steps

Decide between two shapes, then ship it on an attended Grafana push:

- **Move the eight Loki dead-men to the `metrics` receiver.** Smallest change. Costs the `logs` title/body template on those rules, so check what that template does that `metrics` does not before choosing it.
- **Mint a third receiver** — resolve messages ON, `logs` templates kept — and pin the dead-men to it. Preserves the templating and leaves the ERROR-log rules untouched, at the cost of a third contact point to keep as-code.

Either way the verification is the same and must be done by induction, not by reading config: page one of the rules, clear it, and confirm a resolved notice arrives in `#zcrypto`. Drill N is that induction and is repeatable.

**Do not "fix" this by editing rule expressions.** That was tried and disproved; `alerts.yaml`'s comment beside `nas-archive-pull-stalled` records why, and re-deriving it from this file's git history would reach the wrong answer.
