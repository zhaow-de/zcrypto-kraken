# Rung 2 — the box's records

`days.md` is the box's daily record: one entry per box day, appended on the day by the coordinator from the day's reads, each with the clock's stamp as it printed — the first two entries' `xZ` minutes are placeholders a record does not correct in place; what an entry carries is `engine-rung-2-box`'s in `infra/runbooks/engine-procedures.md`. It is append-only: a wrong reading is corrected by a later entry that names it, never by editing the earlier one.

A day's entry is appended in the main checkout on the week's branch, `records/rung2-week-<N>`, cut from `develop` after the previous week's pull request merges. A week's entries reach `develop` in a records pull request on that branch, every file of which sits under this directory or the ops journal's; the merge gate exempts such a PR from the pre-push read (`infra/scripts/merge-gate.py`, the records family), because a week of records has nothing for a reviewer to re-true.
