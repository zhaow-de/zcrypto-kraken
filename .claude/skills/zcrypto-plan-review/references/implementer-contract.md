# Implementer contract

No subagents, no agent tools; everything runs as plain blocking commands, nothing backgrounded.

## The tree

- Nothing under a vault-shaped or `*.sops.*` path is read, printed, grepped, diffed, shown at any revision, archived or copied; a file name printed by `-l` is a read. Every search is `git grep -l <pattern> -- <paths> ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'` — the vault-shaped files are `*vault.yml`, `*.vault`, `*.sops.*`, `*vault-password*` and the vaulted private halves under `infra/ansible/files/`, each opening with `$ANSIBLE_VAULT`; a recursive `grep -r` over `infra/`, a `git archive` or a `cp -r` of `infra/ansible` opens every one of them. A scratch tree is a detached worktree (`git worktree add --detach <dir> <rev>`), never a copy or an archive of the repository.
- A host-side block pasted into a page is never called in a plain shell to check its syntax: the block's own function shells out to `sudo` and `docker`, and the call is live. `bash -n` reads it.
- No `ansible-playbook` in any form, `--syntax-check` and `--check` included: this workstation is the fleet host `zcrypto-ops`, and `localhost` is a live venue-facing node. A role is proven through the test helpers' renders.
- A script's options are read from its argparse with `sed -n` or `python -c`, never by running it with `--help` when its argv is a query or a run.
- The dispatch's scratch lives under its own named directory in the scratchpad and is removed before the report; a process the dispatch starts is stopped before the report, by its PID read from the process tree — never by a pattern the stopping command's own argv carries — and the report names the `pgrep` read before and after.

## The tests

- Before the commit, run every test `infra/scripts/consumers.sh <path>` lists for each changed file; an empty reader list goes in the report, never answered by a bare `uv run pytest`, whose full suite is CI's.
- Stage by explicit path, new files first, then the gate: `pre-commit run -a` reads tracked files only, so an untracked test is invisible to it and a clean gate says nothing about it.
- A commit split by file kind is checked in a scratch worktree at each piece's tree before the pieces are committed: a red intermediate commit is a bisect trap the next reader pays for.
- A fixture that sits equally far from the two states the test separates is vacuous: a symmetry noticed at design time is broken before the case is written, never left for the probe to find.

## The probes

- A red reading is taken in a detached worktree at the base revision, never by hand-swapping a file in the working tree.
- A `bash -c` probe command's trap names absolute paths.
- A pattern a plan quotes is described in a commit message without the verdict words `KILLED`, `SURVIVED` or `control proven`.
- `infra/scripts/prove-inert.py` gates the claim that a diff is prose-only, never the change itself: a refusal means the commit does not say prose-only, not that the file is left unfixed.

## The record

- Never an amend: a fix is a new commit. A hash, a sha or a trailer in a message is pasted from the command that printed it in the same call, never typed or completed by hand.
- The report file is written whole at the path the dispatch names; the return is status, commits, one test line and concerns.
