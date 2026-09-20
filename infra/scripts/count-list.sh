#!/usr/bin/env bash
# The instrument that replaced the refine-rules staleness sweep: one line per entry -- its name and today's value -- for every count the corpus and the contracts name by entry (the top-level runbook pages among them since 2026-09-11), and a universal with no entry beside it is the finding.
# Four entries the corpus does not name close the list: topic-only merges, the claude-kind commits since the last refine round closed, the processes with a cwd inside a worktree, and the ambient bytes every session pays on every turn.
# Usage: count-list.sh [entry...] -- every entry, or only the named ones; a name no entry answers to is exit 2.
set -uo pipefail

errors=()
wanted=()
seen=()

# The count a command printed: pytest's own summary line, else the last line it wrote.
value_of() {
  local raw="$1" summary
  summary="$(printf '%s\n' "$raw" | grep -oE '[0-9]+ passed' | tail -n 1)"
  if [ -n "$summary" ]; then
    printf '%s' "$summary"
    return 0
  fi
  printf '%s\n' "$raw" | tail -n 1 | tr -d '[:space:]'
}

# emit <name> <count-command function>... — one output line, the values joined by "; ".
# grep and the pipelines built on it exit 1 for "no matches", which is a zero count and not an
# error; 2 and above is the command itself failing, and a function that returns 2 says so too.
emit() {
  local name="$1"
  shift
  if [ "${#wanted[@]}" -gt 0 ]; then
    local w hit=0
    for w in "${wanted[@]}"; do [ "$w" = "$name" ] && hit=1; done
    [ "$hit" = 1 ] || return 0
  fi
  seen+=("$name")
  local fn raw status value joined=""
  for fn in "$@"; do
    raw="$("$fn")"
    status=$?
    if [ "$status" -ge 2 ]; then
      errors+=("${name} (exit ${status})")
      printf '%s\tERROR\n' "$name"
      return 0
    fi
    value="$(value_of "$raw")"
    if ! printf '%s' "$value" | grep -qE '^[0-9]+( passed)?$'; then
      errors+=("${name} (unreadable output)")
      printf '%s\tERROR\n' "$name"
      return 0
    fi
    if [ -z "$joined" ]; then joined="$value"; else joined="${joined}; ${value}"; fi
  done
  printf '%s\t%s\n' "$name" "$joined"
}

# The count the corpus does not carry: merges whose every changed file is a topic file. The file
# list is taken against the merge's FIRST parent, because `git show --stat` on a merge renders an
# empty diffstat and would score every merge as touching nothing.
count_micro_prs() {
  local branch="$1" merge files micro=0
  while IFS= read -r merge; do
    files="$(git diff --name-only "${merge}^1" "$merge")"
    if [ -z "$files" ]; then continue; fi
    if ! printf '%s\n' "$files" | grep -qv '^docs/open-topics/'; then
      micro=$((micro + 1))
    fi
  done < <(git log --merges --first-parent "$branch" --format=%H)
  printf '%s\n' "$micro"
}

c_docs_markdown_at_the_root() { git ls-files ':(glob)docs/*.md' | wc -l; }

c_non_pr_merges() { git log --first-parent --merges develop --format=%s | grep -vc '^Merge pull request'; }

