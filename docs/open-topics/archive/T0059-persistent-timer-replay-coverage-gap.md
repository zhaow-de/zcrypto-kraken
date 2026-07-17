---
status: resolved
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

## Done so far

Resolved 2026-07-17 (iter-101, `feat/ops5-offload`) by the recommended **watermark** — the only option where the system is correct after an outage without a human remembering anything:

- **The catch-up loop shipped and is deployed to ops (converged)**: the verified-replay persists the last successfully-replayed date and replays every day from the watermark through yesterday (`24c58b6`), so a multi-day outage is caught up on the next run instead of silently skipped. The `Persistent=true` interaction is now **harmless by construction** — the missed timer's single catch-up run covers every missed day.
- **Hardened against every failure mode found, each execution-reproduced then fixed** (`d100a6f`, `df56b8b`): a zero-byte watermark (interpolated into `date(1)` it parsed as TOMORROW — a permanent silent-skip that bumped `last_success` and fed the dead-man forever), garbage and shape-valid-but-nonexistent dates (loud refusal, watermark untouched), an unpersisted seed, an empty journal day (the day probe requires actual cycle artifacts, and the watermark only advances past a day once its successor has started arriving — a mid-day journal stall can no longer mark a partial day verified forever), and future dates.
- **First organic timer run: 2026-07-18 05:23 UTC.** `zcrypto-verify-replay.timer` (03:41, also `Persistent=true`) was never `--date`-scoped and remains whole-journal, so it stays unaffected — and any future scoping of it now has the watermark loop as the established template.
