# Soak identity NaN refusal — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `realized_internals` refuses a comparison it could not make, so a NaN journaled target voids the soak run instead of reporting the identity holding over it.

**Architecture:** One counter beside `compared` in `realized_internals`' comparison loop, one new field on `RealizedInternals`, one branch-ordering decision after the loop, and one void-reason branch in `soak_report`. No new module, no new helper, no change to what `tol` or `compared == 0` mean.

**Tech Stack:** Python 3.14, `uv run pytest`. `math.isfinite` is already imported in `cli/engine/soak.py`.

**Spec:** `docs/specs/00113-soak-identity-nan-refusal-design.md`

## Global Constraints

- The refusal goes at the comparison in `cli/engine/soak.py`. Do **not** add `validate_record` to any read path — that is `T0194` and out of scope (spec `## Out of scope`).
- Do **not** catch `ValueError` in `realized_internals` or `soak_report`, and do not add a finiteness check to `_validate_grid` — that is `T0193` and out of scope, because it carries an unanswered design question.
- Do not touch `cap_consistent` or its `breach` comparison.
- `compared` keeps its present meaning: comparisons actually made. A non-finite `diff` increments `unmeasurable` instead (spec D2).
- The unmeasurable check is evaluated **before** the `compared == 0` arm (spec D4). Reversing the order makes the all-NaN window report `None`, which does not void.
- Every new fixture is NaN-ONLY (spec D7): the journaled target is `float("nan")` and every other value matches the rebuilt row exactly. A fixture that also mismatches by magnitude passes under the defect for the wrong reason.
- `cli/engine/soak.py` is inside `replay_fingerprint`'s import closure, so any change here invalidates the gate cache and the next run pays a cold replay. Expected for a code fix; do not treat it as a regression.

---

### Task 1: The unmeasurable arm in `realized_internals`

**Files:**
- Modify: `cli/engine/soak.py` — the `RealizedInternals` dataclass (~`:756-765`), the `except` branch's construction (~`:828-837`), the comparison loop (~`:853-884`), and the return (~`:888-898`)
- Test: `tests/test_engine_soak.py` — the `# --- realized_internals ---` section that begins at `:2561`

**Interfaces:**
- Produces: `RealizedInternals.identity_unmeasurable: int` — the number of `(record, asset)` pairs whose `diff` was not finite. `0` on every existing path, including the `available=False` construction. Task 2 consumes it.

- [ ] **Step 1: Write the failing test**

Add beside `test_realized_internals_shift_breaks_identity` in `tests/test_engine_soak.py`. It reuses the module-level `_fake_result` (`:307`) with that section's own `_mk_h4_snapshot_record` (`:2564`) and `_mk_scored_record` (`:2610`), so no builder runs and the test does not depend on the incidental `ValueError` the fast path raises on a NaN price.

```python
def test_realized_internals_refuses_an_identity_it_could_not_measure(monkeypatch):
    """NaN-ONLY, by construction: the one journaled target is `nan` and nothing else disagrees, so
    under the defect both `diff >= worst_diff` and `diff > tol` are False, `worst_diff` never moves,
    and the window reports the identity holding over a comparison nobody could make."""
    base = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    n = 4
    h4_ts = [base + timedelta(hours=4 * k) for k in range(n + 1)]
    closes = [100.0 + k for k in range(n + 1)]
    B = A1 = A2 = [0.09, 0.12, 0.06, 0.03, 0.0]
    mult = [1.0] * (n + 1)
    fake = _fake_result(n_periods=n, sleeve_B=B, sleeve_A1=A1, sleeve_A2=A2, multipliers=mult, governed_net=[0.0] * n)
    monkeypatch.setattr(soak, "build_crossfreq_system_fast", lambda *a, **kw: fake)

    latest, reader = _mk_h4_snapshot_record(h4_ts[-1] + timedelta(hours=4), h4_ts, closes)
    nan_only = [_mk_scored_record(h4_ts[1] + timedelta(hours=4), {"BTC": float("nan")})]

    ri = realized_internals(nan_only, latest, reader)
    assert ri.available is True and ri.reason == ""
    assert ri.identity_ok is False, ri.identity_detail
    assert ri.identity_unmeasurable == 1
    assert "unmeasurable" in ri.identity_detail and "BTC" in ri.identity_detail
```

