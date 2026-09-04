#!/usr/bin/env zsh
# Transports the full working environment between the workstation (ZhaoPrecision.fritz.box) and
# the ops node (z-home-zcrypto.zhaow.pro) so work continues on the other machine exactly where it
# left off (T0086). Run it ON THE SOURCE machine; the destination is inferred (or named as $1).
#
#   usage: workspace-transport.sh [destination-fqdn] [-y|--yes]
#          -y skips the interactive confirmation (required when there is no terminal)
#
# What moves: the repo's git state including UNPUSHED branches and tags (via git bundle -- this repo
# keeps branches local until PR-open, so origin cannot align them), .local/ (gitignored and kept:
# the memo -- hand-edited, unrecoverable if lost -- the coordination table, the lesson inboxes,
# retro artefacts), ~/.claude/ session state (transcripts, memory, plugins set
# AND versions), ~/.claude.json (MCP servers, project trust), the /tmp scratchpad, and the repo's
# .superpowers/ SDD ledgers. What deliberately does NOT move: auth material
# (~/.claude/.credentials.json, ssh/sops/gh/vault -- already aligned on both machines, owner's
# ruling 2026-07-21), machine-local caches, IDE lock files and daemon runtime, and the data/ root
# (regenerable -- the post-steps printed at the end re-derive it).
#
# The destination is made to MIRROR the source. Two classes of destruction, deliberately unequal:
#   - git refs: a destination-only branch is deleted only when its commits are contained in one of
#     the SOURCE's OWN LOCAL branches (never a remote-tracking ref -- that is a local cache, not
#     evidence the remote still has it). Anything else aborts the run before a byte moves.
#   - non-git state (.local/, ~/.claude/): there is no equivalent proof available, so the plan
#     shows what would be destroyed (a memo digest comparison, an rsync --delete dry run) and the
#     destination's .local/ is backed up outside the repo before it is overwritten.
#
# QUIET-POINT DISCIPLINE (run this only at a quiet point, immediately before switching):
#   - no Claude session, background agent, or workflow mid-flight on EITHER machine -- running
#     processes do not transfer, and a live session mutates state mid-rsync;
#   - the /tmp scratchpad copy is only as durable as the destination's uptime (/tmp does not
#     survive a reboot) -- transfer right before you switch, not hours ahead;
#   - the two machines are never used simultaneously: everything here assumes the destination is
#     idle and its state is an older copy of the source's. Both repos must be clean (no uncommitted
#     changes, no stashes, no linked worktrees) or the script aborts before touching anything. A
#     destination branch AHEAD of the source's same-named branch is force-rewound (the reflog
#     retains it) -- committed work must always transfer back before switching.

set -euo pipefail

REPO_DIR="$HOME/Projects/zcrypto-kraken"
PROJECT_SLUG="-home-zhaow-Projects-zcrypto-kraken"
WORKSTATION_FQDN="ZhaoPrecision.fritz.box"
OPS_FQDN="z-home-zcrypto.zhaow.pro"
BUNDLE="/tmp/zcrypto-workspace-transport.bundle"
# Direction/freshness evidence + incomplete-transfer marker. Lives OUTSIDE ~/.claude on purpose:
# inside it, the very rsync --delete this script runs would clobber the destination's copy.
SENTINEL="$HOME/.zcrypto-workspace-transport"

# One transport config for ssh/scp/rsync alike, so a preflight that passes cannot be followed by a
# transfer that authenticates differently.
SSH_OPTS=(-o ConnectTimeout=10)
SSH=(ssh "${SSH_OPTS[@]}")
RSYNC=(rsync -az -e "ssh ${SSH_OPTS[*]}")

# `print -r --`: git C-quotes odd paths ("a\tb.md"), and without -r print would turn the literal
# backslash-t into a tab and mangle the path being reported.
die() { print -r -u2 -- "workspace-transport: $1"; exit 1 }
remote() { "${SSH[@]}" "$DEST" "$@" }

# Every abort path leaks a ~10 MB bundle without this; the remote copy is removed explicitly below.
trap 'rm -f "$BUNDLE"' EXIT INT TERM

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

