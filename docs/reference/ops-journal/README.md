# Operations journal

One entry per daily pass, appended by `/zcrypto-daily-ops`. A quiet day and a day nobody looked are indistinguishable without it; the all-clear entry is the product, not the exception.

## Where

`docs/reference/ops-journal/<YYYY-MM>.md` — one file per month. Rotation is a new file, so a month's PR adds one file and can never conflict with a month of `develop` moving underneath it.

## The entry

A heading carrying the date and the verdict, then one paragraph of labelled clauses:

```markdown
## 2026-08-29 — all-clear

window 24 h to 2026-08-29 06:00Z · alerts none · checks all pass · logs 0 ERROR/CRITICAL lines ·
dead-men 0 down via Grafana, 10 read directly · deploys none ·
reminders refdata sweep: due in 5 days (last sweep 2026-08-04), healable re-derivation: counter unchanged in 24 h · actions none · follow-ups none
```

The verdict is one of `all-clear`, `attention`, `incident`. `tests/test_ops_journal.py` checks only that every heading parses and that dates increase within a file — greppable, not a schema, so the paragraph stays prose an operator can read.

## The branch

A standing branch, `ops-journal`, cut from `develop`. The pass commits to it after every run; at a month change it opens the finished month's PR, merges it on CI green, and re-cuts the branch from `develop`. That is the second standing exception to the attended PR-open gate, registered in `.claude/rules/branch-workflow.md`.

## What this is not

Not a backlog. If a pass produces work, it goes where work lives: something needing a decision opens a `T<NNNN>`, something needing doing goes in the memo queue. A journal that accumulates deferrals becomes a second parking lot competing with the open-topics list.
