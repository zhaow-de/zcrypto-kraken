---
name: open-pr
description: Use when creating a GitHub pull request, editing a PR title or body, or regenerating a PR's trailer aggregation after new commits land — load BEFORE running gh pr create or any PR-body edit.
disable-model-invocation: false
---

# open-pr

## Step 0 — the gate (defense in depth; `branch-workflow.md` is the authority)

A PR delivers **one completed, nameable component**. Before anything below: (1) name the component from durable state — branch name, spec serial, memo queue item, `T<NNNN>` topic; cannot name it → stop, report the branch ready-or-not instead. (2) Confirm the component is complete — topic `resolved`, or `partial` with the remainder registered. (3) Attended session → the user has explicitly said to open; a `/zcrypto-auto-exec` run opens at item completion. A green commit is not a reason; a different component is not a reason to reuse this PR.

## Title (iteration PRs)

GitHub PRs that ship an iteration's work use this exact shape:

```
feat(<scope>): iter-<N> — <short description>
```

- `<scope>` is the snake_case component name (e.g. `cli`), or `config` / `build` if cross-cutting — the component, not the iteration tag.
- `<N>` uses the abbreviated tag `iter-<N>` (e.g. `iter-9`), not spelled out as `iteration 9`.
- Em-dash `—` separates the iteration tag from the description.
- Description mirrors the spec's goal sentence.

## Body

Open PRs using the template at `.github/pull_request_template.md`. Because `gh pr create --body "…"` **bypasses** that template, when you create a PR with `--body` you must mirror the same structure by hand.

**Required, in order:**

1. `## Summary` — one or two sentences mirroring the spec's goal.
2. `## Spec / Plan` — links to the `docs/specs/…` and `docs/plans/…` that produced the PR (`N/A — <reason>` if there was none).
3. the flexible middle (below),
4. `## Checklist`,
5. the aggregated `Co-Authored-By:` trailer — plus a `Reviewed-by:` line if any commits carry reviewer trailers (see below).

**Flexible middle:** between Spec/Plan and Checklist, add whatever sections fit the change — a *menu, not a mandate*: `## Changes`, `## Test plan`, `## Migration / compatibility`, `## Risks`, `## Screenshots`, `## Out of scope`, `## Follow-ups`. Scale to complexity and mirror the spec — a trivial PR may add none, a large one several. **`## Follow-ups` and `## Out of scope` may only reference registered `T<NNNN>` open topics (or state an explicit drop)** — a PR description is never re-read after merge, so it must never be a deferred action's only home (see `open-topics.md`).

### Co-author trailer (PR description)

End the PR body with a single trailer aggregating the **distinct** Claude models that co-authored the PR's commits — deduplicated, **names only** (drop the `<email>`), joined with `; `:

```
Co-Authored-By: Claude Opus 4.8; Claude Sonnet 4.6
```

Derive it from the PR's commits (preserving first-seen order), where `<base>` is the PR's base branch (usually `develop`):

```bash
git log <base>..HEAD --pretty='%(trailers:key=Co-authored-by,valueonly)' \
  | sed '/^$/d' | sed 's/ <[^>]*>//' | awk '!seen[$0]++' | paste -sd , - | sed 's/,/; /g'
```

(`paste -sd ','` joins with a single delimiter, then `sed` expands each into `; ` — a multi-char `paste -sd '; '` would alternate the two characters and drop the space.)

Regenerate the trailer whenever the PR description changes. This aggregated form is for the PR **description only** — per-commit `Co-Authored-By:` trailers stay as-is (one per commit, full `Name <noreply@anthropic.com>` form) per `commit-messages.md`.

### Reviewer trailer (PR description)

If any of the PR's commits carry `Reviewed-by:` trailers (see `commit-messages.md`), add a `Reviewed-by:` line directly below the co-author one, aggregated the **same way** — distinct models, **names only** (drop the `<email>`), `; `-joined — but from the `Reviewed-by` key and emitted as `Reviewed-by:`, so reviewers are never folded into authorship:

```
Reviewed-by: Claude Opus 4.7
```

```bash
git log <base>..HEAD --pretty='%(trailers:key=Reviewed-by,valueonly)' \
  | sed '/^$/d' | sed 's/ <[^>]*>//' | awk '!seen[$0]++' | paste -sd , - | sed 's/,/; /g'
```

Omit the line entirely when there are no reviewer trailers. The PR body is free text, so this line is plain text (not parsed by git's trailer engine) — it just mirrors the co-author aggregation.

## The deferral sweep — before every create or body edit

Sweep the draft body for deferral language — *follow-up, later, once/when X, deferred, out of scope, known imprecision, registered* — and resolve **every hit in the same edit**: an existing `T<NNNN>` reference, a new topic via `topic-ops`, or an explicit drop. Writing the caveat is not registering it; a claim that something "is registered" is checked by grep, not trusted.

## Editing a PR body

`gh pr edit --body/--title` **silently no-ops** in this repo (a Projects-classic GraphQL deprecation aborts the mutation while exiting 0). Update via REST instead, and always verify the edit persisted — never trust the exit code:

```bash
gh api "repos/zhaow-de/zcrypto-kraken/pulls/<N>" -X PATCH -f body="$(cat body.md)"
gh pr view <N> --json body -q .body | head   # confirm the new content is live
```

A stale body matters: the `/merge-pr` gate parses it for unchecked `- [ ]` items.

## Target branch

Feature and iteration PRs target **`develop`** (see `branch-workflow.md`). Release PRs are opened by the `/release` skill from a `release/<timestamp>` branch **into `main`**, titled `Release v<major>.<minor>.<patch>` — you don't write those by hand.
