# Agent operations

Hard-won session lessons; each rule prevents an observed failure.

- **Timeout-guard every network-touching command** (`git push/pull/fetch/ls-remote`, every `gh` call): prefix `timeout 20`–`60`, and run it as its own small step — never buried in a long compound command. For CI waits, poll with per-call timeouts instead of one long foreground wait.
- **Never spawn a shell that polls/waits for a background job you started** — the harness re-invokes you when it completes. A genuine wait on external state (a clock boundary, a slow remote pull) goes *inside* the one backgrounded command doing the work, never in a second watcher shell.
- **`pgrep -f` / `pkill -f <pattern>` match their own command line** — bracket one character (`pgrep -f "[p]attern"`) or the guard never goes false / the kill hits itself.
- **A subagent whose final message says it is *waiting* for a backgrounded command is stranded** — its turn ended, the work sits uncommitted. Check `git status`, then resume the **same** agent via SendMessage with numbered foreground steps ending at the commit; never dispatch a fresh twin (two agents once raced on the same files). A "failed: API error" notification can also be premature — check the tree before re-dispatching.
- **Subagent dispatch prompts say**: run everything as plain blocking commands, background nothing, do not end the turn before the commit exists — and still expect to occasionally resume.
- **Never run two subagents that may write the same worktree concurrently.** Dispatch write-capable agents one at a time, or give each `isolation: "worktree"`. Read-only reviewers may run in parallel with each other, but not alongside a writer — and a reviewer permitted to mutate-and-restore is a writer.
- **A mutation harness seeds from `git archive <sha>`, never `cp -a` the working tree.**
- **Chain history-rewriting git commands one per call, never compounded** — verify each step's effect before issuing the next.
- **A count derived by arithmetic is not a measured count** — `total_a - total_b` is the set difference only when the sets nest. Measure the set.
- **Python `str.replace` edits silently no-op on a missed match** — `assert old in s` (or verify the output) every time; an unasserted miss once aborted a multi-edit so nothing was written.
