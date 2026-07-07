---
name: research-loop
description: Use when the user asks to run the unattended / overnight / autonomous research loop (e.g. invokes /research-loop, "run research overnight while I'm away", "keep iterating autonomously"). The autonomous (unattended) research mode that runs reversible experiments — feature/signal/validation research and the heavy compute, sweeps, and tooling they need — with NO questions and NO waiting, holding hard-to-reverse actions, pre-registered escalation triggers, and high-stakes judgment for an interactive session, advancing the research master plan phase by phase toward its exit bars.
disable-model-invocation: true
---

# research-loop

## Overview

Run the project's research iterations **unattended** — the same brainstorm → spec → plan → subagent-driven execution → A/B verdict → merge cycle this repo runs interactively, but with **zero human interaction**. The human is away; nobody will answer. Your job is to keep the research moving autonomously and leave a reviewable trail.

This is the **standing autonomous procedure**. It is not tied to any particular past run; each run picks up the current backlog and iterates until the morning time-gate.

**Overall goal:** advance the research master plan — `docs/research/00.master-plan.md`, the project's north-star document — toward the **current phase's exit bar** (identify the current phase from the decision log, `docs/iterations-history.md`, and repo state). The loop owns the plan's autonomous work across its phases (data foundation → validation harness & cost model → benchmarks → alpha research sprints → portfolio assembly); each iteration is one *specify → plan → execute → verify → calibrate* pass of the plan's loop discipline (§12). The bar is **benchmark-relative**: the deployable system is the best member of {benchmarks ∪ validated survivors} under the full validation protocol (§9) — an honest kill, a negative result, or "benchmark B4 wins" is **success**, not failure. Optimize for verdicts the trial registry can defend, not for a shiny headline number — and no verdict outranks the instrument that measured it (see *Distrust the instrument — QA before any verdict*).

**The stack is ratified** (master plan §7, Option 4): a lean custom research + validation core (polars, purpose-built CPCV/DSR/bootstrap/trial-registry, explicit Kraken cost model) now, NautilusTrader for execution at Phase 6. **Qlib is not part of this project** — PoC-era material (docs, templates, habits) that assumes Qlib is stale; don't let it steer the loop.

Stay in the **research domain** — Phase 6 (execution engine, paper trading, go-live) and the Decision Register's human touchpoints (§12) belong to attended sessions.

## Interactive vs. autonomous: the division of labor

The split is the master plan's **autonomy contract** (§12), and this loop implements its autonomous side. Knowing which side of the line you are on is the **first** thing this loop does. The boundary is **reversibility and judgment — NOT topic, and NOT how heavy the work is.**

- **AUTONOMOUS (this loop, unattended).** Anything **reversible / discardable** runs here, no matter how heavy. It lands on a branch, is reviewable, and a bad result is simply thrown away — so the cost of being wrong is near zero. This explicitly **includes heavy work**: large backtests, CPCV sweeps, long-running experiments, and even **building substantial tooling, harnesses, fetchers, or pipelines** when that scaffolding is itself reversible (a branch you can discard). It equally includes **read-only public research** — WebFetch on public docs, fee schedules, API references, and venue/market-structure articles — to resolve the researchable half of account/venue questions autonomously (a read is reversible; nothing is gated behind it). It also includes the register's **autonomous-with-defaults** decisions — rule-driven universe finalization, the pre-registered trial budgets (A=40 / B=25 / C=10 per family), the holdout definition, the Phase 5 combination default, benchmark parameter grids: run them on the stated defaults without asking; only their named escalation triggers escalate.
- **INTERACTIVE (attended, with the human).** Two things wait for an attended session, because their cost-of-being-wrong is high:
  1. **Hard-to-reverse or destructive actions** — anything touching **live / paper trading or production**, anything **published externally** (an upstream issue/PR, a release), **overwriting or deleting canonical datasets** (they are immutable and hash-versioned; derive to new paths instead), **spending money** (paid data tiers, infrastructure, subscriptions), and anything that could interrupt the **running capture pipeline** (L2 gaps can never be backfilled — a disrupted capture daemon is permanent data loss).
  2. **High-stakes judgment calls and the plan's pre-registered escalation triggers** — a major strategic pivot, an architecture lock-in, every "good enough to deploy?" call; plus, by name (§12 / Phase 4): **expanding a trial budget**, **abandoning a Bucket-A family early**, **any new data spend**, **any touch of the holdout** (look budget = 1, spent in Phase 5 in the human's presence), the universe rule yielding <8 or >15 names or diverging materially from the plan's table, conflicting survivors at Phase 5 combination time.

