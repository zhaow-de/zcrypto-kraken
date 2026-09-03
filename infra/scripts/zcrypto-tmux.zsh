#!/usr/bin/env zsh
# zcrypto-tmux.zsh -- rebuild the zcrypto tmux cockpit after a workstation restart. Idempotent.
# Lives in the repo; `~/.local/bin/zcrypto-tmux` is a symlink to it so it stays on PATH.
#
# Layout (one tmux session, COCKPIT, one window):
#   +---------------+---------------+
#   |               | zcrypto-alex  |
#   | zcrypto-main  +---------------+
#   |               | zcrypto-bravo |
#   +---------------+---------------+
# plus a separate tmux session `zcrypto-zebra` -- the owner's own shell at the repo root, no
# Claude session started there.
#
# Each cockpit pane cd's into the repo and resumes the Claude Code session of its name, resolved
# to its session ID through <project>/<id>/custom-title.json -- resuming by ID never lands in the
# interactive picker that a bare title can open. A name with no titled session gets a fresh one
# via `claude --name`. Newest titled match wins if a title is duplicated.
#
# Idempotent per tmux session: a session that already exists is left alone (a pane that died inside
# an existing cockpit is not rebuilt -- kill the session and re-run). Env knobs, for testing:
#   ZCRYPTO_TMUX_SOCKET=<name>  use `tmux -L <name>` instead of the default server
#   ZCRYPTO_TMUX_DRY=1          echo each pane's command in the pane instead of running it
set -euo pipefail
setopt null_glob

REPO=${0:A:h:h:h}                                   # infra/scripts/<this> -> the repo root
PROJ=$HOME/.claude/projects/${REPO//\//-}            # Claude Code's project dir: the path with / -> -
COCKPIT=zcrypto-main
ZEBRA=zcrypto-zebra
typeset -a TMUX
TMUX=(tmux)
[[ -n ${ZCRYPTO_TMUX_SOCKET:-} ]] && TMUX=(tmux -L "$ZCRYPTO_TMUX_SOCKET")

# session_id <title> -> newest session dir whose custom-title.json carries exactly that title, or ""
session_id() {
  local title=$1 f best="" best_m=0 m
  for f in "$PROJ"/*/custom-title.json; do
    grep -qF "\"customTitle\":\"$title\"" "$f" || continue
    m=$(stat -c %Y "$f")
    (( m > best_m )) && { best_m=$m; best=${f:h:t}; }
  done
  print -r -- "$best"
}

# claude_cmd <title> -> the command that resumes (by id) or creates (by name) that session
claude_cmd() {
  local title=$1 id
  id=$(session_id "$title")
  if [[ -n $id ]]; then print -r -- "claude --resume $id"; else print -r -- "claude --name '$title'"; fi
}

pane_cmd() {
  local cmd; cmd=$(claude_cmd "$1")
  if [[ -n ${ZCRYPTO_TMUX_DRY:-} ]]; then print -r -- "cd $REPO && echo DRY: $cmd"; else print -r -- "cd $REPO && $cmd"; fi
}

if ! "${TMUX[@]}" has-session -t "=$COCKPIT" 2>/dev/null; then
  "${TMUX[@]}" new-session -d -s "$COCKPIT" -n cockpit -c "$REPO"
  left=$("${TMUX[@]}" display-message -p -t "${COCKPIT}:cockpit" '#{pane_id}')
  [[ -n $left ]] || { print -u2 -- 'zcrypto-tmux: could not resolve the cockpit pane'; exit 1; }
  right=$("${TMUX[@]}" split-window -h -t "$left" -c "$REPO" -P -F '#{pane_id}')
  lower=$("${TMUX[@]}" split-window -v -t "$right" -c "$REPO" -P -F '#{pane_id}')
  "${TMUX[@]}" select-pane -t "$left"  -T zcrypto-main
  "${TMUX[@]}" select-pane -t "$right" -T zcrypto-alex
  "${TMUX[@]}" select-pane -t "$lower" -T zcrypto-bravo
  "${TMUX[@]}" set-option -w -t "${COCKPIT}:cockpit" pane-border-status top   # titles visible, this window only
  "${TMUX[@]}" send-keys -t "$left"  "$(pane_cmd zcrypto-main)"  C-m
  "${TMUX[@]}" send-keys -t "$right" "$(pane_cmd zcrypto-alex)"  C-m
  "${TMUX[@]}" send-keys -t "$lower" "$(pane_cmd zcrypto-bravo)" C-m
  "${TMUX[@]}" select-pane -t "$left"
  print -r -- "zcrypto-tmux: created $COCKPIT (main | alex / bravo)"
else
  print -r -- "zcrypto-tmux: $COCKPIT exists, left alone"
fi

if ! "${TMUX[@]}" has-session -t "=$ZEBRA" 2>/dev/null; then
  "${TMUX[@]}" new-session -d -s "$ZEBRA" -c "$REPO"
  "${TMUX[@]}" send-keys -t "$ZEBRA" "cd $REPO" C-m
  print -r -- "zcrypto-tmux: created $ZEBRA"
else
  print -r -- "zcrypto-tmux: $ZEBRA exists, left alone"
fi
