---
status: resolved
---

# The journal's snapshot metadata carries no finiteness claim about the data behind its `content_hash`

## Context — what

`SnapshotEntry` carries `pair`, `grid`, `n_bars`, `first_ts`, `last_ts`, `content_hash` and `path`. None of
those says anything about the VALUES the hash covers, so a snapshot whose NaN was hashed in at write time is a
valid record by every check the writer makes.

T0193 made the read refuse it: `_validate_grid` now raises `PortfolioError` on a non-finite close, the degrade
net catches it, and the run reports grid, asset, bar index and value. That is the right refusal for a record
already on disk — but it is the read paying for what the write let through.

## Why this matters

The cycle that wrote the record is the only actor still in a position to do something about it: it holds the
frame, it can re-fetch, and it has not yet published a target. By the time a reader refuses, the record is
history and every later reader pays the same cost again. The asymmetry is the T0193 class one level up — the
value door exists, it is just on the wrong side of the write.

## Findings so far

What PR #514 (T0193) measured is the sections above.

**This topic and [[T0199]] are one door.** The snapshot write path this topic names owns no writer of its own: `cli/engine/cycle.py` imports `write_parquet` from `cli/ohlc/dataset.py` and calls it at the journal-snapshot write, and that is the same helper [[T0199]]'s open fork weighs as the place a non-finite close should be refused. A claim added here and a refusal added there land on one function, so whichever is decided first records what it decided for the other.

**The helper is shared well beyond the engine**, and two of its callers write frames carrying no close column at all, so a claim stated at the write cannot assume the frame has one. Carrying it on `SnapshotEntry` instead keeps the change inside the journal's own record and avoids that reach.

## Resolution

Resolved by spec `00116` and the PR that carries it: the refusal lives at the engine's own write. `_journal_snapshots` in `cli/engine/cycle.py` walks every close of every grid before the first snapshot file is written and refuses a present close that is not a finite positive number as an `EngineError` naming the pair, the grid, the bar index, the stamp and the value, so a refused boundary leaves no snapshot directory, no record, no sidecar and no orders beside the venue record of step 0; `None` at a union absence is admitted. No `SnapshotEntry` field was added and the shared `write_parquet` is untouched, which answers the third next step, since the door is the engine's and reaches no other package, and records for [[T0199]] that its helper arm is not the place. The read-side refusal from [[T0193]] stays for records written before the door. The abort's shape is the raise, as the forming-row guard's; the operator reading is the cycle-stale runbook's bullet and its step 3, naming the host's repair as a re-delivery by the engine-tagged converge, since `zcrypto engine seed` is the workstation's command; and that seed reads the newest whole frozen `ohlc-full` sibling under the configured data root for an absent store file, the same PR's earlier commit, without which a 4h leg could not be re-seeded. Measured before the change over the NAS journal mirror on 2026-09-21: 433 records, 9,508 snapshot files, 0 unusable present closes among 156,359,450 close rows, so no record on disk is refused by the read for this reason. The owner's ruling of 2026-09-20 in chat set the placement and the shape.
