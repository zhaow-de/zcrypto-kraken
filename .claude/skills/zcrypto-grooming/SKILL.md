---
name: zcrypto-grooming
description: Drain and groom docs/memo.local.md together with the user — triage NEW IDEAS into agreed dispositions, reconcile WORK-ITEMS QUEUE against what actually merged, verify-and-purge DONE ITEMS, and size the milestone backlogs. Invoked manually — bare /zcrypto-grooming for the full three-step flow, or with an argument ("T0199 is done", "T0199 is partially done") for a single-item queue update. Never self-invoke.
disable-model-invocation: true
model: claude-fable-5
allowed-tools: Read, Edit, Write, Grep, Glob, AskUserQuestion, Bash(git log:*), Bash(git show:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(gh pr list:*), Bash(gh pr view:*), Bash(date:*), Bash(uv run pre-commit:*)
---

# zcrypto-grooming

## What this is

`docs/memo.local.md` is the user's personal working memo — **gitignored, hand-edited between sessions, and not version-controlled**: nothing deleted from it is recoverable. Its canonical sections:

| Section | Role |
|---|---|
| `NEW IDEAS` | idea inbox, ~one paragraph per idea (loosely — points↔paragraphs are usually 1:1 but can be m:n) |
| `WORK-ITEMS QUEUE` | the intermediate backlog; each `###` heading is a user-curated **milestone** |
| `DONE ITEMS` | staging for finished items awaiting verified purge |
| `ABANDONED ITEMS` | ideas decided against, each with its decision date |

Each `##` section carries a one-sentence description directly under its heading — standing text for both readers; preserve it through every edit.

Grooming is a **joint conversation**: this skill structures it, the user decides. Nothing in the memo is disposed of unilaterally — the memo is the user's memory, and an item silently mis-filed is worse than one left untouched.

## Invariants — every invocation, both modes

- **Re-read the file first.** It is gitignored and changes outside Claude sessions; any copy already in context is stale by definition.
- **The memo is not version-controlled, so deletion is licensed only at the purge gate.** There is no git history to recover from. The one sanctioned destruction is Step 2's purge of `DONE ITEMS` after the user's batch confirmation — that confirmation is precisely the license. Outside that gate, condense or relocate prose, never destroy it.
- **Anchored edits only — never rewrite the file wholesale, and only through the Edit/Write tools, never shell heredocs.** A wholesale `Write` silently drops whatever the rewrite forgot, and there is no history to recover it from; a shell write bypasses the read-guard hook (`.claude/hooks/memo-guard.sh`), which enforces fresh-read-before-write and read-back-after on exactly these tools. The memo is the user's private journal: never paste its content into a subagent prompt, never run a subagent on this file in any role.
- **Memo text never lands verbatim in git-tracked files.** A new or revised T-topic paraphrases the idea. Keep `WP<N>` labels out of git-tracked files — the user's instruction, codified only here; one historical exception exists (spec `00058`'s title carries "WP7") — don't add more, and don't "fix" this skill against that precedent.
- **The user's explicit agreement closes each item; undecided is the default state, not a failure.** A point nobody has ruled on simply stays in `NEW IDEAS` — under time pressure, for lack of consensus, or for any reason at all. Deciding solo is never the shortcut.
- **Git-tracked files grooming produces** (new/revised topics, the `docs/open-topics/README.md` index) land through the repo's normal conventions — gate, review, branch/PR — never committed as a side effect of the conversation.
- If the live headings differ from the canonical four above, surface the mismatch and agree the mapping (or a one-time restructure) with the user before editing anything. Non-section scaffolding — the file title, horizontal rules, anything outside the four sections — is preserved untouched.

## How references resolve

| Reference | Resolves to |
|---|---|
| `T0028` | `docs/open-topics/T0028-*.md` — or `docs/open-topics/archive/T0028-*.md` once resolved; the `docs/open-topics/README.md` index links whichever is current |
| `spec 00060` / bare `00060` | `docs/specs/00060-*-design.md` (its plan: `docs/plans/00060-*.md`) |
| `iter-082` | the `## <date> — iter-082: <title>` section of `docs/iterations-history-phase<N>.md` — **N is the iteration's subject-matter phase, not the milestone's**: an item worked for the Phase-6a milestone may be logged in `iterations-history-phase1.md` (entries route by subject per `.claude/rules/iterations-history.md`), so locate with `grep -l "iter-082" docs/iterations-history-phase*.md`, never by assuming the milestone's phase |
| `PR #143` | `gh pr view 143` |

