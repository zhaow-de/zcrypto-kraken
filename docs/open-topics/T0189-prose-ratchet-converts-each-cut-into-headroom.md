---
status: partial
ripe_when: no commit in the last 50 on develop has touched the ratchet baseline -- `git log -50 --oneline develop -- infra/scripts/prose-tripwire-baseline.txt` is empty
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
- [[T0195]] shared this topic's baseline-integrity surface and is resolved: `--write-baseline` refuses a path list that would drop another file's recorded keeps. It was fixed by refusing and NOT by the merge remedy it proposed, for this topic's own reason — scan-and-preserve-untouched would have carried forward exactly the stale, oversized rows this topic exists to stop licensing. So nothing here waits on it, and nothing there relieves it: what this topic names is `_absorbable()`'s path+kind-only matching, which never checks a size's own headroom before consuming it as a match, and that is untouched. (T0195's own defect was the truncating `open(..., "w")`, never `_absorbable()`.)

## Done so far

The check now reports every shape of a shrink instead of swallowing one of them, and names the rows it used to only count. Landed on `fix/t0189-a-shrink-lowers-the-ceiling`, in `fix(prose_tripwire): a shrink is named where it used to be swallowed`.

Measured on a fixture before the fix: a shrink keeping its first line printed nothing at all; one whose first line changed came back as `rewritten:`; one falling below the bar was a bare integer in `retired:`. All three now print an indented line naming both sizes, and only the flush-left lines fail the gate, so an informational line cannot be mistaken for a failing one.

**The cheap form this topic proposed — `--check-baseline` rewriting a recorded entry down to the observed size — is not available, and that is a fact about the gate rather than a preference between two designs.** `--check-baseline` is the pre-commit hook's own command (`pass_filenames: false`, `always_run: true`, both stages). A hook that writes a tracked file leaves it modified and unstaged, and pre-commit then fails the commit. Auto-lowering would therefore break the gate on every prose-cutting commit. Every write stays with `--write-baseline`.

Measured on the committed baseline at the time of the fix: 1229 rows, 1215 sitting exactly at their observed size, 10 above it carrying 6.6 units of slack, and 2 retired. **That number is small because the passes running that day kept re-recording the baseline, not because the defect is rare** — a later reader taking 6.6 as evidence that this barely happens would be reading recent discipline as a property of the tool.

## Suggested next steps

- **Decide whether an unbanked shrink should FAIL rather than only report.** Reporting names the loss; it does not lower the ceiling, so a shrink nobody banks still licenses regrowth to the old size. Failing is the same code path plus an exit code, and it is the option that makes the ratchet monotonic. It was not taken now for sequencing rather than merit: a gate that fails every unbanked shrink breaks the commits of whatever pass is cutting prose at the time, and one was running. It becomes worth taking when prose-cutting stops being routine — which is precisely when the slack starts accumulating again, and is what the trigger above measures.
