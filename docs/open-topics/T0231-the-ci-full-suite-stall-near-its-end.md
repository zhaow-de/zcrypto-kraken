---
status: open
ripe_when: 'a date: 2026-12-02, a week of pull requests run under the `--durations=30` the CI pytest step gained — check: date -u +%F reads 2026-12-02 or later'
---

# The CI full suite stall near its end

## Context — what

The `Full test suite` check now takes 13 to 25 minutes where it took about 13 in early November, and the whole difference is one stall: near 95 % of the run's progress no progress line prints for minutes. Whether that is time inside tests or outside any test is not known.

## Why this matters

Every pull request waits on this check before it can merge, and in a stalled run the stall is most of that wait.

## Findings so far

- The suite's own work barely grew: 15477 tests passed in 812.47 s on 2026-11-05 (run 42013062299), 16442 in 794.04 s on 2026-11-25 (run 45601402669, #895).
- The stall, the longest gap between progress lines: 242 s at 96 % on 2026-11-05; 313 to 848 s at 95–97 % in ten of the eleven runs read from 2026-11-08 on; 62 s at 94 % in #895's run, which took 13 min; 848 s at 96 % in #896's run two hours later, 16442 tests in 1435.14 s.
- Not reproduced on the workstation: the collection's last 15 %, the stall band included, ran in 114.92 s at `-n 4 --dist load --maxschedchunk 4` with no test over 20 s; the heaviest, `tests/test_research_command.py`'s per-subject cases, are single-threaded (18.49 s pinned to one core, 18.77 s on all) and peak under 200 MiB; the tail's network, ssh, vault and sleep calls are mocked or bounded.

## Suggested next steps

- From 2026-12-02, list the runs since the flag merged: `gh api 'repos/zhaow-de/zcrypto-kraken/actions/workflows/test-suite.yml/runs?per_page=100' --jq '.workflow_runs[] | [.id, .run_started_at, .updated_at, .head_branch] | @tsv'`.
- For each, read its job's log — `gh api "repos/zhaow-de/zcrypto-kraken/actions/runs/<run id>/jobs" --jq '.jobs[0].id'`, then `gh api "repos/zhaow-de/zcrypto-kraken/actions/jobs/<job id>/logs"` — and record two things: the `slowest 30 durations` block, and the longest gap between two progress lines (`[ NN%]`) with the percentage it ended at.
- Name the tests whose durations cover the stall in stalled runs and are short or absent in an unstalled one, then put the fix to the owner: make their CI-only slow path fast where the cause is the runner, or change how the step schedules them (`--dist worksteal`, which drains whole shares after `-x`, or splitting a heavy parametrised case) where it is their placement. The block carries no worker or start time: when it names no test that explains the stall, say so, and put to the owner a `-v` run, whose result lines name each test's worker, to see what each worker ran across the gap.
- After each large test file's split merges (the engine executor, research command, ops daily and converge guard tests), read that pull request's own CI run and the next two on `develop` the same way — the stall's length and where it ends, the durations block — against the three runs before it: a split renames files, so it moves the collection order and what the scheduler deals to each worker. Record the six runs' readings in the split's pull request body.
