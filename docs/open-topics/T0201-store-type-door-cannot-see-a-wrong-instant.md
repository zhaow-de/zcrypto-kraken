---
status: open
ripe_when: 'a soak-check run renders `window_bound : store` with a `store last bar` that is not on a 4h boundary (00/04/08/12/16/20 UTC) -- the shape a wrong-instant store frame produces, and one a legitimately short store cannot.'
---

# The store's type door cannot see a wrong instant, and the store leg then degrades at rc 0

## Context — what

`read_store_series` reads TYPES, never the stamps' values. Measured on T0193's branch: a frame correctly typed
`Datetime("us", "UTC")` whose stamps sit 37 minutes off the 4-hour grid passes the door, the realized leg finds
no boundary at all, and the report renders `no realized series available` with `window_bound : store` and
`store last bar : 2026-07-16T08:37:00+00:00` — at **rc 0**.
`tests/test_engine_soak_command.py::test_soak_check_degrades_at_rc_0_on_a_store_frame_whose_stamps_are_the_wrong_instants`
pins exactly that.

## Why this matters

It is the one shape of broken store input T0193 leaves degrading rather than refusing, and it is the shape a
reader cannot tell from a legitimately short store: both render the same line. The door cannot close it — the
grid's alignment is a value question, and refusing on it from a type check would need the reader to know the
grid's origin, which is not the frame's to state.

## Suggested next steps

- The cheapest honest fix is on the REPORT, not the door: `store last bar` already prints the stamp, so the
  renderer can say when that stamp is off the interval's grid. That is a rendering change with no refusal
  attached and no blast radius on the live path.
- If a refusal is wanted instead, it belongs where the interval is known and the frame is being consumed as a
  calendar — `realized_series`, not `read_store_series`.
