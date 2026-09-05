---
status: open
---

# Drop the kraken MCP server and call the CLI through Bash

## Context — what

The sessions register the Kraken CLI's MCP server at the top level of `~/.claude.json` (global across every project on the account) as `kraken mcp -s all` against the live `default` workspace. The owner's decision (2026-09-05): remove the registration rather than narrow it, and call the CLI through Bash with `-o json`. The pending action is the owner's edit of that user-level file; nothing in the repo changes it, and a session proposes the exact edit rather than making it (`prose.md`: a permission grant proven too wide is proposed, never narrowed unilaterally).

## Why this matters

The MCP adds no capability and subtracts some, while widening the live surface every session carries. Once the engine is armed, order placement and withdrawals sit behind one permission prompt, and the prompt's gate is an argument the calling model supplies.

## Findings so far

Read from the shipped v0.4.1 source by `zcrypto-zebra` (`docs/research/91.kraken-cli-paper-trading-assessment.md`):

- Every MCP tool is an argv rewrite into the CLI's own parse and dispatch path (`src/mcp/server.rs`, the vendor's own header comment: tool and CLI behaviour cannot drift). There is no second implementation.
- The MCP surface strictly subtracts: `src/mcp/registry.rs`'s `CLAP_ONLY` names the commands absent from the tool catalog (`mcp`, `record`, `replay`, `streamd start`, `session start`, `playground`, `ws ping`), the record/replay/session primitives and the streaming daemon among them. The catalog is 174 commands, 41 flagged dangerous.
- The danger gate is self-attested: guarded mode requires `acknowledged: true`, an argument the model supplies. A Bash invocation goes through the harness's permission system, which the owner controls and can allowlist per command prefix.
- Every exposed tool's name sits in every session's context; a Bash call costs nothing until made.
- What dropping it gives up: the mode-tagged MCP audit stream (the harness logs Bash invocations already) and the server's single-writer lock across concurrent tool calls, which guards the account journal and matters only for paper or session writes the sessions do not perform.
- The registration verified on the ops host: `~/.claude.json`, top-level `mcpServers.kraken`, `args: ['mcp', '-s', 'all']` (read 2026-09-05T15:59Z).

## Suggested next steps

- **Owner's action, outside the repo**: delete the `kraken` entry from the top-level `mcpServers` in `~/.claude.json` on every machine that runs a session; restart the sessions; confirm with `ListAgents` and the tool listing that no `mcp__kraken__*` tool is loaded.
- In the repo, once done: any rule, skill or runbook that names an `mcp__kraken__*` tool or the `kraken mcp` server names the Bash form instead (`kraken <cmd> -o json`), and the harness allowlist carries the read-only prefixes a research session needs (`kraken market`, `kraken account`, `kraken paper`, `kraken workspace`); an attended order or a fixture mint runs its `kraken trade` line under the prompt, per call.
- Report 91's §7 and §8 recommendation 1 say the narrowing; `zcrypto-zebra` revises them to the removal in its own PR.
