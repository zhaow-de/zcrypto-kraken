---
status: partial
ripe_when: 'the `zcrypto-liquidations` description still names two withholding conditions where the code now has three — read it back through the read-only key, the way `tests/fixtures/healthchecks_descriptions.json` is fetched'
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

- Reproduced end to end on `bf6dce0c`, one `_poll_once` per case with `_run`'s own ping gate applied verbatim. Healthy: `_poll_once -> True`, ping sent, `12.parquet` written. The same cycle with the write refused: `_poll_once -> True`, **ping sent**, nothing written. The two modes are indistinguishable on every external signal.
- The failing write must be injected BELOW `_write_part`'s own `except Exception`, never by replacing `_write_part`: a double that replaces the method removes the swallow under study and the `OSError` propagates, which is not what production does. `_replace_durably` — the last statement inside that `try` — is where a read-only or full mount actually fails, and patching it reproduces the swallow at any euid, so no root-skip is needed.
- One caller today, adjudicated: `cli/liquidations/coinalyze.py:261` inside `_poll_once`. It pings a dead-man after the sweep — `_run`'s `if ok and not watermark.breached and watermark.measurable: ping_healthcheck(...)` — so a silent sweep failure is a false all-clear there. No other call site exists in `cli/`; the two other `git grep` hits are the method's own definition and a comment.

## Done so far

The code half is resolved by the commits below.

- `finalize_completed_hours` returns `FinalizeOutcome(finalized, failed)` instead of a bare count — `fix(capture): a sweep that wrote nothing was indistinguishable from one with nothing to do`. `failed` is read off one fact, no final on disk after the attempt; an hour that was already final and stays so is in neither half, which is the merge this class declines.
- That reading was got wrong once and corrected under review — `fix(capture): the already-final gate hid the very loss this branch exists to report`. Gating the failed arm on `already_final` suppressed the case where an UNREADABLE final is quarantined and its rebuild then fails, leaving the hour with no final at all: T0175 surviving inside its own fix.
- `_poll_once` logs the lost hours by name and returns False, so `_run`'s gate withholds the ping while every other writer still gets its sweep. The `logger.error` also reaches `zcrypto-ops-error-logs`, so the withhold has a second, independent signal.
- Guards, each proven by restoring the defect under `infra/scripts/mutate-probe.sh`: the red test (`test_a_finalize_that_wrote_nothing_withholds_the_dead_man_ping`), its true positive, the open-hour and crash-leftover report arms, and the caller's withhold.
- `infra/runbooks/observability.md`'s dead-man map names the third withholding condition — `docs(obs): the dead-man map's liquidations row gains the third condition that now withholds its ping`.

## Suggested next steps

- **(human)** Rewrite the `zcrypto-liquidations` check's description in healthchecks.io to name the third withholding condition (`zcrypto-daily-ops` step 6's mechanics: the admin key from the capture-host vault, the description field only, read back after), after the fix lands.