## With an argument — single-item update, nothing else

These ad-hoc procedures are also the bookkeeping interface of a human-launched `/zcrypto-auto-exec` run — that launch is the human trigger, so applying them from inside the loop is sanctioned. The FULL flow (the three steps below: NEW IDEAS dispositions, the purge gate, milestone re-grooming) remains exclusively a live conversation with the user; an auto-exec run never drains `NEW IDEAS` and never purges `DONE ITEMS`.

`/zcrypto-grooming T0199 is done`
→ Find the `WORK-ITEMS QUEUE` item(s) referencing that topic. Mark done citing the evidence (iter-N / T-topic / commits / PRs — whichever apply) with a timestamp, then **move** the whole item to `DONE ITEMS`.

`/zcrypto-grooming T0199 is partially done`
→ Append one short cited, timestamped note to the item, **in place**. When the partial resolution changed the item's *shape* — scope shrank, effort resized, prerequisites moved — also update its **subject**, **Size**, and **DependsOn** sub-bullets to describe only the remainder, then **re-order the milestone list** so it stays a dependency-true suggested sequence (nothing above what it depends on; the next work item on top).

`/zcrypto-grooming T0199 registered — insert into queue`
→ For a topic newly registered (typically mid-auto-exec): add a queue item in the standard sub-bullet shape — subject condensed from the `docs/open-topics/README.md` bullet, `Who` / `Size` / `Why` / `DependsOn` — at its **dependency- and priority-correct position** in the milestone list. Touch nothing else.

`/zcrypto-grooming iter-290 (PR #1332) has been merged`
→ The argument may name **delivered work** instead of a topic. Resolve it first — read the iteration's `docs/iterations-history-phase<N>.md` entry (and/or the PR) for the T-topic(s) it addressed — then apply the done / partially-done handling above to each matching queue item, citing the iter/PR as the evidence. Ambiguous resolution (several topics, different completion states) → ask, never guess.

Both forms: touch nothing else. No discovery, no purge, no NEW IDEAS, no frontmatter timestamp — those live in the full flow, behind its confirmations. No matching item → say so and stop.

## Bare invocation — the full flow, three steps in order

### Step 1 — discovery: drain NEW IDEAS

Parse the points and present your understanding of each; ask where unclear. Then per point — discuss, recommend, and settle exactly ONE disposition **together**:

| Agreed outcome | Action |
|---|---|
| Not pursuing | **Rewrite** into `ABANDONED ITEMS` — a summary reflecting the discussion (never a cut-and-paste), the subject, the decision date, and the drop date |
| Enhances / changes / invalidates an existing T\<NNNN\> | Remove the point from the memo; revise the topic file **interactively** so it stays internally consistent; index sync per `.claude/rules/open-topics.md` |
| New, deserves its own topic | Remove the point from the memo; create the T\<NNNN\> per `.claude/rules/open-topics.md` (serial check spans `archive/` **and** unmerged branches) |
| Undecided — any reason (no time, needs thought, no consensus yet) | Stays in `NEW IDEAS`, untouched — **the default**: a point leaves the inbox only through one of the other four outcomes |
| Already addressed (memory gap or changed context) | Cite the evidence — iter-N, T-topic, or PR — and drop **only after the user confirms the citation** |

Enhance-vs-new tiebreak: search for an owning topic first (`docs/open-topics/README.md` + the topic files) — enhance when an existing topic owns the subject, open new when none does. A point that instructs editing the very topic it would be filed into is **filed, not executed**, unless the user says execute now.

A drop the user gives without a reason is recorded as decision + dates only — **never invent a rationale the discussion did not produce**.

### Step 2 — pre-cleanup: reconcile the queue against reality

