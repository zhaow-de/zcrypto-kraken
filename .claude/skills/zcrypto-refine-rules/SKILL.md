---
name: zcrypto-refine-rules
description: Use before editing CLAUDE.md, a rule under .claude/rules/, a skill file or a top-level page under infra/runbooks/, and for `/zcrypto-refine-rules round`, the guidance round.
model: fable
---

# zcrypto-refine-rules

## Before you write guidance

The always-loaded set — `CLAUDE.md`, `.claude/rules/*.md`, every skill's `name:` and `description:` lines, and every saved workflow's `name`, `description` and `whenToUse` strings — is paid by every session on every turn; a skill's body, and a workflow's, is paid only when it loads. Measure it, never recall it: `infra/scripts/count-list.sh ambient-bytes`.

A line lands on one of four grounds, or it does not land:

1. a mechanical check enforces it — a test, a hook, a role's refusal — and the line names the check;
2. it is safety-critical for capture data, the venue account or a secret;
3. it is a recurring cross-session failure with an existing check;
4. the owner kept it by name.

Net ambient growth is the owner's word, in a round or outside one: a coordinator cannot grant it and a session cannot grant its own. A session does not author a change to the instruction set that governs it, so a guidance change rides its own branch, never a payload's.

Three tests on the line as written, two of them the guard's:

- **The universal test.** A bullet that says *every*, *never*, *always*, *only*, *any* or *cannot* names its set and its count — `(set: …; count: `infra/scripts/count-list.sh <entry>`)` — or declares `(no count command: <why nothing in the tree records it>)`. The guard reads every list item of `CLAUDE.md`, the rules and the contracts read whole by the sessions, skills and operators that act on them — `docs/reference/fleet.md`, `docs/reference/fleet-pins.md`, the memo protocol and every top-level page under `infra/runbooks/` (a page in a subdirectory is not read), read for universals and never counted as ambient — `-`, `*`, `+` and numbered, nested ones included, a wrapped item as one block when its continuation lines are indented, a step's prose under its own indented command block included, code spans and fenced code blocks set aside — and refuses one whose prose carries the word with neither the entry nor the declaration; it does not judge the set, which is the reader's. A paragraph or a heading it does not read. An entry is a `c_<name>` function in `infra/scripts/count-list.sh` plus its `emit "<entry>"` line; `tests/test_count_list.py` pins that every entry a corpus line names exists.
- **The trade.** The ambient set grows only for a stated reason: the commit message carries one line, `Ambient grows by N bytes: <reason>`, with N the exact growth the guard measures from the staged files; a deletion of equal size in the same commit needs no line, and a line on a commit that does not grow the set is refused. The guard measures the commit against `HEAD`, or against the amended commit's parent when the subject is unchanged — every file the whole commit changes — so an amend states the whole commit's growth: the hook checks it while the subject is kept, and a message-only amend must keep its line right. To reword an amended commit, stage under the kept subject first, then reword message-only: skip the first step and the hook, seeing only the increment, refuses the whole-growth line as too large, while the gate judges the whole commit. A commit that changes no ambient file is not judged, and neither instrument judges a merge commit — a conflict resolution that adds lines to an ambient file is the reader's. What no commit-msg hook sees — a reworded amend, a squash or fixup in a rebase — `merge-pr`'s gate catches at merge: `infra/scripts/guidance-guard.py --range <base>..<head>` judges every non-merge commit of the branch against its parent, so a line a rewrite lost or doubled is refused there, and a branch whose commits predate the guard states their growth by rewording each commit the mode names; an uncounted universal at an intermediate commit is cured only by a rebase that edits that commit. A growth with no reason worth one line is a line that does not belong.
- **Placement.** A numbered skill step is its own command in its own shell, so a name one step defines is gone in the next: a step hands its successor a printed value or a file, never a variable. What every session must do on every turn goes to `CLAUDE.md`; what it must do in one domain goes to that domain's rule; a procedure goes to the skill step where it runs; a claim a check can make goes to the check, and the sentence goes. A ruling on how work is performed lands its imperative on the surface that performs it — the skill step, the runbook section, the role — in the same change; a ruling that lives only in a spec, a topic or the memo is invisible at execution time. A skill's description is ambient — write it as the trigger and nothing else.

A lesson goes to the inbox through `infra/scripts/append-lesson.py`, never straight into a rule: the round below is where a lesson becomes guidance, under the trade above.

## The round — `/zcrypto-refine-rules round`

A joint session, the owner's word closing every disposition; undecided is the default. One open decision set at a time: fact-collection may run ahead, but the next step's findings are held until the previous step's dispositions close. Any "later" outcome registers a topic in the same step, `T<NNNN>` via `topic-ops`, never only the round's report. A hook is proposed case-by-case and shown to the owner before it lands.

### Step 1 — Harvest

The candidate set is the inbox records themselves: every `.local/agent-lessons/<session>.jsonl` in the main checkout (swept with `infra/scripts/sweep.sh -e '^{"ts":'` — anchored, that is a lesson record's own opening, which no tracked file carries. The sweep's ordinary answer here is a hit, and a hit is its own proof it saw: the archive below keeps the records past rounds took, so a rotation empties the inboxes and not the sweep, and no content pattern separates a live inbox from the archive beside it, the two holding the same records — the paths do, one on every line of the output. A line under `.local/agent-lessons/<session>.jsonl` is a candidate, one under `harvested/` is a record already taken, and any other path is not a lesson record. rc 2 says no record matched anywhere, live inbox or archive — the finding to run down, not the missing control the message offers; whether `.local/` was in the list is the separate door, the `no <path>/.local` line on stderr), `infra/scripts/check-agent-lessons.py` on each first, a malformed line being a finding, not a skip. Read per session and grouped by class into the round's table, id `<session>:<ts>`. A harvested inbox rotates to `.local/agent-lessons/harvested/<round-date>/` in the same step — that rotation is the archive — so the next round starts from empty inboxes and no record is harvested twice.

