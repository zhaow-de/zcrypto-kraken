---
name: dependabot
description: Manage Dependabot dependency-update PRs — list, check out, rebase onto develop, run uv tests + ruff, auto-fix lint/format, push, wait for CI, merge with squash
disable-model-invocation: true
allowed-tools: Bash(git fetch:*), Bash(git checkout:*), Bash(git rebase:*), Bash(git status:*), Bash(git stash:*), Bash(git push:*), Bash(git add:*), Bash(git commit:*), Bash(git log:*), Bash(git branch:*), Bash(git rev-parse:*), Bash(git merge-base:*), Bash(gh pr:*), Bash(gh api:*), Bash(timeout:*), Bash(uv:*), Bash(python3:*), Bash(sleep:*), Bash(date:*), Bash(echo:*), Bash(grep:*), Bash(head:*), Bash(cut:*), Read, Glob, Grep, Edit, Write, AskUserQuestion
---

# Dependabot PR Management

Autonomously process Dependabot dependency-update PRs in this repo: check out, rebase onto `develop`, validate, auto-fix routine issues, push, wait for CI, merge.

## Context

- Current branch: !`git branch --show-current`
- Working tree: !`git status --porcelain || echo "clean"`
- All open PRs (filter for `dependabot/` head branches): !`gh pr list`

## Repo specifics

- **Dependabot is configured** at `.github/dependabot.yml` with `target-branch: "develop"` on every ecosystem, so Dependabot opens PRs against **`develop`** (the integration branch) — never `main`, which is release-only. If a Dependabot PR you see here targets `main`, stop and report — that `target-branch` entry has drifted or been removed.
- Pre-commit hooks (`.pre-commit-config.yaml` at repo root) auto-format on every `git commit` (ruff-format, trailing whitespace, etc.).
- This skill processes every ecosystem `.github/dependabot.yml` lists, a `nautilus-trader` PR excepted (step 4).

## Workflow

### Phase 1 — Setup & discovery

1. **Save current state**: stash uncommitted changes (including untracked) so the cleanup phase can restore them:
   ```bash
   git stash push -m "dependabot-skill-temp" --include-untracked 2>/dev/null || true
   ```

2. **Remember the original branch** so the cleanup phase can return to it:
   ```bash
   ORIGINAL_BRANCH=$(git branch --show-current)
   ```

3. **Sort** the Dependabot PRs from context by priority: minor/patch first, major last. Classify each PR by parsing the `from <X> to <Y>` versions in its title and comparing the major components. Within a priority class, oldest first.

4. **Report plan**: list the PRs to be processed, in the chosen order, with their base branch noted (must be `develop` — see "Repo specifics" above). A `nautilus-trader` PR stays out of the plan, open as the reminder of a new build, and is reported under Skipped: its CI stays red until the build's attended order-semantics pass lands with the bump (`infra/runbooks/order-semantics-verification.md` §1.6), and an edit of `cli/engine/order-semantics-verified.json` is never this skill's to make.

### Phase 2 — Process each PR (loop)

For each PR step 4 plans, in order:

#### 2a. Check out + rebase onto develop

```bash
git fetch origin
gh pr checkout <number>
git rebase origin/develop
```

If the rebase produces conflicts:
- Attempt auto-resolution for simple conflicts (e.g. `uv.lock`: take the Dependabot side since it represents the upgraded lock state).
- Anything non-trivial → **stop and ask** the user via `AskUserQuestion` with the conflict diff.

> **Note:** pushing the rebased branch makes Dependabot stop managing this PR. That is fine — the skill merges it immediately after.

#### 2b. Local validation

Run in this order; stop on the first failure (so the auto-fix step in 2c knows what to attack). **This local full run stays** — a lockfile change reaches every test, including the data-gated ones CI cannot run at all:

```bash
uv run ruff check
uv run ruff format --check
uv run pytest -q
```

(We do not have a separate type-checker; lint + format-check + tests is the full local gate.)

#### 2c. Auto-fix (if validation fails)

| Failure | Auto-action | Max attempts |
|---|---|---|
| Lint (`ruff check` exits non-zero) | `uv run ruff check --fix` then re-run `ruff check`; analyze any remaining errors and patch manually if obvious. | 3 |
| Format (`ruff format --check` exits non-zero) | `uv run ruff format` (rewrites in place). | 1 |
| Tests fail | Read the traceback; if it is an obvious upgrade-shaped issue (renamed import, changed signature, deprecated kwarg), patch it. Re-run `pytest`. | 3 |

After the cap: **stop and ask** the user. Don't silently keep retrying.

Commit any fixes with our project's commit convention — Conventional Commits, one commit-type's file kind per commit:

```bash
# Stage by EXPLICIT PATH — never -A/-u: name exactly the files 2c edited.
git add <paths the auto-fix touched>
git commit -m "$(cat <<'EOF'
fix(config): resolve <symptom> after <package> upgrade

Co-Authored-By: <actual executing model> <noreply@anthropic.com>
EOF
)"
```

If pre-commit reformats during the commit, re-stage and re-commit (NEVER `--no-verify`).

A branch that carries a 2c fix commit is read before the push by a different agent from the author — the `pre-review` workflow over the fix range's prose and message claims, then `review` over the range, since a fix that has had no read yet owes the wide one and `re-review` reads only a range a read already asked to fix — and the read is edited into the PR body as `Read before push by: <model> at <sha>` (`open-pr`'s Body item 3 is the line's contract): §2d's `gh pr merge --squash` bypasses `infra/scripts/merge-gate.py`, so that line is the read's only record. A PR with no fix commit needs no read.

