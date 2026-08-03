---
status: open
ripe_when: EITHER a native abort (exit 134 / SIGABRT, or any signal death) appears in a CI or local pytest run again — now observable rather than fatal, because `tests/test_engine_node.py`'s child-process fence turns it into a normal red test with the child's output attached — OR `nautilus_trader` is bumped past 1.230.0, at which point re-test whether `dispose()` on a never-run node still races. Both are checkable without new instrumentation: the first from any run's exit code, the second from `uv.lock`.
---

# `TradingNode.dispose()` aborts the process on a node that was built but never run

## Context — what

`tests/test_engine_node.py` killed the **entire** pytest process in CI with **exit 134 (SIGABRT)** — 27 tests passing, then a hard abort on the 28th, `test_build_shadow_node_with_exec_client_when_enabled`. No traceback and no panic text: pytest enables `faulthandler` by default, so silence means the abort came off a **non-Python thread**, i.e. nautilus's Rust core.

The mechanism was measured, not inferred. `TradingNode.dispose()` (nautilus 1.230.0) ends with:

```python
self.kernel.dispose()
if self.kernel.executor:
    self.kernel.executor.shutdown(wait=True, cancel_futures=True)
loop = self.kernel.loop
if not loop.is_closed():
    if loop.is_running(): ... loop.stop()
    else:                 loop.close()      # <-- a node that was never run takes this branch
```

Reading `/proc/self/task` around a real build shows a `logging` thread **and** an `iou-sqp-<pid>` io_uring poller still alive when `dispose()` returns with `loop.is_closed()` already `True`; the poller lingers ~0.5 s beyond that. **The race window is inside `dispose()`, between `kernel.dispose()` and `loop.close()`** — which is why the two obvious mitigations cannot work: draining before the call never reaches that window, and settling after it is already too late.

The only structural difference from the sibling test that disposes cleanly is that this one registers `KrakenLiveExecClientFactory`, so `node.build()` constructs the Rust-backed HTTP/WS machinery that teardown then has to unwind.

## Why this matters

- **It is contained, not fixed.** Spec `00078` fenced both node-build tests into a child interpreter that writes its facts to JSON and exits **without disposing**. Containment is proven by construction: `os.abort()`, `ctypes.string_at(0)` (SIGSEGV) and `SIGKILL` in the child each yield `2 failed, 26 passed, pytest exit 1` — never 134. A hung child is bounded by `timeout=120` (measured 120.6 s, no orphan), so CI cannot stall either. The underlying nautilus race is untouched.
- **It cannot bite production today, and the reason is worth keeping**: the live engine *runs* its node, so teardown takes the `loop.stop()` branch, never `loop.close()`. Only the never-run build path reaches the racing branch. That guarantee disappears the moment anything disposes a node it did not run.
- **The correlation is unexplained and that is the uncomfortable part.** The test landed 2026-07-10 and survived **27 clean CI runs**. It then aborted **3 of 4 runs** once spec `00078`'s branch existed — yet running that branch's new archive tests *immediately before* `test_engine_node` in CI **passed** (63 passed). So it is not a two-file interaction; it needs the whole suite's accumulated process state, and that was not narrowed further.

## Findings so far

- Ruled out as causes, each by measurement rather than argument: core count (pinned to 4, passed), file-descriptor cap (1024, passed), process memory (full-suite peak **0.88 GiB** against a 16 GB runner), dependency drift (the branch touched no `pyproject.toml`/`uv.lock`), and local fragility (**40 stress runs** of the file at 4 cores under coverage, zero aborts).
- **Never reproduced locally**, under any configuration tried — including the CI command verbatim. Every conclusion about the abort therefore rests on CI observation plus the `/proc/self/task` measurement of the teardown itself.
- A diagnostic PR's four probes each passed in isolation (the suspect file alone, the same without coverage, the branch's new tests then the suspect file); only the full suite reproduced it.
- **A process lesson worth more than the bug**: that diagnostic used `continue-on-error: true` on every probe so one run would yield the whole matrix — which makes GitHub report each step's conclusion as **success regardless of exit code**. The matrix read all-green while a probe had in fact failed. Read the logs, never the step conclusions.

## Suggested next steps

- *(autonomous)* **When the trigger fires, capture what the fence now preserves.** The child's stdout/stderr and exit signal are attached to the failing assertion, so the next occurrence yields the signal number and any Rust output the bare abort destroyed — the evidence this investigation never had.
- *(autonomous)* **Re-test on the next `nautilus_trader` bump.** Build a node with the Kraken exec client, never run it, dispose it in-process in a loop, and watch for a non-zero exit. If it survives, the fence can be reconsidered; record the version tested either way.
- *(autonomous, cheap)* **Check whether anything else disposes a never-run node.** `grep` for `dispose()` across `cli/` and `tests/`; any other site inherits the same race and the same containment need. Today the fenced tests are believed to be the only ones — confirm rather than assume.
- *(decision, only if it recurs past the fence)* Whether to report upstream. The reproducer would be small — build with an exec client, never run, dispose — but it has never reproduced outside CI, and an unreproducible report is not worth filing.
