---
status: resolved
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

## Resolution

Each item decided by the owner on 2026-09-05; commits cited by subject; all four `alerts.yaml` comments left the file in the rule commit.

- Replay counters: **`NOT_A_FAULT_SIGNAL` entries** — `feat(obs): a verify-replay timer that stops firing pages, and the unwatched-metric guard sees the sweep's whole textfile`. The guard's candidates also derive from the runner's `# TYPE` lines (`_verify_replay_series`); `reused_hours`, `duration_seconds`, `audit_mismatches` are excluded with reasons — a human read on the ops host, the owner's word. KILLED when the `reused_hours` entry is deleted.
- The gap the widening surfaced — nothing watched whether the sweep RUNS; its gauges hold their last value between runs: **new rule** `zcrypto-ops-verify-replay-stale`, 48 h on `ops_verify_replay_last_run_timestamp`, mirroring the verified-replay sibling, with its `infra/runbooks/ops.md` section and panel bar. The owner's option named the last-success stamp; the rule reads the last-run stamp because a standing bad hour freezes `last_success_timestamp` (rc stays 1) — the exit-code page this family retired. KILLED when the expression stops naming the stamp and when the panel bar leaves 48 h.
- Rule health: **the daily pass reads it** — `feat(ops): the daily pass reports every alert rule Grafana could not evaluate`: a rule whose `health` is not `ok`, or whose instance state keeps the `(Error)` reason that, by ngalert's source, `execErrState: OK` leaves (the read-back above saw the suffix shape live, not that mapping), is listed under "Rules not evaluating" with its `lastError` where Grafana attaches one, and the pass exits non-zero.
- Discovery wedged: **recorded drop** — the rollout that retired `zcrypto-alloy-docker-sd-wedged` (spec 00068 D6/D8) removed docker discovery fleet-wide; nothing is left to wedge.
- Deleted `.prom`: **recorded drop** — the 5-minute timer recreates the file, and a missing directory fails the exporter's `mktemp` loudly; the residual is a directory removal nobody performs.

### Pushed and read back by value

Pushed live 2026-09-05 10:41Z by `zcrypto-main` with `infra/scripts/grafana-push.sh` from this branch's reviewed tip, ahead of the merge on the owner's word (`fleet-deploys.md`); four dashboards, template byte-identical, rules pushed, datasources verified, no orphans. Read back at 10:42Z: the provisioned rule equals `alerts.yaml` on expression, `for`, threshold, `noDataState`, receiver and title; every rule in the rules API carries `health`, none other than `ok`, none firing; the new rule `inactive` with no `lastError` and no instances, the ops host's last run 23,551 s old against the 172,800 s bar; the reason suffix `_reason_of` reads was live on one `Normal (NoData)` instance — the shape, not the `execErrState: OK` → `(Error)` mapping, which no instance carried at that moment; the live `zcrypto-integrity` board equals `data-integrity-dashboard.json` on every version-free key, panel 302 whole (gridPos aside) with the bar on both sides.

## Suggested next steps

_(none remain — see Resolution)_
