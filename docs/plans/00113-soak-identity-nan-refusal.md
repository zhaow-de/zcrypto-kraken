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
- The defect fixture is NaN-ONLY (spec D7): the journaled target is `float("nan")` and every other value matches the rebuilt row exactly. A fixture that also mismatches by magnitude passes under the defect for the wrong reason — so the one non-NaN fixture the plan carries, the `float("inf")` target that tells finiteness-keying from NaN-keying (spec `## The measured basis`), asserts on `identity_unmeasurable` and never on `identity_ok`, which the defect already drives `False` there.
- `cli/engine/soak.py` is inside `replay_fingerprint`'s import closure, so any change here invalidates the gate cache and the next run pays a cold replay. Expected for a code fix; do not treat it as a regression.

---

### Task 1: The unmeasurable arm in `realized_internals`

**Files:**
- Modify: `cli/engine/soak.py` — the `RealizedInternals` dataclass (~`:756-765`), the `except` branch's construction (~`:828-837`), the comparison loop (~`:853-884`), and the return (~`:888-898`)
- Test: `tests/test_engine_soak.py` — the `# --- realized_internals ---` section that begins at `:2561`, plus the four `RealizedInternals(` construction sites Step 3 enumerates
- Test: `tests/test_engine_soak_command.py` — `_fake_realized_internals` inside `_patch_canonical_pipeline` (`:161`), whose stub construction at `:191` is the fifth test-side site

**Interfaces:**
- Produces: `RealizedInternals.identity_unmeasurable: int` — the number of `(record, asset)` pairs whose `diff` was not finite. `0` on every existing path, including the `available=False` construction. Task 2 consumes it.
- Produces: `_patch_canonical_pipeline`'s `identity_unmeasurable: int = 0` keyword (`tests/test_engine_soak_command.py:161`), threaded into its stub exactly as `identity_ok` already is. Task 2 consumes it.

- [ ] **Step 1: Write the failing test**

Add beside `test_realized_internals_shift_breaks_identity` in `tests/test_engine_soak.py`. It reuses the module-level `_fake_result` (`:307`) with that section's own `_mk_h4_snapshot_record` (`:2564`) and `_mk_scored_record` (`:2610`), so no builder runs and the test does not depend on the incidental `ValueError` the fast path raises on a NaN price.

Three windows, each pinning something the others cannot. An all-NaN window has `compared == 0` as well, so it is satisfied by the narrower `if unmeasurable and not compared:` too; only a window with a measured comparison beside the unmeasurable one pins spec `00113` D3's *any*; and only an infinite target tells D2's finiteness-keying from a NaN test.

```python
def test_realized_internals_refuses_an_identity_it_could_not_measure(monkeypatch):
    """One journaled target is not a number and nothing else disagrees: the pair is counted
    unmeasurable, never compared, and the identity refuses rather than holding -- over a window where
    that is the only pair, over one where a measured comparison stands beside it, and over an
    infinite target, which is unmeasurable for the same reason a NaN one is."""
    base = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    n = 4
    h4_ts = [base + timedelta(hours=4 * k) for k in range(n + 1)]
    closes = [100.0 + k for k in range(n + 1)]
    B = A1 = A2 = [0.09, 0.12, 0.06, 0.03, 0.0]
    mult = [1.0] * (n + 1)
    fake = _fake_result(n_periods=n, sleeve_B=B, sleeve_A1=A1, sleeve_A2=A2, multipliers=mult, governed_net=[0.0] * n)
    monkeypatch.setattr(soak, "build_crossfreq_system_fast", lambda *a, **kw: fake)

    latest, reader = _mk_h4_snapshot_record(h4_ts[-1] + timedelta(hours=4), h4_ts, closes)
    nan_rec = _mk_scored_record(h4_ts[1] + timedelta(hours=4), {"BTC": float("nan")})

    ri = realized_internals([nan_rec], latest, reader)
    assert ri.available is True and ri.reason == ""
    assert ri.identity_ok is False, ri.identity_detail
    assert ri.identity_unmeasurable == 1
    assert "unmeasurable" in ri.identity_detail and "BTC" in ri.identity_detail

    # `compared == 0` holds above too, so that window alone cannot tell the arm from the narrower
    # `if unmeasurable and not compared:`. Here one comparison IS made and agrees, and the refusal
    # is spec 00113 D3's "any" rather than "nothing was measured".
    agreeing = _mk_scored_record(h4_ts[3] + timedelta(hours=4), {"BTC": fake.final_targets["BTC"][3]})
    mixed = realized_internals([nan_rec, agreeing], latest, reader)
    assert mixed.identity_ok is False, mixed.identity_detail
    assert mixed.identity_unmeasurable == 1
    assert "at n/a" not in mixed.identity_detail  # the measured pair moved `worst_detail` (spec D5)

    # Keyed on the diff's finiteness, never on NaN (spec 00113 D2): an infinite journaled target
    # against a finite rebuilt row is unmeasurable, where `math.isnan(diff)` would count it compared
    # and report a mismatch. `identity_ok` is False under the defect too, so it cannot carry this.
    inf_rec = _mk_scored_record(h4_ts[1] + timedelta(hours=4), {"BTC": float("inf")})
    infinite = realized_internals([inf_rec], latest, reader)
    assert infinite.identity_unmeasurable == 1
    assert infinite.identity_ok is False, infinite.identity_detail
```

