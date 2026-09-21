---
status: partial
ripe_when: 'the writing of the recovery-text spec for the store door''s width, or the next change to `_require_joinable_ts` in `cli/engine/store.py`'
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

**The same door is narrow in TYPE and in KEYS as well as in value, and this topic holds all three** (widened on the owner's word, 2026-09-19, rather than registered apart: it is one door and one decision). `_require_joinable_ts` holds `ts` to `Datetime("us", "UTC")` and `close` to a numeric dtype. `_reconcile`, which `seed_store` and `refresh_store` both run behind it, concatenates the store frame onto a `to_frame` result, and that needs every dtype, every column and the column order to match; and the door reads no row at all, so it cannot see an empty frame, a null stamp or a repeated one.

## Why this matters

The drop is silent in the one place an operator reads. `dropped_tail` is rendered, but nothing distinguishes a
NaN-caused drop from a legitimately short store, so a poisoned tail and a quiet venue look identical on the
page. The fixture attempt that first suggested a NaN could not reach the store hit `to_frame`'s refusal on the
REST parse, not the writer's — measured on T0193's branch, the writer refuses nothing.

## Findings so far

What PR #514 (T0193) measured is the sections above.

**This topic and [[T0200]] are one door.** [[T0200]]'s journal-snapshot write reaches the same `write_parquet` this topic's fork weighs as the place a non-finite close should be refused: `cli/engine/cycle.py` imports it from `cli/ohlc/dataset.py`. Settling them apart invites two incompatible answers on a single function, so whichever is decided first records what it decided for the other. Decided first by [[T0200]], resolved by spec `00116`: the helper is not the door; the engine's own snapshot write refuses an unusable present close before its first file, and the shared `write_parquet` stays as it is, so this fork's helper arm is closed and its other halves stand.

**A door at that helper is not local to the engine, which is a cost the fork has to carry.** Its callers reach past `cli/engine/` into the OHLC, backfill and derivatives packages, and two of them write frames with **no close column at all** (`cli/derivatives/funding.py`'s schema is `ts`/`funding_rate`/`interval_hours`; `cli/derivatives/oi.py` names no close), so a close-value door there cannot be unconditional. `cli/capture/segment_writer.py` is outside the blast radius entirely: it calls polars' own `df.write_parquet` method rather than this helper.

**An ABSENT close is this fork's case as well, and it gets further than a NaN does.** `to_frame` refuses NaN and admits null: a row whose close is JSON `null` comes through with `close` null, because the guard's `is_nan()` answers null for a null and `any()` ignores it — so it passes the REST parse, where the NaN fixture above was refused. `seam_overlap` in `cli/ohlc/seam.py` then compares with `!=`, which answers null for that row, and the filter drops it, so the row counts as a shared stamp that agrees, in `reach_round` and in the store's `_reconcile` alike: an absent close agrees with whatever the other side carries, a disagreeing price included. The one-expression fix is NOT local: it turns such a row inside `refresh_store`, under `run_cycle`, from a silent merge into an `EngineError`, on a path no test drives.

**What the door's width costs.** An `open` of Float32, a `count` of Int32, an extra column and the columns in another order pass the door and the seam and fail at `_reconcile`'s concat, as a bare polars `SchemaError` or `ShapeError`; neither is an `EngineError`, so each passes `run_cycle`'s and both commands' handlers as a traceback. **A re-typed `close`, Float32 or Int64, fails differently, and how depends on the prices.** A price the cast leaves exact compares equal at the seam and reaches the same concat. A real price does not survive the cast, so `seam_overlap` reads the shared stamps as disagreeing and the reader raises the seam's own `overlap mismatch` `EngineError` — named, and wrong about its cause: it blames the data, and under `refresh_store` it prescribes `zcrypto engine seed`, which over that same store file is the one path that does reach the concat and tracebacks. **When the deviated file is the CANONICAL one, `seed_store` has already copied it into the store before either failure** — the refused-copy-left-behind that the comment above that copy says the door prevents; every later run then fails on the store's own file. A canonical with no rows is copied too and ends in the `window shortfall` `EngineError`. A single null stamp, and a repeated stamp, raise nothing on either reader and are carried into the store. Nothing on disk carries any of these today, and the arrival path is a republished canonical set.

**The canonical root's reach door is the worked sibling.** `_read_canonical` in `cli/ohlc/reach.py` holds a canonical file to the whole of `FRAME_SCHEMA` and to non-empty, non-null, unrepeated stamps, and raises the caller's own error naming the file. The store's door was not given the same treatment with it, because its recovery text is the hard part and not its check.

## Done so far

Branch `fix/t0199-t0201-store-refusals`, on the owner's rulings (1) and (3) of 2026-09-21; ruling (2), the door's width, stays open below.

- Ruling (1), an absent close is a disagreement: `seam_overlap` in `cli/ohlc/seam.py` keeps a shared row whose close is null on either side among the mismatches, and both callers refuse it before their mismatch branches, naming the stamp and the side -- `_merge_or_detach` in `cli/ohlc/reach.py` as an `OHLCError`, `_reconcile` in `cli/engine/store.py` as an `EngineError` whatever `allow_replace` is, so a REST null never replaces a store close on a re-seed. `to_frame` in `cli/ohlc/dataset.py` and `write_parquet` are untouched: a REST-only row with a null close stays admitted as an absent bar, because spec `00116` D2 admits `None` at the engine's own write and [[T0200]]'s ruling keeps the shared writer as it is.
- Ruling (3), the report line: `RealizedSeries.dropped_reasons` names, per skipped cycle, a PRESENT non-finite close -- the cycle, the asset, the stamp and the value; `render_report` prints the entries under `dropped_tail` and `_json_payload` carries them in `provenance`. An absent close or a missing stamp is the short store the STORE-BOUND block already describes and gets no line, and no `dropped_tail > 0` trigger was added.
- The canonical is already checked before it is copied: `seed_store` reads it and holds it through `_require_joinable_ts` before `write_parquet` copies it (`cli/engine/store.py`, commit e38c3cfe1) -- for what the door refuses today, so a wider door widens that check with it.
- [[T0201]], the wrong-instant store frame, is resolved on the same branch: the soak's realized leg refuses a stamp off the 4h grid as a plain `EngineError`.

## Suggested next steps

- The door's width is the same decision, and the check is the small half of it. Holding a store frame to `FRAME_SCHEMA` and to sound stamps is a few lines; the claim a change must carry is that every frame it newly refuses already fails -- at the seam or at `_reconcile`'s concat -- so it refuses nothing that works today -- true of the type and shape deviations, and NOT of a null or repeated stamp, which work today in the sense that nothing stops them. The canonical check before the copy widens with the door.
- The recovery text is the large half. The door's two recoveries are written for `ts` alone, and `tests/test_engine_store.py` pins them. A Float32 price has no in-place recast -- the precision is gone -- so a deviated STORE file's recovery is a re-seed forced by deleting the file, which a plain re-seed leaves in place, with the loss and the seam condition that recovery already names. The store is unversioned and `docs/reference/data-catalog-full.md` records that rebuildable is not identical, so the text that prescribes the delete prescribes the copy aside before it. What an operator is told per deviation is a choice on the live trade path, so it takes a spec, and it reaches the engine only at a converge.
- The engine host's store repair carries the same delete, and the recovery text covers it or says why not: the delivery comment in `infra/ansible/roles/engine/tasks/main.yml` and the assert's `fail_msg` remove the store dir for the converge to re-deliver the workstation's copy, naming no copy aside and no loss. Three code carriers send the host to the same workstation command: `refresh_store`'s shortfall and mismatch hints in `cli/engine/store.py` and `run`'s bind-mount refusal in `cli/engine/command.py`; the recovery text routes them by host too, as the engine runbook's cycle-stale bullet and failed-cycle step 5 now do.
- The interior off-grid stamp on the LIVE path is a case the door's spec holds: `_union_align` in `cli/engine/cycle.py` admits it for a non-BTC leg into the model calendar, and only the /BTC case is pinned (`tests/test_engine_cycle.py::test_a_btc_only_stamp_never_enters_the_model_calendar`); the soak's realized leg refuses it since [[T0201]], the cycle does not.
- Two owed sites of that spec's plan, both Fable-floor engine-role changes that ride it: `docs/specs/00042-vps-deployment-design.md:20` is a third carrier of the host's store delete (`rm -rf /var/lib/zcrypto-engine/store`, no copy aside, no loss named) beside the engine role's delivery comment and its assert `fail_msg` in `infra/ansible/roles/engine/tasks/main.yml`; and that `fail_msg` sends the operator to "the poisoned-store runbook above", a source comment ansible output never prints, and spells the re-run without `-e converge_primary=true`, which the comment says is required.
