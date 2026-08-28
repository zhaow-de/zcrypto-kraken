# /zcrypto-refine-rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/zcrypto-refine-rules` skill (spec 00074), add the cold spec+plan review step to the substantive flow, and validate the skill by its first real run on the full corpus.

**Architecture:** Three prose artifacts (skill + reference + one rule edit), then an interactive joint run whose exit gate is the spec's D1 step-5 verify. No Python surface — verification is greps, the commit gate, and cold subagent review.

**Tech Stack:** Markdown under `.claude/`; `uv run pre-commit run -a` as the gate.

## Global Constraints

- All content decisions come from spec 00074 — the plan places them, the spec defines them; on conflict the spec wins.
- Markdown per `docs-style.md`: one line per bullet, no hard wrap, operational voice, sole audience = Claude.
- Commit types: `docs(rules)` for spec/plan, `claude(skills)`/`claude(rules)` for `.claude/` changes.
- Memory files live OUTSIDE the repo — never committed; the run touches them via Write/Edit only, and graduation STAGES (moves), never deletes — deletion is step 5's last action.
- The run must NOT shrink `fleet-deploys.md` unprompted — its shrink had a named trigger (T0084's first real rollout). **Lifted mid-round by the owner's explicit word**: the canary/skill split and the Reboots relocation to `fleet.md` were both owner-directed, each with per-edit sign-off as the protected set requires.
- Joint steps: the user's disposition closes an item; undecided is the default; nothing is decided unilaterally.
- Keep commits local until PR-open (`commit-messages.md`); every non-exempt commit gets a subagent review + `Reviewed-by:` trailer.

---

### Task 1: `references/principles.md`

**Files:** Create: `.claude/skills/zcrypto-refine-rules/references/principles.md`

- [ ] **Step 1:** Write the file: H1 `# Refinement principles`, then P1–P8 exactly as spec 00074 D2 states them, one `## P<N> — <title>` section each, body ≤3 lines per principle. No history, no examples beyond what D2's own wording carries.
- [ ] **Step 2:** Verify each principle is present and distinct: `for n in 1 2 3 4 5 6 7 8; do grep -q "^## P$n " .claude/skills/zcrypto-refine-rules/references/principles.md || echo "MISSING P$n"; done` → no output.

### Task 2: `SKILL.md`

**Files:** Create: `.claude/skills/zcrypto-refine-rules/SKILL.md`

- [ ] **Step 1:** Write the skill with this exact frontmatter:

```yaml
---
name: zcrypto-refine-rules
description: Joint refinement round for CLAUDE.md, rules, skills, and the local memory — harvest lessons, graduate them, sweep staleness, condense, verify losslessly. User-invoked only.
disable-model-invocation: true
model: claude-fable-5
---
```

Sections, in order, content per spec D1: `## What this is` (2–3 lines; the economics in one sentence — the always-loaded tax measured by command, **never a hardcoded number**: `wc -c CLAUDE.md .claude/rules/*.md`); `## Invariants` (spec D1's five: joint/undecided-default, the protected set verbatim, later-outcomes-register-a-topic, net-growth-needs-OK, hooks case-by-case); `## Step 1 — Harvest` (trailer watermark: closing commit carries `Refine-Round-Closed: <ISO-8601 UTC>`, read `git log -1 --grep='^Refine-Round-Closed:' --format=%cI`; **no match ⇒ first round: full inbox + trailing two weeks**; the four sources); `## Step 2 — Graduate (joint)` (disposition table; graduated ⇒ **staged to `graduated/<round-date>/` under the memory dir**, deleted only in Step 5); `## Step 3 — Staleness sweep` (operand-check every cited path/command/flag/skill-name; practice-contradiction flags; unpointed-reference flags (P5); read-only, may fan out); `## Step 4 — Condense` (**load `references/principles.md` here**; biggest always-loaded offenders first); `## Step 5 — Verify` (spec D1's five sub-gates (a)–(e) in order: cold diff review over every changed line, the modal floor `grep -cE 'Never|never|MUST|must|only|refuse|explicit'` before/after with decreases itemized, the graduation table check, the net `wc -c` measurement, the commit gate — then staged files deleted); `## Closing` (the closing commit carries the `Refine-Round-Closed:` trailer; end-to-end check `test "$(git log -1 --grep='^Refine-Round-Closed:' --format=%H)" = "$(git rev-parse HEAD)"`; memory index updated).

- [ ] **Step 2:** Verify the load-bearing properties are pinned in the text:

```bash
f=.claude/skills/zcrypto-refine-rules/SKILL.md
grep -c 'disable-model-invocation: true' $f        # 1
grep -c 'model: claude-fable-5' $f                 # 1
grep -c 'references/principles.md' $f              # >=1  (P5 load-point)
grep -c 'Refine-Round-Closed:' $f                  # >=2  (watermark write + read)
grep -ci 'undecided is the default' $f             # >=1
grep -ci 'staged' $f                               # >=1  (graduation stages, never deletes)
grep -ci 'protected set' $f                        # >=1
grep -ci 'shown to the user' $f                    # >=1  (hooks per-hook approval)
```

- [ ] **Step 3:** Probe `Skill(zcrypto-refine-rules)` from the main loop. PASS only if the error names the skill as disabled/user-invoked-only. An *unknown skill* error is **inconclusive** (the session registry predates the file) — record it as such and re-verify at the run (if the user's `/zcrypto-refine-rules` resolves while the model call is refused, the flag is proven; if the command does not resolve either, the run executes the SKILL.md content directly and the probe re-runs next session).
- [ ] **Step 4:** `uv run pre-commit run -a` until clean; commit Tasks 1+2 as `claude(skills): the zcrypto-refine-rules skill (spec 00074)`.

### Task 3: cold spec+plan review joins the substantive flow

**Files:** Modify: `.claude/rules/spec-plan-locations.md`

- [ ] **Step 1:** In the *Substantive iteration* bullet, extend the flow to `… committed plan → cold spec+plan review → subagent-driven execution …`, and append — as a plain bold-led paragraph, no blockquote markup — after the bullet list:

**Cold spec+plan review (substantive flow only).** After the plan is committed and before execution starts: dispatch a fresh-context subagent to review the spec+plan **pair** — coverage (every spec requirement has a plan task), internal consistency, and whether the planned verification pins the spec's load-bearing properties. Model floor Opus; **Fable** when the change touches the unbackfillable capture path, the live trade path, or canonical data. Fix findings before Task 1; material ones are folded into the plan, not just noted.

- [ ] **Step 2:** Verify: `grep -c 'Cold spec+plan review' .claude/rules/spec-plan-locations.md` → 1. Gate clean; commit as `claude(rules): cold spec+plan review before execution (spec 00074 D3)`.

### Task 4: the first real run (joint, full corpus)

**Sequencing:** T0084 is built and merged on its own branch first, so the sweep covers the rollout skill too; rebase this branch on develop before the run. **Fallback (spec D5):** if T0084 has not merged when the round runs, sweep the current corpus and register the new skill's re-sweep as a `T<NNNN>` — the round never waits indefinitely on another component.

- [ ] **Step 1:** Execute the skill's five steps interactively with the user, full-sweep depth (owner ruling). The D4 case study is the acceptance fixture: `repo-drift-is-not-license-to-drift` and `deferrals-register-at-write-time` must each traverse harvest → graduation and receive a joint disposition.
- [ ] **Step 2:** Staleness sweep may fan out read-only checkers (one per artifact: verify every cited operand exists); writes stay in the main loop.
- [ ] **Step 3:** Run the spec D1 step-5 gate in full — sub-gates (a) through (e), in order, with the protected-set sign-offs collected as they arise. Fix or restore anything the cold reviewer cannot classify; only then delete staged memory files.
- [ ] **Step 4:** Gate clean; commit the run's edits as one or few `claude(...)` commits; skill corrections learned from the run land in `SKILL.md` in the same commits (the T0081 pattern).

### Task 5: closeout

- [ ] **Step 1:** Append the iterations-history entry (phase 6, per `iteration-closeout`) covering: the skill, the cold-review process addition, the run's material outcomes (including the measured always-loaded delta), and the case-study verdict.
- [ ] **Step 2:** The closing commit carries the `Refine-Round-Closed: <ISO-8601 UTC>` trailer (above the `Co-Authored-By:` line, which stays last per `commit-messages.md`). Verify end-to-end: `test "$(git log -1 --grep='^Refine-Round-Closed:' --format=%H)" = "$(git rev-parse HEAD)"` → exit 0. Gate clean. Report branch ready; PR on the user's word (aggregated trailers per `open-pr`).
