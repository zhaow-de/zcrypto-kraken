#!/usr/bin/env zsh
# Transports the full working environment between the workstation (ZhaoPrecision.fritz.box) and
# the ops node (z-home-zcrypto.zhaow.pro) so work continues on the other machine exactly where it
# left off (T0086). Run it ON THE SOURCE machine; the destination is inferred (or named as $1).
#
# What moves: the repo's git state including UNPUSHED branches (via git bundle -- this repo keeps
# branches local until PR-open, so origin cannot align them), docs/memo.local.md (gitignored,
# hand-edited, unrecoverable if lost), ~/.claude/ session state (transcripts, memory, plugins set
# AND versions, jobs), ~/.claude.json (MCP servers, project trust), the /tmp scratchpad, and the
# repo's .superpowers/ SDD ledgers. What deliberately does NOT move: auth material
# (~/.claude/.credentials.json, ssh/sops/gh/vault -- already aligned on both machines, owner's
# ruling 2026-07-21), machine-local caches and daemon runtime, and the data/ root (regenerable --
# the post-steps printed at the end re-derive it).
#
# QUIET-POINT DISCIPLINE (run this only at a quiet point, immediately before switching):
#   - no Claude session, background agent, or workflow mid-flight on EITHER machine -- running
#     processes do not transfer, and a live session mutates state mid-rsync;
#   - the /tmp scratchpad copy is only as durable as the destination's uptime (/tmp does not
#     survive a reboot) -- transfer right before you switch, not hours ahead;
#   - the two machines are never used simultaneously: everything here assumes the destination is
#     idle and its state is an older copy of the source's. Both repos must be clean (no
#     uncommitted changes, no stashes) or the script aborts before touching anything. A
#     destination branch AHEAD of the source's same-named branch is rewound by the forced fetch
#     (the reflog retains it) -- committed work must always transfer back before switching.

set -euo pipefail

REPO_DIR="$HOME/Projects/zcrypto-kraken"
PROJECT_SLUG="-home-zhaow-Projects-zcrypto-kraken"
WORKSTATION_FQDN="ZhaoPrecision.fritz.box"
OPS_FQDN="z-home-zcrypto.zhaow.pro"
BUNDLE="/tmp/zcrypto-workspace-transport.bundle"

die() { print -u2 "workspace-transport: $1"; exit 1 }

# --- destination -------------------------------------------------------------------------------
case "$(hostname -s)" in
  ZhaoPrecision)  DEST="${1:-$OPS_FQDN}" ;;
  z-home-zcrypto) DEST="${1:-$WORKSTATION_FQDN}" ;;
  *)              DEST="${1:-}"; [[ -n "$DEST" ]] || die "unknown host $(hostname -s): pass the destination FQDN as \$1" ;;
esac
print "source: $(hostname -s)  ->  destination: $DEST"

# --- gate: both repos clean --------------------------------------------------------------------
[[ -z "$(git -C "$REPO_DIR" status --porcelain)" ]] || die "source repo is dirty -- commit or discard first"
[[ -z "$(git -C "$REPO_DIR" stash list)" ]]         || die "source repo has stashes -- clear them first (stashes do not transfer)"
ssh "$DEST" "[[ -z \"\$(git -C '$REPO_DIR' status --porcelain)\" ]]" \
  || die "DESTINATION repo is dirty -- it has work the transfer would clobber; resolve there first"
ssh "$DEST" "[[ -z \"\$(git -C '$REPO_DIR' stash list)\" ]]" \
  || die "DESTINATION repo has stashes -- resolve there first"

# --- git state: bundle every local branch, align the destination -------------------------------
CURRENT_BRANCH="$(git -C "$REPO_DIR" branch --show-current)"
[[ -n "$CURRENT_BRANCH" ]] || die "source HEAD is detached -- check out a branch first"
HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
print "aligning git state: branch '$CURRENT_BRANCH' @ ${HEAD_SHA:0:9} + all local branches"

git -C "$REPO_DIR" bundle create "$BUNDLE" --branches
scp -q "$BUNDLE" "$DEST:$BUNDLE"
# Detach first so the fetch may update the checked-out branch, then land on the source's branch.
ssh "$DEST" "git -C '$REPO_DIR' checkout -q --detach \
  && git -C '$REPO_DIR' fetch -q --force '$BUNDLE' 'refs/heads/*:refs/heads/*' \
  && git -C '$REPO_DIR' checkout -q '$CURRENT_BRANCH' \
  && rm -f '$BUNDLE'"
rm -f "$BUNDLE"

# Branches that exist only on the destination are stale-or-foreign: warn, never delete.
DEST_ONLY=$(comm -13 \
  <(git -C "$REPO_DIR" for-each-ref --format='%(refname:short)' refs/heads | sort) \
  <(ssh "$DEST" "git -C '$REPO_DIR' for-each-ref --format='%(refname:short)' refs/heads" | sort))
[[ -z "$DEST_ONLY" ]] || print "WARNING: destination-only branches (not touched, review by hand):\n$DEST_ONLY"

# --- the memo (gitignored; nothing deleted from it is recoverable) -----------------------------
scp -pq "$REPO_DIR/docs/memo.local.md" "$DEST:$REPO_DIR/docs/memo.local.md"

# --- session state -----------------------------------------------------------------------------
# ~/.claude/: everything except machine-local runtime/caches and auth material.
# Excludes are ANCHORED (leading /) to the ~/.claude top level: an unanchored 'cache/' would also
# match plugins/cache/ -- which is not a cache but the pinned plugin payloads (installed_plugins.json
# points installPath into it), exactly the "plugin silently absent on the other machine" failure this
# transfer exists to prevent. .credentials.json stays unanchored deliberately (defensive, both ends).
rsync -a --delete \
  --exclude='.credentials.json' \
  --exclude='/cache/' \
  --exclude='/paste-cache/' \
  --exclude='/downloads/' \
  --exclude='/shell-snapshots/' \
  --exclude='/session-env/' \
  --exclude='/daemon' --exclude='/daemon.lock' --exclude='/daemon.log' --exclude='/daemon.status.json' \
  --exclude='/gh-pr-status-cache.json' --exclude='/mcp-needs-auth-cache.json' --exclude='/stats-cache.json' \
  --exclude='/.last-cleanup' --exclude='/.last-update-result.json' \
  "$HOME/.claude/" "$DEST:.claude/"
# MCP servers + project trust/allowlists -- without this the destination session has different tools.
rsync -a "$HOME/.claude.json" "$DEST:.claude.json"
# The /tmp scratchpad (SDD review packages, diffs, task outputs) -- absent after a reboot.
if [[ -d "/tmp/claude-1000/$PROJECT_SLUG" ]]; then
  rsync -a --delete --rsync-path="mkdir -p /tmp/claude-1000 && rsync" \
    "/tmp/claude-1000/$PROJECT_SLUG/" "$DEST:/tmp/claude-1000/$PROJECT_SLUG/"
fi
# The SDD progress ledgers inside the repo (gitignored).
if [[ -d "$REPO_DIR/.superpowers" ]]; then
  rsync -a --delete "$REPO_DIR/.superpowers/" "$DEST:$REPO_DIR/.superpowers/"
fi

# --- done: what the destination still has to regenerate locally --------------------------------
print "
transfer complete. On $DEST, before working:
  cd ~/Projects/zcrypto-kraken
  uv sync                       # .venv is machine-local
  uv run zcrypto data fetch     # data/ root is regenerable from the NAS hub mirror, never rsynced
  uv run zcrypto engine seed    # price store
(the first 'uv run pre-commit run -a' is slower while ~/.cache/pre-commit repopulates)"
