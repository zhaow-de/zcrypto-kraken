---
name: research-loop
description: Use when the user asks to run the unattended / overnight / autonomous research loop (e.g. invokes /research-loop, "run research overnight while I'm away", "keep iterating autonomously"). The autonomous (unattended) research mode that runs reversible experiments — feature/signal/validation research and the heavy compute, sweeps, and tooling they need — with NO questions and NO waiting, holding hard-to-reverse actions, pre-registered escalation triggers, and high-stakes judgment for an interactive session, advancing the research master plan phase by phase toward its exit bars.
disable-model-invocation: true
---

# research-loop

## What this is

Run the project's research iterations **unattended** — the same brainstorm → spec → plan → subagent-driven execution → verdict → merge cycle as attended work, with **zero human interaction**: nobody will answer, and pausing kills the loop. This is the standing procedure; each run picks up the current backlog and leaves a reviewable trail.

**Goal:** advance `docs/research/00.master-plan.md` toward the **current phase's exit bar** (identify the phase from the decision logs, `docs/iterations-history*.md`, and repo state); each iteration is one *specify → plan → execute → verify → calibrate* pass (§12). The bar is **benchmark-relative** — the deployable system is the best of {benchmarks ∪ validated survivors} under the §9 protocol — so an honest kill or negative result is **success**. Optimize for verdicts the trial registry can defend; **no verdict outranks the instrument that measured it**.

The stack is ratified (§7): the custom polars/CPCV/DSR/bootstrap/registry core + explicit Kraken cost model now, NautilusTrader at Phase 6. **Qlib is not part of this project** — PoC-era Qlib material is stale. Stay in the research domain: Phase 6 (execution, paper/live) and the §12 Decision Register's human touchpoints belong to attended sessions.

## The autonomy boundary — reversibility and judgment, not topic or heaviness

- **AUTONOMOUS: anything reversible/discardable, however heavy** — large backtests, CPCV sweeps, long experiments, building tooling/harnesses/fetchers/pipelines on a branch, read-only public web research — plus the register's **autonomous-with-defaults** decisions (rule-driven universe finalization, the pre-registered trial budgets A=40/B=25/C=10, the holdout definition, the Phase-5 combination default, benchmark parameter grids): run them on defaults; only their named triggers escalate.
- **INTERACTIVE (park the step, keep moving):**
  1. **Hard-to-reverse / destructive** — anything touching live/paper trading or production; publishing externally (upstream issue/PR, release); overwriting/deleting canonical datasets (immutable, hash-versioned — derive to new paths); spending money; anything that could interrupt the **running capture pipeline** (L2 gaps are unbackfillable — permanent data loss).
  2. **High-stakes judgment + the pre-registered escalation triggers (§12)** — strategic pivots, architecture lock-ins, every "good enough to deploy?" call; by name: expanding a trial budget, abandoning a Bucket-A family early, any new data spend, **any touch of the holdout** (look budget = 1, spent in Phase 5 with the human), the universe rule yielding <8 / >15 names or diverging materially from the plan's table, conflicting survivors at Phase-5 combination.

The Decision Register (§12) is the **complete** list of human touchpoints; everything not on it runs autonomously on defaults. This does not conflict with the Iron Rule: the loop decides every reversible research choice itself, and parks **only** irreversible / trigger / high-stakes steps.

### Park the irreversible step, not the heavy work

1. **Do the reversible parts** — including the heavy compute — regardless of an irreversible step elsewhere in the idea.
2. **Prefer a reversible variant** that avoids the step (a new dataset path, a local issue draft, the within-budget variant).
3. **Park only the irreversible step**: log it (`.claude/rules/decisions-log.md`, recorded as parked) **and register it as an R&D open topic with a `ripe_when: <condition>` frontmatter trigger** (`.claude/rules/open-topics.md`). Registration is mandatory — the decisions log is drained at phase close and is not a pick-time source; a park recorded only in prose is a lost park.
4. **Decompose mixed topics**: pursue autonomously-researchable sub-items now if they **feed** the human decision or are **independent** of it; park a sub-item that **waits on** the decision. "Human-gated" is per sub-item, never per topic.

Parking is not a stop — park the one step and keep moving. Never take the irreversible action unattended.

## The Iron Rule

