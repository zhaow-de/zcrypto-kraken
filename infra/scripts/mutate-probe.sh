#!/usr/bin/env bash
# The mutate -> measure -> restore cycle with its traps closed (spec 00082 D4). It refuses a dirty
# worktree, because restore is `git checkout --` and would destroy uncommitted work; refuses pytest
# under `--sandbox`, because the editable install's .pth resolves cli and tests back to the repo so
# every verdict would measure unmutated code; requires the probe to PASS unmutated first, since an
# always-failing probe scores every mutation KILLED with "control proven" attached to the lie;
# requires the CONTROL mutation to FAIL, which is the guard-proving rule as code; refuses a control
# or mutation run that exits 5, pytest's "no tests ran", because a run that selected nothing is no kill; and
# refuses a mutation of a Python or shell file (not a .j2 template) that no longer parses, because the probe's failure is then the syntax's, not the guard's.
# Before the baseline it makes the parent of each `--basetemp=<path>` or `--basetemp <path>` in the probe command's words, resolved from the start directory, when inside the tree the probe runs in; one inside a longer word (`bash -c`, `PYTEST_ADDOPTS=`) or resolved by the command from elsewhere (`uv run --directory`, `env -C`) is the caller's to make.
# Usage: mutate-probe.sh [--sandbox] --file <path> --control <sed-expr> --mutation <sed-expr> -- <probe-cmd...>
# Exit: rc 2 usage, a control or mutation run that exited 5, a mutation that no longer parses, or a parse check that could not run | rc 3 refused (dirty tree, pytest in --sandbox, a second run in this checkout) | rc 4 restore failed | rc 5 control did not fail | rc 6 no-op sed
#     | rc 7 baseline failed | rc 8 seeding failed | rc 9 cleanup restore failed (pristine kept)
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

# ONE handler for every temporary: a second `trap ... EXIT` would REPLACE this one rather than add
# to it, leaking whichever it displaced. It restores BEFORE it cleans and runs on INT/TERM as well
# as EXIT, because a signal delivered while the probe runs lands with the mutation applied, and
# cleaning first would delete the only way back; INT/TERM inside it are ignored, so the restore's
# exit code stands.
work=""; pristine=""; uvtmp=""; mutated=0; cleaned=0
cleanup() {
  trap '' INT TERM
  if [[ $cleaned -eq 1 ]]; then return 0; fi   # INT/TERM handlers are followed by EXIT — run once
  cleaned=1
  if [[ $mutated -eq 1 && -n "$pristine" && -f "$pristine" ]]; then
    if ! cp "$pristine" "$file"; then
      # KEEP the pristine copy — it is the only way back to the unmutated content.
      echo "mutate-probe: cleanup restore FAILED — $file may still carry the mutation; pristine copy KEPT at $pristine" >&2
      if [[ -n "$work" ]]; then rm -rf "$work"; fi
      if [[ -n "$uvtmp" ]]; then rm -rf "$uvtmp"; fi
      exit 9
    fi
  fi
  if [[ -n "$work" ]]; then rm -rf "$work"; fi
  if [[ -n "$uvtmp" ]]; then rm -rf "$uvtmp"; fi
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
  # One probe per checkout: the restore is `git checkout --` over a file a second run may have mutated. The lock
  # is in the worktree's own git dir, so two worktrees of one repository still probe in parallel.
  lock="$(git rev-parse --absolute-git-dir)/mutate-probe.lock"
  exec 9>"$lock"
  if ! flock -n 9; then
    echo "mutate-probe: REFUSING — another mutate-probe holds $lock; one probe at a time in a checkout, each its own call after the previous verdict is read." >&2; exit 3
  fi
fi

export PYTHONDONTWRITEBYTECODE=1
# Without it tests/conftest.py's ledger deselects, from every run after the baseline, a slow case the baseline passed.
export ZCRYPTO_RERUN_SLOW=1
purge() { find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true; }

# I6a: restore must work in BOTH modes — the sandbox has no .git, so keep a pristine copy and
# restore from it; in-repo, git is authoritative and the byte-identity check is the proof.
pristine="$(mktemp)"; cp "$file" "$pristine"
uvtmp="$(mktemp -d)"   # the parse check's TMPDIR: uv leaves an environment lock file in the one it runs under
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

# The parser is chosen before any mutation, so a mutation that deletes the shebang is still checked.
SHEBANG='^#!.*[/[:space:]](ba)?sh([[:space:]]|$)'
parser=""
case "$file" in
  *.j2) ;;   # a template is Jinja until rendered, whatever its shebang
  *.py) parser=python ;;
  *.sh | *.bash) parser=bash ;;
  *) if [[ "$(head -n1 "$file")" =~ $SHEBANG ]]; then parser=bash; fi ;;
