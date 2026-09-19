---
status: open
ripe_when: 'the next change to the store write path -- `seed_store` in `cli/engine/store.py`, or the shared `write_parquet` in `cli/ohlc/dataset.py` -- to `seam_overlap` in `cli/ohlc/seam.py`, or to the `dropped_tail` render in `cli/engine/soak.py`; any is the commit that can distinguish a NaN-caused drop from a short store, or an absent close from an agreeing one.'
---

# A NaN reaching the store drops a report tail instead of refusing it

## Context — what

`cli/ohlc/dataset.py`'s `write_parquet` validates nothing, and `seed_store` copies a canonical through
`_require_joinable_ts`, a type door with no value check. So a non-finite close can be resident in a
store parquet, and the soak report then renders with a dropped tail rather than a refusal.

T0193 closed this input class everywhere it was a traceback: `_validate_grid` refuses a non-finite close at the
door both crossfreq builders enter, `read_store_series` refuses a frame it cannot read as prices, and
`_require_joinable_ts` refuses a `ts` column the seam join cannot take. It deliberately did NOT refuse a
non-finite close at `read_store_series`, on the reading that the degrade net is where this input belongs.

**No decision actually rules on a store NaN, and that is the gap.** Spec `00059` D7 covers the
rebuild-unavailable case — the two internals metrics read `n/a` with a stated reason rather than voiding the
run — and `00058` D2's tail drop is the structural one (score only boundaries whose forward bar is complete and
`T+4h <= now`, which drops the newest 1-2 cycles on every healthy run). Neither says what should happen to a
bar whose close is `nan`. What happens today is that it leaves the scored set silently.

## Why this matters

The drop is silent in the one place an operator reads. `dropped_tail` is rendered, but nothing distinguishes a
NaN-caused drop from a legitimately short store, so a poisoned tail and a quiet venue look identical on the
page. The fixture attempt that first suggested a NaN could not reach the store hit `to_frame`'s refusal on the
REST parse, not the writer's — measured on T0193's branch, the writer refuses nothing.

## Findings so far

What PR #514 (T0193) measured is the sections above.

**This topic and [[T0200]] are one door.** [[T0200]]'s journal-snapshot write reaches the same `write_parquet` this topic's fork weighs as the place a non-finite close should be refused: `cli/engine/cycle.py` imports it from `cli/ohlc/dataset.py`. Settling them apart invites two incompatible answers on a single function, so whichever is decided first records what it decided for the other.

**A door at that helper is not local to the engine, which is a cost the fork has to carry.** Its callers reach past `cli/engine/` into the OHLC, backfill and derivatives packages, and two of them write frames with **no close column at all** (`cli/derivatives/funding.py`'s schema is `ts`/`funding_rate`/`interval_hours`; `cli/derivatives/oi.py` names no close), so a close-value door there cannot be unconditional. `cli/capture/segment_writer.py` is outside the blast radius entirely: it calls polars' own `df.write_parquet` method rather than this helper.

**An ABSENT close is this fork's case as well, and it gets further than a NaN does.** `to_frame` refuses NaN and admits null: a row whose close is JSON `null` comes through with `close` null, because the guard's `is_nan()` answers null for a null and `any()` ignores it — so it passes the REST parse, where the NaN fixture above was refused. `seam_overlap` in `cli/ohlc/seam.py` then compares with `!=`, which answers null for that row, and the filter drops it, so the row counts as a shared stamp that agrees, in `reach_round` and in the store's `_reconcile` alike: a seam of absent closes reads as one that holds. The one-expression fix is NOT local: it turns such a row inside `refresh_store`, under `run_cycle`, from a silent merge into an `EngineError`, on a path no test drives.

## Suggested next steps

- Decide where the refusal belongs: at `write_parquet` (an engine, OHLC, backfill and derivatives blast radius, and it
  would refuse a frame a research path may legitimately hold), or as a distinguishing REASON on the report's
  `dropped_tail` line, which changes no writer.
- If the report line is chosen, the reason has to name the bar and the value, the way `_validate_grid`'s does.
- A trigger on `dropped_tail > 0` alone will not do: spec `00058` D2 scores a cycle only if the next one exists,
  so a healthy run drops the last segment cycle and plan `00058`'s acceptance asserts `dropped_tail >= 1`.
