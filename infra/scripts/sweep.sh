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
# sweep's, so what it proves is a matcher the sweep ran rather than a bare grep. Every operand-taking word of the
# caller's goes over WITH its operand, so a word the sweep's grep refuses the control's refuses too. It never
# inherits the two that would make a positive probe vacuous: a selection the sweep inverts, and a pattern of the
# sweep's own -- the second held back as the whole cluster carrying it, which takes its narrowing letters with it,
# so the control is laxer there and the refusal below names what it lost rather than blaming the control.
# What a control's hit proves is that this matcher could hit SOMEWHERE in the file list; that one directory was
# opened only when the pattern is one that directory alone holds. `git grep` finding no carrier settles the
# tracked half of that; the list also holds the untracked files git does not ignore and everything under
# `.local/`, and a carrier there is outside what any tracked-file check can see. Whether `.local/` was in the
# list at all is the other door: the `no <path>/.local` line below.
# Usage: infra/scripts/sweep.sh [grep flags] --control <known-positive> <pattern>   rc: 0 a hit, 1 none (control hit), 2 an error.
set -euo pipefail
# Given no pattern -- none at all, or flags alone -- grep takes the first path of the file list below as its
# regex and answers whatever that earns, a hit or a clean, never the error this is. WHICH word is the pattern is
# not decided here: it is asked of grep at the probe below, where the reason is written. The table this loop
# reads answers a different question, what the CONTROL may inherit, where wrong costs a control and says so:
# `--include '*.py'` takes a bare operand that is not a pattern, and handed to the control without it the option
# eats the control's own `-e` instead.
# `--color`'s argument is optional and grep reads it only attached, so it is not one of them.
# `pattern` is this loop's own answer to the pattern question, kept because it may only ever REFUSE: an attached
# `-eNEEDLE` is refused although grep accepts it, a loud refusal naming the spelling that works.
pattern=0
skip=0     # the next word is a flag's operand, to be stepped over
carries=0  # ...and that operand is the pattern, so a dangling `-e` never records one
takes=0    # ...and that operand is --control's known positive, which grep never sees
promised=""  # the flag standing LAST with its operand unsupplied, the one word of the caller's that would reach
             # past their own words into the probe's
