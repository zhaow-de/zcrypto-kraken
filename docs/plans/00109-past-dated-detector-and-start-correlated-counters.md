# 00109 — the past-dated detector counts a benign restart: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `ts_past_dated_hour` counting a benign restart re-open, and make the rule that reads it able to see the event it claims to detect.

**Architecture:** One predicate narrows in `cli/capture/segment_writer.py`, using the same disk-evidence helper the writer calls three lines later but at an earlier point. **One** Grafana rule moves from `increase()` to absolute value, and the panel it pages an operator to moves with it. The operator surfaces that state falsehoods are corrected. Nothing changes about the replay itself.

**Tech Stack:** Python 3.14 (uv), pytest, Grafana provisioned alert rules (`infra/grafana/alerts.yaml`), markdown runbooks.

**Spec:** `docs/specs/00109-past-dated-detector-and-start-correlated-counters-design.md` — supersedes spec `00103` D5.

## Global Constraints

- **`00103` is immutable and is NOT edited.** All corrections land in `00109` or on the operating surfaces.
- **`.part` is the capture evidence; `.held` is NOT** (spec 00109 D1). An hour holding only `.held` files must still count — it is the fabrication case the alert summary names. Task 1 pins this with its own test; it is not left to a comment.
- **The predicate is NOT widened to also stat `<HH>.parquet`** (spec 00109 D1). A finalized hour has no parts either, but `_recover` seeds `self._floor` above every committed final, so such an hour's stamp is dropped as a late event and never reaches the counting branch. That conjunct would be unreachable code, and Task 1's floor test is what keeps the argument honest.
- **Landing order is fixed** (spec 00109 D7): the predicate lands and BOTH capture hosts re-pin to an image carrying it — verified by digest, not by reading the counter — BEFORE the rule change is pushed to Grafana. This plan lands repo changes only; the Grafana push is an attended step in the next converge wave and is explicitly NOT a task here. Task 6 lands that imperative where the pushing agent will meet it.
- **Capture path**: `cli/capture/segment_writer.py` is on the unbackfillable L2 path. Review floor is Fable.
- **Only ONE rule converts.** `zcrypto-capture-hour-finalized-early` is examined and deliberately kept on `increase()` (spec 00109 D3): `_count_if_early` also runs from `_finalize_hour` on the ordinary rotation path, so its counter steps at every boundary under any lagging clock and is not start-correlated. Nothing in this plan touches that rule, its runbook entry, or its panel series.
- `zcrypto-capture-rows-quarantined` is **out of scope** (spec 00109 D3) — **not** because the counter is invisible: both causes its rule names spill at `close()`, in a dying process nothing scrapes, while its other increment site (`_hold`'s `flush_rows` cap) is on the live path and `increase()` already reads it correctly. Absolute value changes nothing at either site, which is the reason, and it is the reason Task 7 Step 3's explicit-drop branch must record. Task 7 Step 3 still owes it a registration or an explicit drop before this branch merges.
- **The falsified "hard zero" sentence has ONE enumeration and it is a command, not a list**: `grep -rni "hard.zero" infra/` — measured today, six hits in four files. Task 4 owns the two `infra/grafana/` files, Task 5 the two `infra/runbooks/` ones. Re-run it after both tasks: no surviving hit may still assert the baseline. Nothing else in this plan restates that set.

---

### Task 1: The negative test — the incident, red — plus the two properties nothing else pins

**Files:**
- Test: `tests/test_capture_segment_writer.py`

**Interfaces:**
- Consumes: `_new_writer`, `_oracle_writer`, `_book_event`, `_ts`, `HourOracle`, the `clock` fixture — all already in this module. `_write_part(rows, hour, *, marker=".part")` for the held spill.
- Produces: `test_t0037_restart_reopening_a_captured_hour_counts_nothing`, `test_t0037_a_held_only_past_hour_still_counts`, `test_t0037_a_finalized_past_hour_never_reaches_the_counter`.

**Fixture-date warning, for all three:** `_ts()` builds `datetime(2026, 7, 8, …)` and `_hour_dir` lays the tree out as `<pair>/<kind>/%Y/%m/%d`, so every on-disk path in this module is `BTC/EUR/book/2026/07/08/`. Prefer `tmp_path.rglob(...)` in a fixture assert so the date cannot rot the test.

- [ ] **Step 1: Write the failing test**

Place it immediately after `test_t0037_past_dated_first_stamp_counted` so the pair reads as positive-then-negative.

```python
def test_t0037_restart_reopening_a_captured_hour_counts_nothing(tmp_path, clock):
    # The 2026-09-01 incident (spec 00109 D1): a mid-hour restart whose FIRST event is a replayed
    # pre-restart print opens the PREVIOUS hour — but that hour HAS parts on disk, so nothing was
    # fabricated and nothing may be counted. Distinguished from the positive test above by exactly
    # one property: there, hour 10 never received an event; here, hour 15 holds its own parts.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(15, 30)
    for i in range(5):  # flush_rows=5 → these land as 15.part0000.parquet
        w1.append(_book_event(15, 30, checksum=i + 1))
    del w1  # crash mid-hour: parts on disk, hour never finalized (close() never finalizes anyway)

    assert list(tmp_path.rglob("15.part*.parquet"))  # unfinalized parts, so the floor stays below 15

    clock.now = _ts(16, 15)
    w2 = _oracle_writer(tmp_path, HourOracle())
    w2.append(_book_event(15, 30, checksum=999))  # replayed pre-restart print, one hour back
    assert w2._current_hour == _ts(15, 0)  # the past hour DID open — the branch ran
    assert w2.ts_past_dated_hour == 0      # …and counted nothing, because the hour was captured
```

- [ ] **Step 2: Run it and watch it fail for the right reason**

Run: `uv run pytest tests/test_capture_segment_writer.py::test_t0037_restart_reopening_a_captured_hour_counts_nothing -v`
Expected: FAIL on the last assert, `assert 1 == 0`. **A failure on the glob assert means the fixture never wrote hour 15's parts** — the parts must exist before the second writer starts, or the negative case is not the incident. Check `flush_rows` and the event's hour; do not delete the assert, and do not reach for the code.

- [ ] **Step 3: The `.held` positive — the marker choice, pinned**

D1's `.part`-only rule is the half a later "simplification" can silently invert, and no existing fixture puts a `.held` file on disk for the hour that opens. Add:

```python
def test_t0037_a_held_only_past_hour_still_counts(tmp_path, clock):
    # Spec 00109 D1's DANGEROUS case, and the one the alert summary names: an hour holding only a
    # quarantined `.held` spill was never corroborated by the oracle, so it is NOT captured. Opening
    # it redeems that spill into a manifest-certified final built from rows nothing confirmed — a
    # fabrication, and it must count. A predicate widened to accept any parquet as capture evidence
    # reads 0 here while every other t0037 test stays green.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(14, 30)
    for i in range(5):
        w1.append(_book_event(14, 30, checksum=i + 1))
    clock.now = _ts(15, 5)
    w1.finalize_completed_hours(_ts(15, 0))  # 14.parquet commits, so the recovery floor is 15:00
    w1._write_part([_book_event(15, 40, checksum=7)], _ts(15, 0), marker=".held")
    del w1

    clock.now = _ts(16, 15)
    w2 = _oracle_writer(tmp_path, HourOracle())
    assert not w2._parts_for(w2._hour_dir(_ts(15, 0)), "15")  # no parts…
    assert w2._parts_for(w2._hour_dir(_ts(15, 0)), "15", marker=".held")  # …but a held spill
    w2.append(_book_event(15, 40, checksum=999))
    assert w2._current_hour == _ts(15, 0)  # a `.held` seeds no floor, so the hour really opens
    assert w2.ts_past_dated_hour == 1
```

- [ ] **Step 4: The floor property D1's `.part`-only test rests on**

A finalized hour holds no parts either (`_commit` unlinks them), so the predicate is exact only because such an hour can never reach the branch. Pin that, or the argument is prose:

```python
def test_t0037_a_finalized_past_hour_never_reaches_the_counter(tmp_path, clock):
    # Why `.part`-absence is a sound test for "never captured" (spec 00109 D1): `_commit` unlinks an
    # hour's parts once the merged bytes are durable, so a COMMITTED hour also has none. It is the
    # recovery floor, not the predicate, that rules it out — `_recover` seeds `_floor` at the newest
    # final plus an hour, and the late-event guard then refuses the stamp before `_enter_hour` runs.
    # If this ever fails, the predicate has become wrong: a benign re-open would count as fabrication.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(15, 30)
    for i in range(5):
        w1.append(_book_event(15, 30, checksum=i + 1))
    clock.now = _ts(16, 15)
    w1.finalize_completed_hours(_ts(16, 0))  # hour 15 commits AND its parts are unlinked
    del w1

    w2 = _oracle_writer(tmp_path, HourOracle())
    assert not w2._parts_for(w2._hour_dir(_ts(15, 0)), "15")  # the predicate alone would say "never captured"
    assert w2._floor == _ts(16, 0)  # …but the floor is above hour 15
    w2.append(_book_event(15, 40, checksum=999))
    assert w2._current_hour is None  # dropped as a late event: the branch never ran
    assert w2.ts_past_dated_hour == 0
```

- [ ] **Step 5: Run all three and commit the red set**

Name the node ids rather than filtering — `-k reopening` also selects the pre-existing `test_t0037_an_oracle_less_writer_reopening_a_prior_hour_counts_nothing`, and a fourth result in a run described as three is exactly the ambiguity that gets waved through:

```bash
uv run pytest -v \
  tests/test_capture_segment_writer.py::test_t0037_restart_reopening_a_captured_hour_counts_nothing \
  tests/test_capture_segment_writer.py::test_t0037_a_held_only_past_hour_still_counts \
  tests/test_capture_segment_writer.py::test_t0037_a_finalized_past_hour_never_reaches_the_counter
```

Expected: 3 collected; the re-open test FAILS on `assert 1 == 0`; the other two PASS already — they pin properties the current code has and the fix must keep, so a failure in either is a finding about this fixture, not a red phase.

```bash
git add tests/test_capture_segment_writer.py
git commit -m "test(capture): a restart re-opening a captured hour must count nothing"
```

---

### Task 2: Narrow the predicate

**Files:**
- Modify: `cli/capture/segment_writer.py` — the first-event branch in `_enter_hour` (~line 499), **and** the `ts_past_dated_hour` attribute's own comment in the constructor, which today reads `# oracle-bearing first stamps that opened an hour behind the clock (`_enter_hour`)`: the pre-D1 predicate verbatim, on the definition a maintainer reads first.
- Modify: `cli/capture/command.py` — the `zcrypto_capture_ts_past_dated_hour_total` HELP string, which today reads `"First events that opened a stream's hour already behind the wall clock."` — the pre-D1 predicate verbatim. Prometheus HELP text is operator-visible and is what any by-value verification reads, so the published definition moves in the same commit as the code, or it describes a predicate that no longer exists.

**Three descriptions of the predicate live in `cli/`, and all three move together**: the branch comment, the attribute comment, the HELP string. That is the whole set — `grep -rn "behind the wall clock\|behind the clock" cli/` finds it.

**Interfaces:**
- Consumes: `self._parts_for(hour_dir, hh, *, marker=".part")`, `self._hour_dir(hour)` — both already defined in this class.
- Produces: no signature change; `ts_past_dated_hour` keeps its meaning, narrowed.

- [ ] **Step 1: Change the condition**

Replace:

```python
            if self._oracle is not None and hour < _hour_start(_utcnow()):
```

with:

```python
            # Spec 00109 D1 supersedes 00103 D5's predicate. `hour < _hour_start(now)` alone also
            # matches a benign restart: the first event after a restart is often a replayed
            # pre-restart print (T0026), which opens the PREVIOUS hour. What D5 actually specified is
            # a FABRICATION — a past hour that was never captured — so test that directly. `.part`
            # only: `.held` spills are rows the oracle never confirmed, and an hour holding only
            # those is the fabrication case, not evidence of capture.
            if (
                self._oracle is not None
                and hour < _hour_start(_utcnow())
                and not self._parts_for(self._hour_dir(hour), f"{hour:%H}")
            ):
```

- [ ] **Step 2: Move the metric's published definition with it**

In `cli/capture/command.py`, the counter's HELP string states the old predicate. Narrow it to match — e.g. `"First events that opened a stream's hour already behind the wall clock, where that hour held no captured parts."` Keep the tokens out of the string itself; the spec citation belongs in the comment above it, which today cites the superseded `00103` D5 — re-tense it to `00109` D1 (`code-prose.md`: a closed citation is re-tensed, never left pointing at the ruling it lost).

Narrow `segment_writer.py`'s attribute comment the same way and in the same commit — "…that opened an hour behind the clock **and held no captured parts**". It is the counter's definition; left alone it states the predicate this commit removes.

- [ ] **Step 3: Run the T0037 family together**

Run: `uv run pytest tests/test_capture_segment_writer.py -k t0037 -v`
Expected: **29 collected, all pass** — 26 today (measured: `-k t0037` collects 26, 69 deselected) plus Task 1's three. Confirm the count before reading the result: this selection is the whole T0037 family, far larger than the five past-dated tests, so "more tests than the plan said" must never be waved through as harmless. Of the five, `test_t0037_past_dated_first_stamp_counted` stays a true positive because hour 10 never received an event and so holds no parts.

Step 2 rewrote a Prometheus HELP string — an operator-visible surface (`.claude/rules/operator-facing-text.md`) — so run its guard too, and as its OWN command: a shared `-k t0037` would deselect every test in that file and report a green nobody ran. Tasks 4, 5 and 6 each run it for their own surfaces.

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py -q`

- [ ] **Step 4: Commit**

```bash
git add cli/capture/segment_writer.py cli/capture/command.py
git commit -m "fix(capture): count a past-dated hour only when it holds no capture"
```

- [ ] **Step 5: Prove the guard still bites — AFTER the commit above**

`mutate-probe.sh` refuses on a dirty worktree (exit 3: its restore is `git checkout --`, which would destroy uncommitted work), so this step runs on the committed tree and cannot be moved above Step 4. `--control` is a sed-expr that must FAIL the probe, not a test path — it proves the harness can detect breakage at all before any real verdict counts. The probe must also pass unmutated first (rc 7 otherwise).

Verify the selection actually collects the new tests first — `uv run pytest tests/test_capture_segment_writer.py -k t0037 --collect-only -q` — since a `-k` filter that deselects them would score a KILLED that proves nothing.

Two mutations, because the conjunct has two independent ways to be wrong:

```bash
# (a) the sign of the new conjunct
infra/scripts/mutate-probe.sh \
  --file cli/capture/segment_writer.py \
  --control 's/self\.ts_past_dated_hour += 1/self.ts_past_dated_hour += 0/' \
  --mutation 's/and not self\._parts_for/and self._parts_for/' \
  -- uv run pytest tests/test_capture_segment_writer.py -k t0037 -q

# (b) the MARKER as EVIDENCE — the WIDENING: `.held` accepted as capture too, which no other check catches
infra/scripts/mutate-probe.sh \
  --file cli/capture/segment_writer.py \
  --control 's/self\.ts_past_dated_hour += 1/self.ts_past_dated_hour += 0/' \
  --mutation 's/and not self\._parts_for(self\._hour_dir(hour), f"{hour:%H}")/and not (self._parts_for(self._hour_dir(hour), f"{hour:%H}") or self._parts_for(self._hour_dir(hour), f"{hour:%H}", marker=".held"))/' \
  -- uv run pytest tests/test_capture_segment_writer.py -k t0037 -q
```

The `and not ` prefix on (b) is load-bearing, not decoration: `sed -i` rewrites **every** matching line, and after Step 1 the call `self._parts_for(self._hour_dir(hour), f"{hour:%H}")` appears twice in this file — once in the predicate and once in `_open_hour`'s de-dup seed. An expression anchored on the call alone mutates both and measures a different change.

Expected for each: control FAILS (rc 5 if it does not — the harness is not discriminating and nothing below counts), then **KILLED**. Mutation (a) is killed by the re-open test and the positive test together; (b) is killed by `test_t0037_a_held_only_past_hour_still_counts` **alone**, which is why that test exists. A SURVIVED verdict on (b) means the marker is asserted but not proven.

**(b) is the widening, not a marker SWAP, and the difference is the whole point of the probe.** Measured against this tree by patching each predicate onto `_enter_hour` and replaying the three fixtures: a swap (`.held` read instead of `.part`) makes the re-open fixture read 1 against its `== 0` *and* the held-only fixture read 0 against its `== 1` — so the re-open test kills it on its own and a KILLED verdict says nothing about the held-only test. The widening (`not (parts or held)`) leaves the re-open fixture at 0 and the positive at 1, and fails the held-only fixture only. That is the defect D1's marker choice actually risks — a later "simplification" accepting any parquet as capture evidence — and the one mutation this test uniquely kills.

Check rc 6 ("no-op sed") before anything else if a mutation reports nothing changed — Step 1's exact formatting is what these expressions match, so re-anchor them to the code as committed rather than editing the code to fit them.

---

### Task 3: Make the existing positive test say why it is still positive

**Files:**
- Modify: `tests/test_capture_segment_writer.py` (`test_t0037_past_dated_first_stamp_counted`)

- [ ] **Step 1: Extend its comment**

Its fixture is already correct under D1 — hour 10 holds no parts — but nothing in the test says that is now load-bearing. **The discriminator is that hour 10 never received an event, NOT the crash**: replaying the fixture with `w1.close()` before `del w1` puts `09.part0000.parquet` on disk, and `_parts_for(hour 10)` is still empty, `_floor` is still 09:00 and the counter still reads 1. Name the property that actually decides the case:

```python
    # Under spec 00109 D1 this stays a TRUE positive for a property the fixture already had:
    # neither writer ever appended an event in hour 10, so it holds no `.part` files and the
    # narrowed predicate still counts it. That — not the crash — is what makes this a fabrication
    # rather than a re-open, and it is the one property the negative test below inverts.
```

- [ ] **Step 2: Run and commit**

Run: `uv run pytest tests/test_capture_segment_writer.py -k t0037 -q`
Expected: 29 collected, all pass, unchanged — this step edits a comment only.

```bash
git add tests/test_capture_segment_writer.py
git commit -m "test(capture): the positive case is a fabrication because its hour was never written to"
```

---

### Task 4: The past-dated rule reads by absolute value, and its board moves with it

**Files:**
- Modify: `infra/grafana/alerts.yaml` — `zcrypto-capture-ts-past-dated-hour` only. `zcrypto-capture-hour-finalized-early` is examined and deliberately NOT converted (spec 00109 D3); leave its expression, annotations and comments exactly as they are.
- Modify: `infra/grafana/data-integrity-dashboard.json` — panel 110, refId **B** and the parts of its `description` that describe refId B.

**Interfaces:**
- Consumes: nothing new.
- Produces: a rule expression readable by `tests/test_infra_alert_rules.py`; a panel target that still charts what the rule fires on.

**Everything in this task lands in ONE commit.** The rule links the panel by `__dashboardUid__`/`__panelId__`, so a rule-only change leaves the page's own confirmation surface contradicting the page.

- [ ] **Step 1: Change the expression**

In `zcrypto-capture-ts-past-dated-hour`, replace `increase(zcrypto_capture_ts_past_dated_hour_total{host=~"zcrypto|zcrypto-red"}[6h])` with `max by (host) (zcrypto_capture_ts_past_dated_hour_total{host=~"zcrypto|zcrypto-red"})`, leaving evaluator, `for:` and `noDataState` untouched. The rule's `for: 5m` comment justifies itself on the permanence of the damage, not on a window, so it stays true.

- [ ] **Step 2: Rewrite every string in that rule block the change falsifies**

Six surfaces in the same block, every one of them read by a person rather than by a test — no guard in `tests/test_infra_alert_rules.py` couples any rule's title, summary, unit or `relativeTimeRange` to its selector for these, so nothing catches drift here:

1. `title:` — today `"Capture · a stream opened an archive hour that was already in the past"`: the pre-D1 predicate stated as the alert's NAME. For a Grafana provisioned rule the title IS `alertname`, and `infra/grafana/notification-templates/zcrypto-slack.tmpl` renders `.CommonLabels.alertname` as the message's first line — the phone headline, read before anything else. Retitle to the narrowed predicate — a past hour that held **no captured data** — keeping it a name rather than a sentence. Nothing else in the tree carries this string and no test pins this rule's title (`tests/test_infra_alert_rules.py` pins only `_DARK_WITH_EXPOSURE_TITLE`), so the retitle reaches nothing but the page.
2. `unit:` — today `"first events that opened an hour already in the past, last 6 hours"`. The Slack template renders the unit immediately after the measured value, so a process-lifetime latch would page as "measured 1 … last 6 hours". Restate it windowlessly, naming the capture process as the scope.
3. `summary:` — two corrections in one rewrite. Drop "The baseline is a hard zero over the fleet's whole life", which spec D5 rules false; and make the predicate match D1 — the hour opened was one holding **no captured parts**, not merely one in the past. The summary then carries CURRENT meaning only: cumulative since the capture process started, clears only when that process restarts, do not repair by hand, runbook link — a deployed artifact stands alone, so a pointer to the runbook is not enough. **No dated history in it.** By D7 the benign `1` is gone before this rule's first evaluation, so a summary saying "it has stepped once, benignly" would tell every later page to dismiss itself; that record's home is the runbook note (Task 5 Step 1).
4. The rule's justification comment — the WHOLE paragraph from *"A STEP, not a rate…"* through *"…already certified on disk"*, not its first sentence alone. Its head is the argument spec D2 identifies as the defect, and left standing it is a written case for reverting Step 1; its tail (*"Kraken's ts is measured strictly non-decreasing in production, so the baseline is a hard zero…"*) is the same falsified claim as the summary, and replacing only the quoted head leaves it inside the block. Replace the paragraph with why `increase()` fails here: the step is bound to process start, the reset is never scraped, so the series never re-enters the window below its step.
5. The block's FIRST comment paragraph, which opens `# T0037's past-dated residual (spec 00103 D5)` — the rule keeps citing the ruling this spec supersedes as its provenance. **The citation only**: re-tense it to `00109` D1 (`code-prose.md`: a closed citation is re-tensed, never left pointing at the ruling it lost). The paragraph's own account of the harm — "committing a manifest-certified 'complete' final for a period nothing was captured in" — is already D1's predicate and is left alone.
6. `relativeTimeRange` on the Prometheus node — `{from: 21600, to: 0}`, the six-hour horizon the `[6h]` selector needed. An instant `max by (host)(…)` reads no range, and `tests/test_infra_alert_rules.py`'s dark-with-exposure guard states the standing convention in its own docstring: `relativeTimeRange` is what a maintainer reads for the node's real horizon. Set it to `{from: 600, to: 0}`, matching `zcrypto-capture-venue-not-online` — the absolute-value rule this one now copies.

Keep the internal-token guard in mind: `title`, `summary` and `unit` are phone-read operator surfaces.

- [ ] **Step 3: Move panel 110's past-dated series in the same commit**

`infra/grafana/data-integrity-dashboard.json`, panel 110 ("Hour-rotation residuals — early closes, past-dated opens & clock offset") — the panel BOTH capture rotation rules link. Its refId B is `increase(zcrypto_capture_ts_past_dated_hour_total{host=~"$capture_host"}[6h])`, legend `{{host}} past-dated hour opens (6h)`.

Change refId B to `max by (host) (zcrypto_capture_ts_past_dated_hour_total{host=~"$capture_host"})`, drop `(6h)` from its legend, and correct the TWO sentences of the panel `description` that are about this counter:

1. its definition — *"Past-dated opens count streams whose FIRST event was stamped into an hour already gone — that publishes an hour marked complete for a period nothing was captured"* — which must gain D1's conjunct: an hour already gone **that held no captured parts on disk**. This is the same correction item 3 makes on the summary, and it is the one an operator following the rule's own `__dashboardUid__`/`__panelId__` link reads for confirmation;
2. *"its baseline is a hard zero over the fleet's whole life"* — the falsified sentence, corrected as on the summary, and with no dated history put in its place for the reason item 3 gives.

**The description carries no window wording to fix** (measured: `6h`, `six hour`, `last 6`, `window`, `over the last` all return nothing) — the `(6h)` this step drops is in `legendFormat` only. **Leave refId A, C and D and the early-close half of the description alone**: that rule keeps `increase(...[6h])` and its chart must keep matching it.

refId B's existing `byFrameRefID` override — `custom.thresholdsStyle: line`, `thresholds.steps` red at `0.001` — already puts the red line inside `0 < bar <= 1` and agrees with `> 0` in the old form and the new. Leave it; adding one produces a second override on the same refId.

- [ ] **Step 4: Check the pairing — knowing it is blind here**

The panel-pairing test compares rule and panel expressions for **exact string equality**, and this panel is host-templated (`$capture_host`) where the rules hardcode `zcrypto|zcrypto-red`. Measured: `len(pairs) == 54` and neither capture rotation rule is in that set, before or after this edit. **A PASS therefore proves nothing about panel 110** — it passed identically while the panel was wrong, which is how this was nearly missed.

The check that actually bites is the grep:

```bash
grep -n "zcrypto_capture_ts_past_dated_hour_total\|zcrypto_capture_hour_finalized_early_total" infra/grafana/*.json
```

Expected: hits only in `infra/grafana/data-integrity-dashboard.json` (no other dashboard reads either counter), with the past-dated hits now in the absolute-value form and the early-close hits still `increase(...[6h])`.

- [ ] **Step 5: Correct the file's generalisation comment**

`alerts.yaml` already states, beside `venue-not-online`: *"The sibling `increase()` rules work because their counters already exist at 0 and only step; that idiom does not transfer to a label that materialises on the event."* Replace with a statement that also covers the two cases it misses — an eagerly-published counter on a host **new to the metric** (its first sample already carries the step), and a **start-correlated** step (the reset is never scraped, because the increment lands seconds after start and scrapes are 60 s apart). This is the third and last comment site in this task — Step 2's items 4 and 5 are the other two, both inside the past-dated rule's own block.

- [ ] **Step 6: Run the guards and commit**

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py -q`

The by-value proof spec D8 requires — the replacement expression seen to evaluate non-zero against `zcrypto-red`'s standing `1`, with the sibling counter on the same host as the silent control — belongs to the attended push wave, not to this commit; Task 7 Step 2 is where its values get written down.

```bash
git add infra/grafana/alerts.yaml infra/grafana/data-integrity-dashboard.json
git commit -m "fix(obs): a start-correlated counter is the one increase() cannot read"
```

---

### Task 5: The operator surfaces

**Files:**
- Modify: `infra/runbooks/capture.md` — the `zcrypto-capture-ts-past-dated-hour` entry, **and** the KNOWN LIMITATION decision table's row 4, whose "Past-dated firing ⇒ … with a hard-zero baseline" carries the same falsified claim.
- Modify: `infra/runbooks/README.md` — this alert's index row, which ends "**Hard-zero baseline.**" and describes the pre-D1 predicate ("dated into an hour already gone", with no no-capture conjunct). It is not decoration: it is the index the summary's runbook path resolves through, so an operator reads it BEFORE `capture.md`, and `tests/test_infra_alert_rules.py` checks that row's routing only, never its prose. Drop the baseline claim, state the narrowed predicate, and say the value is cumulative per capture process.

**The family is three sites in two files** — `capture.md`'s entry and its decision-table row 4, plus `README.md`'s index row. Global Constraints' grep is what closes the set; do not re-derive it here. The `zcrypto-capture-hour-finalized-early` entry and its four six-hour-window statements are correct and are NOT touched — that rule keeps `increase(...[6h])` (spec 00109 D3). Panel 110's copy of the falsified baseline sentence moves in Task 4, with the expression it describes.

- [ ] **Step 1: Correct the two false statements**

The entry says the baseline is "a hard zero over the fleet's whole life" and "**This has never fired.** Treat the response as unrehearsed rather than routine." Both are now false: it counted on `zcrypto-red` at 2026-09-01T16:15:25Z, benignly, on the first replayed print after a re-pin. Rewrite in place — not as an appended correction, which reads second and less confidently. Fix the decision table's row 4 in the same pass.

**Record the known `1` here** (spec 00109 D6), as a dated note beside the corrected baseline: the value standing on `zcrypto-red` is that re-pin's artifact under the old, wide predicate, not a fabricated hour. The pins map names the digest a re-pin moved to and never what a counter's value MEANS, so an operator meeting the value has no other provenance, and this entry is what a page links.

**Keep the `<a name="zcrypto-capture-ts-past-dated-hour"></a>` anchor byte-identical.** The alert summary links it and `infra/runbooks/README.md` routes to it; a renamed or split heading breaks the link a paged operator taps.

- [ ] **Step 2: Add what the plan promised and never delivered — the three shapes that reach the page**

`00103`'s plan said the runbook carried a benign-restart carve-out. It never did. State the meaning exactly first, because the loose version misleads: a non-zero value means the hour held no **confirmed** capture **on disk at the moment it opened** — not that nothing was ever captured for it. A re-open of an hour that already has `.part` files no longer counts at all under D1, so that shape never pages; three others do, and only one of them is the fabrication. Each measurement below was replayed against this tree with the narrowed predicate patched onto `_enter_hour`.

1. **Capture was not running for that hour** — an attended reboot, a host outage. The hour holds no parts, so the first replayed stamp after the restart counts, correctly by D1's definition and yet not a bogus timestamp. Measured: hour 14 finalized, nothing written for hour 15, a new oracle-bearing writer at 16:15 whose first event is stamped 15:40 → tree `['14.parquet']`, no parts for 15, the hour opens, counter **1**.
2. **A non-graceful stop lost the unflushed buffer** — and this is the likeliest first page the change produces. There is no timed flush (`DEFAULT_FLUSH_ROWS = 5_000`), so a thin stream's whole hour can sit in RAM; SIGTERM reaches `close()` and spills it, but an OOM kill, SIGKILL, kernel panic or power loss does not, and `command.py`'s own shutdown comment says what is lost. The replay then re-opens an hour that has no parts *because the crash lost them*, and the replay is restoring exactly those rows. Measured: hour 14 finalized, two hour-15 rows buffered below `flush_rows`, the writer dropped without `close()`, a new oracle-bearing writer at 16:15 whose first event is the replayed 15:47 print → tree `['14.parquet']`, no parts for 15, counter **1**; the identical fixture with `close()` first → `15.part0000.parquet` on disk, counter **0**.
3. **The hour held only a quarantined `.held` spill** — D1's headline case, counted on purpose (Global Constraints), because those rows were never corroborated and the hour is about to be certified from rows nothing confirmed. **Its evidence destroys itself, so say so:** opening the hour calls `_redeem_held`, which renames the spill into an ordinary `.part`, and the next rotation merges it into a certified `<HH>.parquet`. Measured: tree `['14.parquet', '15.held0000.parquet']` before the append, `['14.parquet', '15.part0000.parquet']` after it, counter **1**. An operator arriving minutes later finds a full, certified hour and files a real fabrication as a detector fault unless the entry warns them. **Redemption is silent** — the writer logs it nowhere; `_redeem_held`'s only log line is its `could not redeem` failure path — so neither the disk nor the log distinguishes a redeemed hour afterwards. Name the two checks that do survive: the writer's `first stamp opened a past hour` line, which carries the pair, kind and hour, and the peer machine's copy of that hour (step 3), taken **before** anything else touches the tree. `zcrypto_capture_rows_quarantined_total` on that host corroborates only when the spill happened to be scraped before the stop, which a `close()` spill usually is not (spec 00109 D3).

**The discriminator, because shapes 1 and 2 look identical on this host's disk.** Read `RestartCount` and `StartedAt` (step 1 already gets them) and compare the hour against the peer (step 3). A gap on **both** machines spanning the hour is an outage backfill — shape 1. A restart on **this host only**, with the peer's copy of the hour intact and matching what this host now holds, is a crash replay — shape 2; a single-host crash leaves no gap on the peer, so "a gap on both" as the sole test misfiles it as a bad stamp. Neither is a fabrication. What is: a hole the peer cannot fill — and for shape 3 that comparison is the whole of the disk evidence, since the redemption renamed the rest away.

- [ ] **Step 3: State that the rule is a latch** (spec 00109 D2)

Absolute value does not self-clear; it stays firing until the capture process restarts. An operator waiting for a six-hour window to pass waits forever — and say plainly that clearing it means restarting live capture, which is a supervised act on the capture pair rather than something done to quiet a board.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_infra_alert_rules.py -q`
Expected: PASS. The first two cover the prose itself — the runbook is an operator-visible surface, so no `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` or phase tokens in it. `tests/test_infra_alert_rules.py` is the file that actually reaches this edit's real risk: it holds the summary-link, dashboard-link and index-routing guards, and a heading this rewrite renames or splits fails there and nowhere else.

```bash
git add infra/runbooks/capture.md
git commit -m "docs(runbooks): the past-dated baseline is not a hard zero, and the rule is a latch"
```

---

### Task 6: The landing order reaches the surface that performs the push

**Files:**
- Modify: `.claude/rules/fleet-deploys.md` — the "Alert-rule lifecycle" section

Spec D7 rules on how an operation must be performed, and today it lands nowhere the operator meets it: Global Constraints are read by this plan's implementer, and the topic note in Task 7 is read by whoever picks the topic up. Neither is the daily pass, which prepares `grafana-push.sh` after a merged rule fix precisely because it changes what pages — and this PR merges exactly such a fix days before the capture image can carry D1 through its bake. **The constraint is on the whole push, not on one rule**: the script has no per-rule mode.

- [ ] **Step 1: The sign-off gate — before any edit to the file**

`.claude/rules/fleet-deploys.md` is in the **protected set** (`.claude/skills/zcrypto-refine-rules/SKILL.md`): every edit to it takes the user's explicit per-edit sign-off, and a plan's authority is not that sign-off — the point of the rule is that the corpus policing a change cannot be altered by that change. The owner signed off on this task's bullet on 2026-09-01 after reading it verbatim; Step 2's text has since been rewritten (it now forbids running the script rather than pushing one rule), and **sign-off attaches to text, so the rewritten bullet needs the word again before it lands**. Show it verbatim, land exactly what is approved, and change nothing else in the file.

**Under unattended execution this task stops here** — park it, report the branch as complete without it, and leave the imperative to the attended session. Every other task in this plan is landable without it.

- [ ] **Step 2: Add one bullet under "Alert-rule lifecycle"**

State the constraint, not its history, and word it against the tool that exists. `infra/scripts/grafana-push.sh` pushes every dashboard and every rule in `alerts.yaml` in one run — its only selection env vars are `GRAFANA_URL`, the two datasource uids, the folder uid and `GRAFANA_PRUNE` — so an agent told "do not push THIS rule" has only two moves, and neither is what we want: freeze every other rule and dashboard change for the days the bake takes, or push and ship this rule early. The bullet:

> - **Do not run `grafana-push.sh` at all while either capture host lacks the narrowed past-dated predicate** — it upserts every rule in `alerts.yaml`, so there is no "push only the others"; pushing early latches a CRITICAL on the capture pair against a standing benign value. The gate is checkable from repo state: each capture row in `docs/reference/fleet-pins.md` names its build revision, and `git merge-base --is-ancestor <the predicate's commit> <that revision>` decides it per host. A rule that must ship inside the window: revert `zcrypto-capture-ts-past-dated-hour` to its `increase(...[6h])` form on `develop`, push, and re-land the absolute-value form once both rows pass.

It belongs in the same section as the existing push-ordering imperatives. Its retirement is registered as a T0037 next step in Task 7 Step 4 — a one-rollout imperative in the always-loaded corpus outlives its rollout unless something schedules its removal, and this file is protected, so a later agent cannot quietly drop it either.

Put the same constraint in the PR body, where the merging reviewer sees it.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py -q`

`.claude/**` never shares a commit with `docs/`, and this is the branch's only claude-kind change, so it commits alone:

```bash
git add .claude/rules/fleet-deploys.md
git commit -m "claude(config): the past-dated rule waits for both capture hosts to carry its predicate"
```

---

### Task 7: Closeout

**Files:**
- Modify: `docs/iterations-history-phase1.md` (T0037's subject-matter phase — the same file `iter-153` used)
- Modify: `docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md`
- Modify: `docs/open-topics/README.md` (T0037's index bullet echoes its `ripe_when`)

- [ ] **Step 1: Append the iterations-history entry**

Load the `iteration-closeout` skill for the entry format and phase routing. One bullet per thing that landed: the superseded ruling and why it was wrong; the narrowed predicate, the disk evidence it uses, and the floor that makes `.part`-absence exact; the one rule that could not see its own event, and the sibling examined and deliberately left alone; the surfaces that stated falsehoods.

- [ ] **Step 2: Record the by-value evidence D8 owes**

Spec D8's third and fourth bullets are measurements, and no repo check can discharge them. Write into the entry what was measured and when — the standing values on `zcrypto-red` (`max by (host) (...)` reading 1 against `increase(...[6h])` reading 0, and the sibling counter at 0 as the same-host silent control) — **and both hosts' values under the absolute-value form at the wave**, which D7's own gate guarantees are available by then: it holds the push until both hosts carry D1, and D1 ships in the binary that publishes these counters. Nothing is owed after the wave. Without this, nobody after the branch can tell whether the proof was ever taken.

- [ ] **Step 3: Settle the out-of-scope deferral**

`zcrypto-capture-rows-quarantined`'s exposure is stated in the spec, in Global Constraints and in this Self-review, and **three prose homes are not a registration**. A new topic file needs the user's explicit word, so ask for it at closeout in the same breath as the summary; if it is declined, write the explicit drop into the closeout entry instead, **with the reason as Global Constraints states it** — per increment site, not "absolute value does not fix it" unqualified, which reads as a claim about the whole counter and is not one. Do not let this merge as prose.

- [ ] **Step 4: Update T0037, frontmatter included**

Name the fields, because the PR touching a topic carries its whole update:

- `ripe_when:` — today it describes the `00103` sequence "deploy the detectors, read each family by value on both hosts, push the alert rules". D7 supersedes that order (re-pin both hosts, verified by digest → push → read by value); rewrite it and re-sync the echoing bullet in `docs/open-topics/README.md` through the `topic-ops` skill.
- `## Done so far` — its past-dated bullet describes the detector as "gated on the oracle", which is now half the predicate. Add the disk-evidence half.
- `## Suggested next steps` — the residuals stay detection-based, which remains true; add the landing-order constraint so the Grafana push is not taken early, **and its own close-out in the same line**: once both capture rows pass the gate, re-land the absolute-value expression if the bullet's escape hatch was taken, push, then remove the landing-order bullet from `.claude/rules/fleet-deploys.md` (a protected-file edit, so it takes the same sign-off Task 6 Step 1 describes). Nothing else schedules either the re-land or the removal, and a plan sentence is not a registration.

- [ ] **Step 5: Commit**

```bash
git add docs/iterations-history-phase1.md docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md docs/open-topics/README.md
git commit -m "docs(capture): iter-<N> closeout -- the detector's predicate now matches its spec"
```

---

## Self-review

**Spec coverage.** D1 → Tasks 1–3 (Task 1 Steps 3 and 4 pin the `.held` marker and the floor the `.part`-only test rests on). D2 → Task 4 Steps 1–2 (expression and the strings it falsifies) + Task 5 Step 3 (the latch on the operator surface). D3 → Task 4's scope, which converts one rule and states why the sibling keeps `increase()`; the `rows_quarantined` half is out of scope and Task 7 Step 3 owes it a registration or an explicit drop. D4 → Task 4 Step 5. D5 → Task 5 (three sites in two runbook files) + Task 4 Steps 2–3 (the rule block's copies and panel 110's), the set closed by Global Constraints' grep rather than by any list. D6 → Task 5 Step 1, as a dated note in the runbook — the pins map names digests, not what a value means, and this plan authors no pins row. D7 → Task 6, on the operating surface, plus the PR body; the Grafana push itself is deliberately not a task here, and Task 6 Step 1 is a sign-off gate rather than an edit because that file is protected. D8 → Tasks 1–5's verification steps for the code guard, and Task 7 Step 2 for the two bullets that are measurements rather than repo checks.

**Placeholder scan.** One deliberate: `iter-<N>` in Task 7's commit message, which is not knowable until closeout.

**Type consistency.** `_parts_for(hour_dir, hh, *, marker=".part")` and `_hour_dir(hour)` are used in Task 2 exactly as `_open_hour` already calls them at the same file's line ~644 — and that duplication is why Task 2 Step 5's marker mutation is anchored on `and not `, since `sed -i` would otherwise rewrite both call sites.

**Commit-kind split.** Task 6 is the branch's only `.claude/**` change and commits alone; every other commit is code, tests, `infra/` or `docs/`.

**The thing most likely to be wrong.** Task 1's re-open fixture depends on `flush_rows=5` actually producing a `.part` file for hour 15 *and* on that hour never being finalized — a finalized hour would raise the recovery floor above it and the stamp would be dropped as late instead, which is a different (and passing) test. Step 1's glob assert covers the first; Step 4's floor test covers the second by asserting the opposite case explicitly.
