# 00103 — make T0037's accepted residuals observable, and move the limitation onto the runbook

Closes [[T0037]]. Three components, shipped in that order, on one branch and one PR:

| # | component | what it buys | ships via |
| --- | --- | --- | --- |
| A | two capture counters + one shipper admission | the residuals stop being invisible | capture image re-pin, then an Alloy config converge |
| B | four alert rules + the runbook entries they point at | the trigger moves onto a surface that runs without anyone remembering a topic file | Grafana push |
| C | archive T0037, re-tense the code prose | the deferral is discharged rather than re-parked | closeout commit |

**A ships and its baselines are read BY VALUE before any rule in B is pushed.** A rule pushed ahead of its metric's first record pages a spurious no-data alert (`fleet-deploys.md`), and a "baseline zero" claim that was measured in July is not evidence about a counter deployed in August.

This spec does **not** close the residuals. It closes the gap between "accepted limit" and "unwatched limit".

## The measured basis

All read 2026-08-29 against production unless noted.

| reading | value | what it settles |
| --- | --- | --- |
| `increase(zcrypto_capture_rows_held_total[24h])` | **73.05**, identically on both hosts | holding is the normal path (~3 rows per boundary); the counter cannot discriminate a residual |
| `zcrypto_capture_rows_quarantined_total` | **0** on both hosts | the alert's "baseline is zero" claim holds — but it watches the never-confirmed path, not either residual |
| `node_timex_offset_seconds` | **(no series)** | the capture Alloy keep-regex is an allowlist on `__name__` and omits the timex family; nothing anywhere watches clock skew |
| late-event drop | `logger.warning`, `cli/capture/segment_writer.py:362` | no counter; and `zcrypto-rollout-image` documents `dropping late event` after a start as healthy, so the one visible trace reads as noise |
| fleet width | 12 pairs × {book, trade} = **24 writers** | the topic's "20 writers" was stale |
| provenance | oracle `385a735f` 2026-07-14 → metric `7b597fe0` 2026-07-22 → alert `1630ca93` 2026-07-27 | the `.held` alert described the metric backwards from the start; this is not drift |

**The consequence**: T0037's `ripe_when` ("either accepted residual is OBSERVED in production") is unsatisfiable. `open-topics.md` requires a trigger "derived from measured state and verifiably satisfiable — never a condition the data source cannot deliver". Both residuals manifest as *an hour finalized early, and that stream's tail then dropped as late* — and neither half is counted anywhere.

## Decisions

### D1 — ONE early-finalization counter; earliness is structurally bounded by `MAX_TS_AHEAD`

`zcrypto_capture_hour_finalized_early_total` — unlabelled. **There is no second band, because no second band is reachable.** Derived from the code, not assumed:

- `append()` holds any event whose hour exceeds `confirmed`, so `_enter_hour` is reached only with `hour ≤ confirmed`;
- `confirmed` is `_hour_start(witnesses[HOUR_QUORUM-1])`, and `observe()` clamps **every** witness at `now + MAX_TS_AHEAD`;
- `_finalize_hour(P)` requires `hour > P`, so `P ≤ confirmed − 1h`;
- therefore `earliness = (P + 1h) − now ≤ confirmed − now ≤ MAX_TS_AHEAD`.

An earlier draft split the counter at `MAX_TS_AHEAD` and assigned the upper band to residual (b). That band cannot be entered, and the clamp sentence above is what disproves it.

### D1b — residual (b) is invisible to every clock-referenced detector, and D4 is its ONLY coverage

A leading clock does not merely evade the earliness measurement; it **subtracts its own lead back out of it**. With the clock leading 30 min (true 13:56, `now` = 14:26), the handicapped clock witness at 14:21 vouches hour 14, an in-window bogus stamp seconds it, hour 13 finalizes 26 min early *in true time* — and the detector computes `14:00 − 14:26 = −26 min`, counting nothing.

This is D3's principle applied where the earlier draft failed to apply it: **any earliness test measured against the wall clock inherits the clock's error, in both directions.** For a lagging clock the error is conservative (it over-reports); for a leading clock it is exactly self-cancelling. No arrangement of this counter can see residual (b).

So the clock-skew alert (D4) is not a disambiguator for (b) — it is (b)'s **sole** detector, which raises rather than lowers the stakes on its threshold. That is the principled outcome: when the fault is the clock, only the precondition is observable, and it is observable *before* the damage rather than after.

### D2 — the observation sits at the true publish point, which is BOTH callers

Earliness is `(hour + 1h) − now`, evaluated where an hour is published as a committed final. There are **two** such paths, and instrumenting only the rotation one leaves a real case uncounted:

- `_finalize_hour` → `_merge_hour`, the rotation path;
- `_sweep` → `_merge_hour` **directly**, bypassing `_finalize_hour`.

