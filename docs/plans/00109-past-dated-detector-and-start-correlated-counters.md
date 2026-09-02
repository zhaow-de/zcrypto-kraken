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
- **Landing order is fixed** (spec 00109 D7): the predicate lands and BOTH capture hosts re-pin to an image carrying it — verified by digest, not by reading the counter — BEFORE the rule change is pushed to Grafana. This plan lands repo changes only; the Grafana push is an attended step in the next converge wave and is explicitly NOT a task here. Task 6 lands that imperative where the pushing agent will meet it, **and the PR body carries the same constraint** — that sentence belongs to PR-open rather than to Task 6, so a parked Task 6 does not park it too.
- **Capture path**: `cli/capture/segment_writer.py` is on the unbackfillable L2 path. Review floor is Fable.
- **Only ONE rule converts.** `zcrypto-capture-hour-finalized-early` is examined and deliberately kept on `increase()` (spec 00109 D3): `_count_if_early` also runs from `_finalize_hour` on the ordinary rotation path, so its counter steps at every boundary under any lagging clock and is not start-correlated. Nothing in this plan touches that rule, its runbook entry, or its panel series.
- `zcrypto-capture-rows-quarantined` is **out of scope** (spec 00109 D3) — **not** because the counter is invisible: its `close()` spills happen in a dying process nothing scrapes, while `_hold`'s `flush_rows` cap is on the live path and `increase()` already reads it correctly (a lone sparse stream reaches whichever of the two comes first). Absolute value changes nothing at either site, which is the reason, and it is the reason Task 7 Step 3's explicit-drop branch must record. Task 7 Step 3 still owes it a registration or an explicit drop before this branch merges.
- **The falsified "hard zero" sentence has ONE enumeration and it is a command, not a list**: `grep -rni "hard.zero" infra/` — measured today, six hits in four files. Task 4 owns the two `infra/grafana/` files, Task 5 the two `infra/runbooks/` ones. **The committed-tree re-run is Task 5 Step 4's**, which carries the command and its expected output — reading `HEAD` is what keeps an edit that was never staged a hit, and no surviving hit may still assert the baseline. Nothing else in this plan restates that set.
- **D1 creates a SECOND family, enumerated the same way**: every surface stating the pre-D1 predicate — a past hour, with no no-capture conjunct. `grep -rniE "dated into|stamped into|already in the past|behind the (wall )?clock" infra/grafana/ infra/runbooks/ cli/capture/` — measured today, eleven hits and no unrelated ones. **Eight are owned**: `alerts.yaml`'s `title`, `summary` and `unit` and `data-integrity-dashboard.json`'s panel-110 `description` (Task 4); `capture.md`'s entry-opening "What you are seeing" paragraph and `README.md`'s index row (Task 5); `segment_writer.py`'s `ts_past_dated_hour` attribute comment and `command.py`'s HELP string (Task 2). **Three are members that already read correctly and stay**: `alerts.yaml`'s first block-comment paragraph and `capture.md`'s decision-table row, which both already say *past, unpublished hour*, and `_enter_hour`'s block-comment floor sentence, which states a property rather than the predicate. **Its committed-tree re-run is Task 5 Step 4's too** — the last of the three tasks these two families reach. The count falls as rewrites drop the matched phrases; the invariant is not a number but that **no surviving hit describes the predicate without D1's no-capture conjunct**.

---

### Task 1: The negative test — the incident, red — plus the two properties nothing else pins

**Files:**
- Test: `tests/test_capture_segment_writer.py`

**Interfaces:**
- Consumes: `_new_writer`, `_oracle_writer`, `_book_event`, `_ts`, `HourOracle`, `_drop_levels`, the `clock` fixture and pytest's `caplog` — all already in this module (`logging` is imported at its top). `_write_part(rows, hour, *, marker=".part")` for the held spill.
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

A finalized hour holds no parts either (`_commit` unlinks them), so the predicate is exact only because such an hour can never reach the branch. Pin that, or the argument is prose.

**Assert the drop's own log line, not just its outcome.** `append` returns before `_enter_hour` at two places — `_implausible` and the `hour < floor` guard — and both leave `_current_hour is None` and the counter at 0, so the two closing asserts alone cannot tell the floor from the plausibility guard. That substitute is not hypothetical: `infra/runbooks/capture.md`'s decision table names "refuse a first stamp whose hour is behind our clock's hour" as this residual's closing knob, which is a past-direction bound in exactly that guard. Use the module's own idiom, `_drop_levels(caplog, "dropping late event")` — a module-level helper defined further down the file, so its position does not matter — and take `caplog` as a fixture argument:

```python
def test_t0037_a_finalized_past_hour_never_reaches_the_counter(tmp_path, clock, caplog):
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
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w2.append(_book_event(15, 40, checksum=999))
    assert _drop_levels(caplog, "dropping late event") == [logging.INFO]  # the FLOOR refused it…
    assert w2._current_hour is None  # …so the branch never ran
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

**TWO descriptions of the predicate move**: the attribute comment in `segment_writer.py` and the HELP string in `command.py`. `grep -rn "behind the wall clock\|behind the clock" cli/` returns three, and it still returns three after this task — its third hit is `_enter_hour`'s existing block comment, whose floor sentence ("the first event is the only one that can open an hour behind the wall clock") states a property that stays true under D1 and stays as it is. Step 1's new comment sits beneath it; do not rewrite a true sentence to make the count come out.

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

**The superseded citation is its own family, enumerated by `grep -rn "00103 D5" cli/ tests/ infra/` — four hits, all owned.** Two are this task's: `command.py`'s HELP comment above, and `segment_writer.py`'s block comment directly above the branch Step 1 rewrites, whose opening `# Spec 00103 D5, T0037's past-dated residual.` is re-tensed to `00109` D1 the same way — **the citation only**; the paragraph's body is the floor property, which stays true under D1 and is left as it is. The other two are owned elsewhere: `alerts.yaml`'s block comment (Task 4 Step 2 item 5, same re-tense) and `test_capture_segment_writer.py`'s positive test (Task 3 Step 1, whose appended `00109` D1 paragraph re-tenses it in effect). Nothing else in `cli/`, `tests/` or `infra/` cites it.

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

