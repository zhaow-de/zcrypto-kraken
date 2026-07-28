---
status: resolved
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

## Resolution

**Resolved 2026-07-28 by commit `fbfc8fa2`**, on a shared carrier with [[T0043]] — the same defect class (a real outcome with no printed bucket) in the same sweep.

- **The decision, ruled by the owner: the counter does NOT participate in the residual arithmetic.** A fetched-but-unminted row is retryable — the next run re-detects the gap and re-fetches it — so booking it as an explained absence would make the strongest check in the sweep go quiet on exactly the failure it exists for. The reasoning is written beside the counter in `cli/trades/backfill.py`, and `test_a_mint_failure_still_trips_the_accounting_invariant` pins it: the invariant still reports `unaccounted=3` while `mint_failed=3`.
- **`trades_mint_failed` counts `union.added_from_secondary`** — the same quantity `recovered` uses, so the two are directly comparable — accumulated in the `except` branch that previously only logged and `continue`d. The isolation the topic required is preserved: one bad mint still does not end the sweep.
- **Both printers pinned**, the `logger.info` format string and `cli/archive/command.py`'s `typer.echo`, because T0078's review found that deleting a bucket from the format string left every test green when only the result object was asserted.
- **`README.md`'s "every outcome bucket a fetched or existing row can land in" is true again.**
