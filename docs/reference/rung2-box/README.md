# Rung 2 — the box's records

`days.md` is the box's daily record: one entry per box day, appended on the day by the coordinator from the day's reads — the 12Z copy, the gate, the exports, the helper's draft, each placed intent's outcome and the owner's reads — each with the clock's stamp as it printed. It is a record, not prose: an entry is never re-trued by a later read, a wrong reading is corrected by a later entry that names it, and the file is append-only.

A week's entries reach `develop` in a records pull request on a branch named `records/<name>`, every file of which sits under this directory or the ops journal's; the merge gate exempts such a PR from the pre-push read (`infra/scripts/merge-gate.py`, the records family), as it exempts the ops journal's month PR, because a week of records has nothing for a reviewer to re-true. A PR that carries any other file takes every arm.

The condensed week note under the box decision in `docs/research/14.phase6-decisions.md` is the decision log's own summary of each week, written at the Monday weekly read; the decision log `data/rung2/decisions.jsonl` and the exports stay on the workstation, outside the tree.
