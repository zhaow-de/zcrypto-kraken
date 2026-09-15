#!/usr/bin/env bash
# Sweep the tracked tree, the untracked files git does not ignore, AND `.local/` -- the memo, the coordination
# table, the lesson inboxes -- which a bare sweep cannot see: the shell's `grep` honours `.gitignore` and
# `.local/.gitignore` is `*`, so it reports clean over files it never opened. Inside a script `grep` is GNU
# grep, which honours nothing and would walk `.venv`. Both are answered by handing grep the file list rather
# than a flag.
# The `.local/` swept is the MAIN checkout's, whichever checkout you call this from: a linked worktree
# carries a `.local/` of its own holding nothing but the tracked `.gitignore`, and sweeping that one returns
# the silent clean this script exists to end.
# A clean is reported only over a sweep proven able to see: `--control <pattern>` names a known positive, and rc 1
# is reported when that control hit -- an empty result over a file list that opened nothing reads exactly like an
# absent needle, and it is the clean that gets believed. A hit needs no control: it is its own proof the sweep saw.
# The control is matched with the caller's own flags (`-i`, `-w`, `--include`) and its pattern in place of the
# sweep's, so what it proves is a matcher the sweep ran rather than a bare grep. It never inherits a word that
# would make a positive probe vacuous -- a selection the sweep inverts, or a pattern of the sweep's own -- nor a
# cluster whose operand stays behind, which is held back WHOLE and takes its narrowing letters with it: the
# control is then laxer than the sweep, and the refusal below names what it lost rather than blaming the control.
# What a control's hit proves is that this matcher could hit SOMEWHERE in the file list; that one directory was
# opened only when the pattern is one that directory alone holds. `git grep` finding no carrier settles the
# tracked half of that; the list also holds the untracked files git does not ignore and everything under
# `.local/`, and a carrier there is outside what any tracked-file check can see. Whether `.local/` was in the
# list at all is the other door: the `no <path>/.local` line below.
# Usage: infra/scripts/sweep.sh [grep flags] --control <known-positive> <pattern>   rc: 0 a hit, 1 none (control hit), 2 an error.
set -euo pipefail
# Given no pattern -- none at all, or flags alone -- grep takes the first path as its regex and answers
# whatever that earns, a hit or a clean, never the error this is. Deciding this needs grep's option table:
# `--include '*.py'` has a bare operand that is not a pattern, so the flags below that take one AS A
# SEPARATE WORD consume it. `--color`'s argument is optional and grep reads it only attached, so it is not
# one of them. The table below is every long option grep answers "requires an argument" to, each written as
# the shortest prefix grep resolves plus a glob, so an abbreviation is the same word to this loop as the full
# name. What still reads its operand as a pattern and passes this check is a flag outside grep's table, or one
# clustered into `-lm 5`, which the cluster arm decides instead. An attached `-eNEEDLE` is refused although
# grep accepts it -- a loud refusal naming the spelling that works, which is the recoverable error of the two.
# A pattern flag records the pattern from its OPERAND: `sweep.sh -e` supplies none, and grep would then bind the script's own `--` as the regex.
pattern=0
skip=0     # the next word is a flag's operand, to be stepped over
carries=0  # ...and that operand is the pattern, so a dangling `-e` never records one
takes=0    # ...and that operand is --control's known positive, which grep never sees
control=0
known=""
args=()    # what grep is handed: the caller's words, `--control <pattern>` removed
flags=()   # ...those of them that are not a pattern, so the control runs under the same matcher
held=()    # ...and those held back whole, which the refusal names rather than leaving to the control
# grep's short options that take an operand -- every letter grep answers "requires an argument" to -- split by
# what that operand is: a pattern letter's is the sweep's own pattern, which the control must not inherit at all;
# an operand letter's is a NUM, an ACTION or a matcher name, a word this loop leaves in the sweep's arguments.
# Each list is read twice below, where the option stands alone and where it is one letter of a cluster, and
# writing it once is what keeps the two readings one set as grep's table moves.
pattern_letters=ef
operand_letters=mABCdDX
for a in "$@"; do
  if [ "$skip" -eq 1 ]; then
    skip=0
    if [ "$takes" -eq 1 ]; then known="$a"; takes=0; continue; fi
    args+=("$a")
    if [ "$carries" -eq 1 ]; then pattern=1; carries=0; else flags+=("$a"); fi
    continue
  fi
  case "$a" in
    --control) control=1; skip=1; takes=1; continue ;;
    --control=*) control=1; known="${a#--control=}"; continue ;;
    --reg*=*|--file=*) pattern=1; args+=("$a"); continue ;;
    -["$pattern_letters"]|--reg*|--file) skip=1; carries=1; args+=("$a"); continue ;;
    # An operand attached with `=` leaves nothing behind, so its word reaches the control whole. This arm is
    # what keeps the globs below off `--after-context=3`, where one would otherwise step over the pattern.
    --*=*) ;;
    # Every long option grep answers "requires an argument" to, each as the shortest prefix grep resolves: every
    # longer prefix is the same flag, and a word outside grep's table that begins the same way is grep's own loud
    # error rather than a clean. `--file` is an exact match that is ALSO a prefix of `--files-with-matches` and
    # `--files-without-match`, which take no operand, so it is written literally above; `--exclude` is a prefix of
    # `--exclude-dir` and `--exclude-from`, which do take one, so it may be globbed. `--binary` (`-U`) takes none,
    # which is why the glob starts at `--binary-`.
    -["$operand_letters"]|--a*|--be*|--binary-*|--con*|--dev*|--di*|--exclude*|--g*|--inc*|--la*|--m*) skip=1 ;;
    # The sweep may invert its selection; its control never does -- under `-v` a pattern nothing holds selects
    # every line, so the control would prove only that the files have lines. `--inv` and `--files-witho` are where
    # grep's long-option prefixes stop being ambiguous, so every spelling from there to the full name is the same
    # flag and is held back with it; a word outside grep's table that begins either way is grep's loud error.
    # None of them narrows a matcher, so none is a word the refusal below needs to name: a control that missed
    # missed for its own sake here, which is why these are not added to `held`.
    -v|-L|--inv*|--files-witho*) args+=("$a"); continue ;;
    # EVERY short cluster is read, wherever its inverting letter sits: `-vl` is the `-lv` sweep spelled backwards.
    # The option table above deliberately does not read clusters -- one it misses ends in grep's own loud error,
    # one missed here in a silent clean.
    -[!-]*)
      args+=("$a")
      # A letter the control cannot carry alone withholds the cluster whole -- the two lists above, read here as
      # one, because a letter buried in a cluster still leaves its operand behind in the sweep's own arguments,
      # and the letter handed back alone would eat the control's `-e` as that operand.
      case "$a" in *["$pattern_letters$operand_letters"]*) held+=("$a"); continue ;; esac
      selecting="${a#-}"; selecting="${selecting//[vL]/}"
      [ -z "$selecting" ] || flags+=("-$selecting")
      continue ;;
    -*) ;;
    *) pattern=1; args+=("$a"); continue ;;
  esac
  args+=("$a"); flags+=("$a")
