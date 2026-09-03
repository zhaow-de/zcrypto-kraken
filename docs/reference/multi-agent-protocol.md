# Multi-agent protocol

Four named Claude Code sessions on this repo, one owner. The owner keeps all four running; sessions talk only through `SendMessage`, addressed by name.

## Roles

- **`zcrypto-main` — the coordinator.** Runs no payload work: no SDD loop, no plan-review loop, no drill, no daily-ops pass, no investigation. It grooms the backlog, assigns work, holds the authorities below, and runs the hourly tick. Git ownership is coordination: main opens and merges PRs. Its own hands-on work is the coordination corpus itself — grooming, refine-rules rounds, this protocol.
- **`zcrypto-alex`, `zcrypto-bravo` — payload sessions.** Idle until main assigns; execute one assignment at a time in their own worktree; report by message.
- **`zcrypto-zebra` — the owner's own session.** Never in the assignment pool. Main assigns it nothing unless the owner names it.
- **Subagents** belong to the session that dispatched them and are not handed `docs/memo.local.md` or `docs/coordination.local.md` — a dispatch inlines the task's own context and never pastes the memo (`.claude/skills/zcrypto-grooming/references/memo-protocol.md`).

## Authorities held only by main

- **PRs.** A payload session never opens or merges a PR. It sends main the component name (`branch-workflow.md`'s gate, step 1) and its branch state; main answers open, hold, or a reason — it holds the owner's PR word by delegation (`.claude/rules/branch-workflow.md` names it) — and main opens it. The one carve-out: the owner's direct word to a payload session, which then opens the PR itself and names that word in the body.
- **T-topics.** A payload session never registers a topic. A finding it cannot resolve in-branch goes to main as the topic's `Context` + `Why this matters`; main registers, folds, or drops — **with the word recorded**. The request is the queue; silent drop is impossible because dropping now needs main's explicit answer. With no coordinator reachable, the session registers it and names it in its hand-back for confirm-or-kill (`open-topics.md`).
- **Memory.** Only main writes `~/.claude/projects/…/memory/`. A payload session's lessons go to `docs/reference/agent-lessons.jsonl` on its branch — by message to main only for branchless work, per the payload contract; main files in memory what the harvest shows belongs there.
- **The memo.** Written under the token below. `docs/coordination.local.md` is main's alone and needs no token.

## The memo token

`docs/memo.local.md` is gitignored — a clobber has no undo — so writes are serialized by a token main holds.

1. A writer requests the token from main, naming the exact edit.
2. Main grants it to one session at a time.
3. The writer reads the file immediately before writing, edits with the Edit/Write tools only (a shell heredoc bypasses the read-guard), reads back after, and hands the token back with the chain: `sha256 · lines · bytes` before and after.
4. Main verifies the chain from the file, not from the message, and carries it.

## Assignment

- **Availability and affinity.** Main keeps the coordination table: session → status (idle / busy) → branch → topic or spec → warm-context tags → last report. A subject goes to the idle session that already holds its context; else the idle one; never zebra.
- **One assignment per payload session at a time.** An assignment message carries: the component name; the worktree to use; the boundary list — paths it must not write, actions it must not take (venue, credentials, converges, PRs, topics); where output lands; and who to message about what.
- **Every payload status message names its branch and latest commit hash**, so main can read progress from git without asking.

## The hourly tick

Main runs it from an in-session `CronCreate` job — session-only, fires only while main is idle, **expires after seven days**: reinstall it at every restart and every week.

1. `ListAgents`. A session missing for one tick is tolerated; missing for two is reported to the owner.
2. **Poke first.** A payload session that is idle with an open assignment gets a one-line message: what it last declared and a request to continue. This is the whole enforcement mechanism for announced-but-not-started work — a stalled turn resumes on any message, and the owner measured this working where inspection would have been overkill.
3. Read git state — branches moved, worktrees, open PRs — and the memo's work-package markers.
4. Post one report to the owner: per session, what it is on (branch / topic / spec) and whether the branch moved since last tick; the backlog's next three items; anything flagged.

## Restart and rename

- A session cannot be renamed by the session; the owner runs `/rename` from its console, at a quiet moment, and tells main.
- After a `claude` binary update the owner exits and resumes each session with no running tasks; names persist, connections re-establish.
- After a workstation restart, `infra/scripts/zcrypto-tmux.zsh` rebuilds the cockpit — one tmux session `zcrypto-main` with the three payload-and-coordinator panes resuming their Claude sessions by ID — and the owner's `zcrypto-zebra` shell; idempotent, so it is safe to run whenever a session is missing. Main reinstalls its tick on resume and re-reads the coordination table before assigning anything.

## The payload contract

A payload session, on receiving an assignment: works only in the worktree named; never writes outside the boundary list; never opens a PR, registers a topic, or writes memory — it asks main, except as `## Authorities held only by main` carves out; reports at start, at each commit, when blocked, and at completion, each report carrying branch and commit hash; ends a turn only with its state reported, never with work announced and not begun; appends its own self-corrections, rule deviations, and rule or skill feedback to `docs/reference/agent-lessons.jsonl` on its branch as they happen — branchless work (a review, a read) sends the record to main, who appends it with the `session` field naming its origin.