# Identify the peer over the channel we just proved, not by string-comparing a FQDN against a short
# hostname (which never matches, and misses localhost / an IP / an ssh alias). A self-targeted run
# is a no-op that leaves the operator believing the other machine was updated.
PEER_HOST="$(remote 'hostname -s')" || die "could not identify the destination host -- nothing was touched"
[[ "$PEER_HOST" != "$SRC_HOST" ]] \
  || die "destination '$DEST' resolves to the source host ($SRC_HOST) -- nothing was touched"

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

# `status --porcelain` reports the MAIN worktree only. A linked worktree holding one of the branches
# we are about to force-update makes `fetch --force refs/heads/*` abort wholesale (git refuses to
# fetch into a checked-out branch) -- and it would abort AFTER the detach, leaving the destination
# detached and every re-run reproducing it. This repo's own rules hand subagents worktrees, so it is
# a live possibility, and the mirror model has no story for them: refuse up front.
dest_worktrees="$(remote "git -C ${(q)REPO_DIR} worktree list --porcelain")" \
  || die "could not list the destination's worktrees -- nothing was touched"
dest_wt_count="$(grep -c '^worktree ' <<< "$dest_worktrees" || true)"
(( dest_wt_count == 1 )) \
  || die "destination has linked git worktrees -- remove them on $DEST first, nothing was touched:
$dest_worktrees"

CURRENT_BRANCH="$(git -C "$REPO_DIR" branch --show-current)"
[[ -n "$CURRENT_BRANCH" ]] || die "source HEAD is detached -- check out a branch first"
HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"

# --- classify the destination-only branches (still no writes) ----------------------------------
# `lstrip=2`, not `refname:short`: short renders `heads/feat` when a tag shares the name, and the
# deletion below would then target a ref that does not exist.
src_branches="$(git -C "$REPO_DIR" for-each-ref --format='%(refname:lstrip=2)' refs/heads)"
typeset -A SRC_SET
for b in ${(f)src_branches}; do SRC_SET[$b]=1; done

dest_refs="$(remote "git -C ${(q)REPO_DIR} for-each-ref --format='%(refname:lstrip=2) %(objectname)' refs/heads")" \
  || die "could not list the destination's branches -- nothing was touched"

typeset -a DELETABLE UNRECOVERABLE
while IFS=' ' read -r dname dsha; do
  [[ -n "$dname" ]] || continue
  # Associative-array membership, not `grep -qx`: a branch name is not a regex (`fix/bug$` fails to
  # match its own line), and `grep -q` SIGPIPEs its producer, which under `pipefail` reports 141 --
  # i.e. "not on the source" -- for EVERY branch once the list is long enough.
  if (( ${+SRC_SET[$dname]} )); then continue; fi
  # Recoverable iff one of the SOURCE's own local branches contains the commit. Deliberately not
  # `--all`: a remote-tracking ref is a local cache, and a force-push or a closed-unmerged PR leaves
  # it naming a commit the remote no longer has -- deleting the destination's only copy on that
  # evidence is exactly the loss this gate exists to prevent. Every source local branch ships in the
  # bundle, so the surviving invariant is checkable: anything deleted here still exists on BOTH
  # machines under a named branch.
  if git -C "$REPO_DIR" cat-file -e "${dsha}^{commit}" 2>/dev/null \
     && [[ -n "$(git -C "$REPO_DIR" branch --contains "$dsha" 2>/dev/null)" ]]; then
    DELETABLE+=("$dname $dsha")
  else
    UNRECOVERABLE+=("$dname @ ${dsha:0:9}")
  fi
done <<< "$dest_refs"