The sweep path is not hypothetical: residual (a) landing in a restart window (`_current_hour is None`, two bogus stamps confirming the next hour) sweep-publishes the truncated hour — the same shape T0037's own history records as "the startup sweep publishes the live hour truncated". Both call sites take the same arithmetic. A swept hour from a genuinely earlier process yields a negative earliness and counts nothing, so no special case is needed — but that exclusion is arithmetic, not the call graph.

### D3 — a clock lagging by less than the window FIRES the counter, and that is correct

With lag L < `MAX_TS_AHEAD`, a genuine boundary finalizes L early. This is not a false positive to engineer away: the detector cannot be "corrected" by trusting the clock more, because T0036's binding finding is that the clock gets **no veto over live data**.

Read with D4 alongside: counter firing **and** offset within threshold ⇒ residual (a); counter firing **and** clock lagging ⇒ benign. **Pin this in a test** so a later reader does not suppress the signal residual (a) shares.

Magnitude, corrected: the family sums across **24 writers**, each finalizing each hour, so a lagging clock produces up to ~576 increments/day/host — not 24. The alert must be written knowing that, or its `for:` and threshold will be wrong.

### D4 — the clock offset is admitted to the shipper, and it now carries residual (b) alone

Two edits, not one — **admitting a name is not publishing it**. `prometheus.exporter.unix`'s `set_collectors` is an EXACT override of the exporter's defaults, and the capture config's list omitted `timex`, so the metric would not have existed to keep. Enable the `timex` collector **and** add `node_timex_offset_seconds` / `node_timex_sync_status` to the keep-regex. Either edit alone yields `(no series)` — the same shape as the T0051 keep-regex trap, one layer further up, and the reason step 4 reads by value rather than trusting a converge's `changed=`.

Alert at **|offset| > 10 s**, or `sync_status` reporting unsynchronised.

10 s is structural: orders of magnitude above a disciplined clock's steady state, and 30× below `CLOCK_WITNESS_MARGIN`, so skew is flagged long before it can either cause residual (b) or make D1's counter ambiguous. Per D1b this rule is (b)'s only detector, so it ships **critical**, not as a nicety.

### D5 — the past-dated residual is a STARTUP-WINDOW fault, and that is where it is detected

The earlier draft's "count every `ts` that goes backward against `_max_ts`" is wrong three ways, each producing a critical alert on healthy traffic:

1. **Drained held rows.** `append()`'s drain loop re-admits held rows through `_admit`, but `_hold` already advanced `_max_ts` for every one of them — so every drained row but the newest reads backward. At the measured 73 held rows/day/host this alone pages continuously.
2. **T0026 reconnect replays** are by construction older than `_max_ts`.
3. **A neutralized future stamp** parks `_max_ts` ahead, after which every genuine row reads backward — a *future*-stamp scenario the existing tests pin as HEALTHY would page as the past-dated residual.

More importantly, the broad counter does not name the harm. The harm is a past-dated stamp **fabricating a committed final for a past hour** — and that is structurally confined to the startup window, because `append()` computes `floor = self._current_hour or self._floor`: once an hour is open, any past-hour stamp is **already dropped** by the late-event guard. Only the first event of a process, where `_current_hour is None`, can open a past hour.

So the detector is: at `_enter_hour`'s first-event branch, count when the entered hour is materially behind the wall clock's hour. Narrow, no interaction with drains, replays or future stamps, and it names the actual fabrication path.

**Consequence for the plan**: no `_advance_witness` helper, and no extraction from `_admit`/`_hold`. The hot path keeps its current shape.

### D6 — the `.held` alert's prose is corrected, and it gains the runbook entry it never had

`zcrypto-capture-rows-quarantined`'s comment and `summary` are rewritten to say what the metric measures — held rows spilled for an hour the oracle never **confirmed** — and to send the operator after the real causes (a lone stream in a sparse hour; a process stop inside `CLOCK_WITNESS_MARGIN` of a boundary), not after "a late-delivering stream". The summary is read on a phone with nothing open (`operator-facing-text.md`), so this is a correctness fix, not a wording preference.

### D7 — the operating surface is `infra/runbooks/capture.md`, in the shapes it already uses

- **One `KNOWN LIMITATION` entry** for the residual mechanisms, modelled on `cross-hour-straddle`: what you are seeing, what it means (the three residuals, the bands, and which knob would close each and what it would starve), what to do (**the truncation is permanent by design — do not attempt repair**; how to name the residual by reading the band against the clock offset), and `Retire when`.
- **One `ALERT` entry per rule** shipped in B, plus the missing one for `zcrypto-capture-rows-quarantined`.

**The alert uid is the join key, so uids and runbook headings must match exactly.** Alerts here carry no runbook-link annotation — `capture.md`'s headings are literally `## <uid> — ALERT`, and grepping the uid from the page is how an operator gets from a phone notification to the response. A rule whose uid does not appear as a heading is a rule with no runbook, however complete the runbook text is.

