# Multi-agent protocol

Sessions talk through `SendMessage`, addressed by name. Session identity is not in git (`git log -200 --format=%an | sort -u` prints one author): the lines below are assignments the sessions honour, not refusals a tool enforces.

## Roles and authorities

- `zcrypto-marco` — the coordinator: assigns work, keeps `.local/coordination.md`, and holds the PR word, topic registration and the memo.
- `zcrypto-alex`, `zcrypto-bravo` — payload sessions: one assignment at a time, in the worktree the brief names; they report by message.
- `zcrypto-zebra` — the owner's own session; marco assigns it a subject when the owner names it in (set: the zebra row of the table; count: `awk -F'|' '/^\| *zcrypto-zebra/ {gsub(/ /,"",$5); print $5!="—"}' .local/coordination.md`).
- Subagents belong to the dispatching session; a brief inlines the task's context and pastes neither memo nor table (set: the briefs in `.local/dispatch/`, subagent and payload alike — the files there named for the session they address, or for the brief or arm they are; count: `ls .local/dispatch/*.md | grep -Ei -- '-zcrypto-|brief|prompt|drafter|arm' | xargs -r grep -lE '^\| *zcrypto-(alex|bravo|zebra) *\||^#+ (WORK-ITEMS QUEUE|NEW IDEAS|DONE ITEMS|ABANDONED ITEMS)' | wc -l` — run from the main checkout, which is where the directory lives — briefs carrying a table row or a memo section heading; the directory's remaining files are worklists and read reports, which quote both by design).
- **The PR word is marco's, by the owner's delegation**: a payload session sends the component name — a spec, memo item, topic, or the defect a fix kills — with branch and commit hash; marco answers open, hold or a reason, and opens the PR. The owner's direct word to a payload session lets it open the PR itself, naming the word in the body.
- **Topic registration is marco's**: a finding left unresolved in-branch goes to marco as the topic's `Context` + `Why this matters`; marco registers, folds or drops it, and the PR that carried the finding records the answer — a topic file, or an explicit drop under `## Out of scope` (set: the topic keys in `docs/reference/change-index.md`; count: `for t in $(grep -oE '\bT[0-9]{4}\b' docs/reference/change-index.md | sort -u); do find docs/open-topics -name "$t-*.md" | grep -q . || echo "$t"; done | wc -l` — keys with no file).
- **The memo `.local/memo.md` is marco's** — one writer, `.claude/hooks/memo-guard.sh` refusing a write without a fresh read: a payload session sends the text and where it goes; marco writes it per `.claude/skills/zcrypto-grooming/references/memo-protocol.md` and records the chain in the table (set: the live memo against the table's chain line; count: `grep -c "$(sha256sum .local/memo.md | cut -c1-64).* · $(wc -l < .local/memo.md) · $(wc -c < .local/memo.md)" .local/coordination.md` — 1 when they match).
- **A lesson goes to the session's own inbox, not to its harness memory** — `~/.claude/projects/<cwd>/memory/` is one directory per checkout, loaded by that checkout's session and not harvested — through `infra/scripts/append-lesson.py`; the refine round harvests the inboxes (set: `.local/agent-lessons/*.jsonl`; count: `uv run python infra/scripts/check-agent-lessons.py .local/agent-lessons/*.jsonl | wc -l` — malformed records).

## Assignment

- **One subject per payload session — the owner's ruling.** A session whose branch is finished but gated on an external event stays idle; marco offers it no second subject and treats no idle session as spare capacity (set: the payload rows of the table; count: `awk -F'|' '/^\| *zcrypto-(alex|bravo|zebra)/ && split($5,a,/[;,+]/)>1' .local/coordination.md | wc -l` — rows holding two or more subjects).
- A subject goes to the idle session holding its context, else the idle one. A row is the session's current state; a guard, file or property a report names goes into the topic cell, compared pairwise before assigning (count: `awk -F'|' '/^\| *zcrypto-(alex|bravo|zebra)/ {gsub(/ /,"",$5); if ($5!="—") print $5}' .local/coordination.md | sort | uniq -d | wc -l` — a subject on two rows). A block below the table lives while its assignment is in flight (count: `grep -c '^## ' .local/coordination.md` against the rows holding a subject).
- A brief names the component, the session it addresses, the branch and the worktree, the boundary list (paths and actions it stays off), where output lands, whom to message, the concurrency bound, and who decides a gap (no count command: they are prose fields with no fixed literal — nothing can grep whether a brief names who decides a gap — where a memo or table paste, above, is a shape a grep reads; the skeleton below is what a brief is written from). Its shape:

  ```markdown
  # <component> — <session>
  Branch and worktree: <branch> at <path>
  Boundary: <paths and actions it stays off>
  Output: <where the work lands, and the report's shape>
  Message: <whom, at start, at each commit, when blocked, at completion>
  Concurrency: <how many subagents at once, and what may run in parallel>
  A gap is decided by: <marco, or the session itself, and for which class>
  ```