#### 2d. Push + wait for CI + merge

```bash
# The rebase rewrote history, so the push must be forced (lease-guarded).
git push --force-with-lease origin "$(git branch --show-current)"

# test-suite.yml runs on pull_request into develop/main (dependabot targets develop), so a
# Dependabot PR DOES report a "Full test suite" check — wait for it, and merge only when green.
# The Coveralls upload is fail-on-error: false, so a red "Full test suite" check is never the upload.
#
# Poll the check-runs OF THE PUSHED SHA. **Never `gh pr view --json statusCheckRollup` here** —
# it serves the PREVIOUS head's results after a force push, and §2a force-pushes every PR.
# Allowlist green: only `completed` is decided. A denylist of the pending states lets `waiting` — a job
# held by a deployment-protection rule — read as green.
# **An EMPTY result is pending, never green.** On a freshly force-pushed SHA it means the checks
# have not registered yet; the check fires on every PR (above) and branch protection requires the
# `Full test suite` context, so "this repo runs no checks" is not a state this loop can be in.
# Requiring that run BY NAME is what makes the empty window pending.
# Run this as its OWN command and re-read it every ~45 s — never one long foreground loop —
# then merge in a SEPARATE command only after reading `success`.
SHA=$(git rev-parse HEAD)
# default filter=latest: one run per name
timeout 40 gh api "repos/zhaow-de/zcrypto-kraken/commits/$SHA/check-runs" \
  --jq '[.check_runs[] | {n: .name, s: .status, c: (.conclusion // "")}]' | python3 -c '
import sys, json
# `gh api --jq` writes an error BODY to stdout, and a killed `timeout` writes nothing: both
# parse to something that is not a check-run list, and `r["n"]` over either raises mid-run.
try:
    runs = json.loads(sys.stdin.read())
except ValueError:
    runs = None
if not isinstance(runs, list):
    print("no reading — the call did not return a check-run list; re-read it"); raise SystemExit
REQUIRED = "Full test suite"          # the context branch protection requires on develop
run = next((r for r in runs if r["n"] == REQUIRED), None)
if run is None:
    print("pending (not registered yet)"); raise SystemExit
if run["s"] != "completed":
    print(f"pending ({run["s"]})"); raise SystemExit
print("success" if run["c"] in ("success", "neutral", "skipped") else f"failed ({run["c"]})")
'

# After the poll printed `success`, immediately before the squash, each its own command: the squash
# bypasses infra/scripts/merge-gate.py, so it reads behind itself — a head lacking develop's tip
# squashes onto a tree no suite ran. `rc 0` merges; `rc 1` goes back to §2a — a PR carrying a 2c fix
# commit takes its read again over the rebased range, its `Read before push by:` line updated, before
# the second push — and a second `rc 1` on the same PR stops and asks the user (escalation trigger
# #6); any other answer stops. Unscoped on purpose: the paths whose push builds the engine image stay
# in the one list the merge gate's test holds.
git fetch origin develop
git merge-base --is-ancestor origin/develop HEAD; echo "rc $?"

# Merge ONLY after the poll above printed `success` and the read above printed `rc 0` — re-read both,
# never infer them; an empty check list is pending, not green. No shell conditional here on purpose:
# a fresh shell per command means any `if` would test an unset variable and merely LOOK like a guard.
# Squash so each dependency bump is a single commit on develop (the deliberate exception to
# merge-pr's merge-commit rule); also deletes the dependabot/ head branch.
gh pr merge <number> --squash --delete-branch    # the number step 4 planned, not a variable
# Anything other than `success` stops the merge: a red check is escalation trigger #4, and a check
# still pending 30 minutes after the push is reported as stalled. Never merge on a state you did
# not read.
```

### Phase 3 — Cleanup

```bash
git checkout "$ORIGINAL_BRANCH"
# Pop ONLY this skill's entry: on a clean-tree run Phase 1 saved NOTHING, so a bare
# `git stash pop` would pop the user's own pre-existing stash onto the branch.
ref=$(git stash list | grep -F "dependabot-skill-temp" | head -1 | cut -d: -f1)
[ -n "$ref" ] && git stash pop "$ref"
```

Report a summary:
- ✅ Merged PRs (with number + package)
- ⏭️ Skipped PRs (with reasons — e.g. major-version requiring human review, base branch wrong)
- ❌ Failed PRs (with error details — conflicts, persistent test failures, CI failures)

## User escalation triggers

Only pause for user input when:

1. **Merge conflicts** that aren't trivially auto-resolvable (anything beyond `uv.lock` taking the Dependabot side).
2. **Persistent failures** after the per-issue cap in §2c.
3. **Major-version upgrades** where the changelog mentions breaking changes — surface the upgrade summary and ask before merging.
4. **CI failures unrelated to the PR's changes** (e.g. infra flake, pre-existing test that was passing on develop before this branch was opened).
5. **A PR's base branch is not `develop`** (likely `.github/dependabot.yml` `target-branch` misconfigured — surface and stop).
6. **A second `rc 1` on the same PR** — §2d's read found the head lacking `develop`'s tip after its second rebase: `develop` is moving faster than the loop; surface and stop.

## Notes

- Use `fix(config): …` for auto-fix commits — cross-cutting tooling fixes, not component-specific.
- Prefer separate `uv …` / `git …` lines over composite `(cd X && Y) && Z` commands.