c_engine_env_forms() { git grep -nE '\{\{ ?json \.Config(\.Env)? ?\}\}|docker exec [^|;]* env( |$)|docker compose config' -- infra .claude cli ':!*.md' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

c_ansible_inventory_forms() { git grep -nE 'ansible-inventory( +\S+)* +--(host|list|vars)' -- infra .claude cli ':!*.md' ':!infra/ansible/scripts/vault-pass.sh' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

c_prose_chars() { uv run python infra/scripts/prose-chars.py; }

# This entry CALLS merge-gate.py's `read_line_fails` rather than restating it: three reads found three
# divergences in the jq that tried to, each in a different direction, and a counter that disagrees with the gate
# about the same rule measures nothing. So the rule has one implementation and this is a caller of it -- the
# journal-month exemption, the floor, the Fable paths, the substitution line, the renderer-aware body walk and
# the change-index-row exception all come from there, and a change to the gate moves this count by construction.
# The window starts where the read arm last changed shape -- the floor at 2026-09-10, which `git log -S 'Claude
# (Opus|Fable)' -- infra/scripts/merge-gate.py` names, then the messages comparison, `git log -S head_is_the_read`
# -- since a PR merged before that was judged by the arms of its day and breaks no rule; a head amended after
# its read was admitted by the tree arm those arms held. COUNT_LIST_PRS_SNAPSHOT names a recorded `gh pr list` JSON instead
# of the network, for the test -- and with it set, the per-PR head-commit fetch the change-index exception needs
# cannot run, so a row failing ONLY on a sha mismatch is counted rather than excused.
READ_LINE_RULE_SINCE="2026-09-20T12:06:05Z"
# A rule's window is a full INSTANT, never a bare date: `git log --since=2026-09-13` is approxidate and fills
# the missing time from the run's clock, so a bare date slides the window through the day and reads 0 over an
# empty set in the morning. `tests/test_count_list.py` refuses any RULE_SINCE that is not an instant.
PROSE_ONLY_RULE_SINCE="2026-09-13T00:00:00Z"
c_merged_prs_without_a_floor_read() {
  local prs floor oldest
  if [ -n "${COUNT_LIST_PRS_SNAPSHOT:-}" ]; then prs="$(cat "$COUNT_LIST_PRS_SNAPSHOT")" || return 2
  else prs="$(timeout 120 gh pr list --state merged --base develop --limit 400 \
    --json number,body,mergedAt,headRefName,headRefOid,files,changedFiles,mergeCommit)" || return 2
    timeout 60 git fetch -q origin develop || return 2; fi  # the merge commits the clone arm takes its base from
  floor="$(printf '%s' "$prs" | jq -r --arg since "$READ_LINE_RULE_SINCE" '[(now - 2592000 | todate), $since] | max')" || return 2
  # A saturated fetch cannot answer. If the OLDEST row fetched is still inside the window, rows below it were
  # never fetched and the count would silently under-report -- 204 PRs sat in the window against a --limit 200,
  # which is how this read 184 and called it a measurement. An unknowable count is an error, never a number.
  oldest="$(printf '%s' "$prs" | jq -r '[.[] | .mergedAt] | min // "none"')" || return 2
  # `gh pr list` prints `[]` and exits 0 for a base branch that does not exist or a token that cannot see PRs.
  if [ "$oldest" = "none" ]; then
    echo "count-list: the merged-PR fetch returned no rows at all -- check the base branch and the token" >&2
    return 2
  fi
  if [ "$oldest" \> "$floor" ]; then
    echo "count-list: the merged-PR fetch is saturated -- its oldest row ($oldest) is inside the window ($floor), so rows are missing" >&2
    return 2
  fi
  # The PR JSON goes in a FILE, not on stdin: the heredoc below IS this python's stdin, so a pipe into it is
  # silently discarded and `json.load(sys.stdin)` reads the script's own remaining bytes.
  local rows
  rows="$(mktemp)" || return 2
  printf '%s' "$prs" > "$rows" || { rm -f "$rows"; return 2; }
  COUNT_LIST_FLOOR="$floor" python3 - "$(dirname "$0")/merge-gate.py" "$rows" <<'PYGATE'
import importlib.util, json, os, pathlib, subprocess, sys

spec = importlib.util.spec_from_file_location("merge_gate", sys.argv[1])
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
offline = bool(os.environ.get("COUNT_LIST_PRS_SNAPSHOT"))
floor = os.environ["COUNT_LIST_FLOOR"]

heads = json.loads(pathlib.Path(os.environ["COUNT_LIST_HEADS_SNAPSHOT"]).read_text()) if os.environ.get(
    "COUNT_LIST_HEADS_SNAPSHOT") else None


def commit_of(sha):
    """The commit object the change-index-row exception reads -- a head that is the row commit over the tip the
    body names -- and the full sha of the read the clone arm fetches by, asked for only by a row that fails on
    nothing else. COUNT_LIST_HEADS_SNAPSHOT names a recorded `{oid: commit}` map, keyed by full oid and matched by
    prefix since a body names a short sha, so this arm can be driven without the network."""
    if not sha:
        return None
    if heads is not None:
        return next((c for oid, c in heads.items() if oid.startswith(sha)), None)
    if offline:
        return None
    done = subprocess.run(
        ["gh", "api", f"repos/{gate.REPO}/commits/{sha}"],
        capture_output=True, text=True, timeout=60,
    )
    return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None


def read_sha(pr):
    m = gate.READ_LINE.search(gate._as_a_reader_sees_it(pr.get("body") or ""))
    return m.group(2) if m else ""

files_snapshot = json.loads(pathlib.Path(os.environ["COUNT_LIST_FILES_SNAPSHOT"]).read_text()) if os.environ.get(
    "COUNT_LIST_FILES_SNAPSHOT") else None


def file_paths(pr):
    """The gate's view of the PR's files, which is NOT what `gh pr list --json files` returns: that gives the
    first page in the endpoint's own order, so a PR whose only Fable path falls outside it reads as touching
    none. `changedFiles` is the exact test for that -- it is not truncated, and comparing it to the row's length
    needs no belief about what a page holds. An ABSENT list stays None rather than becoming `[]`:
    `read_line_fails` has two refusals that fire only on None, and turning it into an empty list reports
    'touched nothing' and makes both unreachable.

    COUNT_LIST_FILES_SNAPSHOT names a recorded `{number: [path]}` map so the re-fetch below can be driven
    without the network, because an arm no test can reach is an arm no probe can kill -- which is how the
    head-commit arm beside it shipped uncovered once."""
    rows = pr.get("files")
    if rows is None:
        return None
    paths = [f.get("path") for f in rows]
    total = pr.get("changedFiles")
    if total is None or len(paths) >= total:
        return paths
    if files_snapshot is not None:
        return files_snapshot.get(str(pr.get("number")), paths)
    done = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{gate.REPO}/pulls/{pr.get('number')}/files", "--jq", ".[].filename"],
        capture_output=True, text=True, timeout=120,
    )
    if done.returncode != 0:
        # `return 2`, not 1: this entry's other refusals exit 2, and `emit` reads 1 as a zero COUNT.
        print(
            f"count-list: PR #{pr.get('number')} returned {len(paths)} of {total} files and the rest could not "
            f"be fetched -- the Fable-path arm cannot be decided: {done.stderr.strip()[:200]}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    # `splitlines()` where the gate splits on whitespace: a path containing a space survives here and is
    # fragmented there. Unreachable today and this is the correcter form, so the gate is the one to change.
    return [line for line in done.stdout.splitlines() if line.strip()]


commits_snapshot = json.loads(pathlib.Path(os.environ["COUNT_LIST_COMMITS_SNAPSHOT"]).read_text()) if os.environ.get(
    "COUNT_LIST_COMMITS_SNAPSHOT") else None


def with_commits(pr):
    """`commits` for a dependabot branch only, fetched per PR because the bulk list cannot carry it: 400 rows
    times their authors exceeds GraphQL's 500,000-node ceiling and the whole fetch errors. Every other branch
    keeps `commits` absent, which the gate's arm never asks for. COUNT_LIST_COMMITS_SNAPSHOT names a recorded
    `{number: [commit]}` map so the arm can be driven without the network."""
    if not (pr.get("headRefName") or "").startswith("dependabot/"):
        return pr
    number = str(pr.get("number"))
    if commits_snapshot is not None:
        return {**pr, "commits": commits_snapshot.get(number, [])}
    if offline:
        return pr
    done = subprocess.run(
        ["gh", "pr", "view", number, "--json", "commits"],
        capture_output=True, text=True, timeout=60,
    )
    if done.returncode != 0:
        print(
            f"count-list: PR #{number} is a dependabot branch whose commits could not be fetched, so the "
            f"no-fix-commit exemption cannot be decided: {done.stderr.strip()[:200]}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return {**pr, "commits": (json.loads(done.stdout) or {}).get("commits") or []}


kept_snapshot = json.loads(pathlib.Path(os.environ["COUNT_LIST_KEPT_SNAPSHOT"]).read_text()) if os.environ.get(
    "COUNT_LIST_KEPT_SNAPSHOT") else None
root = pathlib.Path(sys.argv[1]).resolve().parents[2]


def kept(pr):
    """`head_is_the_read`'s answer for the tip the body names against the merged head, from the PR's base at the
    merge -- the merge commit's first parent, since develop has moved on -- so a head the read's commits became
    by a rebase, a merge of the base or a re-dating is not booked, and a reworded one is. COUNT_LIST_KEPT_SNAPSHOT
    names a recorded `{headRefOid: answer}` map so the wiring can be driven without the PR's commits in the clone;
    offline with no map, or a PR with no merge commit, answers None and the row is counted rather than excused."""
    head = pr.get("headRefOid") or ""
    if kept_snapshot is not None:
        return kept_snapshot.get(head)
    merge = (pr.get("mergeCommit") or {}).get("oid")
    if offline or not merge:
        return None
    read = (commit_of(read_sha(pr)) or {}).get("sha") or read_sha(pr)
    return gate.head_is_the_read(read, head, f"{merge}^", cwd=root)


count = 0
for pr in json.loads(pathlib.Path(sys.argv[2]).read_text()):
    if (pr.get("mergedAt") or "") < floor:
        continue
    pr = with_commits(pr)
    files = file_paths(pr)
    fails = gate.read_line_fails(pr, None, files)
    if fails and all("not the head" in f for f in fails):
        fails = gate.read_line_fails(pr, commit_of(pr.get("headRefOid")), files, kept(pr))
    if fails:
        count += 1
print(count)
PYGATE
  local rc=$?
  rm -f "$rows"
  return "$rc"
}

c_kraken_cli_on_infra() { git grep -c kraken-cli -- infra cli ':!*.md' ':!infra/scripts/count-list.sh' | wc -l; }

c_prose_only_commits_without_the_prover() {
  comm -23 <(git log develop HEAD --since="$PROSE_ONLY_RULE_SINCE" --no-merges --format='%h %s' -i --grep=prose-only | grep -v ' claude(' | cut -d' ' -f1 | sort) \
           <(git log develop HEAD --since="$PROSE_ONLY_RULE_SINCE" --no-merges -i --grep=prove-inert --grep=prose-only-commits-without-the-prover --format=%h | sort) | wc -l
}

# A commit that records a probe verdict without naming the script. The left arm is the union of the script's
# three verdict words, case-sensitive: `-i` readmits plain English ("survived ten tasks"), and `control proven`
# alone misses a paraphrased record ("mutating it away SURVIVED").
#
# Anchor and arms read `develop HEAD`: develop's history plus the branch being read, so a violation is caught
# where it can still be reworded. A window anchored on one ref and measured on another can miss the set entirely.
c_probe_verdicts_without_the_script() {
  local since
  since="$(git log develop HEAD --reverse --format=%cI -S'probe-verdicts-without-the-script' -- CLAUDE.md | head -1)"
  if [ -z "$since" ]; then
    echo "count-list: no commit adds the probe-block clause to CLAUDE.md, so this count has no window" >&2
    return 2
  fi
  comm -23 <(git log develop HEAD --since="$since" --grep='control proven' --grep=KILLED --grep=SURVIVED --format=%h | sort) \
           <(git log develop HEAD --since="$since" --grep=mutate-probe --format=%h | sort) | wc -l
}

# A failing suite is an error, never a zero count: its output still carries a "N passed" summary.
c_spec_hash_provenance() { uv run pytest tests/test_trial_registry_provenance.py -q || return 2; }

c_operator_term_surfaces() { uv run pytest tests/test_internal_terms_not_operator_visible.py -q || return 2; }

c_operator_term_allowlist_edits() { git log --oneline -G_WP_CARRIERS -- tests/test_internal_terms_not_operator_visible.py | wc -l; }

# The skip gates under `tests/` the guard finds: one opt-in name over those, and every guard one of six
# forms or refused with the remedy it prints. The guard is the count.
c_skip_gate_contract() { uv run pytest tests/test_live_venue_opt_in.py -q || return 2; }

c_topics_without_a_trigger() { grep -L '^ripe_when: *[^ ]' docs/open-topics/T*.md | wc -l; }

# The bullets and numbered steps of the top-level runbook pages, `infra/runbooks/README.md` aside, whose own bullets
# state the rule rather than an operator's step: an internal token --
# `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `WP<N>`, `D<N>` -- inside one is a reference an operator who
# reached the page from an alert description cannot resolve. An HTML comment on the line may carry one; a
# declaration's why is inside its bullet and takes the rule with it. The classes and the path exemption are
# `tests/test_internal_terms_not_operator_visible.py`'s. One line per bullet, its tokens joined, so the count is
# bullets to fix and not tokens.
c_runbook_bullets_with_an_internal_token() { git ls-files 'infra/runbooks/*.md' | grep -vE '^infra/runbooks/(README\.md$|[^/]+/)' | xargs uv run python infra/scripts/runbook-internal-tokens.py | wc -l; }

# The bypasses the ROW names. `converge.sh` accepts an override as JSON and refuses every other
# spelling before the pass, so every bypass THROUGH IT is here; `run.sh` takes raw ansible argv and
# writes no row at all, which is the hole this count cannot see and the confirm gate is why.
c_canary_bypasses() { jq -c 'select(.limit=="zcrypto" and .extra_vars.canary_override!=null)' docs/reference/deploy-log.jsonl | wc -l; }

# COUNT_LIST_FEED_SNAPSHOT is the snapshot arm of the audit: set it and the count reads a recorded
# feed instead of the network, which is how a test runs this line and how a rolled feed keeps its
# coverage. Unset, the count is the live feed, as the corpus states it.
c_converges_inside_a_kraken_window() {
  local feed=()
  if [ -n "${COUNT_LIST_FEED_SNAPSHOT:-}" ]; then feed=(--from-snapshot "$COUNT_LIST_FEED_SNAPSHOT"); fi
  # `--venue-facing` is the rule's own set; the audit's unnarrowed arm still reports every row.
  uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing "${feed[@]}" | sed -n 's/^rows inside an API-impacting window \([0-9][0-9]*\) of .*/\1/p'
}

# shellcheck disable=SC2016  # the backticks are the drill-log row's literal Markdown fences
c_drills_on_the_primary() { grep -cE '^\*host\* `zcrypto`' docs/reference/drill-log.md; }

# `--skip-tags engine` is the Alloy bump's published primary form and names no tag, so it books an
# empty `tags` and its own `skip_tags` cell; counting it here would read a violation that never was.
c_un_tagged_primary_runs() { jq -c 'select(.limit=="zcrypto" and .tags=="" and (.skip_tags // "")=="")' docs/reference/deploy-log.jsonl | wc -l; }

c_engine_rows_outside_the_gap() { uv run python infra/scripts/deploy-log-audit.py engine-window | sed -n 's/^engine rows [0-9][0-9]* outside window \([0-9][0-9]*\) .*/\1/p'; }

c_nas_rows_without_compat() { awk -F'|' '$3 ~ /^ *nas *$/' docs/reference/fleet-pins.md | grep -vc compat; }

c_image_removals_outside_the_pruner() { git grep -nE 'docker (image (prune|rm)|rmi|system prune)' -- infra cli .claude ':!*.md' ':!infra/scripts/prune-host-images.py' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

c_inspect_reads_of_dot_image() { git grep -nE '\{\{ ?(json )?\.Image ?\}\}' -- infra cli .claude ':!*.md' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# A capture host counts unless the setting it reads first -- its host_vars, else the group -- is one of
# six false spellings (0, f, false, n, no, off): the template renders the value raw into apt's config,
# whose reader accepts these and more, so the count never under-reports. A host with the key in neither
# file counts too, since the base role's default is not read here.
c_capture_hosts_with_automatic_reboot() {
  local h f n=0
  for h in zcrypto zcrypto-red; do
    for f in "infra/ansible/host_vars/$h/vars.yml" infra/ansible/group_vars/capture_host/vars.yml; do
      if grep -qE '^base_unattended_upgrades_automatic_reboot:' "$f" 2>/dev/null; then
        grep -qiE '^base_unattended_upgrades_automatic_reboot: *["'"'"']?(0|f|false|n|no|off)["'"'"']? *$' "$f" || n=$((n + 1))
        continue 2
      fi
    done
    n=$((n + 1))
  done
  echo "$n"
}

c_runbook_sections_without_a_trigger() { uv run python infra/scripts/runbook-triggers.py triggers; }

c_runbook_sections_without_a_retire_when() { uv run python infra/scripts/runbook-triggers.py retire-when; }

# The runbook pages take the corpus's universal test (the owner, 2026-09-11): the guard's own bullet reader over the
# tracked top-level pages, the README aside because its own bullets state the rule rather than an operator's steps. It reads 0 and the pages are in the
# guard's contract set, so this entry is the number behind a gate rather than an instrument in front of one.
c_runbook_universals_without_a_count() { git ls-files 'infra/runbooks/*.md' | grep -vE '^infra/runbooks/(README\.md$|[^/]+/)' | xargs uv run python infra/scripts/guidance-guard.py --uncounted | wc -l; }  # top-level pages only, the set the guard judges

# Every successful capture-touching row -- a capture tag, or an un-tagged site.yml run -- becomes one
# restart event per capture host it limits to (the capture_host group is both), and the count is the
# pairs of events on different hosts within an hour of each other; a group row pairs with itself.
# The `capture_host` arm below is for the rows already written: `converge.sh` refuses a group limit
# now — `--limit capture_host` restarts both capture hosts close together, which the rule forbids.
c_capture_hosts_converged_within_an_hour() { jq -s '[.[] | select(.rc == 0 and ((.tags | test("capture")) or .tags == "") and (.limit == "zcrypto" or .limit == "zcrypto-red" or .limit == "capture_host")) | . as $r | (if .limit == "capture_host" then ["zcrypto", "zcrypto-red"] else [.limit] end)[] | {host: ., t: ($r.ts | fromdate)}] | sort_by(.t) | [range(0; length) as $i | range($i + 1; length) as $j | select(.[$i].host != .[$j].host and (.[$j].t - .[$i].t) <= 3600)] | length' docs/reference/deploy-log.jsonl; }

c_converge_sh_wrapped_in_timeout() { git grep -nE 'timeout +[0-9]+[smh]? .*converge\.sh' -- ':!*.md' | wc -l; }

c_micro_prs() { count_micro_prs develop; }

# The other count the corpus does not carry: claude-kind commits since the last refine round
# closed. A missing closing commit is an error, never a count over the whole history.
c_claude_commits_since_the_round_closed() {
  local base
  base="$(git log -1 --grep='^Refine-Round-Closed:' --format=%h)"
  if [ -z "$base" ]; then return 2; fi
  git log "${base}..develop" --no-merges --format=%s | grep -c '^claude('
}

# The third count the corpus does not carry: processes with a cwd inside a worktree, the read that
# catches a stale worktree whatever its branch's merge state (the protocol's worktree line).
c_worktree_processes() { for l in /proc/[0-9]*/cwd; do readlink "$l"; done 2>/dev/null | grep -c /tmp/claude-1000/; }

# The fourth: the always-loaded bytes -- the corpus whole, plus every skill's name and description values,
# which load with it -- measured by the guard's own parser, so this entry and what the guard refuses to
# grow without a stated reason cannot disagree.
c_ambient_bytes() { uv run python infra/scripts/guidance-guard.py --ambient-bytes; }

# --- The W15 candidates that earned an entry --------------------------------------------------------
# Eleven bullets of the runbook pages declared `(no count command: …)` in the universal pass because the
# pass added no entries; these ten counts are what they earned (one serves two pages). The other 31
# candidates stay declarations: a value whose healthy state is non-zero names no finding, a proxy for an
# operator's keystroke is not the set, and an act nothing records cannot be counted.

# A converge that passed `-e <role>_digest=` with nothing after the `=`: the role reads it as defined and
# renders a broken image ref. `converge.sh` refuses an empty value before the pass now, so this
# counts the rows written before that arm landed.
c_deploy_rows_with_an_empty_digest_var() { jq -s '[.[] | select((.extra_vars // {}) | to_entries | any((.key | endswith("_digest")) and ((.value | tostring) | test("^[[:space:]]*$"))))] | length' docs/reference/deploy-log.jsonl; }

# The read-only healthchecks key reaching a host: today only `hc_prometheus_metrics_path` renders, and the
# `group_vars/all/` copy is read from the workstation by file path. A role naming the key is the finding.
c_hc_readonly_key_in_a_role() { git grep -nE 'healthchecks_readonly_api_key' -- infra/ansible/roles | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# A write to one of the six gate gauges from outside `_ExecGauges.update`, whose single call is what makes
# a frozen gauge set indistinguishable from a live one. The awk excises that method's body alone.
c_gate_gauge_writes_outside_the_publish_call() { [ -f cli/engine/command.py ] || return 2; { awk '/^    def update\(self, verdict/{i=1;next} i&&(/^    (def |@)/||/^[^ ]/){i=0} !i' cli/engine/command.py; git grep -h -E '\.(gate_level|armed|kill_tripped|restart_hold|venue_ok|last_evaluation)\.set\(' -- cli ':!cli/engine/command.py'; } | grep -cE '\.(gate_level|armed|kill_tripped|restart_hold|venue_ok|last_evaluation)\.set\('; }

# `--delete` anywhere in the archive pull's module: the mirror keeps every day it ever fetched, which is
# what makes a mismatch count span days and an empty tree mean the pull has never succeeded.
c_archive_pull_delete_flags() { [ -f cli/archive/command.py ] || return 2; grep -nE -- '--delete' cli/archive/command.py | grep -vcE '^[0-9]+:[[:space:]]*#'; }

# A deployed `--cache` naming a path outside `/tmp/`: wider than the bullet's "a path both hosts reach",
# which is the direction that never under-reports the siting the cross-host poisoning rule forbids.
c_gate_cache_args_outside_tmp() { git grep -nE -- '--cache[ =]["'"'"'$]?[/$~.]' -- infra cli ':!*.md' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -vcE -- '--cache[ =]["'"'"']?/tmp/'; }

# A rule whose `folderUID` is a literal rather than `${GRAFANA_ALERT_FOLDER_UID}`: it provisions into
# another folder AND escapes the push script's orphan prune, which selects by that same field.
# shellcheck disable=SC2016  # ${GRAFANA_ALERT_FOLDER_UID} is the placeholder text alerts.yaml carries, compared as a literal
c_alert_rules_without_the_folder_literal() { uv run python -c 'import yaml;print(sum(r.get("folderUID")!="${GRAFANA_ALERT_FOLDER_UID}" for r in yaml.safe_load(open("infra/grafana/alerts.yaml"))["rules"]))'; }

# A verified nautilus version with no adapter-verification record carrying a PASS. Both arming guards read
# that file, so a version added without its attended record is live money on an uncleared adapter.
c_verified_versions_without_a_pass_record() { jq -r '.verified_nautilus_versions[]' cli/engine/order-semantics-verified.json | while read -r v; do grep -qE '\*\*(Verdict: )?PASS\b' "docs/reference/adapter-verification/$v.md" 2>/dev/null || echo "$v"; done | wc -l; }

# A member of the inventory's `engine_host` group other than `zcrypto`: every "primary only" reading on
# the capture-daemon and hosts pages rests on that group holding one host, and the live trade key with it.
c_engine_hosts_besides_the_primary() {
  uv run python - <<'INV'
import yaml

inventory = yaml.safe_load(open("infra/ansible/inventory/hosts.yml"))["all"]
index: dict[str, dict] = {}


def collect(groups):
    """Every group by name, wherever the file defines it and however often -- a group's body may sit under
    `all.children`, nested inside another group, or be split across both, and Ansible merges them all."""
    for name, node in (groups or {}).items():
        node = node or {}
        entry = index.setdefault(name, {"hosts": {}, "children": {}})
        entry["hosts"].update(node.get("hosts") or {})
        entry["children"].update({child: (body or {}) for child, body in (node.get("children") or {}).items()})
        collect(node.get("children"))


collect(inventory.get("children"))
index["engine_host"]  # a KeyError here is the group gone, which must be loud rather than a zero
members, seen, stack = set(), set(), ["engine_host"]
while stack:  # a host reaches the group through a child group too, and it holds the trade key just the same
    name = stack.pop()
    if name in seen:
        continue
    seen.add(name)
    node = index.get(name) or {"hosts": {}, "children": {}}
    members |= set(node["hosts"])
    stack += list(node["children"])
print(len(members - {"zcrypto"}))
INV
}

# `docker inspect <container>` with no `--format`, the form that prints the whole config -- the live Kraken
# trade key with it on the engine host. Each INVOCATION is read, cut at `;`, `&&` or `|`, so an unscoped inspect
# beside a formatted command counts; a backticked mention in prose has no operand and does not. A WRAPPED
# invocation whose `--format` sits on the continuation line counts too, over-reporting in the safe direction for a
# prohibition, since a line-oriented grep cannot see the next line. Narrower than the
# bare command an operator types at a prompt, which nothing records.
c_unscoped_docker_inspects_invoked() { git grep -nE 'docker inspect +[^`;&|]' -- infra cli .claude ':!*.md' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -oE 'docker inspect +[^`;&|][^;&|]*' | grep -vcE -- '--format|-f '; }

# The pinned leaves the edge renders, one `file /etc/caddy/pinned-leaves/<name>.pem` line per tracked PEM:
# a figure to read, not a gate. At 1 every revocation issues its replacement first; at 0 the block is empty.
# Read from the INDEX, while `access_pinned_leaves` globs the filesystem: an untracked PEM in that directory would
# render and is not counted here, which is the direction that keeps the number reproducible in CI. Left knowingly.
c_pinned_leaves_the_edge_renders() { git ls-files ':(glob)infra/ansible/roles/access/files/pinned-leaves/*.pem' | wc -l; }

c_pins_not_yet_converged() { uv run python infra/scripts/pins-converged.py; }

main() {
  wanted=("$@")
  cd "$(git rev-parse --show-toplevel)" || exit 2
  # Five counts read the integration branch by name. A checkout without that ref answers 0 from
  # inside a process substitution, where the failure never reaches the pipeline's status.
  if ! git rev-parse --verify --quiet develop >/dev/null; then
    echo "count-list: this checkout has no develop ref, and five of the counts read it by name" >&2
    exit 2
  fi

  emit "markdown-directly-under-docs" c_docs_markdown_at_the_root
  emit "non-pr-merges-on-develop" c_non_pr_merges
  emit "engine-env-forms-invoked" c_engine_env_forms
  emit "ansible-inventory-secret-forms-invoked" c_ansible_inventory_forms
  emit "kraken-cli-on-infra-surfaces" c_kraken_cli_on_infra
  emit "prose-chars" c_prose_chars
  emit "prose-only-commits-without-the-prover" c_prose_only_commits_without_the_prover
  emit "probe-verdicts-without-the-script" c_probe_verdicts_without_the_script
  emit "spec-hash-provenance" c_spec_hash_provenance
  emit "operator-term-surfaces" c_operator_term_surfaces c_operator_term_allowlist_edits
  emit "skip-gate-contract" c_skip_gate_contract
  emit "live-topics-without-a-trigger" c_topics_without_a_trigger
  emit "runbook-bullets-with-an-internal-token" c_runbook_bullets_with_an_internal_token
  emit "canary-bypasses-on-the-primary" c_canary_bypasses
  emit "converges-inside-a-kraken-window" c_converges_inside_a_kraken_window
  emit "drills-on-the-primary" c_drills_on_the_primary
  emit "un-tagged-primary-runs" c_un_tagged_primary_runs
  emit "engine-rows-outside-the-gap" c_engine_rows_outside_the_gap
  emit "nas-rows-without-compat" c_nas_rows_without_compat
  emit "image-removals-outside-the-pruner" c_image_removals_outside_the_pruner
  emit "inspect-reads-of-dot-image" c_inspect_reads_of_dot_image
  emit "capture-hosts-with-automatic-reboot" c_capture_hosts_with_automatic_reboot
  emit "capture-hosts-converged-within-an-hour" c_capture_hosts_converged_within_an_hour
  emit "runbook-sections-without-a-trigger" c_runbook_sections_without_a_trigger
  emit "runbook-sections-without-a-retire-when" c_runbook_sections_without_a_retire_when
  emit "runbook-universals-without-a-count" c_runbook_universals_without_a_count
  emit "converge-sh-wrapped-in-timeout" c_converge_sh_wrapped_in_timeout
  emit "topic-only-merges" c_micro_prs
  emit "claude-commits-since-the-round-closed" c_claude_commits_since_the_round_closed
  emit "worktrees" c_worktree_processes
  emit "ambient-bytes" c_ambient_bytes
  emit "merged-prs-without-a-floor-read-30d" c_merged_prs_without_a_floor_read
  emit "deploy-rows-with-an-empty-digest-var" c_deploy_rows_with_an_empty_digest_var
  emit "hc-readonly-key-in-a-role" c_hc_readonly_key_in_a_role
  emit "gate-gauge-writes-outside-the-publish-call" c_gate_gauge_writes_outside_the_publish_call
  emit "archive-pull-delete-flags" c_archive_pull_delete_flags
  emit "gate-cache-args-outside-tmp" c_gate_cache_args_outside_tmp
  emit "alert-rules-without-the-folder-literal" c_alert_rules_without_the_folder_literal
  emit "verified-versions-without-a-pass-record" c_verified_versions_without_a_pass_record
  emit "engine-hosts-besides-the-primary" c_engine_hosts_besides_the_primary
  emit "unscoped-docker-inspects-invoked" c_unscoped_docker_inspects_invoked
  emit "pins-not-yet-converged" c_pins_not_yet_converged
  emit "pinned-leaves-the-edge-renders" c_pinned_leaves_the_edge_renders

  local w
  for w in "${wanted[@]}"; do
    case " ${seen[*]} " in *" $w "*) ;; *) echo "count-list: no entry named $w" >&2; exit 2 ;; esac
  done

  if [ "${#errors[@]}" -gt 0 ]; then
    printf 'count-list: %s command(s) errored: %s\n' "${#errors[@]}" "${errors[*]}" >&2
    exit 2
  fi
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then main "$@"; fi
