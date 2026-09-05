---
status: open
---

# Observability blind spots the alert comments carry

## Context — what

Four comments in `infra/grafana/alerts.yaml` record a failure mode nothing watches. The prose cleanup (T0164) kept them in the file on `prose.md`'s clause that a blind spot that matters gets a test or a topic — this is the topic; the sentences leave the file when each item below has a rule, a test, or a recorded drop.

## Why this matters

Each is a silent failure on a path an operator relies on: a verification sweep that reverts to full rescans while every rule reads healthy, a rule that stops evaluating without paging, a log shipper alive but blind, a metrics file deleted without a page.

## Findings so far

- Nothing watches `ops_verify_replay_reused`, its duration, or `audit_mismatches`: a busted checkpoint silently reverts every sweep to a full rescan while all three replay rules read healthy. Not in the guard's `NOT_A_FAULT_SIGNAL` list either.
- A rule-scoped evaluation error on the two capture-silence rules — an expression broken by a later edit, a permission or cardinality failure on that query alone — pages nothing, by design; nothing in the repo watches for it.
- Alloy alive with its docker discovery wedged (the T0048 shape) has been undetected since `zcrypto-alloy-docker-sd-wedged` was retired; T0048 is archived, so no live topic tracked it until this one.
- A deleted `.prom` textfile reads healthy to both the mtime and the skew rules.

## Suggested next steps

- Replay counters: either a `NOT_A_FAULT_SIGNAL` entry with the reason, or a rule beside the three replay rules that fires when `ops_verify_replay_reused` stays 0 across sweeps whose duration says full rescan.
- Rule health: a Grafana rule-health read (`health != ok` per rule from `/api/prometheus/grafana/api/v1/rules`) in `infra/scripts/ops_daily.py`'s report, or a rule on Grafana's own evaluation-error series if the instance exposes one — decide which, then land it.
- Discovery wedged: a rule on the shipped-lines counter per container going flat while the container's own log volume does not, or a recorded drop if the rollout that removed the old rule covers it.
- Deleted `.prom`: per-host `absent()` legs on the textfile families each capture host publishes, or a test asserting both capture hosts publish each expected family.
