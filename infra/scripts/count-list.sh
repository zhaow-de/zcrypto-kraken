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

c_engine_env_forms() { git grep -nE '\{\{ ?json \.Config(\.Env)? ?\}\}|docker exec [^|;]* env( |$)|docker compose config' -- infra .claude cli ':!*.md' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | wc -l; }

c_ansible_inventory_forms() { git grep -nE 'ansible-inventory( +\S+)* +--(host|list|vars)' -- infra .claude cli ':!*.md' ':!infra/ansible/scripts/vault-pass.sh' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | wc -l; }

c_prose_chars() { uv run python infra/scripts/prose-chars.py; }

# The journal month PR is exempt from the read (docs/reference/ops-journal/README.md) and is left out; a
# line naming a model below the floor counts as no read, the same as the gate reads it. The line may sit
# anywhere in the body: jq's "m" flag is dot-all, not line anchoring, so the anchor is a literal newline.
# COUNT_LIST_PRS_SNAPSHOT names a recorded `gh pr list` JSON instead of the network, for the test.
c_merged_prs_without_a_floor_read() {
  local prs
  if [ -n "${COUNT_LIST_PRS_SNAPSHOT:-}" ]; then prs="$(cat "$COUNT_LIST_PRS_SNAPSHOT")" || return 2
  else prs="$(timeout 60 gh pr list --state merged --base develop --limit 200 --json body,mergedAt,headRefName)" || return 2; fi
  printf '%s' "$prs" | jq '[.[] | select(.mergedAt >= (now - 2592000 | todate)) | select(.headRefName != "ops-journal") | select((.body // "") | test("(^|\n)Read before push by: Claude (Opus|Fable)\\b.* at [0-9a-f]{7,}") | not)] | length'
}

c_kraken_cli_on_infra() { git grep -c kraken-cli -- infra cli ':!*.md' ':!infra/scripts/count-list.sh' | wc -l; }

c_mutation_commits_without_a_probe() { comm -23 <(git log develop --since=2026-08-03 -i --grep=mutation --format=%h | sort) <(git log develop --since=2026-08-03 -i --grep=mutate-probe --format=%h | sort) | wc -l; }

c_prose_only_commits_without_the_prover() { comm -23 <(git log develop --since=2026-09-09 -i --grep=prose-only --format=%h | sort) <(git log develop --since=2026-09-09 -i --grep=prove-inert --format=%h | sort) | wc -l; }

# A failing suite is an error, never a zero count: its output still carries a "N passed" summary.
c_spec_hash_provenance() { uv run pytest tests/test_trial_registry_provenance.py -q || return 2; }

c_operator_term_surfaces() { uv run pytest tests/test_internal_terms_not_operator_visible.py -q || return 2; }

c_operator_term_allowlist_edits() { git log --oneline -G_WP_CARRIERS -- tests/test_internal_terms_not_operator_visible.py | wc -l; }

# The skip gates under `tests/` the guard finds: one opt-in name over those; a computed key, or a call it can neither
# resolve in this repo nor attribute to a library, refused; a library call attributed, not walked. The guard is the
# count; its docstring lists what passes it uncaught -- five binding shapes, two `unittest` forms.
c_skip_gate_contract() { uv run pytest tests/test_live_venue_opt_in.py -q || return 2; }

c_topics_without_a_trigger() { grep -L '^ripe_when:' docs/open-topics/T*.md | wc -l; }

# The bullets and numbered steps of the top-level runbook pages, `infra/runbooks/README.md` aside, whose own bullets
# state the rule rather than an operator's step: an internal token --
# `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `WP<N>`, `D<N>` -- inside one is a reference an operator who
# reached the page from an alert description cannot resolve. A paragraph, a table row and a declaration's why may
# carry one (a declaration's why is inside its bullet and takes the rule with it); the classes and the path exemption are `tests/test_internal_terms_not_operator_visible.py`'s. One line
# per bullet, its tokens joined, so the count is bullets to fix and not tokens.
c_runbook_bullets_with_an_internal_token() { git ls-files 'infra/runbooks/*.md' | grep -vE '^infra/runbooks/(README\.md$|[^/]+/)' | xargs uv run python infra/scripts/runbook-internal-tokens.py | wc -l; }

c_canary_bypasses() { jq -c 'select(.limit=="zcrypto" and .extra_vars.canary_override!=null)' docs/reference/deploy-log.jsonl | wc -l; }

# COUNT_LIST_FEED_SNAPSHOT is the snapshot arm of the audit: set it and the count reads a recorded
# feed instead of the network, which is how a test runs this line and how a rolled feed keeps its
# coverage. Unset, the count is the live feed, as the corpus states it.
c_converges_inside_a_kraken_window() {
  local feed=()
  if [ -n "${COUNT_LIST_FEED_SNAPSHOT:-}" ]; then feed=(--from-snapshot "$COUNT_LIST_FEED_SNAPSHOT"); fi
  uv run python infra/scripts/deploy-log-audit.py maintenance "${feed[@]}" | sed -n 's/^rows inside an API-impacting window \([0-9][0-9]*\) of .*/\1/p'
}

c_drills_on_the_primary() { grep -cE '^\*host\* `zcrypto`' docs/reference/drill-log.md; }

c_un_tagged_primary_runs() { jq -c 'select(.limit=="zcrypto" and .tags=="")' docs/reference/deploy-log.jsonl | wc -l; }

c_engine_rows_outside_the_gap() { uv run python infra/scripts/deploy-log-audit.py engine-window | sed -n 's/^engine rows [0-9][0-9]* outside window \([0-9][0-9]*\) .*/\1/p'; }

