---
status: open
ripe_when: 'the engine is armed: `uv run python infra/scripts/grafana-query.py "zcrypto_exec_armed{host=\"zcrypto\"}"` reads 1 (`infra/runbooks/engine-procedures.md` names it as the armed-state read)'
---

# The kraken MCP server exposes the trade and funding services

## Context — what

The sessions' MCP configuration registers the Kraken CLI's server as `kraken mcp -s all` against the live `default` workspace (`~/.claude.json`, user level, outside the repo). The CLI's shipped default service set is read-only — `market,account,paper,workspace,feedback`; `-s all` additionally exposes `trade`, `funding`, `futures`, `earn`, `subaccount` and `auth`: order placement, withdrawals, transfers. Guarded mode requires `acknowledged: true` on a dangerous call, but that argument is supplied by the calling model, so the only human gate is the harness's permission prompt. `--allow-dangerous` is not set, which is correct.

## Why this matters

A research session needs only the read-only set. Once the engine is armed and the account holds real positions, every session on this account carries a live order and withdrawal surface behind one permission prompt, and a prompt is a gate a model can be talked through. The narrowing is a one-line change to the user-level configuration and costs a research session nothing.

## Findings so far

- `docs/research/91.kraken-cli-paper-trading-assessment.md` (`zcrypto-zebra`, 2026-09-05) measured the shipped v0.4.1 binary and source: the default service set, what `-s all` adds, and guarded mode's `acknowledged` argument as a model-supplied value.
- `~/.claude.json` on the ops host registers the server with `args: ['mcp', '-s', 'all']` (read 2026-09-05T15:59Z).

## Suggested next steps

- **Owner's action, outside the repo**: change the registration to the read-only default (drop `-s all`, or name the read-only set explicitly) in `~/.claude.json` on every machine that runs a session; restart the sessions; confirm with `ListAgents`' tool listing that no `kraken_order_*`, `kraken_withdraw*` or `kraken_wallet_transfer` tool is loaded.
- If a session ever needs the trade surface (a fixture mint, an attended order), register a second, named server with the narrower `-s trade` set and remove it after the step, rather than widening the default.
