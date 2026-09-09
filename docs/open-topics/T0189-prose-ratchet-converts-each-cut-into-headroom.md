---
status: partial
---

# The prose ratchet converts every cut into silent headroom

## Context — what

`infra/scripts/prose-tripwire.py --check-baseline` fails only on an offender the baseline does not record **at that size or larger**. So the baseline's recorded size is a ceiling, not a fact about the tree: when a cutting pass shrinks a recorded offender, the entry keeps the old, larger size and thereafter licenses regrowth all the way back to it without failing. The run exits 0 either way, and nothing asks whether the ceiling should come down with the block.

## Why this matters

The ratchet exists to make prose decrease monotonically. Each cutting batch drops the tree away from a ceiling that does not move, in exactly the files that batch worked hardest on — the cut is real, but the guard against its undoing is weakened by the same edit. A later regrowth to the old size is then invisible to the commit gate, which is the one check that runs on every commit.

## Findings so far

- Measured twice, on the same entries both times: after PR #459, and again on `chore/prose-batch-c`. `cli/universe/rules.py:9` shrank 7 → 5 and still trips, so it reports `rewritten:`; `:55` shrank to 4 and no longer trips, so it reports `retired:`. Exit 0 on both runs.
- Two of the three cases are at least reported: `rewritten:` and `retired:` name what happened, and what is missing there is any consequence — neither reduces the recorded ceiling, and neither fails. The third is silent. `new_since` consumes a baseline entry per offender, taking an exact size match first and otherwise the smallest recorded size at least as large, and prints no line at all when the entry it consumed was the larger one — so a shrink spends a bigger ceiling silently.
- `prose.md` offered two dispositions when the hook named a block — cut it, or keep it consciously and re-record. Neither covered this case, because the hook named nothing: the tree got better and the baseline silently got looser. The fix recorded below routes it into the second disposition by making the hook name it and fail.
- [[T0195]] shared this topic's baseline-integrity surface and is resolved: `--write-baseline` refuses a path list that would drop another file's recorded keeps. It was fixed by refusing and NOT by the merge remedy it proposed, for this topic's own reason — scan-and-preserve-untouched would have carried forward exactly the stale, oversized rows this topic exists to stop licensing. So nothing here waits on it, and nothing there relieves it: what this topic names is `_absorbable()`'s path+kind-only matching, which never checks a size's own headroom before consuming it as a match, and that is untouched. (T0195's own defect was the truncating `open(..., "w")`, never `_absorbable()`.)

## Done so far

**A shrink whose first line is unchanged now FAILS the gate until the row comes down with it.** Landed on `fix/t0189-a-shrink-lowers-the-ceiling`. The check names every shape of a shrink, an unbanked one exits 1, and the remedy is the re-record `prose.md` prescribes, taken in the same commit. **The re-keyed shape is NOT covered** — see the remainder below.

**The cheap form this topic proposed — `--check-baseline` rewriting a recorded entry down — is not available, and that is a fact about the gate rather than a preference between designs.** `--check-baseline` IS the pre-commit hook's command (`pass_filenames: false`, `always_run: true`, both stages), and a hook that writes a tracked file leaves it modified and unstaged, at which point pre-commit fails the commit. Every write stays with `--write-baseline`.

**The ceilings were banked in the same branch**, which is what actually lowered them: ten rows standing above their blocks' size came down and two whose blocks no longer trip were dropped.

**What enforcement costs, measured rather than assumed.** Against the 34 files queued in the cleanup, 6 carry baseline rows and 29 rows between them — but that is evidence about the queue, and the ten shrinks actually standing on develop sit in six other files, none of them queued, accumulated over 44 commits by authors who were not running a cleanup pass. So the real cost is not scoped to cutting passes: **every branch that cuts prose must now re-record the whole generated baseline**, a scoped write is refused by design, and two such branches conflict irreconcilably — the only resolution is re-running `--write-baseline` on the merged tree, never a textual merge. A base-advance race that used to exit 0 now reds the post-merge run.

**The enumeration, measured on develop at this branch's base**, and it closes: 1229 rows = 1214 at their observed size + 10 shrunk + 3 rewritten + 2 retired. develop's own copy of the tool cannot show the 10, because the column that separates a shrink from a silent absorption is this branch's.

## Suggested next steps

- **The `rewritten` arm still licenses regrowth, and it is this topic's own defect.** A shrink whose first line ALSO changed re-keys the block, so `_absorbable` absorbs it as `note rewritten` at exit 0, the old larger row stays, and the block can grow back to it without failing. Probed in-process: a plain shrink 8→6 exits 1, the same shrink with a reworded opening line exits 0, and a regrowth 6→8 under the new anchor exits 0. That is the commonest shape a prose pass produces — condensing a block's opening sentence — so the arm matters more than the one already closed. It cannot simply fail, because then every legitimate reword would.
- **Whether the report's line budget or its marker scheme should change.** `_clamped` bounds a line to 120 characters; below that width a line still wraps and its continuation carries no marker, so a `note retired:` row can render a second row beginning `fail closed,...`. Measured over the committed rows, the marker-bearing continuation appears at twelve widths between 20 and 260, including 103–107. The guard asserts only the bound, which is what holds.