**This task lands TWO commits, and the split is what makes Task 6's escape hatch a `git revert` instead of a list of strings to re-edit under time pressure.** Each step below tags its edits **[c1]** or **[c2]**:

1. **[c1] The prose that holds under either expression form** — the `title`, D1's conjunct in the `summary`, in the `unit` and in panel 110's `description`, the dropped hard-zero sentences **and the realness conclusions they carried**, the re-tensed citation, the `for: 5m` comment's rationale, Step 5's generalisation comment. All of it is true whether the rule reads `increase()` or `max by (host)`, so the hatch must never take it back.
2. **[c2] The form move** — the expression, the `unit`'s window and process scope, `relativeTimeRange`, the `summary`'s latch sentence, the justification comment's replaced head, and panel 110's refId B expression and legend. Everything a revert to `increase(...[6h])` must undo, and nothing else. The rule links the panel by `__dashboardUid__`/`__panelId__`, so the panel's series moves **inside this commit**: a rule-only change leaves the page's own confirmation surface contradicting the page.

Both land before the PR, so the merged tree is what Step 6 verifies; the split exists for the revert, not for review — and Step 6's last block is where the split is proven, because nothing else in the repo can tell two commits from one.

**Work this task in TWO PASSES, by tag rather than in step order.** The split is made by what is on disk when each commit runs; Step 6's two `git add` lines name the same two whole paths and cannot separate it afterwards, and items 2, 3 and 4 of Step 2 rewrite the SAME YAML string or comment paragraph in both passes — their c1 text must exist on disk and be committed before the c2 text overwrites it, which no staging trick can do to two states of one line. **Pass 1 (c1)**: Step 2 items 1, 2-c1, 3-c1, 4-c1, 5 and 7; Step 3's two `description` corrections; Step 5 — then Step 6's guard run and the c1 commit. **Pass 2 (c2)**: Step 1's expression; Step 2 items 2-c2, 3-c2, 4-c2 and 6; Step 3's refId B and legend — then Step 4's grep (it reads the absolute-value form, so it cannot run in pass 1), Step 6's guard run and the c2 commit. That enumeration is the whole task: Step 1 sits first for readability and is a **pass-2** edit, so read the whole task before touching either file.

- [ ] **Step 1: Change the expression [c2]**

In `zcrypto-capture-ts-past-dated-hour`, replace `increase(zcrypto_capture_ts_past_dated_hour_total{host=~"zcrypto|zcrypto-red"}[6h])` with `max by (host) (zcrypto_capture_ts_past_dated_hour_total{host=~"zcrypto|zcrypto-red"})`, leaving the evaluator, the `for:` VALUE and `noDataState` untouched. The `for: 5m` comment above it is not untouched — D1 falsifies its damage-is-already-permanent clause — and Step 2 item 7 owns it.

- [ ] **Step 2: Rewrite every string in that rule block the change falsifies**

Seven surfaces in the same block, every one of them read by a person rather than by a test — no guard in `tests/test_infra_alert_rules.py` couples any rule's title, summary, unit or `relativeTimeRange` to its selector for these, so nothing catches drift here:

