---
status: resolved
---

# The canonical root's only join has no door, so `data rebuild ohlc-reach` tracebacks on a foreign-typed frame

## Context — what

T0193's twelfth read walked every reader of a parquet on this file family and found one join a command reaches
left undoored: `reach_round`'s canonical read in `cli/ohlc/reach.py`, over the CANONICAL root (two more, in
`cli/tick/reconcile.py` and `cli/backfill/reconcile.py`, no command reaches today). Its caller is
`cli/data/rebuild.py`, whose command handlers caught `ConfigError` / `DataSyncError` / `ManifestError` — none of
which a polars `SchemaError` is — so a canonical frame whose `ts` column was typed anything but
`Datetime("us", "UTC")` reached the operator as a raw traceback out of `zcrypto data rebuild ohlc-reach`.

That is the T0193 class exactly: a broken data input arriving as a traceback instead of an abort naming the
file. The store side is closed — `_require_joinable_ts` in `cli/engine/store.py` is the door, called by
`refresh_store` and `seed_store` — and the canonical side was one call away from the same treatment.

## Why this matters

Lower stakes than the store readers and worth saying so: this is a workstation-only command, not the live trade
path, and every parquet under `data/` today is `Datetime("us", "UTC")` (128 of 128, measured — every root under `data/`). What makes
it worth registering rather than dropping is the arrival path — a republished quarterly dump is written by
whatever wrote it, and `ns`-typed parquet is what pandas and pyarrow produce.

## Findings so far

What PR #514 (T0193) measured is the sections above.

## Resolution

Delivered by PR #568. `cli/ohlc/reach.py` reads each canonical file through `_read_canonical`, which raises `OHLCError` naming the file, the series, each column that differs and the recovery — a rebuilt set (`zcrypto data rebuild ohlc-full --no-push`, then promoted), never a recast in place — before the REST call is spent. `cli/data/command.py` aborts on `BUILDER_REFUSALS`, the classes a builder in `cli/data/rebuild.py`'s `REBUILDABLE` raises on purpose, so the refusal reaches the operator as an abort.

The door is wider than this topic asked for, because the measurement was. Eleven foreign-typed variants of one canonical file were driven through `reach_round` and every one reached the caller as a bare exception, in five classes: a `ts` of `ns`, `ms` or another zone fails the join, a naive `ts` fails a comparison before it, a string or absent `close` fails the seam's comparison — and a Float32 price, an Int32 `count`, an extra column or another column order pass the join and fail the `pl.concat` behind it. So the door holds a file to the whole of `FRAME_SCHEMA`, the schema `to_frame` writes, which all 94 OHLC parquets under `data/` carry. It reads the keys as well: a frame with no rows, or with no stamp that is not null, was a `TypeError` out of the same function, and a single null stamp or a repeated one was written through into the reach set unremarked. `seam_overlap` in `cli/ohlc/seam.py` now counts an absent close on either side as a disagreement, where a plain `!=` answered null and the filter dropped the row as though it agreed. The handler is wider for the same reason: it caught `DataSyncError` alone, so `BackfillError`, `CostModelError`, `DerivativesError`, `ManifestError`, `SnapshotError` and `UniverseError` were tracebacks out of `data rebuild` as well.

The other joins on `ts` were walked again. `cli/tick/reconcile.py`, `cli/backfill/reconcile.py` and `seam_15m_to_1h` in `cli/backfill/substrate15m.py` are still reached by no command. `quote_volume_in_eur` in `cli/universe/volume.py` IS reached, by `data rebuild universe`, and is left: both of its frames come from one root, and driven over a root retyped `ns` throughout the rebuild succeeds — it fails only over a root whose legs disagree with each other, which is not how a republished set arrives.
