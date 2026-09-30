---
name: zcrypto-grafana-push
description: Push the committed dashboards and alert rules to Grafana Cloud — the one invocation with its credentials, the preflight over the series new rules read, verification by value, the prune, and a push from a feature branch under its conditions.
---

# zcrypto-grafana-push

`infra/scripts/grafana-push.sh` is the push; this page is how it is run, so that nothing about it is rediscovered.

## Step 0 — the invocation

From the repo root of the checkout to push from:

```bash
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"   # a shell under agentboard's tmux lacks it, and sops then finds no gpg agent
GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("grafana_sa_token"))')" \
  PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
```

`GRAFANA_SLACK_WEBHOOK_URL` stays unset on a routine push: the receivers are live.

## Step 1 — the preflight over the series the rules read

For each rule the push adds or changes whose `noDataState` is `Alerting` (`git diff <base> -- infra/grafana/alerts.yaml`), read the series its expression selects, on the hosts it targets, with `uv run python infra/scripts/grafana-query.py '<selector>'` under the same `XDG_RUNTIME_DIR`: such a rule over an absent series pages from its first evaluation, so `(no series)` holds the push until a converge makes the host publish it.

## Step 2 — where to push from

A push from merged `develop` is the default: summaries and panel descriptions cite repo paths, and a push from elsewhere can ship alert text naming files `develop` does not have. A push from a feature branch is admitted under three conditions, together:

1. The branch is the one that will merge, and the push is recorded on its pull request: a `## Grafana push` section in the body naming the branch, the pushed tip and what was pushed (dashboards, rules, a prune).
2. The fix loop stays on that branch: a defect the push or its verification shows is fixed there and pushed again from there.
3. A push from `develop` follows the merge, so what is live matches the merged tree; the closeout names it.

## Step 3 — verify

- Read each new or changed rule's first sample by value with `grafana-query.py`, and each new panel's query the same way; `(no series)` is a fail, not a zero.
- Render each new or changed dashboard as the script's header says, the narrowed-variable case included.

## Step 4 — the prune

`GRAFANA_PRUNE=1` turns the script's orphan report into deletions, scoped to our folder; a superseded rule is pruned only in `.claude/rules/fleet-deploys.md`'s order.

## Closeout

The PR body's `## Grafana push` section (Step 2) is the record: nothing in the tree records a push, and Grafana Cloud carries no identifier to match one against.
