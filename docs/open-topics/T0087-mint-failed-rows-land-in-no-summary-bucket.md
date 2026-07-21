---
status: open
ripe_when: ripe NOW as a small change, but it carries one genuine design question (below), so it wants a decision rather than a reflex — take it with the next `cli/trades` touch, or when a mint failure is actually observed in the ops backfill logs
---

# Rows fetched for an hour whose mint fails land in no summary bucket

## Context — what

`cli/trades/backfill.py`'s mint loop isolates a failing mint (`except (CaptureError, OSError)` at ~line 210): it logs a warning, appends to `errors`, and `continue`s. That `continue` skips `pair_recovered += union.added_from_secondary` at ~line 214, so rows that were **successfully fetched** for that hour are counted in no printed bucket — not `recovered` (they never landed), not `unrecoverable` (the REST served them), not `fetch_failed` (the fetch succeeded).

Found 2026-07-21 by the review of [[T0078]]'s fix, which closed the *sibling* case (a gap whose **fetch** raised). This is the same defect class one step later in the pipeline.

## Why this matters

It is the same shape as [[T0078]] — a real outcome with no bucket — but with a materially weaker consequence, and that difference is the reason this is a separate, lower-priority topic rather than part of that fix:

- **No run can read as clean.** A failed mint always leaves the ids absent on disk, so the D9 invariant (~line 228) computes `residual_missing != 0` and prints `unaccounted=N` alongside `errors>=1`. The number is *visible*; it is merely visible only inside a violation message rather than in the normal summary — which is precisely the complaint [[T0078]] made about `fetch_errors`.
- Damage is to triage speed, not data integrity: the raw mirrors are untouched, and the per-hour warning names pair and hour.

## Findings so far

- The `continue` at ~line 213 is deliberate isolation ("one bad mint must not end the sweep") — the fix must preserve that.
- `README.md`'s summary sentence claims "every outcome bucket a fetched or existing row can land in". After [[T0078]]'s fix that is true for every path *except* this one, so the sentence is again slightly ahead of the code.
- The design question, which is why this is not a reflex fix: a fetched-but-unminted row is **retryable** — the next run re-detects the gap and re-fetches. So the honest bucket may be a *transient* counter (`mint_failed`, reset each run) rather than a loss counter, and it must **not** be subtracted in D9's `residual_missing` the way `fetch_error_missing` is, or a genuine post-mint gap would stop tripping the invariant. Getting that backwards would weaken the strongest check in the sweep.

## Suggested next steps

- **(Decide first)** Whether the new counter participates in the D9 residual arithmetic. Recommended: **no** — count it for the operator, keep D9 blind to it, so a mint failure still trips the invariant loudly. Record the choice in the code comment beside the counter.
- **(Autonomous, small)** Add the run-level counter beside `fetch_failed`, thread it into both summary sites (the `logger.info` format string in `backfill.py` **and** the `typer.echo` in `cli/archive/command.py` — [[T0078]]'s review showed the second is easy to miss), and pin **both** with tests: a `caplog` assertion for the log line and a CLI assertion for the echo.
- **(With it)** Extend `README.md`'s bucket sentence so the "every outcome bucket" guarantee is true again.
- Trivial-change path per `.claude/rules/spec-plan-locations.md`: branch off `develop`, TDD, subagent review, PR into `develop` — no committed spec/plan.