1. **[c1]** `title:` — today `"Capture · a stream opened an archive hour that was already in the past"`: the pre-D1 predicate stated as the alert's NAME. For a Grafana provisioned rule the title IS `alertname`, and `infra/grafana/notification-templates/zcrypto-slack.tmpl` renders `.CommonLabels.alertname` as the message's first line — the phone headline, read before anything else. Retitle to the narrowed predicate — a past hour that held **no captured data** — keeping it a name rather than a sentence. Nothing else in the tree carries this string and no test pins this rule's title (`tests/test_infra_alert_rules.py` pins only `_DARK_WITH_EXPOSURE_TITLE`), so the retitle reaches nothing but the page.
2. `unit:` — today `"first events that opened an hour already in the past, last 6 hours"`, which is the pre-D1 predicate **and** a window. It splits the way item 3 does, and for the same reason. **[c1]**: replace "already in the past" with D1's conjunct as items 1 and 3 do — an hour that held **no captured data** — keeping ", last 6 hours", which c2 is what removes, so the hatch cannot restore the pre-D1 predicate to the phone. **[c2]**: drop the window and name the capture process as the scope; the Slack template renders the unit immediately after the measured value, so a process-lifetime latch left on the old string would page as "measured 1 … last 6 hours".
3. `summary:` — two corrections, and they land in different commits. **[c1]**: the whole sentence *"The baseline is a hard zero over the fleet's whole life and the counter can step at most once per stream per capture process, so any step at all is a real event"*, not the baseline clause alone — spec D5 rules the baseline false, and deleting only that half leaves the step cap carrying a conclusion it never supported. Re-aim the conclusion at what D1 now means: a step says the past hour that opened held no captured data, which Step 2 of Task 5 shows several benign shapes also produce, so the runbook's shape discrimination comes before calling it a fabrication. Make the predicate match D1 in the same pass — the hour opened was one holding **no captured parts**, not merely one in the past. **[c2]**: add the latch sentence, which is only true of the absolute-value form — cumulative since the capture process started, clears only when that process restarts. The summary then carries CURRENT meaning only: the narrowed predicate, the latch, do not repair by hand, runbook link — a deployed artifact stands alone, so a pointer to the runbook is not enough. **No dated history in it.** By D7 the benign `1` is gone before this rule's first evaluation, so a summary saying "it has stepped once, benignly" would tell every later page to dismiss itself; that record's home is the runbook note (Task 5 Step 1).
4. The rule's justification comment — the WHOLE paragraph from *"A STEP, not a rate…"* through *"…already certified on disk"*, not its first sentence alone; and it too splits. **[c1]**: drop the tail (*"Kraken's ts is measured strictly non-decreasing in production, so the baseline is a hard zero…"*), the same falsified claim as the summary, which would otherwise survive inside the block. **[c2]**: replace the remaining head — the argument spec D2 identifies as the defect, and left standing a written case for reverting Step 1 — with why `increase()` fails here: the step is bound to process start, the reset is never scraped, so the series never re-enters the window below its step. Split this way the hatch's revert restores a head that is correct under `increase()` and does not bring the hard-zero sentence back with it.
5. **[c1]** The block's FIRST comment paragraph, which opens `# T0037's past-dated residual (spec 00103 D5)` — the rule keeps citing the ruling this spec supersedes as its provenance. **The citation only**: re-tense it to `00109` D1 (`code-prose.md`: a closed citation is re-tensed, never left pointing at the ruling it lost). The paragraph's own account of the harm — "committing a manifest-certified 'complete' final for a period nothing was captured in" — is already D1's predicate and is left alone.
6. **[c2]** `relativeTimeRange` on the Prometheus node — `{from: 21600, to: 0}`, the six-hour horizon the `[6h]` selector needed. An instant `max by (host)(…)` reads no range, and `tests/test_infra_alert_rules.py`'s dark-with-exposure guard states the standing convention in its own docstring: `relativeTimeRange` is what a maintainer reads for the node's real horizon. Set it to `{from: 600, to: 0}`, matching `zcrypto-capture-venue-not-online` — the absolute-value rule this one now copies.
7. **[c1]** The `for: 5m` comment — *"5m absorbs the one-minute datasource transients and no more: the damage is already permanent when this counts, so nothing is bought by waiting longer."* Its tail is falsified by **D1**, not by D2: under the narrowed predicate a count can be Task 5 Step 2's shape 1 or 2, a benign restart whose hour lost its parts, so not every count is permanent damage. Keep the 5m and re-justify it on what it buys — the transients it absorbs, and the latch that makes a longer wait pointless. It is tagged **[c1]** because it holds under either expression form, so the hatch must not take it back.

**The dropped hard-zero clause has a realness conclusion attached to it, and that is a two-member family** — a sentence that infers "any step is real" from the baseline the same clause asserts: `alerts.yaml`'s `summary` (item 3 above) and `infra/runbooks/capture.md`'s *"any step at all is the event, and there is no threshold to tune"* (Task 5 Step 1, which owns it). Panel 110's *"any step pages critical"* is a statement about the rule's severity rather than about the value's meaning, so it is **not** a member and stays.

Keep the internal-token guard in mind: `title`, `summary` and `unit` are phone-read operator surfaces.

- [ ] **Step 3: Move panel 110's past-dated series with the rule, and correct its description**

`infra/grafana/data-integrity-dashboard.json`, panel 110 ("Hour-rotation residuals — early closes, past-dated opens & clock offset") — the panel BOTH capture rotation rules link. Its refId B is `increase(zcrypto_capture_ts_past_dated_hour_total{host=~"$capture_host"}[6h])`, legend `{{host}} past-dated hour opens (6h)`.

**[c2]** Change refId B to `max by (host) (zcrypto_capture_ts_past_dated_hour_total{host=~"$capture_host"})` and drop `(6h)` from its legend. **[c1]** Correct the TWO sentences of the panel `description` that are about this counter — they describe the counter, not the form, so the hatch leaves them standing:

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

- [ ] **Step 5: Correct the file's generalisation comment [c1]**

`alerts.yaml` already states, beside `venue-not-online`: *"The sibling `increase()` rules work because their counters already exist at 0 and only step; that idiom does not transfer to a label that materialises on the event."* Replace with a statement that also covers the two cases it misses — an eagerly-published counter on a host **new to the metric** (its first sample already carries the step), and a **start-correlated** step (the reset is never scraped, because the increment lands seconds after start and scrapes are 60 s apart). This is the fourth and last comment site in this task — Step 2's items 4, 5 and 7 are the others, all three inside the past-dated rule's own block.

- [ ] **Step 6: Run the guards and commit — once per commit**

Run after each commit's edits, so neither tree ships unverified:

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py -q`

The by-value proof spec D8 requires — the replacement expression seen to evaluate non-zero against `zcrypto-red`'s standing `1`, with the sibling counter on the same host as the silent control — **was already taken, on 2026-09-01T19:2xZ, before any re-pin**, and it exists nowhere else: D7's re-pin restarts capture and D6's counter is process-lifetime state, so at the push both hosts read 0 by construction. Nothing here is owed to the wave but the post-re-pin readings. Task 7 Step 2 records the half that was measured; Step 4 registers the half that is owed.

```bash
# c1 — the prose that holds under either form. Pass 2's edits are NOT on disk yet; if they are,
# stop and re-work the task in the two passes the preamble sets out.
git add infra/grafana/alerts.yaml infra/grafana/data-integrity-dashboard.json
git commit -m "fix(obs): the past-dated surfaces state the predicate the writer now watches"

# c2 — the form move. Its SUBJECT is the operand Task 6's escape hatch reverts by name:
# reword it and the bullet in `.claude/rules/fleet-deploys.md` has to be re-signed-off.
git add infra/grafana/alerts.yaml infra/grafana/data-integrity-dashboard.json
git commit -m "fix(obs): a start-correlated counter is the one increase() cannot read"
```

