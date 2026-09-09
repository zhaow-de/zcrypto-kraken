---
status: open
---

# `--write-baseline` truncates the whole baseline to whatever paths are scanned

## Context — what

`infra/scripts/prose-tripwire.py --write-baseline <out> [paths...]` does not merge into the
existing baseline -- it computes `offenders = scan(paths)`, with `paths` defaulting to the whole
repo's live prose only when none are given (`prose-tripwire.py:427`), and opens `<out>` in
truncating write mode (`prose-tripwire.py:432-433`), replacing its entire content with exactly what
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
- `prose-tripwire.py:432-433`: `with open(args.write_baseline, "w", encoding="utf-8") as fh:
  fh.write(baseline_text(offenders))` -- `"w"` mode, so the file's prior content is discarded
  before the new content is written, regardless of what that new content covers.
- Measured on `docs/prose-gap-round2-batch1`: committed baseline 1228 lines;
  `--write-baseline <scratch> tests/test_cli.py` (0 offenders in that file) produces a 0-line
  file. The same flag, scoped to fewer than every tracked path carrying a baseline entry, produces
  a strict subset of the real baseline every time -- reproduced at 0 lines here, and it would have
  been on the order of the batch's own row count (single digits) had it instead been pointed at the
  batch's own touched files with the committed baseline as `<out>`.
- The safe alternative, used on that branch instead of the flag: hand-edit the specific lines a
  batch's own correction changed or added, keyed by `(path, kind, anchor)` per `prose-tripwire.py`'s
  own `Offender.key`, then prove it with `--check-baseline <baseline> <touched paths>` reporting
  `new: 0 grown: 0` for exactly those paths.

## Suggested next steps

- **Make the destructive path harder to reach by accident.** Options to weigh, not a decision made
  here: `--write-baseline` could refuse (or warn loudly) when given an explicit `paths` list
  narrower than what the existing baseline file already covers; or the flag could default to a
  merge (scan the given paths, keep every other path's existing rows untouched) with a separate,
  explicitly-named flag for a full, deliberate regeneration.
- **This is a guard-construction fix** (a tool that judges the tree, guarding the prose ratchet), so
  it takes the same construction proof `agent-ops.md` requires of any such guard before it ships: a
  fixture where the truncation defect and the corrected behaviour differ, and a true-positive
  fixture (a legitimate full-tree `--write-baseline` run) that must still pass.
- **Cannot ride a prose-only branch.** `prose-tripwire.py` is code, and any fix to this changes its
  AST -- it needs its own branch and its own review, not a fold-in to a docs-kind batch.
