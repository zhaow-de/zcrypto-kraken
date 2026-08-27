#!/usr/bin/env python3
"""How long does the reconcile ledger take to scan, at sizes the live one has not reached?

`_load_ledger` reads the whole append-only JSONL and `_totals` sums it, on EVERY cycle -- so both
are O(ledger). T0044 registered that as a risk against a record-count trigger nobody could check.
This measures the curve instead, so the question is answered by running a command rather than by
re-deriving an estimate under time pressure.

What the numbers are judged against, and why those two:
  * the reconcile cycle runs half-hourly, so a scan approaching 1800 s starts colliding with the
    next cycle. That is the practical cliff.
  * `zcrypto-reconcile-exporter-stale` and `zcrypto-reconcile-source-lag` both page at 3 h. A scan
    cannot threaten those without having blown the cadence first, so the cadence is the binding
    constraint and the alerts are the backstop.

Synthetic records mirror what `_totals` actually reads, and the KEY SPACE is the part that has to be
right: the writer emits each (pair, kind, hour) at most once, so a real ledger's `measured` dedup set
grows with the file and is the one structure in the pass that is not O(1) per record. Cycling pair
and hour off `n % k` saturates that set at a few hundred entries however large the file gets, which
short-circuits nearly every mint-family record at `if key in measured: continue` and understates both
the time and the memory. Hours therefore advance monotonically here, with pair x kind cycling inside
each hour, exactly as the writer does.

Timing AND memory are measured in a child process that has held no other ledger, because `ru_maxrss`
is a high-water mark and a forked child inherits the parent's. Measuring sizes in one loop inflates
every reading after the first; spawning a child from a parent that just did the timing inflates it
identically, while looking rigorous.

Run: `uv run python infra/scripts/bench-ledger-scan.py [--sizes 1000,10000,...]`
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cli.archive.command import _load_ledger, _totals

CYCLE_PERIOD_SECONDS = 1800.0  # half-hourly reconcile cadence -- the binding constraint
PAGE_THRESHOLD_SECONDS = 10800.0  # exporter-stale / source-lag, both 3h -- the backstop

# The writer's own vocabulary. `healable` is NOT one of them; `trade_deficit` and `failed` are.
_STATES = ("minted", "would_mint", "trade_deficit", "both_streams_silent", "total_loss", "unwitnessed", "failed")
_VERDICTS = ("venue_silent", "capture_divergent", "undetermined")
_KINDS = ("book", "trades")


_PAIRS = 12
_GENESIS = datetime(2026, 1, 1, tzinfo=UTC)


def _record(rng: random.Random, n: int) -> dict:
    """One ledger record, keyed as the writer keys them: one (pair, kind, hour) per record, hours
    advancing so the dedup set grows with the file rather than saturating."""
    slot, within = divmod(n, _PAIRS * len(_KINDS))
    hour = _GENESIS + timedelta(hours=slot)
    state = rng.choice(_STATES)
    rec = {
        "ts": hour.isoformat(),
        "pair": f"PAIR{within % _PAIRS}",
        "kind": _KINDS[within // _PAIRS],
        "hour": hour.isoformat(),
        "state": state,
        "residual_seconds": round(rng.uniform(0, 900), 3),
    }
    if state == "minted":
        rec["healed_seconds"] = round(rng.uniform(0, 900), 3)
    if state == "both_streams_silent":
        rec["verdict"] = rng.choice(_VERDICTS)
    if state in ("minted", "would_mint", "trade_deficit"):
        # Read by `_totals` on the mint-family branch; absent, four float() conversions take a
        # missing-key fast path the real records never take.
        rec["claimed_seconds"] = round(rng.uniform(0, 900), 3)
        rec["trades_added"] = rng.randint(0, 5000)
        rec["trades_secondary_deficit"] = rng.randint(0, 500)
        rec["trades_deduped"] = rng.randint(0, 500)
    return rec


def _write(root: Path, count: int, seed: int = 0) -> int:
    rng = random.Random(seed)
    path = root / "reconcile-ledger.jsonl"
    with path.open("w") as fh:
        for n in range(count):
            fh.write(json.dumps(_record(rng, n), default=str) + "\n")
    return path.stat().st_size


def _child(root: Path, repeats: int) -> None:
    """Time and measure one ledger in a process that has held no other.

    Everything happens HERE, not in the parent, and that is the whole point. `ru_maxrss` is a
    high-water mark, and a forked child INHERITS the parent's -- a child that allocates nothing
    reports ~13 MiB from a small parent and ~1820 MiB from a 1.8 GiB one. So a parent that ran the
    timing itself would hand every subsequent size its own peak, which is the same artifact as
    measuring several sizes in one loop, only harder to see.
    """
    import resource

    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    best_load = best_totals = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        records = _load_ledger(root)
        t1 = time.perf_counter()
        _totals(records)
        t2 = time.perf_counter()
        best_load = min(best_load, t1 - t0)
        best_totals = min(best_totals, t2 - t1)
        n = len(records)
        del records
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"{best_load} {best_totals} {peak} {peak - before} {n}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1000,10000,50000,100000,250000,500000,1000000")
    ap.add_argument("--repeats", type=int, default=3, help="best-of, to shed scheduler noise")
    ap.add_argument("--child", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.child:  # re-entry: this process holds nothing else, so its ru_maxrss is this ledger's
        _child(Path(args.child), args.repeats)
        return

    print(f"{'records':>10} {'MiB':>7} {'load s':>9} {'totals s':>9} {'total s':>9} {'% of cycle':>11} {'peak MiB':>9}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for size in (int(s) for s in args.sizes.split(",")):
            nbytes = _write(root, size)
            out = subprocess.run(
                [sys.executable, __file__, "--child", str(root), "--repeats", str(args.repeats)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split()
            best_load, best_totals, peak, _delta, n = float(out[0]), float(out[1]), float(out[2]), float(out[3]), int(out[4])
            assert n == size, f"child loaded {n} of {size}"
            total = best_load + best_totals
            print(
                f"{size:>10,} {nbytes / 1048576:>7.1f} {best_load:>9.3f} {best_totals:>9.3f} "
                f"{total:>9.3f} {total / CYCLE_PERIOD_SECONDS * 100:>10.2f}% {peak:>9.0f}"
            )
    print(
        f"\ncycle period {CYCLE_PERIOD_SECONDS:.0f}s (half-hourly) is the binding constraint; "
        f"exporter-stale/source-lag page at {PAGE_THRESHOLD_SECONDS:.0f}s."
    )


if __name__ == "__main__":
    main()