**Then prove the split once, here, on the branch — by reading the two commits, never by taking the revert.** The c1/c2 split IS the hatch's mechanism and nothing else in the repo can see it: `staged-kind` polices claude-kind against everything else and no test, hook or grep tells two commits from one, so an implementer who lands both sets in one commit passes every check above.

```bash
git log -2 --format=%s
c2=$(git log -1 --format=%H -F --grep='fix(obs): a start-correlated counter is the one increase() cannot read')
git grep -n 'increase(zcrypto_capture_ts_past_dated_hour_total' "$c2~1" -- infra/grafana/
git grep -n 'increase(zcrypto_capture_ts_past_dated_hour_total' "$c2"   -- infra/grafana/
git grep -ni 'hard.zero' "$c2~1" -- infra/grafana/
```

`git log -2` must print the c2 subject and then the c1 subject, one line each — the positive check the split has never had, and the collapse's signature is that it does not. An empty `$c2` says the same thing and is where to stop: the split collapsed, or the subject was reworded and the bullet in `.claude/rules/fleet-deploys.md`, which names it verbatim, has to be re-signed-off. `$c2~1` is c1's tree, which is exactly what a revert of c2 restores for the hunks c2 owns, so the two `git grep`s read both sides of the hatch without moving anything. Expected: **two** `increase(` hits at `$c2~1` — the rule's `expr` and panel 110's refId B — and **none** at `$c2`, because c2 moved both surfaces. One hit at `$c2` means c2 moved only one of the two; fewer than two at `$c2~1` means c1 already carried part of the form move, so the tree the hatch falls back to is not the `increase()` form it promises. The `hard.zero` read is not a count: **read every surviving hit against Global Constraints' invariant** — a hit that DENIES the baseline is c1's correction standing where the hatch leaves it, and only a hit that still ASSERTS the baseline is the collapse. Either collapse verdict is the same remedy: re-split the commits and repeat. **Run the five lines one at a time, never `&&`-chained and never under `set -e`**: each `git grep` exits 1 when it finds nothing, and finding nothing is the PASS for the `$c2` read and can be the pass for the `hard.zero` one, so a chained run stops on a healthy line and reports a green nobody read. Nothing in this block writes — `git grep` against a tree-ish reads a committed tree, so there is no index left staged and no abort to forget, which is what keeps it out of Task 5 Step 4's path-scoped `git add`. Measured against a scratch repo carrying a correct split and both collapse shapes (git 2.47.3): the correct split gives 2 / 0 / two denying `hard.zero` lines and leaves the worktree untouched; a collapse under c2's subject gives the same 2 / 0 and is caught only by `git log -2`'s second line and by the two ASSERTING `hard.zero` hits; a collapse under c1's subject leaves `$c2` empty and the next line fails loudly with `fatal: unable to resolve revision`.

---

### Task 5: The operator surfaces

**Files:**
- Modify: `infra/runbooks/capture.md` — the `zcrypto-capture-ts-past-dated-hour` entry, **and** the KNOWN LIMITATION decision table's row 4, whose "Past-dated firing ⇒ … with a hard-zero baseline" carries the same falsified claim.
- Modify: `infra/runbooks/README.md` — this alert's index row, which ends "**Hard-zero baseline.**" and describes the pre-D1 predicate ("dated into an hour already gone", with no no-capture conjunct). It is not decoration: it is the index the summary's runbook path resolves through, so an operator reads it BEFORE `capture.md`, and `tests/test_infra_alert_rules.py` checks that row's routing only, never its prose. Drop the baseline claim, state the narrowed predicate, and say the value is cumulative per capture process.

**Two families reach this task, and Global Constraints' two greps are what close them — Step 4 runs both against the committed tree; do not re-derive either enumeration here.** The falsified hard-zero baseline is three sites in these two files — `capture.md`'s entry and its decision-table row 4, plus `README.md`'s index row. The pre-D1 predicate is two more — `capture.md`'s entry-opening paragraph and `README.md`'s index row again — with `capture.md`'s decision-table row already reading correctly. The `zcrypto-capture-hour-finalized-early` entry and its four six-hour-window statements are correct and are NOT touched — that rule keeps `increase(...[6h])` (spec 00109 D3). Panel 110's copy of the falsified baseline sentence moves in Task 4, with the expression it describes.

- [ ] **Step 1: Correct the entry's false and superseded statements**

The entry says the baseline is "a hard zero over the fleet's whole life" and "**This has never fired.** Treat the response as unrehearsed rather than routine." Both are now false: it counted on `zcrypto-red` at 2026-09-01T16:15:25Z, benignly, on the first replayed print after a re-pin. Rewrite in place — not as an appended correction, which reads second and less confidently. Fix the decision table's row 4 in the same pass.

**The sentence riding on the baseline goes with it**, in the same paragraph: *"So this is a step detector, not a rate: any step at all is the event, and there is no threshold to tune."* It is this file's member of the realness family Task 4 Step 2 enumerates — a conclusion the deleted baseline was the whole support for, and one Step 2's four shapes disprove. Keep the true half (a step detector rather than a rate, no threshold to tune) and re-aim the conclusion at D1: a step says the hour that opened held no captured data, so the shapes below are what tell an event from a benign restart.

**A third statement in the entry states the pre-D1 predicate**: its opening "What you are seeing" paragraph, *"A stream's first event after a capture process started carried a timestamp dated into an hour that had already passed, and the writer opened that hour."* Left alone it contradicts everything Step 2 adds below it, on the first line an operator reads. Give it D1's conjunct — the hour held no captured data when it opened. (Global Constraints' pre-D1 grep is what closes this set; the decision-table row and `alerts.yaml`'s block comment are the members that already read correctly.)

