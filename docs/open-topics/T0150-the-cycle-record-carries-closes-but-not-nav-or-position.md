---
status: open
ripe_when: either a tracking band is about to be armed, or the engine's first fill approaches the 60-day journal retention.
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

## Suggested next steps

- Decide whether NAV is journaled per cycle or whether the trip should refuse when the live `shadow_nav_eur` differs from the one the scored week was computed under — the second is cheaper and closes the same hole, but needs somewhere to have recorded the old value, which is the first.
- Journal the position beside `closes`, and make the trip read it instead of accumulating fills. Then retire the birth record, the mint recency bound, and the oldest-boundary refusal — all three exist only to detect a truncated fill history.
- Re-check whether `evidence_fingerprint` should cover either field.
- Both land as one schema widening if taken together, which is one converge and one 2490 s NAS window instead of two.
