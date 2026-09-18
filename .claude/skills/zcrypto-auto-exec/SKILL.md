---
name: zcrypto-auto-exec
description: Use when the user asks to run the unattended autonomous execution loop — /zcrypto-auto-exec, "run autonomously while I'm away", "work the queue overnight". Executes open work items from the memo's WORK-ITEMS QUEUE and the open T-topics with zero human interaction; irreversible, attended, and high-stakes steps park.
disable-model-invocation: true
---

# zcrypto-auto-exec

## What this is

Run open work **unattended** — the same brainstorm → spec → plan → plan review → subagent-driven execution → verify → merge cycle as attended work, with **zero human interaction**: nobody will answer, and pausing kills the loop. The loop executes **any** open item within the autonomy boundary — infra, tooling, docs, and research — leaving a reviewable trail.

Two goals, by work type:

- **Queue work**: drain `.local/memo.md`'s `WORK-ITEMS QUEUE` and the open T-topics toward a human-only residue — by hand-back, everything still open either requires the human or is deliberately deferred with a trigger.
- **Research work**: advance `docs/research/00.master-plan.md` toward the current phase's exit bar per its §12 governance. The bar is benchmark-relative; an honest kill is success; **no verdict outranks the instrument that measured it**.

## The autonomy boundary — reversibility and judgment, not topic or heaviness

- **AUTONOMOUS: anything reversible/discardable, however heavy** — backtests, sweeps, building tooling/harnesses on a branch, code + tests + docs for any open topic, public web research, read-only host inspection.
- **INTERACTIVE (park the step, keep moving):**
  1. **Hard-to-reverse / production-facing** — anything touching live/paper trading, the running capture pipeline (L2 gaps are unbackfillable), host converges and image re-pins, alert-rule pushes and other vaulted-credential attended steps, publishing externally, spending money, overwriting canonical datasets (immutable — derive to new paths).
  2. **High-stakes judgment + the pre-registered escalation triggers** (master-plan §12): strategic pivots, architecture lock-ins, "good enough to deploy?", expanding a trial budget, **any touch of the holdout** (the look budget was 1 and is spent — 0 now, master plan §12), the other §12 touchpoints by name.

**The queue item's `Who:` field is a hint; the boundary governs per sub-item.** An item marked `me` can still contain an attended sub-step — decompose, do the reversible parts, park exactly the attended step. Run an autonomous sub-item now iff it **feeds** the parked human decision or is **independent** of it — never if it **waits on** the decision.

**The landing rule — never a PR for a component the loop cannot complete.** The open-and-merge license covers only items the loop completes; a component includes its attended tail (an alert rule not pushed is not delivered). Prep for a parked attended step lands as a committed, reviewed, **pushed branch with no PR**, registered durably — the branch named in the topic file and in the memo item's `DependsOn:`, stating it EXISTS — and the attended session finishes the component on that branch and opens the single PR. Prep may be its own PR only when it passes the PR gate as a complete component **without mentioning the attended remainder** — then it is ordinary decomposition, not fragmentation.

## The Iron Rule

**Never stop to ask, never wait, never defer a reversible choice to the human.** On any reversible fork: 2–3 options with tradeoffs → pick the most beneficial → log it if it is a subject-matter research decision (routing and entry format: `iteration-closeout`) → continue. The loop ends exactly two ways: the **time-gate** (default 08:00 Berlin; the invocation may override), or a **genuinely unrecoverable blocker** (stop-note at the end of the active decisions log). Everything else — empty queue (manufacture work), failed iteration (record the verdict), mid-execution error (fix it), reversible ambiguity (decide it), an irreversible step inside an idea (park that step) — continues. Approval gates are pre-satisfied by the invocation: brainstorming's HARD-GATE → recorded decisions + spec self-review; the PR → **merge it yourself** via `merge-pr` when green. A gate arm the loop cannot satisfy unattended — the Fable floor on a PR touching a `--fable-paths` path, with no Fable reader to dispatch — parks the component under the landing rule, a pushed branch with no PR, never a wait at the gate.

## The work loop (one item)

1. **Re-read `.local/memo.md`.** The memo contract — data model, the read-guard tooling discipline (the Edit tool once the memo exists -- the hook refuses a `Write` of it -- read-before and read-back-after every write), item formats, and the ad-hoc procedures — is **`.claude/skills/zcrypto-grooming/references/memo-protocol.md`**. Read it once per run before the first memo write; its definitions govern.
2. **Pick the topmost `WORK-ITEMS QUEUE` item** whose `DependsOn:` — its own **and its milestone's** — is satisfied (trigger fired, prerequisites done) and whose work is inside the boundary. Skip a blocked or attended item with a one-line note and take the next. Queue empty or fully blocked → sweep the open topics' `ripe_when:` triggers; still nothing → manufacture non-budget work (harden harnesses, data QA, robustness re-analysis) per the research constraints below.
3. **Execute the item by draining its T-topic's sub-items** (decomposition rule above). Ceremony scales with the design question: design-open → full spec/plan/SDD flow; **design-settled** (the deciding ruling or topic PREDATES this run — a loop may not author the decision and claim it in the same run) → branch + TDD + mandatory review, no committed spec. **An iteration's serial is minted when the branch is cut** — `docs/reference/change-index.md`'s highest `iter` plus one, and `open-pr` refuses any other. Research-type items follow the full §12 iteration flow. All repo conventions hold — PRs into `develop`, created and edited through `open-pr`. Before the push, the reads CLAUDE.md's PR bullet names run over `develop..HEAD`; the `Read before push by:` line goes into the body through `open-pr`, and `merge-pr` merges when green.
4. **Bookkeep through the protocol's ad-hoc procedures.** Topic resolved → *done*; partially resolved → *partially done* (the landing rule when the remainder is the attended tail); new topic → register per `topic-ops`, then *insert* — through `zcrypto-marco` in the multi-session setup.
5. **Closeout per item**: decisions-log routing for subject-matter decisions; the deferral sweep — every "later / follow-up / once X" exits as a topic with `ripe_when:`, or an explicit drop. Prose is not registration.
6. **Time-gate** → next item, or stop with the summary: what landed, what parked and why, the queue as reshaped.

