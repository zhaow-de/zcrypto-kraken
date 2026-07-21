---
status: resolved
---

# The trade-backfill run summary omits fetch failures, and the README promises it cannot

## Context — what

`cli/trades/backfill.py` accumulates `pair_fetch_error_missing` as a **per-pair local** (assigned ~line 155, accumulated ~line 162). It never reaches `BackfillResult` (~lines 43-54) and never reaches the run-level completion summary (~lines 240-253). It surfaces in exactly one place: the D9 invariant-violation message (~lines 230-232) — i.e. **only once the invariant has already failed.**

A repo-wide grep finds the identifier in three places: those two code sites and the archived [[T0053]] file. Nothing else covers it.

## Why this matters

**`README.md:209` documents the summary as listing "every outcome bucket a fetched or existing row can land in", and asserts that "a run can never read as clean by omitting one." That guarantee is false today** — a fetch-failed gap's missing ids land in no printed bucket. This is the same defect class as the rest of this audit's findings: an artifact asserting something that is not so.

It matters operationally, not just documentarily. The backfill step runs daily on the ops node (`infra/ansible/roles/ops/templates/archive-pull.sh.j2:145-176`), and [[T0053]]'s own fix **deleted the retry**, so `zcrypto_trade_backfill_exit_code` is the sole signal a failed pass emits. That makes this summary the operator's first diagnostic when the critical alert fires — and it is the one number missing from it.

Severity is genuinely low, for two reasons worth recording so nobody over-reacts: the per-gap warning at ~lines 159-161 prints pair/`after_id`/`before_id`, so the count is manually derivable from the journal (un-totalled, not absent), and the D9 invariant subtracts the bucket, so there are no false "clean" invariant passes. The damage is to triage speed, not to data integrity — the raw mirrors are untouched.

## Findings so far

Found by the 2026-07-20 archived-topic audit. The history shows this was **known and dropped, not out of scope**:

- The sibling defect ("report what the detector FOUND, not only what was healed") was fixed first, in `7e145cf`.
- [[T0053]] was opened *after* it, in `d3d0112`, explicitly citing "same defect class as the found-vs-healed split".
- [[T0053]]'s headline fix landed in `69dfbd6`, touching no reporting code.
- `3c6ec30` archived the topic with this accounting finding still sitting in its `## Findings so far` — never promoted to next steps, never handed to a successor.

[[T0053]] itself stays archived: its headline concern is genuinely fixed, and this is a distinct residual rather than a reopening.

## Resolution

**Resolved 2026-07-21** — commit `8a7a436` (+ its review fixes) on `fix/t0078-backfill-summary-fetch-failures`, PR into `develop`. All three prescribed steps landed:

- run-level `fetch_failed` accumulator + `BackfillResult.trades_fetch_failed`;
- the bucket threaded into **both** summary sites — `backfill.py`'s `logger.info` line **and** the CLI's own `typer.echo` in `cli/archive/command.py`. The topic named only the first; the second was found because the command test silences the logger at `--log-level ERROR` and so pins the echo independently;
- `README.md`'s "every outcome bucket / can never read as clean by omitting one" sentence corrected in the same change, so document and behaviour never disagreed.

Both pins were watched failing first and mutation-verified under `PYTHONDONTWRITEBYTECODE=1`; no double-count (fetch-failed ids stay out of `unrecoverable`, since the fetch never answered), D9's arithmetic unchanged, `--detect-only` still reports `0`.

**Two things the execution added to the record.** The review caught that the *logger* site — the one this topic's own acceptance criterion named — was pinned by no test (deleting `fetch_failed=%d` left all 20 green); a `caplog` assertion now pins it, mutation-verified. And a **second residual of the same class** surfaced and was split out rather than absorbed: rows fetched for an hour whose *mint* fails land in no bucket either — [[T0087]], deliberately its own topic because it carries a design question (whether the new counter participates in D9's residual arithmetic; recommended no) and because burying it here would repeat the mis-filing this topic exists to catch.

## Suggested next steps

- **(Autonomous, ~5 lines)** Add a run-level `trades_fetch_failed` accumulator beside the existing counters (~line 112), add the field to `BackfillResult` (~lines 43-54), and thread it into the summary format string and args (~lines 240-253).
- **(Autonomous)** Correct `README.md:209` — the "every outcome bucket / can never read as clean by omitting one" sentence becomes true only once the fix lands. Land both together so the document and the behaviour never disagree.
- **(Autonomous)** Extend `tests/test_trades_backfill.py:249-256` and `tests/test_trades_command.py:77` to cover a fetch-failed gap, so the summary arithmetic is pinned by a test rather than by prose. Mutation-check it: remove the new field from the summary and confirm a test fails.
- **Do NOT fold this into [[T0043]].** That topic's headline is loss-event attribution in `settle.py`; burying a summary-arithmetic fix there would repeat exactly the mis-filing this audit exists to catch.
- Trivial-change path per `.claude/rules/spec-plan-locations.md`: branch off `develop`, TDD, subagent review, PR into `develop` — no committed spec/plan, no iterations-history entry.
