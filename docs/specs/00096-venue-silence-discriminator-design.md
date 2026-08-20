# 00096 — venue silence vs capture loss: a triage discriminator for the residual-gap counter

Resolves [[T0143]]. Read-only with respect to the ledger: **nothing here changes what `zcrypto_reconcile_residual_gap_seconds_total` books, by how much, or when.** What changes is that the reconciler says *why* it believes the fleet went dark, and the operator woken by the highest-severity rule in the system has that reason in hand instead of having to derive it at 3am.

## Context — a venue outage is indelibly recorded as permanent capture loss

On 2026-08-20 Kraken's book feed emitted essentially nothing between 07:01:04Z and 07:10:14Z across all twelve streams. At the 09:12Z reconcile tick the ledger booked it exactly as designed: `residual_gap` moved 15636.019483 → 21887.369457 (**+6251.35 s**, 520.9 s per stream), state `both_streams_silent`, with `healable_gap` unmoved. Correct by the counter's definition, and wrong as a description of what happened — no data was lost, because there was no data to lose.

Two harms follow, and they compound:

- **The alert teaches the wrong lesson.** `Reconciler · residual gap increased (permanent loss)` is `severity: critical` and fires on any increase at all (`> 0`, deliberately no tolerance). A venue outage that pages it at top severity trains the operator to discount the one alert that must never be discounted — the same [[T0135]] failure mode `00089` D2 was written to avoid, arriving from the opposite direction.
- **The denominator is corrupted.** `continuity.py` over 2026-08-20 reports a 1.88 % gap and FAILS its <0.1 % exit bar entirely on this window. A later reader comparing day-over-day continuity sees a capture regression that did not happen.

The counter is monotonic and derived by summing an append-only ledger, so the 6251.35 s can never be walked back — only explained.

## The load-bearing measurement, and why the obvious signal fails

**Kraken's status page reported no incident.** The candidate signal T0143 offered first — a `SystemStatus` read, the same public endpoint `00088`'s execution gate already consumes — would therefore have booked 2026-08-20 identically. It is refuted by the only event we have. Brief venue degradations routinely go unposted, so this is a property of the source, not bad luck on one sample.

The discriminator that *did* work is cross-host agreement: the primary and the secondary, independent hosts on separate networks and processes, recorded the same sparse events with **microsecond-identical timestamps** (`07:01:04.553253` → `07:08:01.113758` on BTC/EUR on both).

That agreement is sound rather than coincidental, and the reason is verifiable in the capture writer: `cli/capture/command.py` sets `ts = _parse_ts(entry["timestamp"])` — **Kraken's own message timestamp, carried in the payload, never local receipt time.** Two hosts that receive the same message therefore record byte-identical `ts` by construction, and a host that was not receiving cannot manufacture one.

## Decisions

**D1 — `residual_gap_seconds_total` books ABSENCE of data, not FAULT attribution. That is now the ruling, not an accident of implementation.** The counter's contract is "no book data exists for this window on either mirror, and no later cycle can heal it." That statement was true on 2026-08-20 and stays true. Attribution is a separate question with a separate, weaker evidence base, and fusing the two would make a monotonic fail-closed ledger depend on an inference. Recorded here so the booking is never later "corrected" by someone reading the counter's `permanent loss` label as a fault claim.

**D2 — the booking block gains a three-valued verdict, computed from evidence it already holds.** A booked `both_streams_silent` window contains zero events *by construction* — `fleet_dark_windows` runs over the union of both mirrors across all pairs — so the evidence cannot come from inside a window. It comes from the **interior span**: the events falling *between* adjacent booked windows of the same hour, which exist precisely because some stream ticked there. That is what 2026-08-20 produced (one lone book update mid-episode, on both hosts).

Per pair, compare the two mirrors' `ts` multisets over the interior span:

| Interior evidence | Verdict | What it establishes |
| --- | --- | --- |
| Non-empty, mirrors **equal** | `venue_silent` | Both hosts were connected and receiving the same venue messages *during* the episode — the silence was upstream |
| Non-empty, mirrors **differ** | `capture_divergent` | One host missed what the other received — a capture-side finding in its own right |
| Empty | `undetermined` | No interior evidence exists; the case cannot be distinguished |

**D3 — `undetermined` is the default, and bracketing events never promote to `venue_silent`.** Agreement on the events immediately *before* and *after* the episode proves only that both hosts were healthy before and after it — a simultaneous both-host outage that self-healed produces exactly that signature. Accepting brackets would label a real, correlated capture failure `venue_silent`, which is the one direction this design must not fail in. Only interior evidence counts.