- **Watermark**: `git log -1 --grep='^Refine-Round-Closed:' --format=%cI` — the previous round's closing commit, found by its `Refine-Round-Closed:` trailer. The commit's date is the boundary, not the trailer's value, which is stamped before the commit lands; `count-list.sh claude-commits-since-the-round-closed` anchors on the same commit. No match ⇒ first round: harvest every inbox whole plus the trailing two weeks.
- **Other sources since the watermark**: `git log` over `.claude/`; merged PR bodies; lessons either party names in the session.
- **The memory walk** is the standing items the memory dir holds — `MEMORY.md`'s index — the only files Step 2 stages and Step 5 deletes. An item that stays there keeps the memory-file shape: frontmatter `name`/`description`/`metadata.type`, body with **Why** and **How to apply**; a memory that CONFERS a capability names the session it belongs to — read by a session it does not describe, it hands over an authority nobody granted; a prohibition is safe subjectless.
- A candidate that duplicates a standing memory item updates that item instead.

### Step 2 — Graduate (joint)

Walk every candidate in the round's table and every standing memory item alike. Per item, exactly one disposition, the owner's word closing each:

| Disposition | Action |
|---|---|
| → CLAUDE.md or a rule | The shortest imperative form lands there, under the edit contract above — the guard takes the trade and the universal test at the commit |
| → an existing skill | Lands at the step where it applies |
| → a new skill | Only with the description-is-ambient cost measured and acknowledged |
| → a hook proposal | Shown to the owner; on approval, lands with the settings change |
| stays in memory | Personal or session-scoped — not repo-worthy; the default when undecided. An inbox record that stays is written as a memory file in Step 1's shape |
| dropped | With the owner's word; a standing item's file is deleted at Step 5, an inbox record rests in the archive |

A graduated standing item's file is **staged** — moved to `graduated/<round-date>/` under the memory dir — never deleted here: memory is unversioned, and an unverified landing must not be the only copy's obituary; a graduated inbox record is already archived by Step 1's rotation. Record every graduation in a table: *item → disposition → landing path*. Deletion is Step 5's last action.

### Step 3 — Count list

Run `infra/scripts/count-list.sh`. It prints one line per entry — the entry's name and today's value; a surviving universal in `CLAUDE.md` and `.claude/rules/` names its set in prose and its entry as `count: `infra/scripts/count-list.sh <entry>``, and the script's `c_` function behind that entry is the command.

- **A non-zero count is a finding**, except where zero is not the healthy value: `prose-chars`, a number to watch; `pinned-leaves-the-edge-renders`, the client PEMs the edge renders, healthy at 1; a value that reads `N passed`, a passing suite; `topic-only-merges`, `claude-commits-since-the-round-closed` and `worktrees`, each a state of the moment rather than a violation; and `operator-term-surfaces`' second value, which counts every commit whose diff touches `_WP_CARRIERS` — prose that merely names the allowlist moves it as surely as an edit to it, so read those diffs before calling a rise a widening. A separate set is `tests/test_count_list.py`'s `NOT_NAMED`, the entries no corpus line cites; it overlaps this one and is not it. Resolve a finding in the round: fix the practice, narrow the rule, or delete the rule.
- **An `ERROR` line is its own finding** — the script exits 2 and names the entries that errored on stderr; a count that cannot run is not a count of 0.
- **A universal with no entry beside it is the finding** — the guard refuses one at commit, so a standing one is older than the guard or sits in a paragraph the guard does not read. It is given a set and an entry in this round, or it goes.

Read the corpus and you can find a stale path, two texts that disagree, and a name that has gone stale; you structurally cannot find a rule whose text is entirely correct, whose citations all resolve, and which is simply not obeyed by the population it governs, because nothing in a read counts that population — which is why this step counts instead of reading. Output is a findings table, resolved jointly; the values live in that table, never in the corpus lines.

### Step 4 — Condense

**Load `references/principles.md` now** — the principles there govern every edit in this step. Work the biggest always-loaded offenders first (`wc -c CLAUDE.md .claude/rules/*.md | sort -n`, then the skill descriptions by length). The standing prose worklist is `.local/prose-gap/` in the main checkout; `.claude/` is this round's own subject and is worked in Steps 2–3, not here.

### Step 5 — Verify

In order, all five before anything is deleted:

- **(a) Cold read** — the `review` workflow over the round's range at the tip the PR body names, read for weakened or lost invariants on every changed line, not only removals: rewording can weaken a `Never` without deleting it. A commit made after that read re-opens it: the read covers the tip it names and nothing past it.
- **(b) Modal floor** — `grep -cE 'Never|never|MUST|must|only|refuse|explicit' CLAUDE.md .claude/rules/*.md` before vs after; any decrease itemized and justified line by line, never summarized.
- **(c) Graduation table check** — every row's content verified present at its named landing path, staged files included.
- **(d) Net measurement** — `infra/scripts/count-list.sh ambient-bytes` before vs after; the delta goes in the closeout.
- **(e) Commit gate** — `uv run pre-commit run -a` until clean.

Then, and only then, delete the staged memory files and update `MEMORY.md`.

### Closing

The round closes with one commit: Step 5 (d)'s delta in its body as prose (the growth line, when the round grows the set, is its own line), the watermark trailer — `Refine-Round-Closed: <ISO-8601 UTC>` — below `Co-Authored-By:`, which opens the trailer block. Verify end-to-end before reporting done:

```bash
test "$(git log -1 --grep='^Refine-Round-Closed:' --format=%H)" = "$(git rev-parse HEAD)"
```
