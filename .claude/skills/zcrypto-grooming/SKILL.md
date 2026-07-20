---
name: zcrypto-grooming
description: Drain and groom docs/memo.local.md together with the user — triage NEW IDEAS into agreed dispositions, reconcile WORK-ITEMS QUEUE against what actually merged, verify-and-purge DONE ITEMS, and size the milestone backlogs. Invoked manually — bare /zcrypto-grooming for the full three-step flow, or with an argument ("T0199 is done", "T0199 is partially done") for a single-item queue update. Never self-invoke.
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Grep, Glob, AskUserQuestion, Bash(git log:*), Bash(git diff:*), Bash(git add:*), Bash(git commit:*), Bash(gh pr list:*), Bash(gh pr view:*), Bash(date:*), Bash(uv run pre-commit:*)
---

# zcrypto-grooming

## What this is

`docs/memo.local.md` is the user's personal working memo — **gitignored, hand-edited between sessions, and holding plaintext credentials by deliberate design**. Its canonical sections:

| Section | Role |
|---|---|
| `NEW IDEAS` | idea inbox, ~one paragraph per idea (loosely — points↔paragraphs are usually 1:1 but can be m:n) |
| `WORK-ITEMS QUEUE` | the intermediate backlog; each `###` heading is a user-curated **milestone** |
| `DONE ITEMS` | staging for finished items awaiting verified purge |
| `ABANDONED POINTS` | ideas decided against, each with its decision date |

Grooming is a **joint conversation**: this skill structures it, the user decides. Nothing in the memo is disposed of unilaterally — the memo is the user's memory, and an item silently mis-filed is worse than one left untouched.

## Invariants — every invocation, both modes

- **Re-read the file first.** It is gitignored and changes outside Claude sessions; any copy already in context is stale by definition.
- **Anchored edits only — never rewrite the file wholesale.** The credentials block must survive every grooming byte-identical. Never quote credentials into output, never paste memo content into a subagent prompt, never run a subagent on this file in any role. A wholesale `Write` is how credentials get lost; `Edit` with exact anchors is how they don't.
- **Memo text never lands verbatim in git-tracked files.** A new or revised T-topic paraphrases the idea; `WP<N>` labels stay memo-only (standing repo rule).
- **The user's explicit agreement closes each item.** Time pressure does not change this — the protocol's built-in fast path is *leaving points in NEW IDEAS*, not deciding them solo.
- If the live headings differ from the canonical four above, surface the mismatch and agree the mapping (or a one-time restructure) with the user before editing anything.

## With an argument — single-item update, nothing else

`/zcrypto-grooming T0199 is done`
→ Find the `WORK-ITEMS QUEUE` item(s) referencing that topic. Mark done citing the evidence (iter-N / T-topic / commits / PRs — whichever apply) with a timestamp, then **move** the whole item to `DONE ITEMS`.

`/zcrypto-grooming T0199 is partially done`
→ Append one short cited, timestamped note to the item, **in place**.

Both forms: touch nothing else. No discovery, no purge, no NEW IDEAS, no frontmatter timestamp — those live in the full flow, behind its confirmations. No matching item → say so and stop.

## Bare invocation — the full flow, three steps in order

### Step 1 — discovery: drain NEW IDEAS

Parse the points and present your understanding of each; ask where unclear. Then per point — discuss, recommend, and settle exactly ONE disposition **together**:

| Agreed outcome | Action |
|---|---|
| Not pursuing | **Rewrite** into `ABANDONED POINTS` — a summary reflecting the discussion (never a cut-and-paste), the subject, the decision date, and the drop date |
| Enhances / changes / invalidates an existing T\<NNNN\> | Remove the point from the memo; revise the topic file **interactively** so it stays internally consistent; index sync per `.claude/rules/open-topics.md` |
| New, deserves its own topic | Remove the point from the memo; create the T\<NNNN\> per `.claude/rules/open-topics.md` (serial check spans `archive/` **and** unmerged branches) |
| No time to decide now | Leave it in `NEW IDEAS`, untouched |
| Already addressed (memory gap or changed context) | Cite the evidence — iter-N, T-topic, or PR — and drop **only after the user confirms the citation** |

### Step 2 — pre-cleanup: reconcile the queue against reality

1. Read `last-grooming-section-at` from the memo frontmatter. Absent → agree a baseline timestamp with the user and add the key.
2. Collect what landed since then: merged PRs (`gh pr list --state merged --search "merged:>TS"`), commits (`git log --since=TS --oneline develop`), new iterations-history entries, and open-topics moves (the README's Resolved / Partially-done deltas, plus `archive/`).
3. Match against every `WORK-ITEMS QUEUE` item:
   - **fully resolved** → mark done with citations + timestamp, **move** the whole item to `DONE ITEMS`;
   - **partially resolved** → append one very short cited, timestamped note in place;
   - **fully open** → don't touch.
4. Then `DONE ITEMS` — all of it, including items staged by earlier ad-hoc invocations: display every item **numbered**; re-verify each against its citations (open the cited PR / commit / topic — a citation is a claim, and this run checks it); ask for **one batch confirmation**; purge everything confirmed. A negative answer is not the end of the step — discuss the disputed items until each is clear, then purge. **End state: `DONE ITEMS` contains no item.**

### Step 3 — grooming: size what remains

Each `###` milestone under `WORK-ITEMS QUEUE` is a logical cluster: its items plus their referenced T-topics are the **full picture** — all drained ⇒ milestone reached. Jointly, per milestone: dependencies between items, T-shirt size (S/M/L), and priority. `/research-loop` may also update these items during autonomous runs — expect and preserve its annotations.

### Close — full runs only

Set `last-grooming-section-at:` to now (UTC, ISO-8601). Ad-hoc invocations never touch it, so the next full Step 2 re-scans a window covering them — harmless, since matching is idempotent.

## Common mistakes

| Impulse | Reality |
|---|---|
| "I'll just decide these three quickly" | Dispositions are joint. Undecided = stays in NEW IDEAS — that IS the fast path. |
| Rewriting the whole file for tidiness | The file holds credentials; wholesale writes are how they get lost. Anchored edits. |
| Ad-hoc argument, but NEW IDEAS looks messy | Out of scope. Mention it; the user can invoke the full flow. |
| Purging DONE ITEMS as items arrive there | Purge happens once — after the numbered display and the batch confirmation. |
| Copying a memo paragraph into a T-topic | Paraphrase. The memo is private; topics are git-tracked. |
| Editing a T-topic without moving its README bullet | `open-topics.md` violation — index sync rides the same change. |
