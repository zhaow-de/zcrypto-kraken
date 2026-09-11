# The memo protocol — `.local/memo.md`

**One writer:** the memo exists only in the main checkout and is `zcrypto-marco`'s alone (`docs/reference/multi-agent-protocol.md`) — a payload session sends it the exact text and where it goes; the writer reads before, edits with the Edit/Write tools, reads back after, and records the `sha256 · lines · bytes` chain in the coordination table.

The single source of truth for the memo's data model, tooling discipline and mechanical procedures. Loaded by `/zcrypto-grooming` (the owner — its interactive flow is `../SKILL.md`) and by `/zcrypto-auto-exec` (full path: `.claude/skills/zcrypto-grooming/references/memo-protocol.md`). The human gates below attach to the operations themselves, not to whichever skill loaded this file.

## The file

`.local/memo.md` is the user's personal working memo — gitignored, hand-edited between sessions, not version-controlled: nothing deleted from it is recoverable. Canonical sections:

| Section | Role |
|---|---|
| `NEW IDEAS` | idea inbox, ~one paragraph per idea (points↔paragraphs are usually 1:1 but can be m:n) |
| `WORK-ITEMS QUEUE` | the intermediate backlog; each `###` heading is a user-curated **milestone** |
| `DONE ITEMS` | staging for finished items awaiting verified purge |
| `ABANDONED ITEMS` | ideas decided against, each with its decision date |

- Each `##` section carries a one-sentence description directly under its heading — standing text for both readers, preserved through edits.
- Non-section scaffolding — the file title, horizontal rules, anything outside the four sections — is preserved untouched.
- If the live headings differ from the canonical four, surface the mismatch and agree the mapping (or a one-time restructure) with the user before editing anything.
- `last-grooming-section-at:` (frontmatter) is stamped at the close of a FULL grooming run; an ad-hoc operation leaves it, so the next full reconciliation re-scans a window covering them — idempotent by construction. Absent, or not a parseable timestamp → agree a baseline with the user and set the key.

## Tooling discipline — every touch

- **Re-read the file first.** A copy already in context is stale by definition.
- **The Edit and Write tools, under the hook.** `.claude/hooks/memo-guard.sh` (wired in `.claude/settings.json`) refuses a write without a fresh read, instructs the read-back after, and invalidates after each write, so a multi-edit pass re-reads before each further edit. A shell write bypasses the hook and is never used (no count command: the memo is unversioned, and a touch leaves no record in the tree).
- **Anchored edits.** A wholesale `Write` silently drops whatever the rewrite forgot, and there is no history to recover it from.
- **Deletion is licensed only at the purge gate** (human-gated, below); outside it, condense or relocate prose (no count command: the memo is unversioned, and a touch leaves no record in the tree).
- **Privacy.** The memo is the user's private journal: never paste its content into a subagent prompt, never run a subagent on this file in any role, and memo text never lands verbatim in a git-tracked file — a new or revised topic paraphrases (no count command: a prompt leaves no record in the tree). `WP<N>` labels stay out of git-tracked files: `tests/test_internal_terms_not_operator_visible.py` enforces it, its `_WP_CARRIERS` naming the exceptions.
- **Git-tracked files this machinery produces** (new or revised topics, the `docs/open-topics/README.md` index) land through the repo's normal conventions — gate, review, branch, PR — not as a side effect of memo work.

## Item shape and sequencing

- **Queue item** (short lists — no grouping): a bold `T<NNNN> — subject` line, then **sub-bullets** — `Who: … — Size: S/M/L`, `Why: …`, `DependsOn: …` (prerequisites — items, T-topics, or a named trigger/date; "—" when free). Sub-bullets, not inline fields: the memo is read by human and AI alike, and scanning beats parsing.
- **Long lists** (rule of thumb: ~8+ active items, or natural clusters): group into work packages — a level-4 header `#### WP<N>: <name>` with the same sub-bullet fields at package level, then its items, one T-topic each.
- **The list IS the schedule**: ordered as the suggested execution sequence, the next work item on top, and nothing above something it depends on.
- **A `DependsOn:` that names an artifact states whether the artifact EXISTS.** "Read X first" and "build X first" compress to the same reference and fail differently. The work to produce a missing prerequisite is itself a queue item, sequenced above its consumer.
- **Milestones sequence like items.** A `###` milestone may carry one `DependsOn:` line directly under its heading (another milestone, or a named trigger/date); milestones appear in dependency-true order, and an item is eligible for pickup when its own **and** its milestone's `DependsOn:` are satisfied.
- An added item takes the index's title wording as its subject and **condenses** the topic's own text into `Why` — the clauses that matter for this milestone, not a paste; detail stays in the topic file, reachable through the `T<NNNN>` reference.

## How references resolve

| Reference | Resolves to |
|---|---|
| `T0028` | `docs/open-topics/T0028-*.md` — or `docs/open-topics/archive/T0028-*.md` once resolved; the `docs/open-topics/README.md` index links whichever is current |
| `spec 00060` / bare `00060` | `docs/specs/00060-*-design.md` (its plan: `docs/plans/00060-*.md`) |
| `iter-082` | the row whose `iter` cell carries `iter-082` in `docs/reference/change-index.md`; its `PR` cell names the pull request that delivered the iteration, and `gh pr view <N>` prints that PR's description |
| `PR #143` | `gh pr view 143` |

## Ad-hoc procedures — mechanical, single-item, nothing else

Appliable by whoever follows this protocol: the joint grooming conversation, or a human-launched `/zcrypto-auto-exec` run — the launch is the human trigger. They are never a route into the human-gated operations below.

- **done** (`T9999 is done`) → find the `WORK-ITEMS QUEUE` item(s) referencing that topic; mark done citing the evidence (iter-N / T-topic / commits / PRs — whichever apply) with a timestamp; **move** the whole item to `DONE ITEMS`.
- **partially done** (`T9999 is partially done`) → append one short cited, timestamped note in place; when the partial resolution changed the item's *shape* — scope shrank, effort resized, prerequisites moved — also update its **subject**, **Size**, and **DependsOn** to describe the remainder, then **re-order the milestone list** so it stays a dependency-true suggested sequence.
- **insert** (`T9999 registered — insert into queue`) → for a newly registered topic: add a queue item in the standard shape at its **dependency- and priority-correct position** in the milestone list.
- **work-shaped argument** (`iter-290 (PR #1332) has been merged`) → resolve the delivered work to its topic(s) first — the iteration's row in `docs/reference/change-index.md` and the pull request that row names — then apply *done* / *partially done* to each matching item, citing the iter/PR as evidence. Ambiguous resolution (several topics, different completion states) → ask, not guess.

**All forms**: touch nothing else — no discovery, no purge, no `NEW IDEAS`, no frontmatter timestamp. No matching item → say so and stop.

## Human-gated operations — live user confirmation, whoever loaded this file

- **`NEW IDEAS` dispositions** — a point leaves the inbox through the joint conversation (grooming Step 1) and no other way; undecided is the default and stays.
- **The `DONE ITEMS` purge** — numbered display, citation re-verification, ONE batch confirmation; that confirmation is precisely the deletion license. An item the discussion reveals not-done moves back to the queue.
- **Milestone re-grooming** — the goal question, the completeness sweep, sizes and sequence — settled jointly (grooming Step 3).
