---
name: release
description: Cut a release — bump the version on develop, open a PR into main, merge it, push the v<version> tag, create the GitHub Release, and back-merge main into develop
allowed-tools: Bash(git add:*), Bash(git checkout:*), Bash(git tag:*), Bash(git status:*), Bash(git commit:*), Bash(git push:*), Bash(git pull:*), Bash(git fetch:*), Bash(git merge:*), Bash(git log:*), Bash(git branch:*), Bash(git show:*), Bash(gh pr:*), Bash(gh release:*), Bash(gh auth:*), Bash(gh api:*), Bash(git rev-parse:*), Bash(cz:*), Bash(uv:*), Bash(python3:*), Bash(sleep:*), Bash(timeout:*), Bash(which:*), Bash(awk:*), Bash(sed:*), Bash(grep:*), Bash(echo:*), Read, Edit, Write, AskUserQuestion
---

> **This skill has never been run end to end.** Its steps are verified against the tree, not against a real cut, so read what each one prints rather than assuming it worked. After the first real release, re-read the whole skill against what actually happened and correct it in the same branch — that read is owed once and is the only thing a first cut can give.

## Context

- Current branch: !`git branch --show-current`
- Current version: !`cz version --project 2>/dev/null || echo "(cz not installed yet — step 1 installs it)"`
- Prerequisites: !`which gh && which python3 && which uv && echo "all found" || echo "MISSING tools"`
- `cz` present already: !`which cz || echo "(absent — step 1 installs it)"`

## Instructions

1. **Verify prerequisites and install `cz`** from the context above. If not on `develop`, ask the user to switch branches first. If `gh`, `python3` or `uv` is missing, report and stop — those three are the environment's, not this skill's to install.

   `cz` is deliberately not a project dependency — a release is the only thing that uses it. Install it, then prove it answers:

   ```bash
   uv tool install commitizen
   cz version --project
   ```

   If `cz version --project` still fails after the install, stop and report — every later step that bumps, reads the version, or builds the changelog runs through it. Confirm `gh auth status` succeeds — if it returns 401, ask the user to run `gh auth refresh -h github.com` first.

