---
name: zcrypto-auto-exec
description: Use when the user asks to run the unattended / autonomous execution loop (e.g. invokes /zcrypto-auto-exec, "run autonomously while I'm away", "work the queue overnight") — the standing procedure for autonomously executing ANY open work item from the memo's WORK-ITEMS QUEUE and the open T-topics, research and non-research alike, with zero human interaction; irreversible, attended, and high-stakes steps park. Renamed from research-loop 2026-07-21 — historical docs keep the old name.
disable-model-invocation: true
---

# zcrypto-auto-exec

## What this is

Run open work **unattended** — the same brainstorm → spec → plan → subagent-driven execution → verify → merge cycle as attended work, with **zero human interaction**: nobody will answer, and pausing kills the loop. The loop executes **any** open item within the autonomy boundary — infra, tooling, docs, and research — leaving a reviewable trail.

Two goals, by work type:

- **Queue work**: drain `docs/memo.local.md`'s `WORK-ITEMS QUEUE` and the open T-topics toward a human-only residue — by hand-back, everything still open either requires the human or is deliberately deferred with a trigger.
- **Research work**: advance `docs/research/00.master-plan.md` toward the current phase's exit bar per its §12 governance. The bar is benchmark-relative; an honest kill is success; **no verdict outranks the instrument that measured it**.

## The autonomy boundary — reversibility and judgment, not topic or heaviness

- **AUTONOMOUS: anything reversible/discardable, however heavy** — backtests, sweeps, building tooling/harnesses on a branch, code + tests + docs for any open topic, public web research, read-only host inspection.
- **INTERACTIVE (park the step, keep moving):**
  1. **Hard-to-reverse / production-facing** — anything touching live/paper trading, the running capture pipeline (L2 gaps are unbackfillable), host converges and image re-pins, alert-rule pushes and other vaulted-credential attended steps, publishing externally, spending money, overwriting canonical datasets (immutable — derive to new paths).
  2. **High-stakes judgment + the pre-registered escalation triggers** (master-plan §12): strategic pivots, architecture lock-ins, "good enough to deploy?", expanding a trial budget, **any touch of the holdout** (look budget = 1, spent with the human), the other §12 touchpoints by name.

**The queue item's `Who:` field is a hint; the boundary governs per sub-item.** An item marked `me` can still contain an attended sub-step — decompose, do the reversible parts, park exactly the attended step. Run an autonomous sub-item now iff it **feeds** the parked human decision or is **independent** of it — never if it **waits on** the decision.

## The Iron Rule

**Never stop to ask, never wait, never defer a reversible choice to the human.** On any reversible fork: 2–3 options with tradeoffs → pick the most beneficial → log it if it is a subject-matter research decision (`.claude/rules/decisions-log.md`) → continue. The loop ends exactly two ways: the **time-gate** (default 08:00 Berlin; the invocation may override), or a **genuinely unrecoverable blocker** (stop-note at the end of the active decisions log). Everything else — empty queue (manufacture work), failed iteration (record the verdict), mid-execution error (fix it), reversible ambiguity (decide it), an irreversible step inside an idea (park that step) — continues. Approval gates are pre-satisfied by the invocation: brainstorming's HARD-GATE → recorded decisions + spec self-review; the PR → **merge it yourself** via `merge-pr` when green.

## The work loop (one item)

1. **Re-read `docs/memo.local.md`.** It is hand-edited outside sessions; the read-guard hook (`.claude/hooks/memo-guard.sh`) blocks any memo write not preceded by a fresh read and demands a read-back after every write. **Memo writes go through the Edit/Write tools only — never shell heredocs** — the guard only sees those tools, and it invalidates after every single write, so a multi-edit bookkeeping pass interleaves a read before each further edit.
2. **Pick the topmost `WORK-ITEMS QUEUE` item** whose `DependsOn:` is satisfied (trigger fired, prerequisites done) and whose work is inside the boundary. Skip a blocked or attended item with a one-line note and take the next. Queue empty or fully blocked → sweep the open topics' `ripe_when:` triggers; still nothing → manufacture non-budget work (harden harnesses, data QA, robustness re-analysis) per the research constraints below.
3. **Execute the item by draining its T-topic's sub-items** (decomposition rule above). Ceremony scales per `.claude/rules/spec-plan-locations.md`: substantive → full spec/plan/SDD flow; trivial → branch + TDD + mandatory review, no committed spec. Research-type items follow the full §12 iteration flow. All repo conventions hold — every commit reviewed, PRs into `develop`, merged via `merge-pr` when green.
4. **Bookkeep through `/zcrypto-grooming`'s ad-hoc procedures** (read its SKILL.md and follow it; the human's auto-exec launch sanctions exactly these — grooming's FULL flow stays human-only):
   - **Topic resolved** → `resolved` + archived per `.claude/rules/open-topics.md` → grooming's *"T is done"* procedure moves the queue item to `DONE ITEMS` with citations. **Re-read the memo, pick the next item.**
   - **Topic partially resolved** → `partial` per `open-topics.md` → grooming's *partial* procedure: append the short cited, timestamped note — and when the shape changed, also update the item's **subject / Size / DependsOn** to describe only the remainder and **re-order the list** so it stays a dependency-true sequence.
   - **New topic surfaced mid-execution** → register it per `open-topics.md` (file + index, serials checked across `archive/` and branches) **and** insert it into the queue at its dependency- and priority-correct position via grooming's *insert* procedure. A registered-but-unqueued topic is invisible at pick time.