**Record the known `1` here** (spec 00109 D6), as a dated note beside the corrected baseline — **past-tense about the reading, and self-closing**, because this is the surface the summary's `Runbook:` link resolves to and a paged operator reads it against a live value. It records that the counter *read* 1 on `zcrypto-red` on 2026-09-01, an artifact of that day's re-pin under the old, wide predicate rather than a fabricated hour, **and that the re-pin which must precede this rule's first evaluation clears it, so a value seen while this rule is live is not that artifact**. The clearing is a D7 precondition and not yet a measurement — this branch merges before the wave — so it is stated as the condition it is; asserting it in the past tense here would be the same untaken control Task 7 Step 2 refuses to write. History justifying the corrected baseline, never a description of a live value — the same hazard Task 4 Step 2 item 3 keeps out of the summary, arriving here instead unless the tense is pinned. The pins map names the digest a re-pin moved to and never what a counter's value MEANS, so an operator meeting the value has no other provenance, and this entry is what a page links.

**Keep the `<a name="zcrypto-capture-ts-past-dated-hour"></a>` anchor byte-identical.** The alert summary links it and `infra/runbooks/README.md` routes to it; a renamed or split heading breaks the link a paged operator taps.

- [ ] **Step 2: Add what the plan promised and never delivered — the four shapes that reach the page**

`00103`'s plan said the runbook carried a benign-restart carve-out. It never did. State the meaning exactly first, because the loose version misleads: a non-zero value means the hour held no **confirmed** capture **on disk at the moment it opened** — not that nothing was ever captured for it. A re-open of an hour that already has `.part` files no longer counts at all under D1, so that shape never pages. **Four shapes still do, and this host's disk does not separate them**: shapes 1, 2 and 4 all leave the hour with no `.part` files — which is exactly why the predicate counts them — so the peer comparison is the branch, not a tie-breaker. Shapes 1–3 below were each replayed against this tree with the narrowed predicate patched onto `_enter_hour`; shape 4 has shape 1's on-disk fixture by construction and is distinguished by the stamp, never by the tree.

1. **Capture was not running for that hour** — an attended reboot, a host outage. The hour holds no parts, so the first replayed stamp after the restart counts, correctly by D1's definition and yet not a bogus timestamp. Measured: hour 14 finalized, nothing written for hour 15, a new oracle-bearing writer at 16:15 whose first event is stamped 15:40 → tree `['14.parquet']`, no parts for 15, the hour opens, counter **1**.
2. **A non-graceful stop lost the unflushed buffer** — and this is the likeliest first page the change produces. There is no timed flush (`DEFAULT_FLUSH_ROWS = 5_000`), so a thin stream's whole hour can sit in RAM; SIGTERM reaches `close()` and spills it, but an OOM kill, SIGKILL, kernel panic or power loss does not, and `command.py`'s own shutdown comment says what is lost. The replay then re-opens an hour that has no parts *because the crash lost them*, and the replay is restoring exactly those rows. Measured: hour 14 finalized, two hour-15 rows buffered below `flush_rows`, the writer dropped without `close()`, a new oracle-bearing writer at 16:15 whose first event is the replayed 15:47 print → tree `['14.parquet']`, no parts for 15, counter **1**; the identical fixture with `close()` first → `15.part0000.parquet` on disk, counter **0**.
3. **The hour held only a quarantined `.held` spill** — D1's headline case, counted on purpose (Global Constraints), because those rows were never corroborated and the hour is about to be certified from rows nothing confirmed. **Its evidence destroys itself, so say so:** opening the hour calls `_redeem_held`, which renames the spill into an ordinary `.part`, and the next rotation merges it into a certified `<HH>.parquet`. Measured: tree `['14.parquet', '15.held0000.parquet']` before the append, `['14.parquet', '15.part0000.parquet']` after it, counter **1**. An operator arriving minutes later finds a full, certified hour and files a real fabrication as a detector fault unless the entry warns them. **Redemption is silent** — the writer logs it nowhere; `_redeem_held`'s only log line is its `could not redeem` failure path — so neither the disk nor the log distinguishes a redeemed hour afterwards. Name the two checks that do survive: the writer's `first stamp opened a past hour` line, which carries the pair, kind and hour, and the peer machine's copy of that hour (the entry's step 3, *Compare that hour against the peer machine's copy*), taken **before** anything else touches the tree. `zcrypto_capture_rows_quarantined_total` on that host corroborates only when the spill happened to be scraped before the stop, which a `close()` spill usually is not (spec 00109 D3).
4. **A genuinely bogus past-dated stamp — the fabrication this alert exists for.** A first event carries a stamp naming an hour this host never captured; the plausibility guard bounds the future direction only and cannot refuse it, and the writer opens that hour. **On this host's disk it is indistinguishable from shapes 1 and 2** — no parts for the hour, no `.held` file, a restart on this machine — so nothing local separates it, and the two shapes it hides behind are the two the entry itself calls benign. The peer's copy takes it one step further and does not finish the job alone: an hour this host is short while the peer holds it whole is either a single-host outage (shape 1, where the stop, reboot or OOM is on the record) or this one, where **nothing accounts for the gap**. Say plainly that an unaccounted-for gap is filed as this shape — it is what the alert exists for, and the whole cost of a wrong call sits on the side that files it benign.

