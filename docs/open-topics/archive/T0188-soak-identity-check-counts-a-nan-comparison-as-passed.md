---
status: resolved
---

# The soak report's identity check counts a NaN comparison as made and passed

## Context — what

`realized_internals` (`cli/engine/soak.py`) carries spec `00059` D2's window-wide identity proof: every scored cycle's journaled `final_targets` must equal the rebuilt row to `tol`. Its loop counts each `(record, asset)` pair into `compared` and then decides on two comparisons of the same value:

```
diff = abs(row[a] - value)
if diff >= worst_diff: worst_diff, worst_detail = diff, f"cycle={t!r} asset={a!r}"
if diff > tol: identity_ok = False
```

A NaN `diff` is False on both. So a comparison whose operands make `diff` NaN increments `compared`, never moves `worst_diff`, and never drives `identity_ok` to `False`: a window whose every comparison was NaN reports `identity_ok: True` with `identity_detail` still reading `at n/a` — the identity checked and agreeing, over nothing measured.

## Why this matters

`identity_ok is False` is what `soak_report` turns into the `realized-internals identity mismatch` void reason. `True` is the pass, and the pass is what a go-live decision reads — `T0183` calls `soak_report` the instrument that cannot place a trade but can steer whether trades are placed at all. A NaN window returns the pass.

**The refusal that would catch it does not run on this path.** The finiteness check on `final_targets` lives in `validate_record` (`cli/engine/journal.py:144-145`), and `realized_internals` calls it on `latest_record` alone — the record it rebuilds from — never on the `scored_records` whose journaled values it compares. Those arrive through `from_json`, whose docstring says schema stays "the caller's separate concern", and `journal.py` says twice in its own comments that several callers read a record without ever calling `validate_record`.

What stands between is the WRITER: `cli/engine/cycle.py:686` validates before journaling, so an artifact this engine wrote is guarded. The exposure is one call site's discipline rather than a property of the read — a record reaching the report by any other route carries no finiteness guarantee at all, and nothing in the report notices.

## Findings so far

- It is `T0183`'s failure at one remove and deliberately not folded into it: that family is an empty-input branch returning the success value, and this is an unmeasurable comparison **counted as measured**. `T0183` points here from its `identity_detail` exclusion.
- **`identity_ok`'s `None` arm does not cover it.** `T0183`'s branch made `identity_ok` answer `None` when `compared == 0`; a NaN comparison makes `compared` non-zero, so the two are disjoint by construction and the new arm cannot mask the old defect or this one.
- The arithmetic, run rather than reasoned: with `worst_diff = 0.0`, `abs(float("nan") - 1.0)` is `nan`, `nan >= 0.0` is `False`, and `nan > tol` is `False`.
- **The same function's `cap_consistent` is NOT exposed**, so a fixer need not sweep it: its `breach` comparison reads a NaN as False the same way, but `apply_position_caps` refuses a non-finite position on the way in, so `combined` and `capped` are finite by construction.

## Resolution

Closed by spec `00113`, in the three commits the PR that carries this file into `archive/` holds: `fix(engine): realized_internals refuses an identity it could not measure`, `fix(engine): the soak void reason names which identity failure it is`, and `fix(engine): identity_self_check refuses a non-finite replay diff`. The three questions this topic left open are answered below in the order it asked them.

- **Where the refusal belongs: at the comparison, as the guarantee, with read-side validation kept as the belt** (D1). The competing placement lost on a measurement rather than on blast radius — the REBUILT side of the comparison is not provably finite either. `_validate_grid` (`cli/portfolio/crossfreq_system.py`) checks the prices dict's shape, key set, stamps and series lengths and never tests a close VALUE, so what refuses a NaN price on the fast path today is `float.as_integer_ratio()` raising inside the rolling statistics — an accident of exact rational arithmetic, not a guard anyone wrote. A refusal that holds by design therefore has to sit where the wrong answer is produced. The belt stays available as `T0194`, which keeps its reader enumeration owed.
- **The guard, and its degeneracy** (D7). The defect fixture is NaN-only, as this topic required: one scored record whose journaled target for an asset is `float("nan")` against a rebuilt row that is a real number and agrees everywhere else, so no magnitude break can carry the assertion. `test_realized_internals_identity_holds` is the true positive beside it, unchanged and still green. Each new assertion was proved by the mutation that should turn it red — the removal of the unmeasurable arm, the narrowing of the arm to all-NaN windows, keying on `isnan` instead of `isfinite`, a flag in place of the count, and the detail taking the last unmeasurable pair rather than the first — every one killed with the control proven on the same run.
- **A partly-NaN window answers `False`, with the count and the operands beside it** (D2, D3, D5). The arm keys on the finiteness of the `diff` and never on which operand produced it, which is what makes it catch two MATCHING infinities as well as a NaN — the pair this topic's own arithmetic missed. An unmeasurable pair increments the new `RealizedInternals.identity_unmeasurable` and is never added to `compared` and never moves `worst_diff`, so `compared` keeps its meaning. Any non-zero count answers `identity_ok: False`: `None` was not available, because `soak_report` voids on `identity_ok is False` alone, so answering `None` would have moved the silent pass one branch over instead of closing it. The check runs BEFORE the `compared == 0` arm — an all-NaN window satisfies both — so it voids rather than reporting `T0183`'s `None`, and those two arms stay disjoint. `identity_detail` then names the unmeasurable count, the first pair that could not be compared, and that pair's journaled and rebuilt values, since the arm itself cannot say which side went non-finite.
- **The consequence for the operator** (D6). `soak_report` appends `realized-internals identity unmeasurable (<identity_detail>)` in place of `realized-internals identity mismatch` whenever the count is non-zero, so *an operand was not a number* is read apart from *the rebuild disagrees* — the two call for different next actions. The detail rides in parentheses on that one reason because `render_report` renders the void reasons and never `identity_detail`, which otherwise reaches the `--json` reader alone; the payload publishes `identity_unmeasurable` beside `identity_ok`.

**The rest of the sweep** (D8). `## Findings so far` above clears `cap_consistent` alone; D8 enumerated every tolerance-bar agreement check in `cli/engine/soak.py` and found one more instance, closed on this branch: `identity_self_check`'s `abs(replayed[asset] - value) > tol`, whose journaled operand is guarded — `replay_cycle` validates before it replays — while its REPLAYED operand is the side D1 measures as not provably finite. A non-finite difference is now collected into `mismatches` before the magnitude bar sees it, so the check answers `False` and its message names both operands; no new field carries it, because `self_tests` already owns the `None` that means *skipped*. The `breach` bar is the one shape-carrying member deliberately left where it is, at BOTH its sites — `cap_consistent`'s and the one `reconcile_ok` counts (`cli/engine/soak.py:317`) — on the argument this file already accepts for the first: each compares `apply_position_caps` output against its own input, and that function refuses a non-finite position on the way in. The remaining members of the enumeration refuse already: `_chain_consistent` and `instrument_self_check` compare with `!=`, which is True on a NaN, and `_net_live_from_result`'s `reconcile_ok` identity uses `<= 1e-9`, which is False on a non-finite difference, so its `all(...)` is False.

`T0193` — a non-finite snapshot close escaping the report as a traceback — is untouched here and stays open: it arrives at `realized_internals` from the opposite side and carries a design fork this change does not answer.
