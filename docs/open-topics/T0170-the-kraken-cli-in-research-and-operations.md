---
status: open
ripe_when: "per sub-item — the MCP removal: NOW, gated on nothing; the reconciliation second reader: the engine is armed (`grep -c '^exec_armed = false' infra/ansible/roles/engine/templates/zcrypto.toml.j2` returns 0); the microstructure cross-checks: the next alpha search opens"
---

# The Kraken CLI in research and operations

## Context — what

Kraken ships an official CLI (`kraken-cli`, v0.4.1 measured) with a paper engine, an MCP server and read-only account and market commands. Research report 91 (`docs/research/91.kraken-cli-paper-trading-assessment.md`) answered both questions the owner put: whether its paper trading reopens Stage 6a's founding decision (it does not), and how the CLI fits R&D. The owner's rulings (2026-09-05): the CLI is **workstation-only and is never deployed into the production landscape** — not the engine node, not the capture pair, not ops; the MCP server is **dropped** and the CLI is called through Bash with `-o json`; every CLI-relevant concept change is one branch and one PR, report 91's.

## Why this matters

The CLI reaches the account through an implementation separate from the engine's Nautilus client, which makes it a second, independent producer for account facts the cost model and the reconciler depend on. The MCP registration widened every session's live surface with no capability the CLI lacks. And a boundary ruled only in a report is invisible at execution time.

## Findings so far

Report 91 is this topic's evidence and holds every measurement, citation and non-goal: what the paper engine can and cannot represent, why the MCP subtracts rather than adds, what `kraken volume` makes automatable, and where the CLI earns its place. This topic tracks only what remains to be done, so the two cannot drift.

## Suggested next steps

- **Owner's action, outside the repo.** Delete the `kraken` entry from the top-level `mcpServers` in `~/.claude.json` on every machine that runs a session; restart those sessions; confirm no `mcp__kraken__*` tool loads. Then add the read-only prefixes to the harness allowlist (`kraken ticker`, `kraken ohlc`, `kraken orderbook`, `kraken trades`, `kraken spreads`, `kraken pairs`, `kraken assets`, `kraken balance`, `kraken volume`, `kraken ledgers`, `kraken trades-history`, `kraken positions`, `kraken open-orders`), leaving `kraken order`, `kraken withdraw`, `kraken wallet-transfer` and `kraken subaccount` to the per-call prompt.
- **Ripe at go-live: the reconciliation second reader.** Design a workstation-side cross-check of the engine's account view against `kraken balance`, `kraken positions`, `kraken ledgers` and `kraken trades-history`, run from the workstation against the API and never from the engine node. Disagreement between the two producers is the finding; a single client cannot report that it is misreading itself.
- **Ripe at the next alpha search: the microstructure cross-checks.** Spot-check `docs/reference/captured-spread-calibration.md` against live `kraken orderbook-l3` (authenticated per-order book), `kraken spreads` and `kraken trades`. Cross-check only — never a capture path, which is production and excluded by the ruling.
- **Once the registration is gone**, any rule, skill or runbook naming an `mcp__kraken__*` tool renames to the Bash form. None does today.
