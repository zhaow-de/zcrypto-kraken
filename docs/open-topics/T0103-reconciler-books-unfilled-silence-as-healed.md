---
status: partial
ripe_when: the alert-rule leg and the ledger correction are ATTENDED (a Grafana push and a write to the NAS ledger); ripe at the next attended session. The unwitnessed-gap record and the hour-boundary straddle are autonomous and ripe NOW
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

LINK/EUR is the sharpest case: **6 update rows, booked as 209.493793 s healed.** Their spliced block spans 1.638743 s from its single snapshot; the update rows themselves span 0.005246 s across 3 distinct timestamps.

## Why this matters

**The counters that are supposed to tell us whether redundancy is working are the ones that are wrong**, and they fail in the reassuring direction. `zcrypto_reconcile_healed_gap_seconds_total` is the number an operator reads to conclude "the secondary covered it"; for this event it over-stated the repair by 27×.

It also **double-books**. `fleet_dark_windows` (`cli/archive/settle.py`) ends a dark window on any row type, while `secondary_covers` (`cli/archive/reconcile.py`) accepts only `type == "update"`. So the fleet-dark window is a strict subset of every primary gap, and **198.820666 × 11 = 2,187.027326 stream-seconds landed in both** a "we covered it" counter and a "nobody covered it" counter in the same cycle. Both are in stream-seconds, so the overlap is a true double-count, not a units artifact.

**The mechanism is not broken in general — it is broken in exactly one shape.** The 2026-07-17 drill (primary deliberately stopped, secondary genuinely up) healed **99.8444%** for real. It over-claims when *both* mirrors go dark together and the secondary contributes only its post-resubscribe tail. That shape is precisely the one the test suite never constructs.

Bounded blast radius, measured rather than estimated: the ledger's lifetime `healed_seconds` is 17,821.065725 s across exactly two hours, of which **2,228.581124 s (12.5053%) is fictional — all of it this one event**. (An earlier revision of this file said 2,252.718188 s / 12.6408%; that figure reconciled with neither of the two measurements beside it and is superseded by the direct one below, which re-runs the window arithmetic over the minted parquet itself.)

## Findings so far

