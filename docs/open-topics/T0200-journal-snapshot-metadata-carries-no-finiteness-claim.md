---
status: open
ripe_when: 'the next change to `SnapshotEntry` in `cli/engine/journal.py`, or to the snapshot write path in `cli/engine/cycle.py` -- either is the commit that can add the claim at the write instead of the read.'
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

## Suggested next steps

- Enumerate what a write-time claim would cost: `snapshot_content_hash` already walks the closes, so the check
  is one pass over data already in hand.
- Decide whether the claim is a new `SnapshotEntry` field (a schema bump, so a reader migration) or a refusal
  at write with no field at all — the latter needs no schema change and leaves the record format alone.
- A refusal at write is a capture-path change: it takes the same attended-window care as any other.
