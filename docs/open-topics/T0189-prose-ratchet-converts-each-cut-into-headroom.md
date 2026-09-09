---
status: open
---

# The prose ratchet converts every cut into silent headroom

## Context — what

`infra/scripts/prose-tripwire.py --check-baseline` fails only on an offender the baseline does not record **at that size or larger**. So the baseline's recorded size is a ceiling, not a fact about the tree: when a cutting pass shrinks a recorded offender, the entry keeps the old, larger size and thereafter licenses regrowth all the way back to it without failing. The run exits 0 either way, and nothing asks whether the ceiling should come down with the block.

## Why this matters

The ratchet exists to make prose decrease monotonically. Each cutting batch drops the tree away from a ceiling that does not move, in exactly the files that batch worked hardest on — the cut is real, but the guard against its undoing is weakened by the same edit. A later regrowth to the old size is then invisible to the commit gate, which is the one check that runs on every commit.

## Findings so far

- Measured twice, on the same entries both times: after PR #459, and again on `chore/prose-batch-c`. `cli/universe/rules.py:9` shrank 7 → 5 and still trips, so it reports `rewritten:`; `:55` shrank to 4 and no longer trips, so it reports `retired:`. Exit 0 on both runs.
- Two of the three cases are at least reported: `rewritten:` and `retired:` name what happened, and what is missing there is any consequence — neither reduces the recorded ceiling, and neither fails. The third is silent. `new_since` consumes a baseline entry per offender, taking an exact size match first and otherwise the smallest recorded size at least as large, and prints no line at all when the entry it consumed was the larger one — so a shrink spends a bigger ceiling silently.
- `prose.md` offers two dispositions when the hook names a block — cut it, or keep it consciously and re-record the baseline with `--write-baseline` in the same commit. Neither disposition covers this case, because here the hook does not name anything: the tree got better and the baseline silently got looser.
- Shares its baseline-integrity family with [[T0195]] (`--write-baseline` with an explicit path list truncates every other file's recorded keeps): both defects route through `_absorbable()`'s path+kind-only matching, which never checks an anchor's own validity or a size's own headroom before consuming it as a match. Whoever fixes one should hold the other in view — [[T0195]]'s suggested merge remedy (scan the given paths, keep every other path's rows untouched), if built without also addressing this topic, would preserve exactly the stale, oversized rows this topic exists to stop licensing.

## Suggested next steps

- **Decide whether a shrink should lower the ceiling automatically.** The cheap form is for `--check-baseline` to rewrite a recorded entry down to the observed size whenever the observed size is smaller, so the baseline tracks the tree's best-ever state. Weigh it against the churn that puts in every cutting commit's diff, and against whether a ratchet that tightens itself can be re-widened deliberately when a block legitimately grows.
- **Decide what `retired:` should do.** An entry whose block no longer trips is dead weight that will never fail again; leaving it recorded means a future regrowth to the old size passes silently.
- **The guard, and its degeneracy.** Whatever is decided, it is a change to a tool that judges the tree, so it takes the construction proof: a fixture where a recorded offender shrinks and is then regrown to its old recorded size, asserting the regrowth FAILS, with a true-positive control where a legitimately-recorded offender at its recorded size still passes. A fixture whose before and after sizes are equal passes under the defect and proves nothing.
