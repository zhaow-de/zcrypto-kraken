# Open topics

A **park-for-later** convention for newly discovered issues or aspects worth follow-up — recurring warnings, deferred fixes, "we should investigate X" tangents — that surface during regular work but cannot be resolved immediately without derailing the current iteration. Parking them here makes them durable **across context-compaction windows and sessions**: the list is the project's persistent working memory, not a chat note that evaporates. Each topic lives in its own markdown file under `docs/open-topics/` (resolved topics are moved to `docs/open-topics/archive/`); the directory's `README.md` is the index, organized into two top-level categories — `## Research and development` and `## Live trading preparation` — each split into `### Open`, `### Partially done`, and `### Resolved` subsections.

## When to open a topic

Open a topic when a **non-trivial** item surfaces that cannot be resolved immediately within the current iteration: a recurring runtime warning, a deferred fix, an intriguing tangent, a parked irreversible/judgment step. If it can be resolved on the spot, resolve it instead of parking it. Trivial uncertainties (one-off questions answered in the same turn, style nits, already-fixed issues) do **not** qualify.

## Opening is autonomous — no approval gate

Opening a topic requires **no user approval**, in either interactive or unattended mode: when a qualifying item surfaces, write the topic file and update the index in the same change, then carry on. Mention newly opened topics in the iteration closeout / session summary so the user sees them — transparency, not permission.

## "Human-gated" is per sub-item, not per topic — decompose and pursue what you can

A topic that touches the account or the venue is not automatically off-limits. **"Needs the human" — a login, an API key, money, or an irreversible/high-stakes action — is a property of a *sub-item*, not of the whole topic.** When a topic's `## Suggested next steps` mixes both kinds, classify each item and split the work:

- **Autonomously-resolvable sub-items** — public web research (fee schedules, API/support docs, margin & leverage specs, market-structure changes), data pulls, and code — get **done**: pursued autonomously in the research loop, or pre-answered when an interactive session first touches the topic. Public research needs no login and no approval.
- **Genuinely human-gated sub-items** — the ones that literally require the human's account, key, money, or an irreversible action — are the **only** parked residual.

Never park a whole topic as "human" when half of it is public research anyone could do. Decomposing this way is what keeps the drain invariant below honest: the researchable half should already be resolved before hand-back, leaving a clean, actionable human residual.

## Review and drain

The list only works if it is actively drained, not just appended to. Three checkpoints:

- **At the start of every new brainstorming iteration**, review the index's `### Open` and `### Partially done` subsections and **fold the relevant items into the iteration** being brainstormed; anything ripe but out of scope for it is a candidate work package of its own. Addressing a topic pops it from the list per the lifecycle below (close or partially complete + index sync).
- **Before finishing a phase** (ahead of writing its close-out report), sweep the list once more and split it by relevance: a topic **more relevant to the current phase than to future phases** gets a **dedicated brainstorming iteration** to address it before the phase closes; a topic more relevant to a **future phase** is deliberately **deferred** — leave it parked, that phase's iteration-start reviews will pick it up.
- **End-state invariant (autonomous runs):** an autonomous run works the resolvable topics down as it goes, so that by hand-back everything still in `### Open` / `### Partially done` either **requires a human decision** (irreversible, high-stakes, or a pre-registered escalation trigger) or is **deliberately deferred to a future phase**. An autonomously-resolvable *current-phase* topic — **or an autonomously-resolvable *sub-item* of an otherwise human-gated topic** (per the decomposition rule above) — still parked at the end of a run is a miss; it should have been drained or picked as a work package.

## File path & naming

`docs/open-topics/T<NNNN>-<slug>.md`:

- `<NNNN>` is a 4-digit zero-padded counter. Next serial = one above the highest existing serial across **both** `docs/open-topics/` **and `docs/open-topics/archive/`** (the `README.md` is excluded from the count) — so an archived (resolved) topic's serial is never reused. The counter is **independent** of `docs/specs/` and `docs/plans/` — open topics have their own sequence starting at `0000`.
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

## Partially completing a topic

**Keep `status` in sync with the sub-items — flip it as soon as work lands, don't batch it to a closeout sweep.** The frontmatter `status` must track the `## Suggested next steps` checklist: the moment the **first** sub-item is resolved while others remain, the topic is `partial`; when the **last** one resolves, it is `resolved`. A topic whose body shows completed / checked-off items but still reads `status: open` is a **state-drift bug** — flip it in the same change that lands the work, in interactive and autonomous work alike. This is per sub-item, not a once-at-the-end action.

A topic is partially completed by flipping its front-matter `status: open` → `status: partial` **in place**. Then:

- Insert a `## Done so far` section immediately after `## Findings so far`, linking the relevant commits, PRs, and spec that delivered the completed work.
- Trim `## Suggested next steps` to list only the still-open remainder.
- In `docs/open-topics/README.md`, move the topic's bullet from `## Open` to the end of the `## Partially done` section (transition order).

A partially completed topic later closes the normal way (see below).

## Closing a topic

A topic is closed by flipping its front-matter `status` (`open` or `partial`) → `status: resolved` **and moving the file into `docs/open-topics/archive/`** (flat — `git mv docs/open-topics/T<NNNN>-<slug>.md docs/open-topics/archive/`). `docs/open-topics/archive/` is the longitudinal record of completed investigations; the closing commit (or PR) is where the resolution lives. The index still lists the topic in its category's `### Resolved` subsection, with its link now pointing at the archived path (see Index sync).

## Index sync (every change)

In the same change as opening, partially completing, or closing a topic, edit `docs/open-topics/README.md`:

First, place the topic in the right top-level category and keep it there across its lifecycle:

- **`## Research and development`** — research, experiment, validation, modeling, and data-pipeline topics (the work of finding and proving an edge).
- **`## Live trading preparation`** — topics about going live: paper-trading, live-readiness, production execution, monitoring/alerting, and data freshness for live inference.

Within the chosen category, the topic moves between that category's `### Open` / `### Partially done` / `### Resolved` subsections:

- **Opening:** append a new bullet at the **end of the category's `### Open` subsection**. Within `### Open`, entries stay in serial / creation order (append-only).
- **Partially completing:** **move** the bullet from `### Open` to the **end of the same category's `### Partially done` subsection** (transition order).
- **Closing:** **move** the bullet from `### Open` or `### Partially done` to the **end of the same category's `### Resolved` subsection**, and **update its link to the archived path** (`archive/<file>`) since the file itself moves into `docs/open-topics/archive/` (see Closing a topic). Within `### Resolved`, entries are in resolution order (append-only at close time), which may differ from serial order.

Each bullet is a markdown link to the topic file followed by a one-sentence description, e.g. `- [T0000 — empty-slice warnings](T0000-empty-slice-warnings.md) — benign numpy diagnostic per-step aggregation; revisit when the logger gains warning filters.`

The pre-commit `mdformat` hook covers `docs/open-topics/README.md`; the TOC is generated at `--maxlevel 3` (so it lists the two categories and their `###` subsections) — let `mdformat` regenerate it, never hand-edit the `<!-- mdformat-toc … -->` block.
