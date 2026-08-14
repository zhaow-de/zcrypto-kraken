---
status: resolved
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
- **A third instance of the identical shape was found by sweeping the defect class, not by its own trigger** (spec `00089` Task 8, 2026-08-13): `test_a_raising_startup_evaluation_never_prevents_the_engine_from_starting` — pre-existing, unrelated to spec `00089` — also fails standalone for the same `configure()`-starves-`caplog` reason. A fourth near-instance was born the same iteration: `test_run_survives_an_unreadable_venue_record_at_metrics_seed_time`, spec `00089`'s own new test, inherited the identical order-dependence at birth.

## Resolution

Fixed 2026-08-13 (spec/plan `00089` Task 8, commit `bd935f6b`): all three affected tests — this topic's own, `test_run_survives_an_unreadable_venue_record_at_metrics_seed_time` (born the same iteration), and `test_a_raising_startup_evaluation_never_prevents_the_engine_from_starting` (pre-existing, found only by sweeping the defect class) — now attach `caplog`'s handler directly to the `zcrypto` logger via a small shared context manager for the duration of the assertion, mirroring the existing fix in `test_archive_replay.py`, instead of relying on root-logger propagation `configure()` turns off. Production code (`cli/logging/config.py`) is untouched.

Verified both ways for all three: `uv run pytest tests/test_engine_metrics.py::<name> -v` run alone, and the whole file in its normal collection order — both green. Each fix proven non-tautological by mutation: silencing the `logger.exception(...)` call the assertion depends on turns the corresponding test red.
