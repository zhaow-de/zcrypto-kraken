---
status: resolved
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
- **`dispose()` is the enabler, not the site — and only under a stdlib event loop.** `loop.close()` removes the signal handlers `NautilusKernel._setup_loop` registered, and those were the last reference keeping the kernel — and with it the `LogGuard` — alive. Measured on the real node at 1.230.0: stdlib loop → `is_logging_initialized()` `False` after dispose, second `build_shadow_node()` aborts (exit 134); uvloop → guard alive, second node builds, exit 0.
- **The exec client was a coincidence of test ordering**, not part of the mechanism. `exec_enabled=False` aborts identically; the failing test was simply the one that happened to run after enough of the suite had accumulated a droppable guard. GC timing is also what explains the old, unexplained "needs the whole suite's accumulated process state" correlation: the guard drops when the previous kernel is collected, which depends on what else the process was holding.

**Production was structurally unreachable even on 1.230.0, and that is a measured claim rather than an argument.** `cli/engine/command.py` builds exactly **one** node per process, so it never reached a second `init_logging()` at all. Independently, `nautilus_trader/system/kernel.py` sets the uvloop policy whenever `"pytest" not in sys.modules` — i.e. always outside the test suite — and under uvloop's `close()` the guard measurably does not drop. The trap needed a multi-node, stdlib-loop process: pytest, and only pytest.

## Why this matters

- **A month of investigation had no evidence, and the reason was mechanical.** `NautilusKernel._setup_loop` registers an asyncio signal handler for **SIGABRT** (`loop.add_signal_handler`), which installs CPython's own no-op C handler over faulthandler's. Verified by A/B on one interpreter: a full faulthandler dump — Python frames plus a symbolised C stack — becomes **zero bytes of output** at the same exit 134, purely because a node was built first. Every earlier inference drawn from the missing traceback — "the abort comes off a non-Python thread" among them — was reading a silenced handler, not a signal about which thread panicked.
- **The live engine was equally blind.** The repo carried *zero* `faulthandler` references, so a native abort in `zcrypto engine run` would have produced exit 134 and nothing else. That is fixed (see `## Done so far`), and it is the one production-facing change this topic produced. It still matters on 1.231.0: the SIGABRT clobber is a property of nautilus's signal handling, not of the logger fault, and it is unchanged.
- **The containment was right for the wrong reason, and stays.** Spec `00078` fenced both node-build tests into a child interpreter that exits without disposing. One `TradingNode` per process is what upstream prescribes anyway, so the fence is correct on its own terms; only its stated reasoning was wrong.

## Findings so far

- **The dispose probe was blind on every version, which is why its results never made sense.** `infra/scripts/nautilus-dispose-probe.py` spawned pytest-free children; nautilus therefore selected uvloop in each of them, and under uvloop the guard cannot drop. Its 18/18-clean on 1.230.0 — the version whose defect is known present — is explained rather than mysterious, and so is its 24/24-clean on 1.231.0. Its docstring claimed it "exercises the shape of the production shutdown": true of production, false of the CI failure it was pointed at.
- **The engine container's exit-code history is INCONCLUSIVE, not clean.** Checked 2026-08-23 on `zcrypto`: no `134` was found, but the check could not deliver a verdict — the current container had never shut down, dockerd logs no die events in a filterable form, and the windows around known restarts showed only the *new* container starting. Read it as "no evidence either way", never as production having been exonerated by history. The unreachability result above does not rest on it.
- **Ruled out earlier, each by measurement**: core count (pinned to 4), file-descriptor cap (1024), process memory (full-suite peak 0.88 GiB against a 16 GB runner), dependency drift, and local fragility (40 stress runs of the file under coverage). All correct findings; none of them was the cause, because the cause was upstream state, not resources.
- **A process lesson worth more than the bug**: the 2026-08 diagnostic PR used `continue-on-error: true` on every probe so one run would yield the whole matrix — which makes GitHub report each step's conclusion as **success regardless of exit code**. The matrix read all-green while a probe had in fact failed. Read the logs, never the step conclusions.

## Done so far