owed=0     # a cluster already handed to the control takes its operand from the next word; the control needs it too
sourcing=0 # ...and a pattern FILE takes its path from the next word, which the question below needs
control=0
known=""
args=()    # what grep is handed: the caller's words, `--control <pattern>` removed
flags=()   # ...those of them that are not a pattern, so the control runs under the same matcher
held=()    # ...and those held back whole, which the refusal names rather than leaving to the control
sources=() # ...and the pattern FILES named among them, the one input here that is read and not merely passed
# grep's short options that take an operand -- every letter grep answers "requires an argument" to -- split by
# what that operand is: a pattern letter's is the sweep's own pattern, which the control must not inherit at all;
# an operand letter's is a NUM, an ACTION or a matcher name, a word this loop leaves in the sweep's arguments.
# Each list is read twice below, where the option stands alone and where it is one letter of a cluster, and
# writing it once is what keeps the two readings one set as grep's table moves.
# A source letter is the pattern letter whose operand is not a pattern but a FILE of them; it is written as its
# own list because a third reading below asks what that file is, and `pattern_letters` is built from it so the
# two arms that hand a cluster back stay one set with it.
source_letters=f
pattern_letters=e$source_letters
operand_letters=mABCdDX
for a in "$@"; do
  # The cluster handed to the control one word ago is still waiting for the operand grep binds from THIS word,
  # whatever this word spells, so the control takes it too. `--control` standing here is a word of the sweep's own
  # where an operand of the caller's should be, and handing it over leaves grep refusing the control -- a refusal
  # below rather than a clean, which is the direction to err in.
  if [ "$owed" -eq 1 ]; then owed=0; flags+=("$a"); fi
  # The same shape for a pattern FILE: whichever word supplies the path, it is recorded here rather than opened,
  # because what that path NAMES is asked below and decides whether this sweep may run at all.
  if [ "$sourcing" -eq 1 ]; then sourcing=0; sources+=("$a"); fi
  promised=""   # every word clears it, so only the last word of all can leave a promise standing
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
    # The two source spellings stand ahead of the two pattern ones: `-f` is a member of both lists, and the arm
    # that runs is the first that matches.
    --file=*) pattern=1; sources+=("${a#--file=}"); args+=("$a"); continue ;;
    -["$source_letters"]|--file) skip=1; carries=1; sourcing=1; promised="$a"; args+=("$a"); continue ;;
    --reg*=*) pattern=1; args+=("$a"); continue ;;
    -["$pattern_letters"]|--reg*) skip=1; carries=1; promised="$a"; args+=("$a"); continue ;;
    # An operand attached with `=` leaves nothing behind, so its word reaches the control whole. This arm is
    # what keeps the globs below off `--after-context=3`, where one would otherwise step over the pattern.
    --*=*) ;;
    # Every long option grep answers "requires an argument" to, each as the shortest prefix grep resolves: every
    # longer prefix is the same flag, and a word outside grep's table that begins the same way is grep's own loud
    # error rather than a clean. `--file` is an exact match that is ALSO a prefix of `--files-with-matches` and
    # `--files-without-match`, which take no operand, so it is written literally above; `--exclude` is a prefix of
    # `--exclude-dir` and `--exclude-from`, which do take one, so it may be globbed. `--binary` (`-U`) takes none,
    # which is why the glob starts at `--binary-`.
    -["$operand_letters"]|--a*|--be*|--binary-*|--con*|--dev*|--di*|--exclude*|--g*|--inc*|--la*|--m*) skip=1; promised="$a" ;;
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
      # grep binds the REST of a cluster as the operand of its first operand-taking letter, so only a letter
      # standing at the very end of one reaches past the word: `-ldread` and `-lm5` carry their own, `-ld` and
      # `-le` take the next word. That is the same promise the standalone arms above record.
      letters="${a#-}"
      before="${letters%%["$pattern_letters$operand_letters"]*}"   # the letters ahead of the one that binds
      [ "$before" != "${letters%?}" ] || promised="$a"
      # Which of the two lists that binding letter is in decides what the control may be handed, because it
      # decides what the operand IS. Only the letters BEFORE it may be filtered: one dropped from behind it
      # changes what grep binds, and `-dvread` is an invalid ACTION where `-dread` is not.
      binds="${letters:${#before}:1}"
      # A source letter binds a pattern FILE wherever grep takes it from -- attached behind the letter, or the
      # next word -- and the path is what the question below reads, either way.
      case "$binds" in
        ["$source_letters"])
          if [ -n "${letters:${#before}+1}" ]; then sources+=("${letters:${#before}+1}"); else sourcing=1; fi ;;
      esac
      case "$binds" in
        # A pattern letter's operand is the sweep's own pattern, and the letter handed back without it would eat
        # the control's own `-e`: the cluster is withheld WHOLE, narrowing letters and all, and the refusal below
        # names it. The control is no guard in this arm; the checks below are.
        ["$pattern_letters"]) held+=("$a"); continue ;;
        # The operand is a word this loop leaves in the sweep's arguments, so the cluster goes over WITH it,
        # exactly as the standalone arms hand `-d read` over, and the control is then refused by whatever
        # refuses the sweep.
        ["$operand_letters"]) [ -z "$promised" ] || owed=1; flags+=("-${before//[vL]/}${letters:${#before}}") ;;
        # No operand-taking letter at all: nothing waits on a later word, so only the inverting letters go.
        *) selecting="${letters//[vL]/}"; [ -z "$selecting" ] || flags+=("-$selecting") ;;
      esac
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
# The caller's last word is a flag still waiting for the operand grep binds from the NEXT word, and there is no
# next word of theirs -- so the next word is the one the probe below appends. Refused here rather than asked,
# because the probe is only a fair question while nothing of ours is standing where an operand of the caller's
# should be: a dangling `-e` binds `--directories=skip` as the regex and the sweep answers, confidently, about a
# word nobody typed. This is the loop's own answer again, and like `pattern` it may only ever REFUSE -- a flag
# left promising an operand is the caller's error in every spelling, which is why refusing it costs no sweep.
[ -z "$promised" ] || { echo "sweep: '$promised' stands last and nothing supplies the operand it promises -- grep takes the next word for it, and the only word after yours is one this script appends, so the sweep would search for that instead; give the operand as its own word, or drop the flag" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"
main="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd -P)")"
# Under `--separate-git-dir`, or a worktree of a bare repo, that dirname is not a checkout: refuse rather
# than sweep the tracked tree alone.
[ "$(git -C "$main" rev-parse --show-toplevel 2>/dev/null)" = "$main" ] || {
  echo "sweep: no main checkout at $main, resolved from $(git rev-parse --git-common-dir)" >&2; exit 2; }
