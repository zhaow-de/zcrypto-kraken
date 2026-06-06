# Decisions log

`.tmp/decisions.md` (gitignored) is the running log of **subject-matter research decisions** — one paragraph per decision, each prefixed with `[iter-<NNN>]` (the current iteration number, the kind tracked in `docs/iterations-history.md`). It applies in **both** interactive and unattended modes — not only the research loop.

## The gate — when to log, when to skip

Log a question/decision **if and only if BOTH hold:**

1. **It is about the subject matter** — research direction, choice of variants, subject scope, the R&D approach or hypothesis, the feature / model / label / universe / knob to try, and the like.
2. **You are in a live research iteration** — an unattended `research-loop` iteration, **or** an interactive session where you are actively designing/running a research iteration (the kind recorded in `docs/iterations-history.md`).

**Skip the log** (do NOT record) when either fails: you are **not** in a live research iteration; or the question is about permission/approval, engineering/tooling/infrastructure, process/admin, formatting, or anything that is not the research subject matter. Reversible tooling/process choices still get **decided** (autonomously, in the loop) — they just aren't logged here.

## What to log

Only once the gate above passes (both predicates hold) — then, by mode:

**Shared format.** One paragraph per decision, prefixed `[iter-<NNN>]`: the question, **2–3 options each with a short tradeoff**, and the resolution marked `(Decision: N)`. Lay the options out as fully as you would to present the decision. Example:

```markdown
[iter-042] Which feature/model variant to A/B next? (Decision: 2)
  1. **New feature set, current model** — add momentum + realized-vol features on the existing model config. Cheap, isolates the feature contribution; limited upside if the model is the binding constraint.
  2. **Same features, different model class** — swap the model for a regularized linear one as a clean A/B. One knob changes, so the comparison is interpretable. Recommended — highest information-per-iteration on what's prepared.
  3. **New label horizon** — re-label to a longer forward return, same features + model. Probes a longer-horizon edge but changes the target, so it's not a like-for-like A/B, muddying attribution.
```

**Unattended (autonomous) mode** — log the decision **you** made: list the options, pick the most beneficial, record the pick with the `(Decision: N)` marker plus a one-line why. (A parked irreversible / high-stakes step goes here too — recorded as parked, not decided.)

**Interactive mode** — log what the **user** answered:

- They picked a numbered option → record that choice (which option, and the gist).
- They also filled the **freestyle** input (the "Other" / last numbered option) → log that freestyle text too.
- The resolution came from the **"Chat about this"** path (you discussed it instead of a clean option-pick) → summarize the chat's conclusion into key phrases or one sentence, and log that.

## Phase persistence — the running log becomes a committed sibling of the phase's close-out report

`.tmp/decisions.md` is a **running scratchpad, drained once per phase — not per iteration.** A research **phase** (the phased-plan unit of `docs/research/00.master-plan.md` §12 — data foundation, validation harness, benchmarks, alpha sprints, portfolio assembly) spans **several iterations** (the superpowers unit: one `specify → plan → execute → verify` pass). Every phase iteration only *appends* its subject-matter decisions here (each prefixed `[iter-<NNN>]`); they accumulate across the whole phase. Because the file is drained at each phase close-out (below), it holds exactly the **current** phase's entries — the contiguous `[iter-<NNN>]` range since the last drain.

**Trigger — the phase's close-out report, and only that one.** A phase may also emit interim documents (an orientation memo, a mid-phase progress note); **those do not trigger persistence.** Persistence fires **once per phase**, when the phase's **close-out report** — the report written when its exit bar is met (master plan §12 "Exit bar" / "Artifacts") — lands under `docs/research/`, authored in **either mode** (whoever writes it). At that point, persist the phase's decisions into a committed **sibling of that report**:

- **Name & location:** same directory, named `<serial>.phase<N>-decisions.md`, where `<serial>` is the **close-out report's** serial prefix and `<N>` the phase number — e.g. close-out report `04.phase2-stage2-results.md` → sibling `04.phase2-decisions.md` (keep the serial, drop the report's descriptive tail). **One decisions file per phase**, keyed to the close-out report's serial.
- **Persist = copy-then-truncate, not `mv`.** `.tmp/decisions.md` is gitignored and must survive for the next phase, so: **copy** its contents **verbatim** into the sibling, `git add` the sibling, then **truncate `.tmp/decisions.md` to empty** — never `mv` or delete the running file itself. Normally the whole content moves (it holds only this phase's entries, decisions + any parked / stop notes); if it somehow straddles phases, move only this phase's `[iter-<NNN>]` range and leave the rest for its own close-out.
- **Verbatim — keep it OFF the mdformat allowlist.** Commit it as-is; do **not** add the `-decisions.md` file to the mdformat `files:` list in `.pre-commit-config.yaml`, and do **not** count it as a "research paper" for the CLAUDE.md allowlist-append rule — mdformat would renumber/reflow its option lists and the `(Decision: N)` markers. The close-out report itself may be on the allowlist; its `-decisions.md` sibling never is.

**This is a phase close-out task, never an iteration one.** Iteration close-out only *appends* to the running `.tmp/decisions.md` (and to `docs/iterations-history.md`, per `iterations-history.md`); git-persistence of the decisions happens **once per phase**, when its close-out report is written — never per iteration.
