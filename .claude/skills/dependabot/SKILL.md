---
name: dependabot
description: Manage Dependabot dependency-update PRs — list, check out, rebase onto develop, run uv tests + ruff, auto-fix lint/format, push, wait for CI, merge with squash
disable-model-invocation: true
allowed-tools: Bash(git fetch:*), Bash(git checkout:*), Bash(git rebase:*), Bash(git status:*), Bash(git stash:*), Bash(git push:*), Bash(git add:*), Bash(git commit:*), Bash(git log:*), Bash(git branch:*), Bash(gh pr:*), Bash(uv:*), Bash(python3:*), Bash(sleep:*), Bash(date:*), Bash(echo:*), Read, Glob, Grep, Edit, Write, AskUserQuestion
---

# Dependabot PR Management

Autonomously process Dependabot dependency-update PRs in this repo: check out, rebase onto `develop`, validate, auto-fix routine issues, push, wait for CI, merge.

## Context

- Current branch: !`git branch --show-current`
- Working tree: !`git status --porcelain || echo "clean"`
- All open PRs (filter for `dependabot/` head branches): !`gh pr list`

## Repo specifics

- **Dependabot is configured** at `.github/dependabot.yml` with `target-branch: "develop"` on every ecosystem, so Dependabot opens PRs against **`develop`** (the integration branch) — never `main` (which is release-only per `.claude/rules/branch-workflow.md`). If a Dependabot PR you see here targets `main`, stop and report — that `target-branch` entry has drifted or been removed.
- The Python application lives at the **repo root** (flat layout). Tests, lint, and the lockfile (`uv.lock`) all live at the root; run `uv` commands from the repo root.
- Pre-commit hooks (`.pre-commit-config.yaml` at repo root) auto-format on every `git commit` (ruff-format, trailing whitespace, etc.). A push after a hook-driven amend may need re-staging — the loop handles it.
- Configured ecosystems: `uv` (updates `pyproject.toml` + `uv.lock`), `github-actions` (updates `.github/workflows/*`), and `pre-commit` (updates `.pre-commit-config.yaml`). This skill processes any `dependabot/` PR regardless of ecosystem.

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

3. **Sort** the Dependabot PRs from context by priority: minor/patch first, major last. Classify each PR by parsing the `from <X> to <Y>` versions in its title and comparing the major components. Within a priority class, oldest first (longest-pending PRs likely need the most rebasing).

4. **Report plan**: list the PRs to be processed, in the chosen order, with their base branch noted (must be `develop` — see "Repo specifics" above).

### Phase 2 — Process each PR (loop)

For each Dependabot PR in the sorted order:

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

Run in this order; stop on the first failure (so the auto-fix step in 2c knows what to attack). **This local full run stays, and is not the duplicate `CLAUDE.md` retires** — a lockfile change reaches every test, including the data-gated ones CI cannot run at all:

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

Commit any fixes with our project's commit convention (per `.claude/rules/commit-messages.md`):

```bash
# Stage by EXPLICIT PATH — never -A/-u (commit-messages.md): name exactly the files 2c edited.
git add <paths the auto-fix touched>
git commit -m "$(cat <<'EOF'
fix(config): resolve <symptom> after <package> upgrade

Co-Authored-By: <actual executing model> <noreply@anthropic.com>
EOF
)"
```

If pre-commit reformats during the commit, re-stage and re-commit (NEVER `--no-verify`).

Before pushing, dispatch a review subagent on the fix commit and amend its `Reviewed-by:` trailer — mandatory for every Claude-authored commit, no trivial-fix exception (`.claude/rules/commit-messages.md`).

#### 2d. Push + wait for CI + merge

```bash
# The rebase rewrote history, so the push must be forced (lease-guarded).
git push --force-with-lease origin "$(git branch --show-current)"

# Identify the PR number for this branch (or use the number already in the sorted list)
PR_NUMBER=<the number for this PR>

# coverage.yml now runs on pull_request into develop/main (dependabot targets develop), so a
# Dependabot PR DOES report a "Full test suite" check — wait for it, and merge only when green.
# coverage.yml sets fail-on-error: false on the Coveralls upload step, so a red "Full
# test suite" check is always a real pytest failure — never an upload/secrets artifact.
# Poll with SHORT, per-call-timeout commands re-issued until resolution or ~10 min of
# budget is spent — never one long foreground while-loop (agent-ops.md): run the block
# below as its OWN command, read the state, and repeat after ~30 s if still pending.
state=$(timeout 30 gh pr view "$PR_NUMBER" --json statusCheckRollup | python3 -c '
import sys, json
rollup = (json.load(sys.stdin) or {}).get("statusCheckRollup") or []
if not rollup:
    print("none"); raise SystemExit
def cls(item):
    c = (item.get("conclusion") or item.get("state") or "").upper()
    if c in ("FAILURE", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE", "ERROR"):
        return "failed"
    if c in ("SUCCESS", "NEUTRAL", "SKIPPED"):
        return "success"
    return "pending"
states = {cls(i) for i in rollup}
print("failed" if "failed" in states else "pending" if "pending" in states else "success")
')

# Merge only when CI passed or reported no checks. On a failure — or when the
# 10-minute deadline expires with CI still pending — STOP and ask the user
# (escalation trigger #4); never merge a red or unfinished PR into develop.
if [ "$state" = "success" ] || [ "$state" = "none" ]; then
    # Squash so each dependency bump is a single commit on develop (the deliberate
    # exception to merge-pr's merge-commit rule); also deletes the dependabot/ head branch.
    gh pr merge "$PR_NUMBER" --squash --delete-branch
else
    echo "CI state is '$state' (failing, or still pending after 10 min) — skipping merge; surface this PR to the user and stop."
fi
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

## Key commands reference

```bash
# List all open PRs (filter for dependabot/ head branches in the output)
gh pr list

# View one PR's full state including check rollup, head branch, and title
gh pr view <number> --json statusCheckRollup,headRefName,baseRefName,title

# Check out a PR's head branch by number
gh pr checkout <number>

# Merge with squash + delete head branch
gh pr merge <number> --squash --delete-branch

# CI status snapshot (one-off)
# Per-item alternation — `[.statusCheckRollup[].conclusion // ...state]` collects ALL non-null
# conclusions first and only falls back when there are NONE, hiding every pending item.
gh pr view <number> --json statusCheckRollup -q '[.statusCheckRollup[] | .conclusion // .state]'
```

## Notes

- **`main` is PR-only** (branch protection enforces); it advances only via `/release`. Dependabot PRs target `develop`.
- Use `fix(config): …` for auto-fix commits — cross-cutting tooling fixes, not component-specific.
- Prefer separate `uv …` / `git …` lines over composite `(cd X && Y) && Z` commands.
