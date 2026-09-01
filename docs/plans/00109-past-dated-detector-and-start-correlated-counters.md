# 00109 — the past-dated detector counts a benign restart: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `ts_past_dated_hour` counting a benign restart re-open, and make the rules that read it — and its exposed sibling — able to see the events they claim to detect.

**Architecture:** One predicate narrows in `cli/capture/segment_writer.py` using disk evidence the writer already reads three lines later. Two Grafana rules move from `increase()` to absolute value. Two operator surfaces are corrected. Nothing changes about the replay itself.

**Tech Stack:** Python 3.14 (uv), pytest, Grafana provisioned alert rules (`infra/grafana/alerts.yaml`), markdown runbooks.

**Spec:** `docs/specs/00109-past-dated-detector-and-start-correlated-counters-design.md` — supersedes spec `00103` D5.

## Global Constraints

- **`00103` is immutable and is NOT edited.** All corrections land in `00109` or on the operating surfaces.
- **`.part` is the capture evidence; `.held` is NOT** (spec 00109 D1). An hour holding only `.held` files must still count — it is the fabrication case the alert summary names.
- **Landing order is fixed** (spec 00109 D7): the predicate lands and the capture hosts converge (resetting the counter) BEFORE the rule change is pushed to Grafana. This plan lands repo changes only; the Grafana push is an attended step in the next converge wave and is explicitly NOT a task here.
- **Capture path**: `cli/capture/segment_writer.py` is on the unbackfillable L2 path. Review floor is Fable.
- `zcrypto-capture-rows-quarantined` is **out of scope** (spec 00109 D3) — absolute value does not fix it.

---

### Task 1: The negative test — the incident, red

**Files:**
- Test: `tests/test_capture_segment_writer.py`

**Interfaces:**
- Consumes: `_new_writer`, `_oracle_writer`, `_book_event`, `_ts`, `HourOracle`, the `clock` fixture — all already in this module.
- Produces: `test_t0037_restart_reopening_a_captured_hour_counts_nothing`.

- [ ] **Step 1: Write the failing test**

Place it immediately after `test_t0037_past_dated_first_stamp_counted` so the pair reads as positive-then-negative.

```python
def test_t0037_restart_reopening_a_captured_hour_counts_nothing(tmp_path, clock):
    # The 2026-09-01 incident (spec 00109 D1): a mid-hour restart whose FIRST event is a replayed
    # pre-restart print opens the PREVIOUS hour — but that hour HAS parts on disk, so nothing was
    # fabricated and nothing may be counted. Distinguished from the positive test above by exactly
    # one property: there, the crash left hour 10 with no parts; here, hour 15 keeps its own.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(15, 30)
    for i in range(5):  # flush_rows=5 → these land as 15.part0000.parquet
        w1.append(_book_event(15, 30, checksum=i + 1))
    del w1  # crash mid-hour: parts on disk, hour never finalized (close() never finalizes anyway)

    assert list((tmp_path / "BTC" / "EUR" / "book" / "2026" / "01" / "01").glob("15.part*.parquet"))

    clock.now = _ts(16, 15)
    w2 = _oracle_writer(tmp_path, HourOracle())
    w2.append(_book_event(15, 30, checksum=999))  # replayed pre-restart print, one hour back
    assert w2._current_hour == _ts(15, 0)  # the past hour DID open — the branch ran
    assert w2.ts_past_dated_hour == 0      # …and counted nothing, because the hour was captured
```

- [ ] **Step 2: Run it and watch it fail for the right reason**

