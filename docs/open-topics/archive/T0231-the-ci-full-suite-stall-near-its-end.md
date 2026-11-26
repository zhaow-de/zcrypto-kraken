---
status: resolved
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
- The stall is `tests/test_cache_restart.py`. Its 22 tests are contiguous, items 3632–3653 of the 18501 develop collected at d987a46cc (19.6 %), and they carry about 1160–1190 s of wall-clock waits a run: the phase windows; the library's 10 s post-stop wait (`delay_post_stop_secs`, never set by `cli/engine/node.py`), paid by each of the 39 children that start a strategy; and the `[silent]` case's 58.4 s retry budget. The runner's CPU barely moves it: in the seven CI runs read (45643155231 to 45892938987), each of its entries varies by about a second, and the workstation reads the same within about a second.
- `--dist load` places that block. In pytest-xdist 3.8.0, `scheduler/load.py` refills only a worker below a sixteenth of the undealt tests, and it never takes a dealt test back. Most or all of the block lands on one worker early, and once the other three run dry, that worker runs the rest of its harness tests, then the queue behind them, alone. In five of the seven runs the gap ended close to the file's whole 1160–1188 s. Which worker draws the block, and how much of it, is read from gap arithmetic and a fitted model, since no run carries worker ids. The comment above the CI step said `--maxschedchunk 4` spread the harness tests over the workers. The cap sets how many tests a send carries, not which worker gets it.
- The workstation read above could not have seen the stall. The file sits at 19.6 %, outside the collection's last 15 %. And off `develop` and `main`, `tests/conftest.py` deselects slow cases that already passed: 18 of the file's 22 are in `tests/slow-cases.txt`.

## Resolution

- The owner's ruling of 2026-11-26, "Own step + no post-stop wait (Recommended)". It names the model's figure for the rest of the suite, from 986–1446 s to about 431–689 s, and its cost: a red run still waits for the harness step.
- `f25182d0a`: `.github/workflows/test-suite.yml` runs the harness as its own step of a `parallel:` group in the one `Full test suite` job, `uv run pytest tests/test_cache_restart.py -n 4 -m "not retired" --durations=30`. Beside it, the rest of the suite runs the old line with `--ignore=tests/test_cache_restart.py`. Under `CI=true` the two collect 22 and 18480 of the suite's 18502. `-x` does not stop the harness step. `tests/test_ci_suite_scope.py` holds the split and holds the `retired` deselection and the absence of coverage on both steps.
- `1d876e501`: the harness's child builds its node with `delay_post_stop_secs` 0. Locally, at `-n 4 --dist load --maxschedchunk 4`, the file went from `22 passed in 401.96s (0:06:41)` on develop's d987a46cc to `22 passed in 231.63s (0:03:51)`. Its four longest tests went from 125.16, 101.87, 91.36 and 76.47 s to 85.28, 81.33, 61.93 and 58.68 s.
- `ef65e1dcf`: the child reads the cache's orders and positions again after `run()` returns, and every record must read them as at the window's stop. Under the 10 s wait, all 39 children that reach the stop held to it, 36 of them holding an order or a position. They held to it at 0 too, so the shorter wait drops no change to the cache that a test reads.
- This topic's next steps also asked for readings after each large test file's split merges: the stall's length and the durations block on that pull request's run and the next two on `develop`. Those readings belong to the splits, queued for a spec of their own at refine round 26 (`45171a73b`). They stay with that work, not with a new topic. With the harness out of the pool, they no longer look for this stall.
