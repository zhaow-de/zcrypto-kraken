---
status: partial
ripe_when: EITHER a native abort (exit 134 / SIGABRT, or any signal death) appears in a CI or local pytest run again — observable rather than fatal thanks to `tests/test_engine_node.py`'s child-process fence, but note this clause can only catch an abort during **build**, since the fenced child never disposes (see `## Done so far`) — OR `nautilus_trader` is bumped past 1.231.0 (the highest version probed; the repo still pins 1.230.0), at which point re-run the dispose probe. Both are checkable without new instrumentation: the first from any run's exit code, the second from `uv.lock`.
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
- **The live engine takes the racing branch on every shutdown — the "never-run" framing in this topic's title is a red herring, corrected 2026-08-09.** `dispose()` branches on the loop's *state at dispose time*, never on whether the node was run: `if not loop.is_closed(): if loop.is_running(): loop.stop() else: loop.close()`. `zcrypto engine run` is a **synchronous** Typer command, so no loop is running when it calls `node.run()`; `run()` therefore takes `run_until_complete(self.run_async())`, which returns with the loop **not running and not closed** (measured), and nothing in `kernel.dispose()` closes it — so the `finally: node.dispose()` reaches `loop.close()`, the same branch that aborted CI. What remains genuinely unmeasured is whether the Rust threads are still unwinding at that moment on a *run* node, which is what decides whether the race actually fires there rather than merely being reachable.
- **The correlation is unexplained and that is the uncomfortable part.** The test landed 2026-07-10 and survived **27 clean CI runs**. It then aborted **3 of 4 runs** once spec `00078`'s branch existed — yet running that branch's new archive tests *immediately before* `test_engine_node` in CI **passed** (63 passed). So it is not a two-file interaction; it needs the whole suite's accumulated process state, and that was not narrowed further.

## Findings so far

- Ruled out as causes, each by measurement rather than argument: core count (pinned to 4, passed), file-descriptor cap (1024, passed), process memory (full-suite peak **0.88 GiB** against a 16 GB runner), dependency drift (the branch touched no `pyproject.toml`/`uv.lock`), and local fragility (**40 stress runs** of the file at 4 cores under coverage, zero aborts).
- **Never reproduced locally**, under any configuration tried — including the CI command verbatim. Every conclusion about the abort therefore rests on CI observation plus the `/proc/self/task` measurement of the teardown itself.
- A diagnostic PR's four probes each passed in isolation (the suspect file alone, the same without coverage, the branch's new tests then the suspect file); only the full suite reproduced it.
- **A process lesson worth more than the bug**: that diagnostic used `continue-on-error: true` on every probe so one run would yield the whole matrix — which makes GitHub report each step's conclusion as **success regardless of exit code**. The matrix read all-green while a probe had in fact failed. Read the logs, never the step conclusions.

## Done so far

- **Probed against 1.231.0 on 2026-08-09: clean, and the clean result does not clear the topic.** The repo still pins **1.230.0** — the probe ran on PR #270's unmerged branch, and that bump is itself blocked by a separate gate (`tests/test_nautilus_adapter.py`'s version pin, which `docs/research/14.phase6-adapter-verification.md` binds to an attended re-run of the order-semantics probes). A probe built the node with the Kraken exec client — construction copied verbatim from the fence's `_BUILD_PROBE`, same imports, same `EngineConfig`, same credential-stripped child environment — then disposed it without ever running it, 3 disposes per child across 8 child processes. 24/24 disposed, zero signal deaths. The per-child `disposed 3/3` counts confirm the probe reached `dispose()` rather than passing vacuously.
- **That probe is a one-sided instrument, and it was MEASURED to be one rather than argued.** Run against **1.230.0** — the version where the defect is known present, having aborted CI 3 of 4 runs — the same probe returns **18/18 clean** (6 children x 3 disposes). An instrument that cannot detect a defect known to be there cannot certify its absence anywhere else, so the clean 1.231.0 result carries no evidence that the bump fixed anything. Only a *dirty* run is decisive, by showing a version made the race locally reachable. Record future runs as "version probed, probe clean", never as "the race is fixed".
- **The fence traded observability for survivability, which narrows the first trigger clause.** The fenced child ends in `os._exit(0)` and never calls `dispose()`, so CI — the only environment that ever reproduced the abort, 3 of 4 runs — no longer exercises the racing path at all. Nothing in the routine suite can now surface a *dispose*-race recurrence; the first `ripe_when` clause fires only for an abort during **build**. Clearing this race would take a deliberate dispose probe run in CI, which is new work, not a by-product of any bump.
- **The production-safety argument this topic rested on is FALSE, and finding that out is the most important result here.** The cheap grep (2026-08-09) found exactly one production `dispose()` site — `cli/engine/command.py`, in `try: node.run() / finally: … node.dispose()`. The grep counts *sites*; it says nothing about which branch a site takes, and reading it as "a run node takes `loop.stop()`" was the error. Tracing the branch instead of assuming it shows the live engine reaches `loop.close()` (see `## Why this matters`). So the risk is **reachable in production**, not confined to a test fixture — which is why the option of closing this topic on the unreachability argument has been struck.

## Suggested next steps

- *(autonomous)* **When the trigger fires, capture what the fence now preserves.** The child's stdout/stderr and exit signal are attached to the failing assertion, so the next occurrence yields the signal number and any Rust output the bare abort destroyed — the evidence this investigation never had.
- *(autonomous)* **Re-run `infra/scripts/nautilus-dispose-probe.py` on each `nautilus_trader` bump.** Standing, not one-off: it re-arms every bump. Record the version tested either way, and read a clean result strictly as "probe clean", never as grounds to reconsider the fence — per `## Done so far`, the probe can escalate but cannot clear.
- *(autonomous, host-touching — runs in the main loop)* **Read the engine container's recorded exit codes for a shutdown abort.** The live engine has restarted many times across converges, and each shutdown ran the `loop.close()` path, so history is evidence: on `zcrypto`, read `docker inspect --format '{{.State.ExitCode}}' zcrypto-engine` plus `{{.RestartCount}}`, and scan the engine's shutdown log lines for `Closing event loop` followed by an abort. Scope the inspect to those fields — never the whole object (CLAUDE.md `## Secrets`). A 134 anywhere in that history turns this from reachable-in-theory into observed-in-production.
- *(decision)* **Whether to buy back the observability the fence removed.** The routine suite can no longer surface this race at all, so the options are: run a dispose probe as a real CI job (recovers the only environment that ever reproduced it, at the cost of a job that may abort by design and needs its own containment), or leave it dark and accept that the topic can only ever be closed by argument. Closing it on "unreachable from production" is **no longer available** — that argument was measured false. Priority now depends on the exit-code sweep above: a clean history keeps this routine, a 134 makes it urgent.
- *(decision, only if it recurs past the fence)* Whether to report upstream. The reproducer would be small — build with an exec client, never run, dispose — but it has never reproduced outside CI, and an unreproducible report is not worth filing.
