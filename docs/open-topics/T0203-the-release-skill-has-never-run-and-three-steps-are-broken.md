---
status: open
ripe_when: 'a release is being cut: `git branch -a --list "*release/*"` prints a branch, or `git log --oneline main | wc -l` reads more than 1.'
---

# The release skill has never run, and three of its steps are broken as written

## Context — what

`/release` has never been invoked. `main` still carries the initial commit alone, the only tag is `v0.0.0`,
and `CHANGELOG.md` is 0 bytes. A skills survey on 2026-09-14 read it against the tree and found three steps
that cannot run as written:

- `cz` is installed nowhere in this environment, and four steps invoke it bare (`## Context`, steps 4, 6, 9).
  The `## Context` block runs it at load, so a `/release` run stops at step 1.
- `${CLAUDE_SKILL_DIR}` and `${CLAUDE_SESSION_ID}` are not names this harness sets.
- `scripts/fetch-pr-data.py` fetches with `--limit 100` against 502 PRs merged since the `v0.0.0` tag, so the
  first changelog would silently lose 402 of them, with nothing saying so.

Step 14 also merges the release PR into `main` without reading the `Full test suite` check, which `main`'s
protection does not require either — the one merge in this repo that nothing gates.

## Why this matters

A release skill is only exercised by a release, so every defect in it is found at the worst moment: the first
real cut, by whoever is doing it, under the one procedure in the repo that touches `main` and publishes a tag.
The `cz` failure is at load, which is the good case; the PR-fetch truncation is the bad one — it produces a
plausible changelog that is missing four fifths of the work, and nothing in the run says so.

## Findings so far

- The survey's report: the skill's own steps verified against the tree at `ed835cda8`; `cz` absent from the
  dev group and from the environment; `git log --oneline main | wc -l` = 1; `git tag` = `v0.0.0`;
  `wc -c CHANGELOG.md` = 0.
- The owner's ruling of 2026-09-14: mark it, refine it right after rung 3 with a real release run, rather than
  fixing it blind now. The trigger above is the repo state that ruling produces; cutting a release is the
  release's work, not this topic's.

## Suggested next steps

- Decide `cz`'s home: add commitizen to the dev group and rewrite the four call sites as `uv run cz …`, or make
  step 1 install it (`uv tool install commitizen`). Four sites must agree with whichever is chosen.
- Replace the two harness variables with names this harness sets, or with paths.
- Raise `fetch-pr-data.py`'s limit and refuse on saturation: if the page count equals the limit, exit non-zero
  naming the incompleteness rather than writing a truncated JSON.
- Give step 14 the check-runs poll `dependabot` §2d already carries, aimed at the release branch's head sha.
- Run it end to end on the real cut, with the whole skill read against what actually happened.
