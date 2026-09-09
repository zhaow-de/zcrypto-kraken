---
status: open
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

## Suggested next steps

- **Decide where the refusal belongs.** At the comparison — a non-finite `diff` counted as a failure, or as not-compared — closes this one consumer and cannot be defeated by a new read path reaching it. At the read — validating the scored records the way the latest record already is — closes it for every consumer of those records at once. They are not exclusive; pick which is the guarantee and which is the belt.
- **The guard, and its degeneracy.** A window whose comparisons are all NaN must not report `identity_ok: True`. The fixture must be NaN-only: one that ALSO breaks the identity by magnitude passes under the defect for the wrong reason and proves nothing. Beside it a true-positive — a healthy window still reporting `identity_ok: True` — or an always-refusing check ships green.
- Decide what the answer should be when only SOME comparisons are NaN. `identity_ok: None` says nothing was compared, which is false; `False` names a mismatch nobody found. A third state, or a count of unmeasurable comparisons reported beside the verdict, is the choice to make explicitly rather than by whichever branch is easiest to write.
