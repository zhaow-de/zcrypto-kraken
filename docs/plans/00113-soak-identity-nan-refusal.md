# Soak identity NaN refusal — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Both of the soak's tolerance-bar identity comparisons refuse a comparison they could not make, so a non-finite target voids the soak run instead of reporting the identity holding over it.

**Architecture:** One counter beside `compared` in `realized_internals`' comparison loop, one new field on `RealizedInternals`, one branch-ordering decision after the loop, one void-reason branch in `soak_report`, and one more arm in `identity_self_check`'s mismatch comprehension — the file's other comparison of the same shape (spec `00113` D8). No new module, no new helper, no change to what `tol` or `compared == 0` mean.

**Tech Stack:** Python 3.14, `uv run pytest`. `math.isfinite` is already imported in `cli/engine/soak.py`.

**Spec:** `docs/specs/00113-soak-identity-nan-refusal-design.md`

## Global Constraints

- The refusal goes at the comparison in `cli/engine/soak.py`. Do **not** add `validate_record` to any read path — that is `T0194` and out of scope (spec `## Out of scope`).
- Do **not** catch `ValueError` in `realized_internals` or `soak_report`, and do not add a finiteness check to `_validate_grid` — that is `T0193` and out of scope, because it carries an unanswered design question.
- Do not touch, in this file: the `breach` bar at either of its sites (`:317`, `:849`), whose operands are `apply_position_caps` output and its own input and so are finite by construction; `_net_live_from_result`'s `reconcile_ok` identity (`:320`), whose `<= 1e-9` is False on a non-finite difference, so its `all(...)` is False and the verdict refuses; and `_chain_consistent` (`:159`) and `instrument_self_check` (`:729`), which compare with `!=`, True on a NaN, and so refuse already. Spec D8's enumeration puts `identity_self_check` (`:745`) in scope beside `realized_internals` and nothing else in this file.
- `compared` keeps its present meaning: comparisons actually made. A non-finite `diff` increments `unmeasurable` instead (spec D2).
- The unmeasurable check is evaluated **before** the `compared == 0` arm (spec D4). Reversing the order makes the all-NaN window report `None`, which does not void.
- The defect fixture is NaN-ONLY (spec D7): the journaled target is `float("nan")` and every other value matches the rebuilt row exactly. A fixture that also mismatches by magnitude passes under the defect for the wrong reason — so the one non-NaN fixture the plan carries, the `float("inf")` target that tells finiteness-keying from NaN-keying (spec `## The measured basis`), discriminates on `identity_unmeasurable` alone; the `identity_ok` assertion beside it is a shape check the defect also satisfies, and pins nothing.
- `cli/engine/soak.py` is inside `replay_fingerprint`'s import closure, so any change here invalidates the gate cache and the next run pays a cold replay. Expected for a code fix; do not treat it as a regression.

---

### Task 1: The unmeasurable arm in `realized_internals`

**Files:**
- Modify: `cli/engine/soak.py` — the `RealizedInternals` dataclass (~`:756-765`), `realized_internals`' own docstring clause on `identity_ok` (~`:820-821`), the `except` branch's construction (~`:828-837`), the comparison loop (~`:853-884`), and the return (~`:888-898`)
- Test: `tests/test_engine_soak.py` — the `# --- realized_internals ---` section that begins at `:2561`, plus the four `RealizedInternals(` construction sites Step 3 enumerates
- Test: `tests/test_engine_soak_command.py` — `_fake_realized_internals` inside `_patch_canonical_pipeline` (`:161`), whose stub construction at `:191` is the fifth test-side site
- Modify, only on Step 5's re-record branch: `infra/scripts/prose-tripwire-baseline.txt`

**Interfaces:**
- Produces: `RealizedInternals.identity_unmeasurable: int` — the number of `(record, asset)` pairs whose `diff` was not finite. `0` on every existing path, including the `available=False` construction. Task 2 consumes it.
- Produces: `_patch_canonical_pipeline`'s `identity_unmeasurable: int = 0` keyword (`tests/test_engine_soak_command.py:161`), threaded into its stub exactly as `identity_ok` already is. Task 2 consumes it.

- [ ] **Step 1: Write the failing test**

