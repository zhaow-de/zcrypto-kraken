#!/usr/bin/env zsh
# Transports the full working environment between the workstation (ZhaoPrecision.fritz.box) and
# the ops node (z-home-zcrypto.zhaow.pro) so work continues on the other machine exactly where it
# left off (T0086). Run it ON THE SOURCE machine; the destination is inferred (or named as $1).
#
#   usage: workspace-transport.sh [destination-fqdn] [-y|--yes]
#          -y skips the interactive confirmation (required when there is no terminal)
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
# The destination is made to MIRROR the source: branches the destination has and the source does
# not are DELETED there, after the transfer and only when their commits are recoverable (contained
# in some source branch or on a remote). A destination-only branch carrying commits that exist
# nowhere else means the never-simultaneous assumption was already broken -- the script aborts
# before touching anything rather than destroying the only copy.
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

# One transport config for ssh/scp/rsync alike, so a preflight that passes cannot be followed by a
# transfer that authenticates differently.
SSH_OPTS=(-o ConnectTimeout=10)
SSH=(ssh "${SSH_OPTS[@]}")
RSYNC=(rsync -az -e "ssh ${SSH_OPTS[*]}")

die() { print -u2 "workspace-transport: $1"; exit 1 }
remote() { "${SSH[@]}" "$DEST" "$@" }

# --- arguments ---------------------------------------------------------------------------------
ASSUME_YES=0
typeset -a POSITIONAL
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -*)       die "unknown option: $arg (usage: $0 [destination-fqdn] [-y])" ;;
    *)        POSITIONAL+=("$arg") ;;
  esac
done
(( ${#POSITIONAL} <= 1 )) || die "at most one destination may be given, got: ${POSITIONAL[*]}"

# --- destination -------------------------------------------------------------------------------
# Match on `hostname -s`, which is NOT the DNS label: the ops node answers `zcrypto-ops` while its
# FQDN is z-home-zcrypto.zhaow.pro. Matching the DNS label alone is the T0086 first-run defect --
# the script refused to infer a destination on the very host it was written for.
SRC_HOST="$(hostname -s)"
case "$SRC_HOST" in
  ZhaoPrecision)              DEST="${POSITIONAL[1]:-$OPS_FQDN}" ;;
  zcrypto-ops|z-home-zcrypto) DEST="${POSITIONAL[1]:-$WORKSTATION_FQDN}" ;;
  *) DEST="${POSITIONAL[1]:-}"
     [[ -n "$DEST" ]] || die "unknown source host '$SRC_HOST': pass the destination FQDN as \$1" ;;
esac
[[ "$DEST" != "$SRC_HOST" ]] || die "destination equals the source host ($SRC_HOST)"

# --- preflight: reachability, BEFORE any state question ----------------------------------------
# Load-bearing separation. ssh exits 255 when it cannot connect or verify a host key, so folding
# reachability into a state check ("ssh ... || die 'repo is dirty'") reports a dirty repo it never
# managed to query -- the exact false diagnosis this script emitted on 2026-07-21 when the
# destination was missing from known_hosts. Connectivity is proven first, and every later remote
# call distinguishes "the command failed" from "the answer was non-empty".
if ! probe_err="$("${SSH[@]}" "$DEST" true 2>&1)"; then
  die "cannot reach '$DEST' over ssh -- nothing was touched.
  ssh said: ${probe_err:-(no output)}
  'Host key verification failed' here means $DEST is absent from ~/.ssh/known_hosts on $SRC_HOST;
  connect once by hand to record it, then re-run."
fi
remote "test -d ${(q)REPO_DIR}/.git" \
  || die "destination '$DEST' has no git repo at $REPO_DIR -- nothing was touched"

# --- state, gathered before anything is written ------------------------------------------------
[[ -z "$(git -C "$REPO_DIR" status --porcelain)" ]] || die "source repo is dirty -- commit or discard first"
[[ -z "$(git -C "$REPO_DIR" stash list)" ]]         || die "source repo has stashes -- clear them first (stashes do not transfer)"

dest_status="$(remote "git -C ${(q)REPO_DIR} status --porcelain")" \
  || die "could not read the destination repo's status -- nothing was touched"
[[ -z "$dest_status" ]] \
  || die "DESTINATION repo is dirty -- it has work the transfer would clobber; resolve there first.
$dest_status"
dest_stashes="$(remote "git -C ${(q)REPO_DIR} stash list")" \
  || die "could not read the destination repo's stash list -- nothing was touched"
[[ -z "$dest_stashes" ]] || die "DESTINATION repo has stashes -- resolve there first"

CURRENT_BRANCH="$(git -C "$REPO_DIR" branch --show-current)"
[[ -n "$CURRENT_BRANCH" ]] || die "source HEAD is detached -- check out a branch first"
HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"

# --- classify the destination-only branches (still no writes) ----------------------------------
src_branches="$(git -C "$REPO_DIR" for-each-ref --format='%(refname:short)' refs/heads)"
dest_refs="$(remote "git -C ${(q)REPO_DIR} for-each-ref --format='%(refname:short) %(objectname)' refs/heads")" \
  || die "could not list the destination's branches -- nothing was touched"

