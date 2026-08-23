---
status: partial
ripe_when: the `nautilus-trader` pin in `pyproject.toml` moves off `1.230.0` — checkable from `pyproject.toml`/`uv.lock` alone. On a bump, run `infra/scripts/nautilus-logger-guard-probe.py` and record the version probed either way. (The old trigger — "an abort appears in a pytest run", plus a re-run of the dispose probe — is retired: the dispose probe was measured blind on every version, and a recurrence is no longer the only way to learn anything, since the defect now reproduces in six lines on demand.)
---

# nautilus's Rust logger double-init aborts the process

## Context — what

`tests/test_engine_node.py` killed the **entire** pytest process in CI with **exit 134 (SIGABRT)** — 27 tests passing, then a hard abort on the 28th, `test_build_shadow_node_with_exec_client_when_enabled`. No traceback and no panic text.

The mechanism is the Rust logger, and it is measured rather than inferred. `NautilusKernel.__init__` calls `init_logging()` only `if not is_logging_initialized()`, and holds the returned `LogGuard`. On **1.230.0**, dropping that guard resets `is_logging_initialized()` to `False` while the Rust `log` crate's global logger stays set — so the *next* kernel calls `init_logging()` again, and the Rust side panics at `crates/common/src/ffi/logging.rs:198` (`Failed to initialize logging: attempted to set a logger after the logging system was already initialized`) and aborts the process.

Six lines reproduce the whole thing — no `TradingNode`, no event loop, no `dispose()`, no exec client:

```python
g = init_logging()
print(is_logging_initialized())   # True
del g; gc.collect()
print(is_logging_initialized())   # 1.230.0 -> False   1.231.0 -> True
init_logging()                    # 1.230.0 -> SIGABRT  1.231.0 -> RuntimeError
```

Measured 2026-08-23: **1.230.0** → `True / False / panicked at crates/common/src/ffi/logging.rs:198`, exit 134. **1.231.0** → `True / True / RuntimeError: Logging subsystem already initialized`, exit 1.

Three consequences follow, each of which contradicts what this topic used to say:

- **The abort site is `TradingNode.__init__`, not `dispose()`.** The process dies building the *next* node, not tearing down the previous one.
- **`dispose()` is the enabler, not the site — and only under a stdlib event loop.** `loop.close()` removes the signal handlers `NautilusKernel._setup_loop` registered, and those were the last reference keeping the kernel — and with it the `LogGuard` — alive. Measured on the real node: stdlib loop → `is_logging_initialized()` `False` after dispose, second `build_shadow_node()` aborts (exit 134); uvloop → guard alive, second node builds, exit 0.
- **The exec client was a coincidence of test ordering**, not part of the mechanism. `exec_enabled=False` aborts identically; the failing test was simply the one that happened to run after enough of the suite had accumulated a droppable guard. GC timing is also what explains the old, unexplained "needs the whole suite's accumulated process state" correlation: the guard drops when the previous kernel is collected, which depends on what else the process was holding.

**Production is structurally unreachable, and that is a measured claim rather than an argument.** `cli/engine/command.py` builds exactly **one** node per process, so it never reaches a second `init_logging()` at all. Independently, `nautilus_trader/system/kernel.py` sets the uvloop policy whenever `"pytest" not in sys.modules` — i.e. always outside the test suite — and under uvloop's `close()` the guard measurably does not drop, so even a hypothetical second build would survive. The trap needs a multi-node, stdlib-loop process: pytest, and only pytest.

## Why this matters

- **A month of investigation had no evidence, and the reason was mechanical.** `NautilusKernel._setup_loop` registers an asyncio signal handler for **SIGABRT** (`loop.add_signal_handler`), which installs CPython's own no-op C handler over faulthandler's. Verified by A/B on one interpreter: a full faulthandler dump plus C stack becomes **zero bytes of output** at the same exit 134, purely because a node was built first. Every earlier inference drawn from the missing traceback — "the abort comes off a non-Python thread" among them — was reading a silenced handler, not a signal about which thread panicked.
- **The live engine was equally blind.** The repo carried *zero* `faulthandler` references, so a native abort in `zcrypto engine run` would have produced exit 134 and nothing else. That is now fixed (see `## Done so far`), which is the one production-facing change this topic produced.
- **The containment was right for the wrong reason, and stays.** Spec `00078` fenced both node-build tests into a child interpreter that exits without disposing. One `TradingNode` per process is what upstream prescribes anyway, so the fence is correct on its own terms; only its stated reasoning was wrong.

## Findings so far

