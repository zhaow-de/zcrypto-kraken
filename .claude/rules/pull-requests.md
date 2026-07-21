# Pull request convention

- **WHEN to open is `branch-workflow.md`'s PR gate** — one completed, nameable component, on the user's explicit word (attended) or at `/zcrypto-auto-exec` item completion (unattended).
- **HOW — titles, body template, trailer aggregation, the `gh pr edit` REST workaround — is the `open-pr` skill** (`.claude/skills/open-pr/SKILL.md`): load it for every PR create or body edit.
- Ambient essentials: feature/iteration PRs target `develop`; release PRs exist only via `/release`. Iteration titles: `feat(<scope>): iter-<N> — <description>`. A PR body's `## Follow-ups` / `## Out of scope` may only reference registered `T<NNNN>` topics or explicit drops — a PR body is never a deferred action's only home.
