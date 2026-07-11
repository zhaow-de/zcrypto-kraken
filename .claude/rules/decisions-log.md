# Decisions log

The **per-phase** running logs `.tmp/decisions-phase<N>.md` (gitignored) record **subject-matter research decisions** — one paragraph per decision, prefixed `[iter-<NNN>]` (the iteration number tracked in `docs/iterations-history.md`); `<N>` is the master-plan-§12 phase whose subject matter the decision concerns (see *Phase persistence*). Applies in **both** interactive and unattended modes.

## The gate — when to log

Log **iff both** hold: (1) it's about the **subject matter** — research direction, choice of variants, scope, the R&D approach/hypothesis, the feature/model/label/universe/knob to try; and (2) you're in a **live research iteration** (an unattended `research-loop` iteration, or an interactive session actively designing/running one). **Skip** when either fails — not in a live iteration, or about permission/approval, engineering/tooling/infrastructure, process, or formatting. Reversible tooling/process choices are still *decided* (autonomously) — just not logged.

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

## Phase persistence — drain running logs into committed close-out siblings

Iterations only *append* to the running logs; git-persistence happens at a phase **close-out report**, never per iteration. **Route each decision by its subject-matter phase, not the iteration's home phase** — phases run concurrently (e.g. the attended Phase-6 build alongside resumed Phase-4/5 backlog), and one iteration can produce another phase's decision (iter-088 was Phase-4 backlog but its §10 risk-layer decision is Phase 5). The §12 phases: 1 data foundation, 2 validation harness, 3 benchmarks, 4 alpha sprints, 5 portfolio assembly & risk layer, 6 execution — so alpha-family research → 4, combining validated sleeves into a deployable + the §10 risk layer → 5, execution/paper-trading → 6.

**Trigger: a phase's close-out report drains EVERY non-empty running log** — the report written when its exit bar is met (§12 "Exit bar"/"Artifacts"); interim orientation/progress memos never trigger, and a phase §12 names no single report for (e.g. Phase 0) still gets a short dedicated boundary report as its trigger. At that close-out:

- **The closing phase's own log** → `<serial>.phase<N>-decisions.md`, `<serial>` = the close-out report's serial (e.g. `04.phase2-…-results.md` → `04.phase2-decisions.md`). One base file per phase.
- **Each already-closed phase's floating log** (backlog decisions made *after* that phase closed) → `<closed-serial>.phase<N>-cont-decisions-<K>.md`, reusing the closed phase's own serial (`10` Phase 4, `13` Phase 5) with `<K>` a per-phase counter (next = highest existing + 1, from **0**). This groups every Phase-`<N>` doc under its serial while the base file stays immutable.

So a close-out **fans out**: at the Phase-6 close-out, `decisions-phase6.md` → `<serial>.phase6-decisions.md`, `decisions-phase4.md` → `10.phase4-cont-decisions-0.md`, `decisions-phase5.md` → `13.phase5-cont-decisions-0.md`; later Phase-4 backlog drains at the Phase-7 close-out → `10.phase4-cont-decisions-1.md`.

Mechanics: **copy-then-truncate, never `mv`** — the gitignored running log must survive, so copy verbatim into the committed sibling, `git add`, then truncate it to empty. **Each continuation file opens with a one-paragraph memo** (what it continues, which close-out era drained it, the `[iter-<NNN>]` range), then the verbatim entries. **Decisions logs are verbatim** — never let a formatter restructure their option lists or `(Decision: N)` markers.

**Never cross a close-out with a running log un-drained** — the Phase 0 → 1 boundary drifted this way once (fixed retroactively by `docs/research/01.3.phase0-closeout.md`); the fan-out trigger sweeps **all** staged logs to prevent it.
