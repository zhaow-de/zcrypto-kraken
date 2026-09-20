---
name: merge-pr
description: Use when a reviewed pull request is ready to merge and the local clone needs cleanup afterward — e.g. "merge PR #60 and clean up". Merge-commit only (never squash or rebase); Dependabot PRs are handled by the dependabot skill instead.
allowed-tools: Bash(git status:*), Bash(git checkout:*), Bash(git pull:*), Bash(git branch:*), Bash(git ls-remote:*), Bash(git push:*), Bash(git fetch:*), Bash(gh pr:*), Bash(uv run python infra/scripts/merge-gate.py:*)
---

# merge-pr

## Overview

Merging a PR is a shared, hard-to-reverse action: gate it on verification first, then clean up local state safely.

PRs handled by this skill **always merge with a merge commit** (`--merge`) — never squash, never rebase. (The one deliberate exception in this repo is Dependabot PRs, which the `dependabot` skill squash-merges so each bump lands as a single commit — they are not handled here.)

## When to use

- The user confirms a PR is reviewed/ready and asks to merge it and/or clean up local branches.
- Finishing a Claude-authored PR after the user's review.

**Not for:** opening/creating PRs; deciding *how* to finish a branch (see superpowers:finishing-a-development-branch); merging into `main` (release-only — use the `/release` skill).

## Step 1 — Identify the PR

```bash
gh pr view <number> --json number,headRefName,baseRefName,state,mergeable,mergeStateStatus,reviewDecision,isDraft,statusCheckRollup,body,headRefOid
```

