---
status: partial
ripe_when: the core residual is FIXED (cross-stream quorum with wall-clamped witnesses, iter shipped); the two accepted residuals below are each ripe only if ever OBSERVED in production — (a) two independent streams each taking a guard-passing bogus stamp inside the same hour's closing MAX_TS_AHEAD window, (b) a clock leading >5 min AND a bogus stamp landing together
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

**Blast radius reduced (T0036 round 5), not removed.** `MAX_TS_AHEAD` is now **5 minutes**, so a stamp
must be within 5 minutes of *both* witnesses to be trusted — a `14:00` stamp at 13:05 is now dropped.
What survives is the residual: a bogus stamp **≤5 min ahead, landing in the last 5 minutes of an
hour**, still rotates the hour early, and the truncation is still permanent. Bounded to ~5 min of one
stream rather than ~55 min of all 20, but the mechanism is untouched, and only corroboration closes it.

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
- **The "no safe W" finding was right about the *bare* `_max_ts` witness, and it has since been
  dissolved.** The original argument: at W = 5 min, a clock lagging >5 min plus a >5 min gap between
  trades on a thin pair makes both witnesses fire on live data → silent blackout (executed: a pair
  printing every 10 min under a constant 10-min lagging clock loses **12 of 12** prints and never
  recovers, since a dropped event never advances `_max_ts`). The flaw was in the witness, not in W:
  comparing against `_max_ts` **raw** measures the stream against the clock's *value*. Carrying
  `_max_ts` forward by the time elapsed since it was accepted measures it against the clock's *rate*
  instead — and a constant offset, which is what a wrong clock is, then cancels exactly. The same
  quiet pair under the same lagging clock now loses **nothing**. That let W drop to 5 min (T0036
  round 5), which is what bounds this topic's blast radius; see the `_implausible` docstring.
- A wall-clock veto on the rotation (`refuse to close hour H while our clock says H is not over`) is
  still not available: it blacks out the stream whenever the clock lags. The clock is not trustworthy
  enough to gate live data — that is the whole finding of T0036.
- **The two witnesses share one blind spot, and corroboration would not close it either.** A stream
  that is *coherently* wrong — a systematic bad stamp (a `_parse_ts` unit bug, an exchange-side clock
  fault) — advances at the normal rate, so it satisfies the stream witness **by construction**, and an
  AND can then never drop it whatever the clock says. Two events would also happily "agree" on the
  same wrong hour, so T0037's corroboration rule does not help here. Executed against the pre-fix
  writer: a coherent far-future stream poisons the archive from its **first** stamp (the hour opens in
  2030, the late-event guard drops every genuine row behind it, and the startup sweep publishes the
  live hour truncated). Closed in T0036 round 5 by `MAX_TS_ABSURD` (1 day) — a bound that answers to
  no witness and is never stood down, on the grounds that a clock is wrong by minutes or hours and
  never by days. What remains in the **band between MAX_TS_AHEAD and MAX_TS_ABSURD** is this topic:
  a systematic stamp that is wrong by, say, an hour is still accepted, and lands in the wrong hour.
- The only sound fix found is **corroboration**: a new hour is opened, and the old one finalized, only
  once **two** events agree on it. A lone stamp then never rotates. Sketch: hold the first event of a
  candidate hour in a small pending list; a second event in the same hour confirms it (flush the held
  events into the new hour, in order); an event back in the current hour leaves the candidate pending;
  a *later* candidate hour supersedes it, and the superseded hour — which time has demonstrably moved
  past — is opened and flushed rather than dropped, so a lone print in a sparse hour is never lost.
- Not attempted in the T0036 round: it is new state on `append()`'s hot path, which is where every
  round of this fix has drawn its criticals, and it needs its own TDD cycle and its own review.

## Done so far

