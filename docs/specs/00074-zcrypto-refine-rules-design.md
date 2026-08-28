# /zcrypto-refine-rules — the rules/skills refinement round (spec 00074)

**Goal.** A user-invoked skill that keeps the guidance corpus (CLAUDE.md, `.claude/rules/`, `.claude/skills/`, the local memory) truthful, minimal, and placed where it is cheapest to load — plus one process addition: a cold spec+plan review before execution on substantive iterations.

**Scope.** The skill, its `references/principles.md`, and the `spec-plan-locations.md` cold-review addition. The skill's first real run is this branch's validation and lands here too. **Not in scope:** T0084 (own branch/PR), any `fleet-deploys.md` shrink (gated on T0084's first real rollout), memo-protocol changes — and any pre-decided graduation of specific memory items (D4: dispositions belong to the run's joint review, never to this spec).

## The economics that drive every decision

CLAUDE.md + rules are **always-loaded: 33.6 KB ≈ 8.5 k tokens paid by every session on every turn** (measured at design time; each round re-measures). Skills are **not free**: a skill's `name` + `description` are ambient in every session — only the **body** is deferred — so a new skill's description is a real, permanent cost, and "split it into more skills" is never a free move. `references/` cost nothing until a step loads them. Hooks are zero-context at baseline, but a blocking hook injects its message whenever it fires. Refinement moves weight down that gradient without losing an invariant — and **each round measures the net**: always-loaded bytes before and after, with net growth requiring the user's explicit OK.

## D1 — The skill: five steps, joint throughout

`.claude/skills/zcrypto-refine-rules/SKILL.md`. Frontmatter: `disable-model-invocation: true`; `model: claude-fable-5` — the `zcrypto-grooming` precedent: a joint round mutating durable, partly-unversioned state pins the strongest model rather than inheriting whatever the session runs. `allowed-tools` is deliberately unrestricted, decided rather than omitted: the round needs git, the file tools, and read-only fan-out; the safety surface is the joint gates and the protected set below, not the toolset.

