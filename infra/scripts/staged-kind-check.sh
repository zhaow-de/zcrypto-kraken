#!/usr/bin/env bash
# claude-kind files (.claude/, CLAUDE.md) never share a commit with another kind
# Stage by explicit path, one kind per commit.
# Deliberate exception: SKIP=staged-kind git commit ...
set -euo pipefail
# A MERGE stages the union of both parents' kinds, and the author chose neither. This hook exists to stop the two
# kinds being AUTHORED together; a branch that legitimately carries one claude-kind commit and one code commit
# trips it at the merge, where splitting is not a thing you can do. `SKIP=staged-kind` was the workaround used
# four times on 2026-09-13 before this arm existed, and a documented skip that fires routinely stops being read.
if [ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]; then exit 0; fi
staged=$(git diff --cached --name-only)
[ -z "$staged" ] && exit 0
claude=$(grep -cE '^(\.claude/|CLAUDE\.md$)' <<<"$staged" || true)
other=$(grep -cvE '^(\.claude/|CLAUDE\.md$)' <<<"$staged" || true)
if [ "$claude" -gt 0 ] && [ "$other" -gt 0 ]; then
    printf 'claude-kind files mixed with another kind — split the commit (one kind per commit):\n'
    sed 's/^/  /' <<<"$staged"
    exit 1
fi