done
[ "$pattern" -eq 1 ] || { echo "sweep: no pattern in '$*' -- a pattern is a bare word that is not a flag's operand, or follows -e/-f/--regexp/--file as its own word; usage: sweep.sh [grep flags] --control <known-positive> <pattern>" >&2; exit 2; }
# A dangling `--control`, or `--control=`, records the empty pattern, which every line matches: the control that
# proves nothing, and the clean it would wave through is the one this flag exists to hold back.
[ "$control" -eq 0 ] || [ -n "$known" ] || { echo "sweep: --control takes its known positive as its own word -- something this tree certainly holds, e.g. --control 'NEEDLE'" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"
main="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd -P)")"
# Under `--separate-git-dir`, or a worktree of a bare repo, that dirname is not a checkout: refuse rather
# than sweep the tracked tree alone.
[ "$(git -C "$main" rev-parse --show-toplevel 2>/dev/null)" = "$main" ] || {
  echo "sweep: no main checkout at $main, resolved from $(git rev-parse --git-common-dir)" >&2; exit 2; }
ledger=.local
[ "$main" = "$(pwd -P)" ] || ledger="$main/.local"
[ -d "$ledger" ] || echo "sweep: no $ledger -- the memo, the table and the inboxes are not in this sweep" >&2
mapfile -d '' -t listed < <(git ls-files -z --deduplicate --cached --others --exclude-standard -- ':(exclude).local'; [ -d "$ledger" ] && find "$ledger" ! -type d -print0)
# A tracked file deleted in the worktree is still in the index, and grep exits 2 over it whatever it printed,
# so the list is narrowed to what exists and rc keeps the meaning the usage line documents.
files=()
for f in ${listed[@]+"${listed[@]}"}; do
  if [ -f "$f" ]; then files+=("$f")
  # Everything the list can hold that grep will not open -- a nested checkout, a submodule, a link to a
  # directory, a fifo, a dangling link -- is named rather than dropped, because silence here answers
  # "absent" over content nobody opened. A path merely gone from the worktree is the exception: neither
  # test holds, it is in the index alone, with no worktree entry to name.
  elif [ -e "$f" ] || [ -L "$f" ]; then echo "sweep: $f is not a regular file, not swept" >&2
  fi
done
[ "${#files[@]}" -gt 0 ] || { echo "sweep: no files to search under $PWD" >&2; exit 2; }
set +e
grep -I -H ${args[@]+"${args[@]}"} -- "${files[@]}"
rc=$?
if [ "$rc" -eq 1 ]; then
  if [ "$control" -eq 0 ]; then
    echo "sweep: nothing matched in ${#files[@]} files, and nothing here proves this sweep could see them -- re-run with --control <pattern> naming something the tree certainly holds, and the clean is reported when that control hits" >&2
    exit 2
  fi
  grep -I -q ${flags[@]+"${flags[@]}"} -e "$known" -- "${files[@]}"
  crc=$?
  if [ "$crc" -ne 0 ]; then
    echo "sweep: the control '$known' matched nothing either in ${#files[@]} files (grep rc $crc) -- this sweep is not proven able to see, so its clean is no evidence; pick a control this tree holds" >&2
    # Without this the operator's next move is to replace a control that was never wrong: a cluster held back
    # whole takes its narrowing letters with it, so the control ran under less than the sweep did.
    [ "${#held[@]}" -eq 0 ] || echo "sweep: before replacing it: the control ran without ${held[*]}, held back whole because a letter there takes an operand this loop left in the sweep's own words -- spell that cluster as separate words ('-i -m 5' for '-ivm 5') and the control keeps every letter it can use" >&2
    exit 2
  fi
fi
exit $rc