**The discriminator, because shapes 1, 2 and 4 look identical on this host's disk.** The peer comparison — the entry's own step 3, *Compare that hour against the peer machine's copy*, not this task's Step 3 — is therefore mandatory for **every** no-`.held` page, not a tie-breaker between 1 and 2. Read `RestartCount` and `StartedAt` (the entry's step 1, *Anchor it to a process start*, already gets them) and compare the hour against the peer. A gap on **both** machines spanning the hour is an outage backfill — shape 1. A restart on **this host only**, with the peer's copy of the hour intact and matching what this host now holds, is a crash replay — shape 2; a single-host crash leaves no gap on the peer, so "a gap on both" as the sole test misfiles it as a bad stamp. Neither is a fabrication. What is: this host still short against a peer copy that is whole, with **no** stop, reboot or crash on this host accounting for the gap — shape 4, where the rows never existed here and no replay is bringing them; the "matching" clause is the whole of what separates it from shape 2. And for shape 3 that comparison is the whole of the disk evidence, since the redemption renamed the rest away.

- [ ] **Step 3: State that the rule is a latch** (spec 00109 D2)

Absolute value does not self-clear; it stays firing until the capture process restarts. An operator waiting for a six-hour window to pass waits forever — and say plainly that clearing it means restarting live capture, which is a supervised act on the capture pair rather than something done to quiet a board.

**State the latch's second cost too, because it is a blind spot and Step 2's taxonomy makes it likely.** `max by (host)` yields one alert instance per `host`, so a counter stepping 1 → 2 changes `$v` and none of the instance's labels: Grafana sees no state transition and raises no new page. The step surfaces only as the numeral in the Slack template's `measured …` line on a repeat notification for an entry the operator has already filed — and shapes 1, 2 and 4 all page, with shape 2 named the likeliest first one, so the standing-latch case is the expected case rather than a corner. Bound it in the entry: **record the standing value in the ops-journal entry the page produces, and rule any later value above the recorded one a NEW event**, worked from the entry's step 1 (*Anchor it to a process start*) as if it had paged. Name where the latch actually clears — the next capture re-pin, which replaces the container and restarts the process anyway; a converge that changes neither the image nor the config does not restart it and does not clear it.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_infra_alert_rules.py -q`
Expected: PASS — and know what each one actually reads, because two of the three barely touch this edit. `tests/test_infra_alert_rules.py` is the file that reaches its real risk: it holds the summary-link, dashboard-link and index-routing guards, and a heading this rewrite renames or splits fails there and nowhere else. `test_code_prose_citations.py` reaches `infra/**/*.md` for one rule only — a `task <N>` token must carry its 5-digit serial. `test_internal_terms_not_operator_visible.py` does **not** scan `infra/runbooks/` at all beyond the repo-wide `WP<N>` ban, and `.claude/rules/operator-facing-text.md` does not list runbooks either: a `T<NNNN>` citation is legal here, `capture.md` already carries one in the limitation section's *Retire when*, and it must not be stripped to satisfy a ban that no test and no rule imposes on this file.

Both edited files are staged — `README.md`'s index row is Task 5's too, and Global Constraints' greps read the committed tree, so an edit left unstaged reads as a clean sweep:

```bash
git add infra/runbooks/capture.md infra/runbooks/README.md
git commit -m "docs(runbooks): the past-dated baseline is not a hard zero, and the rule is a latch"
```

**Then run Global Constraints' two committed-tree greps — this task is the last of the three they cover (2, 4, 5), so this is where they are owned.** They read `HEAD`, so they run after the commit above, and an edit left unstaged in any of the three tasks reads as a hit rather than as a clean sweep:

```bash
git grep -ni "hard.zero" HEAD -- infra/
git grep -niE "dated into|stamped into|already in the past|behind the (wall )?clock" HEAD -- infra/grafana/ infra/runbooks/ cli/capture/
```

Expected, for **both**: read every surviving hit against the invariant Global Constraints states, never a count. For the first that invariant is that no hit may still ASSERT the baseline — a hit that denies it, as Task 5's own commit subject does, is the correction landing and is not a hit to remove; rewriting a true sentence off an operator surface to empty this grep is the failure this expectation is worded to prevent. For the second it is that no hit describes the predicate without D1's no-capture conjunct; it returns the three members Global Constraints names as already reading correctly, plus whatever survives the two `cli/` rewrites. The total is not the test; a single hit failing its invariant is, whatever the total.

---

### Task 6: The landing order reaches the surface that performs the push

**Files:**
- Modify: `.claude/rules/fleet-deploys.md` — the "Alert-rule lifecycle" section

Spec D7 rules on how an operation must be performed, and today it lands nowhere the operator meets it: Global Constraints are read by this plan's implementer, and the topic note in Task 7 is read by whoever picks the topic up. Neither is the daily pass, which prepares `grafana-push.sh` after a merged rule fix precisely because it changes what pages — and this PR merges exactly such a fix days before the capture image can carry D1 through its bake. **The constraint is on the whole push, not on one rule**: the script has no per-rule mode.

- [ ] **Step 1: The sign-off gate — before any edit to the file**

`.claude/rules/fleet-deploys.md` is in the **protected set** (`.claude/skills/zcrypto-refine-rules/SKILL.md`): every edit to it takes the user's explicit per-edit sign-off, and a plan's authority is not that sign-off — the point of the rule is that the corpus policing a change cannot be altered by that change. The owner signed off on this task's bullet on 2026-09-01 after reading it verbatim; Step 2's text has since been rewritten (it now forbids running the script rather than pushing one rule), and **sign-off attaches to text, so the rewritten bullet needs the word again before it lands**. Show it verbatim, land exactly what is approved, and change nothing else in the file.

**Under unattended execution this task stops here, and so does the PR.** The loop's landing rule (`.claude/skills/zcrypto-auto-exec/SKILL.md`) is that a component includes its attended tail, so this branch stays a reviewed, **pushed branch with NO PR**, named in T0037 and in the memo item's `DependsOn:`; the attended session lands Task 6 and opens the single PR. Never report the branch "complete" — that word is what licenses the merge, and a merge without this bullet ships the rule-form change with D7's constraint on no surface at all. The same stop fires under this plan's own execution mode: a subagent cannot obtain the owner's per-edit sign-off either, so under `subagent-driven-development` the sign-off **and** the edit are the orchestrator's, taken in the main loop. Every other task here is landable without Task 6; none of them is deliverable without it.

- [ ] **Step 2: Add one bullet under "Alert-rule lifecycle"**

State the constraint, not its history, and word it against the tool that exists. `infra/scripts/grafana-push.sh` pushes every dashboard and every rule in `alerts.yaml` in one run — its only selection env vars are `GRAFANA_URL`, the two datasource uids, the folder uid and `GRAFANA_PRUNE` — so an agent told "do not push THIS rule" has only two moves without a hatch, and neither is what we want: freeze every other rule and dashboard change for the days the bake and the two re-pins take, or push and ship this rule early. The bullet gives it a third. The bullet:

> - **`grafana-push.sh` waits for the capture pair — do not run it while `alerts.yaml`'s `zcrypto-capture-ts-past-dated-hour` reads `max by (host)` AND either capture host could still be running without the narrowed past-dated predicate.** The script upserts every rule in `alerts.yaml`, so there is no "push only the others", and pushing early latches a CRITICAL on the capture pair against a standing benign value, clearable only by restarting live capture. Checkable from repo state: for each capture row in `docs/reference/fleet-pins.md` take the row's build revision — the file's digest list names each digest's revision — and run `git show <revision>:cli/capture/segment_writer.py | grep -qF 'and not self._parts_for(self._hour_dir(hour)'`; both rows must pass, and a PASS counts only against a row whose `since` matches that host's current container start — `zcrypto-rollout-image`'s Phase-4 rollback is a hand compose re-pin that appends no deploy-log line and re-trues no pins row, so a stale row passes for a host that would fail. **A rollback re-arms this.** `zcrypto-rollout-image`'s Phase 4 re-pins to the row's rollback operand, which carries the wide predicate until a capture rollout lands on top of the one that introduced it — so a capture rollback taken after that rule was pushed takes the hatch AND pushes it before the host restarts, because the LIVE rule keeps evaluating `max by (host)` until something pushes the revert; a rollback taken before it was ever pushed still re-arms the hazard, and the freshness qualifier above is what catches it. **The hatch, for a rule that must ship inside the window:** `git revert` the commit whose subject is `fix(obs): a start-correlated counter is the one increase() cannot read`, through a PR into `develop` — that revert takes the rule, its unit, its horizon, its latch sentence and its panel series back together and clears this condition on its own — then re-land by reverting the revert once both rows' build revisions pass again. **Retire this bullet only when both rows' rollback operands pass the same test**, because until then a rollback can re-arm the hazard with nothing on any surface saying so.

It belongs in the same section as the existing push-ordering imperatives. **The do-not-push condition IS spec D7's** — both hosts carry D1, verified by digest rather than by reading the counter — so the operating surface and the spec state one condition, not two; the rollback operands gate this bullet's REMOVAL and nothing else. That split is what keeps the retirement sound: both rows carry a pre-D1 operand until one rollout after this one, and Phase 4 re-pins to exactly that operand on any bake abort, so a bullet retired on the running revisions alone would leave a rollback able to re-arm the hazard silently — while a bullet whose *push* gate waited on the operands would hold D2's fix for an interval nothing schedules. Its retirement is registered as a T0037 next step in Task 7 Step 4: a one-rollout imperative in the always-loaded corpus outlives its rollout unless something schedules its removal, and this file is protected, so a later agent cannot quietly drop it either.

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

Spec D8's **by-value alert proof and its silent control** — named rather than numbered, so a bullet inserted later cannot misroute this — are measurements, and no repo check can discharge them. They come in two dated halves, and only the first exists at closeout. **Write the first; register the second — never write it.**

1. **Before the re-pin, already measured (2026-09-01T19:2xZ) — this is what the entry records**: `max by (host) (zcrypto_capture_ts_past_dated_hour_total{...})` reading `{host=zcrypto-red} = 1` against `increase(...[6h])` reading 0, with `max by (host) (zcrypto_capture_hour_finalized_early_total{...})` at 0 on the same host as the silent control. This is the whole of the proof that the replacement expression can see the event D2 says `increase()` cannot; the re-pin D7 gates the push on clears the counter, so it is copied into the entry from this measurement and never re-hunted at the push. Its values are carried in this plan, which is their durable home; `infra/scripts/grafana-query.py` is the instrument that took them.
2. **At the wave, after both hosts re-pin — OWED, not written here**: both hosts' values under the absolute-value form, which are D7's own both-read-0 confirmation and the two-host control D8's last bullet names. The wave happens after this branch merges (Global Constraints), so at closeout these readings do not exist; a number predicted as "0 by construction" and dated with the closeout date would be a control asserted rather than taken, and shape 2 is enough to make the prediction wrong. The entry says the half is owed and where it lands; Step 4's next-step line is what registers it against the operator who takes it.

The entry therefore carries half 1 with its date and the sentence that half 2 is owed at the wave. Without that, nobody after the branch can tell whether the proof was ever taken, or mistake a post-re-pin 0 for a failed replacement.

- [ ] **Step 3: Settle the out-of-scope deferral**

`zcrypto-capture-rows-quarantined`'s exposure is stated in the spec, in Global Constraints and in this Self-review, and **three prose homes are not a registration**. A new topic file needs the user's explicit word, so ask for it at closeout in the same breath as the summary; if it is declined, write the explicit drop into the closeout entry instead, **with the reason as Global Constraints states it** — per increment site, not "absolute value does not fix it" unqualified, which reads as a claim about the whole counter and is not one. Do not let this merge as prose.

- [ ] **Step 4: Update T0037, frontmatter included**

Name the fields, because the PR touching a topic carries its whole update:

- `ripe_when:` — today it describes the `00103` sequence "deploy the detectors, read each family by value on both hosts, push the alert rules". D7 supersedes that order (re-pin both hosts, verified by digest → push → read by value); rewrite it and re-sync the echoing bullet in `docs/open-topics/README.md` through the `topic-ops` skill.
- `## Done so far` — its past-dated bullet describes the detector as "gated on the oracle", which is now half the predicate. Add the disk-evidence half.
- `## Done so far`'s **"Detectors built, not yet deployed"** heading and its lead sentence, *"Each accepted residual now has a signal, and none has run on a capture host"* — false since the 2026-09-01 re-pin put `3fb8f4f5`'s counters on `zcrypto-red` (spec D4); `zcrypto_capture_ts_past_dated_hour_total{host="zcrypto-red"}` read 1 that day. The counters were merged 2026-08-29, which is not the same date and is not the one this sentence turns on — the primary's pin still predates them, which is why no primary series existed to read. Rewrite it to name that reading and the wide predicate that produced it, or the topic merges asserting the detector has emitted nothing while its `ripe_when` is rewritten around clearing what it emitted.
- `## Done so far`'s **"Why this topic is still `partial`"** closure sentence, *"The detectors exist in the repo and have emitted nothing in production… It closes after the attended rollout deploys them and each family is read by value on both hosts."* — its first clause is false, and its second restates `00103`'s landing order, which D7 inverts. Rewrite to D7's order, so the body and the `ripe_when` above it do not prescribe two different waves.
- `status:` stays **`partial`**, and say so: the rule's field list is `status`, `ripe_when`, `## Done so far`, removal of the finished next-step, so a field left unnamed reads as an oversight rather than a decision. The topic's three residuals are unchanged; only the past-dated detector's predicate is repaired here.
- `## Suggested next steps` — the residuals stay detection-based, which remains true; add the landing-order constraint so the Grafana push is not taken early, **and its own close-out in the same line**, in the bullet's own two stages: when both capture rows' **build revisions** carry the predicate, re-land the absolute-value form by reverting the revert if the escape hatch was taken, and push; **read both hosts' `max by (host)` values after the re-pin — D7's own last check — and record them with their date in this topic**, which is D8's owed half 2 and the one part of the proof this branch cannot write; then, when both rows' **rollback operands** carry it too, remove the landing-order bullet from `.claude/rules/fleet-deploys.md` (a protected-file edit, so it takes the same sign-off Task 6 Step 1 describes). Nothing else schedules the re-land, the reading or the removal, and a plan sentence is not a registration. **If Task 6 was parked, this line registers the bullet itself as OWED**, not merely its eventual removal — the attended session lands it before any push.

- [ ] **Step 5: Commit**

```bash
git add docs/iterations-history-phase1.md docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md docs/open-topics/README.md
git commit -m "docs(capture): iter-<N> closeout -- the detector's predicate now matches its spec"
```

---

## Self-review

**Spec coverage.** D1 → Tasks 1–3 (Task 1 Steps 3 and 4 pin the `.held` marker and the floor the `.part`-only test rests on). D2 → Task 4 Steps 1–2 (expression and the strings it falsifies) + Task 5 Step 3 (the latch on the operator surface). D3 → Task 4's scope, which converts one rule and states why the sibling keeps `increase()`; the `rows_quarantined` half is out of scope and Task 7 Step 3 owes it a registration or an explicit drop. D4 → Task 4 Step 5. D5 → Task 5 (three hard-zero sites in two runbook files, plus that entry's pre-D1 opening paragraph) + Task 4 Steps 2–3 (the rule block's copies and panel 110's), both sets closed by Global Constraints' two greps rather than by any list. D6 → Task 5 Step 1, as a dated note in the runbook — the pins map names digests, not what a value means, and this plan authors no pins row. D7 → Task 6, on the operating surface, plus the PR body; the Grafana push itself is deliberately not a task here, and Task 6 Step 1 is a sign-off gate rather than an edit because that file is protected. D8 → Tasks 1–5's verification steps for the code guard, and Task 7 Steps 2 and 4 for the two bullets that are measurements rather than repo checks: Step 2 records the half already taken, Step 4 registers the half the wave still owes, because nothing on this branch can measure it.

