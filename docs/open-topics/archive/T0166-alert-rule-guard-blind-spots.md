---
status: resolved
---

# The alert-rule guard's blind spots

## Context — what

`tests/test_infra_alert_rules.py` guards `infra/grafana/alerts.yaml`. The prose cleanup (T0164) found four places where the guard's own comments, or the rules' comments, describe a check narrower than its sentence — the limit is now written as a decision in the test file until this topic closes it.

## Why this matters

The guard is what lets an alert-rule edit ship on a test's word. A dead-man that the classifier does not recognise can pin the resolve-suppressing receiver and pass; a container the ERROR rule's selector misses ships errors nothing watches.

## Findings so far

- `_fires_on_absence` classifies a dead-man by a THRESHOLD node's `lt` evaluator only. A rule that folds the comparison into a `math` node (`$B < 1` thresholded `gt 0`) and pins `logs` passes `test_a_rule_that_fires_on_absence_can_notify_its_clear`; `zcrypto-engine-dark-with-exposure` and `zcrypto-ops-verify-replay-backlog-stuck` already have that shape (both on `metrics`, so not a live defect today).
- `_RUNBOOK_LINK` is claimed fail-closed on a dot-bearing anchor (the anchor class truncates the match and the resolve assertion fails rather than skips); no test constructs one.
- The ops ERROR rule's container selector is a list; a container the ops compose or journal keep-regex admits but the list omits ships errors nothing watches.
- The memory-limit pin ties each limit literal to its ansible variable; nothing asserts that every limited job has a headroom leg (the liquidations poller and the NAS archive-pull are deliberately absent, with reasons in the file).

## Resolution

Every item was decided by the owner on 2026-09-05, per item, in an attended session; commits are cited by subject (branch `fix/t0165-t0167-asserted-in-prose`).

- `_fires_on_absence`'s math-node limit: **recorded drop** — the paragraph stays in `tests/test_infra_alert_rules.py` as the standing instruction (widen the classifier, never the receiver); a math-node dead-man is caught at review. Both math-node rules today pin `metrics`.
- `_RUNBOOK_LINK` on a dot-bearing anchor: **test** — `test(obs): three of the alert-rule guard's stated limits become assertions`, `test_the_runbook_link_pattern_truncates_a_dot_bearing_anchor_so_it_cannot_resolve`; KILLED when `.` is admitted into the anchor class.
- The ops ERROR rule's selector against the ops log plane: **test** — same commit, `test_the_ops_error_rule_selects_every_container_the_ops_log_plane_can_emit`, deriving the labels from the ops journal keep-regex, Alloy's stream and the poller's `ZCRYPTO_LOG_SERVICE`; KILLED when `liquidations` is dropped from the selector.
- Every memory-limited job has a headroom leg: **test** — same commit, `test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence`, the limited compose sources pinned by glob and each rendered (host, job) covered or named absent with its reason; KILLED when the engine leg is renamed.

## Suggested next steps

_(none remain — see Resolution)_
