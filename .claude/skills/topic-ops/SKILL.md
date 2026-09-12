---
name: topic-ops
description: Use when creating a T<NNNN> topic, flipping its status to partial or resolved, or archiving it — the serials, the file shape, the rendered index and the archive move.
disable-model-invocation: false
---

# topic-ops

The file mechanics for `docs/open-topics/` — the HOW, loaded at the moment of the operation. Whether a follow-up becomes a topic at all, and the six shapes its `ripe_when:` may take, are CLAUDE.md's topics line. A topic that is created here but not inserted into `.local/memo.md`'s queue is invisible at pick time — registration and queue insertion travel together.

## File path & naming

`docs/open-topics/T<NNNN>-<slug>.md`:

- `<NNNN>` is a 4-digit zero-padded counter. Next serial = one above the highest existing serial across **both** `docs/open-topics/` **and `docs/open-topics/archive/`** (the `README.md` is excluded from the count) — so an archived (resolved) topic's serial is never reused. The counter is **independent** of `docs/specs/` and `docs/plans/` — open topics have their own sequence starting at `0000`.
- **A serial claimed by unmerged work on another branch is taken.** Check the branches, not just the two directories (`git log --all --full-history --diff-filter=A --name-only -- 'docs/open-topics/T*.md'` — `--full-history` is load-bearing when this query is run standalone: default simplification prunes add-commits of topics later moved to `archive/`, whose serials the two-directory scan above already covers; the flag keeps the query complete on its own), and skip it — a gap is free, a collision at merge is not.
- `<slug>` is the kebab-case topic title.

## Required file shape

```yaml
---
status: open   # one of: open | partial | resolved
---
```

`ripe_when:` (when present) is the bare condition plus the one check that evaluates it — a clause a reviewer runs and reads true/false at a glance. Its history, reasoning, and what the check read live under `## Findings so far`; when the trigger changes, rewrite the key in place and put the why in the body.

…followed by, in order:

- `# <Title>` — H1 matching the slug; no square bracket in it, since the rendered index links the title.
- `## Context — what` — one paragraph stating what the topic is.
- `## Why this matters` — the consequence or motivation; why it's worth tracking.
- `## Findings so far` — what is already known (link relevant commits, PRs, files, log lines). `_(none)_` is acceptable when the topic is opened cold.
- `## Suggested next steps` — bullet list of concrete actions a future investigator could take. **Human-action items must be executable, not vague:** give the exact screen / endpoint / menu path, the exact values to read or enter, and the expected result, so the human (or a future interactive session) can run the item top-to-bottom **without a clarification round** — e.g. "On Kraken Pro → Fee tab, read the maker/taker tier and 30-day USD volume and record both," never a bare "confirm the fee tier."

A `partial` topic carries a `## Done so far` section between `## Findings so far` and `## Suggested next steps`, recording what landed (link commits/PRs/spec). Its `## Suggested next steps` then lists only the still-open remainder.

**Edit mechanics — every section replacement**: anchor on a string verified UNIQUE in the file (`grep -c` it first) — **and name the section that ENCLOSES it**: uniqueness pins WHERE text lands, never WHAT it lands inside — and compare the heading set (`grep '^#'`) before and after the edit — an anchor whose first occurrence sits inside body prose deletes whole sections silently. A splice — a section moved, merged or removed — is an edit and takes the same anchor count and heading-set check; after any rebase touching the index, re-render it — `uv run python infra/scripts/topics-index.py` — and let the frontmatter test compare.

## Partially completing a topic

**Keep `status` in sync with the sub-items — flip it as soon as work lands, don't batch it to a closeout sweep.** The frontmatter `status` must track the `## Suggested next steps` checklist: the moment the **first** sub-item is resolved while others remain, the topic is `partial`; when the **last** one resolves, it is `resolved`. A topic whose body shows completed / checked-off items but still reads `status: open` is a **state-drift bug** — flip it in the same change that lands the work, in interactive and autonomous work alike. This is per sub-item, not a once-at-the-end action.

A topic is partially completed by flipping its front-matter `status: open` → `status: partial` **in place**. Then:

- Insert a `## Done so far` section immediately after `## Findings so far`, linking the relevant commits, PRs, and spec that delivered the completed work.
- Trim `## Suggested next steps` to list only the still-open remainder.
- Re-render `docs/open-topics/README.md` (Index sync below).

A partially completed topic later closes the normal way (see below).

## Closing a topic

**"Resolve" means the underlying issue is SOLVED. It is never a status change.** Flipping `status: resolved` and moving the file to `archive/` is the bookkeeping that *records* a resolution — never the act of resolving one. Read every instruction to "resolve T\<NNNN\>" as *fix the thing, then archive it*. When the fix is out of scope, unwanted, or blocked, say so and leave the topic open: **never archive to shorten the list.** Archiving an unsolved topic destroys it — archived files are never reviewed again.

A topic may be closed only when **all three** hold:

- **Its issue is genuinely disposed of** — *fixed*, *shown to be a non-issue* (a measured refutation is a valid resolution), or *consciously dropped with the reason recorded in the file*;
- **the file itself records HOW** — a `## Resolution` section naming the commits / PR / spec / measurement that disposed of it. A `partial` topic's `## Done so far` is RENAMED to `## Resolution`, never left under its old heading, and NO `## Suggested next steps` section survives into the archive: a line under either heading reads as pending whatever label it carries, and an archived file is never reviewed again. (The deleted `.claude/rules/open-topics.md` gave that reason and this skill never inherited it; the owner spotted the gap on 2026-09-11.) **and**
- **it carries no live deferred sub-item** — a remaining "do X when Y" is first split into its own topic (with its `ripe_when:`), because a deferral left inside an archived file is lost.

If only some sub-items are done the topic is `partial`, not resolved (see *Partially completing a topic*). If none are, it stays `open`.

Write the evidence at close, while it is known: an archived topic whose work is done but **unrecorded** is indistinguishable on inspection from one whose work was never done.

A topic is closed by flipping its front-matter `status` (`open` or `partial`) → `status: resolved`, **deleting its `ripe_when:` key**, **and moving the file into `docs/open-topics/archive/`** (flat — `git mv docs/open-topics/T<NNNN>-<slug>.md docs/open-topics/archive/`).

When a close owes both a splice and a heading rename — a live sub-item to lift into its own topic and a `## Done so far` to rename — **the splice runs FIRST**: a mention of the section's name inside body prose is the unique anchor's first hit, so renaming first renames the mention and leaves the file with two headings (alex, doing it on T0190).

Delete `ripe_when:` rather than leaving it discharged: `grep -l '^ripe_when:' docs/open-topics/archive/` must stay empty, so that a hit is *by construction* a stranded live deferral rather than something to read through and adjudicate. A closed topic has no trigger — if it still has one, it is not closed. `docs/open-topics/archive/` is the longitudinal record of completed investigations; the closing commit (or PR) is where the resolution lives. The index still lists the topic in the render's `## Resolved` list, with its link now pointing at the archived path (see Index sync).

## Index sync (every change)

`docs/open-topics/README.md` is rendered from the topic files, never edited by hand: after opening, partially completing or closing a topic, run `uv run python infra/scripts/topics-index.py` and commit the result with the topic. The render is three lists by status — `## Open`, `## Partially done`, `## Resolved` — one bullet per topic in serial order, the bullet being the serial and the file's H1 title with, for a live topic, its `ripe_when`; `tests/test_open_topics_frontmatter.py` refuses an index that differs from the render, and `mdformat` leaves the file alone for the same reason.