**Placeholder scan.** One deliberate: `iter-<N>` in Task 7's commit message, which is not knowable until closeout.

**Type consistency.** `_parts_for(hour_dir, hh, *, marker=".part")` and `_hour_dir(hour)` are used in Task 2 exactly as `_open_hour` already calls them at the same file's line ~644 — and that duplication is why Task 2 Step 5's marker mutation is anchored on `and not `, since `sed -i` would otherwise rewrite both call sites.

**Commit-kind split.** Task 6 is the branch's only `.claude/**` change and commits alone; every other commit is code, tests, `infra/` or `docs/`. Task 4 lands two `infra/`-kind commits rather than one — the prose that holds under either expression form, then the form move — so Task 6's escape hatch is a `git revert` of a named subject instead of six strings re-edited by hand under time pressure — and Task 4 Step 6's last block reads the two commits' own trees, because nothing in the repo can otherwise tell a correct split from a collapsed one.

**The thing most likely to be wrong.** Task 1's re-open fixture depends on `flush_rows=5` actually producing a `.part` file for hour 15 *and* on that hour never being finalized — a finalized hour would raise the recovery floor above it and the stamp would be dropped as late instead, which is a different (and passing) test. Step 1's glob assert covers the first; Step 4's floor test covers the second by asserting the opposite case explicitly.
