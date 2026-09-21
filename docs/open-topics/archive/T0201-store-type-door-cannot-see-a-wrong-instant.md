---
status: resolved
---

# The store's type door cannot see a wrong instant, and the store leg then degrades at rc 0

## Context — what

`read_store_series` reads TYPES, never the stamps' values. Measured on T0193's branch: a frame correctly typed
`Datetime("us", "UTC")` whose stamps sit 37 minutes off the 4-hour grid passes the door, the realized leg finds
no boundary at all, and the report renders `no realized series available` with `window_bound : store` and
`store last bar : 2026-07-16T08:37:00+00:00` — at **rc 0**.
`tests/test_engine_soak_command.py::test_soak_check_degrades_at_rc_0_on_a_store_frame_whose_stamps_are_the_wrong_instants`
pins that whole render, the two `ripe_when` fields included.

## Why this matters

It is the one shape of broken store input T0193 leaves degrading rather than refusing. The door cannot close it — the
grid's alignment is a value question, and refusing on it from a type check would need the reader to know the
grid's origin, which is not the frame's to state.

## Findings so far

What PR #514 (T0193) measured is the sections above.

**The daily pass's `soak verdict` row cannot evaluate this trigger.** Spec `00115` runs `soak-check` over a store derived from the newest journaled 240 snapshots, whose last bar is that cycle's own `last_ts` and so sits on a 4h boundary by construction. An off-boundary `store last bar` can only come from a run over the engine host's own store, which has no replica (`docs/reference/fleet.md`).

## Resolution

Resolved on branch `fix/t0199-t0201-store-refusals`, folded in beside [[T0199]] on the owner's rulings of 2026-09-21: `realized_series` in `cli/engine/soak.py` holds every stamp of every asset's `240` leg to the 4h grid, right after the closes are read, and refuses the first breach as a plain `EngineError` naming the leg, the count of off-grid stamps and the first of them -- not a `SoakError`, which `soak_report` folds into a void payload at rc 0 -- so `soak-check` aborts at rc 1. `read_store_series` still reads types alone, and its docstring now says where the value is refused. The test that pinned the rc 0 render is renamed and inverted to `tests/test_engine_soak_command.py::test_soak_check_refuses_a_store_frame_whose_stamps_are_the_wrong_instants`, and `tests/test_engine_soak.py::test_realized_series_refuses_an_interior_off_grid_stamp_on_a_non_btc_leg` drives the interior stamp on a non-BTC leg.

The premise under *Why this matters* -- that refusing on the grid would need the reader to know the grid's origin, "which is not the frame's to state" -- was wrong: the grid is epoch-anchored (`cli/backfill/aggregate.py` floors `ts // interval_secs * interval_secs`), so the predicate reads no origin off any frame. The cheaper fix the first step proposed, a rendering note on `store last bar`, was not taken: the owner ruled a refusal.

The host read the last step asked for was taken and settles spec `00115` D2's equality: on every `240` and `1440` leg the journaled closes equalled the live store's at their stamps, with no extra or missing stamp at or before `last_ts` and no off-grid stamp. The copy was deleted after the read.
