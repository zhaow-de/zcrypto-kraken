---
status: resolved
---

# Engine test claims no assertion carries

## Context — what

The prose cleanup of `tests/test_engine_executor.py` and `tests/test_engine_flatten.py` (T0164) found four sentences that stated an invariant as reassurance while no test asserts it. The sentences are condensed out; the invariants still hold only by reading.

## Why this matters

All four sit on the live trade path or its operator prompt. A docstring that claims a property nobody checks is the class that produced most of the review findings of 2026-09-04: prose stronger than the mechanism beside it.

## Findings so far

- `_enter` is the only writer of the `resting` phase and stamps `placed_at` in the same body (`cli/engine/executor.py`); nothing pins the single write site.
- The time-box IOC fallback goes through `_submit`, which evaluates the gate first; no test drives a time-box fallback with the gate below FULL and asserts the IOC is refused.
- The executor test fixture's comment claimed that tests about the running-nautilus input override the `_nautilus_verified` fixture at the end of the file; no such test exists.
- `test_the_prompt_is_written_to_the_terminal_and_not_to_this_process_s_stdout` passes under `pytest -s` even if the prompt went to stdout, because the child's fd 1 is then the pty slave.

## Resolution

Every item was decided by the owner on 2026-09-05, per item, in an attended session; commits are cited by subject (branch `fix/t0165-t0167-asserted-in-prose`).

- `_enter` as the only writer of the `resting` phase: **recorded drop** — the behavioural test `test_a_resting_orders_placement_time_belongs_to_the_order_and_to_no_other_phase` pins what matters; a structural pin on the write site is not worth a test.
- The time-box IOC fallback refused by the gate: **test** — `test(engine): the fallback IOC is refused when the kill file lands during the time-box cancel`, `tests/test_engine_executor.py::test_a_kill_file_landing_during_the_time_box_cancel_refuses_the_fallback_ioc`; proven by mutation — KILLED when `_submit`'s level check is disabled.
- A test for the running-nautilus gate input: **recorded drop** — the false fixture comment is gone (T0164), and `tests/test_engine_execgate.py` covers the verified-record check.
- The `-s` blind spot: **test** — `test(engine): the prompt-to-terminal test holds under pytest -s`; fd 1 is pointed at `/dev/null` in the forked child. Proven by mutation under `-s` with the prompt written to stdout: this test KILLED, the base test SURVIVED.

## Suggested next steps

_(none remain — see Resolution)_