- [ ] **Step 2: Run it and read WHICH failure fired**

Run: `uv run pytest tests/test_engine_soak.py::test_realized_internals_refuses_an_identity_it_could_not_measure -v`
Expected: FAIL on the first window's `assert ri.identity_ok is False` with `identity_ok` reading `True` and `identity_detail` reading `worst |diff|=0.0 at n/a` — the defect itself. That assertion fires before `ri.identity_unmeasurable` is ever evaluated, so an `AttributeError` on the missing field is NOT the red to expect; read the message rather than the exit code.

- [ ] **Step 3: Add the field to `RealizedInternals`, and thread it through every construction site**

```python
    identity_ok: bool | None  # None = no journaled target was compared, so the identity went unmeasured
    identity_unmeasurable: int  # pairs whose |diff| was not finite: counted, never compared (spec 00113 D2)
    identity_detail: str
```

The dataclass carries no field defaults and this field takes none either: a producer that omits the count is a `TypeError` at construction, where a defaulted `0` would sit silently beside an `identity_ok=False` and make Task 2's branch read it as a mismatch. The cost is that every existing construction site changes in this task. The family is `grep -rn "RealizedInternals(" cli/ tests/ infra/` — seven sites, five of them in tests, none of them inside Step 6's `-k realized_internals` selection:

| Site | What to pass |
| --- | --- |
| `cli/engine/soak.py:828` — the `except (EngineError, PortfolioError)` branch | `identity_unmeasurable=0`, beside `identity_ok=False` |
| `cli/engine/soak.py:890` — the successful return | `identity_unmeasurable=unmeasurable` (Step 5) |
| `tests/test_engine_soak.py:1150` — `_mk_internals`, the helper 13 tests call | `identity_unmeasurable=0` |
| `tests/test_engine_soak.py:1496` | `identity_unmeasurable=0` |
| `tests/test_engine_soak.py:1862` | `identity_unmeasurable=0` |
| `tests/test_engine_soak.py:1935` | `identity_unmeasurable=0` |
| `tests/test_engine_soak_command.py:191` — `_fake_realized_internals`, inside the `_patch_canonical_pipeline` helper 12 tests call | `identity_unmeasurable=identity_unmeasurable`, from a new `identity_unmeasurable: int = 0` keyword parameter added beside `identity_ok`, threaded exactly as `identity_ok` already is — Task 2 sets it |

`tests/test_engine_soak_command.py:252`'s full-dict `payload["internals"]` equality does **not** change here: the payload gains its key in Task 2, not in this task.

- [ ] **Step 4: Count the unmeasurable pairs in the loop**

Replace the inner loop's body **from `compared += 1` onward** — the `a not in row` refusal at `:871-872` is shown below unchanged so the boundary is unambiguous. Deleting it would leave `row[a]` raising a bare `KeyError`, which is neither `EngineError` nor `PortfolioError` and so escapes both `realized_internals`' degrade branch and `soak_report`. `continue` is what keeps `compared` meaning comparisons actually made:

```python
    identity_ok: bool | None = True
    compared = 0
    unmeasurable = 0
    unmeasurable_detail = ""
    worst_diff = 0.0
    worst_detail = "n/a"
```

```python
            if a not in row:
                raise SoakError(f"cycle {t!r}: asset {a!r} not in the rebuilt universe {sorted(row)}")
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
    identity_detail = f"worst |diff|={worst_diff!r} at {worst_detail}"
    # Order is load-bearing (spec 00113 D4): an all-NaN window has `compared == 0` as well, and
    # reaching the `None` arm first would report it unmeasured -- which appends no void reason.
    if unmeasurable:
        identity_ok = False
        identity_detail += f"; {unmeasurable} unmeasurable at/after {unmeasurable_detail}"
    elif not compared:
        # Nothing compared: `True` here would report agreement never measured.
        identity_ok = None
```

One `if unmeasurable:` decides the verdict (D3) and the detail (D5) together, so the two cannot disagree — and the line the Step-8 mutations rewrite matches exactly once in the file, which a second `if unmeasurable:` guarding the detail separately would break.