**Never stop to ask, never wait, never defer a reversible choice to the human.** On any reversible fork: list 2–3 options with tradeoffs → pick the most confident / most beneficial → log it if it is a subject-matter research decision (per `.claude/rules/decisions-log.md`; routine tooling/process choices are decided but not logged) → continue. This replaces the repo's "ask when unclear" for the loop's duration; the human course-corrects later from the log — that is the safety net.

**The loop ends exactly two ways:** the **time-gate** (default 08:00 Berlin — `TZ=Europe/Berlin date`; the invocation may override it), or a **genuinely unrecoverable blocker** (jot a free-form stop-note — not a gated decision entry — at the end of the active `.tmp/decisions-phase<N>.md`). Nothing else is a stop: an empty backlog (manufacture a package — see Constraints), a failed or negative iteration (record the verdict, continue), a mid-execution error (fix it, continue), a reversible ambiguity (decide it), an idea containing an irreversible step (park that step, continue).

**Approval gates are pre-satisfied** by the invocation: brainstorming's HARD-GATE → your recorded decisions + spec self-review; the spec user-review → self-review; the execution handoff → just start (don't ask which mode); the PR → **merge it yourself** via `merge-pr` when green.

## The loop (one iteration)

1. **Pick a work package** from: the master plan's current phase, the last iteration's *Suggested next steps*, and the **R&D open topics** (`docs/open-topics/README.md`) — **evaluating every `ripe_when:` trigger at each pick** (a fired trigger is live work now). The master plan governs; stale / PoC-era items are dropped or reframed. In the alpha phase follow the §5 ranked queue and never exceed a family's budget. Keep it small — one hypothesis + a validation approach; heavy is fine if reversible; apply the park rule to any irreversible step in its path.
2. **Brainstorm** it (`superpowers:brainstorming`) autonomously, folding in relevant open topics (addressing one updates its status + index per the rule).
3. **Spec self-review**; fix inline; proceed.
4. **Plan** (`superpowers:writing-plans`).
5. **Execute** (`superpowers:subagent-driven-development`: fresh subagent per task + per-task review + final whole-branch review).
6. **Fix issues mid-execution** and continue (`superpowers:systematic-debugging` for non-trivial failures); build missing reversible tooling; park only a hard-to-reverse fix.
7. **Closeout** — instrument checks first (below), then the **verdict** — hypothesis, spec hash, dataset hash, result, adopt/reject/park — into the decisions log **and** the append-only trial registry (never an unlogged "it seemed better"). Suggest the next step; write the iterations-history entry. Iteration closeouts only *append* to the relevant `.tmp/decisions-phase<N>.md`; git-persisting it is phase-level (see Constraints).
8. **Deferral sweep (mandatory).** Re-read the closeout prose — the report's next-steps/caveats, the history entry, new decisions entries, docstring flags, and the PR description you are about to open (its `## Follow-ups` / `## Out of scope` may only reference registered topics or explicit drops) — extracting every item phrased "follow-up", "deferred", "later", "flagged for", "once/when X", "revisit", "noted". Every deferred item exits as **(a)** an updated topic, **(b)** a new `T<NNNN>` topic with `ripe_when:`, or **(c)** an explicit one-line drop in the decisions log. **Prose is not registration.** Human-action items are written executable — exact screen/endpoint, exact values, expected result.
9. **Merge** via `merge-pr` when green (tests pass, reviews clean).
10. **Time-gate**: before the gate → next iteration; at/after → stop with a summary (what landed, the proposed next step, the open topics — each now human-gated or deliberately deferred).

## Distrust the instrument — QA before any verdict

The PoC's two worst conclusions were measurement bugs producing plausible numbers, not research errors (`references/case-log.md`); in an unattended loop a wrong verdict steers every later iteration. The harness is a first-class, tested deliverable (§9).