5. **Closeout per item**: decisions-log routing for subject-matter decisions; the deferral sweep — every "later / follow-up / once X" exits as a topic with `ripe_when:`, or an explicit drop. Prose is not registration.
6. **Time-gate** → next item, or stop with the summary: what landed, what parked and why, the queue as reshaped.

## Research work — the ratified protocol still binds

When the item is research-type (alpha families, validation, portfolio/risk): the master plan's §12 Decision Register is the **complete** list of human touchpoints; everything else runs on defaults. **Trial budgets are hard limits** (A=40 / B=25 / C=10; every trial registered; an intra-family variant keeps the family's registry key; a broken instrument suspends spending in that family). **The holdout is untouchable.** Follow the §5 ranked queue; never exceed a family's budget; verdicts — hypothesis, spec hash, dataset hash, result, adopt/reject/park — go to the decisions log **and** the append-only trial registry. Verdicts are read net of the explicit cost model, DSR at true trial count, SPA vs the frozen benchmark. A negative result is a valid deliverable; fabricating a positive is the only unforgivable failure.

## Distrust the instrument — before any verdict, research or not

The project's worst conclusions were measurement bugs producing plausible numbers, and the 2026-07-20 audits found twenty-plus defects that were all *artifacts asserting untruths*. So, for every claim the loop produces:

- **Prove the treatment engaged** before reading a result; bit-identical arms = a dead knob until proven otherwise.
- **Measure, never derive**: a count from arithmetic is not a measured count; a grep hit is not a finding until the line is read; "verified" means the command ran and its output is quoted.
- **A measurement bug is a first-class finding — with a retroactive audit** of every verdict that flowed through it. **A correction is itself a verdict** — same bug-hunt before recording it.
- **Never weaken a guardrail** so tonight's run finishes: a failing assert, tolerance, or QA warning is a finding, not an obstacle.
- **Skepticism is symmetric**: surprising wins get the same scrutiny as surprising kills.

## Constraints

- **The memo protocol is narrow by design**: the loop picks from the top, applies grooming's ad-hoc procedures, and touches nothing else — it **never drains `NEW IDEAS`** (dispositions are joint) and **never purges `DONE ITEMS`** (the purge gate is the human's deletion license).
- **Merge settled findings, not drafts**: run the first-order robustness check on the same branch; keep commits local through the iteration; push once at PR-open. Doc-only micro-fixes ride the next substantive PR.
- **Registered deferrals only** — reports, PR bodies, and docstrings are write-only at pick time.
- **No spending; upstream issues are drafted, never filed; canonical data immutable; slow tasks run in background** (harness-tracked completions re-invoke you — never a watcher shell).

## Failure modes — catch yourself

| The impulse | The reality |
|---|---|
| Ask / wait on a reversible choice | Decide → log → continue. The logs are the human's involvement. |
| "`Who: me` on the item, so its attended sub-step is fine too" | The boundary governs per sub-item. Park the attended step, do the rest. |
| Drain NEW IDEAS or purge DONE ITEMS "while I'm in the memo anyway" | Human-only gates. The loop's memo surface is exactly the ad-hoc procedures. |
| Resolve the topic, move on without the grooming bookkeeping | The item isn't done until the queue reflects it and the memo was re-read. |
| Edit the memo via a shell heredoc | Bypasses the read-guard. Edit/Write tools only. |
| Register a topic without queueing it | Invisible at the next pick. Register **and** insert. |
| Stop at an open PR for approval | The loop merges via `merge-pr` when green. |
| Squeeze one more item past the time-gate | Stop at the gate; hand back the summary. |
| Peek at the holdout / expand a budget / touch production "just this once" | Named park triggers. Park and continue. |
| Record a verdict from a suspicious run | Instrument bug-hunt first — plausible numbers from broken instruments steered this project wrong twice. |
| Loosen a failing assert so the run finishes | Guardrails are the product; a red check is a finding. |

## Notes

- Orchestrates: `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, `superpowers:systematic-debugging`, `merge-pr`, and `/zcrypto-grooming` (ad-hoc procedures only). All `.claude/rules/` conventions hold. Unattended mode changes *who approves* — not *what gets produced*.
- War stories behind these rules: `references/case-log.md` — read it when a rule's rationale matters to a live call.
- Renamed from `research-loop` 2026-07-21; `docs/research/` and older specs keep the old name as history.
