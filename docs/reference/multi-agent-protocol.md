# Multi-agent protocol

Four named Claude Code sessions on this repo, one owner. The owner keeps all four running; sessions talk only through `SendMessage`, addressed by name.

## Roles

- **`zcrypto-marco` — the coordinator.** Runs no payload work: no SDD loop, no plan-review loop, no drill, no daily-ops pass, no investigation. It grooms the backlog, assigns work, holds the authorities below, and runs the hourly tick. Git ownership is coordination: main opens and merges PRs. Its own hands-on work is the coordination corpus itself — grooming, refine-rules rounds, this protocol. It runs on Fable; when the weekly Fable quota is exhausted it falls back to Opus and says so in the coordination table. Payload drafting runs on the tier the owner names per assignment; reviewers by blast radius (`commit-messages.md`).
- **`zcrypto-alex`, `zcrypto-bravo` — payload sessions.** Idle until main assigns; execute one assignment at a time in their own worktree; report by message.
- **`zcrypto-zebra` — the owner's own session.** Never in the assignment pool. Main assigns it nothing unless the owner names it.
- **Subagents** belong to the session that dispatched them and are not handed `.local/memo.md` or `.local/coordination.md` — a dispatch inlines the task's own context and never pastes the memo (`.claude/skills/zcrypto-grooming/references/memo-protocol.md`).

## Authorities held only by main