Run: `uv run pytest tests/test_capture_segment_writer.py::test_t0037_restart_reopening_a_captured_hour_counts_nothing -v`
Expected: FAIL on the last assert, `assert 1 == 0`. **If it fails on the glob assert instead, the fixture is wrong, not the code** — the parts must exist before the second writer starts, or the test proves nothing.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_capture_segment_writer.py
git commit -m "test(capture): a restart re-opening a captured hour must count nothing"
```

---

### Task 2: Narrow the predicate

**Files:**
- Modify: `cli/capture/segment_writer.py` (the first-event branch in `_enter_hour`, ~line 499)

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

- [ ] **Step 2: Run both T0037 tests together**

Run: `uv run pytest tests/test_capture_segment_writer.py -k t0037 -v`
Expected: the new negative test PASSES, and all five pre-existing `t0037` tests still pass — including `test_t0037_past_dated_first_stamp_counted`, which stays a true positive because its crash left hour 10 with no parts.

- [ ] **Step 3: Prove the guard still bites**

`--control` is a sed-expr that must FAIL the probe, not a test path — it proves the harness can detect breakage at all before any real verdict counts. The probe must also pass unmutated first (rc 7 otherwise).

```bash
infra/scripts/mutate-probe.sh \
  --file cli/capture/segment_writer.py \
  --control 's/self\.ts_past_dated_hour += 1/self.ts_past_dated_hour += 0/' \
  --mutation 's/and not self\._parts_for/and self._parts_for/' \
  -- uv run pytest tests/test_capture_segment_writer.py -k t0037 -q
```

Expected: control FAILS (rc 5 if it does not — the harness is not discriminating and nothing below counts), then the mutation reports **KILLED**. A SURVIVED verdict means the negative test cannot see the sign-flip and Task 1 needs a better fixture. Verify the selection actually collects the new test first — `uv run pytest tests/test_capture_segment_writer.py -k t0037 --collect-only -q` — since a `-k` filter that deselects it would score a KILLED that proves nothing.

- [ ] **Step 4: Commit**

```bash
git add cli/capture/segment_writer.py
git commit -m "fix(capture): count a past-dated hour only when it holds no capture"
```

---

### Task 3: Make the existing positive test say why it is still positive

**Files:**
- Modify: `tests/test_capture_segment_writer.py` (`test_t0037_past_dated_first_stamp_counted`)

- [ ] **Step 1: Extend its comment**

Its fixture is already correct under D1 — the hard crash leaves hour 10 with no parts — but nothing in the test says that is now load-bearing. Add to the existing comment block:

```python
    # Under spec 00109 D1 this stays a TRUE positive for a reason the fixture already had by
    # accident: `del w1` loses the buffered hour-9 row, so hour 10 has no `.part` files and the
    # narrowed predicate still counts it. The negative test below differs in exactly that property.
    # Do not "simplify" the crash away — it is what makes this a fabrication rather than a re-open.
```

- [ ] **Step 2: Run and commit**

Run: `uv run pytest tests/test_capture_segment_writer.py -k t0037 -q`
Expected: all pass, unchanged.

```bash
git add tests/test_capture_segment_writer.py
git commit -m "test(capture): the positive case is a fabrication because the crash left no parts"
```

---

### Task 4: The two alert rules read by absolute value

**Files:**
- Modify: `infra/grafana/alerts.yaml` — `zcrypto-capture-ts-past-dated-hour`, `zcrypto-capture-hour-finalized-early`

**Interfaces:**
- Consumes: nothing new.
- Produces: rule expressions readable by `tests/test_infra_alert_rules.py`; the panel-pairing test matches rule to panel on **exact string equality**, so any charted panel expression must move in the same commit.

- [ ] **Step 1: Change both expressions**

For each of the two uids, replace `increase(<counter>{host=~"zcrypto|zcrypto-red"}[6h])` with `max by (host) (<counter>{host=~"zcrypto|zcrypto-red"})`, leaving evaluator, `for:` and `noDataState` untouched.

- [ ] **Step 2: Correct the generalisation comment**

`alerts.yaml` already states, beside `venue-not-online`: *"The sibling `increase()` rules work because their counters already exist at 0 and only step; that idiom does not transfer to a label that materialises on the event."* Replace with a statement that also covers the two cases it misses — an eagerly-published counter on a host **new to the metric** (its first sample already carries the step), and a **start-correlated** step (the reset is never scraped, because the increment lands seconds after start and scrapes are 60 s apart).

- [ ] **Step 3: Check whether either rule is charted**

Run: `uv run pytest tests/test_dashboards_cover_metrics.py::test_a_panels_red_line_agrees_with_the_rule_it_charts -q`
Expected: PASS. If it fails, a panel charts one of these rules and its `expr` must take the identical edit in this commit — the test pairs on exact string equality, so a rule-only change silently drops the pair rather than failing loudly.

- [ ] **Step 4: Run the rule guards and commit**

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py -q`

