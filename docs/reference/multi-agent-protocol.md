# Multi-agent protocol

Sessions talk through `SendMessage`, addressed by name. Session identity is not in git (`git log -200 --format=%an | sort -u` prints one author): the lines below are assignments the sessions honour, not refusals a tool enforces.

## Roles and authorities

- `zcrypto-marco` — the coordinator: assigns work, keeps `.local/coordination.md`, and holds the PR word, topic registration, the memo and memory.
- `zcrypto-alex`, `zcrypto-bravo` — payload sessions: one assignment at a time, in the worktree the brief names; they report by message.
- `zcrypto-zebra` — the owner's own session; marco assigns it a subject when the owner names it in (set: the zebra row of the table; count: `awk -F'|' '/^\| *zcrypto-zebra/ {gsub(/ /,"",$5); print $5!="—"}' .local/coordination.md`).
- Subagents belong to the dispatching session; a brief inlines the task's context and pastes neither memo nor table (set: the briefs in `.local/dispatch/`; count: `grep -rl --no-ignore-files 'Memo chain carried by main' .local/dispatch/ | wc -l`).
- **The PR word is marco's, by the owner's delegation**: a payload session sends the component name — a spec, memo item, topic, or the defect a fix kills — with branch and commit hash; marco answers open, hold or a reason, and opens the PR. The owner's direct word to a payload session lets it open the PR itself, naming the word in the body.
- **Topic registration is marco's**: a finding left unresolved in-branch goes to marco as the topic's `Context` + `Why this matters`; marco registers, folds or drops it, and the PR that carried the finding records the answer — a topic file, or an explicit drop under `## Out of scope` (set: the topic keys in `docs/reference/change-index.md`; count: `for t in $(grep -oE '\bT[0-9]{4}\b' docs/reference/change-index.md | sort -u); do find docs/open-topics -name "$t-*.md" | grep -q . || echo "$t"; done | wc -l` — keys with no file).
- **The memo `.local/memo.md` is marco's** — one writer, `.claude/hooks/memo-guard.sh` refusing a write without a fresh read: a payload session sends the text and where it goes; marco writes it per `.claude/skills/zcrypto-grooming/references/memo-protocol.md` and records the chain in the table (set: the live memo against the table's chain line; count: `grep -c "$(sha256sum .local/memo.md | cut -c1-64).* · $(wc -l < .local/memo.md) · $(wc -c < .local/memo.md)" .local/coordination.md` — 1 when they match).
- **Memory (`~/.claude/projects/…/memory/`) is marco's**: a lesson goes to the session's own inbox through `infra/scripts/append-lesson.py`, and the refine round harvests the inboxes (set: `.local/agent-lessons/*.jsonl`; count: `uv run python infra/scripts/check-agent-lessons.py .local/agent-lessons/*.jsonl | wc -l` — malformed records).

## Assignment

- **One subject per payload session — the owner's ruling.** A session whose branch is finished but gated on an external event stays idle; marco offers it no second subject and treats no idle session as spare capacity (set: the payload rows of the table; count: `awk -F'|' '/^\| *zcrypto-(alex|bravo|zebra)/ && split($5,a,/[;,+]/)>1' .local/coordination.md | wc -l` — rows holding two or more subjects).
- A subject goes to the idle session holding its context, else the idle one. A row is the session's current state; a guard, file or property a report names goes into the topic cell, compared pairwise before assigning (count: `awk -F'|' '/^\| *zcrypto-(alex|bravo|zebra)/ {gsub(/ /,"",$5); if ($5!="—") print $5}' .local/coordination.md | sort | uniq -d | wc -l` — a subject on two rows). A block below the table lives while its assignment is in flight (count: `grep -c '^## ' .local/coordination.md` against the rows holding a subject).
- A brief names the component, the worktree, the boundary list (paths and actions it stays off), where output lands, whom to message, the concurrency bound, and who decides a gap (set: the briefs; count: `grep -rL --no-ignore-files -E 'worktree|wt-' .local/dispatch/*.md | wc -l` — briefs naming no worktree).
- An assignment whose pre-push loop reaches a third round carrying a Critical or Important gets a transcript retro by marco before that session's next assignment, written to a dated directory under `.local/retro/` with a proposed rule or skill change.

## Mechanics

- The hourly tick is installed on the owner's word, not by default — `zcrypto-main-session-init` holds its install step and prompt — and the table's `tick installed:` line records whether it is installed (`grep '^tick installed' .local/coordination.md`).
- A worktree is removed when its branch merges; the count that catches a stale one is processes with a cwd inside it (`for l in /proc/[0-9]*/cwd; do readlink "$l"; done 2>/dev/null | grep -c /tmp/claude-1000/`) beside worktrees whose branch is merged (`git worktree list --porcelain` against `git branch --merged develop`).
- `CLAUDE.md` and `.claude/` are edited through a `claude(…)` commit and no other kind — the `staged-kind` hook refuses the mix (set: `develop`'s commits touching those paths; count: `git log develop --format='%h %s' -- CLAUDE.md .claude | grep -vc ' claude('`); a PR lists its `claude(…)` commits under `## Guidance changes` (`open-pr`), where the owner reviews them.
- The owner renames a session with `/rename` from its console and tells marco; after a workstation restart `infra/scripts/zcrypto-tmux.zsh` rebuilds the cockpit, and marco re-reads the table before assigning.

## The payload contract

A payload session works in the worktree named, inside the boundary list; reports at start, at each commit, when blocked and at completion, naming branch and commit hash; ends a turn with its state reported, not with work announced and unbegun; says what it saw — *I have heard nothing*, not *the owner has not spoken*, which the coordinator alone can tell apart; appends its lessons as they happen.