typeset -a DELETABLE UNRECOVERABLE
while IFS=' ' read -r dname dsha; do
  [[ -n "$dname" ]] || continue
  print -r -- "$src_branches" | grep -qx -- "$dname" && continue      # also on the source: not dest-only
  # Recoverable iff the source already has that commit reachable from one of its own refs
  # (local branch or remote-tracking), i.e. deleting the destination copy loses nothing.
  if git -C "$REPO_DIR" cat-file -e "${dsha}^{commit}" 2>/dev/null \
     && [[ -n "$(git -C "$REPO_DIR" branch --all --contains "$dsha" 2>/dev/null)" ]]; then
    DELETABLE+=("$dname")
  else
    UNRECOVERABLE+=("$dname @ ${dsha:0:9}")
  fi
done <<< "$dest_refs"

if (( ${#UNRECOVERABLE} )); then
  die "destination-only branches carry commits that exist NOWHERE else -- refusing to mirror.
$(printf '  %s\n' "${UNRECOVERABLE[@]}")
  Push them, transfer them back, or delete them by hand on $DEST, then re-run.
  Nothing was touched."
fi

# --- the plan, then the gate -------------------------------------------------------------------
print "
workspace-transport plan
  source        : $SRC_HOST
  destination   : $DEST
  repo          : $REPO_DIR
  will check out: $CURRENT_BRANCH @ ${HEAD_SHA:0:9}  (all local branches force-updated from a bundle)"
if (( ${#DELETABLE} )); then
  print "  will DELETE on the destination (destination-only, commits recoverable elsewhere):"
  printf '                  %s\n' "${DELETABLE[@]}"
else
  print "  will delete   : nothing (destination has no branches the source lacks)"
fi
print "  will mirror   : memo.local.md, ~/.claude/, ~/.claude.json, scratchpad, .superpowers/  (rsync --delete)
"

if (( ! ASSUME_YES )); then
  [[ -r /dev/tty ]] \
    || die "no terminal available for confirmation -- re-run from a shell, or pass -y to accept this plan"
  print -n "Proceed? [yes/N] "
  read -r reply < /dev/tty
  [[ "$reply" == "yes" || "$reply" == "y" ]] || die "aborted by operator -- nothing was touched"
fi

# --- git state: bundle every local branch, align the destination -------------------------------
print "aligning git state: branch '$CURRENT_BRANCH' @ ${HEAD_SHA:0:9} + all local branches"
git -C "$REPO_DIR" bundle create "$BUNDLE" --branches
scp "${SSH_OPTS[@]}" -q "$BUNDLE" "$DEST:$BUNDLE"
# Detach first so the fetch may update the checked-out branch, then land on the source's branch.
remote "git -C ${(q)REPO_DIR} checkout -q --detach \
  && git -C ${(q)REPO_DIR} fetch -q --force ${(q)BUNDLE} 'refs/heads/*:refs/heads/*' \
  && git -C ${(q)REPO_DIR} checkout -q ${(q)CURRENT_BRANCH} \
  && rm -f ${(q)BUNDLE}" \
  || die "destination git alignment FAILED -- the destination may be mid-update; inspect $DEST before re-running"
rm -f "$BUNDLE"

# Mirror the branch set. Safe by construction: the destination is now on CURRENT_BRANCH (which the
# source has, so it is never in this list), and every name here was proven recoverable above.
for b in "${DELETABLE[@]}"; do
  remote "git -C ${(q)REPO_DIR} branch -D ${(q)b}" >/dev/null \
    || die "failed to delete destination-only branch '$b' on $DEST"
  print "  deleted destination-only branch: $b"
done

# --- the memo (gitignored; nothing deleted from it is recoverable) -----------------------------
scp "${SSH_OPTS[@]}" -pq "$REPO_DIR/docs/memo.local.md" "$DEST:$REPO_DIR/docs/memo.local.md"

# --- session state -----------------------------------------------------------------------------
# ~/.claude/: everything except machine-local runtime/caches and auth material.
# Excludes are ANCHORED (leading /) to the ~/.claude top level: an unanchored 'cache/' would also
# match plugins/cache/ -- which is not a cache but the pinned plugin payloads (installed_plugins.json
# points installPath into it), exactly the "plugin silently absent on the other machine" failure this
# transfer exists to prevent. .credentials.json stays unanchored deliberately (defensive, both ends).
"${RSYNC[@]}" --delete \
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
"${RSYNC[@]}" "$HOME/.claude.json" "$DEST:.claude.json"
# The /tmp scratchpad (SDD review packages, diffs, task outputs) -- absent after a reboot.
if [[ -d "/tmp/claude-1000/$PROJECT_SLUG" ]]; then
  "${RSYNC[@]}" --delete --rsync-path="mkdir -p /tmp/claude-1000 && rsync" \
    "/tmp/claude-1000/$PROJECT_SLUG/" "$DEST:/tmp/claude-1000/$PROJECT_SLUG/"
fi
# The SDD progress ledgers inside the repo (gitignored).
if [[ -d "$REPO_DIR/.superpowers" ]]; then
  "${RSYNC[@]}" --delete "$REPO_DIR/.superpowers/" "$DEST:$REPO_DIR/.superpowers/"
fi

# --- done: what the destination still has to regenerate locally --------------------------------
print "
transfer complete. On $DEST, before working:
  cd ~/Projects/zcrypto-kraken
  uv sync                       # .venv is machine-local
  uv run zcrypto data fetch     # data/ root is regenerable from the NAS hub mirror, never rsynced
  uv run zcrypto engine seed    # price store
(the first 'uv run pre-commit run -a' is slower while ~/.cache/pre-commit repopulates)"
