---
status: open
ripe_when: 'refine-rules round 8 is on develop: `git log origin/develop --grep="^Refine-Round-Closed: 2026-09-05" --format=%h` is non-empty'
---

# The global prose cleanup under `prose.md`

## Context — what

Round 8 landed one prose rule (`.claude/rules/prose.md`: a durable file holds state and decisions, an event goes to git) and the tripwire that holds its thresholds (`infra/scripts/prose-tripwire.py`, PR #397). The rule stops new prose over the bar from entering; nothing yet removes what exists. The owner's word (2026-09-04): right after the round, a global scan of every existing comment, docstring and living doc under that rule — the third such cleanup, the first with a written bar.

## Why this matters

The retro study of 2026-09-04 measured the prose layer as the day's cost: 26 of 30 Critical or Important review findings were prose stronger than the mechanism beside it, and half of every component's wall-clock went into the review loop that found them. Comments and docstrings are a second, untyped layer only a second reader checks; the docs half (the phase changelogs, `fleet-pins.md`, `fleet.md`) had become a commit log and a story board respectively, reviewed like code.

## Findings so far

- Baseline on develop `f5400d19`, `.local/retro/2026-09-04/study/prose-ratio.py` (tokenizer count of comment + docstring lines): `cli/` 29%, `tests/` 21%, `infra/scripts/` 24%, total 27,479 prose lines of 112,950 (24%). Re-run the script for the after-number; never carry the figure.
- Tripwire census at `b655d00e`, `uv run python infra/scripts/prose-tripwire.py`: comment-block 1909, file-prose 183, table-row 98, section 352 (in 51 files), changelog-entry 135 — 2,677 offenders, exit 1. `--since origin/develop` reports 0, so the tool gates new prose while this topic is open.
- The docs half, measured 2026-09-04 on develop: `docs/iterations-history-phase6.md` 1,232 lines / 620 KB with entries of 1.9–7.5 KB; `docs/reference/fleet-pins.md` 45 lines / 14.5 KB with rows of 1,400–1,500 characters rewritten 38 times; `docs/reference/fleet.md` 80 lines / 20 KB.

## Suggested next steps

- **Three assignments, one PR per directory group, dispatched by `zcrypto-main`**: `cli/`; `tests/` with `infra/`; the three docs. Worklist per assignment: the tripwire's report for that scope; order by `.local/retro/2026-09-04/study/churn.md` (most-changed files first).
- **Per file, `prose.md`'s four dispositions** (cut, condense, keep, relocate), findings agreed before editing, false-or-stale first; a config file's non-comment lines extracted before and after and byte-identical; a test docstring re-read against its assertions.
- **The docs half**: each changelog entry collapses to one-line bullets naming what an operator or agent now does differently, with `git log` as the chronicle it collapses into; each `fleet-pins.md` row to its cells plus one clause of payload; `fleet.md` to topology, paths, endpoints and access, nothing dated.
- **Measured before and after**: the tripwire's summary line and `prose-ratio.py` on the merge-base and on the tip of each PR, quoted in the PR body; the pre-commit hook for the tripwire lands with the last PR, once `--since` is no longer needed to make the tool pass.
