---
status: resolved
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

## Resolution

Fixed ahead of a release rather than during one, on the owner's word of 2026-09-22 that the trigger above was
artificial: none of the four defects needed a real cut to see, and every one of them would have been found by
the person least able to afford it.

- **`cz`'s home — ruled: install it at step 1.** `uv tool install commitizen`, with the four call sites left
  bare. `pyproject.toml` and `uv.lock` are untouched, so no dev dependency and no CI install time is spent on a
  tool only a release uses. Step 1 now installs it and proves it answers instead of stopping on its absence, and
  the `## Context` block tolerates it being missing so the skill can still load.
- **The two harness variables are gone, not replaced.** `${CLAUDE_SKILL_DIR}` became the repo-relative path the
  skill's own Notes already assume, and `${CLAUDE_SESSION_ID}` became a `tempfile` path the script prints on
  stdout alone for the caller to capture. Swapping in a name this harness happens to set would have left the
  same coupling that broke it.
- **The fetch limit is 2000 and saturation refuses.** A list as long as the limit exits non-zero naming the
  incompleteness, because `gh pr list` is silent when it truncates and the result is a changelog that reads
  complete.
- **Step 14 reads the suite by name on the release head's sha** before it merges, and `.github/settings.yml` now
  requires the `Full test suite` context on `main` as well as `develop` — the release PR was the one merge in
  the repo that nothing gated, from either side.

What a first cut can still teach is an instruction on the skill itself, not a deferral: its banner tells the
runner of the first real release to re-read the whole skill against what happened and correct it in the same
branch. That lands the remaining item on the surface that performs it, which is why this topic closes with no
live sub-item rather than splitting one off.