2. **Update develop and verify it is synced with main**:
   ```bash
   git pull origin develop
   git fetch origin main
   ```

   Check for drift — a commit on `main` that is not on `develop` will conflict in the release PR:

   ```bash
   git log develop..origin/main --oneline
   ```

   If this shows any commits, drift exists. Use `AskUserQuestion` to ask whether to resolve it now by merging `main` into `develop`, or to abort:
   - Show the drifting commits (so the user can see what's about to come in).
   - Options: "Yes, back-merge main → develop now" / "Abort, I'll handle it manually".

   **If the user chooses to back-merge:**
   ```bash
   git merge origin/main --no-edit
   ```

   - If the merge succeeds cleanly: `develop` is PR-protected (no direct pushes — the same fact step 17 is built on), so land it exactly as step 17 lands the back-merge — a short `chore/pre-release-sync-v<VERSION>` branch, PR, poll-then-merge. Then continue to step 3.
   - If the merge fails with conflicts, do **not** push. Investigate each conflicted file, propose a resolution to the user (typical patterns: version files → take whichever is newer / about-to-be-bumped; `CHANGELOG.md` → keep both entries chronologically; modified-on-main but deleted-on-develop → confirm the fix exists in the replacement code, then keep the deletion), apply it, commit the merge, and land it via the same PR route. Only then continue.

   **If the user chooses to abort:** stop and report — do not proceed.

3. **Create the release branch**:
   ```bash
   git checkout -b "release/$(date +%Y%m%d-%H%M%S)"
   ```

4. **Bump the version files and generate the raw changelog** — `--files-only`, so nothing is committed or tagged yet:
   ```bash
   cz bump --yes --changelog --files-only
   ```

   This updates the `version_files` (`pyproject.toml` and the README `Version` badge), bumps `.cz.toml`, and writes the raw commit list to `CHANGELOG.md`.

5. **Refresh `uv.lock` to record the new version**:
   ```bash
   uv lock
   ```
   `cz bump` does not touch `uv.lock`; without this step the lockfile would silently drift behind `pyproject.toml`. The change is uncommitted at this point; step 9 commits it together with the version bump and changelog.

6. **Verify `version_files` were actually bumped**:

   `cz bump` silently skips a `version_files` entry whose line no longer contains the previous version string (drift from a past bad bump). A silent skip means `pyproject.toml` or the README `Version` badge would keep the old version.

   ```bash
   NEW_VERSION=$(cz version --project)
   PYPROJECT_VERSION=$(grep -E '^version' pyproject.toml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
   README_VERSION=$(grep -oE 'badge/version-v[0-9]+\.[0-9]+\.[0-9]+' README.md | head -1 | sed -E 's/.*-v//')

   if [ "$PYPROJECT_VERSION" != "$NEW_VERSION" ] || [ "$README_VERSION" != "$NEW_VERSION" ]; then
       echo "ERROR: cz bump skipped one or more version_files"
       echo "  cz says: $NEW_VERSION"
       echo "  pyproject.toml: $PYPROJECT_VERSION"
       echo "  README.md badge: $README_VERSION"
       echo "Stop and investigate — do NOT push. Likely cause: the file's version drifted from .cz.toml in a past release, so cz's find-and-replace cannot locate the old value."
       exit 1
   fi
   ```

   If this fails, stop and report — do not proceed.

7. **Fetch PR data for the changelog.** It prints the path it wrote on stdout alone; step 8 needs that path itself, since a variable dies with this command:
   ```bash
   python3 .claude/skills/release/scripts/fetch-pr-data.py
   ```

   If the script refuses a possibly truncated `gh pr list`, do what its message says and re-run this step.

8. **Generate the user-friendly changelog**:

   Read the PR data from the path step 7 printed and follow the format and guidelines in [changelog-format.md](changelog-format.md). Replace the raw commit list `cz bump` wrote into `CHANGELOG.md` with the user-friendly section for the new version at the top, and **preserve all previous version sections below it**.

9. **Commit the release and create the tag**:
   ```bash
   VERSION=$(cz version --project)
   git add .cz.toml pyproject.toml README.md CHANGELOG.md uv.lock
   git commit -m "chore(release): bump version to v$VERSION"
   git tag "v$VERSION"
   ```

   Remember `VERSION` for the remaining steps.

10. **Push the release branch**:
    ```bash
    git push origin "$(git branch --show-current)"
    ```

11. **Create the PR** with `gh pr create` targeting `main`, using the description template from [pr-description.md](pr-description.md) (fill in `{version}` with `VERSION`). Include flags `--base main`, `--title "Release v<VERSION>"`, `--assignee @me`, and pass the filled template via `--body-file` (or `--body`).

12. **Store the PR number and URL** from the output of step 11.

13. **Return to develop**:
    ```bash
    git checkout develop
    ```

14. **Auto-merge the release PR** with a merge commit (preserving the tagged bump commit on `main`). Releases run end-to-end without pausing to ask. Stop only if something is genuinely worth attention: the PR has conflicts, or it was closed without merging.

    **Read the suite's verdict first, by name, on the release branch's own head sha.** `.github/settings.yml` requires the `Full test suite` context on `main`, so this read is the same verdict the merge below waits on, not a second opinion. Run it as its OWN command, re-read every ~45 s, and never as one long foreground loop:

    ```bash
    SHA=$(git rev-parse "v<VERSION>")
    timeout 40 gh api "repos/zhaow-de/zcrypto-kraken/commits/$SHA/check-runs" \
      --jq '[.check_runs[] | {n: .name, s: .status, c: (.conclusion // "")}]' | python3 -c '
    import sys, json
    try:
        runs = json.loads(sys.stdin.read())
    except ValueError:
        print("pending (no reading — the call returned nothing)"); raise SystemExit
    run = next((r for r in runs if r["n"] == "Full test suite"), None)
    if run is None:
        print("pending (not registered yet)"); raise SystemExit
    if run["s"] != "completed":
        print(f"pending ({run["s"]})"); raise SystemExit
    print("success" if run["c"] in ("success", "neutral", "skipped") else f"failed ({run["c"]})")
    '
    ```

    A `pending` reading is this poll working: re-read it. One still pending 30 minutes after the push is stalled and worth attention, not a stop. A `failed` reading stops the release, and then delete the local tag (`git tag -d v<VERSION>`) first, or step 9 of the re-cut fails on a tag naming a version that must not ship. Only once it prints `success`, read the PR's state with per-call timeouts, as its OWN command re-issued every ~30 s, and merge as soon as GitHub reports it mergeable and not blocked by branch protection:
    ```bash
    PR_NUMBER=<the PR number from step 12>

    pr_state=$(timeout 30 gh pr view "$PR_NUMBER" --json state -q .state)
    pr_mergeable=$(timeout 30 gh pr view "$PR_NUMBER" --json mergeable -q .mergeable)
    pr_state_status=$(timeout 30 gh pr view "$PR_NUMBER" --json mergeStateStatus -q .mergeStateStatus)
    if [ "$pr_state" = "MERGED" ]; then
        echo "PR merged!"
    elif [ "$pr_state" = "CLOSED" ]; then
        echo "PR was closed without merging — stop"
    elif [ "$pr_mergeable" = "CONFLICTING" ]; then
        echo "PR has conflicts — stop, do not merge"
    elif [ "$pr_mergeable" = "MERGEABLE" ] && [ "$pr_state_status" != "BLOCKED" ]; then
        timeout 60 gh pr merge "$PR_NUMBER" --merge --delete-branch
    else
        echo "PR not ready (state: $pr_state, mergeable: $pr_mergeable, status: $pr_state_status) — re-run this block in ~30 s"
    fi
    ```

15. **Push the release tag** so it points at the bump commit now on `main`. The tag was created in step 9 and persists across the branch switch.
    ```bash
    git push origin "v<VERSION>"
    ```

16. **Create the GitHub Release** directly, with the new version's changelog section as the description. Extract that section **from the tag** (`git show v<VERSION>:CHANGELOG.md`), *not* the working-tree `CHANGELOG.md`: by this point you are back on `develop` (step 13), whose `CHANGELOG.md` does not yet carry the new section (it arrives only via the back-merge in step 17), so reading the working tree would publish **empty** notes.
    ```bash
    git show "v<VERSION>:CHANGELOG.md" | awk 'NR>1 && /^## v[0-9]/{exit} {print}' > "/tmp/release_notes_v<VERSION>.md"
    if [ ! -s "/tmp/release_notes_v<VERSION>.md" ]; then
        echo "ERROR: extracted release notes are empty — do NOT publish. Check the tag's CHANGELOG.md."
        exit 1
    fi
    gh release create "v<VERSION>" --title "v<VERSION>" --notes-file "/tmp/release_notes_v<VERSION>.md" --verify-tag
    ```
    The `awk` prints from the top of the tagged `CHANGELOG.md` until the next `## v…` header — i.e. just the new version's section. `--verify-tag` aborts if the tag was not pushed in step 15. The command prints the Release URL — keep it for the final report.

17. **Back-merge `main` → `develop` via a PR.** This repo's `develop` is protected against direct pushes, so the back-merge cannot be a plain `git push`. Cut a dedicated `chore/back-merge-v<VERSION>` branch off `origin/main` (a topic branch keeps the PR's head distinct from the long-lived ref, and step 18 deletes it). Push it, open the PR, then auto-merge with the same read-then-merge block as step 14, re-issued the same way:
    ```bash
    git fetch origin main
    BACKMERGE_BRANCH="chore/back-merge-v<VERSION>"
    git checkout -b "$BACKMERGE_BRANCH" origin/main
    git push -u origin "$BACKMERGE_BRANCH"
    BACKMERGE_URL=$(gh pr create --base develop --head "$BACKMERGE_BRANCH" \
        --title "chore(config): back-merge v<VERSION> into develop" \
        --body "Back-merge of the \`v<VERSION>\` release commit from \`main\` into \`develop\` so the two branches stay in lock-step. Auto-opened by the \`/release\` skill.")
    BACKMERGE_NUMBER=$(echo "$BACKMERGE_URL" | sed -E 's|.*/pull/([0-9]+)|\1|')

    pr_state=$(timeout 30 gh pr view "$BACKMERGE_NUMBER" --json state -q .state)
    pr_mergeable=$(timeout 30 gh pr view "$BACKMERGE_NUMBER" --json mergeable -q .mergeable)
    pr_state_status=$(timeout 30 gh pr view "$BACKMERGE_NUMBER" --json mergeStateStatus -q .mergeStateStatus)
    if [ "$pr_state" = "MERGED" ]; then
        echo "Back-merge PR merged!"
    elif [ "$pr_state" = "CLOSED" ]; then
        echo "Back-merge PR was closed without merging — stop"
    elif [ "$pr_mergeable" = "CONFLICTING" ]; then
        echo "Back-merge PR has conflicts — stop, do not merge"
    elif [ "$pr_mergeable" = "MERGEABLE" ] && [ "$pr_state_status" != "BLOCKED" ]; then
        timeout 60 gh pr merge "$BACKMERGE_NUMBER" --merge --delete-branch
    else
        echo "Back-merge PR not ready (state: $pr_state, mergeable: $pr_mergeable, status: $pr_state_status) — re-run this block in ~30 s"
    fi
    ```

18. **Local cleanup** — fast-forward both branches against their remotes, drop the throwaway release **and** back-merge branches, and prune stale tracking refs:
    ```bash
    git checkout develop
    git pull --ff-only origin develop
    git checkout main
    git pull --ff-only origin main
    git checkout develop
    git branch -d release/<timestamp from step 3>
    git branch -d chore/back-merge-v<VERSION>
    git fetch --all --prune
    ```

    Both `git branch -d` calls succeed because each branch is fully integrated via its merge commit (the release branch into `main` via PR step 14; the back-merge branch into `develop` via PR step 17). If either ever errors "not fully merged" while its PR shows merged and the remote head is gone, the work is integrated — `git branch -D` is then safe.

19. **Report success** with the release PR URL, the GitHub Release URL (printed by step 16), and the back-merge PR URL.

## Notes

- If any step fails, stop and report the error to the user.
- Auto-merge in steps 14 and 17 uses `--merge` — never switch to `--squash` or `--rebase`, which would lose the bump-commit-tagged invariant on `main`.
- Do not use composite commands — they always force a permission request from the user.
- You are already in the repo folder — do not `cd` first (redundant, and can cause a composite command).
