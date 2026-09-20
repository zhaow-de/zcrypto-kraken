---
status: open
ripe_when: '`cli/engine/store.py` is next changed -- a session already at the two doors this topic is about, and the arm the daily pass decides; OR a soak-check run renders `window_bound : store` with a `store last bar` that is not on a 4h boundary (00/04/08/12/16/20 UTC) -- the shape a wrong-instant store frame produces, and one a legitimately short store cannot.'
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

The trigger gained its file-touched arm with spec `00115`: the other is an evaluation statement over a `soak-check` run, which `zcrypto-daily-ops` names unevaluated, so until then nothing scheduled ever read it.

## Suggested next steps

- The cheapest honest fix is on the REPORT, not the door: `store last bar` already prints the stamp, so the
  renderer can say when that stamp is off the interval's grid. That is a rendering change with no refusal
  attached and no blast radius on the live path.
- If a refusal is wanted instead, it belongs where the interval is known and the frame is being consumed as a
  calendar — `realized_series`, not `read_store_series`.
- When the engine host's store is next read in an attended session, compare its live `240` legs against the newest journal record's snapshots: the daily `soak verdict` row scores the journaled closes (spec `00115` D2), and their equality with the live store has never been read. Pull with `ssh zcrypto 'sudo tar -C /var/lib/zcrypto-engine -cf - store' | tar -C <scratch> -xf -`, then for each `240` leg read `n_bars`, `last_ts` and the closes of `<scratch>/store` against the file the record's `snapshots[].path` names under `/mnt/zhao-crypto/engine-journal`; equal on every leg settles D2, a difference is a finding for this topic. If this topic resolves with the read still untaken, the step leaves with its own topic.
