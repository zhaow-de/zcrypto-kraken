#!/usr/bin/env bash
# claude-kind files (.claude/, CLAUDE.md) never share a commit with another kind
# Stage by explicit path, one kind per commit.
# Deliberate exception: SKIP=staged-kind git commit ...
set -euo pipefail
staged=$(git diff --cached --name-only)
[ -z "$staged" ] && exit 0
# The hook sees the index against HEAD, so `git commit --amend` passes it whatever the commit ends up holding;
# `guidance-guard.py --range`, which `merge-pr`'s gate runs, refuses the mixed commit at merge.
# A merge stages the union of the parents' kinds, which the author chose neither of and cannot split, so the
# merge's own candidate files get a pass -- only those, or a stopped merge admits anything staged beside them.
mergehead="$(git rev-parse --git-dir)/MERGE_HEAD"
if [ -f "$mergehead" ]; then
    candidates=""
    while read -r theirs; do  # one line per merged head
        base="$(git merge-base HEAD "$theirs")"
        candidates="$candidates$(git diff --name-only "$base" HEAD; git diff --name-only "$base" "$theirs")
"
    done < "$mergehead"
    candidates="$(printf '%s' "$candidates" | sed '/^$/d' | sort -u)"
    staged="$(comm -23 <(printf '%s\n' "$staged" | sort -u) <(printf '%s\n' "$candidates"))"
    [ -z "$staged" ] && exit 0
fi
claude=$(grep -cE '^(\.claude/|CLAUDE\.md$)' <<<"$staged" || true)
other=$(grep -cvE '^(\.claude/|CLAUDE\.md$)' <<<"$staged" || true)
if [ "$claude" -gt 0 ] && [ "$other" -gt 0 ]; then
    printf 'claude-kind files mixed with another kind — split the commit (one kind per commit):\n'
    sed 's/^/  /' <<<"$staged"
    exit 1
fi
