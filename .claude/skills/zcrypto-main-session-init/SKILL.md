---
name: zcrypto-main-session-init
description: Start or resume the coordinator session — load the multi-agent protocol, rebuild the coordination table, install the hourly tick when the owner asks for it
disable-model-invocation: true
---

# zcrypto-main-session-init

Run this at the start of every `zcrypto-marco` session (the coordinator session) and after every resume. The protocol itself is `docs/reference/multi-agent-protocol.md` — read it first; this skill is only the startup sequence and the tick's text.

## Startup

1. Read `docs/reference/multi-agent-protocol.md`, then `.local/memo.md` (the backlog authority — `.claude/skills/zcrypto-grooming/references/memo-protocol.md` governs its edits), then `.local/coordination.md` (the session table; create it from the template below if absent).
2. `ListAgents`. Reconcile the table against what is actually alive: names, busy/idle, and any rename the owner reported. Then `CronList`, reconciled against the table's `tick installed:` line — the job lives only in the session that created it and is gone when that process exits, so a resume can carry a table that names a job the listing no longer holds: correct that line to `NONE (lost at <event>)` in the same edit, and re-install only through step 3, on the owner's word.
3. Install the tick only on the owner's word — it is off by default, and the coordination table's `tick installed` line records which: `CronCreate` with `cron: "7 * * * *"`, `recurring: true`, and the prompt below verbatim. A cron field is in the PROCESS's zone — UTC on this workstation (`date -u` and `date` agree), whatever zone the owner reads — so a one-shot read is written in UTC and never converted; every spoken time keeps its `Z`. Record the job id in the coordination table. It expires after seven days and does not outlive the session that created it — the table's `tick installed` line is the reminder, and step 2's `CronList` reconcile is what catches the loss.
4. Report the reconciled table to the owner in one message, and wait for an instruction. Main assigns nothing on its own initiative at startup.

## The tick prompt

> Hourly tick. (1) `ListAgents`, then prove each `interactive` row ALIVE from the row's own tmux target `<session>:@<w>.%<p>` — a row carries no PID, and a `Remote Control` row has no local process: `tmux has-session -t '=<session>'` (quoted — in zsh a bare leading `=` is filename expansion and aborts the line), then `tmux list-panes -a -F '#{pane_id}'` must contain `%<p>` as a whole line (`grep -x`; a substring match hits every pane sharing a prefix) (a vanished pane target silently resolves to the session's active pane, so assert the pane), then `pgrep -P "$(tmux display -p -t %<p> '#{pane_pid}')" -x claude` must return a PID, then `ss -xlp` must show `/tmp/cc-socks/<that pid>.sock` listening with `pid=<that pid>`. Any step failing is DEAD, never idle — `ListAgents` keeps listing a session after its process has exited. A `Remote Control` row, having no tmux target, is judged by its own online/offline marker: an offline row is DEAD rather than idle, and a row carrying both a marker and a tmux target is judged by the tmux ladder. A name `ListAgents` lists with no row in the table is reported in (4), never reconciled away. A session missing or dead for a second consecutive tick is flagged. (2) For every payload session that is idle with an open assignment in `.local/coordination.md`, send one line: what it last declared, and continue. (3) `timeout 60 git fetch --all --prune` first, then read the tip that would actually merge — the local ref where one exists, the remote-tracking ref otherwise — plus `git worktree list`, `timeout 60 gh pr list --state open`, and the memo's work-package markers (`infra/scripts/sweep.sh --control '^## WORK-ITEMS QUEUE' -e '^#### WP'` — a tick where the memo groups nothing is a clean, and the control is what makes that clean evidence: anchored, it is the memo's own section heading, which no tracked file carries, while the unanchored string is prose in tracked files, this one included. rc 2 then says the memo is absent or its headings have drifted from the canonical four; whether `.local/` was in the list is the separate door, the `no <path>/.local` line on stderr); compare the table's topic columns pairwise — a guard, file or property named on two branches is a collision: flag it in the report, to be routed to one owner after the tick. A flag states what was READ (a branch tip's date, a file's absence), never what it implies; the topic that owns a routine is read before its silence is flagged. (4) Post one report to the owner: per session — branch / topic / spec, and whether the branch moved since the last tick; the backlog's next three items; anything flagged. A payload session that is alive and holds no subject is itself a flag, reported as free with the backlog's head beside it: the tick reads what is blocked, and a session with nothing open declares nothing, so it is invisible unless the report names it. Update the table's `last tick` and each session's `last report` line. Do not assign, merge, or write the memo inside the tick. This shell is zsh: spell every loop argument out or iterate an array (an unquoted `$var` is one word, and a descending `{a..b}` runs backwards), and a pairwise check prints its expected comparison count `n·(n−1)/2` and asserts rc 0 before its results are read — an error's one-line output satisfies a one-line success test.

## Coordination table template

```markdown
# Coordination — session table (gitignored, main writes only)

Live state only: a row is the session's current state and a block below the table lives while its assignment is in flight; history is the memo's.

**Standing rulings**
- <one line per ruling of the owner's that binds assignments; none yet>

tick installed: NONE
last tick: —

| session | status | branch | topic / spec | warm context | last report | session URLs |
|---|---|---|---|---|---|---|
| zcrypto-alex | idle | — | — | — | — | — |
| zcrypto-bravo | idle | — | — | — | — | — |
| zcrypto-zebra | owner's — assigned only when the owner names it in | — | — | — | — | — |

Memo chain carried by main: <sha256> · <lines> · <bytes> (<ISO-8601 UTC> — <coverage>)
```

`tick installed:` is `NONE` — `NONE (lost at <event>)` after step 2 finds the id gone — until step 3 installs the job, and then `<ISO-8601 UTC> · job id: <id> · expires: <ISO-8601 UTC>`. The chain line is filled from the memo as read — `sha256sum .local/memo.md | cut -c1-64`, `wc -l`, `wc -c` — and rewritten after every memo write; the protocol's count over it is 1 when they match.

`session URLs` is a **list, appended, never replaced**: one session holds several `https://claude.ai/code/session_…` URLs over its life, so attributing a commit to a session means matching every URL the session has held. A payload session names its URL in its start report; after the fact it is read off the branch's commits — the distinct values, less those `zcrypto-marco`'s own row holds, since `open-pr` Step 4's change-index row and any fix the coordinator lands on the branch carry the coordinator's URL and the tip alone often reads as it: `git log --format='%(trailers:key=Claude-Session,valueonly)' develop..<branch> | grep . | grep -vF -e <URL> | sort | uniq -c | sort -rn`, one `-e` per URL in `zcrypto-marco`'s row, each value printed with its commit count. An empty result is a fact, not a miss: the session ran with Remote Control off, and a session without it writes no trailer. Where two payload sessions worked one branch, nothing on it says which URL is whose — the cell takes the values the count puts first, the dominant author's, since a cell that may be wrong serves a reader better than a confident wrong one. The reconcile in step 2 appends a URL the list does not already hold. No rule hangs on it.
