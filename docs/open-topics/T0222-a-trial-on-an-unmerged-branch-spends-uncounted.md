---
status: open
ripe_when: "an evaluation statement: a trial past record 47 is registered on develop, the first after this topic was registered — check: `git grep -h -c -E '\"trial_id\":(4[89]|[5-9][0-9]|[1-9][0-9]{2,})[,}]' -- docs/reference/trial-registry.jsonl` prints at least 1"
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

## Suggested next steps

- Measure each shape against the trials 1–47 as they were registered: which would have counted every run the decisions logs pre-registered, and what each costs a research iteration.
- Decide one with the owner, and land it before the next trial after record 48 runs; record 48 ran before the decision.
