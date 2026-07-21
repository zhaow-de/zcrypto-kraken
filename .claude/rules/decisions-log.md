# Decisions log

One git-tracked decision log **per phase**, `docs/research/<serial>.phase<N>-decisions.md`, records **subject-matter research decisions** — one paragraph per decision, prefixed `[iter-<NNN>]` (the iteration number tracked in `docs/iterations-history.md`); `<N>` is the master-plan-§12 phase whose subject matter the decision concerns (see *Routing*). Appended live and committed with each iteration's closing commit, exactly like the changelog — no draining, no continuation files. Applies in **both** interactive and unattended modes.

## The gate — when to log

Log **iff both** hold: (1) it's about the **subject matter** — research direction, choice of variants, scope, the R&D approach/hypothesis, the feature/model/label/universe/knob to try; and (2) you're in a **live research iteration** (an unattended `zcrypto-auto-exec` iteration, or an interactive session actively designing/running one). **Skip** when either fails — not in a live iteration, or about permission/approval, engineering/tooling/infrastructure, process, or formatting. Reversible tooling/process choices are still *decided* (autonomously) — just not logged.

## What to log

One paragraph per decision prefixed `[iter-<NNN>]`: the question, **2–3 options each with a short tradeoff**, and the resolution marked `(Decision: N)` — options laid out as fully as you'd present them. Example:

```markdown
[iter-042] Which feature/model variant to A/B next? (Decision: 2)
  1. **New feature set, current model** — add momentum + realized-vol features on the existing config. Cheap, isolates the feature contribution; limited upside if the model is the binding constraint.
  2. **Same features, different model class** — swap to a regularized linear model as a clean A/B. One knob changes, so the comparison is interpretable. Recommended — highest information-per-iteration.
  3. **New label horizon** — re-label to a longer forward return. Probes a longer-horizon edge but changes the target, so it's not like-for-like, muddying attribution.
```

- **Unattended:** log the decision **you** made — options, your pick with `(Decision: N)` + a one-line why. (A parked irreversible/high-stakes step goes here too, recorded as parked.)
- **Interactive:** log what the **user** answered — the numbered pick (which + gist), any freestyle "Other" text, or a one-sentence summary if it was resolved by discussion rather than a clean pick.

## Routing — one file per phase

Each decision appends to its phase's single decision log; there is no draining and there are no continuation files. To place a decision:

1. **Determine its subject-matter phase `N`** — the §12 phase whose subject matter it concerns, *not* the iteration's home phase (phases run concurrently: iter-088 was Phase-4 backlog but its §10 risk-layer decision is Phase 5). The §12 phases: 1 data foundation, 2 validation harness, 3 benchmarks, 4 alpha sprints, 5 portfolio assembly & risk layer, 6 execution — so alpha-family research → 4, combining validated sleeves into a deployable + the §10 risk layer → 5, execution/paper-trading → 6.
2. **Find phase `N`'s serial.** A phase's serial is fixed by its **first** `docs/research/` doc and shared by all its docs (Phase 1 `02`, Phase 4 `10`, Phase 5 `13`, Phase 6 `14`): if any `docs/research/<serial>.phase<N>-*` file exists, reuse that serial; if the phase has **no** doc yet, this decision log is its first doc — take the next-free serial (highest existing + 1).
3. **Append the `[iter-<NNN>]` entry** to `docs/research/<serial>.phase<N>-decisions.md` (create it if absent), committed with the iteration's closing commit.
4. **Post-close backlog:** when a **closed** phase (its `<serial>.phase<N>-…closeout…`/exit-bar report exists) receives its first entry after that close-out, precede it with a one-line `**Continuation — …**` divider between two `______` rules — cosmetic, the changelog's own convention. Pre-close entries stay verbatim above it, never edited.

**A decision bound to no phase** (rare — e.g. one that opens a brand-new phase) routes to the phase it concerns: a decision that *creates* a specific new phase is that new phase's founding entry (step 2, first doc). A decision that restructures §12 without a single target phase is a **master-plan revision** — captured by the `00.master-plan.md` edit and its commit, not a decisions-log entry.

**Decisions logs are verbatim** — kept off the mdformat allowlist; never let a formatter restructure their option lists or `(Decision: N)` markers.
