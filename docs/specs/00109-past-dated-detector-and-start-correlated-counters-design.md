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

The implemented predicate is `self._oracle is not None and hour < _hour_start(_utcnow())`. It never tests whether the hour holds data. **It is strictly wider than the condition it was specified to detect**, and every restart satisfies the extra width, because `close()` deliberately never finalizes the open hour.

D5's claim of immunity — "no interaction with drains, replays or future stamps" — holds mid-stream, where the floor is `_current_hour`. It fails at the first event, where the floor is `_floor` and can sit an hour back. The plan stated the false premise outright: "A normal restart mid-hour opens the CURRENT hour, so `hour < _hour_start(now)` is false and nothing counts."

The knowledge was available: the rollout skill documented this replay as healthy **one day before** `00103` was written, and the writer carries a comment naming T0026 replay eleven lines from the branch. It simply never reached D5.

## Decisions

### D1 — The predicate gains the test D5 already specified: the hour must hold no data

Count only when the opened past hour has **no parts on disk**. The writer already reads exactly this evidence three lines later — `_open_hour` seeds its de-dup set from `self._parts_for(self._hour_dir(hour), ...)` — so the fix reorders a read it already performs rather than adding a new one.

This restores the predicate to its specified meaning: a past hour that was **never captured**, which is the only shape that can fabricate a certified final. A restart that re-opens an hour it already has parts for is, by construction, not fabricating anything.

`_sweep` is not the vehicle. It rglobs every `.part*.parquet` under the stream root and is literally the code that knows which hours hold data, but its `hour < before` bound excludes the hour in question, and it runs one line **after** the increment.

### D2 — The alert reads the counter by absolute value, not by `increase()`

`increase()` cannot see this counter, and the reason is permanent rather than a timing artifact. The step is bound to process start (`self._current_hour is None`), scrapes are 60 s apart, so the counter's reset to 0 is never sampled. Over a series whose every in-window sample is `1`, `increase()` returns `0.0` **forever** — no sample below 1 re-enters the window. The 15:00Z event can never be reported by that rule.

The rule's own comment argues the opposite as its justification: "the counter can advance at most once per stream per process — one first event each — so `increase() > 0` over a long window is the whole detection". A counter whose only step is bound to process start is precisely the counter `increase()` cannot read.

The contrast already exists in the same file: `zcrypto-capture-venue-not-online` reads its process-lifetime counter **by absolute value**, for this exact reason.

### D3 — Two sibling rules carry the same defect and are fixed with it

- **`zcrypto-capture-hour-finalized-early`** — shipped in the same commit and image; `_count_if_early` is reachable from `_sweep`, which runs on the restart path, so it is start-correlated identically.
- **`zcrypto-capture-rows-quarantined`** — a mirror mechanism: one of the two causes its own comment names increments inside `close()`, in the dying process, with a 60 s scrape and no `stop_grace_period` override, so that increment is usually **never scraped at all**.

Fixing only the subject rule would leave two rules asserting coverage they do not have.

### D4 — The file's existing generalisation about this class is wrong and is corrected

`alerts.yaml` already diagnosed this failure class for `venue-not-online` and then generalised it incorrectly: "The sibling `increase()` rules work because their counters already exist at 0 and only step; that idiom does not transfer to a label that materialises on the event."

That covers only lazily-materialising series. It misses **eagerly-published counters on a host new to the metric** (today's case — the counter shipped 2026-08-29 and reached `zcrypto-red` only at the re-pin, so its first-ever sample already carried the 1) and **start-correlated steps** generally. The corrected statement belongs beside the rules it governs.

### D5 — The operator surfaces are corrected, because both now state falsehoods

`capture.md`'s entry says the baseline is "a hard zero over the fleet's whole life" and "**This has never fired.** Treat the response as unrehearsed rather than routine." The first is false and the second is misleading — it has now counted, benignly. The plan's one benign-case carve-out never reached the runbook at all; the runbook must carry it, because the runbook is what a paged operator reads.

### D6 — The existing `1` on `zcrypto-red` is left in place and explained

It is process-lifetime state and will clear on the next restart. Nothing is repaired by hand — the runbook's own instruction is "Do not attempt to repair the hour by hand", and there is no hour to repair. What changes is the record: the value is a known benign artifact of the 16:15:21Z re-pin, and `fleet-pins.md`'s row for that digest already says so.

### D7 — Verification

The guard is unproven until the defect it names is constructed and seen to trip it, on a fixture where defect and correct behaviour **differ**:

- **The existing positive test actively asserts the wrong behaviour** and must be re-pointed, not merely kept green. It constructs a crash-restart and asserts `ts_past_dated_hour == 1`, with nothing bogus in the fixture — its two firing properties are exactly the incident's. Its target hour is empty on disk, which is the discriminator D1 introduces, so under D1 it becomes a **true** positive and keeps its assertion for the right reason. That must be stated in the test, or the next reader will think the fix changed nothing.
- **A new negative test** builds the incident: an oracle-bearing writer, a mid-hour restart, a first stamp one hour back, and **parts on disk for that hour**. It must read `0`. The whole T0026 replay family currently misses this branch by one constructor argument — those tests use the oracle-less writer while production passes the oracle — so the new test uses the production shape.
- **The alert change is proven by value against a real series**, not by reading the expression: the rule must be seen to evaluate non-zero against `zcrypto-red`'s current `1`, which the `increase()` form reads as `0`.
- **A control that must stay silent**: a healthy host whose counter is 0 must not fire under the absolute-value form.

## Out of scope

- The `hour < _hour_start(now)` bound itself. D1 narrows *what counts*, not the boundary arithmetic.
- Any change to the late-event guard or the replay behaviour. The replay is correct; only its accounting was wrong.
- `zcrypto-capture-venue-not-online`, which already reads by absolute value and is the pattern D2 adopts.