- **`healed_seconds` measures the input, not the output.** `cli/archive/command.py` computes `healed = sum(gap.seconds for gap in gaps)` — the full *width* of each primary-silence window — before the splice, and never revises it against what the splice actually inserted. The admission gate is only `secondary_covers`, whose own docstring says *"True iff the secondary has at least one **update** row inside `gap`"*: **one row books the whole window.**
- **`residual_seconds` on a minted record is a hardcoded `0.0`**, as is the `residual_gaps=[]` passed to `mint_hour` — which is why every provenance sidecar reads `residual_gaps: []`. On a `both_streams_silent` record it *is* measured.
- **A pair with a real gap and no update witness produces NO ledger record at all.** ADA/EUR's 208.566668 s hole — the largest in the canonical archive for that hour — is invisible to `healable_gap_seconds_total`: the secondary held 200 rows inside the gap, all `type='snapshot'` at a single timestamp, zero updates, so `secondary_covers` was False, `find_book_gaps` returned `[]`, and the `if not gaps: continue` path wrote nothing. **The gap-rate signal is blindest exactly where the damage is worst.** (ADA/EUR also has no reconciled file at all, so `canonical_segments` falls back to the raw primary.)
- **`trade_deficit` records book `residual_seconds: 0.0`** — 18 of the ledger's 47 records; suspected at the time to be the symmetric defect for trades. **Enumerated since, and it is not one**: every one of the 18 is a *secondary* deficit (`trades_added = 0` in all 18, 1,926 secondary rows in total across 2026-07-14T18/19, 07-17T16 and 07-23T19/20), so the canonical stream lost nothing and the `0.0` is correct. See *Done so far*.
- **The residual counter under-states too, and separately.** This event's residual was booked as the intersection window × stream count (2,385.847992 s) rather than each pair's own hole, under-stating the measured per-pair loss by **51.300205 s**. Mostly closed — a healed hour now books its own unfilled remainder on top of the fleet share, leaving 9.746002 s unbooked, all of it ADA/EUR's (see *Done so far*). **The same intersection-vs-own-window shortfall measures 34.243169 s on the 2026-07-13 event** and is the live decision under *Suggested next steps*. An earlier revision attributed that one to an hour-boundary straddle; re-measurement refuted it — the straddle is 28 ms across the whole event.
- **A minor predicate asymmetry that did not bite here** (fixed — see *Done so far*): `fleet_dark_windows` kept windows `>= min_seconds` while `find_book_gaps` requires strictly `> min_gap_seconds`, so a window of exactly 30.0 s was residual-booked and never heal-considered.
- **Every minted file now carries TWO snapshots** ~7 s apart (the spliced secondary one and the primary's own resubscribe). Measured on `BTC/EUR` hour 07: 07:04:27.350301 and 07:04:34.576215; the raw primary has one. Consumers that reset the book on every snapshot row discard whatever the splice inserted — so for such a consumer the effective heal of this event is ≈0 s. Whether that is a defect here or in the consumer is undecided; see [[T0104]].
- Provenance sidecars (`*.provenance.json`) record the blocks actually spliced and are the cheapest assertion surface for a fix: `healed_seconds` vs `sum(secondary block spans)` is a **pure file assertion over data already on disk**, needing no replay harness.

## Done so far

**The counters now measure the splice** — `cli/archive/{reconcile,command,mint,settle}.py`, commit `1da2ea52`. `measure_residual` re-runs the window arithmetic over the frame actually minted; `healed_seconds` becomes claimed − unfilled; the unfilled remainder reaches the provenance sidecar as real `residual_gaps` instead of a literal `[]`; the new `claimed_seconds` field keeps `healable_gap_seconds_total` — the degrading-primary *rate* — denominated in primary silence, because a correlated outage is not the primary degrading. `fleet_dark_windows`'s `>= min_seconds` became `> min_seconds`, so the two silence predicates agree and a window of exactly 30.0 s can no longer be residual-booked while never being heal-considered.

**The double count is gone in both directions, and neither side recomputes.** Each side subtracts what the *ledger records* the other already booked (`overlap_seconds`): a per-pair record subtracts the ledgered `both_streams_silent` windows for its own stream, and that fleet record in turn subtracts whatever a stream's own book record already booked. Subtracting a *fresh recomputation* instead was measured wrong in both directions — a pair whose mirrors land after the fleet decision was never given a share of it (its whole loss vanished), and an unreadable segment suppresses the detector for a cycle, so a pair minting meanwhile books first and the fleet record would book the same seconds again. `residual_seconds` also joined the per-(pair, kind, hour) dedup `healable` already rode: an hour ledgered `would_mint` and then `minted` carries the same measured residual twice, and the second step reads to the CRITICAL page as a fresh permanent-loss event.

**Validated on a known answer before its verdicts were read.** Re-run over the real ledger and the minted parquet on the NAS (read-only):

| hour | claimed | measured healed | fiction |
| --- | --- | --- | --- |
| 2026-07-17T15:00 (the drill — primary deliberately stopped, secondary genuinely up) | 15,509.529138 s | **15,509.529138 s** | **0.000000 s (0.0000%)** |
| 2026-07-27T07:00 (the blackout) | 2,311.536587 s | **82.955463 s** | 2,228.581124 s (96.4112%) |

The drill hour is not slandered by the stricter measure — the guard against "correcting" a genuine heal into a phantom. And the blackout's 82.955463 s reproduces this file's independently derived figure *to the microsecond* by a different method (that one compared the canonical hole against the primary hole; this one re-runs the arithmetic over the minted rows), which is why the fiction figure above is the one that changed rather than this one.

**The `trade_deficit` residual is not a defect — measured, then dropped.** All 18 records enumerated from the ledger: **every one is a SECONDARY deficit, `trades_added = 0` in all 18**, 1,926 secondary rows missing in total (2026-07-14T18/19, 07-17T16, 07-23T19/20). The canonical trade stream lost nothing, so `residual_seconds: 0.0` on those records is correct rather than a symmetric blind spot. Permanent *trade* loss cannot appear in a `trade_deficit` record at all: rows absent from both mirrors are invisible to a cross-host union, and `zcrypto archive backfill-trades` already measures them as `unrecoverable`. Consciously dropped, with the measurement as the reason.

**What the corrected counters would book for the blackout hour**, per the code as landed: 82.955463 s healed, and 41.553798 s of per-pair residual on top of the fleet record's existing 2,385.847992 s — 2,427.401790 s of the measured 2,437.147792 s permanent loss. The 9.746002 s shortfall is ADA/EUR's, and it is exactly the unwitnessed-gap sub-item below: that pair has no ledger record to carry its own remainder, so only its 198.820666 s share of the fleet window is booked.

## Suggested next steps

The landed work sits on the pushed branch **`feat/t0101-remediation`** (no PR — the component's *tail* is attended; the two `(autonomous)` items below are ripe now and belong on a fresh branch).

- *(decision)* **The fleet intersection under-books every stream except the binding one — and the cross-hour mechanism this item used to claim is not the cause.** Re-measured 2026-07-28 from the raw mirrors, hours 06 and 07 of 2026-07-13, all 10 pairs:

  | quantity | measured |
  | --- | --- |
  | fleet intersection inside hour 07 | **266.178874 s** (07:00:00 → 07:04:26.178874) × 10 streams = **2,661.788740 s**, matching the ledger exactly |
  | sum of each pair's OWN dual-silence | **2,696.031909 s** |
  | unbooked cross-hour head | **0.002794 s per stream** |

  An earlier revision of this file asserted a 2,697.235577 s "true" total and blamed `fleet_dark_windows` clamping to `hour_start` for the ~35 s difference. **Both halves are wrong.** The latest stamp anywhere in hour 06 is 06:59:59.997206, so the straddle costs **28 milliseconds across the whole event**, and the quoted total does not reproduce (2,696.031909 s measured).

  The real gap: `both_streams_silent` books the **intersection** — the window in which *every* stream on *both* hosts was silent — times the stream count. LTC/EUR's own dark window is exactly 266.178874 s: it is the binding pair, last to go quiet and first to return. The other nine were each dark ~4 s longer, and that surplus is booked nowhere. Under-count for this event: **34.243169 s (1.27%)**.

  The decision, because it moves what the loss counter means for a third time: keep the intersection as the *discriminator* that says "this is an outage, not a thin market" — that is the whole reason it exists — but once an outage is established, book **each stream's own dark window** instead of the intersection × N.

- *(autonomous, a rider)* **Cross-hour silence, the residual after the above.** `fleet_dark_windows` clamps to `hour_start`, so a straddling head is measured from the boundary rather than from the last stamp of the previous hour. Bounded above by `min_gap_seconds` per stream — a straddle wider than the threshold is already booked by the previous hour's own tail window — and measured at 0.002794 s per stream on the 2026-07-13 event. Not worth its own change; fold it into whatever lands above.
- *(autonomous)* **Write a record for an unwitnessed gap** (state `unwitnessed`, or `would_mint` with residual set) so a pair like ADA/EUR stops being invisible. Test: replay the real 2026-07-27T07:00 hour into a **scratch** overlay root — never `/mnt/zhao-crypto/capture-reconciled`, never a live capture dir — and assert **12** book records, not 11, with ADA/EUR's residual = 208.566668.
- *(decision — ATTENDED, a write to the NAS ledger)* **The 2,228.581124 s of existing fiction.** The ledger is append-only and `_totals` re-derives every counter from the whole of it each cycle, so *any* record that lowers `healed_gap_seconds_total` is a counter DECREASE — which Prometheus reads as a reset, making `increase()` over the containing window report the post-reset value as fresh healing. That is louder than the fiction it corrects. The proposed shape is therefore an appended **note record carrying no counter field** (`state: "correction"`, the measured 82.955463 s, and the reason), which `_totals` ignores by construction: the ledger reads true, the series stays continuous, and the counter's documented over-statement is bounded at 2,228.581124 s of 17,821.065725 for hours before commit `1da2ea52`. The append itself is attended — the ledger lives on the NAS, and the mount is read-only from here.

### The alert inversion — observed live, 2026-07-27

**The misleading alert is louder and more persistent than the true one, and that inversion is worse than either defect alone.** Read off the Slack channel and Grafana's own rule state, not inferred:

| rule | duration | truth |
| --- | --- | --- |
| *Reconciler · residual gap increased* (**critical**) | fired 09:18:35Z, **false-resolved 10:18Z** via `grafana_state_reason = MissingSeries` — 60 min | **correct**: 2,437 s permanently gone |
| *Reconciler · primary gap rate high* (**warning**) | active since 09:48:00Z, re-notified 4× (11:48 / 15:49 / 19:50 / 23:53 CEST), **still firing 24 h later** | its summary says *"Every gap was covered"* — **false**; only 82.96 s was really healed |

So the alert that got the facts right went quiet after an hour, while the one asserting the fiction has re-notified four times and continues until the 24 h window rolls past the ledger append (~09:12Z). Its `A` value is pinned at **2313.14** across all four notifications. That is the fictional healed figure this topic exists to correct, paged repeatedly as though it were reassurance — and it does not equal the ledger's **2,311.536587 s** exactly because `increase()` extrapolates a counter step to its window edges (the same arithmetic that returns ~1.0007 for a single increment, recorded under [[T0008]]'s alert leg). The ~1.6 s difference is the extrapolation, not a second event.

This is live evidence rather than analysis, and it raises the ranking: fixing the counters (above) also fixes what the warning *says*, and the `increase(...[1h])` window (below) is what silenced the page that was right.

### The two alert rules that read these counters

Folded in 2026-07-27 rather than left as prose in spec `00073`'s *Out of scope*, which claimed they were "registered" when no topic named them — the exact drift `open-topics.md` forbids. They belong here because both are defects **in the surfacing of the counters this topic fixes**; re-deriving either number before the counters mean what they say would be fitting a threshold to a known-wrong signal.

- *(decision — ATTENDED, a Grafana push)* **`zcrypto-reconcile-residual-gap`'s summary is now stale.** It tells whoever it pages to *"Check the reconcile ledger for the `both_streams_silent` / `total_loss` records behind it"*, and since commit `1da2ea52` the page can be driven entirely by a per-pair `minted` / `would_mint` residual with no such record present — the operator follows the instruction and finds nothing. Reword with the same push as the two below.
- *(decision — ATTENDED, a Grafana push)* **`zcrypto-reconcile-healable-gap-rate` is denominated in pair-seconds while its operator summary claims minutes.** `params: [600]` against a counter summed across streams: at 12 pairs that is **~50 wall-clock seconds**, not the "more than 10 minutes" the summary tells whoever it pages — and the effective threshold **tightens every time a pair is added**, silently, because the denominator grew. Fix the unit (divide by live pair count, or restate the summary honestly in pair-seconds) and repoint the stale `T0039 recalibrates it` comment. A test asserting the summary's stated quantity and the evaluator's unit agree is the durable guard; `tests/test_internal_terms_not_operator_visible.py` is the precedent for enforcing operator-facing text mechanically.
- *(decision — ATTENDED, a Grafana push)* **`zcrypto-reconcile-residual-gap` — the CRITICAL permanent-loss page — presents as resolved after 60 minutes.** It fires on `increase(...[1h])` over a 1 h relative range, so the highest-severity signal the system has for a *permanent, unbackfillable* condition self-resolves to `MissingSeries` an hour later. That is very likely why [[T0101]] was written without it, despite it having paged Slack at 09:18:35Z. Add a durable surface on the counter's **level** rather than its increase, leaving the existing step-detector alone; validate by replaying the rule against the real counter series spanning that step and confirming the new signal does not go Normal at +60 min.
- *(autonomous, but blocked on history)* **Do NOT re-derive the healable-gap threshold's number yet.** The measured history contains only `0` and `≥2311` — the counter series begins 2026-07-14 and holds ~12.6 days, of which ~10 are post-drill steady state. Any re-derivation now would be intuition wearing a table. Re-register the number itself with a `ripe_when` on accumulated steady-state history once the counters are trustworthy.
