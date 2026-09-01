# 00109 — the past-dated detector counts a benign restart, and its alert cannot see it either way

Spec `00103` D5 ruled the shape of [[T0037]]'s past-dated-hour detector. This spec **supersedes that ruling**. `00103` is not edited: a spec is immutable once written, and a dated addendum inside it would break any hash pinned to it.

## The measured basis

On 2026-09-01 at 16:15:21Z the capture container on `zcrypto-red` was re-pinned and restarted. Four seconds later:

```
16:15:25,265 WARNING segment_writer - first stamp opened a past hour pair=SOL/BTC kind=trades hour=2026-09-01 15:00:00+00:00
```

`zcrypto_capture_ts_past_dated_hour_total{host="zcrypto-red"}` reads **1**. The rule that watches it, `increase(zcrypto_capture_ts_past_dated_hour_total[6h])`, reads **0**.

Nothing was fabricated. `SOL/BTC` is a thin pair; on restart its first replayed trade print carried a stamp from hour 15 while the clock read 16:15, and `15.part0000.parquet` was already on disk for that hour. The replayed prints were then recognised from that file and dropped. This is the resubscribe replay the rollout skill documents as **healthy**, and which the writer's own comment names as T0026 behaviour.

Two independent defects met here, and each hid the other:

1. the detector counted a benign restart as a fabrication, and
2. the alert was structurally incapable of reporting it, so no page ever contradicted the baseline.

The result is worse than either alone: the operator surface asserts the baseline is "a hard zero over the fleet's whole life" and that the rule "has never fired", while the counter reads 1 on a live host.

## What `00103` D5 actually specified, and what was built

D5 names the harm precisely — "the harm is a past-dated stamp **fabricating a committed final for a past hour**" — and the runbook renders it as "a stamp dated into a past, **unpublished** hour". Both require the hour to have held **no capture**.

The implemented predicate is `self._oracle is not None and hour < _hour_start(_utcnow())`. It never tests whether the hour holds data. **It is strictly wider than the condition it was specified to detect**, and a restart satisfies the extra width whenever a stream had no event in the current hour before the stop: its previous hour is then still open — `close()` deliberately never finalizes it, so `_recover` seeds no floor above it — and the first replayed stamp re-opens it. A stream that had already crossed into the current hour leaves its previous hour finalized, the floor sits above that hour, and the replayed stamp is dropped as a late event instead. That is the same floor argument D1 rests on, read from the other side.

D5's claim of immunity — "no interaction with drains, replays or future stamps" — holds mid-stream, where the floor is `_current_hour`. It fails at the first event, where the floor is `_floor` and can sit an hour back. The plan stated the false premise outright: "A normal restart mid-hour opens the CURRENT hour, so `hour < _hour_start(now)` is false and nothing counts."

The knowledge was available: the rollout skill documented this replay as healthy **one day before** `00103` was written, and `_hold`'s own docstring names the T0026 reconnect replay thirty-odd lines from the branch. It simply never reached D5.

## Decisions

### D1 — The predicate gains the test D5 already specified: the hour must hold no data

Count only when the opened past hour has **no `.part` files on disk**. The predicate reuses the helper the writer already uses three lines later — `_open_hour` seeds its de-dup set from `self._parts_for(self._hour_dir(hour), ...)`, which defaults to `marker=".part"` — but this is a **new, earlier read**, not a reordering of that one, and the two see different disk states. `_open_hour`'s read runs after `_redeem_held` has renamed the hour's `.held` spills into `.part` files; the predicate's must run before it, at the first-event branch, over the pre-redemption file set. **That ordering is load-bearing**: sharing one read with `_open_hour` would make a `.held`-only hour look captured and blind the detector to the case the next paragraph exists to protect.

