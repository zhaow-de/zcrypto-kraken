---
name: zcrypto-grooming
description: Drain and groom .local/memo.md together with the user. Bare /zcrypto-grooming runs the full three-step flow; an argument ("T9999 is done", "T9999 is partially done", "T9999 registered — insert into queue", "iter-290 (PR #1332) has been merged") applies one mechanical queue procedure.
disable-model-invocation: true
model: claude-fable-5
allowed-tools: Read, Edit, Write, Grep, Glob, AskUserQuestion, Skill, Bash(git log:*), Bash(git show:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(gh pr list:*), Bash(gh pr view:*), Bash(date:*), Bash(uv run pre-commit:*)
---

# zcrypto-grooming

## What this is

`.local/memo.md` is the user's personal working memo. Its data model, tooling discipline, and the mechanical ad-hoc procedures live in **`references/memo-protocol.md`** — the single source of truth, also loaded by `/zcrypto-auto-exec`. Read it before touching the file.

Grooming is a **joint conversation**: this skill structures it, the user decides. Nothing in the memo is disposed of unilaterally — the memo is the user's memory, and an item silently mis-filed is worse than one left untouched.

## Invariants — every invocation, both modes

- **The protocol governs every touch of the file** — `references/memo-protocol.md`: re-read first, Edit/Write tools only under the read-guard, anchored edits, deletion only at the purge gate, privacy, formats.
- **The user's explicit agreement closes each item; undecided is the default state, not a failure.** A point nobody has ruled on simply stays in `NEW IDEAS` — under time pressure, for lack of consensus, or for any reason at all. Deciding solo is never the shortcut.

## With an argument — single-item update, nothing else

The four argument forms — each defined, with its exact scope, in `references/memo-protocol.md` § *Ad-hoc procedures*; the definitions there govern:

- `/zcrypto-grooming T9999 is done`
- `/zcrypto-grooming T9999 is partially done`
- `/zcrypto-grooming T9999 registered — insert into queue`
- `/zcrypto-grooming iter-290 (PR #1332) has been merged` (work-shaped — resolve to topics first)

All are mechanical and single-item — scope limits per the protocol's **All forms** rule. They may also be applied from within a human-launched `/zcrypto-auto-exec` run; the full flow below remains a live conversation with the user.

## Bare invocation — the full flow, three steps in order

### Step 1 — discovery: drain NEW IDEAS

Parse the points and present your understanding of each; ask where unclear. Then per point — discuss, recommend, and settle exactly ONE disposition **together**:

| Agreed outcome | Action |
|---|---|
| Not pursuing | **Rewrite** into `ABANDONED ITEMS` — a summary reflecting the discussion (never a cut-and-paste), the subject, the decision date, and the drop date |
| Enhances / changes / invalidates an existing T\<NNNN\> | Remove the point from the memo; revise the topic file **interactively** so it stays internally consistent; index sync through the `topic-ops` skill, which `.claude/rules/open-topics.md` reserves every topic-file operation for |
| New, deserves its own topic | Remove the point from the memo; create the T\<NNNN\> through the `topic-ops` skill (its serial check spans `archive/` **and** unmerged branches) |
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
2. **Completeness sweep.** Walk the open topics (`docs/open-topics/README.md`'s `### Open` / `### Partially done` subsections, every `ripe_when`): anything relevant to the milestone and not on its list is added — jointly. This is where follow-ups hiding inside already-purged done work resurface (e.g. a tool shipped and purged whose *at-the-gate run* is still open). An added item **condenses, never pastes** (rule + shape per the protocol § *Item shape and sequencing*). The sweep reads Open / Partially-done only — resolved topics stay done; if the user asks to queue one anyway, surface its resolved status first and confirm: the right shape is usually a NEW topic referencing the archived one, not a revival.
3. **Formats per the protocol**: short list → per-topic sub-bullet entries; ~8+ active items → `#### WP<N>:` groups.
4. Settle sizes, `DependsOn` edges, and the sequence jointly — the list is the schedule, and milestones themselves order dependency-true with their own `DependsOn:` lines (protocol § *Item shape and sequencing*). `/zcrypto-auto-exec` updates these items during autonomous runs via the ad-hoc procedures above — expect and preserve its annotations.

### Close — full runs only

Set `last-grooming-section-at:` to now (UTC, ISO-8601) — full runs only; semantics per the protocol § *The file*.

## Common mistakes

| Impulse | Reality |
|---|---|
| "I'll just decide these three quickly" | Dispositions are joint. Undecided = stays in NEW IDEAS — that IS the fast path. |
| Rewriting the whole file for tidiness | Not version-controlled — whatever a rewrite silently drops is gone for good. Anchored edits. |
| Ad-hoc argument, but NEW IDEAS looks messy | Out of scope. Mention it; the user can invoke the full flow. |
| Purging DONE ITEMS as items arrive there | Purge happens once — after the numbered display and the batch confirmation. |
| Copying a memo paragraph into a T-topic | Paraphrase. The memo is private; topics are git-tracked. |
| Changing a T-topic's *status* without moving its `docs/open-topics/README.md` bullet | `open-topics.md` violation — the bullet moves on status transitions; a content-only edit may merely refresh its description. |
| Moving a *summary* to DONE ITEMS while the item's text stays in the queue | Move the WHOLE item — a groomed milestone carries no done work. |
