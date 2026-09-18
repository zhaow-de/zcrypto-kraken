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

## Findings so far

Nothing investigated since registration: what PR #514 (T0193) measured is the sections above.

**This topic and [[T0199]] are one door carrying two numbers, measured 2026-09-18.** The snapshot write path this topic names owns no writer of its own: `cli/engine/cycle.py` imports `write_parquet` from `cli/ohlc/dataset.py`, where it is defined once, and calls it at the journal-snapshot write. That is the same helper [[T0199]]'s open fork weighs as the place a non-finite close should be refused. So a finiteness claim added at this write and a refusal added there would land on one function, and deciding them separately invites two incompatible answers on it. Whichever is decided first records what it decided for the other.

**The helper is shared well beyond the engine**, with nine call sites across seven modules — three in `cli/engine/store.py`, one each in `cycle.py`, `ingest.py`, `reach.py`, `backfill.py`, `oi.py` and `funding.py` — and two of those callers write frames carrying no close column at all, so a claim stated at the write cannot assume the frame has one. Carrying it on `SnapshotEntry` instead keeps the change inside the journal's own record and avoids that reach, which is the trade this topic's next steps weigh.

## Suggested next steps

- Enumerate what a write-time claim would cost: `snapshot_content_hash` already walks the closes, so the check
  is one pass over data already in hand.
- Decide whether the claim is a new `SnapshotEntry` field (a schema bump, so a reader migration) or a refusal
  at write with no field at all — the latter needs no schema change and leaves the record format alone.
- A refusal at write is a capture-path change: it takes the same attended-window care as any other.