**Why absent `.part` files mean the hour was never captured, given that a FINALIZED hour has none either.** `_commit` unlinks an hour's parts once the merged bytes are durable, so `_parts_for` returns `[]` for an hour holding a certified `<HH>.parquet` as surely as for an empty one. That does not widen the predicate, because such an hour can never reach the first-event branch at all: `_recover` seeds `self._floor` from every committed final on disk as `max(hour) + 1 h`, so any hour with a final is strictly below the floor and `append`'s late-event guard drops its stamp before `_enter_hour` is called. The `.part` test is therefore exact for every hour the branch can actually see, and it is deliberately NOT widened to also stat `<HH>.parquet` — that conjunct would be unreachable code guarding a door the floor already closes, and it would mask a future regression in `_recover` instead of letting it fail. What holds this together is the floor, so it is pinned by a test rather than left as prose (D8).

**`.part` specifically, and `.held` must NOT count as captured.** Held spills (`<HH>.held####.parquet`) are rows the oracle never confirmed, quarantined outside the canonical tree. An hour holding only `.held` files is the **dangerous** case, not a benign one: the alert's own summary says a fabricated final "can pull a quarantined `.held` sidecar in with it", which is precisely the redemption path `_redeem_held` performs. Testing `.held` as evidence of capture would blind the detector to its worst case.

This restores the predicate to its specified meaning: a past hour that was **never captured**, which is the only shape that can fabricate a certified final. A restart that re-opens an hour it already has parts for is, by construction, not fabricating anything.

`_sweep` is not the vehicle. It rglobs every `.part*.parquet` under the stream root and is literally the code that knows which hours hold data, but its `hour < before` bound excludes the hour in question, and it runs one line **after** the increment.

### D2 — The alert reads the counter by absolute value, not by `increase()`

`increase()` cannot see this counter, and the reason is permanent rather than a timing artifact. The step is bound to process start (`self._current_hour is None`), scrapes are 60 s apart, so the counter's reset to 0 is never sampled. Over a series whose every in-window sample is `1`, `increase()` returns `0.0` **forever** — no sample below 1 re-enters the window. The 15:00Z event can never be reported by that rule.

The rule's own comment argues the opposite as its justification: "the counter can advance at most once per stream per process — one first event each — so `increase() > 0` over a long window is the whole detection". A counter whose only step is bound to process start is precisely the counter `increase()` cannot read.

The contrast already exists in the same file: `zcrypto-capture-venue-not-online` reads its process-lifetime counter **by absolute value**, for this exact reason.

**What this changes about clearing, stated because it is a real cost.** An absolute-value rule stays firing until the counting process restarts — there is no window for it to fall out of. Under D1 that is the behaviour we want: a non-zero counter now means a genuine fabricated hour exists, and that condition does not stop being true merely because six hours passed. It does mean the rule is a latch, and the runbook entry must say so, or an operator will wait for a self-clear that never comes.

### D3 — The two sibling counters were examined for the same defect; NEITHER is converted

**`zcrypto-capture-hour-finalized-early` is NOT start-correlated, so `increase()` reads it correctly and it keeps that form.** `_count_if_early` has **two** call sites: `_sweep`, on the restart path, and — the one that decides this — the first statement of `_finalize_hour`, which runs on `_enter_hour`'s ordinary rotation branch at every hour boundary on every one of the 24 writers. Any clock lagging at all makes every genuine boundary confirm early, which `00103` D3 rules a true positive; the runbook sizes that at up to ~576 counts a day per machine and makes the magnitude the operator's discriminator. A counter that steps hundreds of times a day is exactly the counter `increase()` CAN read, and D2's argument — that the only step is bound to process start, so the reset is never scraped — does not transfer to it.

Converting it anyway would be a deliberate move from a warning that self-clears to a latch an operator can only clear by restarting live capture on the unbackfillable path, and it would falsify the six-hour window the runbook's magnitude test, its step 1 and its step 6 are all built on. That is a worse rule, not a more consistent one.

**Its residual is named and accepted**: a step taken only on the sweep path, seconds after start, has its own reset unscraped for the same reason D2 gives — so a first-ever early close on a freshly-started process is a one-count blind spot in the `increase()` form. That is one count of a signal whose detection is the recurring series, not the whole of it, and closing it is not worth the latch.