## Research work — the ratified protocol still binds

When the item is research-type (alpha families, validation, portfolio/risk): the master plan's §12 Decision Register is the **complete** list of human touchpoints; everything else runs on defaults. **Trial budgets are hard limits** (A=40 / B=25 / C=10; every trial registered; an intra-family variant keeps the family's registry key; a broken instrument suspends spending in that family). **The holdout is untouchable.** Follow the §5 ranked queue; never exceed a family's budget; verdicts — hypothesis, spec hash, dataset hash, result, adopt/reject/park — go to the decisions log **and** the append-only trial registry. Verdicts are read net of the explicit cost model, DSR at true trial count, SPA vs the frozen benchmark. A negative result is a valid deliverable; fabricating a positive is the only unforgivable failure.

## Distrust the instrument — before any verdict, research or not

Measurement bugs produce plausible numbers — *artifacts asserting untruths*. So, for every claim the loop produces:

- **Prove the treatment engaged** before reading a result; bit-identical arms = a dead knob until proven otherwise.
- **Plausibility-gate every metric before it counts**: NaN/inf/degenerate values, zero trades or zero turnover under a live signal, identical numbers where seeds/windows/arms should differ, a Sharpe far above the family's literature bound — instrument suspects first, findings second.
- **New measurement code proves itself on known answers before its verdicts count**: a planted signal recovered, a null ≈ 0, an injected look-ahead caught, registry invariants intact. TDD applies to the harness *especially*.
- **Measure, never derive**: a count from arithmetic is not a measured count; a grep hit is not a finding until the line is read; "verified" means the command ran and its output is quoted.
- **A measurement bug is a first-class finding — with a retroactive audit** of every verdict that flowed through it. **A correction is itself a verdict** — same bug-hunt before recording it.
- **Never weaken a guardrail** so tonight's run finishes: a failing assert, tolerance, or QA warning is a finding, not an obstacle.
- **Skepticism is symmetric**: surprising wins get the same scrutiny as surprising kills.

## Constraints

- The protocol's human-gated operations stay with the user.
- **Merge settled findings, not drafts**: run the first-order robustness check on the same branch; keep commits local through the iteration; push once, at PR-open — or at the landing-rule handoff for a parked attended tail. Doc-only micro-fixes ride the next substantive PR.
- **Registered deferrals only** — reports, PR bodies, and docstrings are write-only at pick time.
- **Phase close-out**: sweep the open topics first — a current-phase topic gets a **dedicated iteration** before the phase closes; future-phase topics stay parked — and grep the phase's reports and its decisions log (`docs/research/*.phase<N>-decisions.md`) for unregistered deferral language, registering or explicitly dropping each hit. **Never cross a phase boundary without the close-out report.**
- **No spending; upstream issues are drafted, never filed; canonical data immutable; slow tasks run in background** (harness-tracked completions re-invoke you — never a watcher shell).

## Failure modes — catch yourself

| The impulse | The reality |
|---|---|
| Resolve the topic, move on without the grooming bookkeeping | The item isn't done until the queue reflects it and the memo was re-read. |
| Edit the memo via a shell heredoc | Bypasses the read-guard. The Edit tool, under the hook. |
| Squeeze one more item past the time-gate | Stop at the gate; hand back the summary. |
| Peek at the holdout / expand a budget / touch production "just this once" | Named park triggers. Park and continue. |
| "Correct" a doc by appending the retraction below the old text | The retracted claim still reads first, and more confidently. Rewrite the narrative — the durable file must read correctly cold. |

## Notes

- Orchestrates: `superpowers:brainstorming`, `superpowers:writing-plans`, `zcrypto-plan-review`, `superpowers:subagent-driven-development` (its task loop; the branch read is the trio, per `zcrypto-plan-review`'s Exit), `superpowers:systematic-debugging`, the `pre-review` / `review` / `re-review` workflows, `open-pr`, `merge-pr`, and `/zcrypto-grooming` (ad-hoc procedures only). All of `CLAUDE.md` and `.claude/rules/fleet-deploys.md` holds, and this skill carries the open-and-merge licence: the loop opens and merges its own PRs at item completion, never for a component it cannot complete. Unattended mode changes *who approves* — not *what gets produced*.
- War stories behind these rules: `references/case-log.md` — read it when a rule's rationale matters to a live call.
- Older docs and specs call this loop `research-loop`; the names are the same thing.