Add beside `test_realized_internals_shift_breaks_identity` in `tests/test_engine_soak.py`. It reuses the module-level `_fake_result` (`:307`) with that section's own `_mk_h4_snapshot_record` (`:2564`) and `_mk_scored_record` (`:2610`), so no builder runs and the test does not depend on the incidental `ValueError` the fast path raises on a NaN price.

Three windows, each pinning something the others cannot. An all-NaN window has `compared == 0` as well, so it is satisfied by the narrower `if unmeasurable and not compared:` too; only a window with a measured comparison beside the unmeasurable one pins spec `00113` D3's *any*; and only an infinite target tells D2's finiteness-keying from a NaN test. That middle window carries TWO unmeasurable pairs, which is what makes the count observable as a count and the detail's coordinate observable as the first offender.

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
    # Both operands, since the arm never says which one went non-finite (spec 00113 D5).
    assert "journaled=nan" in ri.identity_detail and "rebuilt=" in ri.identity_detail

    # `compared == 0` holds above too, so that window alone cannot tell the arm from the narrower
    # `if unmeasurable and not compared:`. Here one comparison IS made and agrees, and the refusal
    # is spec 00113 D3's "any" rather than "nothing was measured". Two unmeasurable pairs, because a
    # count every window puts at 1 is satisfied by an assignment, and "at/after" by an overwrite.
    agreeing = _mk_scored_record(h4_ts[3] + timedelta(hours=4), {"BTC": fake.final_targets["BTC"][3]})
    later_nan = _mk_scored_record(h4_ts[2] + timedelta(hours=4), {"BTC": float("nan")})
    mixed = realized_internals([nan_rec, agreeing, later_nan], latest, reader)
    assert mixed.identity_ok is False, mixed.identity_detail
    assert mixed.identity_unmeasurable == 2
    assert "at n/a" not in mixed.identity_detail  # the measured pair moved `worst_detail` (spec D5)
    # "at/after" is the FIRST pair the loop could not compare, so the second one's stamp is absent.
    assert f"cycle={nan_rec.cycle_ts!r} asset='BTC'" in mixed.identity_detail
    assert f"cycle={later_nan.cycle_ts!r}" not in mixed.identity_detail

    # Keyed on the diff's finiteness, never on NaN (spec 00113 D2): an infinite journaled target
    # against a finite rebuilt row is unmeasurable, where `math.isnan(diff)` would count it compared
    # and report a mismatch. `identity_ok` is False under the defect too, so it cannot carry this.
    inf_rec = _mk_scored_record(h4_ts[1] + timedelta(hours=4), {"BTC": float("inf")})
    infinite = realized_internals([inf_rec], latest, reader)
    assert infinite.identity_unmeasurable == 1
    assert infinite.identity_ok is False, infinite.identity_detail
    # The `continue` kept an unmeasurable pair out of `worst_diff`: the docstring's "never compared".
    # Without it this window's detail reads `worst |diff|=inf`, a magnitude nothing measured.
    assert infinite.identity_detail.startswith("worst |diff|=0.0 at n/a")
```

- [ ] **Step 2: Run it and read WHICH failure fired**

Run: `uv run pytest tests/test_engine_soak.py::test_realized_internals_refuses_an_identity_it_could_not_measure -v`
Expected: FAIL on the first window's `assert ri.identity_ok is False` with `identity_ok` reading `True` and `identity_detail` reading `worst |diff|=0.0 at n/a` — the defect itself. That assertion fires before `ri.identity_unmeasurable` is ever evaluated, so an `AttributeError` on the missing field is NOT the red to expect; read the message rather than the exit code.

- [ ] **Step 3: Add the field to `RealizedInternals`, and thread it through every construction site**

```python
    identity_ok: bool | None  # None = nothing compared and none unmeasurable; any unmeasurable pair answers False (spec 00113 D4)
    identity_unmeasurable: int  # pairs whose |diff| was not finite: counted, never compared (spec 00113 D2)
    identity_detail: str