**Invariants** (the skill's own section, in this order):

- Joint dispositions close items; **undecided is the default**, exactly as in grooming.
- **Protected set**: CLAUDE.md's `## Secrets` section, `fleet-deploys.md`, `commit-messages.md`'s different-agent-reviewer rule, and `open-topics.md`'s registration rule. Every edit to these requires the user's **explicit per-edit sign-off** during the round — P7 classification alone is not sufficient. The round must not be able to quietly weaken the rules that police it.
- **Any "later" outcome registers a topic in the same step** — a deferred hook, a parked sweep finding, a graduation postponed: `T<NNNN>` via `topic-ops`, never only the round's report. The round must not reproduce its own case study's defect.
- **Net always-loaded growth needs the user's explicit OK** — graduation adds weight, condensing removes it; the round reports the measured delta, never assumes the sign.
- Hooks: proposed **case-by-case, each shown to the user before it lands** (owner ruling, this round). Precedent: memo-guard.

The five steps:

1. **Harvest** — populate the memory inbox: sweep evidence since the last round into candidate memory items in the standard shape. Sources: git log over `.claude/`, iterations-history entries, merged PR bodies, lessons either party names. **The watermark is a git trailer, not prose**: each round's closing commit carries `Refine-Round-Closed: <ISO-8601 UTC>`, read back as `git log -1 --grep='^Refine-Round-Closed:' --format=%cI` — prose cannot produce the token, so an intermediate commit mentioning the round cannot silently advance the watermark and truncate the next harvest. **No match ⇒ first round**: the full current memory inbox plus the trailing two weeks.
2. **Graduate (joint)** — per memory item, one disposition: → CLAUDE.md / → a rule / → an existing skill / → a new skill / → a hook proposal / stays in memory / dropped. A graduated item's file is **staged** — moved to `graduated/<round-date>/` under the memory dir — **never deleted here**: memory is unversioned, and an unverified landing must not be the only copy's obituary. Deletion is step 5's last action.
3. **Staleness sweep** — mechanical, read-only, may fan out: every path, command, flag, and skill name an artifact cites is checked against the tree; rules contradicted by current practice are flagged; `references/` files with no load-point are flagged (P5). Output is a findings table, resolved jointly.
4. **Condense** — apply the principles (P1–P8, **loaded from `references/principles.md` at this step** — the P5 load-point), biggest always-loaded offenders first.
5. **Verify** — the P7 gate, scoped to **every changed line, not only removals**: (a) a cold subagent reviews the round's full diff for weakened or lost invariants; (b) the mechanical modal floor — before/after counts of `Never|never|MUST|must|only|refuse|explicit` across CLAUDE.md + `.claude/rules/` — any decrease itemized and justified line by line, never summarized; (c) the graduation table (item → disposition → landing path) checked against each staged file's content; (d) the net always-loaded measurement (`wc -c CLAUDE.md .claude/rules/*.md`, before vs after); (e) the commit gate; then, and only then, staged memory files are deleted.

## D2 — The principles (`references/principles.md`)

- **P1 Single home, deliberate echoes.** One home per instruction; others point. Sole allowed duplication: a safety invariant ambient + at point-of-use, the point-of-use copy in one-line form.
- **P2 Audience = a fresh Claude context.** Keep-test per line: *would a fresh session act differently without it?*
- **P3 History goes to git; the why stays only where its absence invites "correction".** No dates, derivations, or narration; the one-clause why survives on rules that would otherwise look wrong.
- **P4 Load cost drives placement.** Ambient iff needed before knowing the task (safety invariants, routing). Operation-scoped content lives in the operation's skill — the WHEN/HOW split (`open-topics.md` / `topic-ops` is the pattern). A skill's description is ambient; only its body is deferred.
- **P5 References are operands.** Every `references/` file is named at the step that loads it; unpointed references are dead weight.
- **P6 Prefer enforcement over prose.** A mechanically checkable rule becomes a test or hook; the prose shrinks to a pointer. A rule violated while written down is a mechanization candidate, not a wording problem.
- **P7 Lossless compression, verified — on every changed line.** Rewriting can weaken an invariant without deleting anything, so the gate covers edits, not just removals: cold diff review plus the modal-language floor; nothing weakened or dropped without an itemized reason.
- **P8 Memory is the inbox, not an archive.** Lessons land in memory first; rounds graduate, keep, or drop them jointly; graduation stages the file and step 5 deletes it after verification.

## D3 — Cold spec+plan review (the `spec-plan-locations.md` addition)

After the plan is committed and **before execution begins**: dispatch a fresh-context subagent to review the spec+plan **pair** — coverage (every spec requirement has a plan task), internal consistency, and whether the planned verification pins the spec's load-bearing properties. Model floor **Opus**; **Fable** when the change touches the unbackfillable capture path, the live trade path, or canonical data. Findings are fixed before Task 1 starts; material ones are folded into the plan, not just noted. First application: this spec+plan — whose review returned FIX FIRST and reshaped D1's watermark, graduation, and verify steps.

## D4 — The case study: two seeded lessons, dispositions decided in the run

Two memory items are the first run's acceptance fixture, **not** pre-decided rule edits: `repo-drift-is-not-license-to-drift` (a spec shipped planless, justified by sibling drift) and `deferrals-register-at-write-time` (deferrals whose only home was the PR body — a memory item that itself did not exist until this spec's review caught its absence, which is the harvest step's own justification).

The skill passes the case study iff the run carries both items through harvest → graduation and each receives a **joint** disposition there. What that disposition is — a rule line, an enforcement step, a hook, or stays-in-memory — is decided in the run; anything this spec fixed in advance would bypass the very flow it is building. One observation travels with them, deciding nothing: each was already written down as a rule when it was violated.

## D5 — Validation

The skill's first real run **is** the validation (the T0081 pattern: a written procedure is proven by its first live execution, and the run's corrections land in the skill). The run executes on this branch after T0084 merges so the sweep covers the rollout skill too — **with a fallback**: if T0084 has not merged when the round runs, sweep the current corpus and register the new skill's re-sweep as a `T<NNNN>`; the round never waits indefinitely on another component. Exit: the D1 step-5 gate, the commit gate, and the end-to-end watermark check — `git log -1 --grep='^Refine-Round-Closed:' --format=%H` must equal `git rev-parse HEAD` at close. Closeout entry routes to phase 6.
