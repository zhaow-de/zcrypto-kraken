---
status: resolved
---

# The prose ratchet converts every cut into silent headroom

## Context — what

`infra/scripts/prose-tripwire.py --check-baseline` fails only on an offender the baseline does not record **at that size or larger**. So the baseline's recorded size is a ceiling, not a fact about the tree: when a cutting pass shrinks a recorded offender, the entry keeps the old, larger size and thereafter licenses regrowth all the way back to it without failing. The run exits 0 either way, and nothing asks whether the ceiling should come down with the block.

## Why this matters

The ratchet exists to make prose decrease monotonically. Each cutting batch drops the tree away from a ceiling that does not move, in exactly the files that batch worked hardest on — the cut is real, but the guard against its undoing is weakened by the same edit. A later regrowth to the old size is then invisible to the commit gate, which is the one check that runs on every commit.

## Findings so far

- Measured twice, on the same entries both times: after PR #459, and again on `chore/prose-batch-c`. `cli/universe/rules.py:9` shrank 7 → 5 and still trips, so it reports `rewritten:`; `:55` shrank to 4 and no longer trips, so it reports `retired:`. Exit 0 on both runs.
- Two of the three cases are at least reported: `rewritten:` and `retired:` name what happened, and what is missing there is any consequence — neither reduces the recorded ceiling, and neither fails. The third is silent. `new_since` consumes a baseline entry per offender, taking an exact size match first and otherwise the smallest recorded size at least as large, and prints no line at all when the entry it consumed was the larger one — so a shrink spends a bigger ceiling silently.
- `prose.md` offered two dispositions when the hook named a block — cut it, or keep it consciously and re-record. Neither covered this case, because the hook named nothing: the tree got better and the baseline silently got looser. The resolution below routes it into the second disposition by making the hook name it and fail.
- [[T0195]] shared this topic's baseline-integrity surface and is resolved: `--write-baseline` refuses a path list that would drop another file's recorded keeps. It was fixed by refusing and NOT by the merge remedy it proposed, for this topic's own reason — scan-and-preserve-untouched would have carried forward exactly the stale, oversized rows this topic exists to stop licensing. So nothing here waits on it, and nothing there relieves it: what this topic names is `_absorbable()`'s path+kind-only matching, which never checks a size's own headroom before consuming it as a match, and that is untouched. (T0195's own defect was the truncating `open(..., "w")`, never `_absorbable()`.)

## Resolution

**A shrink now FAILS the gate until the row comes down with it, so the ceiling is no longer a ratchet in name only.** Landed on `fix/t0189-a-shrink-lowers-the-ceiling`. The check reports every shape of a shrink — the one it used to swallow entirely, the one it called `rewritten:`, and the rows it only counted as `retired:` — and an unbanked shrink exits 1, naming both sizes. The remedy is the re-record `prose.md` already prescribes for a conscious keep, taken in the same commit.

**The cheap form this topic proposed — `--check-baseline` rewriting a recorded entry down — is not available, and that is a fact about the gate rather than a preference between designs.** `--check-baseline` IS the pre-commit hook's command (`pass_filenames: false`, `always_run: true`, both stages), and a hook that writes a tracked file leaves it modified and unstaged, at which point pre-commit fails the commit. Every write stays with `--write-baseline`.

**Enforcement was parked once and then measured rather than argued.** The objection was that failing every unbanked shrink breaks whatever pass is cutting prose. Measured against the 34 files still queued in the cleanup: **6 carry baseline rows at all, 29 rows between them**, so a cut in the other 28 cannot trip the gate, and in the six the remedy is one extra command in one commit. That is the sanctioned workflow rather than a break. (The first run of that measurement returned a vacuous zero — the queue file is tab-separated and the join matched whole lines — so the figure above is the second, validated one.)

**The ceilings were banked in the same branch**, which is what actually lowered them: the ten rows standing above their observed size came down, and the two whose blocks no longer trip were dropped.

**Every line the check emits is clamped to one row.** The marker only means anything if no line wraps: a continuation can begin `fail ` by accident, since an anchor is arbitrary repo prose — 40 of the committed anchors contain the word — and a path is not sanitisable. Simulated across widths 20–260 over all committed rows, 9 continuations began with the marker before the clamp. Budgeting the anchor alone did not close it: the longest line was 164 characters and an unbudgeted path made it.

**The three shapes, measured on a fixture before the fix**: a shrink keeping its first line printed nothing at all; one whose first line changed came back as `rewritten:`; one falling below the bar was a bare integer in `retired:`. All three are named now, and a shrink exits 1.

**The slack this closed, measured on the committed baseline before banking**: 1229 rows, 1215 sitting exactly at their observed size, 10 above it, and 2 retired. The ten are not summable into one figure — six are `file-prose` percentages and four are `comment-block` line counts — so the slack is 5 lines across four blocks and 1.6 percentage points across six files. **Those numbers are small because the passes running that day kept re-recording the baseline, not because the defect is rare**: a later reader taking them as evidence that this barely happens would be reading recent discipline as a property of the tool.
