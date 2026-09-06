---
status: resolved
---

# The Kraken CLI in research and operations

## Context — what

Kraken ships an official CLI (`kraken-cli`, v0.4.1 measured) with a paper engine, an MCP server and read-only account and market commands. Research report 91 (`docs/research/91.kraken-cli-paper-trading-assessment.md`) answered both questions the owner put: whether its paper trading reopens Stage 6a's founding decision (it does not), and how the CLI fits R&D. The owner's rulings (2026-09-05): the CLI is **workstation-only and is never deployed into the production landscape** — not the engine node, not the capture pair, not ops; the MCP server is **dropped** and the CLI is called through Bash with `-o json`; every CLI-relevant concept change is one branch and one PR, report 91's.

## Why this matters

The CLI reaches the account through an implementation separate from the engine's Nautilus client, which makes it a second, independent producer for account facts the cost model and the reconciler depend on. The MCP registration widened every session's live surface with no capability the CLI lacks. And a boundary ruled only in a report is invisible at execution time.

## Findings so far

Report 91 is this topic's evidence and holds every measurement, citation and non-goal: what the paper engine can and cannot represent, why the MCP subtracts rather than adds, what `kraken volume` makes automatable, and where the CLI earns its place. This topic tracks only what remains to be done, so the two cannot drift.

## Resolution (2026-09-06)

- **The MCP registration is gone** — the owner removed the `kraken` entry from `~/.claude.json`'s `mcpServers`; no rule, skill or runbook ever named an `mcp__kraken__*` tool.
- **The read-only prefixes are allowlisted** — sixteen `Bash(kraken <cmd>:*)` entries in `.claude/settings.json`; `order`, `withdraw`, `wallet-transfer` and `subaccount` stay behind the per-call prompt.
- **The reconciliation second reader is a procedure** — `infra/runbooks/engine-procedures.md`'s pre-probe step 8: the boot's `Reconciliation complete` line against `kraken open-orders`, `extended-balance`, `positions` and `trades-history` from the workstation, disagreement the finding. Its first run, against the disarmed engine's 2026-09-04 boot, agreed on fills and positions, listed one order placed after the boot, which the boot line could not have counted (the log lookup step 8 names was not part of this run), and read the EUR the venue holds against it (`hold_trade`); the comparison is one screen by eye, so no script is owed (the run is in the resolving commit's message).
- **The spread calibration is spot-checked** — `docs/reference/captured-spread-calibration.md`'s Recalibrating section names the live spot-check; the 2026-09-06 run over the twelve basket pairs read BTC/EUR and ETH/EUR at 0.01×–0.11× of the table at every rung while `kraken spreads`' 250-sample half-spread mean for BTC/EUR sits within 0.002 bps of the table's @€100, and the ten other pairs between 0.12× and 1.49× of the table in both directions; a Sunday-morning snapshot is one sample of a fifteen-day mean, so no recalibration (the per-pair figures are in the resolving commit's message).
- The account cross-check recurs at every arming window (step 8) and the calibration spot-check before every recalibration. The `orderbook-l3` queue-realism read report 91 paired with them is dropped: nothing in the tree consumes queue position, and a check with no consumer is not owed.

## Suggested next steps

_(none — every item above is done or has its recurring home)_