1. Read `last-grooming-section-at` from the memo frontmatter. Absent **or not a parseable timestamp** (a placeholder counts as absent) → agree a baseline with the user and set the key.
2. Queue empty → skip this and the matching step (nothing can match; say so). Otherwise collect what landed since then: merged PRs (`gh pr list --state merged --search "merged:>TS"`), commits (`git log --since=TS --oneline develop`), new iterations-history entries, and open-topics moves (`docs/open-topics/README.md`'s Resolved / Partially-done deltas, plus `archive/` — note `--diff-filter=A` there counts relocations as adds, so the index deltas and PR list are the reliable signal).
3. If the queue holds narrative status prose rather than discrete items, the same rule applies at block level: a block describing only finished work moves into `DONE ITEMS` **entire, never summarized-with-the-original-left-behind** — the purge gate disposes of it on confirmation; a mixed block keeps only its open remainder in the queue. **After grooming, the milestone contains only open work.** Then match against every `WORK-ITEMS QUEUE` item:
   - **fully resolved** → mark done with citations + timestamp, **move** the whole item to `DONE ITEMS`;
   - **partially resolved** → append one very short cited, timestamped note in place;
   - **fully open** → don't touch.
4. Then `DONE ITEMS` — all of it, including items staged by earlier ad-hoc invocations. **Empty → say so and move on**; the gate exists for content, not ceremony. Otherwise: display every item **numbered**; re-verify each against its citations (open the cited PR / commit / topic — a citation is a claim, and this run checks it); ask for **one batch confirmation**; purge everything confirmed. A negative answer is not the end of the step — discuss the disputed items until each is clear; an item the discussion reveals **not** actually done moves **back to `WORK-ITEMS QUEUE`** (with a note on what remains), and only the confirmed remainder is purged. **End state: `DONE ITEMS` contains no item.**

### Step 3 — grooming: analyze each milestone, then size it

Per `###` milestone under `WORK-ITEMS QUEUE`, in order:

1. **Ask the goal question — "what do we have to do to achieve this?"** The milestone's items plus their referenced T-topics are the **full picture**: all drained ⇒ milestone reached.
2. **Completeness sweep.** Walk the open topics (`docs/open-topics/README.md`'s `### Open` / `### Partially done` subsections, every `ripe_when`): anything relevant to the milestone and not on its list is added — jointly. This is where follow-ups hiding inside already-purged done work resurface (e.g. a tool shipped and purged whose *at-the-gate run* is still open). An added item **condenses** its index entry, never pastes it: the subject keeps the index's title wording; `Why` compresses to the one or two clauses that matter *for this milestone*; everything else stays in the topic file, reachable through the `T<NNNN>` reference. The sweep reads Open / Partially-done only — resolved topics stay done; if the user asks to queue one anyway, surface its resolved status first and confirm: the right shape is usually a NEW topic referencing the archived one, not a revival.
3. **Format follows length:**
   - **Short list** — no grouping. One entry per item, each a single T-topic: a bold subject line (the `docs/open-topics/README.md` index's wording is fine), then **sub-bullets** — `Who: … — Size: S/M/L`, `Why: …`, `DependsOn: …` (prerequisites — items, T-topics, or a named trigger/date; "—" when free). Sub-bullets, not inline fields: the memo is read by human and AI alike, and scanning beats parsing.
   - **Long list** (rule of thumb: ~8+ active items, or natural clusters) — group into work packages: a level-4 header `#### WP<N>: <name>` with the same sub-bullet fields at package level, then its items — one T-topic each.
4. **The list IS the schedule: order it as the suggested execution sequence, so the next work item is always the top one.** Nothing may sit above something it depends on. Settle sizes, `DependsOn` edges, and the sequence jointly. `/zcrypto-auto-exec` updates these items during autonomous runs via the ad-hoc procedures above — expect and preserve its annotations.

### Close — full runs only

Set `last-grooming-section-at:` to now (UTC, ISO-8601). Ad-hoc invocations never touch it, so the next full Step 2 re-scans a window covering them — harmless, since matching is idempotent.

## Common mistakes

| Impulse | Reality |
|---|---|
| "I'll just decide these three quickly" | Dispositions are joint. Undecided = stays in NEW IDEAS — that IS the fast path. |
| Rewriting the whole file for tidiness | Not version-controlled — whatever a rewrite silently drops is gone for good. Anchored edits. |
| Ad-hoc argument, but NEW IDEAS looks messy | Out of scope. Mention it; the user can invoke the full flow. |
| Purging DONE ITEMS as items arrive there | Purge happens once — after the numbered display and the batch confirmation. |
| Copying a memo paragraph into a T-topic | Paraphrase. The memo is private; topics are git-tracked. |
| Changing a T-topic's *status* without moving its `docs/open-topics/README.md` bullet | `open-topics.md` violation — the bullet moves on status transitions; a content-only edit may merely refresh its description. |
| Moving a *summary* to DONE ITEMS while the item's text stays in the queue | Move the WHOLE item — a groomed milestone carries no done work. (Caught in the first dry-run: a `DONE, merged` narrative survived grooming.) |
