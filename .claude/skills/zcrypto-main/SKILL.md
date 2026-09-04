---
name: zcrypto-main
description: Start or resume the coordinator session — load the multi-agent protocol, rebuild the coordination table, install the hourly tick
disable-model-invocation: true
---

# zcrypto-main

Run this at the start of every `zcrypto-main` session and after every resume. The protocol itself is `docs/reference/multi-agent-protocol.md` — read it first; this skill is only the startup sequence and the tick's text.

## Startup

1. Read `docs/reference/multi-agent-protocol.md`, then `docs/memo.local.md` (the backlog authority — `.claude/skills/zcrypto-grooming/references/memo-protocol.md` governs its edits), then `docs/coordination.local.md` (the session table; create it from the template below if absent).
2. `ListAgents`. Reconcile the table against what is actually alive: names, busy/idle, and any rename the owner reported.
3. Install the tick: `CronCreate` with `cron: "7 * * * *"`, `recurring: true`, and the prompt below verbatim. Record the job id in the coordination table. It expires after seven days — the table's `tick installed` line is the reminder.
4. Report the reconciled table to the owner in one message, and wait for an instruction. Main assigns nothing on its own initiative at startup.

## The tick prompt

> Hourly tick. (1) `ListAgents`, then prove each `interactive` row ALIVE from the row's own tmux target `<session>:@<w>.%<p>` — a row carries no PID, and a `Remote Control` row has no local process: `tmux has-session -t '=<session>'` (quoted — in zsh a bare leading `=` is filename expansion and aborts the line), then `tmux list-panes -a -F '#{pane_id}'` must contain `%<p>` as a whole line (`grep -x`; a substring match hits every pane sharing a prefix) (a vanished pane target silently resolves to the session's active pane, so assert the pane), then `pgrep -P "$(tmux display -p -t %<p> '#{pane_pid}')" -x claude` must return a PID, then `ss -xlp` must show `/tmp/cc-socks/<that pid>.sock` listening with `pid=<that pid>`. Any step failing is DEAD, never idle — `ListAgents` keeps listing a session after its process has exited. A session missing or dead for a second consecutive tick is flagged. (2) For every payload session that is idle with an open assignment in `docs/coordination.local.md`, send one line: what it last declared, and continue. (3) Read `git branch -r`, `git worktree list`, `gh pr list --state open`, and the memo's work-package markers; compare the table's topic columns pairwise — a guard, file or property named on two branches is a collision to route to one owner now. (4) Post one report to the owner: per session — branch / topic / spec, and whether the branch moved since the last tick; the backlog's next three items; anything flagged. Update the table's `last tick` and each session's `last report` line. Do not assign, merge, or write the memo inside the tick.

## Coordination table template

```markdown
# Coordination — session table (gitignored, main writes only)

tick installed: <ISO-8601 UTC> · job id: <id> · expires: <ISO-8601 UTC>
last tick: <ISO-8601 UTC>

| session | status | branch | topic / spec | warm context | last report |
|---|---|---|---|---|---|
| zcrypto-alex | idle | — | — | — | — |
| zcrypto-bravo | idle | — | — | — | — |
| zcrypto-zebra | owner's — never assigned | — | — | — | — |
```
