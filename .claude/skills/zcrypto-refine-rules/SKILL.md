---
name: zcrypto-refine-rules
description: Joint refinement round for CLAUDE.md, rules, skills, and the local memory — harvest lessons, graduate them, count the universals, condense, verify losslessly. User-invoked only.
disable-model-invocation: true
model: claude-fable-5
---

# zcrypto-refine-rules

## What this is

A joint session that keeps the guidance corpus truthful, minimal, and placed where it is cheapest to load. The economics: CLAUDE.md + `.claude/rules/` are paid by every session on every turn — measure the tax with `wc -c CLAUDE.md .claude/rules/*.md`, never quote a remembered number. Skills defer only their **body**; the `name` + `description` are ambient, so a new skill is a permanent cost too. Refinement moves weight down the load gradient without losing an invariant.

## Invariants

- **Joint dispositions close items; undecided is the default.** Nothing is decided unilaterally, exactly as in grooming.
- **One open decision set at a time.** Fact-collection may run ahead in the background, but the next step's findings are HELD until the previous step's dispositions close — later steps depend on earlier outcomes, and presenting two open sets collides them mid-review.
- **Any "later" outcome registers a topic in the same step** — a deferred hook, a parked finding, a postponed graduation: `T<NNNN>` via `topic-ops`, never only the round's report.
- **Net always-loaded growth needs the user's explicit OK** — graduation adds weight, condensing removes it; report the measured delta, never assume the sign.
- **Hooks are proposed case-by-case, each shown to the user before it lands.**

## Step 1 — Harvest

Populate the memory inbox with candidate items in the standard memory-file shape (frontmatter `name`/`description`/`metadata.type`, body with **Why** and **How to apply**). **A memory that CONFERS a capability names the session it belongs to** — read by a session it does not describe, it hands over an authority nobody granted; a prohibition is safe subjectless. (An inbox record mechanizes this with its required `session` field.)

- **Watermark**: `git log -1 --grep='^Refine-Round-Closed:' --format=%cI` — the previous round's closing commit carries the `Refine-Round-Closed: <ISO-8601 UTC>` trailer. **No match ⇒ first round**: harvest the full current memory inbox plus the trailing two weeks.
- **Sources since the watermark**: every inbox `.local/agent-lessons/*.jsonl` in the main checkout — `infra/scripts/check-agent-lessons.py` on each first, a malformed line being a finding, not a skip; `git log` over `.claude/`; merged PR bodies; lessons either party names in the session. **A harvested inbox rotates** to `.local/agent-lessons/harvested/<round-date>/` in the same step, so the next round starts from empty inboxes and no record is harvested twice.
- A candidate that duplicates an existing memory item updates that item instead (the memory system's own dedup rule).

## Step 2 — Graduate (joint)

Walk every memory item — candidates and standing ones alike. Per item, exactly one disposition, the user's word closing each:

| Disposition | Action |
|---|---|
| → CLAUDE.md | The shortest imperative form lands there, and **only in the same commit as a deletion of equal or larger byte size from the always-loaded corpus — a trade, never an addition** |
| → a rule | Lands in the owning `.claude/rules/` file, and **only in the same commit as a deletion of equal or larger byte size from the always-loaded corpus — a trade, never an addition** |
| → an existing skill | Lands at the step where it applies (P4) |
| → a new skill | Only with the description-is-ambient cost acknowledged |
| → a hook proposal | Shown to the user; on approval, lands with the settings change |
| stays in memory | Personal or session-scoped — not repo-worthy; the default when undecided |
| dropped | With the user's word; the file is deleted at Step 5 |

A graduated item's file is **staged** — moved to `graduated/<round-date>/` under the memory dir — **never deleted here**. Memory is unversioned; an unverified landing must not be the only copy's obituary. Record every graduation in a table: *item → disposition → landing path*. Deletion is Step 5's last action.

## Step 3 — Count list

Run `infra/scripts/count-list.sh`. It prints one line per surviving universal in `CLAUDE.md` and `.claude/rules/` — the set that universal quantifies, the command that counts the set, and today's value.

- **A non-zero count is a finding.** Resolve it in the round: fix the practice, narrow the rule, or delete the rule.
- **A universal that appears with no command beside it is the finding.** It is given a set and a command in this round, or it goes — an uncountable universal cannot be reported on.

Read the corpus and you can find a stale path, two texts that disagree, and a name that has gone stale; you structurally cannot find a rule whose text is entirely correct, whose citations all resolve, and which is simply not obeyed by the population it governs, because nothing in a read counts that population — which is why this step counts instead of reading.

Output is a findings table, resolved jointly. A finding that cannot be resolved in the round registers a topic (see Invariants). **The values live in that table, never in the corpus lines**, which carry set and command only — a count written into a rule is stale the next day.

## Step 4 — Condense

**Load `references/principles.md` now** — the principles there govern every edit in this step. Work the biggest always-loaded offenders first (`wc -c CLAUDE.md .claude/rules/*.md | sort -n`). A prose-cleanup worklist over the whole tree excludes `.claude/*` and `docs/specs/*` + `docs/plans/*`; `docs/open-topics/*` keeps `topic-ops`'s shape.

## Step 5 — Verify

In order, all five before anything is deleted:

- **(a) Cold diff review** — a fresh subagent reads the round's full diff for weakened or lost invariants, **every changed line, not only removals**: rewording can weaken a `Never` without deleting it.
- **(b) Modal floor** — `grep -cE 'Never|never|MUST|must|only|refuse|explicit' CLAUDE.md .claude/rules/*.md` before vs after; any decrease itemized and justified line by line, never summarized.
- **(c) Graduation table check** — each staged file's content verified present at its named landing path.
- **(d) Net measurement** — `wc -c CLAUDE.md .claude/rules/*.md` before vs after; the delta goes in the closeout; growth needs the user's explicit OK.
- **(e) Commit gate** — `uv run pre-commit run -a` until clean.

Then, and only then, delete the staged memory files and update `MEMORY.md`.

## Closing

The round's closing commit carries the watermark trailer — `Refine-Round-Closed: <ISO-8601 UTC>` — placed below `Co-Authored-By:`, which opens the trailer block. Verify end-to-end before reporting done:

```bash
test "$(git log -1 --grep='^Refine-Round-Closed:' --format=%H)" = "$(git rev-parse HEAD)"
```

Closeout entry routes to phase 6 per `iteration-closeout`.