esac
check_parse() {   # 0 when $file parses or has no parser; 1, the parser's first error line printed, when it does not; 2 when the check could not run
  local out="" rc=0
  case "$parser" in
    python) out="$(TMPDIR="$uvtmp" uv run --no-sync python -I -c '
import ast, sys
try:
    ast.parse(open(sys.argv[1], "rb").read(), sys.argv[1])
except SyntaxError as e:
    print(f"line {e.lineno}: {e.msg}")
    sys.exit(3)' "$file" 2>"$uvtmp/stderr" 9>&-)" || rc=$?
      if [[ $rc -ne 0 && $rc -ne 3 ]]; then return 2; fi ;;
    bash) out="$(bash -O extglob -n "$file" 2>&1)" || rc=$? ;;   # -n never runs the file's own `shopt -s extglob`
  esac
  [[ $rc -eq 0 ]] || { printf '%s\n' "${out%%$'\n'*}"; return 1; }
}
could_not_run() {
  echo "mutate-probe: REFUSING — the parse check could not run on $file, so there is no verdict; its error:" >&2
  cat "$uvtmp/stderr" >&2
  exit 2
}
# A file that does not parse unmutated has no parse for a mutation to break.
prc=0; err="$(check_parse)" || prc=$?
if [[ $prc -eq 2 ]]; then could_not_run; fi
if [[ $prc -eq 1 ]]; then echo "mutate-probe: $file does not parse unmutated ($err), so its mutation takes no parse check." >&2; parser=""; fi

# pytest mkdirs its basetemp, without parents, at os.path.abspath(<path>): the parent is taken from that lexical path, then resolved physically so an in-tree symlink out of the tree is outside it.
if [[ $sandbox -eq 1 ]]; then tree="$(pwd -P)"; else tree="$(git rev-parse --show-toplevel)"; fi
prev=""
for w in "$@"; do
  basetemp=""
  case "$w" in
    --basetemp=*) basetemp="${w#--basetemp=}" ;;
    *) if [[ "$prev" == --basetemp ]]; then basetemp="$w"; fi ;;
  esac
  prev="$w"
  [[ -n "$basetemp" ]] || continue
  parent="$(realpath -m -- "$(dirname -- "$(realpath -s -m -- "$basetemp")")")"
  [[ "$parent" == "$tree" || "$parent" == "$tree"/* ]] || continue
  mkdir -p -- "$parent" || true   # a parent that cannot be made fails the baseline below, after mkdir's own error line
done

# 0. baseline: the probe must PASS on UNMUTATED code, or the control's failure says nothing about the
# control. Run it under the SAME conditions as the real probes -- bytecode export set, caches purged --
# or the baseline is not comparable to what follows.
purge
if ! "$@" 9>&- >/dev/null 2>&1; then
  echo "mutate-probe: baseline failed — the probe must pass on unmutated code. Fix the probe command (or the tree) before any verdict here means anything." >&2
  exit 7
fi

no_test_ran() {
  echo "mutate-probe: REFUSING — the $1 run exited 5, pytest's \"no tests ran\": nothing was measured, so it is no kill. Fix the probe's selection." >&2
  exit 2
}

# 1. control: must FAIL, or the harness is not measuring
apply "$control" "control sed"
rc=0; "$@" 9>&- >/dev/null 2>&1 || rc=$?
restore
if [[ $rc -eq 0 ]]; then echo "mutate-probe: CONTROL mutation did not fail the probe — the harness does not bite; no real probe counts. Pick a control the probe must detect." >&2; exit 5; fi
if [[ $rc -eq 5 ]]; then no_test_ran control; fi

# 2. the real mutation
apply "$mutation" "mutation sed"
prc=0; err="$(check_parse)" || prc=$?
if [[ $prc -ne 0 ]]; then
  restore; purge
  if [[ $prc -eq 2 ]]; then could_not_run; fi
  echo "mutate-probe: REFUSING — the mutation leaves $file unparseable ($err): a mutation that does not parse is no kill. Mutate so the file still parses." >&2
  exit 2
fi
rc=0; "$@" 9>&- >/dev/null 2>&1 || rc=$?
restore; purge
if [[ $rc -eq 5 ]]; then no_test_ran mutation; fi
if [[ $rc -eq 0 ]]; then verdict=SURVIVED; else verdict=KILLED; fi
echo "mutate-probe: $verdict (control proven, tree restored byte-identically)"
[[ "$verdict" == KILLED || "$verdict" == SURVIVED ]]