- [ ] **Step 2: Run it and read WHICH failure fired**

Run: `uv run pytest tests/test_engine_soak.py::test_realized_internals_refuses_an_identity_it_could_not_measure -v`
Expected: FAIL on `AttributeError: 'RealizedInternals' object has no attribute 'identity_unmeasurable'`, or — once the field exists — on `assert ri.identity_ok is False` with `identity_ok` reading `True`. The second is the defect; read the message rather than the exit code.

- [ ] **Step 3: Add the field to `RealizedInternals`**

```python
    identity_ok: bool | None  # None = no journaled target was compared, so the identity went unmeasured
    identity_unmeasurable: int  # pairs whose |diff| was not finite: counted, never compared (spec 00113 D2)
    identity_detail: str
```

Set `identity_unmeasurable=0` in the `available=False` construction in the `except (EngineError, PortfolioError)` branch, beside `identity_ok=False`.

- [ ] **Step 4: Count the unmeasurable pairs in the loop**

Replace the inner loop's body. `continue` is what keeps `compared` meaning comparisons actually made:

```python
    identity_ok: bool | None = True
    compared = 0
    unmeasurable = 0
    unmeasurable_detail = ""
    worst_diff = 0.0
    worst_detail = "n/a"
```

```python
            diff = abs(row[a] - value)
            # Keyed on the diff's finiteness, never on which operand produced it (spec 00113 D2):
            # `nan` and two MATCHING infinities are both False against the bars below, so counting
            # either as compared reports the identity holding over a comparison nobody could make.
            if not math.isfinite(diff):
                unmeasurable += 1
                if not unmeasurable_detail:
                    unmeasurable_detail = f"cycle={t!r} asset={a!r}"
                continue
            compared += 1
            if diff >= worst_diff:
                worst_diff = diff
                worst_detail = f"cycle={t!r} asset={a!r}"
            if diff > tol:
                identity_ok = False
```

Note the `compared += 1` moved BELOW the `diff` computation; it was above it before.

- [ ] **Step 5: Order the two arms, and extend the detail**

```python
    # Order is load-bearing (spec 00113 D4): an all-NaN window has `compared == 0` as well, and
    # reaching the `None` arm first would report it unmeasured -- which appends no void reason.
    if unmeasurable:
        identity_ok = False
    elif not compared:
        # Nothing compared: `True` here would report agreement never measured.
        identity_ok = None
    identity_detail = f"worst |diff|={worst_diff!r} at {worst_detail}"
    if unmeasurable:
        identity_detail += f"; {unmeasurable} unmeasurable at/after {unmeasurable_detail}"
```

Pass `identity_unmeasurable=unmeasurable` in the successful return.

- [ ] **Step 6: Run the section and confirm the true positive is still green**

Run: `uv run pytest tests/test_engine_soak.py -k realized_internals -v`
Expected: PASS, including `test_realized_internals_identity_holds` (the true positive — a healthy window still reporting `identity_ok: True`), `test_realized_internals_identity_is_unmeasured_with_no_scored_record` (`identity_ok is None` unchanged, both its routes), and `test_realized_internals_shift_breaks_identity`.

- [ ] **Step 7: Prove the guard bites**

Run, from the repo root on a clean tree:

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/^    if unmeasurable:$/    if False:/' \
  -- uv run pytest tests/test_engine_soak.py -k realized_internals -q
```

The mutation deletes the arm under proof — the ordering decision of Step 5 — and must report KILLED. The control widens `tol` so the shift test's mismatch stops being detected, and must FAIL, which is how the probe proves it is measuring. Read which assertion fired, not the exit code. `--collect-only` the `-k` filter first: it must select the four `realized_internals` tests and not deselect the new one.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/soak.py tests/test_engine_soak.py
git commit   # body names the mutation constructed and the assertion that fired (commit-messages.md)
```

