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
- **Trial 48 ran ahead of this topic's decision (2026-10-16).** B1 trial 3 was pre-registered in `[iter-177]` decisions-log entries whose headers the earlier check did not match, since it grepped for `trial <N> shape` or `trial <N> pre-registration`. It was run and registered as record 48 on the unmerged branch `research/t0022-b1-candidate-hypotheses`, whose pull request carries the record to `develop`.
- Three shapes are in view, none measured: (1) the count reads pre-registrations, which land on `develop` before the run, so an abandoned run shows as a pre-registered trial with no record; (2) an append-only attempts log outside git, written at `--register` time and reconciled against `develop`'s registry; (3) a process rule — a trial runs and registers only on a branch with an open pull request, and a closed, unmerged one counts against its family, GitHub keeping closed pull requests.

## Resolution

Delivered by the pull request from `research/00133-t0222-abandoned-trials` (spec 00133, plan 00133), on the owner's ruling of 2026-10-17 as the spec records it: "/zcrypto-auto-exec resolve T0222 in full, if needed, ride it on T0022". The run was unattended, so no question was answered: the recommendation the spec builds on, its option 1, was taken.

- Measured: the spec's census of trials 1–48, each shape's cost to a research iteration and where each fails. No abandoned registration is on record, and no historical count or budget figure moves under the chosen shape.
- Decided: the spec's option 1, this topic's second shape: a local attempts log, carried into the record (the `[00133]` entry in `docs/research/10.phase4-decisions.md`). The spec's option 2, that log plus an off-workstation mirror, and its option 3, pre-registration rows, this topic's first shape, are not built (spec 00133 D11); this topic's third shape, a trial only on a branch with an open pull request, is no option.

Until this branch's `infra/scripts/workspace-transport.zsh` reaches both machines' checkouts, a transport mirrors `.local/` whole: run from the other machine it deletes or overwrites this one's `.local/trial-attempts.jsonl`, and run from here it copies the log there under the same id.