**`zcrypto-capture-rows-quarantined` is exposed too, and absolute value does NOT fix it — so it is deliberately OUT of scope here.** Its mechanism is different in kind, and the exposure is per increment SITE rather than per counter. Of the two causes the rule's own comment names, the second — a process stopping inside `CLOCK_WITNESS_MARGIN` of a boundary — spills at `close()`; the first, a lone stream in a sparse hour, spills at whichever site it reaches first, `_hold`'s `flush_rows` cap on the live path or `close()`. A `close()` spill happens in the dying process, with a 60 s scrape and no `stop_grace_period` override, so those increments are usually **never scraped at all**, and a value that is never published cannot be read by any expression, absolute or windowed. The cap site — reached when one unconfirmed hour piles up `flush_rows` held rows — is on the live path and IS scraped normally, so the counter is not unobservable in general; but that site is not start-correlated, so D2's argument does not reach it and `increase()` already reads it correctly. Absolute value therefore buys nothing at either site, which is what keeps this out of scope rather than any claim that the whole counter is invisible. Its real fix is a different question — persist the count across restart, or widen the shutdown grace so the last scrape lands. Not a log-line ruling: the writer emits no critical-level logging at all, so there is no CRITICAL line to promote to detector. Bundling any of this here would ship a change that looks like a fix and is not. **This needs its own decision and is not registered by this spec** — a deferral whose only home is a spec is not tracked.

### D4 — The file's existing generalisation about this class is wrong and is corrected

`alerts.yaml` already diagnosed this failure class for `venue-not-online` and then generalised it incorrectly: "The sibling `increase()` rules work because their counters already exist at 0 and only step; that idiom does not transfer to a label that materialises on the event."