(Omit `<number>` to use the current branch's PR.) Record `number`, `headRefName`, `baseRefName`, and the gate fields below.

Base correctness (`develop`, never `main`) is the Step-2 gate's first check.

## Step 2 — The merge gate (STOP if ANY fails)

GitHub has no single ready-to-merge field; readiness is spread across several fields. Run the evaluator — it fetches the Step 1 fields itself, reads the head commit from the REST API only when the read line and the head differ, and prints `GATE PASSED` or lists every failing gate (`tests/test_merge_gate.py` drives every arm):

```bash
uv run python infra/scripts/merge-gate.py <number>
```

What each gate covers:

1. **`state == "OPEN"`** and **`isDraft == false`** — not already merged/closed, not a draft.
2. **`mergeable == "MERGEABLE"`** — GitHub computed a clean (conflict-free) merge. `CONFLICTING` is a hard stop; `UNKNOWN` means GitHub is still computing — wait a few seconds and re-run (the gate refuses it).
3. **`mergeStateStatus != "BLOCKED"`** — `BLOCKED` means branch protection is unsatisfied (required review missing or a required check failing). `CLEAN`, `UNSTABLE`, `BEHIND`, and `HAS_HOOKS` are all fine for a merge commit (being behind `develop` is reconciled by the merge; non-required checks don't block).
4. **`reviewDecision != "CHANGES_REQUESTED"`** — if reviews aren't required by the repo, `reviewDecision` comes back empty and the user's go-ahead (why this skill was invoked) is the approval. If reviews ARE required, gate 3 (`BLOCKED`) enforces them.
5. **No failing and no still-running CI** — the gate blocks both: `develop` requires the **`Full test suite`** check (`.github/settings.yml`), so GitHub now refuses a red or unfinished run by itself — this evaluator is defense in depth, not the only gate, and it still catches what GitHub does not: an unchecked checklist, a wrong base, a draft. Do not relax it on the strength of the branch rule; the rule lives in a file one PR can change. `coverage.yml` runs the suite on **`pull_request` into `develop`/`main`** (only — no `push` trigger, so no redundant post-merge run), and a failing suite fails that check; an empty rollup means it has not registered yet, which is also a wait. CI is the only place the whole suite runs (`.github/workflows/coverage.yml`; the `Full test suite` context in `.github/settings.yml`).
6. **Checklist complete** — the PR description has no unchecked task-list item, `- [ ]`, `* [ ]` or `1. [ ]`, read as a reader sees the page: a marker in a code span or a fenced block is text, a box inside `<details>` or a quote is still a box (GitHub does not enforce these, so the gate parses the body).
7. **The whole-branch read covers the head** — the body's `Read before push by: <model> at <sha>` line names a model at the floor and the PR head; a commit pushed after the read takes a delta read (`re-review`) or a re-read (`review`) with the line updated. A head that is the read's tip rebased onto a moved base passes when `git merge-tree` of the read onto the new base gives the head's tree, or differs from it only in `docs/reference/change-index.md` and `docs/open-topics/README.md`, the two rendered files a rebase resolves by hand — every patch unchanged, no delta to read. The line's contract — the floor, the two heads admitted past the named tip, the substitution — is `open-pr`'s Body item 3, which writes it.
8. **The `ops-journal` month PR is exempt from gate 7** — its README declares the month PR outside the pre-push read; a head branch named `ops-journal` whose every file is under `docs/reference/ops-journal/` skips the read-line arm; one carrying any other file takes every arm, floor included.
9. **Every commit of the branch states its ambient growth** — the gate fetches the base and head branches and runs `infra/scripts/guidance-guard.py --range <merge-base>..<head>`, which judges each non-merge commit against its parent: the check the commit-msg hook cannot make under a rewrite, where a reworded amend or a squash lands a lost or doubled `Ambient grows by` line. A branch whose commits predate the guard carries no lines: the mode names each of them that grows the set, and the author rewords it with its line before the merge; a universal the mode refuses at an intermediate commit takes a rebase that edits that commit. The same walk refuses a non-merge commit that mixes claude-kind files with another kind: the `staged-kind` hook sees the index, and an amend lands the mix past it. A head branch gone from origin, or no merge base, is reported as this arm's failure, never a crash.
10. **A keyed branch owes its change-index row** — when the head branch name carries an `iter-NNN`, a 5-digit spec serial or a `T<NNNN>` (the grammar `test_every_keyed_merge_on_develop_has_a_row` reads), the gate refuses unless `docs/reference/change-index.md` holds a `| #<number> ` row. That test reads the merge subject's branch name and so can only fail on develop AFTER the merge, when this PR's own CI has long been green. The arm reads the index **from the checkout**, so run the gate from the branch that carries the row — from `develop`, or with a `<number>` that is not the current branch's, it refuses a PR whose row is simply not in this working tree.

**If any gate fails:** report which one and why, ask the user to resolve it manually (update the branch, fix CI, get the review, check the boxes), then **STOP**. Do not merge.

## Step 2b — Read the checked boxes (STOP on a false claim)

Gate 6 reads a box's state, never its text: a `- [x]` checked with a false `N/A` reason passes it. For every checked box whose claim no gate arm reads, verify the claim against the branch, the `N/A` reason above all — its condition is the whole claim:

- **Change-index row.** Gate 10 reads a key in the branch name only; a key in the title or the body's `## Spec / Plan` section owes a row by the same grammar (`open-pr` Step 4): `gh pr view <number> --json title -q .title | grep -oE '\biter-[0-9]{1,3}\b|\b[0-9]{5}\b|\b[Tt][0-9]{4}\b'`, and the section read for a serial or a topic; then `grep -n "^| #<number> " docs/reference/change-index.md`. A key without a row, or an `N/A` beside a key, is a STOP.
- **README `## Usage`.** `gh pr diff <number> --name-only | grep '^cli/'` — a CLI file in the diff with the box checked as not applicable takes a read of `README.md`'s `## Usage` against the option change.
- **Tests pass.** Gate 5 reads the run itself; nothing to add.

## Step 3 — Merge

```bash
gh pr merge <number> --merge --delete-branch
```

`--merge` keeps per-commit history and the `Co-Authored-By:` trailers.

## Step 4 — Sync develop (never through a dirty worktree)

```bash
git status --porcelain
git branch --show-current
```

On `develop` with a clean tree, `git pull --ff-only`; not a fast-forward is a STOP (never a local merge commit). On `<headRefName>` with a clean tree, `git checkout develop` first — that branch is yours, no peer holds it. Otherwise — a dirty tree, or a branch a peer session may hold in the shared checkout — do not switch; move the ref without touching the worktree:

```bash
git fetch origin develop:develop
```

A refspec without `+` fast-forwards a branch that is not checked out and refuses anything else, the current branch included: a refusal is a STOP and a report, never a `+` or a `--force`. This line stands in wherever the pull cannot run — never nothing: `git fetch --all --prune` alone advances `origin/develop` and leaves the local `develop` at the pre-merge commit, the red one the PR may have existed to fix.

## Step 5 — Delete the local branch

```bash
git branch -d <headRefName>
```

Run git from the repo root. `-d` needs only that the current branch is another one; when Step 4 left you on `<headRefName>` (a dirty tree), the delete waits with the switch. Because the PR merged with a merge commit (Step 3), the branch is fully integrated and `-d` succeeds. (If `-d` ever errors "not fully merged" **and** the PR shows merged **and** the remote branch is gone, the work IS integrated — `git branch -D <headRefName>` is then safe.)

## Step 6 — Confirm the remote branch is gone

```bash
git ls-remote --heads origin <headRefName>
```

Empty output = deleted (expected from Step 3). If it still prints a ref, **warn** the user, then delete it:

```bash
git push origin --delete <headRefName>
```

## Step 7 — Fetch all remotes + prune

```bash
git fetch --all --prune
```

## Report

Summarize: PR merged (or which gate or box stopped you), develop synced (pull, or the `develop:develop` fetch, or the refusal that deferred it), local + remote branch deleted, prune done.
