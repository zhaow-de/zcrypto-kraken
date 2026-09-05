---
status: partial
ripe_when: 'the rule commit is on develop: `git log origin/develop --oneline --grep="^feat(obs): a verify-replay timer that stops firing pages"` is non-empty'
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

## Done so far

Each item decided by the owner on 2026-09-05, per item, in an attended session; commits cited by subject (branch `fix/t0165-t0167-asserted-in-prose`). All four `alerts.yaml` comments left the file in the rule commit.

- Replay counters: **`NOT_A_FAULT_SIGNAL` entries** — `feat(obs): a verify-replay timer that stops firing pages, and the unwatched-metric guard sees the sweep's whole textfile`. The guard's candidates also derive from the runner's `# TYPE` lines (`_verify_replay_series`), so the sweep's eleven series are candidates; `reused_hours`, `duration_seconds`, `audit_mismatches` excluded with reasons — a human read on the ops host, the owner's word. KILLED when the `reused_hours` entry is deleted.
- The gap the widening surfaced — nothing watched whether the sweep RUNS; its gauges hold their last value between runs: **new rule** `zcrypto-ops-verify-replay-stale`, same commit, 48 h on `ops_verify_replay_last_run_timestamp`, mirroring `zcrypto-ops-verified-replay-stale`, with its `infra/runbooks/ops.md` section and panel bar. The owner's option named the last-success stamp; the rule reads the last-run stamp because the runner freezes `last_success_timestamp` while any known bad hour stands (rc stays 1) — the exit-code page this family retired. KILLED when the expression stops naming the stamp, and when the panel bar leaves 48 h.
- Rule health: **the daily pass reads it** — `feat(ops): the daily pass reports every alert rule Grafana could not evaluate`: every rule whose `health` is not `ok`, with its `lastError`, under "Rules not evaluating"; the pass exits non-zero on one. Three TDD tests.
- Discovery wedged: **recorded drop** — the rollout that retired `zcrypto-alloy-docker-sd-wedged` (spec 00068 D6/D8) removed docker discovery fleet-wide; nothing is left to wedge.
- Deleted `.prom`: **recorded drop** — the 5-minute timer recreates the file, and a missing directory fails the exporter's `mktemp` loudly; the residual is a directory removal nobody performs.

## Suggested next steps

- Push the rule (alert-rule lifecycle, `fleet-deploys.md`): after the branch's PR merges, run `infra/scripts/grafana-push.sh` from merged `develop` — attended, the owner's — then read `zcrypto-ops-verify-replay-stale` back from `/api/prometheus/grafana/api/v1/rules`: `health` `ok`, state `inactive` while the ops host's last run is under 48 h old. Record the push here and archive the topic.
