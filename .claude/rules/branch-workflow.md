# Branch & PR workflow

- **`develop` is the integration branch.** Every branch — bug fixes, features, iterations, doc updates — is cut from `develop` and opens a GitHub pull request **into `develop`**.
- **`main` is release-only.** It advances solely by merging `release/<timestamp>` branches (cut from `develop` by the `/release` skill), and each such merge is tagged `v<major>.<minor>.<patch>`. Never branch off `main`, never open a PR into `main` for feature work, and never commit to `main` directly. After a release merges, `main` is back-merged into `develop` so the two stay in lock-step.
- **GitHub is the remote** — use `gh`.
- **One PR holds one logical development component** — its spec, plan, implementation, fixes found along the way, and closeout all land in the **same** PR. Keep committing to the open component branch (a branch living for days with many commits is correct); merge only when the component is complete. Only genuinely independent work (a different component) gets its own branch/PR — never cut a new branch just because a fix is "ready now".
- **A trivial, already-verified one-liner while a related PR is open**: fold it into that PR as a small extra commit instead of a separate branch/PR; subagent review may be skipped for such fold-ins (see `commit-messages.md`). When unsure it qualifies, ask.
- Cut releases with the `/release` skill (commitizen; bump rules in `.cz.toml`). See `pull-requests.md` for PR titles.
