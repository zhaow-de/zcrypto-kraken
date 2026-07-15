# Agent operations

Hard-won session lessons; each rule prevents an observed failure.

- **Timeout-guard every network-touching command** (`git push/pull/fetch/ls-remote`, every `gh` call): prefix `timeout 20`–`60`, and run it as its own small step — never buried in a long compound command. For CI waits, poll with per-call timeouts instead of one long foreground wait.
- **Never spawn a shell that polls/waits for a background job you started** — the harness re-invokes you when it completes. A genuine wait on external state (a clock boundary, a slow remote pull) goes *inside* the one backgrounded command doing the work, never in a second watcher shell.
- **`pgrep -f` / `pkill -f <pattern>` match their own command line** — bracket one character (`pgrep -f "[p]attern"`) or the guard never goes false / the kill hits itself.
- **A subagent whose final message says it is *waiting* for a backgrounded command is stranded** — its turn ended, the work sits uncommitted. Check `git status`, then resume the **same** agent via SendMessage with numbered foreground steps ending at the commit; never dispatch a fresh twin (two agents once raced on the same files). A "failed: API error" notification can also be premature — check the tree before re-dispatching.
- **Subagent dispatch prompts say**: run everything as plain blocking commands, background nothing, do not end the turn before the commit exists — and still expect to occasionally resume.
- **Python `str.replace` edits silently no-op on a missed match** — `assert old in s` (or verify the output) every time; an unasserted miss once aborted a multi-edit so nothing was written.
