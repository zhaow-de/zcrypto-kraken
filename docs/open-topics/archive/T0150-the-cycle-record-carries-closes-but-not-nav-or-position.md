---
status: resolved
---

# The cycle record carries `closes` but not the NAV or the position the drift was computed against

## Context — what

Spec `00091` widened `cycle-<HH>.json` with the base-keyed `closes` each cycle used, so realized drift is computable from the journal alone instead of by replaying (a replay was measured at 73 s for one ISO week, which cannot run on the trade path). Two of the three terms that drift needs are now journaled — `final_targets` and `closes`. The other two are not:

- **NAV** is read from live config (`EngineConfig.shadow_nav_eur`) at scoring time, not recorded per cycle.
- **The position** (`held`) is reconstructed by accumulating every journaled fill from the series' first one.

Both were left out deliberately — `closes` alone was what the trip needed to stop replaying — and both were recorded in prose (the spec's D10 residual, an executor comment, and a runbook standing condition) rather than registered. This topic is that registration.

## Why this matters

**The NAV gap is a live spurious-kill vector.** Targets are `weight × nav / close` and drift is `/ nav`, so a `shadow_nav_eur` change while a band is armed makes the next boundary re-score an already-closed, healthy week against the new denominator — halving NAV roughly doubles every reading. Nothing refuses it. The only thing standing against it is one runbook sentence telling the operator to disarm the band across any NAV change and re-arm a week later, and nothing mechanical enforces that sentence. Every other refusal in this component is a guard; this one is a habit.

**The position gap gives the trip a finite life.** Because `held` is cumulative from the series' birth, starting from the opening holdings recorded with it, and `zcrypto-engine-journal-prune.sh` deletes whole day-dirs at `engine_journal_retention_days: 60`, the trip refuses permanently once the day holding the birth's boundary ages past the horizon — the fills since it are no longer all on the host and no operator action recovers them. A write-once birth record (`exec/first-fill`) plus a 7-day mint recency bound converts every wrong-birth case into a loud refusal rather than a false kill, so the failure is honest; it is not extended. Journalling the position removes the dependence on fill history altogether and closes the class.

Both were found by construction, not argument: the pruned-head case made spec `00091`'s own healthy fixture read 298.4 bps and latch the kill file, and a lost birth record over a quiet-cut pruned head re-minted a wrong birth and latched again.

## Findings so far

- The widening pattern is established and cheap to repeat: `CycleRecord` in `cli/engine/journal.py` owns the shape, `to_json`/`from_json` carry explicit key lists, `validate_record` is schema-aware, and an absence-tolerant read is what keeps existing artifacts loadable. `closes` went in that way.
- Readers converge before the writer. Old `from_json` constructs from named keys and ignores unknown ones, so an additive widening is safe in both directions — but that is a property of *additive* widenings and should not be read as licence for a non-additive one.
- Any change here re-enters the NAS gate-export's replay closure (`cli/engine/journal.py` and `cli/engine/cycle.py` are both inside it), so the gate-export replays cold. Size that window as `docs/reference/fleet-pins.md`'s standing constraint reads it, from the live series, never an older cold figure from a smaller journal.
- `evidence_fingerprint` enumerates its payload explicitly and does not read `closes`; check whether it should read either new field before assuming the same.

## Resolution

**The schema widening landed — `nav` and `held` are journaled on every cycle record.** Additive, in the pattern `closes` established: optional on `CycleRecord`, validated when present, omitted from `to_json` when absent so records predating the keys re-serialize byte-identically (the v1 golden pins that), and read back absence-tolerantly. `nav` is refused unless finite and positive, because it sets both halves of drift; `held` is refused for a pair key, and admits zero and negative because flat and short are real books.

**The NAV gap is closed IN CODE on both consuming surfaces: each cycle is scored under the NAV it actually priced against.** `CycleStages` carries the journaled value and `realized_drift` prefers it per cycle, with the caller's scalar as the fallback for records written before the field existed. Both producers of `CycleStages` hand it through — `executor._stage` on the engine's trip path and `feeders.replay_stages` on the `tracking-report` path. That pairing is the point, not an implementation detail: the report is where the band is re-derived and the trip is armed against that band, so a fix to one surface alone would have left the human banding at one NAV while the engine tripped at another. The first attempt did exactly that and was caught in review. A week straddling the widening now scores each half correctly rather than refusing.

**What is NOT yet true is the deployed behaviour, and the runbook says so on purpose.** `infra/runbooks/engine.md` still requires the band disarmed across any `shadow_nav_eur` change, and that instruction stays REQUIRED until the engine converges onto this code — an operator reading a re-trued runbook against the running image would skip a disarm that is still owed. Re-truing it is registered below as a deploy-time step, together with the stale clause in the same runbook line that calls the journaling "the next schema widening".

**One asymmetry inside the weekly report is deliberate and is NOT a gap.** `weekly_tracking` scores its realized half per journaled cycle, but its FLOOR half (`accumulation_payload`) stays on the caller's live scalar. The two answer different questions: realized drift asks "what did this closed week actually cost against the NAV it traded under", a past-tense question that must not be re-denominated; the floor asks "what is unavoidable at the size I run TODAY", a present-tense question whose whole point is a constant NAV across the window. Re-denominating the floor per cycle would make it a different measurement, not a more accurate one. The consequence to remember after a NAV change: every week in the report window that CLOSED under the old value carries a numerator at that old journaled NAV against a floor at the new scalar, so the whole pre-change stretch reads advisory until it ages out of the window — not merely the week the change fell in. `--simulated-fills` inherits the same seam — its fills are built at the scalar and scored per cycle — which makes it a diagnostic, not evidence, across such a change.

**`held` is journaled but NOT yet read, deliberately.** It comes from the venue read (`VenueState.positions`), narrowed to the model's BASE key space over the /EUR legs — a /BTC leg is dropped rather than folded in, which would double-count that base under two quotes. It is `None` when the venue read failed, because absence is the honest answer where a zeroed book would read as FLAT, a real position.

**`evidence_fingerprint` does NOT cover either field, and that is now pinned by a test.** The fingerprint covers what a REPLAY verdict depends on; these are drift-scoring inputs a replay never reads, exactly as `closes` is. Pinned so a later widening cannot quietly fold them in and invalidate every cached verdict.

**One existing guard had to be narrowed rather than extended.** `test_targets_are_identical_with_and_without_venue_state` — the read-only pin that venue truth is journaled and never consulted — asserted the two cycle artifacts were byte-identical. The record now carries one deliberately venue-derived field, so that assertion could not survive intact. It now asserts the adversarial venue read WAS journaled, then neutralises that one field and compares the rest byte-for-byte through the real serializer: everything the venue must not touch is pinned exactly as before, plus a positive assertion that was not there.

**Deploy cost, unchanged from this topic's warning**: `cli/engine/journal.py` is inside the gate-export replay closure (transitively, via `command.py` from `_REPLAY_ROOTS`), so the NAS gate-export replays cold. Size the window as `docs/reference/fleet-pins.md`'s standing constraint reads it, from the live series.

**The position half is consumed — the trip and the weekly report score each cycle from the journaled book** (`feat/t0150-held-consumption`, on the owner's rulings of 2026-10-27, recorded in `docs/research/14.phase6-decisions.md`): cycle B is scored against the book journaled at B+4h, the venue read after B's plan has ended (a668f7d15); a cycle whose next boundary journals `held=None` refuses the week, naming the boundary, never a kill; the `first-fill` birth record, the 7-day mint window and the oldest-boundary refusal retired with the fill accumulation they guarded (6b8d91f27); the series' start is an operator-written `exec/series-start`, read only for the start-week refusal — written at entry, rewritten to the next boundary after any attended act on the book, so a flatten's week is never scored (0fce5bd73); `engine-procedures.md` and drill B rewritten to it (418ce9489, 76b4ff84f). The clock had run: every cycle record in the engine host's 60-day retention carried `held` and `nav`, none `None`, read 2026-10-27. The running image already scored per-cycle NAV and `engine.md` carried no NAV-disarm bullet, so nothing was owed there. The deployment is the engine's next image, the fleet's concern: `executor.py`, `tracking.py`, `feeders.py` and `command.py` are in the NAS gate-export replay closure, so that deploy replays the gate export cold.
