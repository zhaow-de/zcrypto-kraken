---
status: open
ripe_when: the ops node is offline (or its timer misses) for more than one day
---

# `Persistent=true` + `--date yesterday` silently skips a multi-day outage

## Context — what

Spec `00054` D9 scoped the ops node's daily verified-replay to a single day (`zcrypto engine replay --path verified --date $(date -u -d yesterday +%F)`), bounding a cost that previously grew with the archive forever. `zcrypto-verified-replay.timer` fires daily at 05:23 UTC with `Persistent=true`.

## Why this matters

`Persistent=true` runs a missed timer **once** on boot — not once per missed occurrence. Combined with `--date yesterday`, a three-day outage therefore replays exactly **one** day (the day before it came back) and the other two are never verified. Nothing reports the gap: the unit succeeds, the dead-man pings, and `ops_verified_replay_last_success_timestamp` goes fresh — so the metrics say "healthy" while two days went unchecked.

The previous whole-journal replay covered this **by accident**: replaying everything every day meant a missed run was harmless. Bounding the scope removed that accidental safety net along with the unbounded cost. This is a real trade the iteration made knowingly and deferred, not an oversight.

## Findings so far

- Introduced deliberately in spec `00054` D9; flagged by the implementer at the time, and by the reviewer, both of whom were told not to fix it in-task (scope).
- The same reasoning applies to `zcrypto-verify-replay.timer` (03:41 daily, also `Persistent=true`), which was **not** re-scoped by D9 — so it is unaffected today, but any later `--date` scoping of it inherits this gap.
- Not yet triggered: the ops node has not been offline for more than a day since the change landed.

## Suggested next steps

- Pick a mechanism and implement it:
  - **Watermark, not "yesterday"** — persist the last successfully-replayed date and replay every day from there to yesterday. Self-healing, bounded in steady state, and the honest fix; costs a state file and a loop.
  - **Detect and report** — keep `--date yesterday` but compare the journal's available days against a watermark and publish an `ops_verified_replay_unverified_days` gauge, alerting when it is non-zero. Cheaper; converts a silent gap into a visible one without changing behaviour.
  - **Accept and document** — decide multi-day outages are rare enough and their re-verification manual. Only defensible if written down where the operator will read it after an outage.
- Recommend the **watermark**: it is the only option where the system is correct after an outage without a human remembering anything.