```

The `identity_ok` comment is rewritten, not re-emitted: after Step 5, `None` requires `compared == 0` **and** `unmeasurable == 0`, so the old sentence would be false from the moment this task lands — and it is the sentence Task 4 Step 2 corrects downstream in `T0183`.

The dataclass carries no field defaults and this field takes none either: a producer that omits the count is a `TypeError` at construction, where a defaulted `0` would sit silently beside an `identity_ok=False` and make Task 2's branch read it as a mismatch. The cost is that every existing construction site changes in this task. The family is `grep -rn "RealizedInternals(" cli/ tests/ infra/` — seven sites, five of them in tests, none of them selected by the `-k realized_internals` filter, which is why Step 6 runs both files whole:

| Site | What to pass |
| --- | --- |
| `cli/engine/soak.py:828` — the `except (EngineError, PortfolioError)` branch | `identity_unmeasurable=0`, beside `identity_ok=False` |
| `cli/engine/soak.py:890` — the successful return | `identity_unmeasurable=unmeasurable` (Step 5) |
| `tests/test_engine_soak.py:1150` — `_mk_internals`, the helper 11 tests call | `identity_unmeasurable=0` |
| `tests/test_engine_soak.py:1496` | `identity_unmeasurable=0` |
| `tests/test_engine_soak.py:1862` | `identity_unmeasurable=0` |
| `tests/test_engine_soak.py:1935` | `identity_unmeasurable=0` |
| `tests/test_engine_soak_command.py:191` — `_fake_realized_internals`, inside the `_patch_canonical_pipeline` helper 9 tests call | `identity_unmeasurable=identity_unmeasurable`, from a new `identity_unmeasurable: int = 0` keyword parameter added beside `identity_ok`, threaded exactly as `identity_ok` already is — Task 2 sets it |

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
                    # Both operands, because this arm never decides which one went non-finite and the
                    # rebuilt side is not provably finite either (spec 00113 D1, D5).
                    unmeasurable_detail = f"cycle={t!r} asset={a!r} journaled={value!r} rebuilt={row[a]!r}"
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

Replace `cli/engine/soak.py:881-884` — the `# Nothing compared:` comment, the `if not compared:` arm under it, and the `identity_detail = …` assignment that sits BELOW that arm today — with the block here. The assignment moves ABOVE both arms because the unmeasurable arm appends to it: inserted above the existing four lines instead of over them, the leftover `if not compared: identity_ok = None` runs after the new arm and the leftover assignment overwrites the extended detail, which puts the all-NaN window back on `identity_ok=None` with no void reason — the silent pass this pair exists to close.

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

And extend `realized_internals`' own contract sentence at `:820-821` — "`identity_ok` is spec 00059 D2's window-wide check that the rebuilt row equals the journaled `final_targets` to `tol`" — with ", and refuses when a `diff` was not finite (spec 00113 D2)". Three sentences in this file state `identity_ok`'s contract and the family is exactly those three: this one; the field comment Step 3 rewrites (`:763`); and the dataclass docstring at `:757` ("spec 00059 D2's window-wide proof that each resolved row is that cycle's own"), which states the field's PURPOSE rather than its arms and is left alone. Outside the family: `soak_report`'s gate list at `:1645` names `identity_ok` without saying what `False` means, and `SelfTestReport.identity_ok` (`:685`) belongs to a different class.

That extension costs a line the prose ratchet is watching. The docstring spans `:815-822` — 8 lines — and `infra/scripts/prose-tripwire-baseline.txt` records it at exactly that size (`grep "soak.py:815" infra/scripts/prose-tripwire-baseline.txt` → `comment-block 8 > 4`); re-wrapping its closing paragraph with the added clause returns four lines where three stand, both at the width the docstring's own longest line implies and at `ruff.toml`'s 132 (`uv run python -c` over `textwrap.wrap`). Nine against a recorded 8 is `grown`, which fails the hook at `pre-commit` and again at `pre-push`. So either condense the docstring's existing tail by a line in the same edit, or keep the ninth consciously and re-record with `uv run python infra/scripts/prose-tripwire.py --write-baseline infra/scripts/prose-tripwire-baseline.txt`, staged in Step 7's commit — the script's header requires reading `--check-baseline`'s classification first, because the re-record absorbs everything else the tree has grown along with this line.

- [ ] **Step 6: Run both files and confirm the true positive is still green**

Run: `uv run pytest tests/test_engine_soak.py tests/test_engine_soak_command.py -q`

Both files, not the `-k realized_internals` filter — that filter selects none of Step 3's five test-side construction sites, so it would report PASS over a tree where every test reaching one of them raises `TypeError`. (The filter's one remaining use is Step 8's probe selection, run against a tree this step has already proven green.)

