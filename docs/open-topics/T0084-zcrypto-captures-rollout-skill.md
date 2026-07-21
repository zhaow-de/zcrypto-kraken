---
status: open
ripe_when: before the next capture-image rollout — the skill should exist by the time it is next needed (rollouts are expected to be rare once the harness work settles)
---

# `/zcrypto-captures-rollout` — wrap the capture-image canary rollout into a skill

## Context — what

The capture-image rollout discipline (canary order, ≥24 h secondary bake, Slack T+24h reminder, primary re-pin gates, verification by outcome) lives in `.claude/rules/capture-deploys.md` — an always-loaded rule file that cannot be scoped to a path, so it sits in every session's context forever. This topic tracks wrapping the procedure into a skill callable by human or model, so the discipline is *executable* rather than ambient.

Deliberately isolated from [[T0081]] (the Alloy bump skill): different procedure, different risk profile (capture images restart unbackfillable capture; Alloy is telemetry-only), different triggers.

## Why this matters

Standing rules grow context on every session whether or not a rollout is near; a skill loads only when invoked. And a procedure encoded as an executable checklist (with its gates as steps) is harder to half-follow than one recalled from ambient prose — the canary rule's history shows the cost of a missed step is permanent data loss.

## Findings so far

- `capture-deploys.md` already contains the full procedure: canary rule, digest verification by label, pre-staging, stop→start window contents, outcome verification (`<HH>.parquet` boundaries, manifests, continuity.py), maintenance windows, and the Slack-scheduled T+24h reminder.
- The rule file cannot shrink to a pointer until the skill exists and has run at least one real rollout.

## Suggested next steps

- **(When ripe)** Write the skill from `capture-deploys.md` verbatim-in-substance (steps, gates, checks), `disable-model-invocation: false` per the owner's note that model invocation is acceptable here — confirm that choice at build time.
- **(After its first real rollout)** Shrink `capture-deploys.md` to the invariants + a pointer to the skill; the rule file keeps only what must hold even outside a rollout (SSH posture, vault safety, window times).