- **Prove the treatment engaged** before reading a result: arms must differ (bit-identical or near-identical metrics across arms = a dead knob until proven otherwise); an overlay/gate/feature must demonstrably change weights, trades, or exposure. Engagement evidence is part of the experiment.
- **Plausibility-gate every metric**: NaN/inf/degenerate values, zero trades or zero turnover under a live signal, identical numbers where seeds/windows/arms should differ, a Sharpe far above the family's literature bound — instrument suspects first, findings second.
- **New measurement code proves itself on known answers** before its verdicts count: a planted signal recovered, a null ≈ 0, an injected look-ahead caught, registry invariants intact (DSR finite, trial counts monotonic, hash chain intact). TDD applies to the harness *especially* — it is the product of Phases 2–5.
- **A measurement bug is a first-class finding — with a retroactive audit**: fix it with a regression test, then re-audit every prior verdict that flowed through the buggy path — re-run the cheap ones, flag the rest — and correct the decision log / open topics so no tainted verdict stands.
- **A correction is a verdict** — the same symmetric bug-hunt before recording it: verify the economically decisive quantities (P&L, drawdown, exposure), not only the metric that raised the doubt; pre-merge review applies; so does the retroactive audit (case-log: the iter-053 over-correction).
- **Never weaken a guardrail** — a failing assert, integrity check, tolerance, acceptance test, or QA warning is a finding to investigate, never an obstacle to delete, skip, or loosen so tonight's run finishes.
- **Skepticism is symmetric**: a surprising win gets the same bug-hunt as a surprising kill, scaled to the decision weight (the PoC minted one of each).

## Constraints

