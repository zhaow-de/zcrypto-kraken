# Iterations history

The per-iteration changelog is **split by master-plan §12 phase**: `docs/iterations-history-phase<N>.md`, one file per phase, with `docs/iterations-history.md` a thin index linking them (these are the only changelog files that live directly under `docs/`). Appending a new entry is the **final task of every implementation plan** — when writing a plan (superpowers:writing-plans), include it explicitly so it's never missed. **Skip the entry for trivial changes** that skip the committed spec/plan (see `spec-plan-locations.md`) — the changelog tracks substantive iterations, not one-file tweaks.

**Which file:** append to the changelog of the iteration's **subject-matter phase** — the same routing as the decisions logs (`decisions-log.md`), so an iteration doing Phase-4 backlog while Phase 6 is active lands in `iterations-history-phase4.md`, and a Phase-5 decision made during that work lands in `phase5`. Unlike the decisions logs, the changelog is committed **live per iteration** (not staged in `.tmp` and drained at close-out), so no continuation *file* is minted: a **closed** phase that receives later backlog entries just keeps appending them under a one-line `**Continuation — …**` divider (between two `______` rules) marking where the post-close backlog begins.

Each entry is a new section appended at the bottom of its phase file (`## <YYYY-MM-DD> — <heading>`) followed by a bullet list: one bullet per feature/change/fix, covering what landed, the artifacts/settings/log events it introduced, and any non-obvious behavior.

**Not part of this per-iteration close-out:** persisting a running decisions log (`docs/research/decisions-running-phase<N>.md`) into its committed close-out sibling is a **phase**-level close-out task — done once when a phase's close-out report is written, never per iteration. See `decisions-log.md` (*Phase persistence*).

## Dataset-catalog sync (every dataset-introducing closeout)

An iteration that introduces, relocates, or retires a dataset updates `docs/reference/data-catalog-full.md` (or `data-catalog.md` for v0-class sets) **in the same closeout** — location(s), producer, schema/grid, consumption convention, caveats. The catalogs are the research loop's dataset inventory; the open-topics index carries consumer-shaped pointers, but a loop brainstorming "what inputs exist?" reads the catalog — an uncataloged dataset is invisible to it (the 2026-07-15 discovery-gap finding: liquidations + the L2 panel ran for a day uncataloged).

## Closeout-doc discipline

The iterations-history entry is one instance of a broader rule: **completed-work docs are authored at closeout, when the work is real — never pre-written during planning.** This covers status flips (e.g. flipping an open-topic to `partial`/`resolved`, see `open-topics.md`), "Done so far" sections, the changelog entry itself, and rule/doc text that documents behavior a not-yet-landed feature introduces — that lands with the feature, not during its planning. When writing a plan, capture these as explicit closeout tasks (with the PR/spec links to fill in), not edits made during the planning phase — writing "this is done" while it only exists as a plan reads as done when it isn't, and goes stale if the design shifts. (Codifying a standing convention that already reflects how we work is not a completion claim and isn't gated to closeout.)
