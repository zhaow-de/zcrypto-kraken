---
status: open
ripe_when: live now — one bad `timestamp` field from Kraken permanently truncates the hour it lands in, on every affected stream
---

# Hour rotation trusts an untrusted timestamp, so one bad stamp closes the hour early

## Context — what

`SegmentWriter.append()` rotates the hour from the **event's own `ts`** — `entry["timestamp"]`, a
field Kraken sends and `cli/capture/command.py::_parse_ts` parses straight through. A single event
stamped **up to `MAX_TS_AHEAD` (1 h) in the future** therefore finalizes the hour still in progress:

1. the event's hour > `_current_hour`, so `_finalize_hour()` publishes the live hour as a **committed,
   complete** `<HH>.parquet` — with only the rows captured so far;
2. every genuine event for the rest of that hour is then dropped by the late-event guard, because
   `<HH>.parquet` on disk is exactly what "this hour is closed" means;
3. and the loss **survives a restart**: the next process seeds its floor from that same final.

Executed (a reviewer, against `251e064`): clock 13:05, live events 13:00–13:02, then one event stamped
`14:00` → `13.parquet` published holding 3 rows; events at 13:20 and 13:59 dropped, before *and*
after a restart. ~54 min × 20 streams, permanent.

`_implausible()` does not catch it: it drops a stamp only when it is more than `MAX_TS_AHEAD` ahead of
**both** our clock and the stream itself, and `+1 h` is inside that window by construction.

## Why this matters

L2 is unbackfillable, and this is the same blast radius as the T0036 clock bug it outlived
(330/330 rows across 55 min, all pairs, both kinds) — but reachable from a **single untrusted input
field** rather than from a mis-set clock. It is pre-existing (the same stamp truncates the hour on
`develop` too), but T0036 changed its aftermath: the old writer's restart re-seeded the hour from the
wall clock and healed, via the `_adopt_partial_final` path that was itself removed for duplicating
rows. Under the T0036 invariant a committed final is never reopened, so the truncation is now
**permanent by design** — correctly, since the writer cannot know the final was premature.

Never observed in production. It is a hardening gap, not a live incident.

## Findings so far

- Reproduced by a review subagent against `251e064` (`_implausible`, `segment_writer.py:42`;
  rotation, `:173-186`; floor, `:436`).
- Shrinking `MAX_TS_AHEAD` does **not** fix it: the window is what keeps the two witnesses'
  failure modes from overlapping. At 5 min, a clock lagging >5 min plus a >5 min gap between trades
  on a thin pair (routine, overnight) makes both witnesses fire on live data → silent blackout. The
  window trades "a garbage stamp within W passes" against "a clock lag > W *and* a stream gap > W
  blacks the stream out", and there is no W that is safe on both sides.
- A wall-clock veto on the rotation (`refuse to close hour H while our clock says H is not over`) is
  the same trade in another shape: it blacks out the stream whenever the clock lags. The clock is not
  trustworthy enough to gate live data — that is the whole finding of T0036.
- The only sound fix found is **corroboration**: a new hour is opened, and the old one finalized, only
  once **two** events agree on it. A lone stamp then never rotates. Sketch: hold the first event of a
  candidate hour in a small pending list; a second event in the same hour confirms it (flush the held
  events into the new hour, in order); an event back in the current hour leaves the candidate pending;
  a *later* candidate hour supersedes it, and the superseded hour — which time has demonstrably moved
  past — is opened and flushed rather than dropped, so a lone print in a sparse hour is never lost.
- Not attempted in the T0036 round: it is new state on `append()`'s hot path, which is where every
  round of this fix has drawn its criticals, and it needs its own TDD cycle and its own review.

## Suggested next steps

- Implement the corroboration rule above in `SegmentWriter.append()`, TDD, with regression tests for:
  a lone far-future stamp (must not rotate, must not publish); a genuine boundary (must rotate on the
  second event, losing nothing); a lone print in an otherwise empty hour (must still be published);
  out-of-order events straddling a boundary (must land in their own hours, not be dropped as late);
  and `close()` (the held events must not be silently lost).
- Decide what to do with the held stamp itself once its hour is corroborated — it is a real book delta
  with a wrong `ts`. Storing it in the hour its `ts` names is the current behaviour and keeps the
  "hour H's file holds hour H's rows" invariant; dropping it loses a real row. Prefer storing it.
- Consider whether `MAX_TS_AHEAD` earns its keep at all once rotation is corroborated: its only job
  then is to stop a far-future stamp from being *stored* in a wrong-hour segment, which is a much
  smaller harm than either of the failure modes the guard itself can cause.
