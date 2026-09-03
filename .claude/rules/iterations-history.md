# Iterations history

The per-iteration changelog is split by master-plan §12 phase: `docs/iterations-history-phase<N>.md`, indexed by `docs/iterations-history.md`. **Appending the entry is the final task of every implementation plan** — include it explicitly when writing a plan. Owed whenever the change alters a surface an operator or agent acts on, however small — the test is `spec-plan-locations.md`'s.

**Which file, entry format, and dataset-catalog sync are the `iteration-closeout` skill** (`.claude/skills/iteration-closeout/SKILL.md`): load it at closeout.

## Closeout-doc discipline

**Completed-work docs are authored at closeout, when the work is real — never pre-written during planning.** This covers status flips, "Done so far" sections, the changelog entry itself, and rule/doc text documenting behavior a not-yet-landed feature introduces — that lands with the feature. When writing a plan, capture these as explicit closeout tasks (with links to fill in), not edits made while planning. (Codifying a standing convention that already reflects how we work is not a completion claim and isn't gated to closeout.)

**On a long-lived branch, closeout is the branch's END**: re-verify the entry and every status claim the branch touched against the full branch log immediately before PR-open — an entry drafted mid-branch reads stale the moment later work lands beside it.
