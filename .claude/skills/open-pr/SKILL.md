---
name: open-pr
description: Use when creating a GitHub pull request or editing a PR title or body — load BEFORE running gh pr create or any PR-body edit.
disable-model-invocation: false
---

# open-pr

## Step 0 — the gate

A PR delivers **one completed, nameable component**. Before anything below: (1) name the component from durable state — branch name, spec serial, memo queue item, `T<NNNN>` topic; cannot name it → stop, report the branch ready-or-not instead. (2) Confirm the component is complete — topic `resolved`, or `partial` with the remainder registered. (3) The word — `zcrypto-marco`'s by delegation in the multi-session setup, the user's explicit say-so for a single attended session; a `/zcrypto-auto-exec` run opens at item completion. A green commit is not a reason; a different component is not a reason to reuse this PR.

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
4. `## Checklist`.

**Flexible middle:** between Spec/Plan and Checklist, add whatever sections fit the change — a *menu, not a mandate*: `## Changes`, `## Test plan`, `## Migration / compatibility`, `## Risks`, `## Screenshots`, `## Out of scope`, `## Follow-ups`. Scale to complexity and mirror the spec — a trivial PR may add none, a large one several. **`## Follow-ups` and `## Out of scope` may only reference registered `T<NNNN>` open topics (or state an explicit drop)** — a PR description is never re-read after merge, so it must never be a deferred action's only home.

## The deferral sweep — before every create or body edit

Sweep the draft body for deferral language — *follow-up, later, once/when X, deferred, out of scope, known imprecision, registered* — and resolve **every hit in the same edit**: an existing `T<NNNN>` reference, a new topic via `topic-ops`, or an explicit drop. Writing the caveat is not registering it; a claim that something "is registered" is checked by grep, not trusted.

## Creating the PR — four steps, in order

Steps 1 and 2 refuse before anything reaches GitHub; steps 3 and 4 are one operation and neither is finished without the other. **This skill runs BEFORE `iteration-closeout`**, so the PR number an entry cites already exists when closeout writes it.

**Step 1 — the title check.** A title longer than 72 characters is refused: `docs/reference/change-index.md`'s title cell IS the title, capped at 72 by `tests/test_change_index.py`, so a longer one either loses its tail or fails the guard. Measure it, never eyeball it — and write any `/` in a title as `-`, because no cell may carry a path-shaped token:

```bash
TITLE='feat(<scope>): iter-<N> — <short description>'
printf '%s' "$TITLE" | wc -m      # > 72 → rewrite the title shorter, do not create
```

**Step 2 — the serial refusal.** If the branch name or the title carries `iter-<N>`, that number must be the change index's highest `iter` **plus one**, or must already appear in the index against this same branch (re-opening a PR for a branch that already has a row). Anything else means the serial was improvised rather than minted:

```bash
HIGHEST=$(awk -F'|' '/^\| #/ {print $5}' docs/reference/change-index.md | grep -oE 'iter-[0-9]{3}' | sort -u | tail -1)
grep -n "$(git rev-parse --abbrev-ref HEAD)" docs/reference/change-index.md   # a row already ours?
```

On a mismatch, **refuse to create the PR** and print both numbers — the one in the branch or title, and the index's highest — so the mint can be corrected before the PR exists. A serial is minted when the branch is cut, from this same command; nothing else mints one.

**Step 3 — `gh pr create`.** The PR number comes back in the URL it prints; keep it.

**Step 4 — the change-index row.** Parse the three key kinds out of the branch name, the PR title, and the body's `## Spec / Plan` section — iterations `\biter-(\d{1,3})\b`, spec serials `\b\d{5}\b`, topics `\bT\d{4}\b`. If **at least one** key is present, append one row to `docs/reference/change-index.md`, commit it on the branch, and push:

```
| #<PR number> | <today, UTC> | <title, at most 72 chars> | <iters> | <specs> | <topics> |
```

Iterations are zero-padded to three digits (`iter-007`), several keys of one kind are comma-separated, and a kind with no key is an em dash `—`. Rows stay sorted by PR number ascending, and **no cell may hold a file path** — a spec is its bare serial `00034`, never `docs/specs/00034-…`. No key of any kind ⇒ no row. Then re-read the file and confirm the row is there before reporting the PR open.

## Editing a PR body

`gh pr edit --body/--title` **silently no-ops** in this repo (a Projects-classic GraphQL deprecation aborts the mutation while exiting 0). Update via REST instead, and always verify the edit persisted — never trust the exit code:

```bash
gh api "repos/zhaow-de/zcrypto-kraken/pulls/<N>" -X PATCH -f body="$(cat body.md)"
gh pr view <N> --json body -q .body | head   # confirm the new content is live
```

A stale body matters: the `/merge-pr` gate parses it for unchecked `- [ ]` items.

## Target branch

Feature and iteration PRs target **`develop`**. Nothing opened here targets `main`.