**D4 — no ledger field, no new counter, no schema change.** The verdict is computed at booking time and written to the existing `logger.error("archive reconcile: both_streams_silent …")` line, alongside the window count and residual seconds it already carries. Consequences, all deliberate: the reconcile ledger's record format is untouched, so `capture-deploys.md`'s **readers-before-writer** converge ordering is not triggered; no series joins the active-series budget, so no Alloy keep-list edit and no admitted-metrics rule is owed; and `gate_cache.py`'s replay fingerprint is untouched — `cli/archive/command.py` is measured absent from the 74-file transitive `cli.*` replay closure, so no NAS converge pays the cold gate-export replay.

The upgrade path is left open and explicitly *not* taken now: if a second episode books and the verdict proves out on a second independent sample, promoting it to a ledger field and a `venue_silent` counter is additive and can be specified then. Building the counter on one sample would be speculative, and a wrong classifier baked into an append-only ledger is not walk-backable.

**D5 — the alert gains a triage line naming the discriminator.** `zcrypto-reconcile-residual-gap`'s `summary` currently sends the operator to the ledger for the *state* behind the increase. It gains the next step: check the reconcile log's verdict for that hour, and the discriminator itself — two independent hosts recording identical venue timestamps across the window means the silence was upstream. The rule's `expr`, threshold, `for`, severity, and uid are unchanged, so this is an upsert of annotation text with **no prune owed** and no superseded uid. Per `capture-deploys.md`'s alert-rule lifecycle the push still happens after the converge, and the rule is verified evaluating by value rather than merely stored.

The summary is operator-facing text read on a phone with nothing open, so it carries no `T<NNNN>`, spec serial, or phase token — `operator-facing-text.md`, enforced by `tests/test_internal_terms_not_operator_visible.py`.

**D6 — the 2026-08-20 event is annotated where its numbers are quoted, not corrected.** The counter is monotonic; the 6251.35 s stands forever. `docs/reference/` gains the explanation wherever that day's continuity figure can be read, so a future reader comparing day-over-day continuity is not misled into diagnosing a capture regression. The narrative is written in place rather than appended as a retraction (`agent-ops.md`), and the per-event evidence — the timestamps, the counter values, the tick that booked it — belongs to the updating commit's message, not the living doc (`docs-style.md`).

## Verification

- **The guard is unproven until the defect trips it** (`agent-ops.md`), so each verdict is constructed from synthetic two-mirror frames: equal interior multisets → `venue_silent`; a single event dropped from one mirror → `capture_divergent`; an episode with no interior events → `undetermined`.
- **A true-positive is mandatory**: a production-shaped healthy hour — no fleet-dark window at all — must book nothing and emit no verdict, so an always-classifying implementation cannot ship green.
- **The booking is pinned as unchanged**, and this is the load-bearing regression test: for an input that books `both_streams_silent` today, `residual_seconds` and the ledger record must be byte-identical with the verdict present. D1 is a claim about behaviour, so it gets a test, not a sentence.
- **Replayed against the real 2026-08-20 hour-07 data** on a pulled copy (never the live capture dir), the verdict must read `venue_silent` and the booked seconds must reproduce 6251.35 s at full precision — the number is reproduced from source, not quoted from the topic (`agent-ops.md`).
- The alert's post-push verification reads the rule **evaluating**, by value.

## What this does NOT do — bounded claims

- It does not make the counter able to distinguish venue silence from capture loss. It makes the *reconciler* able to say which it believes, for the subset of episodes carrying interior evidence, and leaves the counter's contract exactly as it was.
- It does not classify an episode with no interior events. Such an episode reads `undetermined` and pages exactly as it does today — by design, per D3.
- It does not change alert severity, threshold, or firing behaviour. A venue outage will still page `critical`; what changes is that the page's triage path is one log line away instead of a derivation.
- It does not retroactively alter the 6251.35 s already booked, or `continuity.py`'s 2026-08-20 verdict. Both are explained (D6), never corrected.

## Out of scope

- A `venue_silent` counter and its ledger field — D4's deliberate upgrade path, gated on a second independent sample.
- Any venue-status input to the reconciler — refuted for this purpose by the 2026-08-20 measurement, and re-opening it needs a source that demonstrably reports brief degradations.
- `continuity.py`'s exit-bar arithmetic — and **not** because the classification is missing. It takes a single positional capture `root` and never reads the reconcile ledger, so no ledger field or counter this spec could build would be visible to it, and with one mirror the cross-host discriminator is unavailable in principle. More decisively, spec `00050` deliberately isolates the exit-bar report from any second source that heals gaps — its own docstring: an overlay "would otherwise let a raw-capture regression bank a 'clean' run -- exactly the defect class the bar exists to catch". A venue-fault verdict is structurally that same move, so feeding one in is refused by design rather than deferred. The 2026-08-20 FAIL is explained (D6), never subtracted. Stakes are bounded: T0003's bar was met and resolved 2026-07-16, so what this instrument gates today is the post-deploy truncated-hours check, which this window does not touch.
