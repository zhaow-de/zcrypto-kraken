---
name: topic-ops
description: Use for EVERY T<NNNN> open-topic file operation — creating a topic, flipping status to partial or resolved, archiving, or editing docs/open-topics/README.md — load BEFORE writing the file or touching the index.
disable-model-invocation: false
---

# topic-ops

The file mechanics for `docs/open-topics/` — when-and-whether rules live ambiently in `.claude/rules/open-topics.md`; this skill is the HOW, loaded at the moment of the operation.

## File path & naming

`docs/open-topics/T<NNNN>-<slug>.md`:

- `<NNNN>` is a 4-digit zero-padded counter. Next serial = one above the highest existing serial across **both** `docs/open-topics/` **and `docs/open-topics/archive/`** (the `README.md` is excluded from the count) — so an archived (resolved) topic's serial is never reused. The counter is **independent** of `docs/specs/` and `docs/plans/` — open topics have their own sequence starting at `0000`.
- **A serial claimed by unmerged work on another branch is taken.** Check the branches, not just the two directories (`git log --all --diff-filter=A --name-only -- 'docs/open-topics/T*.md'`), and skip it — a gap is free, a collision at merge is not.
- `<slug>` is the kebab-case topic title.

## Required file shape

```yaml
---
status: open   # one of: open | partial | resolved
---
```

…followed by, in order:

- `# <Title>` — H1 matching the slug.
- `## Context — what` — one paragraph stating what the topic is.
- `## Why this matters` — the consequence or motivation; why it's worth tracking.
- `## Findings so far` — what is already known (link relevant commits, PRs, files, log lines). `_(none)_` is acceptable when the topic is opened cold.
- `## Suggested next steps` — bullet list of concrete actions a future investigator could take. **Human-action items must be executable, not vague:** give the exact screen / endpoint / menu path, the exact values to read or enter, and the expected result, so the human (or a future interactive session) can run the item top-to-bottom **without a clarification round** — e.g. "On Kraken Pro → Fee tab, read the maker/taker tier and 30-day USD volume and record both," never a bare "confirm the fee tier."

A `partial` topic carries a `## Done so far` section between `## Findings so far` and `## Suggested next steps`, recording what landed (link commits/PRs/spec). Its `## Suggested next steps` then lists only the still-open remainder.

**Edit mechanics — every section replacement**: anchor on a string verified UNIQUE in the file (`grep -c` it first), and compare the heading set (`grep '^#'`) before and after the edit — an anchor whose first occurrence sits inside body prose deletes whole sections silently (T0139's close ate three sections and needed a rebuild from the pre-close body).

## Partially completing a topic

**Keep `status` in sync with the sub-items — flip it as soon as work lands, don't batch it to a closeout sweep.** The frontmatter `status` must track the `## Suggested next steps` checklist: the moment the **first** sub-item is resolved while others remain, the topic is `partial`; when the **last** one resolves, it is `resolved`. A topic whose body shows completed / checked-off items but still reads `status: open` is a **state-drift bug** — flip it in the same change that lands the work, in interactive and autonomous work alike. This is per sub-item, not a once-at-the-end action.

A topic is partially completed by flipping its front-matter `status: open` → `status: partial` **in place**. Then:

- Insert a `## Done so far` section immediately after `## Findings so far`, linking the relevant commits, PRs, and spec that delivered the completed work.
- Trim `## Suggested next steps` to list only the still-open remainder.
- In `docs/open-topics/README.md`, move the topic's bullet from `## Open` to the end of the `## Partially done` section (transition order).

A partially completed topic later closes the normal way (see below).

## Closing a topic

**"Resolve" means the underlying issue is SOLVED. It is never a status change.** Flipping `status: resolved` and moving the file to `archive/` is the bookkeeping that *records* a resolution — never the act of resolving one. Read every instruction to "resolve T\<NNNN\>" as *fix the thing, then archive it*. When the fix is out of scope, unwanted, or blocked, say so and leave the topic open: **never archive to shorten the list.** Archiving an unsolved topic destroys it — archived files are never reviewed again.

A topic may be closed only when **all three** hold:

- **Its issue is genuinely disposed of** — *fixed*, *shown to be a non-issue* (a measured refutation is a valid resolution), or *consciously dropped with the reason recorded in the file*;
- **the file itself records HOW** — a `## Resolution` section (or the `## Done so far` a `partial` topic already carries) naming the commits / PR / spec / measurement that disposed of it, and trimming or explicitly labelling any `## Suggested next steps` that no longer apply; **and**
- **it carries no live deferred sub-item** — a remaining "do X when Y" is first split into its own topic (with its `ripe_when:`), because a deferral left inside an archived file is lost.

If only some sub-items are done the topic is `partial`, not resolved (see *Partially completing a topic*). If none are, it stays `open`.

Write the evidence at close, while it is known: an archived topic whose work is done but **unrecorded** is indistinguishable on inspection from one whose work was never done.

A topic is closed by flipping its front-matter `status` (`open` or `partial`) → `status: resolved`, **deleting its `ripe_when:` key**, **and moving the file into `docs/open-topics/archive/`** (flat — `git mv docs/open-topics/T<NNNN>-<slug>.md docs/open-topics/archive/`).

Delete `ripe_when:` rather than leaving it discharged: `grep -l '^ripe_when:' docs/open-topics/archive/` must stay empty, so that a hit is *by construction* a stranded live deferral rather than something to read through and adjudicate. A closed topic has no trigger — if it still has one, it is not closed. `docs/open-topics/archive/` is the longitudinal record of completed investigations; the closing commit (or PR) is where the resolution lives. The index still lists the topic in its category's `### Resolved` subsection, with its link now pointing at the archived path (see Index sync).

## Index sync (every change)

In the same change as opening, partially completing, or closing a topic, edit `docs/open-topics/README.md`:

First, place the topic in the right top-level category and keep it there across its lifecycle:

- **`## Research and development`** — research, experiment, validation, modeling, and data-pipeline topics (the work of finding and proving an edge).
- **`## Live trading preparation`** — topics about going live: paper-trading, live-readiness, production execution, monitoring/alerting, and data freshness for live inference.

Within the chosen category, the topic moves between that category's `### Open` / `### Partially done` / `### Resolved` subsections:

- **Opening:** append a new bullet at the **end of the category's `### Open` subsection**. Within `### Open`, entries stay in serial / creation order (append-only).
- **Partially completing:** **move** the bullet from `### Open` to the **end of the same category's `### Partially done` subsection** (transition order).
- **Closing:** **move** the bullet from `### Open` or `### Partially done` to the **end of the same category's `### Resolved` subsection**, and **update its link to the archived path** (`archive/<file>`) since the file itself moves into `docs/open-topics/archive/` (see Closing a topic). Within `### Resolved`, entries are in resolution order (append-only at close time), which may differ from serial order.

Each bullet is a markdown link to the topic file followed by a one-sentence description, e.g. `- [T9999 — an example topic](T9999-an-example-topic.md) — one-sentence description of what it is and when it becomes ripe.`

The pre-commit `mdformat` hook covers `docs/open-topics/README.md`; the TOC is generated at `--maxlevel 3` (so it lists the two categories and their `###` subsections) — let `mdformat` regenerate it, never hand-edit the `<!-- mdformat-toc … -->` block.