Pass `identity_unmeasurable=unmeasurable` in the successful return.

- [ ] **Step 6: Run both files and confirm the true positive is still green**

Run: `uv run pytest tests/test_engine_soak.py tests/test_engine_soak_command.py -q`

Both files, not the `-k realized_internals` filter — that filter selects none of Step 3's five test-side construction sites, so it would report PASS over a tree where every test reaching one of them raises `TypeError`. (The filter's one remaining use is Step 8's probe selection, run against a tree this step has already proven green.)

Expected: PASS, including `test_realized_internals_identity_holds` (the true positive — a healthy window still reporting `identity_ok: True`), `test_realized_internals_identity_is_unmeasured_with_no_scored_record` (`identity_ok is None` unchanged, both its routes), `test_realized_internals_shift_breaks_identity`, and `test_realized_internals_asset_outside_universe_raises` — the last of which reds with a `KeyError` if Step 4 took the `a not in row` refusal with it.

- [ ] **Step 7: Commit**

```bash
git add cli/engine/soak.py tests/test_engine_soak.py tests/test_engine_soak_command.py
git commit
```

- [ ] **Step 8: Prove the guard bites, then amend the body with the verdict**

The probe runs AFTER the commit: `infra/scripts/mutate-probe.sh` refuses a dirty worktree outright (rc 3 — restore is `git checkout --`, which would destroy uncommitted work), and `--sandbox`, its only other mode, refuses any probe command containing `pytest`. Stashing is not the way round it — the stash stack is shared with the other worktrees. So run the probes here and land the result with `git commit --amend`, whose body names the mutations constructed and the assertions that fired (`commit-messages.md`).

`--collect-only` the `-k` filter first:

```bash
uv run pytest --collect-only -q tests/test_engine_soak.py -k realized_internals
```

It must select every `test_realized_internals_*` test and deselect none of them — 10 on this branch's base, 11 with the new one. Do not narrow the filter to make a number match: the wider set is what carries the probe's true positives, including the schema-2 and real-journal tests that walk the same loop.

Two mutations, one probe run each, same control. Both must report KILLED, and the control must FAIL in both, which is how the probe proves it is measuring — it widens `tol` so `test_realized_internals_shift_breaks_identity`'s mismatch stops being detected. Read which assertion fired, not the exit code.

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/^    if unmeasurable:$/    if False:/' \
  -- uv run pytest tests/test_engine_soak.py -k realized_internals -q
```

Deletes the arm under proof, which is Step 5's ordering decision: the all-NaN window falls through to `identity_ok = None` and the first window's `assert ri.identity_ok is False` fires.

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/^    if unmeasurable:$/    if unmeasurable and not compared:/' \
  -- uv run pytest tests/test_engine_soak.py -k realized_internals -q
```

Narrows the arm to the reading Step 5's own comment invites. The all-NaN window still passes under it; only Step 1's mixed window kills it, on `assert mixed.identity_ok is False`. If this one reports SURVIVED, the mixed window is not discriminating and the fixture is the thing to fix.

---

### Task 2: The void reason names which of the two happened

**Files:**
- Modify: `cli/engine/soak.py` — the void-reason branch at `:1718-1719`, and the internals payload at `:1529-1530`
- Test: `tests/test_engine_soak_command.py` — `test_soak_check_void_wiring_for_internals` (`:270`) and the full-dict payload equality at `:252`

**Interfaces:**
- Consumes: `RealizedInternals.identity_unmeasurable` and `_patch_canonical_pipeline`'s `identity_unmeasurable` keyword, both from Task 1.

- [ ] **Step 1: Write the failing assertion, as a fourth arm of the existing wiring test**

`tests/test_engine_soak.py` reaches `soak_report` nowhere — `grep -n "soak_report" tests/test_engine_soak.py` returns two comment lines and no call — so the test belongs in `tests/test_engine_soak_command.py`, beside the guard that already pins the other reason string: `test_soak_check_void_wiring_for_internals` (`:270`) asserts `any("identity mismatch" in r for r in payload["void_reasons"])` under `identity_ok=False`. A fourth arm there decides both strings in one run, with the mismatch arm standing as its true positive.

`_patch_canonical_pipeline` stubs `realized_internals`, the PRODUCER of the count; `soak_report` still computes `void_reasons` itself, so the branch under test is the live one. Task 1's `test_realized_internals_refuses_an_identity_it_could_not_measure` is what pins that a NaN journaled target produces the count; this arm pins which string the branch picks given it.

Place the arm after the `identity_ok=False` one and before the `identity_ok=None` one, and extend the test's docstring to state the claim the new assertions make:

```python
    # A journaled value that is not a number and a rebuild that disagrees by magnitude are different
    # operator actions, so they take different reasons. The branch sees only the count, which is how
    # it names the unmeasurable case when both hold (spec 00113 D6).
    _patch_canonical_pipeline(monkeypatch, identity_ok=False, identity_unmeasurable=1)
    unmeasurable_out = tmp_path / "identity-unmeasurable.json"
    result = runner.invoke(app, [*common_args, "--json", str(unmeasurable_out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(unmeasurable_out.read_text())
    assert any("identity unmeasurable" in r for r in payload["void_reasons"])
    assert not any("identity mismatch" in r for r in payload["void_reasons"])
    assert payload["internals"]["identity_unmeasurable"] == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_engine_soak_command.py::test_soak_check_void_wiring_for_internals -v`
Expected: FAIL on `assert any("identity unmeasurable" in r for r in payload["void_reasons"])` — the payload carries `realized-internals identity mismatch`, the wrong reason. Not a `TypeError` on an unknown keyword: Task 1 Step 3 added the `identity_unmeasurable` parameter.

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

That new key makes `tests/test_engine_soak_command.py:252`'s full-dict `payload["internals"]` equality fail until it gains `"identity_unmeasurable": 0,` — add it here, in the same step as the payload change.

- [ ] **Step 4: Run both files**

Run: `uv run pytest tests/test_engine_soak.py tests/test_engine_soak_command.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/soak.py tests/test_engine_soak_command.py
git commit
```

---

### Task 3: Closeout

**Files:**
- Modify: `docs/open-topics/T0188-soak-identity-check-counts-a-nan-comparison-as-passed.md`, `docs/open-topics/README.md`
- Modify: `docs/open-topics/T0183-reconciliation-reports-perfect-on-an-empty-set.md`, `docs/open-topics/T0194-journal-readers-that-never-validate-the-record.md` — two live topics carrying claims this change falsifies
- Modify: `docs/iterations-history-phase6.md`

- [ ] **Step 1: Resolve T0188 through the `topic-ops` skill**

Load `.claude/skills/topic-ops/SKILL.md` and follow it: `status: resolved`, a `## Resolution` naming the commits and what each decision landed as, `git mv` into `docs/open-topics/archive/`, and the index bullet moved to the same category's `### Resolved` with its link repointed at `archive/`. Its `## Suggested next steps` bullets are answered, in their own order, by spec `00113` D1 (where the refusal belongs), D7 (the guard's fixture and its degeneracy) and D2/D3/D5 (what a partly-NaN window answers, and what the detail then carries), with D6 as the consequence for the void reason — say which, so the archived file records the answers rather than the questions.

- [ ] **Step 2: Re-tense the two topics this change falsifies**

Neither is `T0188`, and neither is archived here — the edits are prose corrections in files that stay open:

- `docs/open-topics/T0183-reconciliation-reports-perfect-on-an-empty-set.md:53` reads "A non-finite `diff` renders the same string with comparisons counted, which is `T0188` — a different defect … and not this topic's to fix". After this branch the string is no longer the same and the comparisons are no longer counted: re-tense it to the outcome and repoint the link at `archive/`.
- The same file's table row at `:93` states `identity_ok`'s range as "`bool | None` — `None` when no `(record, asset)` pair was compared". Correct it to name the new arm as well: `False` when any pair was unmeasurable.
- `docs/open-topics/T0194-journal-readers-that-never-validate-the-record.md:17` already reads "That is closed at the comparison by spec `00113`" while nothing had landed — a completed-work sentence ahead of the step that makes it true (`prose.md`). Re-tense it to name what closed it.

- [ ] **Step 3: The changelog entry**

The soak report's void reasons and its `--json` internals block are surfaces an agent and an operator act on, so an entry is owed (`prose.md`). One-line bullets, one per changed surface, each saying what a reader now does differently. Load `.claude/skills/iteration-closeout/SKILL.md` for the file mechanics.

- [ ] **Step 4: Verify the reach, once, on the final tip**

`git grep -l "soak" -- tests/` names the reachable files; run `tests/test_engine_soak.py` and `tests/test_engine_soak_command.py` at minimum, plus `tests/test_internal_terms_not_operator_visible.py` (the new void-reason string is runtime output from `cli/`, which that test's `SCANNED_PACKAGES` covers) and `tests/test_code_prose_citations.py` — which resolves no serial and no `T<NNNN>`, only that a `task <N>` token carries a 5-digit serial nearby, so it is the guard that catches such a token if a fix-up introduces one into the new comments. Then `uv run pre-commit run -a`.

- [ ] **Step 5: Commit**

```bash
git add docs/open-topics docs/iterations-history-phase6.md
git commit
```