- **Research domain only** — no Phase-6 / "Live trading preparation" work; it is production-facing and attended.
- **The holdout is untouchable**: the pre-registered holdout (the final 12 months at data freeze) has a look budget of exactly **1**, spent in Phase 5 with the human present (D3(v)). Never compute, print, or "sanity-check" anything on it; the temptation is a park.
- **Trial budgets are hard limits** (A=40 / B=25 / C=10; every trial registered; spending the last trials is fine, **expanding** is a park; kill bars honored mechanically — archiving a failed family is autonomous, abandoning a Bucket-A family *early* is a park). Corollaries: **(i) a broken instrument suspends spending** — when a kill-bar leg or measurement path is shown unable to discriminate (e.g. the frozen benchmark fails it) and the fix is human-gated, register no further trials in that family; run no-trial-spend packages and park resumption on the protocol decision. **(ii) An intra-family variant keeps the family's registry key** — the cap is enforced by the monotone per-key `n_trials_in_family`; a new key silently un-caps it; record the variant in `notes`.
- **Merge settled findings, not drafts of them — and push once.** Before opening a verdict/finding PR, ask: *which first-order robustness check would most plausibly overturn this* (cost realism, window/warm-up asymmetry, offset/seed sensitivity, multiplicity)? Run it on the same branch. A follow-on iteration revising a finding merged hours earlier is a smell — extend the still-open branch instead. Keep commits local through the iteration (amend and bulk freely while unpushed); push exactly once, at PR-open. Doc-only micro-fixes ride the next substantive PR, never their own.
- **Deferrals must be registered.** Anything deferred beyond this iteration lives in `docs/open-topics/` with a `ripe_when:` trigger, or is explicitly dropped (step 8). Reports, iterations-history entries, PR descriptions, the decisions log, docstrings, and phase-close-out "carried forward" sections are **write-only at pick-time** (step 1 reads only the *last* entry's next-steps). Never resolve/archive a topic carrying a live deferred sub-item — split it into its own topic first. The phase-close-out sweep also greps the phase's reports + history entries for unregistered deferral language (defer / follow-up / later / once / when / flagged / revisit / noted), registering or explicitly dropping each hit before the close-out report is written.
- **Drain the open topics toward human-only.** Fold them into brainstorms; keep each topic's `status` in sync per sub-item (a checked-off item under `status: open` is a drift bug); pursue the researchable sub-items of human-gated topics per the decomposition rule. By hand-back, everything still open is human-gated or deliberately deferred — an autonomously-resolvable item, or a fired `ripe_when:` trigger neither picked up nor consciously re-deferred, left parked is a miss.
- **No spending** — paid data tiers, infrastructure, subscriptions are human decisions (D3). A result that justifies a paid unlock is a finding to park as a topic, not a purchase to make.
- **Canonical data is immutable** — hash-versioned; backtests reference dataset hashes, never "latest"; derive to new paths. The capture pipeline is production: improving its code on a branch is fine; anything that could interrupt the running daemon parks.
- **Upstream bug?** Draft the issue to `.tmp/<project>-bug-<subject>.md` (actually *filing* it is the irreversible step); build a workaround; don't block.
- **Out of packages?** Drain the topic list first; then manufacture non-budget work — harden the harness/acceptance tests, deepen data QA, recalibrate the cost model, robustness/stress re-analysis of already-registered results, reproducibility tooling — or take the next §5 family/variant within its budget, as a clean A/B against its baseline. Log the choice.
- **Phase close-out**: sweep the topics first (a current-phase topic gets a dedicated iteration before the phase closes; future-phase topics stay parked), then persist the decisions log — copy `.tmp/decisions.md` verbatim to `docs/research/<serial>.phase<N>-decisions.md` (kept **off** the mdformat allowlist), `git add` it, truncate the running file. Never per-iteration. **Never cross a phase boundary without the close-out report + drained decisions** (full mechanics in `.claude/rules/decisions-log.md`; case-log: the Phase 0→1 drift).
- **Slow tasks** run in the background with ~hourly status checks (harness-tracked completions re-invoke you). Heavy is fine; blocking is not.
- **Honesty holds.** Verdicts are read on the protocol's own metrics — net of the explicit Kraken cost model (fee tier, spread, margin open + rollover), DSR at the family's true trial count, SPA vs the frozen benchmark, surviving the 1.5×/2× cost stress — never on gross returns or a cherry-picked slice. A negative result is a valid deliverable; fabricating or cherry-picking a positive is the only unforgivable failure.

## Failure modes — catch yourself

| The impulse | The reality |
|---|---|
| Ask (`AskUserQuestion`) / draft options / wait for the human on a reversible choice ("Rule 1 says ask") | Decide → log → continue. The decisions log IS their involvement; waiting kills the loop. |
| "This judgment belongs to the human" (for a reversible research choice) | Only irreversible / trigger / high-stakes steps wait. Everything else you own. |
| Stop at the open PR for approval | Attended mode stops at the PR; the loop merges via `merge-pr` when green. |
| "The brainstorming HARD-GATE / spec review needs approval first" | Pre-satisfied by the invocation — recorded decisions + spec self-review; proceed. |
| End the turn before the time-gate with green work and a clear next step | Nothing but the gate or an unrecoverable blocker ends the loop. |
| "It's past the gate but I'll squeeze in one more iteration" | Stop at the gate; hand back the summary. |
| Treat an empty backlog or a failed iteration as terminal | Manufacture a package; record the negative verdict and continue. |
| Skip heavy / infrastructure work as "not loop work" | Reversibility is the line, not heaviness — build it on a branch. |
| Take the irreversible step "just this once" (dataset overwrite, production/capture touch, publishing, spending) | Park that step; run the reversible variant. |
| Peek at the holdout "just to sanity-check" | The look budget is 1, Phase 5, human present. A peek silently spends it and poisons the final test — validate on CPCV / walk-forward as the protocol prescribes. |
| Run past a family's budget, or leave trials unregistered, because the thread is promising | Expansion is a named trigger — record the finding, park it, take the next family. |
| Record a verdict from a suspicious run (bit-identical arms, NaN, zero trades, too-good Sharpe) | Instrument bug-hunt first — the PoC's fake winner and false negative both ran "clean". |
| Loosen a failing assert / tolerance / acceptance test so tonight's run finishes | Guardrails are the product; a red check is a finding. Park the package if needed. |
| Fix a measurement bug and move on | Re-audit every prior verdict that flowed through the buggy path first. |
| Overturn a prior claim because one metric contradicts it | A correction is a verdict — verify the economics (P&L / drawdown / exposure) before recording (case-log: iter-053). |
| Register trials against a leg just shown unable to discriminate ("finish the family cleanly") | Uninformative rows at a hard-capped price — suspend spending until the protocol decision. |
| "I noted the follow-up in the report / history / PR description — it's captured" | Prose is write-only at pick-time. Topic with `ripe_when:`, or an explicit drop (case-log: the iter-045 lost flag). |
| Resolve/archive a topic still carrying a live deferred sub-item | Split it into its own topic first — archives are never reviewed. |
| Open a new registry family key for an intra-family variant | It restarts `n_trials_in_family` and silently un-caps the shared budget. |
| Open a PR for a finding whose obvious robustness check hasn't run; open a doc-only micro-PR | Settle the finding on the branch first; fold micro-fixes into the next substantive PR. |
| Reach for Qlib or PoC-era templates | The ratified stack is the custom core; stale material doesn't steer the loop. |

## Notes

- This skill **orchestrates** the existing ones: `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, `superpowers:systematic-debugging`, `merge-pr`. All repo conventions hold (`.claude/rules/`: branch workflow, commit/PR trailers, spec & plan locations, iterations-history, open-topics, decisions-log) plus the master plan's §12 governance. Unattended mode changes *who approves* (you, recorded) — not *what gets produced*.
- The war stories behind these rules live in `references/case-log.md` — read it when a rule's rationale matters to a live judgment call.