- **PRs.** A payload session never opens or merges a PR. It sends main the component name (`branch-workflow.md`'s gate, step 1) and its branch state; main answers open, hold, or a reason — it holds the owner's PR word by delegation (`.claude/rules/branch-workflow.md` names it) — and main opens it. The one carve-out: the owner's direct word to a payload session, which then opens the PR itself and names that word in the body.
- **T-topics.** A payload session never registers a topic. A finding it cannot resolve in-branch goes to main as the topic's `Context` + `Why this matters`; main registers, folds, or drops — **with the word recorded in a topic file in the PR that carried the finding**, never only in a reply or the coordination table; a *later batch* answer is a registration into the umbrella topic now. The request is the queue; silent drop is impossible because dropping now needs main's explicit answer. With no coordinator reachable, the session registers it and names it in its hand-back for confirm-or-kill (`open-topics.md`).
- **Memory.** Only main writes `~/.claude/projects/…/memory/`. A session's lessons go to its own inbox per `agent-ops.md`'s inbox rule; a record's `session` names the origin and its `branch` where the WORK happened, `(branchless: <what>)` when there was none; the refine-rules round harvests every inbox, and main files in memory what the harvest shows belongs there.
- **The memo.** Main's alone — the section below. `.local/coordination.md` is main's alone too.

## The memo

`.local/memo.md` is gitignored (`agent-ops.md`'s no-undo rule applies) and exists only in the main checkout — a worktree has no `.local/` — so the memo has one writer: main. A payload session sends main the exact text and where it goes; main writes it under the memo-protocol's read-guard (`.claude/skills/zcrypto-grooming/references/memo-protocol.md`) and records the chain — `sha256 · lines · bytes` — in the coordination table after every write.

## Assignment

- **Availability and affinity.** Main keeps the coordination table: session → status (idle / busy) → branch → topic or spec → warm-context tags → last report. A subject goes to the idle session that already holds its context; else the idle one; never zebra.
- **One assignment per payload session at a time**, and every payload status message names its branch and latest commit hash, so main reads progress from git without asking.
- **A dispatch on a fresh owner instruction that REORDERS a sequenced package waits one turn for the owner's next message, or its brief says HELD at its head** — a dispatch is cheap to send and expensive to unwind.
- **A table row is the session's CURRENT state, one line per cell** — status, branch, topic or spec, and what the branch has GROWN: a new guard, file or claimed property named in a payload report goes into the topic column, and the tick compares the columns pairwise, since a property pinned on two branches is a merge collision and a doubled review cost before it is anything else. A block below the table exists only while its assignment is in flight and is deleted when it lands.
- **A dispatched assignment whose pre-push loop reaches its third round carrying a Critical or Important gets a transcript retro by main before that session's next assignment** — rounds, findings by class, minutes per round, what the author's own tier could have caught; the output is registry records and a proposed rule or skill change, never a verbal note.

## The brief

An assignment message carries:

- the component name and the worktree to use;
- the boundary list — paths it must not write, actions it must not take (venue, credentials, converges, PRs, topics) — and where output lands;
- who to message about what, and the concurrency bound — a fan-out wider than it asks first;
- an arm for a gap surfaced by implementation: it goes to whoever decides items in that assignment;
- when the owner is present in the payload session, what the owner decides, with questions batched per topic.

Its scope has three rules: a scope line that licenses an artefact licenses the artefact's mandatory consequences — an alert rule carries its runbook section, panel and README row; a brief that DEFINES a check states the census it was run against, as a spec's measured basis does; under a hard clock the first wave is the set that can COMPLETE inside the window, never the head of the global order. And an assignment governed by rules that exist only on an unmerged branch waits for the merge, or the brief names the branch and quotes every clause relied on — the relay is the rule.

## The hourly tick

**The coordinator is unpoked.** The tick resumes a stalled payload turn; nothing resumes main's, so `agent-ops.md`'s announcing rule is main's own check at the top of every turn.

Main runs it from an in-session `CronCreate` job — session-only, fires only while main is idle, **expires after seven days**: reinstall it at every restart and every week. Its cron field, like every one-shot read's, is in the process's zone — UTC — never a conversion to the owner's.

1. `ListAgents`, then prove each `interactive` row ALIVE from the row's own tmux target — a row carries no PID and a `Remote Control` row has no local process. The chain, every step from the row and the host: `tmux has-session -t '=<session>'` (quoted — in zsh a bare leading `=` is filename expansion and aborts the line); `tmux list-panes -a -F '#{pane_id}'` contains the row's `%<p>` as a whole line (`grep -x`) (a vanished pane target silently resolves to the session's active pane — assert the pane); `pgrep -P "$(tmux display -p -t %<p> '#{pane_pid}')" -x claude` returns a PID; `ss -xlp` shows `/tmp/cc-socks/<pid>.sock` listening with `pid=<pid>`. Any step failing is DEAD, never idle — `ListAgents` keeps listing a session after its process has exited, and the chain is immune to PID reuse, stale socket files and zombies. A session missing or dead for one tick is tolerated; for two it is reported to the owner.
2. **Poke first.** A payload session that is idle with an open assignment gets a one-line message: what it last declared and a request to continue. This is the whole enforcement mechanism for announced-but-not-started work — a stalled turn resumes on any message.
3. Read git state — branches moved, worktrees, open PRs — and the memo's work-package markers.
4. Post one report to the owner: per session, what it is on (branch / topic / spec) and whether the branch moved since last tick; the backlog's next three items; anything flagged.

## Restart and rename

- A session cannot be renamed by the session; the owner runs `/rename` from its console, at a quiet moment, and tells main.
- After a `claude` binary update the owner exits and resumes each session with no running tasks; names persist, connections re-establish.
- After a workstation restart, `infra/scripts/zcrypto-tmux.zsh` rebuilds the cockpit — one tmux session `zcrypto-main` with the three payload-and-coordinator panes resuming their Claude sessions by ID — and the owner's `zcrypto-zebra` shell; idempotent per TMUX session, so re-running it rebuilds a missing cockpit or zebra and leaves a live one alone — a Claude pane that died inside a live cockpit is NOT rebuilt: kill that tmux session and re-run. Main reinstalls its tick on resume and re-reads the coordination table before assigning anything.

## The payload contract

A payload session, on receiving an assignment: works only in the worktree named; never writes outside the boundary list; never opens a PR, registers a topic, or writes memory — it asks main, except as `## Authorities held only by main` carves out; reports at start, at each commit, when blocked, and at completion, each report carrying branch and commit hash; ends a turn only with its state reported, never with work announced and not begun; reports only what it can see — *I have heard nothing*, never *the owner has not spoken*, which only the coordinator can tell apart; appends its own self-corrections, rule deviations, miscounts, and rule or skill feedback to its inbox `.local/agent-lessons/<session>.jsonl` in the main checkout as they happen — a review or a read included, with `(branchless: <what>)` in the `branch` field.
