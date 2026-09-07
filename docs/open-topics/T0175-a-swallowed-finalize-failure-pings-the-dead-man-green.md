---
status: open
ripe_when: 'the next change to `cli/capture/segment_writer.py::finalize_completed_hours` or to `cli/liquidations/coinalyze.py::_poll_once` — `git log --oneline develop -- cli/capture/segment_writer.py cli/liquidations/coinalyze.py` shows a commit newer than the one this topic cites'
---

# T0175 — a swallowed finalize failure pings the dead-man green

## Context — what

On a read-only or full mount, `SegmentWriter.finalize_completed_hours` swallows the write failure by its callees' documented contract (`_write_part`, `_merge_hour`), returns 0, and `cli/liquidations/coinalyze.py::_poll_once` returns True and pings the `zcrypto-liquidations` healthchecks.io dead-man. Hours go unfinalized while every signal reads healthy.

## Why this matters

The dead-man is the only external witness of the liquidations poller; a ping after a silently failed sweep is a false all-clear on the capture write path, where a gap is not backfillable within the venue's history window. The same shape may hold for every other caller of `finalize_completed_hours`.

## Findings so far

- Surfaced 2026-09-07 by `zcrypto-alex`'s Opus reviewer while fixing the liquidations `_poll_once` contract (refine-rules round 9's fold-in `fix/round9-live-defects`): probed end to end on a read-only tree with the real writer set — `_poll_once` returns True and pings, before and after the fix. Recorded here as that reviewer's measurement, not re-run by the coordinator; the first next step reproduces it.
- The T0164 retro's claim that a raise from the sweep crash-loops the container was FALSE: `finalize_completed_hours`'s only `raise` is the oracle guard, unreachable from `_run`, which builds writers with no oracle; the rest delegates to callees that swallow.
- The healthchecks fixture's description for `zcrypto-liquidations` enumerates two withholding conditions; a swallowed sweep failure would be a third, and changing the live description is a host action.

## Suggested next steps

- Reproduce: in a scratch worktree, mount-simulate a failing write (`chmod a-w` the hour directory, or a `_write_part` double that raises `OSError`), run one `_poll_once` with the real writer set, and read `finalize_completed_hours`'s return and the ping call — expected today: 0 and a ping.
- Decide the signal: `finalize_completed_hours` returns a count of failed hours beside the finalized count (or raises `CaptureError` on any hour it could not finalize), and `_poll_once` withholds the ping when any hour failed. Widen the guard first: a test where a finalize failure withholds the ping, red before the fix, and the healthy sweep as the true positive; then the fix, then the mutation probe.
- Sweep every caller of `finalize_completed_hours` (`git grep -n finalize_completed_hours -- cli/`) — one adjudication row per call site: does its caller ping a dead-man or publish a healthy gauge after the sweep?
- **(human)** Rewrite the `zcrypto-liquidations` check's description in healthchecks.io to name the third withholding condition (`zcrypto-daily-ops` step 6's mechanics: the admin key from the capture-host vault, the description field only, read back after), after the fix lands.
