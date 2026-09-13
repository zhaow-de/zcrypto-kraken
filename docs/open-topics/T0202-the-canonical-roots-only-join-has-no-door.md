---
status: open
ripe_when: 'either arm: the quarterly canonical dump is republished (a foreign-typed frame is how one would arrive), or `cli/ohlc/reach.py` is next touched.'
---

# The canonical root's only join has no door, so `data rebuild ohlc-reach` tracebacks on a foreign-typed frame

## Context — what

T0193's twelfth read walked every reader of a parquet on this file family and found exactly one join left
undoored: `cli/ohlc/reach.py:88`, over the CANONICAL root. Its caller is `cli/data/rebuild.py`, whose command
handlers catch `ConfigError` / `DataSyncError` / `ManifestError` — none of which a polars `SchemaError` is — so
a canonical frame whose `ts` column is typed anything but `Datetime("us", "UTC")` reaches the operator as a raw
traceback out of `zcrypto data rebuild ohlc-reach`.

That is the T0193 class exactly: a broken data input arriving as a traceback instead of an abort naming the
file. The store side is closed — `_require_joinable_ts` in `cli/engine/store.py` is the door, called by
`refresh_store` and `seed_store` — and the canonical side is one call away from the same treatment.

## Why this matters

Lower stakes than the store readers and worth saying so: this is a workstation-only command, not the live trade
path, and every parquet under `data/` today is `Datetime("us", "UTC")` (128 of 128, measured — every root under `data/`). What makes
it worth registering rather than dropping is the arrival path — a republished quarterly dump is written by
whatever wrote it, and `ns`-typed parquet is what pandas and pyarrow produce.

## Suggested next steps

- Call `_require_joinable_ts` (or a `cli/ohlc/`-local twin, since importing from `cli/engine/` inverts the
  dependency) before `reach.py`'s join, and widen `rebuild.py`'s handler to the class it raises.
- The message has to name the canonical path and a recovery that works: a rebuilt set (`data rebuild ohlc-full`
  mints a correctly typed sibling), never a recast in place, which invalidates the canonical's `dataset_hash` —
  the frozen arm of T0193's door says the same.