Expected: PASS, including `test_realized_internals_identity_holds` (the true positive — a healthy window still reporting `identity_ok: True`), `test_realized_internals_identity_is_unmeasured_with_no_scored_record` (`identity_ok is None` unchanged, both its routes), `test_realized_internals_shift_breaks_identity`, and `test_realized_internals_asset_outside_universe_raises` — the last of which reds with a `KeyError` if Step 4 took the `a not in row` refusal with it.

- [ ] **Step 7: Commit**

```bash
git add cli/engine/soak.py tests/test_engine_soak.py tests/test_engine_soak_command.py
git commit
```

Add `infra/scripts/prose-tripwire-baseline.txt` to that `git add` if Step 5 re-recorded it, and only then — the condense branch leaves the file untouched. Left unstaged it is stashed by pre-commit's partial-commit handling, and the ratchet then reads the old baseline against the grown block and refuses the commit.

- [ ] **Step 8: Prove the guard bites, then amend the body with the verdict**

The probe runs AFTER the commit: `infra/scripts/mutate-probe.sh` refuses a dirty worktree outright (rc 3 — restore is `git checkout --`, which would destroy uncommitted work), and `--sandbox`, its only other mode, refuses any probe command containing `pytest`. Stashing is not the way round it — the stash stack is shared with the other worktrees. So run the probes here and land the result with `git commit --amend`, whose body names the mutations constructed and the assertions that fired (`commit-messages.md`).

`--collect-only` the `-k` filter first:

```bash
uv run pytest --collect-only -q tests/test_engine_soak.py -k realized_internals
```

It must select every `test_realized_internals_*` test and deselect none of them — 10 on this branch's base, 11 with the new one. Do not narrow the filter to make a number match: the wider set is what carries the probe's true positives, including the schema-2 and real-journal tests that walk the same loop.

Five mutations, one probe run each, same control. All five must report KILLED, and the control must FAIL in each, which is how the probe proves it is measuring — it widens `tol` so `test_realized_internals_shift_breaks_identity`'s mismatch stops being detected.

`mutate-probe.sh` discards the probe command's output in all three of its phases (`:99`, `:106`, `:111`) and prints its verdict alone, so KILLED plus the proven control is all it observes. The assertion text `commit-messages.md` wants in the body therefore comes from the probe command's OWN redirect, which the script's `>/dev/null 2>&1` cannot reach: every probe below is wrapped as `sh -c '… > "<log>" 2>&1'`, and `sh -c` exits with the wrapped command's status, so the verdict is unchanged. A scratch worktree is deliberately NOT the mechanism — a second checkout puts the mutation and the measurement in different trees with nothing in the body saying which one the assertion came from, and every command aiming it is a `git checkout --` steered by a cwd that resets between calls (`agent-ops.md`).

Each log holds the last phase that RAN — baseline (`:99`), control (`:106`), mutation (`:111`), each overwriting, and `restore` runs no probe — which is the mutation's only when the script printed KILLED or SURVIVED. Four exits stop earlier: rc 3 (dirty tree, `:61`) before any phase runs, rc 7 (baseline failed, `:99`), rc 5 (control did not fail, `:106`), and rc 6 (a no-op sed, `:87-91`), which on the MUTATION sed aborts with the control phase's output already in the log. Nothing in the log names its run or its phase, so read `mutate-probe.sh`'s verdict line first and the log only under a KILLED — and never the control's failure text, which no phase keeps; the verdict line is what attests that. The wrapper belongs on every mutate-probe invocation in this plan, each with its own log name — the five probes below and Task 3 Step 6's — and each fence clears the logs it is about to write, so an earlier attempt's cannot be read as this run's.

Create the log directory once first and clear the five logs this step writes. `.tmp/` is gitignored, so the logs leave the tree clean for the next probe's own dirty-tree refusal:

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.tmp"
find "$(git rev-parse --show-toplevel)/.tmp" -maxdepth 1 -name '00113-*.log' -delete
```

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/^    if unmeasurable:$/    if False:/' \
  -- sh -c 'uv run pytest tests/test_engine_soak.py -k realized_internals -q > "$(git rev-parse --show-toplevel)/.tmp/00113-arm.log" 2>&1'
```

