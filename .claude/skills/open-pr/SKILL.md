---
name: open-pr
description: Use when creating a GitHub pull request or editing a PR title or body — load BEFORE running gh pr create or any PR-body edit.
---

# open-pr

## Step 0 — the gate

A PR delivers **one completed, nameable component**. Before anything below: (1) name the component from durable state — branch name, spec serial, memo queue item, `T<NNNN>` topic; cannot name it → stop, report the branch ready-or-not instead. (2) Confirm the component is complete — topic `resolved`, or `partial` with the remainder registered. (3) The word — `zcrypto-marco`'s by delegation in the multi-session setup, the user's explicit say-so for a single attended session; a `/zcrypto-auto-exec` run opens at item completion. A green commit is not a reason; a different component is not a reason to reuse this PR. The ban on a second PR is on the one that follows the merge: a change that lands while the branch is open is a commit on it, not a follow-up. The one case a second component rides an open PR is an owner-directed fold-in, named under `## Changes` with the owner's word — never under `## Out of scope`.

**The rider that is not a second component.** A follow-up whose trigger would name a file this PR ALREADY touches is done here, not registered: the reader is in those files, and a topic saying "next time someone is here" written by someone who is here is satisfied the moment it is filed. Both halves bind — the file must be one this branch has opened, and the work must be cheap BECAUSE you are already there. Anything needing its own design decision, its own spec, or a file this branch has not touched stays a topic and the one-component rule holds. Name the rider under `## Changes`; it needs no separate word.

