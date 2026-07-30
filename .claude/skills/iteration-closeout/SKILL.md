---
name: iteration-closeout
description: Use at an iteration's closeout — appending the iterations-history entry, appending decisions-log entries, syncing dataset catalogs — and whenever recording a subject-matter research decision mid-iteration. Load BEFORE writing either entry.
disable-model-invocation: false
---

# iteration-closeout

The closeout file mechanics. The ambient rules keep the WHEN (`.claude/rules/iterations-history.md` — the entry is every plan's final task; `.claude/rules/decisions-log.md` — the logging gate) and the closeout-doc discipline; this skill is the HOW.

## The iterations-history entry

**Which file:** append to the changelog of the iteration's **subject-matter phase** — the same routing as the decisions logs (`decisions-log.md`), so an iteration doing Phase-4 backlog while Phase 6 is active lands in `iterations-history-phase4.md`, and a Phase-5 decision made during that work lands in `phase5`. The changelog and the per-phase decision logs (`decisions-log.md`) now follow the **same** model: one file per phase, appended **live per iteration**, never drained into a separate serial file — so no continuation *file* is minted: a **closed** phase that receives later backlog entries just keeps appending them under a one-line `**Continuation — …**` divider (between two `______` rules) marking where the post-close backlog begins.

Each entry is a new section appended at the bottom of its phase file (`## <YYYY-MM-DD> — <heading>`) followed by a bullet list: one bullet per feature/change/fix, covering what landed, the artifacts/settings/log events it introduced, and any non-obvious behavior.

## Dataset-catalog sync (every dataset-introducing closeout)

An iteration that introduces, relocates, or retires a dataset updates `docs/reference/data-catalog-full.md` (or `data-catalog.md` for v0-class sets) **in the same closeout** — location(s), producer, schema/grid, consumption convention, caveats. The catalogs are the research loop's dataset inventory; the open-topics index carries consumer-shaped pointers, but a loop brainstorming "what inputs exist?" reads the catalog — an uncataloged dataset is invisible to it (the 2026-07-15 discovery-gap finding: liquidations + the L2 panel ran for a day uncataloged).

## The decisions-log entry

### What to log

One paragraph per decision prefixed `[iter-<NNN>]`: the question, **2–3 options each with a short tradeoff**, and the resolution marked `(Decision: N)` — options laid out as fully as you'd present them. Example:

```markdown
[iter-042] Which feature/model variant to A/B next? (Decision: 2)
  1. **New feature set, current model** — add momentum + realized-vol features on the existing config. Cheap, isolates the feature contribution; limited upside if the model is the binding constraint.
  2. **Same features, different model class** — swap to a regularized linear model as a clean A/B. One knob changes, so the comparison is interpretable. Recommended — highest information-per-iteration.
  3. **New label horizon** — re-label to a longer forward return. Probes a longer-horizon edge but changes the target, so it's not like-for-like, muddying attribution.
```

- **Unattended:** log the decision **you** made — options, your pick with `(Decision: N)` + a one-line why. (A parked irreversible/high-stakes step goes here too, recorded as parked.)
- **Interactive:** log what the **user** answered — the numbered pick (which + gist), any freestyle "Other" text, or a one-sentence summary if it was resolved by discussion rather than a clean pick.

### Routing — one file per phase

Each decision appends to its phase's single decision log; there is no draining and there are no continuation files. To place a decision:

1. **Determine its subject-matter phase `N`** — the §12 phase whose subject matter it concerns, *not* the iteration's home phase (phases run concurrently: iter-088 was Phase-4 backlog but its §10 risk-layer decision is Phase 5). The §12 phases: 1 data foundation, 2 validation harness, 3 benchmarks, 4 alpha sprints, 5 portfolio assembly & risk layer, 6 execution — so alpha-family research → 4, combining validated sleeves into a deployable + the §10 risk layer → 5, execution/paper-trading → 6.
2. **Find phase `N`'s serial.** A phase's serial is fixed by its **first** `docs/research/` doc and shared by all its docs (Phase 1 `02`, Phase 4 `10`, Phase 5 `13`, Phase 6 `14`): if any `docs/research/<serial>.phase<N>-*` file exists, reuse that serial; if the phase has **no** doc yet, this decision log is its first doc — take the next-free serial (highest existing + 1).
3. **Append the `[iter-<NNN>]` entry** to `docs/research/<serial>.phase<N>-decisions.md` (create it if absent), committed with the iteration's closing commit.
4. **Post-close backlog:** when a **closed** phase (its `<serial>.phase<N>-…closeout…`/exit-bar report exists) receives its first entry after that close-out, precede it with a one-line `**Continuation — …**` divider between two `______` rules — cosmetic, the changelog's own convention. Pre-close entries stay verbatim above it, never edited.

**A decision bound to no phase** (rare — e.g. one that opens a brand-new phase) routes to the phase it concerns: a decision that *creates* a specific new phase is that new phase's founding entry (step 2, first doc). A decision that restructures §12 without a single target phase is a **master-plan revision** — captured by the `00.master-plan.md` edit and its commit, not a decisions-log entry.

**Decisions logs are verbatim** — kept off the mdformat allowlist; never let a formatter restructure their option lists or `(Decision: N)` markers.
