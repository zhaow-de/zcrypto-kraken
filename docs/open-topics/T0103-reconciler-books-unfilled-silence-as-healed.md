---
status: open
ripe_when: NOW — every input is measured and on disk (the ledger, the parquet, and the provenance sidecars); nothing waits on an observation. The only sequencing constraint is that it is a different producer from [[T0101]] and therefore its own component
---

# The reconciler books unfilled silence as healed, and double-counts it as permanent loss

## Context — what

Split out of [[T0101]] on 2026-07-27. Measuring the 2026-07-27 07:00 UTC capture blackout against the parquet — rather than against the reconciler's own ledger — found four defects in `cli/archive`, all in the same direction: the reconciler over-states what it repaired and under-states what was lost.

For that one hour the ledger claims **2,311.536587 s healed** across 11 pairs, each record carrying `residual_seconds: 0.0`. Measured from the files:

| quantity | value |
| --- | --- |
| claimed `healed_seconds` | 2,311.536587 s |
| **actually healed** (canonical hole vs primary hole) | **82.955463 s** — 3.59% |
| secondary rows spliced in | 2,434, of which **2,200 are eleven 200-row single-timestamp snapshots** |
| genuine `update` rows justifying the claim | **234** |
| total span of the spliced secondary blocks | 69.997211 s |
| L2 permanently absent from the canonical archive | **2,437.147792 s** across 12 pairs |

LINK/EUR is the sharpest case: **6 update rows spanning 1.638743 s, booked as 209.493793 s healed.**

## Why this matters

**The counters that are supposed to tell us whether redundancy is working are the ones that are wrong**, and they fail in the reassuring direction. `zcrypto_reconcile_healed_gap_seconds_total` is the number an operator reads to conclude "the secondary covered it"; for this event it over-stated the repair by 27×.

It also **double-books**. `fleet_dark_windows` (`cli/archive/settle.py`) ends a dark window on any row type, while `secondary_covers` (`cli/archive/reconcile.py`) accepts only `type == "update"`. So the fleet-dark window is a strict subset of every primary gap, and **198.820666 × 11 = 2,187.027326 stream-seconds landed in both** a "we covered it" counter and a "nobody covered it" counter in the same cycle. Both are in stream-seconds, so the overlap is a true double-count, not a units artifact.

**The mechanism is not broken in general — it is broken in exactly one shape.** The 2026-07-17 drill (primary deliberately stopped, secondary genuinely up) healed **99.8444%** for real. It over-claims when *both* mirrors go dark together and the secondary contributes only its post-resubscribe tail. That shape is precisely the one the test suite never constructs.

Bounded blast radius, measured rather than estimated: the ledger's lifetime `healed_seconds` is 17,821.065725 s across exactly two hours, of which **2,252.718188 s (12.6408%) is fictional — all of it this one event**.

## Findings so far

- **`healed_seconds` measures the input, not the output.** `cli/archive/command.py` computes `healed = sum(gap.seconds for gap in gaps)` — the full *width* of each primary-silence window — before the splice, and never revises it against what the splice actually inserted. The admission gate is only `secondary_covers`, whose own docstring says *"True iff the secondary has at least one **update** row inside `gap`"*: **one row books the whole window.**
- **`residual_seconds` on a minted record is a hardcoded `0.0`**, as is the `residual_gaps=[]` passed to `mint_hour` — which is why every provenance sidecar reads `residual_gaps: []`. On a `both_streams_silent` record it *is* measured.
- **A pair with a real gap and no update witness produces NO ledger record at all.** ADA/EUR's 208.566668 s hole — the largest in the canonical archive for that hour — is invisible to `healable_gap_seconds_total`: the secondary held 200 rows inside the gap, all `type='snapshot'` at a single timestamp, zero updates, so `secondary_covers` was False, `find_book_gaps` returned `[]`, and the `if not gaps: continue` path wrote nothing. **The gap-rate signal is blindest exactly where the damage is worst.** (ADA/EUR also has no reconciled file at all, so `canonical_segments` falls back to the raw primary.)
- **`trade_deficit` records book `residual_seconds: 0.0`** — 18 of the ledger's 47 records. Permanent *trade* loss is structurally invisible in the loss counter, the symmetric defect for the other kind. Affected hours: 2026-07-14T18/19 (10 pairs), 07-17T16 (6), 07-23T19/20 (2). Their actual deficits have not been enumerated.
- **The residual counter under-states too, and separately.** This event's residual is booked as the intersection window × stream count (2,385.847992 s) rather than each pair's own hole, under-stating the measured per-pair loss by **51.300205 s**. And for the 2026-07-13 event the true per-pair total is **2,697.235577 s** against a booked 2,661.788740 s — a different mechanism: `fleet_dark_windows` clamps to `hour_start`, but that silence began at 06:59:59.69–06:59:59.99, **inside the previous hour**.
- **A minor predicate asymmetry that did not bite here**: `fleet_dark_windows` keeps windows `>= min_seconds` while `find_book_gaps` requires strictly `> min_gap_seconds`, so a window of exactly 30.0 s is residual-booked and never heal-considered.
- **Every minted file now carries TWO snapshots** ~7 s apart (the spliced secondary one and the primary's own resubscribe). Measured on `BTC/EUR` hour 07: 07:04:27.350301 and 07:04:34.576215; the raw primary has one. Consumers that reset the book on every snapshot row discard whatever the splice inserted — so for such a consumer the effective heal of this event is ≈0 s. Whether that is a defect here or in the consumer is undecided; see [[T0104]].
- Provenance sidecars (`*.provenance.json`) record the blocks actually spliced and are the cheapest assertion surface for a fix: `healed_seconds` vs `sum(secondary block spans)` is a **pure file assertion over data already on disk**, needing no replay harness.

## Suggested next steps

- **Measure the output, not the input.** After the splice, re-measure the minted frame's remaining holes above `min_gap_seconds` and write them as `residual_gaps` / `residual_seconds`; set `healed_seconds` to claimed − residual. Validate with (a) a unit test in the production shape — a primary gap strictly containing a secondary dark window, secondary contributing only a post-resubscribe tail — that **fails on today's code first**, or it proves nothing; and (b) a sidecar assertion over the existing 2026-07-27 files.
- **Make the two silence predicates agree**, so `healed + residual` can never exceed window width × stream count. Add the hour-boundary-straddling case (the 07-13 mechanism) and align `>= min_seconds` with `> min_gap_seconds`.
- **Write a record for an unwitnessed gap** (state `unwitnessed`, or `would_mint` with residual set) so a pair like ADA/EUR stops being invisible. Test: replay the real 2026-07-27T07:00 hour into a **scratch** overlay root — never `/mnt/zhao-crypto/capture-reconciled`, never a live capture dir — and assert **12** book records, not 11, with ADA/EUR's residual = 208.566668.
- **Enumerate the 18 `trade_deficit` records' actual deficits** and decide whether trades loss belongs in the residual counter.
- **Decide explicitly what to do about the 2,252.718188 s of existing fiction.** The ledger is append-only, so either leave it with a written note or correct it by an appended record — but a fix that silently leaves the counter wrong is not done, and a correction reads to Prometheus as a counter reset (see [[T0044]]).