That covers only lazily-materialising series. It misses **eagerly-published counters on a host new to the metric** (today's case — the counter shipped 2026-08-29 and reached `zcrypto-red` only at the re-pin, so its first-ever sample already carried the 1) and **start-correlated steps** generally. The corrected statement belongs beside the rules it governs.

### D5 — The operator surfaces are corrected, because both now state falsehoods

`capture.md`'s entry says the baseline is "a hard zero over the fleet's whole life" and "**This has never fired.** Treat the response as unrehearsed rather than routine." The first is false and the second is misleading — it has now counted, benignly. The plan's one benign-case carve-out never reached the runbook at all; the runbook must carry it, because the runbook is what a paged operator reads.

### D6 — The existing `1` on `zcrypto-red` is left in place and explained

It is process-lifetime state and will clear on the next restart. Nothing is repaired by hand — the runbook's own instruction is "Do not attempt to repair the hour by hand", and there is no hour to repair.

What changes is the record. `fleet-pins.md`'s capture rows name the DIGEST a re-pin moved to; what a standing `1` MEANS is not something a pins row says, and it is what a paged operator needs. The durable home is the runbook entry a page links, as a dated note beside the corrected baseline — it is read at exactly the moment the question is asked. The pins map is re-trued by whoever performs the re-pin, from host reads; this spec does not author that row.

### D7 — Landing order: BOTH capture hosts carry the writer's fix before the rule is pushed

D2 and D6 collide, and the collision would page on landing. `zcrypto-red`'s counter reads `1` today and D6 leaves it alone; an absolute-value rule pushed while that `1` stands fires immediately on a value we have already established is benign — a spurious CRITICAL on the capture pair, which is the one place a false page is most expensive.

So the order is fixed: **land D1, re-pin BOTH capture hosts to an image carrying it — verified by digest, not by reading the counter — and only then push D2's rule change**, confirming both counters read 0 by value as the last check rather than as the gate.

**The gate is the digest, and saying "converge the capture hosts" collapses a two-step deploy into one.** D1 changes `cli/capture/segment_writer.py`, so the deploy is a new-digest re-pin, and the canary rule forbids re-pinning the primary to a capture-image digest whose secondary bake has not passed — the two hosts therefore re-pin at different times with a bake between them. A value gate would pass in that gap: only `zcrypto-red` carries a non-zero counter today, so "both read 0" is satisfied the moment the secondary re-pins, while the primary is still running the wide predicate and one ordinary restart of it — a converge, a reboot, an OOM — would step the counter on the 2026-09-01 shape and latch a CRITICAL on the capture pair. Reading 0 is a fact about the counter's history; carrying D1 is a fact about the code, and only the second is the safe condition.

This is the same shape as the standing rule that a schema-widening deploy converges every reader before the writer — here the writer's correction must reach both hosts before the reader is allowed to believe it.

Pushing the rule first is not a smaller step. It is the one ordering that guarantees a page for a non-event.

### D8 — Verification

The guard is unproven until the defect it names is constructed and seen to trip it, on a fixture where defect and correct behaviour **differ**:

- **The existing positive test actively asserts the wrong behaviour** and must be re-pointed, not merely kept green. It constructs a crash-restart and asserts `ts_past_dated_hour == 1`, with nothing bogus in the fixture — its two firing properties are exactly the incident's. Its target hour is empty on disk, which is the discriminator D1 introduces, so under D1 it becomes a **true** positive and keeps its assertion for the right reason. That must be stated in the test, or the next reader will think the fix changed nothing.
- **A new negative test** builds the incident: an oracle-bearing writer, a mid-hour restart, a first stamp one hour back, and **parts on disk for that hour**. It must read `0`. The whole T0026 replay family currently misses this branch by one constructor argument — those tests use the oracle-less writer while production passes the oracle — so the new test uses the production shape.
- **A `.held`-only positive**, because D1's marker choice is the half that can be re-widened silently. No existing fixture puts a `.held` file on disk for the hour that opens, so a predicate widened to accept any parquet as capture evidence would pass the whole suite while blinding the detector to the fabrication the alert summary names. The test writes a `.held` spill for the past hour and asserts the count is still taken; the marker is proven by a mutation that **widens** the evidence test to accept `.held` as capture too — the defect the marker choice actually risks, and the only mutation this test alone fails. A swap (`.held` read instead of `.part`) is killed by the negative test on its own and therefore proves nothing about this one.
- **The floor argument D1 rests on is pinned too**: a past hour holding a committed `<HH>.parquet` must never reach the counting branch, because `_recover`'s floor refuses its stamp as a late event. Without that test the `.part`-only predicate is correct only by an argument no guard checks.
- **The alert change is proven by value against a real series**, not by reading the expression: the replacement expression seen to evaluate non-zero against `zcrypto-red`'s standing `1`, which the `increase()` form reads as `0`. **That proof exists only BEFORE the re-pin**, and is taken there: D7 gates the push on a re-pin that restarts capture, and D6's counter is process-lifetime state, so by the push both hosts read 0 by construction and the discriminating reading is gone. It is a measurement, not a repo check — recorded once and copied into the closeout, never re-hunted at the push, where the only check available is D7's own both-read-0 confirmation.
- **A control that must stay silent**: **the sibling counter on the same host** (`hour_finalized_early_total`, 0 under the same absolute-value form) — the only control available to the 2026-09-01 measurement, whose selector returned exactly one series. The **two-host** control needs no separate wait and is owed nothing after the wave: D7 gates the push on both hosts carrying D1, and D1 ships in the same binary that publishes these counters, so both series exist by the time the push happens. The same-host control is taken with the non-zero proof above and shares its date; the two-host one is taken at the wave. An absent series and a series reading 0 are different states, and `noDataState` decides which one pages.

## Out of scope

- The `hour < _hour_start(now)` bound itself. D1 narrows *what counts*, not the boundary arithmetic.
- Any change to the late-event guard or the replay behaviour. The replay is correct; only its accounting was wrong.
- `zcrypto-capture-venue-not-online`, which already reads by absolute value and is the pattern D2 adopts.
