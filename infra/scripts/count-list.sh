#!/usr/bin/env bash
# The instrument that replaced the refine-rules staleness sweep: one line per count command the corpus names, and a universal with no command beside it is the finding.
# Three entries the corpus does not name close the list: topic-only merges, the claude-kind commits since the last refine round closed, and the processes with a cwd inside a worktree.
set -uo pipefail

errors=()

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

c_merged_prs_without_a_read() { timeout 60 gh pr list --state merged --base develop --limit 200 --json body,mergedAt | jq '[.[] | select(.mergedAt >= (now - 2592000 | todate)) | select((.body // "") | test("^Read before push by: .+ at [0-9a-f]{7,}"; "m") | not)] | length'; }

c_kraken_cli_on_infra() { git grep -c kraken-cli -- infra ':!*.md' ':!infra/scripts/count-list.sh' | wc -l; }

c_mutation_commits_without_a_probe() { comm -23 <(git log develop --since=2026-08-03 -i --grep=mutation --format=%h | sort) <(git log develop --since=2026-08-03 -i --grep=mutate-probe --format=%h | sort) | wc -l; }

c_prose_only_commits_without_the_prover() { comm -23 <(git log develop --since=2026-09-09 -i --grep=prose-only --format=%h | sort) <(git log develop --since=2026-09-09 -i --grep=prove-inert --format=%h | sort) | wc -l; }

# A failing suite is an error, never a zero count: its output still carries a "N passed" summary.
c_spec_hash_provenance() { uv run pytest tests/test_trial_registry_provenance.py -q || return 2; }

c_operator_term_surfaces() { uv run pytest tests/test_internal_terms_not_operator_visible.py -q || return 2; }

c_operator_term_allowlist_edits() { git log --oneline -G_WP_CARRIERS -- tests/test_internal_terms_not_operator_visible.py | wc -l; }

c_topics_without_a_trigger() { grep -L '^ripe_when:' docs/open-topics/T*.md | wc -l; }

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

main() {
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
  emit "live-topics-without-a-trigger" c_topics_without_a_trigger
  emit "canary-bypasses-on-the-primary" c_canary_bypasses
  emit "converges-inside-a-kraken-window" c_converges_inside_a_kraken_window
  emit "drills-on-the-primary" c_drills_on_the_primary
  emit "un-tagged-primary-runs" c_un_tagged_primary_runs
  emit "engine-rows-outside-the-gap" c_engine_rows_outside_the_gap
  emit "nas-rows-without-compat" c_nas_rows_without_compat
  emit "converge-sh-wrapped-in-timeout" c_converge_sh_wrapped_in_timeout
  emit "topic-only-merges" c_micro_prs
  emit "claude-commits-since-the-round-closed" c_claude_commits_since_the_round_closed
  emit "worktrees" c_worktree_processes
  emit "merged-prs-without-a-read-line-30d" c_merged_prs_without_a_read

  if [ "${#errors[@]}" -gt 0 ]; then
    printf 'count-list: %s command(s) errored: %s\n' "${#errors[@]}" "${errors[*]}" >&2
    exit 2
  fi
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then main "$@"; fi
