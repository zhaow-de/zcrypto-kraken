---
status: open
ripe_when: 'a soak report renders a non-zero `dropped_tail` on a store no one hand-edited -- the JSON payload of `zcrypto engine soak-check` carries `dropped_tail > 0` while `store last bar` is on the current 4h boundary.'
---

# A NaN reaching the store drops a report tail instead of refusing it

## Context — what

`cli/ohlc/dataset.py`'s `write_parquet` validates nothing, and `seed_store` copies a canonical through
`write_parquet(read_parquet(...))`, which validates nothing either. So a non-finite close can be resident in a
store parquet, and the soak report then renders with a dropped tail rather than a refusal.

T0193 closed this input class everywhere it was a traceback: `_validate_grid` refuses a non-finite close at the
door both crossfreq builders enter, `read_store_series` refuses a frame it cannot read as prices, and
`_require_joinable_ts` refuses a `ts` column the seam join cannot take. It deliberately did NOT refuse a
non-finite close at `read_store_series`, because spec `00059` D7 wants a store NaN dropped as a tail and a
journaled one degraded with a reason — the drop is the specified behaviour, not the defect.

## Why this matters

The drop is silent in the one place an operator reads. `dropped_tail` is rendered, but nothing distinguishes a
NaN-caused drop from a legitimately short store, so a poisoned tail and a quiet venue look identical on the
page. The fixture attempt that first suggested a NaN could not reach the store hit `to_frame`'s refusal on the
REST parse, not the writer's — measured on T0193's branch, the writer refuses nothing.

## Suggested next steps

- Decide where the refusal belongs: at `write_parquet` (a capture-adjacent change, its own blast radius, and it
  would refuse a frame a research path may legitimately hold), or as a distinguishing REASON on the report's
  `dropped_tail` line, which changes no writer.
- If the report line is chosen, the reason has to name the bar and the value, the way `_validate_grid`'s does.
