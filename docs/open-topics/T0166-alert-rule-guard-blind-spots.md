---
status: open
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

## Suggested next steps

- Widen `_fires_on_absence` to read math-node expressions as well as threshold evaluators, with a fixture for each form (threshold `lt`; math `$B < 1` under `gt 0`) proven to trip on `logs` and pass on `metrics`; then delete the restored limit paragraph.
- A case that feeds `_RUNBOOK_LINK` a `file.md#some.anchor` string and asserts the captured anchor is truncated, hence unresolvable.
- A test asserting every container the ops journal keep-regex admits is matched by the ops ERROR rule's selector.
- Extend the memory-limit pin: every limited job has a headroom leg, or is named in the file's deliberate-absence list with its reason.