```bash
git add infra/grafana/alerts.yaml
git commit -m "fix(obs): a start-correlated counter is the one increase() cannot read"
```

---

### Task 5: The operator surfaces

**Files:**
- Modify: `infra/runbooks/capture.md` — the `zcrypto-capture-ts-past-dated-hour` entry

- [ ] **Step 1: Correct the two false statements**

The entry says the baseline is "a hard zero over the fleet's whole life" and "**This has never fired.** Treat the response as unrehearsed rather than routine." Both are now false: it counted on `zcrypto-red` at 2026-09-01T16:15:25Z, benignly. Rewrite in place — not as an appended correction, which reads second and less confidently.

- [ ] **Step 2: Add what the plan promised and never delivered**

`00103`'s plan said the runbook carried a benign-restart carve-out. It never did. State the discriminator an operator can act on: a count with `.part` files present for that hour is a re-open, not a fabrication — and under D1 that no longer counts at all, so a non-zero value now means a genuine never-captured hour.

- [ ] **Step 3: State that the rule is a latch** (spec 00109 D2)

Absolute value does not self-clear; it stays firing until the capture process restarts. An operator waiting for a six-hour window to pass waits forever.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py -q`
Expected: PASS. The runbook is an operator-visible surface — no `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` or phase tokens in its prose.

```bash
git add infra/runbooks/capture.md
git commit -m "docs(runbooks): the past-dated baseline is not a hard zero, and the rule is a latch"
```

---

### Task 6: Closeout

**Files:**
- Modify: `docs/iterations-history-phase1.md` (T0037's subject-matter phase — the same file `iter-153` used)
- Modify: `docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md`

- [ ] **Step 1: Append the iterations-history entry**

Load the `iteration-closeout` skill for the entry format and phase routing. One bullet per thing that landed: the superseded ruling and why it was wrong; the narrowed predicate and the disk evidence it uses; the two rules that could not see their own events; the surfaces that stated falsehoods.

- [ ] **Step 2: Update T0037**

Its `## Suggested next steps` describe the detectors as delivered and their residuals as detection-based. That remains true, but the detector's meaning has changed — record it, and note the landing-order constraint (D7) so the Grafana push is not taken early.

- [ ] **Step 3: Commit**

```bash
git add docs/iterations-history-phase1.md docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md
git commit -m "docs(capture): iter-<N> closeout -- the detector's predicate now matches its spec"
```

---

## Self-review

**Spec coverage.** D1 → Tasks 1–3. D2 → Task 4 (expression) + Task 5 step 3 (the latch on the operator surface). D3 → Task 4 (the sibling); its out-of-scope half is stated in Global Constraints and needs its own decision, which this plan does not take. D4 → Task 4 step 2. D5 → Task 5. D6 → no task: the live `1` is left alone deliberately, and `fleet-pins.md` already records it. D7 → Global Constraints; the Grafana push is deliberately not a task here. D8 → the verification steps inside Tasks 1–5.

**Placeholder scan.** One deliberate: `iter-<N>` in Task 6's commit message, which is not knowable until closeout.

**Type consistency.** `_parts_for(hour_dir, hh, *, marker=".part")` and `_hour_dir(hour)` are used in Task 2 exactly as `_open_hour` already calls them at the same file's line ~644.

**The thing most likely to be wrong.** Task 1's fixture depends on `flush_rows=5` actually producing a `.part` file for hour 15 before the writer is dropped. Step 2 asserts the glob for that reason — if it fails there, the test is not yet the incident and fixing the code would prove nothing.
