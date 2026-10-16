# Rung 3 — the accumulation's records

`days.md` is rung 3's record, born with the rung, appended on the day by the coordinator, each entry with the clock's stamp as it printed; when an entry is written and what it carries are `engine-rung-3`'s in `infra/runbooks/engine-procedures.md`. It is append-only: a wrong reading is corrected by a later entry that names it, never by editing the earlier one.

A day's entry is appended on the week's branch, `records/rung3-week-<N>`, in its own worktree as the box's is — the main checkout stays on `develop`, the nightly data-gated run's tree — and the Monday carrying the week's read closes it; the next week's branch is cut from `develop` once its pull request merges, and `records/rung3-week-1` at the Sunday sitting, before the birth's entry. That pull request carries `days.md` alone, so the gate's records family (`infra/scripts/merge-gate.py`) exempts it from the pre-push read.
