---
status: open
ripe_when: the next time `tests/test_engine_metrics.py` is touched for another reason, or any iteration that changes `cli/logging/config.py`'s logging configuration (handler wiring, `propagate`) — either touch is the natural moment to fix the ordering dependency alongside.
---

# `test_run_survives_an_unreadable_journal_record_at_metrics_seed_time` fails when run alone

## Context — what

`tests/test_engine_metrics.py::test_run_survives_an_unreadable_journal_record_at_metrics_seed_time` **fails when invoked alone** (`uv run pytest tests/test_engine_metrics.py::test_run_survives_an_unreadable_journal_record_at_metrics_seed_time`) but **passes when the file runs in its normal collection order**. Confirmed by execution twice, and independently by two reviewers, during the `feat/t0018-execution-safety-envelope` final whole-branch review (2026-08-11).

Measured cause: `cli/logging/config.py::configure()` sets `propagate = False` on the `zcrypto` logger (the sole entry in `_TARGET_LOGGERS`). pytest's `caplog` fixture captures by default through a handler attached to the **root** logger, so once `propagate` is `False`, nothing logged under `zcrypto` (or its descendants) reaches it. Logger objects are process-global singletons shared across every test in the same worker, so whether `caplog.records` ends up non-empty by the time this test's `assert any(r.levelno >= 40 for r in caplog.records)` runs depends on what state earlier tests in the same process already left the `zcrypto` logger in — hence the intra-file-order dependency. Run alone, this test's own path through `configure()` sets `propagate = False` before the assertion, and `caplog.records` is empty.

Pre-existing, not introduced by this branch: both the test and `configure()`'s `propagate = False` predate `feat/t0018-execution-safety-envelope`.

## Why this matters

The defect is in test infrastructure — an ordering-dependent `caplog` assertion — not in engine behaviour. The code path under test (graceful degradation when a journal record is unreadable at metrics-seed time) is exercised correctly either way; only the log-capture assertion is order-sensitive. The suite is green in normal operation (`uv run pytest` always collects the file in its default order), so nothing in CI or the commit gate currently observes the failure, and deferring the *fix* is reasonable: it is isolated test-infrastructure work with no trading-behaviour or user-facing impact. What is not reasonable is leaving it unregistered — this branch's own workspace ledger is gitignored and deleted when the branch finishes, so it is not a durable home for a deferred defect.

## Findings so far

- Reproduced twice by execution, and independently by two reviewers, during the branch's final whole-branch review.
- Cause isolated to `cli/logging/config.py::configure()`'s `lg.propagate = False` on the `zcrypto` logger, which starves the root-attached `caplog` handler.
- The order-sensitive assertion is `assert any(r.levelno >= 40 for r in caplog.records)` in `test_run_survives_an_unreadable_journal_record_at_metrics_seed_time`.

## Suggested next steps

- **(autonomous, when ripe)** Make the test order-independent: capture against the `zcrypto` logger directly (e.g. `caplog.set_level` targeted at that logger's own handler, or attaching a handler explicitly to it for the duration of the `with caplog.at_level(...)` block) instead of relying on root propagation.
- **(autonomous, when ripe)** After fixing, verify both ways go green: the single test run alone, and the full file — `uv run pytest tests/test_engine_metrics.py::test_run_survives_an_unreadable_journal_record_at_metrics_seed_time` and `uv run pytest tests/test_engine_metrics.py`.
