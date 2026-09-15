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
# The control is the caller's own words with its own pattern standing where the sweep's did, so what it proves is
# the matcher the sweep ran rather than a bare grep: a word that refused the sweep's grep refuses the control's
# too, and a grep that opened no file never licenses a clean.
# What a control's hit proves is that this matcher could hit SOMEWHERE in the file list; that one directory was
# opened only when the pattern is one that directory alone holds. Whether `.local/` was in the list at all is the
# other door: the `no <path>/.local` line below.
# Usage: infra/scripts/sweep.sh [grep flags] -e <pattern> [--control <known-positive>]
#   rc: 0 a hit, 1 none (control hit), 2 an error.
set -euo pipefail
# `+(...)` below, where a `*` swallows the letter the glob has to stop at. Off, the case is a syntax error.
shopt -s extglob
# The pattern is REQUIRED as `-e <pattern>`, its own word, and that is the whole of what this script reads out of
# the caller's words: which word the control replaces is then a lookup, not a model of grep's option table. Every
# other word goes to grep unexamined, its operands riding along in place; a pattern spelt any other way records
# none and reaches the refusal below, which names the spelling that works.
control=0
known=""
pat_at=-1  # where the sweep's pattern stands in `args` -- the one word the control puts its own in place of
take=""    # the next word is the operand of `--control` or of `-e`
args=()    # what grep is handed: the caller's words, `--control <pattern>` removed
for a in "$@"; do
  case "$take" in
    control) known="$a"; take=""; continue ;;
    pattern) [ "$pat_at" -ge 0 ] || pat_at="${#args[@]}"; args+=("$a"); take=""; continue ;;
  esac
  case "$a" in
    --control) control=1; take=control; continue ;;
    --control=*) control=1; known="${a#--control=}"; continue ;;
    -e) take=pattern ;;
    # grep takes the pattern attached to the flag; this script does not read it there, so the words would reach
    # grep as a sweep for a pattern nothing here recorded. Refused by the spelling that works.
    -e?*)
      echo "sweep: '$a' attaches the pattern to its flag -- give it as -e <pattern>, its own word" >&2; exit 2 ;;
    # A pattern FILE is refused rather than opened: no sweep prescribed here uses one, and taking it would put a
    # reader of the caller's patterns ahead of grep's -- over anything but a plain file, the sweep's own grep
    # then searches for whatever that reader left. `--file` is written out because it is a prefix of
    # `--files-with-matches` and `--files-without-match`, which name no pattern file. A cluster is read only as
    # far as its `X`: grep binds the rest of a cluster to its first operand-taking letter, so the `f` of
    # `-lXfgrep` stands inside a matcher name and names nothing.
    -f*|--file|--file=*|-+([!-X])f*)
      echo "sweep: '$a' names a pattern FILE, which this sweep does not read -- give the pattern as -e <pattern>, its own word" >&2; exit 2 ;;
    # An inverting selection is refused for what it does to the control: under `-v` a pattern nothing holds
    # selects every line, so a control carrying the sweep's words hits whatever the tree holds and the clean it
    # licenses proves nothing. Both short globs are needed: a cluster inverts wherever its letter sits, and
    # `-vl` is the `-lv` sweep spelled backwards. `--inv` and `--files-witho` are where grep's long-option
    # prefixes stop being ambiguous, so every spelling from there to the full name is the same flag.
    -[vL]*|-[!-]*[vL]*|--inv*|--files-witho*)
      echo "sweep: '$a' inverts the selection, and a control run under it hits whatever the tree holds -- the clean it would license proves nothing; sweep for the pattern itself" >&2; exit 2 ;;
  esac
  args+=("$a")
done
[ "$pat_at" -ge 0 ] || { echo "sweep: no pattern in '$*' -- the pattern is required as -e <pattern>, its own word; usage: sweep.sh [grep flags] -e <pattern> [--control <known-positive>]" >&2; exit 2; }
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
grep -I -H "${args[@]}" -- "${files[@]}"
rc=$?
if [ "$rc" -eq 1 ]; then
  if [ "$control" -eq 0 ]; then
    echo "sweep: nothing matched in ${#files[@]} files, and nothing here proves this sweep could see them -- re-run with --control <pattern> naming something the tree certainly holds, and the clean is reported when that control hits" >&2
    exit 2
  fi
  probe=("${args[@]}")
  probe[pat_at]="$known"
  grep -I -q "${probe[@]}" -- "${files[@]}"
  crc=$?
  if [ "$crc" -ne 0 ]; then
    # The control's words are the sweep's own but for the pattern, and the sweep's grep compiled them one run
    # ago, so an rc 2 here is of the control's pattern and nothing else. rc 1 is the honest miss -- and the one
    # refusal GNU grep answers 1 to, an invalid `-d` ACTION, where the sweep's grep opened no file either and
    # grep's own complaint stands above this line.
    if [ "$crc" -eq 2 ]; then
      echo "sweep: grep refused the control pattern '$known' -- every other word here is the sweep's own, which grep has just compiled, so the pattern is what to fix: give a control grep compiles, naming something this tree holds" >&2
    else
      echo "sweep: the control '$known' matched nothing either in ${#files[@]} files -- this sweep is not proven able to see, so its clean is no evidence; pick a control this tree holds, and read any grep complaint above, which is what a sweep whose words opened no file leaves" >&2
    fi
    exit 2
  fi
fi
exit $rc