Deletes the arm under proof, which is Step 5's ordering decision: the all-NaN window falls through to `identity_ok = None` and the first window's `assert ri.identity_ok is False` fires.

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/^    if unmeasurable:$/    if unmeasurable and not compared:/' \
  -- sh -c 'uv run pytest tests/test_engine_soak.py -k realized_internals -q > "$(git rev-parse --show-toplevel)/.tmp/00113-narrowed.log" 2>&1'
```

Narrows the arm to the reading Step 5's own comment invites. The all-NaN window still passes under it; only Step 1's mixed window kills it, on `assert mixed.identity_ok is False`. If this one reports SURVIVED, the mixed window is not discriminating and the fixture is the thing to fix.

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/if not math.isfinite(diff):/if math.isnan(diff):/' \
  -- sh -c 'uv run pytest tests/test_engine_soak.py -k realized_internals -q > "$(git rev-parse --show-toplevel)/.tmp/00113-isnan.log" 2>&1'
```

Narrows D2's keying from finiteness to a NaN test, which is the claim the spec calls load-bearing and the reason Step 1 carries a third window at all. The fragment matches once after Step 4 (`grep -c "if not math.isfinite(diff):" cli/engine/soak.py` is `0` on this branch's base and `1` once Step 4 lands). Only the infinite window kills it, on `assert infinite.identity_unmeasurable == 1`: under `math.isnan` an infinite journaled target counts as compared again and reports a magnitude mismatch, which is the reclassification spec `00113` D2 rejects. Without this run the third window is asserted and never shown to bite, and the commit body would claim proof for the ordering arm alone.

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/unmeasurable += 1/unmeasurable = 1/' \
  -- sh -c 'uv run pytest tests/test_engine_soak.py -k realized_internals -q > "$(git rev-parse --show-toplevel)/.tmp/00113-count.log" 2>&1'
```

Turns the count into a flag, which is what the `--json` payload publishes. Only Step 1's mixed window kills it, on `assert mixed.identity_unmeasurable == 2` — every other window has exactly one unmeasurable pair, where a count and a flag read alike.

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/if diff > tol:/if diff > tol * 1e12:/' \
  --mutation 's/if not unmeasurable_detail:/if True:/' \
  -- sh -c 'uv run pytest tests/test_engine_soak.py -k realized_internals -q > "$(git rev-parse --show-toplevel)/.tmp/00113-first.log" 2>&1'
```

Makes the detail's coordinate the LAST pair the loop could not compare instead of the first, which is what "at/after" claims. Only the mixed window kills it, on the `cycle=` assertion naming `nan_rec`'s stamp. Both fragments match once after Step 4, and both mutants keep the block's shape, so the red is the assertion's and not a parse error.

---

### Task 2: The void reason names which of the two happened

**Files:**
- Modify: `cli/engine/soak.py` — the void-reason branch at `:1718-1719`, and the internals payload at `:1529-1530`
- Test: `tests/test_engine_soak_command.py` — `test_soak_check_void_wiring_for_internals` (`:270`) and the full-dict payload equality at `:252`
- Modify, only on Step 1's re-record branch: `infra/scripts/prose-tripwire-baseline.txt`

**Interfaces:**
- Consumes: `RealizedInternals.identity_unmeasurable` and `_patch_canonical_pipeline`'s `identity_unmeasurable` keyword, both from Task 1.

- [ ] **Step 1: Write the failing assertion, as a fourth arm of the existing wiring test**

`tests/test_engine_soak.py` reaches `soak_report` nowhere — `grep -n "soak_report" tests/test_engine_soak.py` returns two comment lines and no call — so the test belongs in `tests/test_engine_soak_command.py`, beside the guard that already pins the other reason string: `test_soak_check_void_wiring_for_internals` (`:270`) asserts `any("identity mismatch" in r for r in payload["void_reasons"])` under `identity_ok=False`. A fourth arm there decides both strings in one run, with the mismatch arm standing as its true positive.

`_patch_canonical_pipeline` stubs `realized_internals`, the PRODUCER of the count; `soak_report` still computes `void_reasons` itself, so the branch under test is the live one. Task 1's `test_realized_internals_refuses_an_identity_it_could_not_measure` is what pins that a NaN journaled target produces the count; this arm pins which string the branch picks given it.