The Decision Register (§12) is the **complete** list of human touchpoints — everything not on it runs autonomously on defaults, with the triggers above as the only parks. The reversible experiments the loop does — a new feature family or transform, a different signal/ensemble parameterization, a new label or horizon, a different universe tier or cost scenario, a clean A/B against a family's baseline, plus the tooling and compute to run them — are **examples of "reversible," not the definition of the loop's scope.** If a heavy or infrastructural task is reversible, it is in scope.

Phase 6 preparation (execution engine, paper/live trading) stays **out of this loop entirely** — not because it's heavy, but because it is hard-to-reverse / production-facing and belongs to an attended session.

### The Iron Rule vs. the boundary — how they fit together

These two rules look like they conflict; they do not, because they govern **different kinds of decision**:

- The loop **owns every small, reversible research decision** — which feature, signal, label, universe tier, or knob to try next. For these you **decide → log if it's a subject-matter live-iteration decision (per `.claude/rules/decisions-log.md`) → continue.** A wrong such decision is just a discardable experiment on a branch; throwing it away costs nothing. The Iron Rule (below) tells you to make these yourself, and you do.
- Only a **hard-to-reverse action**, a **pre-registered escalation trigger**, or a **high-stakes judgment call** (the interactive cases above) is reserved for the human. "Judgment work waits for interactive mode" means **that** judgment — irreversible/high-stakes — **not** the ordinary reversible decisions the Iron Rule tells the loop to make.

So there is no contradiction: the loop decides freely on everything cheap-to-reverse, and parks only the rare irreversible/high-stakes step.

### The "park the irreversible step, not the heavy work" rule

Sometimes an iteration's natural path would require a hard-to-reverse action, an escalation trigger, or a high-stakes judgment call the loop should not make alone. When that happens:

1. **Do the reversible parts autonomously — including the heavy compute.** Run the backtests, the sweeps, build the reversible tooling. None of that is gated by the presence of an irreversible step elsewhere in the idea.
2. **Prefer a reversible variant that avoids the irreversible step.** Reframe the hypothesis so the whole thing can run reversibly tonight (e.g. write to a new dataset path instead of overwriting; draft an upstream issue locally instead of filing it; run the within-budget variant instead of the one that needs a budget expansion or a paid data tier). A clean experiment you *can* run reversibly beats a perfect one that needs an irreversible action.
3. **Park ONLY the irreversible / high-stakes step** for the next interactive session — log it (per `.claude/rules/decisions-log.md`, recorded as parked) and/or capture it as an R&D open-topic (per `.claude/rules/open-topics.md`). Then immediately continue with the reversible variant or the next work package.
4. **Decompose a mixed topic — do the researchable half, park only the human-gated half.** A parked topic that touches the account or venue (e.g. the Phase-0 account-actions topic) usually **mixes** autonomously-researchable sub-items — public web research, data, and code (the AUTONOMOUS activities above) — with sub-items that genuinely need the human (a login, a key, money). **Resolve the researchable sub-items autonomously and record them; park only the login/human ones.** "Human-gated" is per sub-item, not per topic (`.claude/rules/open-topics.md`). Leaving a topic's public-research half unpursued because the topic is "about the account" is exactly the miss the drain invariant forbids.

**Never stop, and never take the irreversible / destructive action unattended.** Parking is not a stop — you park the one step and keep moving. Heavy or infrastructural work is **not** what gets parked; only the irreversible/high-stakes step is.

