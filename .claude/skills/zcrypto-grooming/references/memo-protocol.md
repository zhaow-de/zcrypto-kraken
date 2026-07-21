# The memo protocol — `docs/memo.local.md`

The single source of truth for the memo's data model, tooling discipline, and mechanical procedures. Loaded by `/zcrypto-grooming` (the owner — its interactive flow is `../SKILL.md`) and by `/zcrypto-auto-exec` (full path: `.claude/skills/zcrypto-grooming/references/memo-protocol.md`). **The human gates below attach to the operations themselves, not to whichever skill loaded this file** — any future memo machinery inherits them.

## The file

`docs/memo.local.md` is the user's personal working memo — **gitignored, hand-edited between sessions, and not version-controlled**: nothing deleted from it is recoverable. Canonical sections:

| Section | Role |
|---|---|
| `NEW IDEAS` | idea inbox, ~one paragraph per idea (loosely — points↔paragraphs are usually 1:1 but can be m:n) |
| `WORK-ITEMS QUEUE` | the intermediate backlog; each `###` heading is a user-curated **milestone** |
| `DONE ITEMS` | staging for finished items awaiting verified purge |
| `ABANDONED ITEMS` | ideas decided against, each with its decision date |

- Each `##` section carries a one-sentence description directly under its heading — standing text for both readers; preserve it through every edit.
- Non-section scaffolding — the file title, horizontal rules, anything outside the four sections — is preserved untouched.
- If the live headings differ from the canonical four, surface the mismatch and agree the mapping (or a one-time restructure) with the user before editing anything.
- `last-grooming-section-at:` (frontmatter) is stamped only at the close of a FULL grooming run; ad-hoc operations never touch it, so the next full reconciliation re-scans a window covering them — idempotent by construction. Absent **or not a parseable timestamp** → agree a baseline with the user and set the key.

## Tooling discipline — every touch

- **Re-read the file first.** Any copy already in context is stale by definition.
- **Edit/Write tools only — never shell heredocs.** The read-guard hook (`.claude/hooks/memo-guard.sh`, wired in `.claude/settings.json`) enforces fresh-read-before-write and read-back-after-write on exactly these tools; it invalidates after every single write, so a multi-edit pass interleaves a read before each further edit.
- **Anchored edits only — never rewrite the file wholesale.** A wholesale `Write` silently drops whatever the rewrite forgot, and there is no history to recover it from.
- **Deletion is licensed only at the purge gate** (human-gated, below). Outside it, condense or relocate prose, never destroy it.
- **Privacy.** The memo is the user's private journal: never paste its content into a subagent prompt, never run a subagent on this file in any role. Memo text never lands verbatim in git-tracked files — a new or revised T-topic **paraphrases**. Keep `WP<N>` labels out of git-tracked files — the user's instruction, codified only here; one historical exception exists (spec `00058`'s title carries "WP7") — don't add more, and don't "fix" the repo against that precedent.
- **Git-tracked files this machinery produces** (new/revised topics, the `docs/open-topics/README.md` index) land through the repo's normal conventions — gate, review, branch/PR — never committed as a side effect of memo work.

## Item shape and sequencing

- **Queue item** (short lists — no grouping): a bold `T<NNNN> — subject` line, then **sub-bullets** — `Who: … — Size: S/M/L`, `Why: …`, `DependsOn: …` (prerequisites — items, T-topics, or a named trigger/date; "—" when free). Sub-bullets, not inline fields: the memo is read by human and AI alike, and scanning beats parsing.
- **Long lists** (rule of thumb: ~8+ active items, or natural clusters): group into work packages — a level-4 header `#### WP<N>: <name>` with the same sub-bullet fields at package level, then its items, one T-topic each.
- **The list IS the schedule**: ordered as the suggested execution sequence, the next work item always on top, and nothing above something it depends on.
- **A `DependsOn:` that names an artifact states whether the artifact EXISTS.** "Read X first" and "build X first" compress to the same reference and fail differently — a scheduled item once depended on reading a map nobody had built (T0071/T0014, 2026-07-21). The work to produce a missing prerequisite is itself a queue item, sequenced above its consumer.
- **Milestones sequence like items.** A `###` milestone may carry one `DependsOn:` line directly under its heading (another milestone, or a named trigger/date); milestones appear in dependency-true order, and an item is eligible for pickup only when its own **and** its milestone's `DependsOn:` are satisfied.
- An added item **condenses** its `docs/open-topics/README.md` entry, never pastes it: the subject keeps the index's title wording; `Why` compresses to the clauses that matter for this milestone; detail stays in the topic file, reachable through the `T<NNNN>` reference.

## How references resolve

| Reference | Resolves to |
|---|---|
| `T0028` | `docs/open-topics/T0028-*.md` — or `docs/open-topics/archive/T0028-*.md` once resolved; the `docs/open-topics/README.md` index links whichever is current |
| `spec 00060` / bare `00060` | `docs/specs/00060-*-design.md` (its plan: `docs/plans/00060-*.md`) |
| `iter-082` | the `## <date> — iter-082: <title>` section of `docs/iterations-history-phase<N>.md` — **N is the iteration's subject-matter phase, not the milestone's**: an item worked for the Phase-6a milestone may be logged in `iterations-history-phase1.md` (entries route by subject per `.claude/rules/iterations-history.md`), so locate with `grep -l "iter-082" docs/iterations-history-phase*.md`, never by assuming the milestone's phase |
| `PR #143` | `gh pr view 143` |

## Ad-hoc procedures — mechanical, single-item, nothing else

Appliable by whoever follows this protocol: the joint grooming conversation, or a human-launched `/zcrypto-auto-exec` run — the launch is the human trigger. They are **never** a route into the human-gated operations below.

- **done** (`T0199 is done`) → find the `WORK-ITEMS QUEUE` item(s) referencing that topic; mark done citing the evidence (iter-N / T-topic / commits / PRs — whichever apply) with a timestamp; **move** the whole item to `DONE ITEMS`.
- **partially done** (`T0199 is partially done`) → append one short cited, timestamped note in place; when the partial resolution changed the item's *shape* — scope shrank, effort resized, prerequisites moved — also update its **subject**, **Size**, and **DependsOn** to describe only the remainder, then **re-order the milestone list** so it stays a dependency-true suggested sequence.
- **insert** (`T0199 registered — insert into queue`) → for a newly registered topic: add a queue item in the standard shape at its **dependency- and priority-correct position** in the milestone list.
- **work-shaped argument** (`iter-290 (PR #1332) has been merged`) → resolve the delivered work to its topic(s) first — the iteration's `docs/iterations-history-phase<N>.md` entry and/or the PR — then apply *done* / *partially done* to each matching item, citing the iter/PR as evidence. Ambiguous resolution (several topics, different completion states) → ask, never guess.

**All forms**: touch nothing else — no discovery, no purge, no `NEW IDEAS`, no frontmatter timestamp. No matching item → say so and stop.

## Human-gated operations — live user confirmation, whoever loaded this file

- **`NEW IDEAS` dispositions** — a point leaves the inbox only through the joint conversation (grooming Step 1); undecided is the default and stays.
- **The `DONE ITEMS` purge** — numbered display, citation re-verification, ONE batch confirmation; that confirmation is precisely the deletion license. An item the discussion reveals not-done moves back to the queue.
- **Milestone re-grooming** — the goal question, the completeness sweep, sizes and sequence — settled jointly (grooming Step 3).