**The core residual is closed by cross-stream quorum (design C, chosen by a judge over three executed
alternatives).** `HourOracle` (one instance shared by all 20 writers) makes a writer act on an hour
boundary — finalize the previous hour, open the new one — only once `HOUR_QUORUM` (2) witnesses have
seen time reach it. Witnesses are each stream's newest plausible `ts`, **clamped at the wall clock +
`MAX_TS_AHEAD` when observed** (see the hardening round below — unclamped witnesses re-opened the
truncation through the oracle's own state), plus the wall clock, handicapped by
`CLOCK_WITNESS_MARGIN` (5 min) so a leading clock cannot second a bogus stamp. A row for an
unconfirmed hour is **held**, never dropped — the live hour stays open (no genuine row behind the
stamp is refused) and the held row is written the moment its hour is corroborated, in arrival order,
into the hour its `ts` names (T0037's own "store it, never delete" recommendation). `close()` spills
held rows to disk under their named hour and never finalizes, so T0036 is untouched (nothing is
published early, so nothing is ever reopened). The plausibility guard (`_implausible`, `MAX_TS_AHEAD`,
`MAX_CONSECUTIVE_DROPS`, `MAX_TS_ABSURD`) is UNCHANGED — the oracle sits behind it. `oracle=None`
preserves the pre-change writer byte-for-byte (`command.py` passes one shared oracle to all writers).

**Hardening round (adversarial verification of the quorum itself; three executed defects fixed).**

- **Witness poisoning is closed by the wall clamp.** `observe()` recorded held/stood-down —
  unconfirmed, possibly bogus — stamps as witnesses and never expired them, so one stream's garbage
  burst (or a coherently-fast in-band walk of stamps each within `MAX_TS_AHEAD` of the last) parked
  its witness hours ahead; a later LONE in-window bogus stamp on any other stream then met quorum
  against the poisoned witness and truncated its live hour (executed: fed=60, LOST=[56..59],
  manifest-certified, surviving restarts) — falsifying this doc's earlier "same hour, one window,
  none lost" residual claim. The rule now: **a stream may vouch that time has reached T only once
  the wall clock is itself within `MAX_TS_AHEAD` of T** — `observe()` clamps the recorded witness at
  `now + MAX_TS_AHEAD`. Every witness (the handicapped clock included) is then ≤ `now +
  MAX_TS_AHEAD`, so no quorum, however poisoned, can confirm an hour more than `MAX_TS_AHEAD` before
  the wall reaches it. A lagging clock only *delays* confirmation — rows held/spilled, drained when
  the wall catches up, never dropped — so the no-veto rule stands. Executed on both attack shapes
  (LOST=[] on each); the genuine two-stream boundary, the lone-stream clock-paced rotation and the
  lagging-clock set-equality against the `oracle=None` baseline are pinned unchanged.
- **Held rows pass the trade de-dup.** `_hold()` never consulted `_seen`, so a T0026 reconnect
  replay landing while its hour was unconfirmed was held blind, and a stop before confirmation
  spilled BOTH copies — merged by the next process into the committed final (executed: trade_ids
  `[0,1,2,3,4,0,1,2,3,4,10]`). Held rows now dedup against a per-held-hour set seeded from the
  hour's on-disk parts and held-spills, same `trade_id` rule as stored rows.
- **A never-confirmed held spill can no longer fabricate an hour.** A held bogus stamp spilled at a
  stop became an ordinary part; if the process slept through that hour, the next start's sweep
  merged it into a manifest-certified final whose SOLE content was the uncorroborated stamp — a
  fabricated hour published as "committed and complete" (executed: `11.parquet == [999]`, valid
  sidecar). Held rows now spill as **`<HH>.held####.parquet`** — quarantine the sweep, the merge,
  the recovery floor and the archive's `verify_tree` all ignore, kept and never deleted — and are
  **redeemed** into ordinary parts only when a live, quorum-confirmed event stream OPENS their hour.
  The accepted cost: a genuine lone print held at a stop, whose hour never sees another live event
  after the restart, stays quarantined on disk instead of entering the archive — it is
  indistinguishable from the bogus stamp by construction (that is what "never confirmed" means), and
  keeping it out of certified finals is the safe side. Note for `--pairs` smoke runs with a single
  short-lived process: a stop inside the first `CLOCK_WITNESS_MARGIN` of a lone stream's hour leaves
  its rows as `.held` files until a later run genuinely opens that hour.

- Landed: `cli/capture/segment_writer.py` (`HourOracle`, `_held`, `_enter_hour`/`_admit`/`_hold`,
  `_write_part`), `cli/capture/command.py` (one shared `HourOracle`); hardening round:
  `HourOracle.observe` (wall clamp), `_hold`/`_held_seen` (held de-dup), `_redeem_held` +
  `.held`-marker spills (`segment_writer.py`), `verify_tree` skip (`cli/archive/pull.py`).
- 10 executed regression tests in `tests/test_capture_segment_writer.py` (`test_t0037_*`): the lone
  in-window bogus stamp in the last 5 min (0 loss, bogus stored in its named hour, publishes on the
  second witness); the bogus-first-stamp-after-restart (cannot sweep-publish the live hour); a genuine
  two-stream boundary (publishes within one event, streams-only, clock lagging); a 10-min lagging
  clock (loss set-EQUAL to the `oracle=None` baseline — zero added); a 10-min leading clock (no early
  publish); three escalating in-window stamps on one stream (0 loss — the attack that beats designs A
  and B); a stand-down burst (future hour never published); a lone clock-paced stream (rotation ≤300 s,
  lone print never lost); `close()`→held-spills redeemed, merged and replay-deduped by a restart; and
  the drain-order bounds. The pre-fix loss was reproduced against HEAD `189a56a` (57/58/59 dropped in
  the core and escalating scenarios; the live hour sweep-published on a bogus first stamp). The
  hardening round added 7 more (`test_t0037_*` poisoned-witness, coherently-fast walk, two replay
  de-dup shapes, fabricated-hour, held-spill floor guard; `test_verify_tree_skips_held_spills`), each
  reproduced failing against the pre-hardening writer.
- **Deploy note for ops:** finals for a quiet-market hour may now appear up to ~5 min later than
  before, when only the clock witness paces the rotation. Under a clock lagging by more than 5 min,
  confirmation (and thus finalization) is delayed by roughly the lag minus the margin — rows are
  held and spilled meanwhile, never dropped. No on-disk format change; no migration. `.held` files
  in the tree are quarantined never-confirmed rows, not corruption.

## Suggested next steps

Only two accepted, documented residuals remain — both deliberately un-addressed now (the knob for
each starves a legitimate case), each ripe only **if ever observed in production**:

- **(a) Two independent streams each taking a guard-passing bogus stamp inside the same hour's
  closing `MAX_TS_AHEAD` window** defeats `k=2`: their clamped witnesses both reach past the
  boundary (the stamps need NOT name the same hour — any stamp far enough ahead clamps to
  `now + MAX_TS_AHEAD`), the next hour confirms up to `MAX_TS_AHEAD` early, and each *stamped*
  stream's live hour publishes truncated by at most the window (its post-stamp tail drops as late;
  unstamped streams finalize on their genuine crossing and lose nothing). This is the corrected
  form of the old "same hour, none lost" claim, which adversarial verification falsified: the loss
  is real but bounded to `MAX_TS_AHEAD` per stamped stream, and it now takes two independent bad
  stamps in one five-minute window — a lone stamp, a burst, or a walk can no longer produce it
  (executed). A higher quorum would starve small `--pairs` runs. Revisit only if two streams are
  ever seen agreeing on a bogus boundary.
- **(b) A clock leading >5 min AND a bogus stamp landing together** truncates by lead-minus-5min. The
  knob — require two DISTINCT requester `ts` before the clock may second — is rejected now because it
  starves lone sparse streams. Revisit only if a leading-clock + bogus-stamp truncation is observed.