## The Iron Rule of autonomy

**Never stop to ask. Never wait for input. Never defer a reversible choice to the human.** There is no human to respond — pausing means the loop dies.

When you hit ANY reversible question or decision (a design fork, an ambiguity, an approval gate, a "which option" choice):

1. **List the options** (2-3) and their tradeoffs.
2. **Evaluate** them and **pick the most confident / most beneficial** one.
3. **Log** it — if it's a subject-matter research decision in this live iteration, record it per `.claude/rules/decisions-log.md` (the gate and format live there). Routine tooling/process decisions you still decide, but they're outside the log's gate — don't record them.
4. **Continue** immediately with your pick.

This protocol **replaces** the repo's default "Rule 1: ask when unclear" *for the duration of the loop*. You still surface tradeoffs — but for subject-matter decisions you surface them **into the decisions log**, then decide and proceed. The human reviews `.tmp/decisions.md` later and can correct course; that is the safety net, not a blocking question. (The narrow exception is a genuinely hard-to-reverse action, an escalation trigger, or a high-stakes judgment call — park that one step, per the boundary above; everything reversible, you decide.)

**There are exactly two ways the loop ends — nothing else is a stop:**
1. **The 08:00 Berlin time-gate** (step 10) — the normal end of an overnight run.
2. **A genuinely unrecoverable blocker** you cannot fix after real effort (e.g. the dataset is gone, the environment won't run). Even then: jot what blocked you at the end of `.tmp/decisions.md` before stopping (a free-form stop-note, not a gated decision entry).

Everything else that *feels* like a stopping point is NOT one — keep going:
- **An empty / exhausted open-topics backlog is NOT a stop** → manufacture the next work package (harden the harness, deepen QA, next family within budget — see Constraints & special cases).
- **A failed or negative-result iteration is NOT a stop** → record the verdict, pick the next thread, continue.
- **A mid-execution error is NOT a stop** → diagnose, fix, continue (step 6).
- **A reversible decision/ambiguity is NOT a stop** → decide → log if it's subject-matter (per the rule) → continue (above).
- **An idea with a hard-to-reverse step or an escalation trigger is NOT a stop** → do the reversible parts (incl. heavy compute), park only that step, run a reversible variant or the next package (the park rule above).

**The approval gates are pre-satisfied.** Invoking the loop IS the human's standing approval. So:
- `superpowers:brainstorming`'s HARD-GATE (design approval before implementing) → satisfied by the recorded decisions + your spec self-review. Proceed to writing-plans without waiting.
- the spec user-review gate → satisfied; do your own self-review and move on.
- the executing-plans / subagent-driven-development handoff → just start; don't ask which mode.
- the PR merge → merge it yourself via `merge-pr` when green (do NOT stop at the PR for human approval, unlike attended mode).

## The loop (one iteration)

1. **Pick a work package.** Source it from: the **master plan's current phase** (its autonomous-loop items, worked toward the phase exit bar), the *Suggested next steps* of the **last iteration** (`docs/iterations-history.md`), and the **R&D open-topics** (`docs/open-topics/README.md`, the `## Research and development` Open/Partially-done lists). The master plan governs — a backlog item that contradicts it (or predates it, e.g. PoC-era leftovers) is stale; drop or re-frame it against the plan. In the alpha-sprint phase, follow the ranked family queue (§5) and **never spend trials beyond a family's pre-registered budget**. Keep the package **small**: one hypothesis + a suggested validation approach, sized for a single iteration. It may be heavy (a big sweep, a long backtest, building reversible tooling) — that's fine, as long as it's reversible. If its natural path includes a hard-to-reverse action, an escalation trigger, or a high-stakes judgment call, apply the park rule: pick a reversible variant and park only that step. If no feasible package remains, **create one** (see Constraints & special cases).
2. **Brainstorm** it with `superpowers:brainstorming` as a new iteration — autonomously (apply the Iron Rule to every question the skill would ask). As part of brainstorming, review `docs/open-topics/README.md` (Open + Partially done) and fold in anything relevant to this iteration — addressing a topic pops it from the list (close/partial + index sync per `.claude/rules/open-topics.md`).
3. **Spec self-review** — run the brainstorming self-review; fix inline. (No user review gate — proceed.)
4. **Plan** with `superpowers:writing-plans`.
5. **Execute** with **`superpowers:subagent-driven-development`** (fresh-subagent-per-task + per-task review + final whole-branch review).
6. **Handle issues mid-execution** — if something breaks (a failing test, a runtime error, a stale lock, a tooling gap), **diagnose and fix it, then continue**. Don't abandon the iteration; don't wait. Use `superpowers:systematic-debugging` for non-trivial failures. Building the missing tooling is fair game when it's reversible; only a hard-to-reverse fix gets parked (work around it tonight; park that step).
7. **Closeout** — run the instrument checks first (*Distrust the instrument*, below): treatment engaged, metrics plausible, no tainted measurement path. Then produce the **A/B verdict** — hypothesis, spec hash, dataset hash, result, verdict: adopt/reject/park — recorded per `.claude/rules/decisions-log.md` and, once the Phase 2 harness exists, as an entry in the **append-only trial registry** (never an unlogged "it seemed better"). **Suggest the next step** based on the result. Write the iterations-history entry. This *appends* to the running (gitignored) `.tmp/decisions.md`; **git-persisting** the decisions log is a **phase**-close-out task (a phase spans several iterations), done only when the phase's close-out report is written — never here per iteration (see Constraints).
8. **Capture follow-ups** — if multiple next steps surface, or you discover a better next step than the current backlog, or you spot a new tangent worth tracking (including any parked irreversible/trigger/judgment step), write them into `docs/open-topics/` (new `T<NNNN>` topic files + index, per `.claude/rules/open-topics.md` — opening is autonomous, no approval needed), logging the rationale per `.claude/rules/decisions-log.md`. Write any **human-action** item as a concrete, executable step — exact screen/endpoint, exact values to read or enter, expected result — so the next interactive session needs no clarification round (the actionable-items standard in `.claude/rules/open-topics.md`).
9. **Merge** — when everything is green (tests pass, reviews clean), merge the PR with `merge-pr`.
10. **Time-gate** — check **Berlin time** (`TZ=Europe/Berlin date`). If it is **before 08:00**, start the **next** iteration (go to step 1). If it is **08:00 or later**, **stop and wait for the human** — post a concise summary of what landed, the proposed next step, and the topics still open (by now each should need a human decision or be deferred to a future phase — see Constraints).

## Distrust the instrument — QA before any verdict

The PoC's two worst wrong conclusions were not research errors but **measurement bugs producing plausible-looking numbers** (master plan, prior-baseline note): a silent sizing-hook bug left the regime gate **inert for a dozen iterations** — backtests ran clean and minted a confident *false negative* ("regime gating doesn't help"), caught only when a four-arm A/B returned bit-identical Sharpes — and a **broken trial register produced a NaN deflated Sharpe** that minted an apparent *winner* that was pure artifact. In an unattended loop a wrong verdict is worse than a crashed run: it enters the decision log and steers every subsequent iteration. So: **the harness is a first-class, unit-tested deliverable (§9), and no verdict outranks the instrument that measured it.**

- **Prove the treatment engaged before reading the result.** In any A/B, confirm the variant actually did something: arms must differ (bit-identical or near-identical metrics across arms = a dead knob until proven otherwise); an overlay/gate/feature must demonstrably change weights, trades, or exposure somewhere in the sample. Cheap engagement evidence — an exposure diff, a nonzero gate-transition count, a non-constant feature — is part of the experiment, not optional polish.
- **Plausibility-gate every metric before recording it.** NaN/inf/degenerate metrics, zero trades or zero turnover under a live signal, identical numbers where seeds/windows/arms should differ, a Sharpe far above the family's literature bound — all are **instrument suspects first, findings second**. Diagnose the measurement before writing the verdict.
- **New measurement code proves itself on known answers before its verdicts count.** A new harness path, metric, cost hook, or feature-construction step ships with tests that would catch the known failure modes: a planted signal is recovered, a null scores ≈0, an injected look-ahead is caught, registry invariants hold (DSR finite, trial counts monotonic, hash chain intact). TDD applies to the harness *especially* — it is the product of Phases 2–5.
- **A measurement bug is a first-class finding — with a retroactive audit.** On finding a bug in the harness / validation / cost path: fix it with a regression test, then **re-audit every prior verdict that flowed through the buggy path** — re-run the cheap ones, flag the rest, and correct the decision log / open topics so no known-tainted verdict stands. (The PoC's inert-gate fix overturned a 12-iteration-old conclusion; the overturn was the real deliverable.)
- **Never weaken a guardrail to keep the loop green.** A failing assert, integrity check, reconciliation tolerance, or acceptance test is a *result to investigate*, never an obstacle to delete, skip, or loosen so tonight's sweep can finish. The same goes for warnings that encode QA signals.
- **Skepticism is symmetric.** The inert gate minted a false negative; the broken register minted a false positive. Surprise in either direction — too good, or too clean a kill — gets a bug-hunt before the verdict is recorded, scaled to the decision-weight the result will carry.

## Constraints & special cases

- **Research domain only.** Do not start Phase 6 work — execution engine, paper/live trading, go-live prep (the "Live trading preparation" open-topics category) — hard-to-reverse / production-facing, out of scope for this loop.
- **Reversibility is the line, not heaviness.** Heavy compute, big sweeps, and building reversible tooling/harnesses/pipelines all run autonomously. Park only a hard-to-reverse action, an escalation trigger, or a high-stakes judgment call — and park only *that step*, per the park rule. Prefer a reversible variant that sidesteps it.
- **The holdout is untouchable.** The pre-registered holdout (final 12 months at data freeze) has a look budget of exactly **1**, spent in Phase 5 **in the human's presence** (D3(v)). No unattended run ever computes, prints, or "just sanity-checks" anything on it. The temptation to peek is a park, not a decision.
- **Trial budgets are hard limits.** Pre-registered per family (A=40, B=25, C=10); every trial gets a registry entry once the registry exists. Spending a budget's *last* trials is fine; **expanding** a budget is a park. Kill bars are honored mechanically: archiving a family that fails its bar is autonomous, but abandoning a Bucket-A family *early* is a park.
- **No spending.** Paid data unlocks (the plan's earn-it rule), new infrastructure, subscriptions — human decisions (D3). If results justify a paid unlock, that's a *finding to park as an open topic*, not a purchase to make.
- **Canonical data is immutable.** Datasets are hash-versioned; backtests reference dataset hashes, never "latest". Derive to new paths; never overwrite or delete canonical data unattended. Treat the capture pipeline (VPS daemon → workstation sync → NAS) as production: improving its *code* on a branch is reversible and fine, but anything that could interrupt the *running* capture parks (L2 gaps are unbackfillable).
- **Upstream bug discovered** (NautilusTrader, polars, a data source, …)? Write an issue draft to `.tmp/<project>-bug-<subject>.md` (a draft is reversible — actually *filing* it upstream is the irreversible step, so leave that for an interactive session). Keep going by building a workaround — don't block on it.
- **Drain the open-topics list toward human-only.** Open topics are the durable parking place across context-compaction windows (`.claude/rules/open-topics.md`): park what you can't resolve immediately (autonomously, no approval), fold relevant topics into every new brainstorm (step 2), and sweep the list at phase close-out (dedicated iteration for current-phase topics — see the phase-close-out bullet). By hand-back, everything still in Open/Partially-done should either **require a human decision** or be **deliberately deferred to a future phase** — an autonomously-resolvable current-phase topic left parked at the time-gate is a miss. Keep each touched topic's `status` in sync as sub-items land (`open→partial→resolved`) — a checked-off item under `status: open` is a drift bug — and treat "human-gated" as **per sub-item**: pursue a parked topic's public-research/data/code sub-items autonomously (the park rule's decomposition step), so the "miss" also covers an autonomously-resolvable **sub-item** of a human-gated topic left unpursued.
- **Out of feasible work packages?** Don't stop — first **drain the open-topics list**: pick the next autonomously-resolvable topic from Open/Partially-done and work it. Only when none remains, manufacture a package that doesn't burn alpha-trial budget: harden the validation harness or its acceptance tests, deepen data QA, refine or recalibrate the cost model, add robustness/stress analysis of already-registered results, improve reproducibility tooling — or take the next family/variant in the §5 queue *within its pre-registered budget*, as a clean A/B against its baseline. Log the choice per `.claude/rules/decisions-log.md`.
- **Phase close-out report ⇒ sweep open topics first, then persist the decisions log.** A research phase spans several iterations; when a work package *is* writing a phase's **close-out report** (the exit-bar report — not an interim orientation/progress note): **before** writing it, sweep `docs/open-topics/README.md` — a topic **more relevant to the current phase than to future phases** gets a **dedicated brainstorming iteration** first, while future-phase topics stay parked for their phase to pick up (per `.claude/rules/open-topics.md`); don't close the phase over unaddressed current-phase topics. Then, with the report, persist that phase's decisions: **copy** `.tmp/decisions.md` verbatim into a committed sibling beside the report at `docs/research/<serial>.phase<N>-decisions.md`, `git add` it, then **truncate** the running (gitignored) `.tmp/decisions.md` — the sibling stays **off** the mdformat allowlist. Full rule in `.claude/rules/decisions-log.md` (*Phase persistence*). Ordinary iteration close-outs only *append* to `.tmp/decisions.md`; they never git-persist it.
- **Slow tasks** (CPCV sweeps, full-history rebuilds, large fetches, long backtests): run them in the background and **check status about every hour** (a long fallback wakeup) rather than blocking — avoid endless waiting. When harness-tracked background work finishes you're re-invoked automatically. Heavy is fine; just don't block on it.
- **Honesty holds.** Verdicts are read on the validation protocol's own metrics — net of the explicit Kraken cost model (fee tier, spread, margin open + rollover), DSR at the family's true trial count, SPA vs the frozen benchmark, surviving the 1.5×/2× cost stress — never on gross returns or a cherry-picked slice. A negative/null result is a valid, valuable deliverable — record it and pick the next thread. Fabricating or cherry-picking a positive is the only unforgivable failure — and an unverified instrument is how one gets minted by accident (see *Distrust the instrument*).

## Red flags — you are about to violate autonomy

If you catch yourself doing any of these, STOP that impulse and apply the Iron Rule (decide → log per the rule → continue) — or, for an irreversible/trigger/judgment step, the park rule:

- Drafting a question / `AskUserQuestion` / "I'll ask the human" for a **reversible** decision
- "This decision belongs to the human" — for a reversible research choice (it doesn't; only irreversible/trigger/high-stakes does)
- "Rule 1 says ask when unclear"
- "I'll leave a note / draft and wait for them to wake up"
- "The brainstorming HARD-GATE / spec review / merge needs approval first"
- Stopping at the open PR instead of merging it
- Ending the turn while it is still before 08:00 Berlin with green work and a clear next step
- Treating an empty open-topics backlog as a "terminal condition" / reason to stop (manufacture a work package instead)
- Treating a failed iteration or a blocker as the end of the loop (fix it or pivot, then continue)
- **Refusing to run heavy/infrastructural work** because it "feels like infrastructure work" — if it's reversible, run it (only an irreversible/high-stakes step is parked)
- **Taking a hard-to-reverse or destructive action unattended** (overwriting a canonical dataset, touching live/paper/production or the running capture daemon, publishing externally, spending money) — park that step and run a reversible variant
- **Peeking at the holdout** ("just to sanity-check the candidate") — the look budget is 1 and it is not yours to spend
- **Running trials past a family's budget, or leaving trials unregistered,** to keep a promising thread alive — record the finding, park the expansion, move on
- **Recording a verdict from a suspicious run** — bit-identical arms, NaN/degenerate metrics, zero trades under a live signal, identical numbers where seeds/windows should differ — without hunting the instrument bug first
- **Deleting, skipping, or loosening a failing assert, integrity check, tolerance test, or acceptance test** so tonight's run can finish
- **Fixing a measurement bug and moving on** without re-auditing the prior verdicts that flowed through the buggy path
- **Reaching for Qlib** or PoC-era Qlib workflows/templates — the ratified stack is the custom validation core; stale material doesn't steer the loop

## Rationalizations — and the reality

| Rationalization | Reality |
|---|---|
| "This design choice belongs to the human." | In the loop you own every **reversible research** decision. Log it per `.claude/rules/decisions-log.md`; the human reviews and corrects later. That log IS their involvement. Only a hard-to-reverse action, an escalation trigger, or a high-stakes judgment call waits. |
| "Rule 1 says surface tradeoffs and ask." | Rule 1's *ask* is suspended for reversible decisions. You honor "surface tradeoffs" by listing+evaluating options (logging subject-matter ones), then deciding. Not deciding = the loop dies. |
| "The brainstorming HARD-GATE needs approval before I implement." | Invoking the loop is the standing approval. Your recorded decisions + spec self-review substitute for the interactive gate. Proceed. |
| "I'll draft the options and wait for them to wake up." | Waiting = the loop dies. Never defer a reversible choice to the human mid-loop; the only stop is the 08:00 time-gate. |
| "I should stop at the PR for human merge approval." | Attended mode stops at the PR; the loop does not. Merge it via `merge-pr` when green. |
| "This idea needs new tooling / a harness — that's interactive-session work, I'll skip it." | Heaviness isn't the boundary; reversibility is. Build the tooling on a branch — it's reversible. Only a hard-to-reverse step gets parked, and even then just that step, not the heavy work. |
| "Part of this would overwrite the dataset / touch production — I'll just do it." | That's the one thing you don't do unattended. Run a reversible variant (new path, local draft), park the irreversible step for an interactive session, continue. |
| "One holdout look would settle whether this survivor is real." | The look budget is 1, pre-registered, spent in Phase 5 with the human present. A peek tonight spends it silently and poisons the final test. Validate on CPCV / walk-forward as the protocol prescribes; park the question. |
| "The family's budget is spent but the next variant looks so promising." | Budget expansion is a named escalation trigger. Record the finding, park the expansion request as an open topic, take the next family in the queue. |
| "The backtest ran clean and the numbers look plausible — record the verdict." | The PoC's two worst wrong conclusions came from clean-running, plausible-looking measurements: an inert gate minted a false negative that stood for a dozen iterations; a broken register's NaN DSR minted a fake winner. Engagement + plausibility checks come first; then the verdict. |
| "This assert/acceptance test is blocking the sweep — I'll relax it tonight and restore it later." | The guardrails are the product (§9). A red integrity check is a finding to investigate, not an obstacle; relaxing it unattended is exactly how a fake winner gets minted. Park the affected work package if needed — never weaken the check. |
| "It's 08:00+ but I'll squeeze one more iteration." | Stop at the time-gate. Hand back a summary; the human resumes. |
| "The result is negative, the iteration failed — I should ask what to do." | A negative result is a real finding. Record the verdict, write/select the next step, continue. |

## Notes

- This skill **orchestrates** the existing skills — it does not replace them. Use `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, `superpowers:systematic-debugging`, and `merge-pr` as the loop's steps; this skill only adds the autonomy discipline + the reversibility/judgment boundary + the iteration cadence + the closeout/next-step/time-gate rules.
- Follow all the repo's standing conventions (`.claude/rules/`): branch off `develop`, commit-message + co-author/reviewer trailers, the spec/plan locations, the iterations-history closeout entry, the open-topics convention, and the decisions-log convention — plus the master plan's governance (§12: autonomy contract, Decision Register, escalation triggers). Unattended mode changes *who approves* (you, recorded), not *what gets produced*.
