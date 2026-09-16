---
status: open
ripe_when: the owner has ruled on giving the `Full test suite` job a `GH_TOKEN` — check `grep -c 'GH_TOKEN' .github/workflows/coverage.yml`, which is 0 while the ruling is outstanding
---

# Nine count-list gates skip on every CI run

## Context — what

`tests/test_count_list.py` guards nine of its cases with `@pytest.mark.skipif(not _develop_resolves())`, and `_develop_resolves()` verifies the **local** `develop` ref only. A `pull_request` checkout is detached at the merge ref and carries `origin/develop` alone, so all nine take a silent skip in every CI run — the same silence that `fix/ci-shallow-checkout` closed for the change-index guard, in the same job.

## Why this matters

A skip is indistinguishable from a pass in a summary line. Nine of the counts that hold this repo's universals — the ones `CLAUDE.md` and `.claude/rules/fleet-deploys.md` name as the set behind each rule — are therefore unmeasured on the run that gates a merge, and have been for as long as the gates have existed.

## Findings so far

- The ref is what the gates want, and giving it to CI works. Driven in a CI-shaped clone (full clone, detached at `origin/develop`, no local branch): `git branch --force develop origin/develop` before the suite turns **13 passed / 3 failed / 9 silent skips** into **15 passed / 1 failed**.
- That remaining failure is the decision, not a detail. With the gates live, `test_the_script_prints_one_shaped_line_per_entry` runs `count-list.sh`, whose `merged-prs-without-a-floor-read-30d` shells out to `gh pr list`; `.github/workflows/coverage.yml` sets no `GH_TOKEN`, so the count exits 2 and the build goes red.
- Resolving `origin/develop` inside `count-list.sh` was tried first and is the wrong size: the script names `develop` in nine git commands, and two cases pin the script's own wording, so the refactor breaks guards that exist to keep the prose true.
- Found by the pre-read class walk on `fix/ci-shallow-checkout`, 2026-09-16, as a surviving member of that branch's class.

## Suggested next steps

- Owner decision, one of two: give the `Full test suite` job `GH_TOKEN: ${{ github.token }}` so the network count can run, or take the network counts out of the entry that case drives. Neither is a code change until it is made.
- Then add `- run: git branch --force develop origin/develop` after the checkout in `.github/workflows/coverage.yml`, and confirm the nine gates run rather than skip: `GITHUB_ACTIONS=true uv run pytest -q tests/test_count_list.py -rs` in a CI-shaped clone must report no skip at lines 179, 231, 298, 348, 395, 425, 442, 463 or 475.
- Consider whether `_develop_resolves()` should accept `origin/develop` as `tests/test_change_index.py` does, which would make the gates honest in any detached worktree as well as in CI.
