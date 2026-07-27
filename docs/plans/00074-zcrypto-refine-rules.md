# /zcrypto-refine-rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/zcrypto-refine-rules` skill (spec 00074), add the cold spec+plan review step to the substantive flow, and validate the skill by its first real run on the full corpus.

**Architecture:** Three prose artifacts (skill + reference + one rule edit), then an interactive joint run whose exit gate is the P7 lossless verify. No Python surface — verification is greps, the commit gate, and cold subagent review.

**Tech Stack:** Markdown under `.claude/`; `uv run pre-commit run -a` as the gate.

## Global Constraints

- All content decisions come from spec 00074 — the plan places them, the spec defines them; on conflict the spec wins.
- Markdown per `docs-style.md`: one line per bullet, no hard wrap, operational voice, sole audience = Claude.
- Commit types: `docs(rules)` for spec/plan, `claude(skills)`/`claude(rules)` for `.claude/` changes.
- Memory files live OUTSIDE the repo — never committed; the run edits them via Write/Edit only.
- The run must NOT shrink `capture-deploys.md` — that has a named trigger (T0084's first real rollout).
- Joint steps: the user's disposition closes an item; undecided is the default; nothing is decided unilaterally.
- Keep commits local until PR-open (`commit-messages.md`); every non-exempt commit gets a subagent review + `Reviewed-by:` trailer.

---

### Task 1: `references/principles.md`

**Files:** Create: `.claude/skills/zcrypto-refine-rules/references/principles.md`

- [ ] **Step 1:** Write the file: H1 `# Refinement principles`, then P1–P8 exactly as spec 00074 D2 states them, one `## P<N> — <title>` section each, body ≤3 lines per principle. No history, no examples beyond the one-clause precedent already inside D2's wording.
- [ ] **Step 2:** Verify: `grep -c '^## P' .claude/skills/zcrypto-refine-rules/references/principles.md` → `8`.

### Task 2: `SKILL.md`

**Files:** Create: `.claude/skills/zcrypto-refine-rules/SKILL.md`

- [ ] **Step 1:** Write the skill with this exact frontmatter:

```yaml
---
name: zcrypto-refine-rules
description: Joint refinement round for CLAUDE.md, rules, skills, and the local memory — harvest lessons, graduate them, sweep staleness, condense, verify losslessly. User-invoked only.
disable-model-invocation: true
---
```

Sections, in order: `## What this is` (2–3 lines; the always-loaded-tax economics in one sentence); `## Invariants` (joint dispositions, undecided default, P7 gate before any deletion reaches a commit, hooks case-by-case with per-hook user approval); `## Step 1 — Harvest` (watermark: `git log -1 --grep="refine-rules round" --format=%cI`; sources: git log over `.claude/`, iterations-history, merged PR bodies, lessons either party names; output: candidate memory files in standard shape); `## Step 2 — Graduate (joint)` (disposition table: CLAUDE.md / rule / existing skill / new skill / hook proposal / stays / dropped; graduated ⇒ memory file deleted); `## Step 3 — Staleness sweep` (operand-check every cited path/command/flag/skill-name against the tree; practice-contradiction flags; unpointed-reference flags; read-only, may fan out); `## Step 4 — Condense` (**load `references/principles.md` here** — the named load-point; biggest always-loaded offenders first); `## Step 5 — Verify` (cold subagent diffs old→new for lost invariants; then the commit gate); `## Closing` (the round's closing commit subject MUST contain `refine-rules round` — it is the next round's watermark; memory index updated).

- [ ] **Step 2:** Verify: `grep -c 'disable-model-invocation: true' .claude/skills/zcrypto-refine-rules/SKILL.md` → `1`; `grep -c 'references/principles.md' .claude/skills/zcrypto-refine-rules/SKILL.md` → ≥1 (the P5 load-point); `grep -c 'refine-rules round' .claude/skills/zcrypto-refine-rules/SKILL.md` → ≥1 (the watermark contract).
- [ ] **Step 3:** Attempt `Skill(zcrypto-refine-rules)` from the main loop and confirm it is REFUSED (disable-model-invocation working). Expected: tool_use_error.
- [ ] **Step 4:** `uv run pre-commit run -a` until clean; commit Tasks 1+2 as `claude(skills): the zcrypto-refine-rules skill (spec 00074)`.

### Task 3: cold spec+plan review joins the substantive flow

**Files:** Modify: `.claude/rules/spec-plan-locations.md`

- [ ] **Step 1:** In the *Substantive iteration* bullet, extend the flow to `… committed plan → cold spec+plan review → subagent-driven execution …`, and append this paragraph after the bullet list:

> **Cold spec+plan review (substantive flow only).** After the plan is committed and before execution starts: dispatch a fresh-context subagent to review the spec+plan **pair** — coverage (every spec requirement has a plan task), internal consistency, and whether the planned verification pins the spec's load-bearing properties. Model floor Opus; **Fable** when the change touches the unbackfillable capture path, the live trade path, or canonical data. Fix findings before Task 1; material ones are folded into the plan, not just noted.

- [ ] **Step 2:** Verify: `grep -c 'Cold spec+plan review' .claude/rules/spec-plan-locations.md` → 1. Gate clean; commit as `claude(rules): cold spec+plan review before execution (spec 00074 D3)`.

### Task 4: the first real run (joint, full corpus)

**Interleave note:** T0084 is built and merged on its own branch BEFORE this task, so the sweep covers the rollout skill too. Rebase this branch on develop first.

- [ ] **Step 1:** Execute the skill's five steps interactively with the user, full-sweep depth (owner ruling). The D4 case study is the acceptance fixture: `repo-drift-is-not-license-to-drift` and `deferrals-register-at-write-time` must each traverse harvest → graduation and receive a joint disposition.
- [ ] **Step 2:** Staleness sweep may fan out read-only checkers (one per artifact: verify every cited operand exists); writes stay in the main loop.
- [ ] **Step 3:** P7 exit gate: cold subagent verifies every removal in the round's diff is relocation / obsolescence / enforcement-replacement. Fix or restore anything it cannot classify.
- [ ] **Step 4:** Gate clean; commit the run's edits as one or few `claude(...)` commits; any skill corrections learned from the run land in `SKILL.md` in the same commits (the T0081 pattern).

### Task 5: closeout

- [ ] **Step 1:** Append the iterations-history entry (phase 6, per `iteration-closeout`) covering: the skill, the cold-review process addition, the run's material outcomes, and the case-study verdict.
- [ ] **Step 2:** Final commit subject contains `refine-rules round` (the watermark). Gate clean. Report branch ready; PR on the user's word (aggregated trailers per `open-pr`).