# What a pattern FILE names, asked before any grep here opens it, and after the `cd` so a relative path resolves
# as it will for them. Three greps read that file ahead of the sweep's own -- the pattern question below, then
# the empty-set probe and its control -- and a regular file answers all four alike. Two kinds do not, and under
# either the set the probes ask about is not the set the sweep would run with: a clean could then stand over a
# grep that never carried the caller's pattern, which is the one thing this script exists to refuse. Refused
# rather than modelled around: `git grep -ho "sweep\.sh[^\`]*" -- '*.md'` finds four prescribed sweeps and not
# one of them names a pattern file, so this costs a spelling nothing here asks for.
for src in ${sources[@]+"${sources[@]}"}; do
  case "$src" in
    # A name for the caller's own stdin, or for a descriptor already open. The greps above the sweep read with
    # stdin redirected to `/dev/null`, so this path is one file to them and another to the sweep. A stat cannot
    # tell: `/dev/stdin` over a redirected file stats as a regular file. The name is what tells.
    -|/dev/stdin|/dev/fd/*|/proc/self/fd/*|/proc/[0-9]*/fd/*) ;;
    # A pipe or a socket, however it was spelled -- `<(...)` reaches here as `/dev/fd/N`, a pipe. The first
    # reader drains it and the sweep's grep, reading last, gets nothing.
    *) [ -p "$src" ] || [ -S "$src" ] || continue ;;
  esac
  echo "sweep: the pattern source '$src' cannot be put to grep twice -- a pipe is drained by the first of the three greps that run before the sweep, and a name for stdin is /dev/null to those three and yours to the sweep -- so what the sweep would search for is not what was asked about, and a clean over it would stand over a grep that never carried your pattern. Write the patterns into a regular file and name that file, or give the pattern as a word of your own" >&2
  exit 2
done
# The pattern question, put to grep. Handed the sweep's own words and no file operand of the caller's, grep
# either has a pattern of its own -- and searches the empty stdin for it, 0 or 1 -- or refuses at rc 2, because
# the word it would have bound as the regex is the file list this script is about to supply. Asking keeps the
# answer from being one spelling behind grep's own parser; it costs a second grep per sweep, and a refusal in
# grep's words rather than this script's. It runs from the toplevel, after the `cd`, so a `-f pattern-file`
# resolves exactly as it will for the sweep. `--directories=skip` goes last because `-r` with no file operand
# means "search the working directory", which is a walk of the whole tree for nothing and an rc 2 over any path
# here that cannot be read. It is the one word of ours here, and only a flag still promising an operand could
# take it, which is what the check above holds back.
probe="$(grep -I -H ${args[@]+"${args[@]}"} --directories=skip </dev/null 2>&1 >/dev/null)" && prc=0 || prc=$?
# rc 2 is more than the missing pattern: an unrecognised option, a bad `-m` argument and an invalid regex all
# land here, each carrying its own first line. Explaining them all as a missing pattern sends that operator to
# add an `-e` to a sweep that already has one, so the explanation below is offered rather than asserted.
# It is also less than every refusal grep has: `-d` with an invalid ACTION is rejected at rc 1, which reads here
# as a pattern found, and the sweep's own grep then fails the same way and reads as "nothing matched". Of every
# operand this loop steps over it is the only one -- `-D`, `-m`, `-A`, `-B`, `-C`, `-X`, `-f`, `-e`,
# `--binary-files` and `--exclude-from` all answer 2 and stop here. What keeps it from ending in a clean is not
# this line but the control, which carries that letter and its operand and is refused by the same grep. Widening
# this line to refuse on anything the probe wrote would rest on grep writing nothing while exiting 0 or 1, a
# claim about grep it need not make.
[ "$prc" -ne 2 ] || { echo "sweep: grep refuses these words without a file list -- '${probe%%$'\n'*}'. Where that is a missing pattern: this script supplies the file list, so the word grep lacks it takes from there -- a file path as the regex, and a hit or a clean about a filename. Give the pattern as a word of your own, -e <pattern> if it begins with a dash. Any other complaint above is about the word grep names in it" >&2; exit 2; }
# The pattern SET, put to grep the same way, because an EMPTY one is a clean the control cannot catch: the control
# carries a pattern of its own, so it hits over a sweep whose grep opened nothing. `-f`/`--file` naming a file that
# holds no pattern is the way left to it -- every other pattern source is a pattern by being written, and one that
# is no file is refused above -- and grep with none reads no file, refuses nothing, and answers 1: the rc this
# script reports as an absence. What it also does
# not do is stat a file operand, which is the question here. One path that cannot exist stands in for the list
# (`/dev/null` is a character device, so anything under it is ENOTDIR wherever this runs): words carrying a pattern
# are refused over it at rc 2, words carrying none answer 1 in silence.
# The second run is that question's own control, and it is what keeps this refusal off an ordinary sweep: it adds a
# pattern and asks again, so a 1 is read as "no pattern" only where a pattern DOES reach the path. `-m 0` stops
# before the stat with a pattern and without one alike and answers 1 twice -- a sweep that opens nothing for its
# own reason, which the control below is what answers -- and under `-v` an empty pattern set selects every line, so
# grep opens the files, the stat happens, and rc 2 leaves this alone.
nowhere=/dev/null/no-such-file
grep -I -H ${args[@]+"${args[@]}"} --directories=skip -- "$nowhere" </dev/null >/dev/null 2>&1 && reached=0 || reached=$?
grep -I -H ${args[@]+"${args[@]}"} -e '' --directories=skip -- "$nowhere" </dev/null >/dev/null 2>&1 && reachable=0 || reachable=$?
[ "$reached" -ne 1 ] || [ "$reachable" -ne 2 ] || { echo "sweep: these words reach grep with an empty pattern set -- an -f/--file file that holds no pattern is the way there -- so grep opens no file and exits 1, which this script reports as a clean over a sweep that read nothing. Write the patterns into that file, or give the pattern as a word of your own" >&2; exit 2; }
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
    # A control REFUSED and a control that ran and missed arrive here as the same rc -- an invalid `-d` ACTION is
    # rc 1 like an honest miss -- and they want opposite next moves, so which it was is asked rather than read off
    # `crc`: the control's words, put to grep with no file list, where nothing but a refusal can make it write.
    # (Over the file list it could also write about a file it could not open, which is no refusal and belongs to
    # the sweep's own grep above.)
    refusal="$(grep -I -q ${flags[@]+"${flags[@]}"} -e "$known" --directories=skip </dev/null 2>&1 >/dev/null)" || true
    # A refusal of those words is of the caller's or of the control's OWN pattern, and those two want opposite
    # moves again: the caller's word refused the sweep's grep too, so its rc 1 is no absence, while a control
    # pattern grep cannot compile leaves that rc standing and unproven. Which it was is asked the same way, the
    # same words with `-e ''` where the control's pattern stood: nothing there is the caller's to refuse but the
    # caller's own words. Not read off the first probe above, whose silence would have to mean grep never writes
    # while exiting 0 or 1 -- a claim about grep this script need not make.
    theirs="$(grep -I -q ${flags[@]+"${flags[@]}"} -e '' --directories=skip </dev/null 2>&1 >/dev/null)" || true
    if [ -n "$refusal" ] && [ -n "$theirs" ]; then
      echo "sweep: grep refused the control's words -- '${refusal%%$'\n'*}' -- and they are the sweep's own, so the sweep's grep was refused the same way and its rc 1 is no absence. Fix the word grep names above; the control '$known' is not what is wrong here" >&2
    elif [ -n "$refusal" ]; then
      echo "sweep: grep refused the control pattern '$known' -- '${refusal%%$'\n'*}' -- so the control never ran and this clean stays unproven. The sweep's own words grep accepts: put to it with a pattern in the control's place they draw no complaint, so the pattern is what to fix -- give a control grep compiles, naming something this tree holds" >&2
    else
      echo "sweep: the control '$known' matched nothing either in ${#files[@]} files (grep rc $crc) -- this sweep is not proven able to see, so its clean is no evidence; pick a control this tree holds" >&2
      # Without this the operator's next move is to replace a control that was never wrong: a cluster held back
      # whole takes its narrowing letters with it, so the control ran under less than the sweep did.
      [ "${#held[@]}" -eq 0 ] || echo "sweep: before replacing it: the control ran without ${held[*]}, held back whole because a letter there takes the sweep's own pattern as its operand -- spell that cluster out, the pattern flag and its pattern each a word of their own ('-i -v -e .' for '-ive .'), and the control keeps the letters that narrow it" >&2
    fi
    exit 2
  fi
fi
exit $rc
