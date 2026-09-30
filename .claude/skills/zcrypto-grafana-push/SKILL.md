---
name: zcrypto-grafana-push
description: Push the committed dashboards and alert rules to Grafana Cloud — the one invocation with its credentials, the preflight over the series new rules read, verification by value, the prune, and a push from a feature branch under its conditions.
---

# zcrypto-grafana-push

`infra/scripts/grafana-push.sh` is the push; this page is how it is run so that nothing about it is rediscovered. The rules it enforces are `.claude/rules/fleet-deploys.md`'s (the prune order) and the script's own header (the datasource read-back, the render check); this page points at them.

## Step 0 — the invocation

From the repo root of the checkout to push from, one command, the token assigned by command substitution and nothing else, so its value reaches no file, log or argv:

```bash
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"   # a shell under agentboard's tmux lacks it, and sops then finds no gpg agent
GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("grafana_sa_token"))')" \
  PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
```

`PATH` puts the project venv first because the script calls bare `python3` and needs its PyYAML. The stack, the two datasource uids and the alert folder uid have defaults inside the script; `GRAFANA_PRUNE=1` turns the orphan report into deletions (Step 4); `GRAFANA_SLACK_WEBHOOK_URL` is unset on a routine push, the receivers being live. A push is idempotent: each dashboard overwrites by its uid, each rule upserts by its uid, the notification template is verified byte-identical.

## Step 1 — the preflight over the series the rules read

For each rule the push adds or changes (`git diff <base> -- infra/grafana/alerts.yaml`, the `expr:` lines), read the series its expression selects, on the hosts it targets, with `uv run python infra/scripts/grafana-query.py '<selector>'` under the same `XDG_RUNTIME_DIR`. A present series at its expected value admits the rule; `(no series)` holds the push, since a rule over an absent series pages on its no-data state from its first evaluation. The hold ends when the host publishes the series, which is a converge's outcome (the rollout of 2026-09-30 held its push until ops published `node_reboot_required`).

## Step 2 — where to push from

A push from merged `develop` is the default: summaries and panel descriptions cite repo paths, and a push from elsewhere can ship alert text naming files `develop` does not have. A push from a feature branch is admitted under three conditions, together:

1. The branch is the one that will merge, and the push is recorded on its pull request: a `## Grafana push` section in the body naming the branch, the pushed tip and what was pushed (dashboards, rules, a prune).
2. The fix loop stays on that branch: a defect the push or its verification shows is fixed there and pushed again from there.
3. A push from `develop` follows the merge, so what is live matches the merged tree; the closeout names it.

An abandoned branch is the case the default guards against; with condition 1, the next `develop` push overwrites what it left.

## Step 3 — verify

- The script reads back each rule's `datasourceUid` after the push (its header's T0034 note) and stops on a foreign one.
- Read each new or changed rule's first sample by value with `grafana-query.py`, and each new panel's query the same way; `(no series)` is a fail, not a zero.
- Verify a dashboard by rendering it rather than by reading its JSON back: the script's header carries the `render/d-solo` form and the narrowed-variable case that renames the value field.

## Step 4 — the prune

The push upserts and deletes nothing, so a rule removed from `infra/grafana/alerts.yaml`, or one whose uid changed, keeps evaluating beside its replacement. The script reports such orphans on each run; `GRAFANA_PRUNE=1` deletes them, scoped to our folder. The order is `fleet-deploys.md`'s: converge, push, verify the replacement's first sample by value, prune, confirm the old uid answers 404, since `delta()` and `increase()` are blind to a condition already present in a series' first sample.

## Closeout

The PR body's `## Grafana push` section (Step 2) is the record; nothing in the tree records a push, and Grafana Cloud carries no identifier to match one against. A branch push owes the `develop` push after the merge, named in the same section as done.