c_nas_rows_without_compat() { awk -F'|' '$3 ~ /^ *nas *$/' docs/reference/fleet-pins.md | grep -vc compat; }

c_image_removals_outside_the_pruner() { git grep -nE 'docker (image (prune|rm)|rmi|system prune)' -- infra cli .claude ':!*.md' ':!infra/scripts/prune-host-images.py' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | wc -l; }

c_inspect_reads_of_dot_image() { git grep -nE '\{\{ ?(json )?\.Image ?\}\}' -- infra cli .claude ':!*.md' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | wc -l; }

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
# renders a broken image ref. `converge.sh` stores every `-e k=v` it was handed in the row, stripped.
c_deploy_rows_with_an_empty_digest_var() { jq -s '[.[] | select((.extra_vars // {}) | to_entries | any((.key | endswith("_digest")) and ((.value | tostring) | test("^[[:space:]]*$"))))] | length' docs/reference/deploy-log.jsonl; }

# The read-only healthchecks key reaching a host: today only `hc_prometheus_metrics_path` renders, and the
# `group_vars/all/` copy is read from the workstation by file path. A role naming the key is the finding.
c_hc_readonly_key_in_a_role() { git grep -nE 'healthchecks_readonly_api_key' -- infra/ansible/roles | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | wc -l; }

# A write to one of the six gate gauges from outside `_ExecGauges.update`, whose single call is what makes
# a frozen gauge set indistinguishable from a live one. The awk excises that method's body alone.
c_gate_gauge_writes_outside_the_publish_call() { [ -f cli/engine/command.py ] || return 2; { awk '/^    def update\(self, verdict/{i=1;next} i&&(/^    (def |@)/||/^[^ ]/){i=0} !i' cli/engine/command.py; git grep -h -E '\.(gate_level|armed|kill_tripped|restart_hold|venue_ok|last_evaluation)\.set\(' -- cli ':!cli/engine/command.py'; } | grep -cE '\.(gate_level|armed|kill_tripped|restart_hold|venue_ok|last_evaluation)\.set\('; }

# `--delete` anywhere in the archive pull's module: the mirror keeps every day it ever fetched, which is
# what makes a mismatch count span days and an empty tree mean the pull has never succeeded.
c_archive_pull_delete_flags() { grep -nE -- '--delete' cli/archive/command.py | grep -vE '^[0-9]+:[[:space:]]*#' | wc -l; }

# A deployed `--cache` naming a path outside `/tmp/`: wider than the bullet's "a path both hosts reach",
# which is the direction that never under-reports the siting the cross-host poisoning rule forbids.
c_gate_cache_args_outside_tmp() { git grep -nE -- '--cache[ =]["'"'"'$]?[/$~.]' -- infra cli ':!*.md' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -vE -- '--cache[ =]["'"'"']?/tmp/' | wc -l; }

# A rule whose `folderUID` is a literal rather than `${GRAFANA_ALERT_FOLDER_UID}`: it provisions into
# another folder AND escapes the push script's orphan prune, which selects by that same field.
c_alert_rules_without_the_folder_literal() { uv run python -c 'import yaml;print(sum(r.get("folderUID")!="${GRAFANA_ALERT_FOLDER_UID}" for r in yaml.safe_load(open("infra/grafana/alerts.yaml"))["rules"]))'; }

# A verified nautilus version with no adapter-verification record carrying a PASS. Both arming guards read
# that file, so a version added without its attended record is live money on an uncleared adapter.
c_verified_versions_without_a_pass_record() { jq -r '.verified_nautilus_versions[]' cli/engine/order-semantics-verified.json | while read -r v; do grep -qE '\*\*(Verdict: )?PASS\b' "docs/reference/adapter-verification/$v.md" 2>/dev/null || echo "$v"; done | wc -l; }

# A member of the inventory's `engine_host` group other than `zcrypto`: every "primary only" reading on
# the capture-daemon and hosts pages rests on that group holding one host, and the live trade key with it.
c_engine_hosts_besides_the_primary() {
  uv run python - <<'INV'
import yaml
groups = yaml.safe_load(open("infra/ansible/inventory/hosts.yml"))["all"]["children"]
members, stack = set(), [groups["engine_host"]]
while stack:  # a host reaches the group through a child group too, and it holds the trade key just the same
    node = stack.pop()
    members |= set(node.get("hosts") or {})
    stack += list((node.get("children") or {}).values())
print(len(members - {"zcrypto"}))
INV
}

# `docker inspect <container>` with no `--format`, the form that prints the whole config -- the live Kraken
# trade key with it on the engine host. Narrower than the bare command an operator types, which nothing records.
c_unscoped_docker_inspects_invoked() { git grep -nE 'docker inspect +[^`]' -- infra cli .claude ':!*.md' ':!infra/scripts/count-list.sh' | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -vE -- '--format|-f ' | wc -l; }

# The pinned leaves the edge renders, one `file /etc/caddy/pinned-leaves/<name>.pem` line per tracked PEM:
# a figure to read, not a gate. At 1 every revocation issues its replacement first; at 0 the block is empty.
c_pinned_leaves_the_edge_renders() { git ls-files ':(glob)infra/ansible/roles/access/files/pinned-leaves/*.pem' | wc -l; }

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
  emit "mutation-commits-without-a-probe" c_mutation_commits_without_a_probe
  emit "prose-only-commits-without-the-prover" c_prose_only_commits_without_the_prover
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
