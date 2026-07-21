# Commit message convention

[Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/): `<type>(<scope>)<!>: <subject>` — types `feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore` `revert` plus **`claude`** (any change to `CLAUDE.md` or `.claude/` — never `docs`). Scope: the snake_case component, or `config`/`build` for cross-cutting. Subject: imperative, lowercase, no trailing period. No `iter-N` tags in commit subjects — that belongs only in PR titles.

Breaking changes: append `!` after the scope (preferred). A descriptive footer must use the **hyphenated** token `BREAKING-CHANGE:` — the space form is not a valid git trailer, and when it shares the footer block with `Co-Authored-By:` git drops the whole block, silently losing the co-author. Commitizen bumps MAJOR for either spelling.

## Trailers

- Every Claude-authored commit ends `Co-Authored-By: <the ACTUAL authoring model> <noreply@anthropic.com>` — last line, blank-separated from the body; a subagent credits its **own** model (verify against the dispatched model; dispatch prompts never hardcode a version).
- **Review before push is mandatory, and the reviewer is a DIFFERENT agent from the author** — an implementer's commit is reviewed by a subagent other than the implementer, and the orchestrator is never its own reviewer. Each reviewer that signs off gets `Reviewed-by: <actual reviewer model> <noreply@anthropic.com>` on that commit — a reviewer is never a co-author. Exactly three exemptions: an already-verified one-liner folded into an open related PR (`branch-workflow.md`); spec/plan/closeout-docs commits whose content the user explicitly approved in the producing flow; merge commits (produced by `gh`, no trailers).
- Keep commits local through the iteration — amending trailers is free until push; push at finishing points. A commit that reached remote unreviewed: review now, amend the trailer, `git push --force-with-lease` (permitted on feature branches and `develop`; **never rewrite `main`**). The iteration's closeout commit is the fallback home for a trailer that couldn't land on its own commit.
- PR-description aggregation of authors and reviewers: the `open-pr` skill.
