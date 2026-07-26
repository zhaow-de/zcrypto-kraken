# Agent operations

Hard-won session lessons; each rule prevents an observed failure.

- **Never guess a path on a fleet host** — read `docs/reference/fleet.md` (roles, paths, mounts, endpoints; pins in `fleet-pins.md`) and the data catalogs first; probe only where the doc is silent, and write what the probe finds back into the doc in the same change.
- **A recorded footgun names the safe alternative in the same sentence** — "don't use the default X" without "use Y at Z" strands the next context at the moment it needs the answer.
- **Before requesting the user's word on an irreversible/production action, sweep the open-topics index + memo for blockers** and present the result with the request — "ready" without the sweep is not ready.
- **Timeout-guard every network-touching command** (`git push/pull/fetch/ls-remote`, every `gh` call): prefix `timeout 20`–`60`, and run it as its own small step — never buried in a long compound command. For CI waits, poll with per-call timeouts instead of one long foreground wait.
- **Never spawn a shell that polls/waits for a background job you started** — the harness re-invokes you when it completes. A genuine wait on external state (a clock boundary, a slow remote pull) goes *inside* the one backgrounded command doing the work, never in a second watcher shell.
- **`pgrep -f` / `pkill -f <pattern>` match their own command line** — bracket one character (`pgrep -f "[p]attern"`) or the guard never goes false / the kill hits itself.
- **A subagent whose final message says it is *waiting* for a backgrounded command is stranded** — its turn ended, the work sits uncommitted. Check `git status`, then resume the **same** agent via SendMessage with numbered foreground steps ending at the commit; never dispatch a fresh twin. A "failed: API error" notification can also be premature — check the tree before re-dispatching.
- **Subagent dispatch prompts say**: run everything as plain blocking commands, background nothing, do not end the turn before the commit exists — and still expect to occasionally resume.
- **Never run two subagents that may write the same worktree concurrently.** Dispatch write-capable agents one at a time, or give each `isolation: "worktree"`. Read-only reviewers may run in parallel with each other, but not alongside a writer — and a reviewer permitted to mutate-and-restore is a writer.
- **A mutation harness seeds from `git archive <sha>`, never `cp -a` the working tree.**
- **Never mutate-and-restore in a worktree carrying uncommitted work** — `git checkout -- <file>` restores the *committed* state, silently destroying the uncommitted changes. Commit first, or run the probe in a `git archive` sandbox.
- **Chain history-rewriting git commands one per call, never compounded** — verify each step's effect before issuing the next.
- **A count derived by arithmetic is not a measured count** — `total_a - total_b` is the set difference only when the sets nest. Measure the set.
- **Python `str.replace` edits silently no-op on a missed match** — `assert old in s` (or verify the output) every time.
- **Correct a durable doc by rewriting the narrative in place, never by appending retraction bullets** — the uncorrected story reads first, and more confidently than the correction below it; the file must read correctly cold.
- **A number quoted from a reviewer's or subagent's report is unmeasured until you reproduce it** against the source data, at full precision.
- **An empty filtered query is not an absent event** — require a positive trace before concluding nothing happened; validate the filter before trusting its emptiness.
- **Never narrate a wall-clock time or elapsed duration you did not just measure** — run `date`/`uptime` first.
