---
status: partial
ripe_when: every cycle record inside the 60-day journal retention carries a journaled `held` — i.e. the retention horizon has passed the deploy of the widening
---

# The cycle record carries `closes` but not the NAV or the position the drift was computed against

## Context — what

Spec `00091` widened `cycle-<HH>.json` with the base-keyed `closes` each cycle used, so realized drift is computable from the journal alone instead of by replaying (a replay was measured at 73 s for one ISO week, which cannot run on the trade path). Two of the three terms that drift needs are now journaled — `final_targets` and `closes`. The other two are not:

- **NAV** is read from live config (`EngineConfig.shadow_nav_eur`) at scoring time, not recorded per cycle.
- **The position** (`held`) is reconstructed by accumulating every journaled fill from the series' first one.

Both were left out deliberately — `closes` alone was what the trip needed to stop replaying — and both were recorded in prose (the spec's D10 residual, an executor comment, and a runbook standing condition) rather than registered. This topic is that registration.

## Why this matters

**The NAV gap is a live spurious-kill vector.** Targets are `weight × nav / close` and drift is `/ nav`, so a `shadow_nav_eur` change while a band is armed makes the next boundary re-score an already-closed, healthy week against the new denominator — halving NAV roughly doubles every reading. Nothing refuses it. The only thing standing against it is one runbook sentence telling the operator to disarm the band across any NAV change and re-arm a week later, and nothing mechanical enforces that sentence. Every other refusal in this component is a guard; this one is a habit.

**The position gap gives the trip a finite life.** Because `held` is cumulative from the first fill ever, and `zcrypto-engine-journal-prune.sh` deletes whole day-dirs at `engine_journal_retention_days: 60`, the trip refuses permanently once the day holding the first fill ages past the horizon — those fills are not on the host and no operator action recovers them. A write-once birth record (`exec/first-fill`) plus a 7-day mint recency bound converts every wrong-birth case into a loud refusal rather than a false kill, so the failure is honest; it is not extended. Journalling the position removes the dependence on fill history altogether and closes the class.

Both were found by construction, not argument: the pruned-head case made spec `00091`'s own healthy fixture read 298.4 bps and latch the kill file, and a lost birth record over a quiet-cut pruned head re-minted a wrong birth and latched again.

## Findings so far

- The widening pattern is established and cheap to repeat: `CycleRecord` in `cli/engine/journal.py` owns the shape, `to_json`/`from_json` carry explicit key lists, `validate_record` is schema-aware, and an absence-tolerant read is what keeps existing artifacts loadable. `closes` went in that way.
- Readers converge before the writer. Old `from_json` constructs from named keys and ignores unknown ones, so an additive widening is safe in both directions — but that is a property of *additive* widenings and should not be read as licence for a non-additive one.
- Any change here re-enters the NAS gate-export's replay closure (`cli/engine/journal.py` and `cli/engine/cycle.py` are both inside it), so the gate-export replays cold at its measured **2490 s**. Size that window against 2490, never the smaller figure.
- `evidence_fingerprint` enumerates its payload explicitly and does not read `closes`; check whether it should read either new field before assuming the same.

## Done so far

**The schema widening landed — `nav` and `held` are journaled on every cycle record.** Additive, in the pattern `closes` established: optional on `CycleRecord`, validated when present, omitted from `to_json` when absent so records predating the keys re-serialize byte-identically (the v1 golden pins that), and read back absence-tolerantly. `nav` is refused unless finite and positive, because it sets both halves of drift; `held` is refused for a pair key, and admits zero and negative because flat and short are real books.

**The NAV gap is CLOSED, and closed the way the owner ruled: each cycle is scored under the NAV it actually priced against.** `CycleStages` carries the journaled value, `_stage` hands it through, and `realized_drift` prefers it per cycle with the caller's scalar as the fallback for older records. So a `shadow_nav_eur` change can no longer re-score a closed week against a denominator nobody traded under, and a week straddling the widening scores each half correctly rather than refusing. The runbook's disarm-across-a-NAV-change sentence is now unnecessary rather than mechanized — the habit is replaced by arithmetic, not by a second guard.

**`held` is journaled but NOT yet read, deliberately.** It comes from the venue read (`VenueState.positions`), narrowed to the model's BASE key space over the /EUR legs — a /BTC leg is dropped rather than folded in, which would double-count that base under two quotes. It is `None` when the venue read failed, because absence is the honest answer where a zeroed book would read as FLAT, a real position.

**`evidence_fingerprint` does NOT cover either field, and that is now pinned by a test.** The fingerprint covers what a REPLAY verdict depends on; these are drift-scoring inputs a replay never reads, exactly as `closes` is. Pinned so a later widening cannot quietly fold them in and invalidate every cached verdict.

**One existing guard had to be narrowed rather than extended.** `test_targets_are_identical_with_and_without_venue_state` — the read-only pin that venue truth is journaled and never consulted — asserted the two cycle artifacts were byte-identical. The record now carries one deliberately venue-derived field, so that assertion could not survive intact. It now asserts the adversarial venue read WAS journaled, then neutralises that one field and compares the rest byte-for-byte through the real serializer: everything the venue must not touch is pinned exactly as before, plus a positive assertion that was not there.

**Deploy cost, unchanged from this topic's warning**: `cli/engine/journal.py` is inside the gate-export replay closure (transitively, via `command.py` from `_REPLAY_ROOTS`), so the NAS gate-export replays cold at the measured **2490 s**. Size the window against 2490.

## Suggested next steps

**What remains is the position half's CONSUMPTION, and it is gated on time rather than on work.**

- Make the trip read the journaled `held` instead of accumulating fills, then retire the birth record, the mint recency bound, and the oldest-boundary refusal — all three exist only to detect a truncated fill history, which a journaled position removes the need for entirely.
- **This cannot be done at the widening, and the reason is the straddle.** A week scored shortly after deploy can span cycles written before it, which carry no `held`; a scorer reading the journaled value for some cycles and accumulating fills for others would mix two position sources inside one week. The change becomes safe only once every record inside the 60-day retention carries the field — that is the `ripe_when`, and it is a clock, not a task.
- Until then the three guards stay live and correct: they convert a truncated fill history into a loud refusal rather than a false kill, which is exactly what is still needed while some cycles have no journaled position.