Place the arm after the `identity_ok=False` one and before the `identity_ok=None` one, and extend the test's docstring to state the claim the new assertions make — in four lines, because that docstring (`tests/test_engine_soak_command.py:271-274`) already sits exactly at the tripwire's `COMMENT_BLOCK_LINES` and `grep "test_engine_soak_command.py:2" infra/scripts/prose-tripwire-baseline.txt` returns nothing, so a fifth line is a NEW offender and Step 5's commit is refused. Condense a clause to make room, or re-record the baseline the way Task 1 Step 5 sets out.

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
    # The text report renders `void_reasons` and never `identity_detail`, so the reason it picks
    # carries the detail (spec 00113 D6) -- read off the payload, and non-empty, or `in` is vacuous.
    detail = payload["internals"]["identity_detail"]
    assert detail and any(detail in r for r in payload["void_reasons"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_engine_soak_command.py::test_soak_check_void_wiring_for_internals -v`
Expected: FAIL on `assert any("identity unmeasurable" in r for r in payload["void_reasons"])` — the payload carries `realized-internals identity mismatch`, the wrong reason. Not a `TypeError` on an unknown keyword: Task 1 Step 3 added the `identity_unmeasurable` parameter.

- [ ] **Step 3: Branch the reason and publish the count**

```python
            if internals.available and internals.identity_ok is False:
                # Both can hold at once; the unmeasurable case is the weaker claim and names the reason, which
                # then carries `identity_detail` -- `render_report` renders these reasons and never that field,
                # so the displaced mismatch would otherwise reach the JSON reader alone (spec 00113 D6).
                # Parenthesised because that renderer joins reasons with `; ` and the detail carries one.
                void_reasons.append(
                    f"realized-internals identity unmeasurable ({internals.identity_detail})"
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

Add `infra/scripts/prose-tripwire-baseline.txt` to that `git add` if Step 1 re-recorded it, for the reason Task 1 Step 7 states.

---

### Task 3: The same refusal in `identity_self_check`

**Files:**
- Modify: `cli/engine/soak.py` — `identity_self_check`'s mismatch comprehension (`:742-746`) and its docstring's closing clause (`:739-740`)
- Test: `tests/test_engine_soak.py` — beside `test_identity_self_check_pass_and_fail` (`:863`)

**Interfaces:**
- Produces nothing. The signature, the return type and the message format are unchanged; a non-finite difference joins the list the function already builds, so no later task consumes anything from here.

- [ ] **Step 1: Write the failing test**

`replay_cycle` is stubbed, exactly as `test_identity_self_check_pass_and_fail` beside it stubs it, so no snapshot reader and no builder run. The fixture is a replayed NaN against a finite journaled value — the whole reachable silent set here, because `replay_cycle` calls `validate_record` before it replays and so the journaled operand cannot be the non-finite one (spec `00113` D8, `## The measured basis`). That is also why this task carries no finiteness-versus-NaN window: the input that would discriminate is one production cannot produce.

```python
def test_identity_self_check_refuses_a_comparison_it_could_not_make(monkeypatch):
    """A replayed target that is not a number makes the difference non-finite, so the pair is collected
    and the check refuses -- where the `> tol` bar alone reads it as agreement (spec 00113 D8). The
    finite asset beside it must stay out of the message, or the arm refuses everything."""
    rec = types.SimpleNamespace(final_targets={"BTC": 0.12, "ETH": -0.05})
    monkeypatch.setattr(soak, "replay_cycle", lambda r, reader, path="fast": {"BTC": float("nan"), "ETH": -0.05})
    ok, msg = identity_self_check(rec, snapshot_reader=None, tol=1e-6)
    assert ok is False, msg
    assert "replayed=nan" in msg and "ETH" not in msg
```

- [ ] **Step 2: Run it and read WHICH failure fired**

Run: `uv run pytest tests/test_engine_soak.py::test_identity_self_check_refuses_a_comparison_it_could_not_make -v`
Expected: FAIL on `assert ok is False` with `msg` reading `identity check passed` — the defect. Not a `TypeError` or a `KeyError`: the stub answers both assets.

- [ ] **Step 3: Add the finiteness arm and re-tense the docstring**

```python
        if asset not in replayed or not math.isfinite(replayed[asset] - value) or abs(replayed[asset] - value) > tol
```

The new arm sits AFTER the membership refusal, which is what keeps `replayed[asset]` from raising, and BEFORE the magnitude bar, which is the one that reads a non-finite difference as agreement.

The docstring's closing clause — "distinct from this function's own only failure, a genuine value mismatch" — is false once the arm lands and is rewritten with it, to name both failures: `function's own failure: a value mismatch, or a difference that was not finite (spec 00113 D8)."""`. Keep the block at FOUR lines: it is not in `infra/scripts/prose-tripwire-baseline.txt` (`grep "soak.py:736" infra/scripts/prose-tripwire-baseline.txt` returns nothing), so a fifth line is a new offender and Step 5's commit is refused.

- [ ] **Step 4: Run both files**

Run: `uv run pytest tests/test_engine_soak.py tests/test_engine_soak_command.py -q`
Expected: PASS, including `test_identity_self_check_pass_and_fail` — the true positive, a finite replay still passing — and `test_self_tests_threads_path_to_identity_self_check`, which stubs the function whole and so cannot see the arm. The command file is in scope because `_patch_canonical_pipeline(stub_self_tests=False)` runs the REAL `self_tests`, and that is the one route from a command test into this function.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/soak.py tests/test_engine_soak.py
git commit
```

- [ ] **Step 6: Prove the guard bites, then amend the body with the verdict**

The probe runs after the commit, for Task 1 Step 8's reason — `mutate-probe.sh` refuses a dirty worktree — and the verdict lands by `git commit --amend`. `--collect-only` the filter first: `uv run pytest --collect-only -q tests/test_engine_soak.py -k identity_self_check` selects 2 on this branch's base and 3 with the new test.

```bash
mkdir -p "$(git rev-parse --show-toplevel)/.tmp"
rm -f "$(git rev-parse --show-toplevel)/.tmp/00113-selfcheck.log"
infra/scripts/mutate-probe.sh \
  --file cli/engine/soak.py \
  --control 's/abs(replayed\[asset\] - value) > tol/abs(replayed[asset] - value) > tol * 1e12/' \
  --mutation 's/ or not math.isfinite(replayed\[asset\] - value)//' \
  -- sh -c 'uv run pytest tests/test_engine_soak.py -k identity_self_check -q > "$(git rev-parse --show-toplevel)/.tmp/00113-selfcheck.log" 2>&1'
```

Deletes the arm under proof; the new test's `assert ok is False` fires. The control widens the magnitude bar past `test_identity_self_check_pass_and_fail`'s `2e-6` mismatch, so that test's `assert ok2 is False` fails and the harness is proven to bite. Both expressions match once after Step 3. The assertion text is read from `.tmp/00113-selfcheck.log`, the redirect Task 1 Step 8 sets out — the probe's own run, in this checkout.

---

### Task 4: Closeout

**Files:**
- Modify: `docs/open-topics/T0188-soak-identity-check-counts-a-nan-comparison-as-passed.md`, `docs/open-topics/README.md`
- Modify: `docs/open-topics/T0183-reconciliation-reports-perfect-on-an-empty-set.md`, `docs/open-topics/T0193-nonfinite-snapshot-close-escapes-the-soak-report.md`, `docs/open-topics/T0194-journal-readers-that-never-validate-the-record.md` — three live topics carrying claims this change falsifies
- Modify: `docs/iterations-history-phase6.md`

- [ ] **Step 1: Resolve T0188 through the `topic-ops` skill**

Load `.claude/skills/topic-ops/SKILL.md` and follow it: `status: resolved`, a `## Resolution` naming the commits and what each decision landed as, `git mv` into `docs/open-topics/archive/`, and the index bullet moved to the same category's `### Resolved` with its link repointed at `archive/`. Its `## Suggested next steps` bullets are answered, in their own order, by spec `00113` D1 (where the refusal belongs), D7 (the guard's fixture and its degeneracy) and D2/D3/D5 (what a partly-NaN window answers, and what the detail then carries), with D6 as the consequence for the void reason — say which, so the archived file records the answers rather than the questions. Its `## Findings so far` clears `cap_consistent` alone; D8 is what swept the rest of the file, so the `## Resolution` names `identity_self_check` as the second instance this branch closed, the `breach` bar's OTHER site — the one `reconcile_ok` counts (`:317`), the one shape-carrying member left where it is, on the same finiteness argument the topic already accepts for `cap_consistent`'s — and D8's non-members — the two `!=` comparisons and `reconcile_ok`'s `<=` bar — as the rest of the sweep.

In the same edit that moves the index bullet, rewrite its TEXT as the outcome — what the arm now answers and which void reason it emits — and drop its closing "Ripe now.". `docs/open-topics/README.md:124` states the defect in the present tense today, and every bullet already under a `### Resolved` heading reads as its outcome instead; `topic-ops` prescribes the move and the repointed link, not the wording, so the plan is the only place this can land.

- [ ] **Step 2: Re-tense the three topics this change falsifies**

None is `T0188`, and none is archived here — the edits are prose corrections in files that stay open. The family is `grep -rn "T0188" docs/` less the `00113` spec/plan pair: five live-file hits — `T0183:53`, `T0193:25` and `T0194:17`, one bullet each below; `README.md:124`, which Step 1's archive move already carries; and `docs/iterations-history-phase6.md:889`, a point-in-time changelog entry that correctly keeps its wording. The `T0183:93` bullet carries no `T0188` token — it is the same `identity_ok` contract sentence Task 1 Step 3 rewrites at its source:

- `docs/open-topics/T0183-reconciliation-reports-perfect-on-an-empty-set.md:53` reads "A non-finite `diff` renders the same string with comparisons counted, which is `T0188` — a different defect … and not this topic's to fix". After this branch the string is no longer the same and the comparisons are no longer counted: re-tense it to the outcome, keeping the bare `T0188` citation — `grep -rn "T0188-soak-identity" docs/` returns `README.md:124` as the only markdown link to the topic file, so no bullet here repoints one.
- The same file's table row at `:93` states `identity_ok`'s range as "`bool | None` — `None` when no `(record, asset)` pair was compared". Correct it to name the new arm as well: `False` when any pair was unmeasurable.
- `docs/open-topics/T0193-nonfinite-snapshot-close-escapes-the-soak-report.md:25` reads "`T0188` is a silent pass over an unmeasurable comparison, this is a loud escape past a contract that promised degradation" — present tense about a defect this branch closes, in a topic that stays open and whose own fork is the one spec `00113` parks. Re-tense it to the outcome, keeping the citation (`prose.md`); the sentence's point — that the two arrive at `realized_internals` from opposite sides — survives the re-tensing.
- The same file's `:23` reads "the verified builder raises `AlphaError` on the same input" — the claim spec `00113`'s measured basis corrects: `AlphaError` at the three 4h placements, `BenchmarkError` at the three daily ones. Correct it here too, or the disproof lives only in a spec a `T0193` reader has no reason to open. This member carries no `T0188` token and the grep above cannot see it; it is found by reading the file the `:25` edit already opens.
- `docs/open-topics/T0194-journal-readers-that-never-validate-the-record.md:17` already reads "That is closed at the comparison by spec `00113`" while nothing had landed — a completed-work sentence ahead of the step that makes it true (`prose.md`). Re-tense it to name what closed it.

- [ ] **Step 3: The changelog entry**

The soak report's void reasons, its `--json` internals block and the identity self-test's verdict are surfaces an agent and an operator act on, so an entry is owed (`prose.md`). One-line bullets, one per changed surface, each saying what a reader now does differently. Load `.claude/skills/iteration-closeout/SKILL.md` for the file mechanics.

- [ ] **Step 4: Verify the reach, once, on the final tip**

`git grep -l "soak" -- tests/` names the reachable files; run `tests/test_engine_soak.py` and `tests/test_engine_soak_command.py` at minimum, plus `tests/test_internal_terms_not_operator_visible.py` (the new void-reason string is runtime output from `cli/`, which that test's `SCANNED_PACKAGES` covers) and `tests/test_code_prose_citations.py` — which resolves no serial and no `T<NNNN>`, only that a `task <N>` token carries a 5-digit serial nearby, so it is the guard that catches such a token if a fix-up introduces one into the new comments. Add `tests/test_open_topics_frontmatter.py` too: it is the only mechanical check over Step 1's own operation — `test_frontmatter_parses_as_yaml_with_a_valid_status` on the `status` flip, `test_an_archived_topic_carries_no_ripe_when` on the archive move, `test_every_topic_link_in_the_index_resolves` on the repointed index bullet — and no grep for `soak` can select it (`grep -c "soak" tests/test_open_topics_frontmatter.py` → `0`). Then `uv run pre-commit run -a`, which runs no pytest.

- [ ] **Step 5: Commit**

```bash
git add docs/open-topics docs/iterations-history-phase6.md
git commit
```