- An assignment whose pre-push loop reaches a third round carrying a Critical or Important gets a transcript retro by marco before that session's next assignment, written to a dated directory under `.local/retro/` with a proposed rule or skill change.

## Mechanics

- The hourly tick is installed on the owner's word, not by default — `zcrypto-main-session-init` holds its install step and prompt — and the table's `tick installed:` line records whether it is installed (`grep '^tick installed' .local/coordination.md`).
- A worktree is removed when its branch merges; the count that catches a stale one is processes with a cwd inside it (`for l in /proc/[0-9]*/cwd; do readlink "$l"; done 2>/dev/null | grep -c /tmp/claude-1000/`) beside worktrees whose branch is merged (`git worktree list --porcelain` against `git branch --merged develop`).
- `CLAUDE.md` and `.claude/` are edited through a `claude(…)` commit and no other kind — the `staged-kind` hook refuses the mix (set: `develop`'s commits touching those paths; count: `git log develop --format='%h %s' -- CLAUDE.md .claude | grep -vc ' claude('`); a PR lists its `claude(…)` commits under `## Guidance changes` (`open-pr`), where the owner reviews them.
- The owner renames a session with `/rename` from its console and tells marco; after a workstation restart `infra/scripts/zcrypto-tmux.zsh` rebuilds the cockpit, and marco re-reads the table before assigning.

## The worktree

- A payload session's branch lives in its own worktree, cut from the main checkout: `git worktree add -b <branch> /tmp/claude-1000/-home-zhaow-Projects-zcrypto-kraken/wt-<slug> develop`.
- The hooks are the clone's and every worktree shares them: `hooks` is one of the paths git keeps in the common directory rather than per worktree, so `git rev-parse --git-path hooks` in a worktree prints the main checkout's (where `--git-path HEAD` prints the worktree's own). A fresh worktree therefore commits under the same gate with no `pre-commit install`; what it pays instead is one `uv sync` on the first `uv run` there, since `.venv` is per-worktree. **A CLONE is the opposite and the sentence above does not cover it**: `git clone` gets its own hooks directory and inherits none, so a scratch clone commits with no gate at all until `pre-commit install` runs there — and the install is confirmed by its output — one `pre-commit installed at` line per hook type in `.pre-commit-config.yaml`'s `default_install_hook_types`, two today, so a bare `pre-commit install` that prints one line has not installed the commit-msg gate (a flagged `--hook-type` install prints one line naming its hook) — never assumed, because a suppressed one is indistinguishable from a successful one (2026-09-11: a thirteen-commit fix round ran in a scratch clone with no gate, found when `ruff format` failed at the tip).
- `.local/` and `data/` carry only their own `.gitignore`, so the memo, the coordination table and every dataset are absent there by construction. A dataset a task needs is symlinked in, unlinked before `git worktree remove`, and the main checkout's `data/` listing read afterwards (`CLAUDE.md` carries the rule; there is no undo).
- `infra/scripts/append-lesson.py` resolves the main checkout itself, so a lesson written from a worktree lands in the one inbox the refine round reads; the session passes its own name to `--session`.
- A worktree is removed when its branch merges (the count is in *Mechanics* above).

## The payload contract

A payload session works in the worktree named, inside the boundary list; reports at start, at each commit, when blocked and at completion, naming branch and commit hash; ends a turn with its state reported, not with work announced and unbegun; says what it saw — *I have heard nothing*, not *the owner has not spoken*, which the coordinator alone can tell apart; appends its lessons as they happen.

**The read before push is the payload session's own.** `CLAUDE.md` asks for a different agent from the author, and `infra/scripts/merge-gate.py` reads the model and the tip that the body's `Read before push by:` line names and never which session ran it — so the payload runs the `review` workflow itself over `develop..HEAD`, at the floor its own diff requires (Fable when a path it touched is under one the fixed list `uv run python infra/scripts/merge-gate.py --fable-paths` prints, Opus otherwise), fixes what the read holds, re-reads the fix range with `re-review`, and hands marco the tip and the line to put in the body. Marco takes the read instead only where the brief says so.
