# Implementer contract

No subagents, no agent tools; everything runs as plain blocking commands, nothing backgrounded.

## The tree

- Nothing under a vault-shaped path — a pathspec of `VAULT_EXCLUDES` in `infra/scripts/consumers.sh` — is read, printed, grepped, diffed, shown at any revision, archived or copied; a file name printed by `-l` is a read. Every search is `git grep -l <pattern> -- <paths>` with those pathspecs; a recursive `grep -r` over `infra/`, a `git archive` or a `cp -r` of `infra/ansible` opens every vault file. A scratch tree is a detached worktree (`git worktree add --detach <dir> <rev>`), never a copy or an archive of the repository.
- A host-side block pasted into a page is never called in a plain shell to check its syntax: the block's own function shells out to `sudo` and `docker`, and the call is live. `bash -n` reads it.
- No `ansible-playbook` run that executes tasks or connects to a host, `--check` included: this workstation is the fleet host `zcrypto-ops`, and `localhost` is a live venue-facing node. A role is proven through the test helpers' renders; the commit gate's ansible-lint syntax check parses only and is allowed.
- A script's options are read from its argparse with `sed -n` or `python -c`, never by running it with `--help` when its argv is a query or a run.
- The dispatch's scratch lives under the worktree's `.tmp/<role>/`, its own directory, pytest's through `--basetemp=.tmp/<role>/pt`, never the session's shared scratchpad, and the dispatch removes only what it created there before the report; a process the dispatch starts is stopped before the report, by its PID read from the process tree — never by a pattern the stopping command's own argv carries — and the report names the `pgrep` read before and after.
- No network call: no `git fetch` or `git pull` (a `--dry-run` fetch contacts the remote all the same), no `gh`, no endpoint. The merge base is the local `origin/develop`, which the controller fetched before the dispatch; a check that wants a fresher ref reports that instead.

## The tests

- Before each commit, run the tests `infra/scripts/consumers.sh --direct <path>` lists for each changed file and the file's own test; a code file with none listed runs its own test, the empty list going in the report — the list is held in `T` and `pytest` runs only under its test, `[ -n "$T" ] && uv run pytest $T`, because an empty `$T` runs the whole suite. Per commit, `-m "not slow"`. The tree-walker union, `consumers.sh <path>` without `--direct`, runs once over the branch as the last step before its push, after its reads and folds, a `slow` case (`tests/slow-cases.txt`) only where its file is a `--direct` reader of the branch's changes; `tests/conftest.py`'s run ledger deselects a slow case already passed on the branch until a file its test names changes.
- Stage by explicit path, new files first, then the gate: `pre-commit run -a` reads tracked files only, so an untracked test is invisible to it and a clean gate says nothing about it.
- A commit split by file kind is checked in a scratch worktree at each piece's tree before the pieces are committed when a piece changes code or tests: a red intermediate commit is a bisect trap the next reader pays for.
- A fixture that sits equally far from the two states the test separates is vacuous: a symmetry noticed at design time is broken before the case is written, never left for the probe to find.

## The probes

- A guard is probed on a `full` tier (`infra/scripts/tier.py`) through its own `-k` case, on `light` one probe per new guard file; never through a `slow` case, the commit recording `probe skipped: slow case`.
- A red reading is taken in a detached worktree at the base revision, never by hand-swapping a file in the working tree.
- A `bash -c` probe command's trap names absolute paths.
- A pattern a plan quotes is described in a commit message without the verdict words `KILLED`, `SURVIVED` or `control proven`.
- `infra/scripts/prove-inert.py` gates the claim that a diff is prose-only, never the change itself: a refusal means the commit does not say prose-only, not that the file is left unfixed.

## The record

- Never an amend: a fix is a new commit. A hash, a sha or a trailer in a message is pasted from the command that printed it in the same call, never typed or completed by hand.
- The report is written whole at the path the dispatch names, or, for an implementer in its own worktree, returned as the text; the return is status, commits, one test line and concerns.