- **The abort is fixed upstream, and the repo now pins the version that fixes it.** `nautilus-trader` moved `1.230.0` → **`1.231.0`** here (`pyproject.toml` + `uv.lock` via uv). Measured with `infra/scripts/nautilus-logger-guard-probe.py` on 1.231.0: **all three arms clean** — the bare reproducer raises `RuntimeError: Logging subsystem already initialized` instead of panicking, and two nodes now coexist in one process under a stdlib loop *and* under uvloop. Full suite on the new version: **3792 passed, 21 skipped**, the same count as on 1.230.0.
- **A second `init_logging()` is still REFUSED, just no longer fatal.** That distinction is load-bearing and the probe's verdict now states it explicitly: the version fixes the *abort*, not the *restriction*. It is not licence to build two nodes in one process.
- **The fence stays, as posture rather than necessity.** With the abort gone it is no longer load-bearing for survival, but one `TradingNode` per process is what upstream prescribes, so the child-interpreter fence in `tests/test_engine_node.py` is kept and its comment rewritten to the measured mechanism.
- **The engine re-arms faulthandler immediately after `build_shadow_node`** (`cli/engine/command.py`, commit `bf0682d9`), so a native abort in production arrives with a stack instead of a bare exit 134. `disable()` before `enable()` is load-bearing — `faulthandler.enable()` returns early when faulthandler already considers itself enabled. It passes `file=2` rather than taking the default `sys.stderr`: the default form *raises* when `sys.stderr` has no `fileno()`, and since `disable()` has already run by then the engine would start with faulthandler switched **off** — strictly worse than never re-arming. Measured both ways. Asserting on `signal.getsignal(SIGABRT)` would have proved nothing — it reads identical on both sides, because faulthandler installs below CPython's cache.
- **The dispose probe is retired and replaced by `infra/scripts/nautilus-logger-guard-probe.py`.** The new instrument is two-sided, which the old one never was: arm 1 is the bare reproducer (no node, no loop, no dispose), so a clean result there really is evidence the upstream defect is gone; arm 2 is the pytest arrangement; arm 3 is the production arrangement. On 1.230.0 it reports DIRTY / DIRTY / clean; on 1.231.0, clean / clean / clean.
- **Nothing is filed upstream — decided, not deferred.** v1 is EOL with security backports only, and `system/kernel.py` does not exist on v2 (develop/master/nightly), so the bug template's "still reproduces on 2.0.0rcN" checkbox is untickable as a matter of fact. Their `AI_POLICY.md` forbids an agent filing. No issue, no PR.
- **No teardown "fix" was adopted, and none should be.** `asyncio.run`, deleting `loop.close()`, closing the loop first, dropping the `LogGuard` before dispose, `UV_USE_IO_URING=0` — every one of these targets the falsified mechanism, and the guard-drop variant additionally blocks on a `logger_drop` join that holds the GIL with no timeout.
- **The old "reachable in production" conclusion (2026-08-09) is superseded.** It was derived correctly from a wrong mechanism: `dispose()` does reach `loop.close()` on every engine shutdown, but that branch is inert on its own — it only mattered if a *second* node were built afterwards in the same process, which the engine never does.

## Resolution

Resolved on all counts: the mechanism was found and the old account falsified by measurement, the abort is fixed in the version the repo now pins, production was never reachable, the blind instrument is replaced by a two-sided one, the fence and its reasoning are corrected, and the engine can now read a native abort instead of dying mute. Upstream reporting was decided against with the reason recorded.

Two obligations left this topic rather than lapsing with it, and neither is this topic's:

- **The attended ~€0.20 order-semantics re-run on 1.231.0 has NOT happened.** It is a precondition of **arming**, not of merging, and it is enforced on the operating surface: the pre-probe checklist in `infra/runbooks/engine.md` refuses arming unless the engine's running nautilus version has its own verification doc. It is also carried as a go-live sub-item in [[T0085]]. 1.231.0 introduces new TLS-destructor machinery (upstream #4496/#4516) in the same failure class as the logger fault, so that re-run is real verification work rather than ceremony.
- **Running the logger-guard probe on each future bump** is a standing routine whose durable home is the committed script's own docstring, plus [[T0085]]'s bump checklist — not a deferral parked in prose.
