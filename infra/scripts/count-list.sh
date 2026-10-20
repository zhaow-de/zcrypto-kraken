#!/usr/bin/env bash
# One line per entry -- its name and today's value -- for every count the corpus and the contracts name by entry; a universal with no entry beside it is the finding.
# Usage: count-list.sh [entry...] -- every entry, or only the named ones; a name no entry answers to is exit 2.
# COUNT_LIST_ALL=1 counts every deploy-log row where an entry reads only those since the last refine round closed.
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

# retire when: a pre-commit hook in .pre-commit-config.yaml refuses a staged docs/*.md, the refusal replacing this count
c_docs_markdown_at_the_root() { git ls-files ':(glob)docs/*.md' | wc -l; }

# retire when: the trade key and the Loki password leave the engine container's env for a mounted secrets file in infra/ansible/roles/engine/, so an env dump prints nothing
c_engine_env_forms() { git grep -nE '\{\{ ?json \.Config(\.Env)? ?\}\}|docker exec [^|;]* env( |$)|docker compose config' -- infra .claude cli ':!*.md' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# retire when: the inventory's secrets leave ansible-vault for a store ansible-inventory cannot render, infra/ansible/scripts/vault-pass.sh retired with them
c_ansible_inventory_forms() { git grep -nE 'ansible-inventory( +\S+)* +--(host|list|vars)' -- infra .claude cli ':!*.md' ':!infra/ansible/scripts/vault-pass.sh' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# retire when: the refine round stops reading it
c_prose_chars() { uv run python infra/scripts/prose-chars.py; }

# This entry CALLS merge-gate.py's `read_line_fails` rather than restating it: a counter that disagrees with the gate
# about the same rule measures nothing, and a change to the gate moves this count by construction. A gate change
# moves this window to its own instant only when it counts a PR merged before it: that PR was judged by the gate of
# its day and breaks no rule.
READ_LINE_RULE_SINCE="2026-09-20T12:06:05Z"
# A rule's window is a full INSTANT, never a bare date: `git log --since=2026-09-13` is approxidate and fills
# the missing time from the run's clock, so a bare date slides the window through the day and reads 0 over an
# empty set in the morning. `tests/test_count_list.py` refuses any RULE_SINCE that is not an instant.
PROSE_ONLY_RULE_SINCE="2026-09-13T00:00:00Z"
# One second past 095f96016 (2026-09-21T17:42:22Z), excusing it and 07aeec2f2 (17:42:01Z) and nothing else: the
# 00117 spec and plan docs commits of PR #584, merged and unrewritable, whose "KILLED with control proven" sums up
# verdicts their sibling fix(engine) commits earned through the script. Unexcused they pin this count above 0 for
# good, and a count that cannot read 0 is not a detector. The window is the LATER of this and the clause's landing,
# so an earlier value cannot widen the count past the rule.
PROBE_VERDICT_RULE_SINCE="2026-09-21T17:42:23Z"
# retire when: the whole-branch read is a required status check in .github/settings.yml, GitHub refusing the merge instead of merge-gate.py's read-line arm
c_merged_prs_without_a_floor_read() {
  local prs floor oldest
  if [ -n "${COUNT_LIST_PRS_SNAPSHOT:-}" ]; then prs="$(cat "$COUNT_LIST_PRS_SNAPSHOT")" || return 2
  else prs="$(timeout 120 gh pr list --state merged --base develop --limit 400 \
    --json number,body,mergedAt,headRefName,headRefOid,files,mergeCommit)" || return 2
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
GH_TIMEOUT = float(os.environ.get("COUNT_LIST_GH_TIMEOUT") or 120)


def gh(*args):
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None


def refuse(what, done):
    why = f"no answer in {GH_TIMEOUT:g}s" if done is None else f"exit {done.returncode}: {done.stderr.strip()[:200]}"
    print(f"count-list: {what}: {why}", file=sys.stderr)
    raise SystemExit(2)


def commit_of(sha, number, on_github=False):
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
    done = gh("api", f"repos/{gate.REPO}/commits/{sha}")
    if done is None or (on_github and done.returncode != 0):
        refuse(f"PR #{number}'s commit {sha} could not be fetched -- whether the read covers the head cannot be decided", done)
    return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None


def read_sha(pr):
    m = gate.READ_LINE.search(gate._as_a_reader_sees_it(pr.get("body") or ""))
    return m.group(2) if m else ""

files_snapshot = json.loads(pathlib.Path(os.environ["COUNT_LIST_FILES_SNAPSHOT"]).read_text()) if os.environ.get(
    "COUNT_LIST_FILES_SNAPSHOT") else None


def file_paths(pr):
    """The files endpoint's paths, or a COUNT_LIST_FILES_SNAPSHOT `{number: [path]}` map's, plus every bulk path they lack."""
    rows = pr.get("files")
    if rows is None:
        return None
    paths = [f.get("path") for f in rows]
    if files_snapshot is not None:
        fetched = files_snapshot.get(str(pr.get("number")), [])
    elif offline:
        return paths
    else:
        done = gh("api", "--paginate", f"repos/{gate.REPO}/pulls/{pr.get('number')}/files", "--jq", gate.PR_FILES_JQ)
        if done is None or done.returncode != 0:
            refuse(f"PR #{pr.get('number')}'s file list could not be fetched -- the Fable-path arm cannot be decided", done)
        fetched = [line for line in done.stdout.splitlines() if line.strip()]
    return fetched + [p for p in paths if p not in fetched]


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
    done = gh("pr", "view", number, "--json", "commits")
    if done is None or done.returncode != 0:
        refuse(
            f"PR #{number} is a dependabot branch whose commits could not be fetched, so the no-fix-commit exemption "
            "cannot be decided",
            done,
        )
    return {**pr, "commits": (json.loads(done.stdout) or {}).get("commits") or []}


kept_snapshot = json.loads(pathlib.Path(os.environ["COUNT_LIST_KEPT_SNAPSHOT"]).read_text()) if os.environ.get(
    "COUNT_LIST_KEPT_SNAPSHOT") else None
root = pathlib.Path(sys.argv[1]).resolve().parents[2]


def kept(pr):
    """`head_is_the_read`'s answer for the tip the body names against the merged head, from the PR's base at the
    merge -- the merge commit's first parent, since develop has moved on. COUNT_LIST_KEPT_SNAPSHOT names a
    recorded `{headRefOid: answer}` map so the wiring can be driven without the PR's commits in the clone;
    offline with no map, or a PR with no merge commit, answers None and the row is counted rather than excused."""
    head = pr.get("headRefOid") or ""
    if kept_snapshot is not None:
        return kept_snapshot.get(head)
    merge = (pr.get("mergeCommit") or {}).get("oid")
    if offline or not merge:
        return None
    read = (commit_of(read_sha(pr), pr.get("number")) or {}).get("sha") or read_sha(pr)
    return gate.head_is_the_read(read, head, f"{merge}^", cwd=root)


count = 0
for pr in json.loads(pathlib.Path(sys.argv[2]).read_text()):
    if (pr.get("mergedAt") or "") < floor:
        continue
    pr = with_commits(pr)
    files = file_paths(pr)
    fails = gate.read_line_fails(pr, None, files)
    head_commit = None
    if fails and all("not the head" in f for f in fails):
        head_commit = commit_of(pr.get("headRefOid"), pr.get("number"), on_github=True)
        fails = gate.read_line_fails(pr, head_commit, files)
    if fails and all("not the head" in f for f in fails):
        fails = gate.read_line_fails(pr, head_commit, files, kept(pr))  # the clone is asked only where the row arm did not admit
    if fails:
        count += 1
print(count)
PYGATE
  local rc=$?
  rm -f "$rows"
  return "$rc"
}

# retire when: kraken-cli leaves the workstation too — git grep kraken-cli over the tree and docs/reference hits nothing
c_kraken_cli_on_infra() { git grep -c kraken-cli -- infra cli ':!*.md' ':!infra/scripts/count-list.sh' | wc -l; }

# retire when: a commit-msg hook in .pre-commit-config.yaml runs infra/scripts/prove-inert.py over a message that says prose-only, refusing the claim at the commit
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
# retire when: infra/scripts/message-citations.py, the commit-msg hook, refuses KILLED, SURVIVED or control proven without mutate-probe named, the refusal replacing this count
c_probe_verdicts_without_the_script() {
  local landed since
  landed="$(git log develop HEAD --reverse --format=%cI -S'probe-verdicts-without-the-script' -- CLAUDE.md | head -1)"
  if [ -z "$landed" ]; then
    echo "count-list: no commit adds the probe-block clause to CLAUDE.md, so this count has no window" >&2
    return 2
  fi
  since="$landed"
  [[ "$PROBE_VERDICT_RULE_SINCE" > "$since" ]] && since="$PROBE_VERDICT_RULE_SINCE"
  # A docs(plans) or docs(specs) commit quotes a plan's probe rows, whose fences name the script themselves: out.
  comm -23 <(git log develop HEAD --since="$since" --grep='control proven' --grep=KILLED --grep=SURVIVED --format='%h %s' | grep -vE ' docs\((plans|specs)\)' | cut -d' ' -f1 | sort) \
           <(git log develop HEAD --since="$since" --grep=mutate-probe --format=%h | sort) | wc -l
}

# A failing suite is an error, never a zero count: its output still carries a "N passed" summary.
# retire when: no record in trial-registry.jsonl or reading-ledger.jsonl carries spec_hash — tests/test_trial_registry_provenance.py goes with them
c_spec_hash_provenance() { uv run pytest tests/test_trial_registry_provenance.py -q || return 2; }

# retire when: tests/test_internal_terms_not_operator_visible.py is removed — the operator-read surfaces it walks gone, or the internal-token vocabulary retired
c_operator_term_surfaces() { uv run pytest tests/test_internal_terms_not_operator_visible.py -q || return 2; }

# retire when: _WP_CARRIERS is gone from tests/test_internal_terms_not_operator_visible.py — no allowlist left to widen
c_operator_term_allowlist_edits() { git log --oneline -G_WP_CARRIERS -- tests/test_internal_terms_not_operator_visible.py | wc -l; }

# The skip gates under `tests/` the guard finds: one opt-in name over those, and every guard one of six
# forms or refused with the remedy it prints. The guard is the count.
# retire when: no test under tests/ reaches a venue — tests/test_live_venue_opt_in.py finds no skip gate and is removed
c_skip_gate_contract() { uv run pytest tests/test_live_venue_opt_in.py -q || return 2; }

# A deploy-log count that calls this reads the rows stamped at or after the previous refine round's closing commit --
# its commit date, the anchor `c_claude_commits_since_the_round_closed` finds -- so a row a round has read is not
# counted again in the next; the capture-pair count pairs every row first and keeps a pair whose later row is so
# stamped, so a pair straddling the close counts once. COUNT_LIST_DEPLOY_LOG names another log for them, which is how
# a test drives the window.
round_closed_at() {
  [ "${COUNT_LIST_ALL:-}" = 1 ] && return 0
  local closed
  closed="$(git log -1 --grep='^Refine-Round-Closed:' --format=%cI)" || return 2
  if [ -z "$closed" ]; then
    echo "count-list: no commit carries a Refine-Round-Closed: trailer, so the deploy-log window has no start" >&2
    return 2
  fi
  date -u -d "$closed" +%Y-%m-%dT%H:%M:%SZ || return 2
}

# The bypasses the ROW names. `converge.sh` accepts an override as JSON and refuses every other
# spelling before the pass, so every bypass THROUGH IT is here; `run.sh` takes raw ansible argv and
# writes no row at all, which is the hole this count cannot see and the confirm gate is why.
# retire when: canary_override is gone from infra/ansible/roles/capture/tasks/main.yml — no bypass left to count
c_canary_bypasses() {
  local since
  since="$(round_closed_at)" || return 2
  jq -c --arg since "$since" 'select(($since == "" or (.ts | fromdate) >= ($since | fromdate)) and .limit=="zcrypto" and .extra_vars.canary_override!=null)' "${COUNT_LIST_DEPLOY_LOG:-docs/reference/deploy-log.jsonl}" | wc -l
}

# COUNT_LIST_FEED_SNAPSHOT is the snapshot arm of the audit: set it and the count reads a recorded
# feed instead of the network, which is how a test runs this line and how a rolled feed keeps its
# coverage. Unset, the count is the live feed, as the corpus states it.
# retire when: infra/ansible/scripts/converge.sh reads the scheduled-maintenances feed whole and refuses a venue-facing run inside a window, the refusal replacing this count
c_converges_inside_a_kraken_window() {
  local feed=()
  if [ -n "${COUNT_LIST_FEED_SNAPSHOT:-}" ]; then feed=(--from-snapshot "$COUNT_LIST_FEED_SNAPSHOT"); fi
  # `--venue-facing` is the rule's own set; the audit's unnarrowed arm still reports every row.
  uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing "${feed[@]}" | sed -n 's/^rows inside an API-impacting window \([0-9][0-9]*\) of .*/\1/p'
}

# shellcheck disable=SC2016  # the backticks are the drill-log row's literal Markdown fences
# `, the engine` opens an order-path entry, outside the rule's set (.claude/rules/fleet-deploys.md).
# retire when: docs/reference/drill-log.md is closed — no drill family open in infra/runbooks/drills-telemetry.md or infra/runbooks/drills-order-path.md
c_drills_on_the_primary() {
  local log="${COUNT_LIST_DRILL_LOG:-docs/reference/drill-log.md}"
  [ -f "$log" ] && [ -r "$log" ] || return 2
  grep -E '^\*host\* `zcrypto`' "$log" | grep -vcE '^\*host\* `zcrypto`, the engine\b'
}

# `--skip-tags engine` is infra/README.md's published primary form and names no tag, so it books an
# empty `tags` and its own `skip_tags` cell; counting it here would read a violation that never was.
# retire when: infra/ansible/scripts/converge.sh refuses --limit zcrypto with neither --tags nor --skip-tags, the refusal replacing this count
c_un_tagged_primary_runs() { jq -c 'select(.limit=="zcrypto" and .tags=="" and (.skip_tags // "")=="")' docs/reference/deploy-log.jsonl | wc -l; }

# retire when: the engine converge no longer needs the inter-cycle gap — the window assert gone from infra/ansible/site.yml with the 4-hourly cycle, or infra/ansible/roles/engine/ removed
c_engine_rows_outside_the_gap() {
  local since window=()
  since="$(round_closed_at)" || return 2
  if [ -n "$since" ]; then window=(--since "$since"); fi
  uv run python infra/scripts/deploy-log-audit.py engine-window --log "${COUNT_LIST_DEPLOY_LOG:-docs/reference/deploy-log.jsonl}" "${window[@]}" | sed -n 's/^engine rows [0-9][0-9]* outside window \([0-9][0-9]*\) .*/\1/p'
}

# The engine window's bypasses: every row whose run carried a non-null `engine_window_override`, recorded or not.
# One without a record that landed outside the fixed gap is counted by the entry above as well.
# retire when: engine_window_override is gone from infra/ansible/site.yml — no bypass left to count
c_engine_window_overrides() {
  local since window=()
  since="$(round_closed_at)" || return 2
  if [ -n "$since" ]; then window=(--since "$since"); fi
  uv run python infra/scripts/deploy-log-audit.py engine-window --log "${COUNT_LIST_DEPLOY_LOG:-docs/reference/deploy-log.jsonl}" "${window[@]}" | sed -n 's/^engine rows .* overridden \([0-9][0-9]*\) inferred .*/\1/p'
}

# A watch number, not a gate: the band's successful rows that carry no well-formed `window`, whose admission can only be inferred.
# retire when: every engine row since the floor carries a well-formed window — infra/ansible/scripts/converge.sh writes it on each engine run, nothing left to infer
c_engine_rows_on_the_completion_floor() {
  local since window=()
  since="$(round_closed_at)" || return 2
  if [ -n "$since" ]; then window=(--since "$since"); fi
  uv run python infra/scripts/deploy-log-audit.py engine-window --log "${COUNT_LIST_DEPLOY_LOG:-docs/reference/deploy-log.jsonl}" "${window[@]}" | sed -n 's/^engine rows .*of which on the completion floor \([0-9][0-9]*\)$/\1/p'
}

# The window opens at the log's first row carrying a `preflight`, the rows before it gated by the capture bake. An empty
# `tags` stays out: `site.yml` admits one on the primary only beside `--skip-tags engine`, a run of no engine-role task.
# shellcheck disable=SC2016  # $first and $since are jq's, bound by the program and by --arg
engine_preflight_rows='(map(has("preflight")) | index(true)) as $first | if $first == null then [] else .[$first:] end | map(select(($since == "" or (.ts | fromdate) >= ($since | fromdate)) and .limit == "zcrypto" and (.tags | split(",") | any(. == "engine")) and .extra_vars.engine_image_digest != null))'

# retire when: engine_preflight_override is gone from infra/ansible/roles/engine/tasks/main.yml — no bypass left to count
c_engine_preflight_overrides() {
  local since
  since="$(round_closed_at)" || return 2
  jq -s --arg since "$since" "$engine_preflight_rows"' | map(select(.extra_vars.engine_preflight_override != null)) | length' "${COUNT_LIST_DEPLOY_LOG:-docs/reference/deploy-log.jsonl}"
}

# retire when: the NAS leaves the fleet (no nas row in docs/reference/fleet-pins.md), or the compat runtime is dropped from .github/workflows/capture-image.yml
c_nas_rows_without_compat() { awk -F'|' '$3 ~ /^ *nas *$/' docs/reference/fleet-pins.md | grep -vc compat; }

# retire when: infra/scripts/prune-host-images.py is retired for a role or timer that prunes on the host — the rule's only-by-the-script clause gone with it
c_image_removals_outside_the_pruner() { git grep -nE 'docker (image (prune|rm)|rmi|system prune)' -- infra cli .claude ':!*.md' ':!infra/scripts/prune-host-images.py' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# retire when: no fleet role under infra/ansible/roles/ runs docker — the container read docs/reference/fleet-pins.md prescribes gone with it
c_inspect_reads_of_dot_image() { git grep -nE '\{\{ ?(json )?\.Image ?\}\}' -- infra cli .claude ':!*.md' ':!infra/scripts/count-list.sh' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# A host that reboots by hand counts unless the setting it reads first -- its host_vars, else its group's --
# is one of six false spellings (0, f, false, n, no, off): the template renders the value raw into apt's config,
# whose reader accepts these and more, so the count never under-reports. A host with the key in neither file
# counts too, since the base role's default is not read here.
# retire when: the five hosts leave infra/ansible/inventory/hosts.yml, or the base role refuses a truthy base_unattended_upgrades_automatic_reboot on them with tests/test_infra_unattended_upgrades.py proving it
c_attended_hosts_with_automatic_reboot() {
  local h f n=0
  for h in zcrypto:capture_host zcrypto-red:capture_host zcrypto-ops:ops_host zcrypto-mon:mon_host zcrypto-hc:hc_host; do
    for f in "infra/ansible/host_vars/${h%%:*}/vars.yml" "infra/ansible/group_vars/${h#*:}/vars.yml"; do
      if grep -qE '^base_unattended_upgrades_automatic_reboot:' "$f" 2>/dev/null; then
        grep -qiE '^base_unattended_upgrades_automatic_reboot: *["'"'"']?(0|f|false|n|no|off)["'"'"']? *$' "$f" || n=$((n + 1))
        continue 2
      fi
    done
    n=$((n + 1))
  done
  echo "$n"
}

# retire when: infra/scripts/runbook-triggers.py triggers is a pre-commit hook in .pre-commit-config.yaml, refusing an untriggered section at the commit
c_runbook_sections_without_a_trigger() { uv run python infra/scripts/runbook-triggers.py triggers; }

# retire when: infra/scripts/runbook-triggers.py retire-when is a pre-commit hook in .pre-commit-config.yaml, refusing the section at the commit
c_runbook_sections_without_a_retire_when() { uv run python infra/scripts/runbook-triggers.py retire-when; }

# Every successful capture-touching row -- a capture tag, or an un-tagged site.yml run -- becomes one
# restart event per capture host it limits to (the capture_host group is both), and the count is the
# pairs of events on different hosts within an hour of each other; a group row pairs with itself.
# The `capture_host` arm below is for the rows already written: `converge.sh` refuses a group limit
# now — `--limit capture_host` restarts both capture hosts close together, which the rule forbids.
# retire when: infra/ansible/scripts/converge.sh reads docs/reference/deploy-log.jsonl and refuses a capture-host run within an hour of the other host's, the refusal replacing this count
c_capture_hosts_converged_within_an_hour() {
  local since
  since="$(round_closed_at)" || return 2
  jq -s --arg since "$since" '[.[] | select(.rc == 0 and ((.tags | test("capture")) or .tags == "") and (.limit == "zcrypto" or .limit == "zcrypto-red" or .limit == "capture_host")) | . as $r | (if .limit == "capture_host" then ["zcrypto", "zcrypto-red"] else [.limit] end)[] | {host: ., t: ($r.ts | fromdate)}] | sort_by(.t) | [range(0; length) as $i | range($i + 1; length) as $j | select(.[$i].host != .[$j].host and (.[$j].t - .[$i].t) <= 3600 and ($since == "" or .[$j].t >= ($since | fromdate)))] | length' "${COUNT_LIST_DEPLOY_LOG:-docs/reference/deploy-log.jsonl}"
}

# retire when: infra/ansible/scripts/converge.sh stops reading /dev/tty for its confirm — a timeout then kills the whole run, the rule's harm gone
c_converge_sh_wrapped_in_timeout() { git grep -nE 'timeout +[0-9]+[smh]? .*converge\.sh' -- ':!*.md' | wc -l; }

# The count the corpus does not carry: claude-kind commits since the last refine round
# closed. A missing closing commit is an error, never a count over the whole history.
# retire when: the refine round stops reading it
c_claude_commits_since_the_round_closed() {
  local base
  base="$(git log -1 --grep='^Refine-Round-Closed:' --format=%h)"
  if [ -z "$base" ]; then return 2; fi
  git log "${base}..develop" --no-merges --format=%s | grep -c '^claude('
}

# The other: the always-loaded bytes -- the corpus whole, plus every skill's name and description values,
# which load with it -- measured by the guard's own parser, so this entry and what the guard refuses to
# grow without a stated reason cannot disagree.
# retire when: the refine round stops reading it
c_ambient_bytes() { uv run python infra/scripts/guidance-guard.py --ambient-bytes; }

# --- The W15 candidates that earned an entry --------------------------------------------------------
# Eleven bullets of the runbook pages declared `(no count command: …)` in the universal pass because the
# pass added no entries; these ten counts are what they earned (one serves two pages). The other 31
# candidates stay declarations: a value whose healthy state is non-zero names no finding, a proxy for an
# operator's keystroke is not the set, and an act nothing records cannot be counted.

# A converge that passed `-e <role>_digest=` with nothing after the `=`: the role reads it as defined and
# renders a broken image ref. `converge.sh` refuses an empty value before the pass now, so this
# counts the rows written before that arm landed.
# retire when: docs/reference/deploy-log.jsonl is rotated past the rows written before infra/ansible/scripts/converge.sh's empty-digest refusal — the only rows the count can read
c_deploy_rows_with_an_empty_digest_var() { jq -s '[.[] | select((.extra_vars // {}) | to_entries | any((.key | endswith("_digest")) and ((.value | tostring) | test("^[[:space:]]*$"))))] | length' docs/reference/deploy-log.jsonl; }

# The service's read-only key, or healthchecks.io's (healthchecks_readonly_api_key), named on a non-comment line of a
# role outside the service key's one render, ops' Alloy secrets template.
# retire when: the healthchecks.io scrape leaves ops' Alloy — infra/ansible/roles/ops/templates/alloy-secrets.env.j2 no longer renders the key
c_hc_readonly_key_in_a_role() { git grep -nE '(hc|healthchecks)_readonly_api_key' -- infra/ansible/roles ':!infra/ansible/roles/ops/templates/alloy-secrets.env.j2' | grep -vcE '^[^:]+:[0-9]+:[[:space:]]*#'; }

# A write to one of the seven gate gauges from outside `_ExecGauges.update`, whose one call publishes the
# six readings at every gate evaluation and the heartbeat at each but the executor's idle refresh: a
# write elsewhere is a gauge moving with no evaluation behind it. The awk excises that method's body alone.
# retire when: _ExecGauges.update is gone from cli/engine/command.py — the seven gate gauges published another way, their rule rewritten with it
c_gate_gauge_writes_outside_the_publish_call() { [ -f cli/engine/command.py ] || return 2; { awk '/^    def update\(self, verdict/{i=1;next} i&&(/^    (def |@)/||/^[^ ]/){i=0} !i' cli/engine/command.py; git grep -h -E '\.(gate_level|armed|kill_tripped|restart_hold|venue_ok|venue_read_failed|last_evaluation)\.set\(' -- cli ':!cli/engine/command.py'; } | grep -cE '\.(gate_level|armed|kill_tripped|restart_hold|venue_ok|venue_read_failed|last_evaluation)\.set\('; }

# `--delete` anywhere in the archive pull's module: the mirror keeps every day it ever fetched, which is
# what makes a mismatch count span days and an empty tree mean the pull has never succeeded.
# retire when: the journal pull leaves cli/archive/command.py, or the NAS mirror stops being the retention the engine host's 60-day prune relies on
c_archive_pull_delete_flags() { [ -f cli/archive/command.py ] || return 2; grep -nE -- '--delete' cli/archive/command.py | grep -vcE '^[0-9]+:[[:space:]]*#'; }

# A deployed `--cache` naming a path outside `/tmp/`: wider than the bullet's "a path both hosts reach",
# which is the direction that never under-reports the siting the cross-host poisoning rule forbids.
# retire when: the --cache option is gone from cli/engine/command.py and cli/engine/gate_cache.py — no path left for the cross-host poisoning the ephemeral siting prevents
c_gate_cache_args_outside_tmp() { git grep -nE -- '--cache[ =]["'"'"'$]?[/$~.]' -- infra cli ':!*.md' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -vcE -- '--cache[ =]["'"'"']?/tmp/'; }

# A rule whose `folderUID` is a literal rather than `${GRAFANA_ALERT_FOLDER_UID}`: it provisions into
# another folder AND escapes the push script's orphan prune, which selects by that same field.
# retire when: tests/test_infra_alert_rules.py refuses a rule whose folderUID is not the ${GRAFANA_ALERT_FOLDER_UID} literal, the refusal replacing this count
# shellcheck disable=SC2016  # ${GRAFANA_ALERT_FOLDER_UID} is the placeholder text alerts.yaml carries, compared as a literal
c_alert_rules_without_the_folder_literal() { uv run python -c 'import yaml;print(sum(r.get("folderUID")!="${GRAFANA_ALERT_FOLDER_UID}" for r in yaml.safe_load(open("infra/grafana/alerts.yaml"))["rules"]))'; }

# A verified nautilus version with no adapter-verification record carrying a PASS. Both arming guards read
# that file, so a version added without its attended record is live money on an uncleared adapter.
# retire when: tests/test_nautilus_pin_verified.py refuses a verified_nautilus_versions entry whose docs/reference/adapter-verification/<version>.md carries no PASS, the refusal replacing this count
c_verified_versions_without_a_pass_record() { jq -r '.verified_nautilus_versions[]' cli/engine/order-semantics-verified.json | while read -r v; do grep -qE '\*\*(Verdict: )?PASS\b' "docs/reference/adapter-verification/$v.md" 2>/dev/null || echo "$v"; done | wc -l; }

# A member of the inventory's `engine_host` group other than `zcrypto`: every "primary only" reading on
# the capture-daemon and hosts pages rests on that group holding one host, and the live trade key with it.
# retire when: the engine_host group leaves infra/ansible/inventory/hosts.yml — the engine run elsewhere, every primary-only reading rewritten
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
# retire when: .claude/hooks/bash-guard.sh refuses docker inspect <container> with no --format, the refusal replacing this count
c_unscoped_docker_inspects_invoked() { git grep -nE 'docker inspect +[^`;&|]' -- infra cli .claude ':!*.md' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -oE 'docker inspect +[^`;&|][^;&|]*' | grep -vcE -- '--format|-f '; }

# The pinned leaves the edge renders, one `file /etc/caddy/pinned-leaves/<name>.pem` line per tracked PEM:
# a figure to read, not a gate. At 1 every revocation issues its replacement first; at 0 the block is empty.
# Read from the INDEX, while `access_pinned_leaves` globs the filesystem: an untracked PEM in that directory would
# render and is not counted here, which is the direction that keeps the number reproducible in CI. Left knowingly.
# retire when: infra/ansible/roles/access/files/pinned-leaves/ is gone — the edge verifying clients by a CA instead of pinned leaves
c_pinned_leaves_the_edge_renders() { git ls-files ':(glob)infra/ansible/roles/access/files/pinned-leaves/*.pem' | wc -l; }

# retire when: infra/ansible/scripts/converge.sh writes the pin row itself on a SUCCEEDED run — docs/reference/fleet-pins.md rendered from docs/reference/deploy-log.jsonl, nothing left to disagree
c_pins_not_yet_converged() { uv run python infra/scripts/pins-converged.py; }

# retire when: Alloy leaves the fleet — infra/ansible/group_vars/observed/alloy.yml gone, or the observed group empty in infra/ansible/inventory/hosts.yml
c_hosts_off_the_fleets_alloy_version() { uv run python infra/scripts/alloy-version.py off-fleet; }

main() {
  wanted=("$@")
  cd "$(git rev-parse --show-toplevel)" || exit 2
  # Four counts read the integration branch by name. A checkout without that ref answers 0 from
  # inside a process substitution, where the failure never reaches the pipeline's status.
  if ! git rev-parse --verify --quiet develop >/dev/null; then
    echo "count-list: this checkout has no develop ref, and four of the counts read it by name" >&2
    exit 2
  fi

  emit "markdown-directly-under-docs" c_docs_markdown_at_the_root
  emit "engine-env-forms-invoked" c_engine_env_forms
  emit "ansible-inventory-secret-forms-invoked" c_ansible_inventory_forms
  emit "kraken-cli-on-infra-surfaces" c_kraken_cli_on_infra
  emit "prose-chars" c_prose_chars
  emit "prose-only-commits-without-the-prover" c_prose_only_commits_without_the_prover
  emit "probe-verdicts-without-the-script" c_probe_verdicts_without_the_script
  emit "spec-hash-provenance" c_spec_hash_provenance
  emit "operator-term-surfaces" c_operator_term_surfaces c_operator_term_allowlist_edits
  emit "skip-gate-contract" c_skip_gate_contract
  emit "canary-bypasses-on-the-primary" c_canary_bypasses
  emit "converges-inside-a-kraken-window" c_converges_inside_a_kraken_window
  emit "drills-on-the-primary" c_drills_on_the_primary
  emit "un-tagged-primary-runs" c_un_tagged_primary_runs
  emit "engine-rows-outside-the-gap" c_engine_rows_outside_the_gap
  emit "engine-window-overrides" c_engine_window_overrides
  emit "engine-rows-on-the-completion-floor" c_engine_rows_on_the_completion_floor
  emit "engine-preflight-overrides" c_engine_preflight_overrides
  emit "nas-rows-without-compat" c_nas_rows_without_compat
  emit "image-removals-outside-the-pruner" c_image_removals_outside_the_pruner
  emit "inspect-reads-of-dot-image" c_inspect_reads_of_dot_image
  emit "attended-hosts-with-automatic-reboot" c_attended_hosts_with_automatic_reboot
  emit "capture-hosts-converged-within-an-hour" c_capture_hosts_converged_within_an_hour
  emit "runbook-sections-without-a-trigger" c_runbook_sections_without_a_trigger
  emit "runbook-sections-without-a-retire-when" c_runbook_sections_without_a_retire_when
  emit "converge-sh-wrapped-in-timeout" c_converge_sh_wrapped_in_timeout
  emit "claude-commits-since-the-round-closed" c_claude_commits_since_the_round_closed
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
  emit "hosts-off-the-fleets-alloy-version" c_hosts_off_the_fleets_alloy_version

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
