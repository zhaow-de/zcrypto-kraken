---
name: zcrypto-refine-rules
description: Joint refinement round for CLAUDE.md, rules, skills, and the local memory — harvest lessons, graduate them, sweep staleness, condense, verify losslessly. User-invoked only.
disable-model-invocation: true
model: claude-fable-5
---

# zcrypto-refine-rules

## What this is

A joint session that keeps the guidance corpus truthful, minimal, and placed where it is cheapest to load. The economics: CLAUDE.md + `.claude/rules/` are paid by every session on every turn — measure the tax with `wc -c CLAUDE.md .claude/rules/*.md`, never quote a remembered number. Skills defer only their **body**; the `name` + `description` are ambient, so a new skill is a permanent cost too. Refinement moves weight down the load gradient without losing an invariant.

## Invariants

- **Joint dispositions close items; undecided is the default.** Nothing is decided unilaterally, exactly as in grooming.
- **Protected set** — CLAUDE.md's `## Secrets`, `capture-deploys.md`, `commit-messages.md`'s different-agent-reviewer rule, `open-topics.md`'s registration rule: every edit to these needs the user's **explicit per-edit sign-off** during the round; Step 5 classification alone is not sufficient. The round must not be able to quietly weaken the rules that police it.
- **Any "later" outcome registers a topic in the same step** — a deferred hook, a parked finding, a postponed graduation: `T<NNNN>` via `topic-ops`, never only the round's report.
- **Net always-loaded growth needs the user's explicit OK** — graduation adds weight, condensing removes it; report the measured delta, never assume the sign.
- **Hooks are proposed case-by-case, each shown to the user before it lands.** Precedent: memo-guard.

## Step 1 — Harvest

Populate the memory inbox with candidate items in the standard memory-file shape (frontmatter `name`/`description`/`metadata.type`, body with **Why** and **How to apply**).

- **Watermark**: `git log -1 --grep='^Refine-Round-Closed:' --format=%cI` — the previous round's closing commit carries the `Refine-Round-Closed: <ISO-8601 UTC>` trailer. **No match ⇒ first round**: harvest the full current memory inbox plus the trailing two weeks.
- **Sources since the watermark**: `git log` over `.claude/`; new iterations-history entries; merged PR bodies; lessons either party names in the session.
- A candidate that duplicates an existing memory item updates that item instead (the memory system's own dedup rule).

## Step 2 — Graduate (joint)

Walk every memory item — candidates and standing ones alike. Per item, exactly one disposition, the user's word closing each:

| Disposition | Action |
|---|---|
| → CLAUDE.md | The shortest imperative form lands there; note the net-growth invariant |
| → a rule | Lands in the owning `.claude/rules/` file, docs-style |
| → an existing skill | Lands at the step where it applies (P4) |
| → a new skill | Only with the description-is-ambient cost acknowledged |
| → a hook proposal | Shown to the user; on approval, lands with the settings change |
| stays in memory | Personal or session-scoped — not repo-worthy; the default when undecided |
| dropped | With the user's word; the file is deleted at Step 5 |

A graduated item's file is **staged** — moved to `graduated/<round-date>/` under the memory dir — **never deleted here**. Memory is unversioned; an unverified landing must not be the only copy's obituary. Record every graduation in a table: *item → disposition → landing path*. Deletion is Step 5's last action.

## Step 3 — Staleness sweep

Mechanical and read-only — may fan out (one checker per artifact; writes stay in the main loop):

- **Operand check**: every path, command, flag, config key, and skill name cited by CLAUDE.md, each rule, and each skill exists in the tree and means what the citation implies.
- **Practice check**: rules contradicted by how recent iterations actually worked are flagged — a contradiction is a finding to resolve jointly, in either direction.
- **Reference check** (P5): every `references/` file is named at a loading step; unpointed ones are flagged.

Output is a findings table, resolved jointly. A finding that cannot be resolved in the round registers a topic (see Invariants).

## Step 4 — Condense

**Load `references/principles.md` now** — P1 through P8 govern every edit in this step. Work the biggest always-loaded offenders first (`wc -c CLAUDE.md .claude/rules/*.md | sort -n`). The protected set's per-edit sign-off applies throughout.

## Step 5 — Verify

In order, all five before anything is deleted:

- **(a) Cold diff review** — a fresh subagent reads the round's full diff for weakened or lost invariants, **every changed line, not only removals**: rewording can weaken a `Never` without deleting it.
- **(b) Modal floor** — `grep -cE 'Never|never|MUST|must|only|refuse|explicit' CLAUDE.md .claude/rules/*.md` before vs after; any decrease itemized and justified line by line, never summarized.
- **(c) Graduation table check** — each staged file's content verified present at its named landing path.
- **(d) Net measurement** — `wc -c CLAUDE.md .claude/rules/*.md` before vs after; the delta goes in the closeout; growth needs the user's explicit OK.
- **(e) Commit gate** — `uv run pre-commit run -a` until clean.

Then, and only then, delete the staged memory files and update `MEMORY.md`.

## Closing

The round's closing commit carries the watermark trailer — `Refine-Round-Closed: <ISO-8601 UTC>` — placed above the `Co-Authored-By:` line (which stays last). Verify end-to-end before reporting done:

```bash
test "$(git log -1 --grep='^Refine-Round-Closed:' --format=%H)" = "$(git rev-parse HEAD)"
```

Closeout entry routes to phase 6 per `iteration-closeout`.
