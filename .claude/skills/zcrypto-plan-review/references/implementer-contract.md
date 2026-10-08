# Implementer contract — pasted whole into every implementer, fixer and task-reviewer dispatch of the task loop

The dispatch names `model` explicitly, and the brief's trailer line reads `Claude <the model the dispatch passes>` — never "as your system prompt names it", which under a model override names the session's model. No subagents, no agent tools; everything runs as plain blocking commands, nothing backgrounded.

## The tree

- Nothing under a vault-shaped or `*.sops.*` path is read, printed, grepped, diffed, shown at any revision, archived or copied; a file name printed by `-l` is a read. Every search is `git grep -l <name> -- tests infra .claude ':!*vault*' ':!*.sops.*'`; a recursive `grep -r` over `infra/`, a `git archive` or a `cp -r` of `infra/ansible` opens every vault file in it. A scratch tree is a detached worktree (`git worktree add --detach <dir> <rev>`), never a copy or an archive of the repository.
- A host-side block pasted into a page is never called in a plain shell to check its syntax: the block's own function shells out to `sudo` and `docker`, and the call is live. `bash -n` reads it.
- No `ansible-playbook` in any form, `--syntax-check` and `--check` included: this workstation is the fleet host `zcrypto-ops`, and `localhost` is a live venue-facing node. A role is proven through the test helpers' renders.
- A script's options are read from its argparse with `sed -n` or `python -c`, never by running it with `--help` when its argv is a query or a run.
- The dispatch's scratch lives under its own named directory in the scratchpad and is removed before the report; a process the dispatch starts is stopped before the report, by its PID read from the process tree — never by a pattern the stopping command's own argv carries — and the report names the `pgrep` read before and after.

## The tests

- The consumers of a changed file are what `infra/scripts/consumers.sh <path>` prints: its direct readers and the tests that walk the tree (the selector guard, the metric census, the operator-term and internal-token walkers, the count list, the guidance guard), which name no file and so never match a grep for one. Every listed test runs before the commit. An empty direct-reader list is a finding to state in the report, answered by the file's own test or its directory's readers — never by a bare `uv run pytest`, whose full suite is CI's on every push.
- Stage by explicit path, new files first, then the gate: `pre-commit run -a` reads tracked files only, so an untracked test is invisible to it and a clean gate says nothing about it.
- A commit split by file kind is checked in a scratch worktree at each piece's tree before the pieces are committed: a red intermediate commit is a bisect trap the next reader pays for.
- A fixture that sits equally far from the two states the test separates is vacuous: a symmetry noticed at design time is broken before the case is written, never left for the probe to find.

## The probes

- A guard is proven with `infra/scripts/mutate-probe.sh`, one run at a time, each its own tool call issued after the previous verdict is read — never a batch of probe calls in one block, which the harness runs concurrently over one file. A red reading is taken in a detached worktree at the base revision, never by hand-swapping a file in the working tree.
- A `bash -c` probe command's trap names absolute paths.
- A commit message that carries `KILLED`, `SURVIVED` or `control proven` names `mutate-probe` in the same sentence; a pattern a plan quotes is described without the verdict word.
- `infra/scripts/prove-inert.py` gates the claim that a diff is prose-only, never the change itself: a refusal means the commit does not say prose-only, not that the file is left unfixed.

## The record

- Never an amend: a fix is a new commit. A hash, a sha or a trailer in a message is pasted from the command that printed it in the same call, never typed or completed by hand.
- The report file is written whole at the path the dispatch names; the return is status, commits, one test line and concerns.