`### Retire when` is the runbook's own native form of `ripe_when`, and it is read at the moment the thing fires rather than during a review of an index. That is the whole transformation: the trigger stops being a promise in a topic file and becomes a condition on the page an operator is already on.

### D8 — T0037 archives, and its code prose is re-tensed rather than deleted

At closeout: `status: resolved`, `ripe_when` **deleted** (an archived topic carrying a trigger is by construction a stranded deferral), file moved to `archive/`, index bullet moved and re-pointed. Its `## Resolution` names the runbook entries and the alert uids, in the shape T0025 used — *the trigger is retired rather than waited on*. Citations in `cli/capture/segment_writer.py` are re-tensed to `(T0037, resolved, records why)`, never removed (`code-prose.md`).

**What is resolved is the deferral, not the mechanism.** The residuals remain accepted design limits; the judgement that each closing knob starves a legitimate case is unchanged and is carried into the runbook entry verbatim in substance.

## Verification

Every detector needs a **constructed defect that trips it** and a **healthy production-shaped control that must stay silent** (`agent-ops.md`) — a guard that always fires ships green just as surely as one that never does.

| detector | constructed defect | control that must stay silent |
| --- | --- | --- |
| `hour_finalized_early_total`, rotation path | two streams stamped bogus inside one closing window (residual (a)) | genuine two-stream boundary, healthy clock |
| `hour_finalized_early_total`, **sweep path** | residual (a) landing with `_current_hour is None`, so the sweep publishes the truncated hour | a sweep republishing a genuinely past hour — negative earliness, counts nothing |
| the same counter, D3 | clock lagging 3 min, genuine traffic — **must fire**, pinned as intended | — |
| `ts_past_dated_hour_total` | a bogus past-dated FIRST stamp opening an un-published past hour | a normal start whose first stamp is current; **and** ≥2 distinct-ts held rows draining; **and** the pinned lone-bogus-*future*-stamp scenario — all must read zero |
| clock skew | — (not code) | the series is present with a plausible value on both hosts |

**Two controls are load-bearing because the earlier draft failed them.** The drain control needs **≥2 distinct-ts held rows** — with one row it stays silent under the defect and proves nothing. The lone-bogus-future-stamp control is an existing pinned-healthy `test_t0037_*` scenario that the earlier D5 would have paged on; it must stay at zero.

**`beyond_window` has no row because it has no reachable state** (D1). A test asserting it fires would be unfailable-by-construction in the wrong direction — it would sit red forever.

Existing coverage that must stay green unchanged: the 16 `test_t0037_*` cases and `test_verify_tree_skips_held_spills`. The `oracle=None` byte-for-byte equivalence and the lagging-clock set-equality baseline are the two that would catch an accidental behaviour change from adding observations.

**The hot path is observed, never redirected**: these are counter increments and one comparison; no decision in `append()`, `_admit`, `_hold` or the oracle may change. A diff that alters a rotation outcome has failed this spec regardless of its tests.

## Deploy sequence

1. Land A's code + tests. Cold spec+plan review at the **Fable** floor — this is the unbackfillable capture path (`spec-plan-locations.md`).
2. Build the image; roll out under `zcrypto-rollout-image` in full: secondary → bake gate → primary. A capture-image re-pin owes the whole canary discipline; nothing here is exempt.
3. Alloy keep-regex converge, pinned to the **currently-running** Alloy digest — config-only, no bake owed.
4. Read all three families by VALUE on both hosts: `hour_finalized_early_total` present and zero; `ts_past_dated_hour_total` present and zero **over a window containing at least one process restart** — its only reachable path is a process's first event, so a restart-free window cannot exercise it and is not a baseline; `node_timex_offset_seconds` present and within threshold. `(no series)` is not a zero.
5. Push B's rules (Grafana), then confirm each evaluates.
6. Runbook entries, topic archive, closeout, iterations-history entry.

**If step 4 finds the clock offset outside the D4 threshold, that is a finding to act on in this branch** — the discipline gets fixed, or the threshold is re-derived against measured reality with the reason recorded. It is not a deferral, and it does not become a new topic.

## Out of scope

- **Closing the residuals themselves.** Raising `HOUR_QUORUM` starves small `--pairs` runs; requiring two distinct requester `ts` before the clock may second starves lone sparse streams. Both judgements stand, and this spec's purpose is to watch what they leave behind.
- **Bounding the `.held` quarantine's growth.** Spills are kept and never deleted by design, and the prune's name globs deliberately exclude them. Nothing observed today suggests accumulation; the measured spill count is zero on both hosts.
- **Configuring chrony/timesyncd.** No role configures either today. D4 admits the measurement that would tell us whether that is a problem — acting on a bad reading is step 4's business, not a standing work item.
