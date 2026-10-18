---
status: resolved
---

# A trial run on a branch that never merges spends uncounted

## Context — what

The trial registry lives in the tree, so a trial run and registered on a branch that is then abandoned, for example because its result was unwelcome, leaves no record on `develop`. The next trial in the family counts `--n-trials` from `develop`'s file, and nothing in the repo sees the abandoned run.

## Why this matters

`n_trials_in_family` feeds the deflated-Sharpe correction and the family's hard budget (A=40, B=25, C=10, master plan §12). Every abandoned branch understates both — the selection bias the registry exists to correct.

## Findings so far

- Spec 00129 (`docs/specs/00129-trial-provenance-design.md`) records each trial's invocation and commit and holds every record past 47 to its subject in CI; a record that never reaches `develop` is outside all of it.
- **Trial 48 ran ahead of this topic's decision (2026-10-16).** B1 trial 3 was pre-registered in `[iter-177]` decisions-log entries whose headers the earlier check did not match, since it grepped for `trial <N> shape` or `trial <N> pre-registration`. It was run and registered as record 48 on the unmerged branch `research/t0022-b1-candidate-hypotheses`, whose pull request carries the record to `develop`. The check now reads the registry rather than a header's spelling, which no convention fixes.
- Three shapes are in view, none measured: (1) the count reads pre-registrations, which land on `develop` before the run, so an abandoned run shows as a pre-registered trial with no record; (2) an append-only attempts log outside git, written at `--register` time and reconciled against `develop`'s registry; (3) a process rule — a trial runs and registers only on a branch with an open pull request, and a closed, unmerged one counts against its family, GitHub keeping closed pull requests.

## Resolution

Delivered by the pull request from `research/00133-t0222-abandoned-trials` (spec 00133, plan 00133), on the owner's ruling of 2026-10-17 as the spec records it: "/zcrypto-auto-exec resolve T0222 in full, if needed, ride it on T0022". The run was unattended, so no question was answered: the recommendation the spec builds on, its option 1, was taken.

- The measurement the first next step asked for is the spec's measured basis: the census of trials 1–48, each shape's cost to a research iteration and where each fails. No abandoned registration is on record, and no historical count or budget figure moves under the chosen shape.
- The decision the second asked for is the spec's option 1, this topic's second shape: a local attempts log, carried into the record (the `[00133]` entry in `docs/research/10.phase4-decisions.md`). The spec's option 2, that log plus an off-workstation mirror, and its option 3, pre-registration rows, this topic's first shape, are not built (spec 00133 D11); this topic's third shape, a trial only on a branch with an open pull request, is no option.

The branch's commits deliver:

- the trial-attempts log, hash-chained in the main checkout's `.local/`, and the count that reconciles it with the landed records, so every ruled run counts once, as the record it became or as an orphan;
- the hard budgets, A=40, B=25 and C=10, and each family's bucket, as literals in `cli/registry/budget.py` that CI asserts;
- `zcrypto research attempts-init`, which creates the log once, the committed allowlist of log ids `docs/reference/trial-attempt-logs.txt`, and a workspace transport whose `.local/` rsyncs exclude the log;
- the conftest fixtures that put each test's log and allowlist in its `tmp_path` and refuse the real ones at teardown;
- schema 6, under which a record past 48 and a reading past 1 carry the attempt their run's `begin` and `end` lines minted, a record also the orphans it counted;
- each ruled subject's declared family and trial count, at which its kill bar deflates;
- the register path's family, count, budget and log refusals, its provisional absorption of an open attempt, and the refusal of a ruled subject's plain eval;
- CI's checks holding every record past 48 to its family, count, budget, log and carry-forward;
- the decisions-log tie, under which a trial's header names every orphan its record counted.

The log exists: the workstation's main checkout holds `.local/trial-attempts.jsonl` (host `zcrypto-ops`), created by the branch's one `zcrypto research attempts-init` run, its id `60c9f39c37ec81b4a53396218b690304` the allowlist's row. `infra/scripts/workspace-transport.zsh` leaves it where it is only when the script a transport runs is this branch's: the earlier script mirrors `.local/` whole, copying the log onto the other machine or, run from there, deleting or overwriting it here, so a transport from the other machine leaves it in place only once this branch's script reaches that machine's checkout.
