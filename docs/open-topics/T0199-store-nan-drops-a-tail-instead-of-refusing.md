---
status: open
ripe_when: 'the next change to the store write path (`write_parquet`/`seed_store` in `cli/engine/store.py`) or to the `dropped_tail` render in `cli/engine/soak.py` -- either is the commit that can distinguish a NaN-caused drop from a short store.'
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

PR #514 (T0193) measured the writer refusing nothing and found no decision — spec `00059` D7, `00058` D2 — that
rules on a store NaN; nothing investigated since registration.

## Suggested next steps

- Decide where the refusal belongs: at `write_parquet` (a capture-adjacent change, its own blast radius, and it
  would refuse a frame a research path may legitimately hold), or as a distinguishing REASON on the report's
  `dropped_tail` line, which changes no writer.
- If the report line is chosen, the reason has to name the bar and the value, the way `_validate_grid`'s does.
- A trigger on `dropped_tail > 0` alone will not do: spec `00058` D2 scores a cycle only if the next one exists,
  so a healthy run drops the last segment cycle and plan `00058`'s acceptance asserts `dropped_tail >= 1`.
