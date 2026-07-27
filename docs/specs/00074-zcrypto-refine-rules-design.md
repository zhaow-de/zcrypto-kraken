# /zcrypto-refine-rules — the rules/skills refinement round (spec 00074)

**Goal.** A user-invoked skill that keeps the guidance corpus (CLAUDE.md, `.claude/rules/`, `.claude/skills/`, the local memory) truthful, minimal, and placed where it is cheapest to load — plus one process addition: a cold spec+plan review before execution on substantive iterations.

**Scope.** The skill, its `references/principles.md`, and the `spec-plan-locations.md` cold-review addition. The skill's first real run is this branch's validation and lands here too. **Not in scope:** T0084 (own branch/PR), any `capture-deploys.md` shrink (gated on T0084's first real rollout), memo-protocol changes — and any pre-decided graduation of specific memory items (D4: dispositions belong to the run's joint review, never to this spec).

## The economics that drive every decision

CLAUDE.md + rules are **always-loaded: 33.6 KB ≈ 8.5 k tokens paid by every session on every turn**. Skills cost nothing until invoked; `references/` cost nothing until a step loads them; hooks cost zero context. Refinement means moving weight down that gradient without losing an invariant on the way.

## D1 — The skill: five steps, joint throughout

`.claude/skills/zcrypto-refine-rules/SKILL.md`, frontmatter `disable-model-invocation: true` — the round is a joint session; the user's dispositions close items, never mine. Undecided is the default state, exactly as in grooming.

1. **Harvest** — populate the memory inbox: sweep evidence since the last round (git log over `.claude/`, iterations-history entries, merged PR bodies, lessons either party names) into candidate memory items in the standard memory-file shape. The watermark is git-derived, never a hand-edited stamp: `git log -1 --grep="refine-rules round" --format=%cI` — each round's closing commit subject carries the phrase, so the next round finds its own start. First round: the full current memory inbox plus the trailing two weeks.
2. **Graduate (joint)** — per memory item, one disposition: → CLAUDE.md / → a rule / → an existing skill / → a new skill / → a hook proposal / stays in memory (personal, not repo-worthy) / dropped. A graduated item's memory file is **deleted** — its home is now the repo (P8).
3. **Staleness sweep** — mechanical, read-only, may fan out: every path, command, flag, and skill name an artifact cites is checked against the tree; rules contradicted by current practice are flagged; `references/` files with no load-point are flagged (P6). Output is a findings table, resolved jointly.
4. **Condense** — apply the principles (P1–P8, loaded from `references/principles.md` at this step), biggest always-loaded offenders first.
5. **Verify** — the P7 lossless check: a cold subagent diffs old→new corpus and confirms every removal is a relocation, an obsolescence (operand gone), or an enforcement-replacement; then the commit gate.

Hooks: the round may propose them **case-by-case, each shown to the user before it lands** (owner ruling, this round). Precedent: memo-guard.

## D2 — The principles (`references/principles.md`)

- **P1 Single home, deliberate echoes.** One home per instruction; others point. Sole allowed duplication: a safety invariant ambient + at point-of-use, the point-of-use copy in one-line form.
- **P2 Audience = a fresh Claude context.** Keep-test per line: *would a fresh session act differently without it?*
- **P3 History goes to git; the why stays only where its absence invites "correction".** No dates, derivations, or narration; the one-clause why survives on rules that would otherwise look wrong.
- **P4 Load cost drives placement.** Ambient iff needed before knowing the task (safety invariants, routing). Operation-scoped content lives in the operation's skill — the WHEN/HOW split (`open-topics.md` / `topic-ops` is the pattern).
- **P5 References are operands.** Every `references/` file is named at the step that loads it; unpointed references are dead weight.
- **P6 Prefer enforcement over prose.** A mechanically checkable rule becomes a test or hook; the prose shrinks to a pointer. A rule violated while written down is a mechanization candidate, not a wording problem.
- **P7 Lossless compression, verified.** Nothing deleted silently; a cold reviewer confirms relocation/obsolescence/enforcement for every removal before commit.
- **P8 Memory is the inbox, not an archive.** Lessons land in memory first; rounds graduate, keep, or drop them jointly; graduation deletes the memory file.

## D3 — Cold spec+plan review (the `spec-plan-locations.md` addition)

After the plan is committed and **before execution begins**: dispatch a fresh-context subagent to review the spec+plan **pair** — coverage (every spec requirement has a plan task), internal consistency, and whether the planned tests pin the spec's load-bearing properties. Model floor **Opus**; **Fable** when the change touches the unbackfillable capture path, the live trade path, or canonical data. Findings are fixed before Task 1 starts. First application: this spec+plan.

## D4 — The case study: two seeded lessons, dispositions decided in the run

Two memory items are the first run's acceptance fixture, **not** pre-decided rule edits: `repo-drift-is-not-license-to-drift` (a spec shipped planless, justified by sibling drift) and `deferrals-register-at-write-time` (deferrals whose only home was the PR body — a memory item that itself did not exist until this spec's review caught its absence, which is the harvest step's own justification).

The skill passes the case study iff the run carries both items through harvest → graduation and each receives a **joint** disposition there. What that disposition is — a rule line, an `open-pr` enforcement step, a hook, or stays-in-memory — is decided in the run; anything this spec fixed in advance would bypass the very flow it is building. Both lessons share one shape worth noticing at graduation time: each was already written down as a rule when I violated it, which makes both P6 candidates (enforcement over prose).

## D5 — Validation

The skill's first real run **is** the validation (the T0081 pattern: a written procedure is proven by its first live execution, and the run's corrections land in the skill). The run executes on this branch after T0084 merges, so the sweep covers the full current corpus. The P7 cold review is the run's own exit gate; `uv run pre-commit run -a` is the commit gate; the round's closeout entry routes to phase 6.
