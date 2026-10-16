# Rung 2 — the box's records

`days.md` is the box's daily record: one entry per box day, appended on the day by the coordinator from the day's reads, each with the clock's stamp as it printed — an earlier stamp carrying an `x` or a `~` was not; what an entry carries is `engine-rung-2-box`'s in `infra/runbooks/engine-procedures.md`. It is append-only: a wrong reading is corrected by a later entry that names it, never by editing the earlier one.

A day's entry is appended on the week's branch, `records/rung2-week-<N>`, in its own worktree as `ops-journal`'s is — the main checkout stays on `develop`, the nightly data-gated run's tree — and the Monday carrying the week's read closes it; the next week's branch is cut from `develop` once its pull request merges. That pull request carries `days.md` alone, so the gate's records family (`infra/scripts/merge-gate.py`) exempts it from the pre-push read.