if (( ${#UNRECOVERABLE} )); then
  die "destination-only branches carry commits that exist NOWHERE else -- refusing to mirror.
$(printf '  %s\n' "${UNRECOVERABLE[@]}")
  Push them from $DEST and then run 'git fetch --all' HERE, or transfer them back,
  or delete them by hand on $DEST, then re-run.
  Nothing was touched."
fi

# --- what the non-git half would destroy (no proof available, so: disclose) --------------------
CLAUDE_EXCLUDES=(
  --exclude='.credentials.json'
  --exclude='/cache/'
  --exclude='/paste-cache/'
  --exclude='/downloads/'
  --exclude='/shell-snapshots/'
  --exclude='/session-env/'
  --exclude='/ide/'
  --exclude='/daemon' --exclude='/daemon.lock' --exclude='/daemon.log' --exclude='/daemon.status.json'
  --exclude='/gh-pr-status-cache.json' --exclude='/mcp-needs-auth-cache.json' --exclude='/stats-cache.json'
  --exclude='/.last-cleanup' --exclude='/.last-update-result.json'
)
src_memo_sum="$(md5sum "$REPO_DIR/.local/memo.md" 2>/dev/null | cut -d' ' -f1 || true)"
dst_memo_sum="$(remote "md5sum ${(q)REPO_DIR}/.local/memo.md 2>/dev/null | cut -d' ' -f1" || true)"
claude_deletes="$("${RSYNC[@]}" -n --delete "${CLAUDE_EXCLUDES[@]}" \
  "$HOME/.claude/" "$DEST:.claude/" 2>/dev/null | grep -c '^deleting ' || true)"
dest_sentinel="$(remote "cat ${(q)SENTINEL} 2>/dev/null" || true)"

# --- the plan, then the gate -------------------------------------------------------------------
print -r -- "
workspace-transport plan
  source        : $SRC_HOST
  destination   : $DEST ($PEER_HOST)
  repo          : $REPO_DIR
  will check out: $CURRENT_BRANCH @ ${HEAD_SHA:0:9}
                  (all local branches + tags force-updated from a bundle; a destination branch
                   AHEAD of the source's same-named branch is rewound -- reflog keeps it)"
if (( ${#DELETABLE} )); then
  print -r -- "  will DELETE   : destination-only branches (commits contained in a source branch):"
  for entry in "${DELETABLE[@]}"; do print -r -- "                  ${entry%% *}"; done
else
  print -r -- "  will delete   : no branches (destination has none the source lacks)"
fi
if [[ -n "$dst_memo_sum" && "$src_memo_sum" != "$dst_memo_sum" ]]; then
  print -r -- "  .local/memo.md: destination copy DIFFERS and will be discarded (the destination's
                  .local/ is backed up on $DEST to ~/.zcrypto-local.pre-transport/) -- it is
                  gitignored, so no clean-repo check can protect it. Make sure the newer copy is
                  the one here."
else
  print -r -- "  .local/memo.md: identical on both machines"
fi
print -r -- "  ~/.claude/    : rsync --delete would remove $claude_deletes destination path(s)
                  (transcripts + memory live here and exist on no remote)"
[[ -z "$dest_sentinel" ]] \
  && print -r -- "  last transport: destination has no record of a previous transport" \
  || print -r -- "  last transport: $dest_sentinel"
print -r -- ""

if (( ! ASSUME_YES )); then
  # `[[ -r /dev/tty ]]` is access(2) on a 0666 device node -- true under setsid/cron/CI, where the
  # read then fails and `set -e` exits before the die below can ever print. Opening it is the only
  # honest test.
  exec {tty_fd}</dev/tty 2>/dev/null \
    || die "no terminal available for confirmation -- re-run from a shell, or pass -y to accept this plan"
  print -n "Proceed? [yes/N] "
  read -r reply <&$tty_fd || reply=""     # bare `read` at EOF (Ctrl-D) would exit silently under -e
  exec {tty_fd}<&-
  [[ "$reply" == "yes" || "$reply" == "y" ]] || die "aborted by operator -- nothing was touched"
fi

# --- from here on the destination is being written ---------------------------------------------
STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
remote "print -r -- 'from $SRC_HOST at $STARTED_AT -- IN PROGRESS' > ${(q)SENTINEL}" || true

print "aligning git state: branch '$CURRENT_BRANCH' @ ${HEAD_SHA:0:9} + all local branches and tags"
git -C "$REPO_DIR" bundle create "$BUNDLE" --branches --tags
scp "${SSH_OPTS[@]}" -q "$BUNDLE" "$DEST:$BUNDLE"

# Detach FIRST, then delete, then fetch. Order is load-bearing: a destination sitting on a
# destination-only branch cannot have it deleted while checked out, and a stale branch named `fix`
# blocks fetching `fix/anything` (a ref file where git needs a directory) -- so deleting after the
# fetch would deadlock the run permanently, since the fetch that fails is what gates the deletion.
remote "git -C ${(q)REPO_DIR} checkout -q --detach" \
  || die "destination detach FAILED -- nothing was fetched; inspect $DEST"

for entry in "${DELETABLE[@]}"; do
  b="${entry%% *}"; sha="${entry##* }"
  # Delete by SHA, not by name: classification and this moment are separated by a human-length
  # confirmation pause. update-ref refuses if the ref moved in between.
  remote "git -C ${(q)REPO_DIR} update-ref -d refs/heads/${(q)b} ${(q)sha}" \
    || die "failed to delete destination-only branch '$b' on $DEST (did it move since the plan was shown?)"
  print -r -- "  deleted destination-only branch: $b"
done

remote "git -C ${(q)REPO_DIR} fetch -q --atomic --force ${(q)BUNDLE} \
    'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*' \
  && git -C ${(q)REPO_DIR} checkout -q ${(q)CURRENT_BRANCH}" \
  || die "destination git alignment FAILED -- the destination is left DETACHED; inspect $DEST before re-running"
remote "rm -f ${(q)BUNDLE}" || true
rm -f "$BUNDLE"

# --- .local/ (gitignored; nothing deleted from the memo is recoverable) ------------------------
# The backup lands in $HOME, never inside $REPO_DIR: an untracked file there would fail the
# both-repos-clean gate on the next run. The destination's .local/ is made to mirror the source's.
remote "rm -rf ~/.zcrypto-local.pre-transport && cp -pr ${(q)REPO_DIR}/.local ~/.zcrypto-local.pre-transport 2>/dev/null || true"
"${RSYNC[@]}" --delete "$REPO_DIR/.local/" "$DEST:$REPO_DIR/.local/"

# --- session state -----------------------------------------------------------------------------
# ~/.claude/: everything except machine-local runtime/caches and auth material.
# Excludes are ANCHORED (leading /) to the ~/.claude top level: an unanchored 'cache/' would also
# match plugins/cache/ -- which is not a cache but the pinned plugin payloads (installed_plugins.json
# points installPath into it), exactly the "plugin silently absent on the other machine" failure this
# transfer exists to prevent. .credentials.json stays unanchored deliberately (defensive, both ends).
# /ide/ is excluded because it holds lock files keyed to this machine's ports and PIDs.
"${RSYNC[@]}" --delete "${CLAUDE_EXCLUDES[@]}" "$HOME/.claude/" "$DEST:.claude/"
# MCP servers + project trust/allowlists -- without this the destination session has different tools.
# NOTE: this file also carries machineID/userID/installMethod; same account both ends, so benign
# today, but it is why the file is copied whole rather than merged.
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

# Written LAST: an interrupted run leaves "IN PROGRESS" on the destination, so the next plan (and
# the operator walking over to work there) can tell a completed transfer from a half-finished one.
FINISHED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
remote "print -r -- 'from $SRC_HOST at $FINISHED_AT -- COMPLETE' > ${(q)SENTINEL}" || true
print -r -- "from $PEER_HOST at $FINISHED_AT -- SENT" > "$SENTINEL" || true

# --- done: what the destination still has to regenerate locally --------------------------------
print "
transfer complete. On $DEST, before working:
  cd ~/Projects/zcrypto-kraken
  uv sync                       # .venv is machine-local
  git fetch --prune origin      # bundle carries branches+tags, not remote-tracking refs
  uv run zcrypto data fetch     # data/ root is regenerable from the NAS hub mirror, never rsynced
  uv run zcrypto engine seed    # price store
(the first 'uv run pre-commit run -a' is slower while ~/.cache/pre-commit repopulates)"