---

### Task 2: The void reason names which of the two happened

**Files:**
- Modify: `cli/engine/soak.py` — the void-reason branch at `:1718-1719`, and the internals payload at `:1529-1530`
- Test: `tests/test_engine_soak.py`

**Interfaces:**
- Consumes: `RealizedInternals.identity_unmeasurable` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
def test_an_unmeasurable_identity_voids_under_its_own_reason(monkeypatch):
    """A mismatch and an unmeasurable comparison are different operator actions -- the rebuild
    disagreeing with what was journaled, against a journaled value that is not a number."""
    ...  # build a payload through soak_report's normal path with a NaN journaled target
    assert "realized-internals identity unmeasurable" in payload["void_reasons"]
    assert "realized-internals identity mismatch" not in payload["void_reasons"]
    assert payload["internals"]["identity_unmeasurable"] == 1
```

Model the harness on the existing `soak_report` tests in this file rather than inventing one; if no existing test reaches `soak_report`'s internals branch with a controllable record set, assert on `analyze_soak`/the payload builder at `:1529` and on the void-reason branch through a constructed `RealizedInternals` instead, and say so in the commit body.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_engine_soak.py::test_an_unmeasurable_identity_voids_under_its_own_reason -v`
Expected: FAIL — the payload carries `realized-internals identity mismatch`, the wrong reason.

- [ ] **Step 3: Branch the reason and publish the count**

```python
            if internals.available and internals.identity_ok is False:
                # Both can hold at once; the unmeasurable case is the weaker claim and names the
                # reason, and `identity_detail` carries the worst measured diff beside the count.
                void_reasons.append(
                    "realized-internals identity unmeasurable"
                    if internals.identity_unmeasurable
                    else "realized-internals identity mismatch"
                )
```

And in the internals payload beside `"identity_detail"`:

```python
            "identity_unmeasurable": internals.identity_unmeasurable,
```

- [ ] **Step 4: Run the file**

Run: `uv run pytest tests/test_engine_soak.py tests/test_engine_soak_command.py -q`
Expected: PASS. A payload-shape test that enumerates the internals keys will need the new key added — that is the change, not a break.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/soak.py tests/test_engine_soak.py
git commit
```

---

### Task 3: Closeout

**Files:**
- Modify: `docs/open-topics/T0188-soak-identity-check-counts-a-nan-comparison-as-passed.md`, `docs/open-topics/README.md`
- Modify: `docs/iterations-history-phase6.md`

- [ ] **Step 1: Resolve T0188 through the `topic-ops` skill**

Load `.claude/skills/topic-ops/SKILL.md` and follow it: `status: resolved`, a `## Resolution` naming the commits and what each decision landed as, `git mv` into `docs/open-topics/archive/`, and the index bullet moved to the same category's `### Resolved` with its link repointed at `archive/`. The topic's three open decisions are answered by spec `00113` D1, D2/D3 and D5/D6 — say which, so the archived file records the answers rather than the questions.

- [ ] **Step 2: The changelog entry**

The soak report's void reasons and its `--json` internals block are surfaces an agent and an operator act on, so an entry is owed (`prose.md`). One-line bullets, one per changed surface, each saying what a reader now does differently. Load `.claude/skills/iteration-closeout/SKILL.md` for the file mechanics.

- [ ] **Step 3: Verify the reach, once, on the final tip**

`git grep -l "soak" -- tests/` names the reachable files; run `tests/test_engine_soak.py` and `tests/test_engine_soak_command.py` at minimum, plus `tests/test_code_prose_citations.py` (the new spec/plan/topic citations must resolve) and `tests/test_internal_terms_not_operator_visible.py` (the new void-reason string is runtime output from `cli/`). Then `uv run pre-commit run -a`.

- [ ] **Step 4: Commit**

```bash
git add docs/open-topics docs/iterations-history-phase6.md
git commit
```
