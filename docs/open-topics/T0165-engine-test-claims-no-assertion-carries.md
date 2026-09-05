---
status: open
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

## Suggested next steps

- Beside `test_a_resting_orders_placement_time_belongs_to_the_order_and_to_no_other_phase`: an AST walk over `cli/engine/executor.py` asserting `phase = "resting"` is assigned at exactly one site and that `placed_at` is set in the same body.
- In the ladder section of `tests/test_engine_executor.py`: touch the kill file after the time-box cancel goes out, answer the cancel, assert the IOC is refused by the gate.
- At the end of `tests/test_engine_executor.py` (or in `tests/test_engine_execgate.py`): a test that lets `execgate._installed_nautilus_version` run unstubbed and asserts the gate's verdict names the running-nautilus input.
- In `tests/test_engine_flatten.py`, in the forked child: `os.dup2` of `/dev/null` onto fd 1 before `read_confirm`, as it already does for fd 0, so only a write through `/dev/tty` reaches the drained master and the `b"TYPE-THE-WORD?"` assertion holds under `-s` too.
