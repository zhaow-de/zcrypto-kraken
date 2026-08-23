"""Probe whether nautilus's Rust logger still aborts the process on a second `init_logging()`.

Run this on every `nautilus_trader` bump (T0115's standing next step), before deciding anything
about the one-node-per-process fence in `tests/test_engine_node.py`:

    uv run python infra/scripts/nautilus-logger-guard-probe.py

THE MECHANISM. `NautilusKernel.__init__` calls `init_logging()` only `if not
is_logging_initialized()`, and keeps the returned `LogGuard`. When that guard is dropped, 1.230.0
resets `is_logging_initialized()` to False while the Rust `log` crate's global logger stays set --
so the NEXT kernel calls `init_logging()` again and the Rust side panics (`Failed to initialize
logging: attempted to set a logger after the logging system was already initialized`,
crates/common/src/ffi/logging.rs) and SIGABRTs the whole process. The abort therefore lands in
`TradingNode.__init__`, not in `dispose()`.

`dispose()` is only the ENABLER, and only under a stdlib event loop: `loop.close()` removes the
signal handlers registered by `NautilusKernel._setup_loop`, which were the last reference keeping
the kernel -- and with it the guard -- alive. Under uvloop the guard measurably does not drop.

WHY THIS REPLACED THE DISPOSE PROBE. Its predecessor spawned pytest-free children and looped
`dispose()`; nautilus selects uvloop whenever `"pytest" not in sys.modules` (`system/kernel.py`), so
every one of those children ran the arrangement in which the guard cannot drop. It was blind on
EVERY version -- which is why it returned 18/18 clean on 1.230.0, the version whose defect is known
present. This probe is two-sided: arm 1 is a bare reproducer with no node, no loop and no dispose
at all, so a clean result here really is evidence the upstream defect is gone.

READING THE RESULT.
  * `guard-drop`  -- DIRTY means the defect is present (1.230.0's shape: the second init aborts).
    `second-init RAISES` means upstream turned it into a catchable `RuntimeError` (1.231.0's
    shape): no longer fatal, still no second logger. `second-init CLEAN` means a second
    `init_logging()` now succeeds -- the fence's premise is gone and the fence can be reconsidered.
  * `stdlib-node` -- the pytest-shaped arrangement (two nodes, one process, stdlib loop). DIRTY
    here is what killed CI, and is the fence's whole reason to exist.
  * `uvloop-node` -- the production-shaped arrangement. `zcrypto engine run` builds exactly one node
    per process, so it never even reaches a second build; this arm proves the weaker claim that a
    second build would survive anyway. DIRTY here would mean production is genuinely at risk.

Record the version probed either way.
"""

import os
import subprocess
import sys

# Arm 1: the whole defect, with no TradingNode, no event loop, no dispose() and no exec client.
_GUARD_DROP = """
import gc
import nautilus_trader
from nautilus_trader.common.component import init_logging, is_logging_initialized

print("probe: version", nautilus_trader.__version__, flush=True)
guard = init_logging()
print("probe: initialized-after-first-init", is_logging_initialized(), flush=True)
del guard
gc.collect()
print("probe: initialized-after-guard-drop", is_logging_initialized(), flush=True)
try:
    init_logging()
except Exception as exc:
    print("probe: second-init RAISES", type(exc).__name__, exc, flush=True)
else:
    print("probe: second-init CLEAN", flush=True)
"""

# Arm 2/3: the same question asked through the real node, under each event-loop implementation.
# `exec_enabled=False` deliberately: the exec client was a coincidence of the original CI ordering,
# never part of the mechanism, and leaving it out keeps the arm fast and keyless.
_TWO_NODES = """
import asyncio, gc, sys, tempfile
from pathlib import Path

from cli.config import EngineConfig
from cli.engine import build_shadow_node
from nautilus_trader.common.component import is_logging_initialized

if sys.argv[1] == "uvloop":
    import uvloop

    loop = uvloop.new_event_loop()
else:
    loop = asyncio.SelectorEventLoop()
asyncio.set_event_loop(loop)
print("probe: loop", type(loop).__module__ + "." + type(loop).__name__, flush=True)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    node = build_shadow_node(EngineConfig(store_dir=root / "s1", journal_dir=root / "j1"))
    node.dispose()
    del node
    gc.collect()
    print("probe: initialized-after-dispose", is_logging_initialized(), flush=True)
    # The abort, when it comes, lands HERE -- inside the second node's kernel construction.
    build_shadow_node(EngineConfig(store_dir=root / "s2", journal_dir=root / "j2"))
    print("probe: second-node BUILT", flush=True)
"""


def _run(code: str, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, timeout=300, env=env)


def _report(name: str, result: subprocess.CompletedProcess) -> str:
    """Classify one arm. A signal death is DIRTY; anything else non-zero is NO VERDICT, never a
    finding -- an import error from the very bump under test must not be reported as the defect."""
    # Only the probe's own lines: nautilus prints a multi-screen banner to stdout on every build.
    for line in result.stdout.splitlines():
        if line.startswith("probe: "):
            print(f"    {line.removeprefix('probe: ')}")
    if result.returncode < 0 or result.returncode >= 128:
        print(f"    stderr: {' | '.join((result.stderr or '').strip().splitlines()[-4:])}")
        print(f"  {name}: DIRTY — signal death (code={result.returncode})")
        return "dirty"
    if result.returncode != 0:
        print(f"    stderr: {' | '.join((result.stderr or '').strip().splitlines()[-6:])}")
        print(f"  {name}: NO VERDICT — exited {result.returncode} without a signal; nothing was tested")
        return "no-verdict"
    print(f"  {name}: clean")
    return "clean"


def main() -> int:
    print("arm 1 — guard-drop (no node, no loop, no dispose):")
    guard = _run(_GUARD_DROP)
    guard_verdict = _report("guard-drop", guard)

    print("\narm 2 — stdlib-node (two nodes in one process, stdlib loop — the pytest arrangement):")
    stdlib_verdict = _report("stdlib-node", _run(_TWO_NODES, "stdlib"))

    print("\narm 3 — uvloop-node (two nodes in one process, uvloop — the production arrangement):")
    uvloop_verdict = _report("uvloop-node", _run(_TWO_NODES, "uvloop"))

    print()
    if "no-verdict" in (guard_verdict, stdlib_verdict, uvloop_verdict):
        print("VERDICT: NO VERDICT — an arm failed without a signal. Read its stderr and fix the probe or")
        print("         the environment before concluding anything about this version.")
        return 1
    if uvloop_verdict == "dirty":
        print("VERDICT: DIRTY IN PRODUCTION SHAPE — the guard now drops under uvloop too. This is no longer")
        print("         a test-only trap; escalate before merging the bump.")
        return 1
    if "second-init CLEAN" in guard.stdout and stdlib_verdict == "clean":
        print("VERDICT: FIXED UPSTREAM — a second init_logging() succeeds and two nodes coexist in one")
        print("         process. The one-node-per-process fence can be reconsidered on this version.")
        return 0
    print("VERDICT: the trap is still present upstream (see arm 1) and still confined to the multi-node,")
    print("         stdlib-loop arrangement. Keep the fence. Record the version probed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
