#!/usr/bin/env bash
# The mutate -> measure -> restore cycle with its recorded traps closed (spec 00082 D4):
#   * refuses a dirty worktree (restore uses `git checkout --`, which destroys uncommitted work)
#   * --sandbox seeds from `git archive HEAD` (never cp -a) and REFUSES pytest there (the editable
#     install's .pth resolves cli/tests to the repo, so every verdict would measure unmutated code)
#   * PYTHONDONTWRITEBYTECODE=1 + __pycache__ purge (a same-second same-length mutation re-runs a
#     stale .pyc otherwise)
#   * the probe must PASS on the UNMUTATED target before anything is mutated (exit 7) -- an
#     always-failing probe command (wrong path, broken invocation) makes the control "fail" for a
#     reason unrelated to the mutation, and then scores every real mutation KILLED with "control
#     proven" attached to the lie
#   * the CONTROL mutation must FAIL the probe before any real probe counts -- an unproven harness
#     proves nothing (the guard-proving rule as code)
# Usage: mutate-probe.sh [--sandbox] --file <path> --control <sed-expr> --mutation <sed-expr> -- <probe-cmd...>
# Exit: rc 2 usage | rc 3 refused (dirty worktree, or pytest under --sandbox) | rc 4 restore failed
#     | rc 5 control did not fail | rc 6 no-op sed | rc 7 baseline failed | rc 8 seeding failed
#     | rc 9 cleanup restore failed (pristine kept)
set -euo pipefail

sandbox=0; file=""; control=""; mutation=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sandbox) sandbox=1; shift ;;
    --file) file="$2"; shift 2 ;;
    --control) control="$2"; shift 2 ;;
    --mutation) mutation="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "mutate-probe: unknown arg $1" >&2; exit 2 ;;
  esac
done
[[ -n "$file" && -n "$control" && -n "$mutation" && $# -gt 0 ]] || { echo "usage: mutate-probe.sh [--sandbox] --file F --control SED --mutation SED -- CMD..." >&2; exit 2; }

# ONE handler for both temporaries — the sandbox dir (sandbox mode only) and the pristine copy (both
# modes). A second `trap ... EXIT` would REPLACE this one rather than add to it, leaking whichever
# it displaced on every run.
#
# It RESTORES BEFORE IT CLEANS, and it runs on INT/TERM as well as EXIT. A signal delivered while the
# probe runs (a hung probe killed, an interactive Ctrl-C) lands with the mutation applied to the
# target: cleaning first would delete the pristine copy that is the only way back, leaving the file
# mutated on disk — the worst possible failure for a script whose whole job is safe restoration.
work=""; pristine=""; mutated=0; cleaned=0
cleanup() {
  if [[ $cleaned -eq 1 ]]; then return 0; fi   # INT/TERM handlers are followed by EXIT — run once
  cleaned=1
  if [[ $mutated -eq 1 && -n "$pristine" && -f "$pristine" ]]; then
    if ! cp "$pristine" "$file"; then
      # KEEP the pristine copy — it is the only way back to the unmutated content.
      echo "mutate-probe: cleanup restore FAILED — $file may still carry the mutation; pristine copy KEPT at $pristine" >&2
      if [[ -n "$work" ]]; then rm -rf "$work"; fi
      exit 9
    fi
  fi
  if [[ -n "$work" ]]; then rm -rf "$work"; fi
  if [[ -n "$pristine" ]]; then rm -f "$pristine"; fi
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

if [[ $sandbox -eq 1 ]]; then
  # Substring match, so a probe merely NAMED like pytest (or any argument under a .../pytest/... path)
  # is refused too. Deliberate: over-refusing costs a rename, under-refusing silently measures
  # unmutated code.
  for w in "$@"; do case "$w" in *pytest*) echo "mutate-probe: REFUSING pytest in --sandbox — the editable install's .pth resolves cli/tests to the REPO, so the verdict measures unmutated code. Mutate in-repo on a committed tree instead." >&2; exit 3 ;; esac; done
  work="$(mktemp -d)"
  if ! git archive HEAD | tar -x -C "$work"; then
    echo "mutate-probe: sandbox seeding FAILED (git archive HEAD | tar) — no verdict; nothing was mutated." >&2
    exit 8
  fi
  cd "$work"
else
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "mutate-probe: REFUSING — worktree dirty; restore uses 'git checkout --', which would destroy uncommitted work. Commit or stash first." >&2; exit 3
  fi
fi

export PYTHONDONTWRITEBYTECODE=1
purge() { find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true; }

# I6a: restore must work in BOTH modes — the sandbox has no .git, so keep a pristine copy and
# restore from it; in-repo, git is authoritative and the byte-identity check is the proof.
pristine="$(mktemp)"; cp "$file" "$pristine"
restore() {
  if [[ $sandbox -eq 0 ]]; then
    git checkout -q -- "$file"
    git diff --quiet -- "$file" || { echo "mutate-probe: restore FAILED for $file" >&2; exit 4; }
  else
    cp "$pristine" "$file"
  fi
  cmp -s "$pristine" "$file" || { echo "mutate-probe: restore FAILED for $file (differs from pristine copy)" >&2; exit 4; }
  mutated=0
}

# I6b: a sed expression that matches nothing silently no-ops (the str.replace trap) — a probe on
# unmutated code is a false SURVIVED. Every apply must prove the file actually changed.
apply() {   # apply <sed-expr> <phase: "control sed"|"mutation sed">
  mutated=1   # BEFORE the write: a signal landing between sed and the flag would strand the file
  sed -i "$1" "$file"
  if cmp -s "$pristine" "$file"; then
    echo "mutate-probe: $2 '$1' did not change $file — a no-op sed proves nothing. Fix the expression." >&2
    exit 6
  fi
  purge
}

# 0. baseline: the probe must PASS on UNMUTATED code, or the control's failure says nothing about the
# control. Run it under the SAME conditions as the real probes -- bytecode export set, caches purged --
# or the baseline is not comparable to what follows.
purge
if ! "$@" >/dev/null 2>&1; then
  echo "mutate-probe: baseline failed — the probe must pass on unmutated code. Fix the probe command (or the tree) before any verdict here means anything." >&2
  exit 7
fi

# 1. control: must FAIL, or the harness is not measuring
apply "$control" "control sed"
if "$@" >/dev/null 2>&1; then restore; echo "mutate-probe: CONTROL mutation did not fail the probe — the harness does not bite; no real probe counts. Pick a control the probe must detect." >&2; exit 5; fi
restore

# 2. the real mutation
apply "$mutation" "mutation sed"
if "$@" >/dev/null 2>&1; then verdict=SURVIVED; else verdict=KILLED; fi
restore; purge
echo "mutate-probe: $verdict (control proven, tree restored byte-identically)"
[[ "$verdict" == KILLED || "$verdict" == SURVIVED ]]
