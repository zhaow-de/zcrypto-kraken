---
name: zcrypto-grafana-push
description: Push the committed dashboards and alert rules to Grafana Cloud — the one invocation with its credentials, the preflight over the series added or changed rules read, verification by value, the prune, and a push from a feature branch under its conditions.
---

# zcrypto-grafana-push

`infra/scripts/grafana-push.sh` is the push; this page is how it is run, so that nothing about it is rediscovered.

## Step 0 — the invocation

From the repo root, once Steps 1 and 2 pass:

```bash
GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("grafana_sa_token"))')" \
  PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
```

`GRAFANA_SLACK_WEBHOOK_URL` stays unset on a routine push: the receivers are live.

## Step 1 — the preflight over the series the rules read

For each rule the push adds or changes (`git diff <base> -- infra/grafana/alerts.yaml`), read what its expression selects on each host it targets: a Prometheus rule's selector with `uv run python infra/scripts/grafana-query.py '<selector>'`, a Loki rule's metric expression, less its `or on() vector(0)`, with `uv run python infra/scripts/grafana-query.py --loki '<logql>'`. `(no series)` where a healthy host always publishes holds the push until a converge makes it publish. `noDataState` does not decide this: it covers a query that returns nothing, while an `or on() vector(0)`, or a `count()` across hosts one of which is absent, returns a value and fires the rule.

## Step 2 — where to push from

The script pushes the working tree it runs from, whole, and its prune deletes the folder's rules that tree lacks, so a stale or dirty checkout reverts what `develop` changed since: every push starts with `git fetch origin develop && git merge-base --is-ancestor origin/develop HEAD` exiting 0 and `git status --porcelain -- infra/grafana` printing nothing, in the checkout that pushes. A push from merged `develop` is then the default: summaries and panel descriptions cite repo paths, and a push from elsewhere can ship alert text naming files `develop` does not have. A push from a feature branch is admitted under three conditions, together:

1. The branch is the one that will merge, and the push is recorded on its pull request: a `## Grafana push` section in the body naming the branch, the pushed tip and what was pushed (dashboards, rules).
2. The fix loop stays on that branch: a defect the push or its verification shows is fixed there and pushed again from there.
3. A push from `develop` follows the merge, so what is live matches the merged tree; the closeout names it.

## Step 3 — verify

- Read each new or changed rule's first sample by value with `grafana-query.py`, `--loki` for a Loki rule, and each new panel's query the same way; `(no series)` is a fail, not a zero.
- Render each new or changed dashboard as the script's header says, the narrowed-variable case included; `GRAFANA_URL` is `https://zcrypto2026.grafana.net`, the script's default, which the rendering shell does not hold.

## Step 4 — the prune

`GRAFANA_PRUNE=1` turns the script's orphan report into deletions, scoped to our folder, from a `develop` checkout that passes Step 2's freshness test; a superseded rule is pruned only in `.claude/rules/fleet-deploys.md`'s order.

## Closeout

The PR body's `## Grafana push` section (Step 2) is the record: nothing in the tree records a push, and Grafana Cloud carries no identifier to match one against.
