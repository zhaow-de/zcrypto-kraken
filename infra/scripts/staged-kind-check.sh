#!/usr/bin/env bash
# claude-kind files (.claude/, CLAUDE.md) never share a commit with another kind
# Stage by explicit path, one kind per commit.
# Deliberate exception: SKIP=staged-kind git commit ...
set -euo pipefail
staged=$(git diff --cached --name-only)
[ -z "$staged" ] && exit 0
# A merge stages the union of both parents' kinds, which the author chose neither of, and splitting it is not a
# thing you can do -- the hook is about AUTHORING the two kinds together. Only the merge's OWN candidate files
# get that pass: during a stopped merge anything can be staged, so exempting the whole set would turn a visible
# `SKIP=staged-kind` into an invisible one.
mergehead="$(git rev-parse --git-dir)/MERGE_HEAD"
if [ -f "$mergehead" ]; then
    theirs="$(cat "$mergehead")"
    base="$(git merge-base HEAD "$theirs")"
    candidates="$( { git diff --name-only "$base" HEAD; git diff --name-only "$base" "$theirs"; } | sort -u)"
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
