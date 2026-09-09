---
status: resolved
---

# `--write-baseline` truncates the whole baseline to whatever paths are scanned

## Context — what

`infra/scripts/prose-tripwire.py --write-baseline <out> [paths...]` does not merge into the
existing baseline -- it computes `offenders = scan(paths)`, with `paths` defaulting to the whole
repo's live prose only when none are given (`prose-tripwire.py:427`), and opens `<out>` in
truncating write mode (`prose-tripwire.py:433-434`), replacing its entire content with exactly what
that one scan found. Passed the committed baseline path together with any subset of files smaller
than the whole tracked tree, it silently discards every recorded keep for every file NOT in that
subset.

Measured, on develop (`e53b6eba`): the committed baseline is 1228 lines.
`prose-tripwire.py --write-baseline <scratch> tests/test_cli.py` (a file carrying zero current
offenders) writes a 0-line file. The same command, scoped instead to the files a correction batch
had just touched, would replace 1228 recorded keeps with only that batch's handful of rows.

## Why this matters

The baseline is the prose ratchet's whole memory of what a past pass judged over the bar and
consciously chose to leave. It is committed, but in effect unversioned between edits -- nothing
about the file's own shape distinguishes a full, correct baseline from one scoped to whatever paths
the last `--write-baseline` invocation happened to pass. A session correcting one file's entries,
reading `--write-baseline PATH` as "the tool for recording a keep" without also passing every other
tracked path carrying an entry, truncates the whole repo's ratchet memory in one write -- and the
failure is loud only afterwards, the next time `--check-baseline` runs unscoped and reports
thousands of already-accepted blocks as `new` offenders.

## Findings so far

- `prose-tripwire.py:427`: `paths = expand_paths(args.paths) if args.paths else default_paths()` --
  `paths` is exactly what the caller passed, with no union against the existing baseline file's own
  recorded paths.
- `prose-tripwire.py:433-434`: `with open(args.write_baseline, "w", encoding="utf-8") as fh:
  fh.write(baseline_text(offenders))` -- `"w"` mode, so the file's prior content is discarded
  before the new content is written, regardless of what that new content covers.
- Measured on `develop` (`e53b6eba`), the same tree and figure as above: `--write-baseline
  <scratch> tests/test_cli.py` (0 offenders in that file) produces a 0-line file. The same flag,
  scoped to fewer than every tracked path carrying a baseline entry, produces a strict subset of
  the real baseline every time -- reproduced at 0 lines here, and it would have been on the order
  of a handful of rows had it instead been pointed at a small correction's own touched files with
  the committed baseline as `<out>`. A figure like this crosses every commit that touches the
  baseline; re-derive against the tree in hand rather than reuse it.
- The safe alternative, used on that branch instead of the flag: hand-edit the specific lines a
  batch's own correction changed or added, keyed by `(path, kind, anchor)` per `prose-tripwire.py`'s
  own `Offender.key`, then prove it with `--check-baseline <baseline> <touched paths>` reporting
  `new: 0 grown: 0` for exactly those paths.
- **That proof bar has a blind spot the same branch also hit.** A hand-edited docstring whose FIRST
  line changes re-keys its anchor, so its old baseline row no longer matches by `(path, kind,
  anchor)` -- but `_absorbable()` still claims it via a path+kind-only fallback, so the stale row
  (now naming text the file no longer carries) neither reports nor blocks. `--check-baseline`
  reporting `new: 0 grown: 0` is not proof the baseline's anchors are current, only that nothing
  regressed past a recorded ceiling; the anchor itself has to be re-verified against the file by
  hand. Shares its baseline-integrity family with [[T0189]] (a shrink licenses silent regrowth to
  the old ceiling) and neither topic pointed at the other until now: T0189's shrink-without-lowering
  defect and this topic's stale-anchor-still-absorbed defect are two ways the same `_absorbable()`
  fallback hides drift, and the merge remedy weighed at the time, if built as scan-and-preserve-untouched,
  would compound T0189's problem rather than fix it -- a change to one needs the other in view.

## Resolution

`--write-baseline` refuses when its target already records a path the scan does not cover, naming how many and the first of them, and writes nothing. A first write to a target that holds no baseline, and an unscoped write, are unchanged.

Refusing rather than merging is the ruling this topic asked for and it is the one [[T0189]] forces: the merge option — scan the given paths, preserve every other path's rows — would carry forward exactly the stale, oversized rows T0189 exists to stop licensing. A refusal preserves nothing and licenses nothing, so T0189's ceiling question is untouched, and the `_absorbable()` stale-anchor blind spot recorded above stays with T0189, which is open and names it.

Measured on `develop` at the fix, the figure re-derived rather than reused: the committed baseline is 1229 lines there. Against a scratch copy of it, `--write-baseline <copy> tests/test_cli.py` exits 0 and leaves 0 lines on the pre-fix tool, and exits 2 leaving 1229 on the fixed one.