- **The dispose probe was blind on every version, which is why its results never made sense.** `infra/scripts/nautilus-dispose-probe.py` spawned pytest-free children; nautilus therefore selected uvloop in each of them, and under uvloop the guard cannot drop. Its 18/18-clean on 1.230.0 — the version whose defect is known present — is explained rather than mysterious, and so is its 24/24-clean on 1.231.0. Its docstring claimed it "exercises the shape of the production shutdown": true of production, false of the CI failure it was pointed at.
- **The engine container's exit-code history is INCONCLUSIVE, not clean.** Checked 2026-08-23 on `zcrypto`: no `134` was found, but the check could not deliver a verdict — the current container had never shut down, dockerd logs no die events in a filterable form, and the windows around known restarts showed only the *new* container starting. Read it as "no evidence either way", never as production having been exonerated by history. The unreachability above does not rest on it.
- **1.231.0 is not simply "fixed".** It keeps the guard alive after the drop (`is_logging_initialized()` stays `True`) and converts the second `init_logging()` from an abort into a catchable `RuntimeError` — better, but still not two loggers. It also introduces new TLS-destructor machinery in this same failure class, so the attended order-semantics re-run that gates the bump is doing real work rather than ceremony.
- **Ruled out earlier, each by measurement**: core count (pinned to 4), file-descriptor cap (1024), process memory (full-suite peak 0.88 GiB against a 16 GB runner), dependency drift, and local fragility (40 stress runs of the file under coverage). All correct findings; none of them was the cause, because the cause was upstream state, not resources.
- **A process lesson worth more than the bug**: the 2026-08 diagnostic PR used `continue-on-error: true` on every probe so one run would yield the whole matrix — which makes GitHub report each step's conclusion as **success regardless of exit code**. The matrix read all-green while a probe had in fact failed. Read the logs, never the step conclusions.

## Done so far

- **The engine now re-arms faulthandler immediately after `build_shadow_node`** (`cli/engine/command.py`, commit `bf0682d9`), so the next native abort in production arrives with a stack instead of a bare exit 134. `disable()` before `enable()` is load-bearing — `faulthandler.enable()` returns early when faulthandler already considers itself enabled, and on its own cannot reinstall the handler asyncio replaced. Five child-process arms in `tests/test_engine_node.py` pin the behaviour (armed-and-unclobbered dumps; armed-then-built is silent; `enable()`-only is silent; the production shape is silent without the re-arm and dumps with it), and `tests/test_engine_command.py` pins the call site and its order against the real `engine run`. Asserting on `signal.getsignal(SIGABRT)` would have proved nothing — it reads identical on both sides, because faulthandler installs below CPython's cache.
- **The dispose probe is retired and replaced by `infra/scripts/nautilus-logger-guard-probe.py`.** The new instrument is two-sided, which the old one never was: arm 1 is the bare reproducer (no node, no loop, no dispose), so a clean result there really is evidence the upstream defect is gone; arm 2 is the pytest arrangement (two nodes, one process, stdlib loop); arm 3 is the production arrangement (uvloop). On 1.230.0 it reports DIRTY / DIRTY / clean, which is the correct reading of this version.
- **The fence's comment in `tests/test_engine_node.py` is rewritten to the measured mechanism.** The fence itself is unchanged: one node per process is the right posture regardless of which upstream version is pinned.
- **Nothing is filed upstream — decided, not deferred.** v1 is EOL with security backports only, and `system/kernel.py` does not exist on v2 (develop/master/nightly), so the bug template's "still reproduces on 2.0.0rcN" checkbox is untickable as a matter of fact. Their `AI_POLICY.md` forbids an agent filing. No issue, no PR.
- **No teardown "fix" was adopted, and none should be.** `asyncio.run`, deleting `loop.close()`, closing the loop first, dropping the `LogGuard` before dispose, `UV_USE_IO_URING=0` — every one of these targets the falsified mechanism, and the guard-drop variant additionally blocks on a `logger_drop` join that holds the GIL with no timeout.
- **The old "reachable in production" conclusion (2026-08-09) is superseded.** It was derived correctly from a wrong mechanism: `dispose()` does reach `loop.close()` on every engine shutdown, but that branch is harmless on its own — it only matters if a *second* node is built afterwards in the same process, which the engine never does.

## Suggested next steps

- *(autonomous)* **Run `infra/scripts/nautilus-logger-guard-probe.py` on each `nautilus_trader` bump, and record the version probed either way.** Standing, not one-off: it re-arms at every bump. Unlike its predecessor this probe can exonerate — arm 1 reporting `second-init CLEAN` means the upstream defect is gone and the one-node-per-process fence can be reconsidered; arm 3 turning DIRTY means the trap has reached the production arrangement and the bump must not merge. The 1.230.0 → 1.231.0 bump held in PR #270 is the next occasion, behind that PR's own attended order-semantics gate.
