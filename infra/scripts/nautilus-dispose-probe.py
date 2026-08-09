"""Probe whether `TradingNode.dispose()` still races when it closes the event loop.

Run this on every `nautilus_trader` bump (T0115's standing next step), before deciding anything
about the child-process fence in `tests/test_engine_node.py`:

    uv run python infra/scripts/nautilus-dispose-probe.py [children] [disposes_per_child]

The committed suite cannot answer this question. Its node-build probe ends in `os._exit(0)`,
deliberately skipping `dispose()`, so a green suite is silent about the race by construction.

ONE-SIDED INSTRUMENT — read the verdict accordingly. The race never reproduced locally on 1.230.0,
including the CI command verbatim; only CI ever reproduced it, 3 of 4 runs. So a clean run here is
the expected outcome whether or not the bump fixed anything, and CANNOT clear the topic. A dirty
run is decisive in the other direction: it means the new version made the race locally reachable.
Record a clean result as "version tested, probe clean", never as "the race is fixed".

The node construction is copied from `tests/test_engine_node.py`'s `_BUILD_PROBE` so the build path
is identical -- same import sites, same `EngineConfig`, same credential-stripped child environment
-- with `os._exit(0)` replaced by the dispose loop that the fence exists to avoid. Each child runs
several disposes; children are separate processes so a native abort is observable as a signal exit
rather than killing this runner.

The node here is never run, but that is convenience, not the mechanism: `dispose()` picks its branch
from the loop's STATE, so `zcrypto engine run` -- a synchronous command whose `run_until_complete`
returns with the loop open and idle -- reaches the same `loop.close()` on every shutdown.
"""

import os
import subprocess
import sys
import tempfile

# `exec_enabled=True` registers the Kraken exec client, which builds the Rust-backed HTTP/WS
# machinery whose teardown is the subject; the sibling build without it disposes cleanly.
_PROBE = """
import asyncio, sys
from pathlib import Path

from cli.config import EngineConfig
from cli.engine import build_shadow_node

root = Path(sys.argv[1])
rounds = int(sys.argv[2])
for i in range(rounds):
    asyncio.set_event_loop(asyncio.new_event_loop())
    node = build_shadow_node(
        EngineConfig(store_dir=root / f"store{i}", journal_dir=root / f"journal{i}", exec_enabled=True)
    )
    # Never run(). dispose() closes the loop as its last act while the adapter's Rust threads are
    # still unwinding -- the racing branch. Note dispose() picks that branch from the loop's STATE,
    # not from whether the node ran: `zcrypto engine run` reaches loop.close() too, so this probe
    # exercises the shape of the production shutdown, not a test-only corner.
    node.dispose()
    print(f"disposed {i + 1}/{rounds}", flush=True)
"""


def main() -> int:
    children = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    # Zero rounds would make every child trivially "complete" and the whole run vacuously clean.
    if children < 1 or rounds < 1:
        print("children and disposes_per_child must both be >= 1")
        return 2

    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)

    version = subprocess.run(
        [sys.executable, "-c", "import nautilus_trader as n; print(n.__version__)"],
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()
    print(f"nautilus_trader {version} — {children} children x {rounds} dispose(s)\n")

    signals, clean, other = 0, 0, 0
    for i in range(1, children + 1):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, "-c", _PROBE, td, str(rounds)],
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
        code = result.returncode
        # Count the child's own progress lines and REQUIRE the full set: a child that exits 0 without
        # reaching dispose() has proven nothing, and must never be counted as a clean result.
        done = result.stdout.count("disposed")
        if code == 0 and done == rounds:
            clean += 1
            verdict = f"clean ({done}/{rounds} disposed)"
        elif code == 0:
            other += 1
            verdict = f"INCONCLUSIVE — exited 0 after only {done}/{rounds} disposed"
        elif code < 0 or code >= 128:
            signals += 1
            verdict = f"SIGNAL DEATH code={code} after {done}/{rounds} disposed"
        else:
            other += 1
            verdict = f"non-zero code={code} after {done}/{rounds} disposed"
        print(f"  child {i:2d}/{children}: {verdict}")
        if code != 0:
            print("    " + "\n    ".join((result.stderr or "").strip().splitlines()[-15:]))

    print(f"\nnautilus_trader {version}: clean={clean} signal-deaths={signals} other={other} of {children}")
    # Kept apart deliberately: only a SIGNAL death is evidence of the race. A child that died any
    # other way (an import error from the very bump under test, a partial run) means the probe never
    # reached a verdict -- reporting that as the race would manufacture a finding out of a broken run.
    if signals:
        print("VERDICT: DIRTY — a native abort occurred. The race is locally reachable; escalate,")
        print("         and do not merge the bump on this version.")
        return 1
    if other:
        print("VERDICT: NO VERDICT — children failed without a signal, so nothing was tested. Read the")
        print("         stderr above and fix the probe or the environment before concluding anything.")
        return 1
    print("VERDICT: clean — this does NOT clear the race (it never reproduced locally on the previous")
    print("         version either). Record the version probed; the open topic stays open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