**A draft is not a delivery.** `.github/workflows/coverage.yml` fires on `pull_request` alone, so a branch with no PR runs no CI at all and its author pays for the whole suite by hand. Open the PR as a draft (`gh pr create --draft`) at the branch's first green commit: CI then runs the suite on every push, and `merge-pr`'s first gate refuses a draft, so nothing leaves early. The three conditions above are read at the undraft, not at the create; the body and Step 4's change-index row are written at create time, except the `Read before push by:` line, which names a read that has not happened yet and is written at the undraft.

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
3. `Read before push by: Claude Opus at <sha>` (or `Claude Fable`; the gate's floor matches the `Claude` prefix, and a body that drops it is refused) — one line naming the agent that read the whole branch before push, a different agent from the author, and the tip it read — the `review` workflow run over `develop..HEAD` before the push, `re-review` over the fix range before the push that carries the fixes; `merge-pr`'s gate refuses a body whose sha is not the PR head, so a commit pushed after the read takes a read of the delta and an updated line — except Step 4's change-index row commit and a message amend of the named tip, the two heads the gate admits past it. When the read is Opus and the PR touches a `--fable-paths` path, a second line goes directly below this one — `Fable floor substituted by Opus: <reason>` — whose reason the gate refuses when it is the placeholder, a filler token, or too little to be a reason, and which it reads as a reader sees it — a line inside a comment, a fenced block, a `<details>` block or a quote does not count, and an unterminated comment or fence hides everything after it.
4. `## Guidance changes` — when `git log develop..HEAD --format='%h %s' | grep '^[0-9a-f]* claude('` prints a line, that output verbatim under this heading, one commit per line; omitted when it prints nothing.
5. the flexible middle (below),
6. `## Checklist`.

**Flexible middle:** between the lines above and Checklist, add whatever sections fit the change — a *menu, not a mandate*: `## Changes`, `## Test plan`, `## Migration / compatibility`, `## Risks`, `## Screenshots`, `## Out of scope`, `## Follow-ups`. Scale to complexity and mirror the spec — a trivial PR may add none, a large one several. Every `## Changes` bullet is derived from the file-scoped diff at write time — `git diff <base> <tip> -- <path>` — never from a working summary of the branch; and a body claim about the branch names the class it covers, never a count, because the count is false the moment the next commit lands under it. **`## Follow-ups` and `## Out of scope` may only reference registered `T<NNNN>` open topics (or state an explicit drop)** — a PR description is never re-read after merge, so it must never be a deferred action's only home.

## The deferral sweep — before every create or body edit

Sweep the draft body for deferral language — *follow-up, later, once/when X, deferred, out of scope, known imprecision, registered* — and resolve **every hit in the same edit**: an existing `T<NNNN>` reference, a new topic via `topic-ops`, or an explicit drop. Writing the caveat is not registering it; a claim that something "is registered" is checked by grep, not trusted. Its mirror image: every `T<NNNN>` the body reports resolved, partial or archived is checked against `git diff develop...HEAD --name-only | grep T<NNNN>` — a status claim the diff does not carry is a false claim about durable state, the same way "is registered" is.

## Creating the PR — four steps, in order

Steps 1 and 2 refuse before anything reaches GitHub; steps 3 and 4 are one operation and neither is finished without the other. **This skill runs BEFORE `iteration-closeout`**, so the PR number an entry cites already exists when closeout writes it. Step 0's gate is read at the undraft, so a draft takes these four steps at the branch's first green commit and the gate again when it is undrafted.

**Step 1 — the title check.** A title longer than 72 characters is refused: `docs/reference/change-index.md`'s title cell IS the title, capped at 72 by `tests/test_change_index.py`, so a longer one either loses its tail or fails the guard. Measure it, never eyeball it — and the measurement and the create never share a Bash call: branch on the number in the script, or read it in one call and act in the next, because a number printed above a `gh pr create` line gates nothing. A title carrying a path-shaped token — a repo root `cli/`, `tests/`, `infra/`, `docs/`, `.claude/`, or `word/word.ext` — writes its `/` as `-` (`tests/test_change_index.py::test_no_cell_carries_a_path_shaped_token` is the grammar); a bare `long/flat` is not a path and keeps its slash:

```bash
TITLE='feat(<scope>): iter-<N> — <short description>'
N=$(printf '%s' "$TITLE" | wc -m); [ "$N" -le 72 ] || { echo "REFUSE: title is $N chars, cap is 72"; exit 1; }
```

**Step 2 — the serial refusal.** If the branch name or the title carries `iter-<N>`, that number must be the change index's highest `iter` **plus one**, or the index must already hold this PR's own row (a body edit on a PR that has one). Anything else means the serial was improvised rather than minted:

```bash
TITLE='feat(<scope>): iter-<N> — <short description>'   # Step 1's title again: a fresh shell per call
HIGHEST=$(awk -F'|' '/^\| #/ {print $5}' docs/reference/change-index.md | grep -oE 'iter-[0-9]{3}' | sort -u | tail -1)
NEXT=$(printf 'iter-%03d' $((10#${HIGHEST#iter-} + 1)))
MINE=$(printf '%s\n%s' "$(git branch --show-current)" "$TITLE" | grep -oE '\biter-[0-9]{1,3}\b' | head -1)
[ -z "$MINE" ] || [ "$(printf 'iter-%03d' $((10#${MINE#iter-})))" = "$NEXT" ] || grep -q "^| #<PR number> " docs/reference/change-index.md \
  || { echo "REFUSE: the branch or title says $MINE, the index's highest is $HIGHEST, so the mint is $NEXT"; exit 1; }
```

The refusal is the branch above, in the same call as the measurement and never in the call that creates: it prints both numbers — the one in the branch or title, and the index's highest — so the mint can be corrected before the PR exists; the `grep` arm is the body edit on a PR that already has its row. A serial is minted when the branch is cut, from this same `HIGHEST`; nothing else mints one.

**Step 3 — `gh pr create`.** `--draft` unless the branch is already complete and has the word; the PR number comes back in the URL it prints either way, and keep it. The turn does not end at the PR number: start the CI watch in the same turn — one backgrounded command re-reading the `Full test suite` check-run of the pushed sha with a per-call `timeout`, its terminal branch matched case-insensitively against the raw value, never a lowercase guess — and it ends at that run's conclusion, exiting non-zero on anything but success so the exit code carries the verdict, not only the echoed line; `merge-gate.py <n>` waits for the undraft, since its first gate refuses a draft.

```bash
SHA=$(git rev-parse HEAD)   # the pushed head; a later push restarts the watch on its sha
until R=$(timeout 40 gh api "repos/zhaow-de/zcrypto-kraken/commits/$SHA/check-runs" --jq '.check_runs[] | select(.name == "Full test suite") | "\(.status) \(.conclusion // "")"'); [[ "${R,,}" == completed* ]]; do sleep 45; done; echo "$R"; [[ "${R,,}" == *success* ]]
```

**Step 4 — the change-index row.** Parse the keys — iterations `\biter-(\d{1,3})\b` from the branch name and the PR title only, since a `## Spec / Plan` sentence naming an earlier iteration as its precedent is a cross-reference, not a delivery; spec serials `\b\d{5}\b`, topics `\bT\d{4}\b` matched case-insensitively (`(?i)` — a branch spells it `t0189`) and written with an upper-case `T`, from the branch name, the title and the body's `## Spec / Plan` section — and a topic the PR only **registers** is not a key: it is a cross-reference like the iteration above, recorded by `docs/open-topics/README.md`, and a row claiming it says the index delivered what it only filed. If **at least one** key is present, append one row to `docs/reference/change-index.md`, commit it on the branch, and push:

```
| #<PR number> | <the PR's creation date, UTC> | <title, at most 72 chars> | <iters> | <specs> | <topics> |
```

Iterations are zero-padded to three digits (`iter-007`), several keys of one kind are comma-separated, and a kind with no key is an em dash `—`. Rows stay sorted by PR number ascending, and **no cell may hold a file path** — a spec is its bare serial `00034`, never `docs/specs/00034-…`. No key of any kind ⇒ no row, and a topic the PR only registers is no key — except in the BRANCH NAME, which always takes a row, even when the PR delivered none of it and every cell is an em dash: `tests/test_change_index.py::test_every_keyed_merge_on_develop_has_a_row` reads the branch name and fires only on the merge, so this PR's CI is green without the row and develop goes red after it. The registration-only PR is exactly this case. The date is the PR's, not the clock's — `gh pr view <PR number> --json createdAt -q .createdAt | cut -dT -f1` — which differ whenever a row is written late. **A row already present is re-derived, not left**: every guard that checks a row AGAINST its pull request matches the PR number alone, and the cell guards read shape — the title cap, the path-shaped token — never correspondence, so a retitle or a newly minted key silently leaves the cells describing the pull request as it was when the row was written. Then re-read the file and confirm the row is there before reporting the PR open. The row commit is one of the two heads `merge-pr`'s gate admits past the tip the read line names — a single commit touching the index alone (the other is a message amend of that tip) — so it takes no delta read and the line stays as written.

## Editing a PR body

A title edit and a `## Spec / Plan` edit both re-derive Step 4's change-index row — they are two of the three sources its keys come from.

`gh pr edit --body/--title` **silently no-ops** in this repo (a Projects-classic GraphQL deprecation aborts the mutation while exiting 0). Update via REST instead, and always verify the edit persisted — never trust the exit code:

```bash
gh api repos/zhaow-de/zcrypto-kraken/pulls/<N> -X PATCH --input body.json   # {"body": "..."}
gh pr view <N> --json body -q .body | head   # confirm the new content is live
```

A stale body matters: the `/merge-pr` gate parses it for unchecked `- [ ]` items.

## Target branch

Feature and iteration PRs target **`develop`**; release PRs are the `release` skill's.
