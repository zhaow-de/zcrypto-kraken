---
name: iteration-closeout
description: Use whenever a decision on a phase's subject is made or ruled — research, or execution (engine, order path, rungs and the box, risk limits, trade-path gates and their fleet) — in any session, on any branch, and at closeout to sync dataset catalogs. Load BEFORE writing the entry.
disable-model-invocation: false
---

# iteration-closeout

The change-index row is **not** this skill's: `open-pr` writes it into `docs/reference/change-index.md` before the pull request is created.

A branch-end status claim names the CLASS it covers ("every spec/plan commit on this branch"), never an enumeration or a count — an enumeration is falsified by the next commit that lands beside it.

## Dataset-catalog sync (every dataset-introducing closeout)

An iteration that introduces, relocates, or retires a dataset updates `docs/reference/data-catalog-full.md` **in the same closeout** — location(s), producer, schema/grid, consumption convention, caveats. The catalogs are the research loop's dataset inventory; the open-topics index carries a topic's title and trigger, but a loop brainstorming "what inputs exist?" reads the catalog — an uncataloged dataset is invisible to it.

## The decisions-log entry

**Log every decision on a phase's subject matter**, the phase's own subject — whichever session makes or hears it, attended or unattended, on whatever branch, whoever rules it:

- **Phases 1–5 — research:** the direction, variants, scope, the feature, model, label, universe or knob to try, a dataset's design, a trial's verdict.
- **Phase 6 — execution:** the engine's behaviour on the venue and its order path; a rung's or the box's entry, exit and rules; risk limits and kill trips; the gates that let an image or a converge onto the trade path; the tax pipeline that gates a ramp; and the fleet infrastructure under them, when the owner rules its design (`[iter-116]`, `[iter-124]` are the shape).

Skipped: permission, process, formatting, and engineering that touches none of the above. A reversible tooling choice is still decided autonomously, just not logged.

**When, and by whom:** the session that makes the decision or hears the ruling writes the entry on its own branch and commits it before the branch's whole-branch read (the `review` workflow), so the read covers it and `merge-pr`'s gate admits the head. A ruling given between branches rides the next branch that touches its subject, never a gitignored file alone. A plan whose tasks carry such a decision ends with the task that writes its entry, or its last task states `Decisions log: none — <reason>`.

### What to log

One paragraph per decision prefixed by its branch's key in the change index's grammar — `[iter-<NNN>]` when the branch minted one, else its spec serial `[<NNNNN>]`, else its topic `[T<NNNN>]` (the row's iter, spec and topic cells, in that order; a trial's verdict always rides an `[iter-<NNN>]`, which `tests/test_decisions_log_ties.py` reads): the question, **2–3 options each with a short tradeoff**, and the resolution marked `(Decision: N)` — options laid out as fully as you'd present them. Example:

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

1. **Determine its subject-matter phase `N`** — the §12 phase whose subject matter it concerns, *not* the iteration's home phase (phases run concurrently). The §12 phases: 1 data foundation, 2 validation harness, 3 benchmarks, 4 alpha sprints, 5 portfolio assembly & risk layer, 6 execution — so alpha-family research → 4, combining validated sleeves into a deployable + the §10 risk layer → 5, execution/paper-trading → 6.
2. **Find the phase's decisions log.** A phase has exactly ONE: `ls docs/research/*.phase<N>-decisions.md` names it — append there. A phase's research docs may span several serials, so never derive the log's serial from the phase's other docs. The glob matches nothing → create the log at the next-free serial: the highest serial BELOW 90 across `docs/research/` + 1 — the 90-series is the meta band (protocols, assessments) and never mints a phase log's serial.
3. **Append the keyed entry** to `docs/research/<serial>.phase<N>-decisions.md`, committed on the branch before its whole-branch read.
4. **Post-close backlog:** the first entry after a phase's closeout is preceded by one `**Continuation — …**` divider between two `______` rules (`tests/test_decisions_log_shape.py` holds the one-divider rule). Pre-close entries stay verbatim above it, never edited.

**A decision bound to no phase** routes to the phase it concerns: a decision that *creates* a new phase is that phase's founding entry (step 2, first doc). A decision that restructures §12 without a single target phase is a **master-plan revision** — captured by the `00.master-plan.md` edit and its commit, not a decisions-log entry.

**Decisions logs are verbatim** — kept off the mdformat allowlist; never let a formatter restructure their option lists or `(Decision: N)` markers.
