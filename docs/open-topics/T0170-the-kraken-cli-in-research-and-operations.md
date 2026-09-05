---
status: open
---

# The Kraken CLI in research and operations

## Context — what

Kraken ships an official CLI (`kraken-cli`, v0.4.1 measured) with a paper engine, an MCP server and read-only account and market commands. Research report 91 (`docs/research/91.kraken-cli-paper-trading-assessment.md`) answered whether its paper trading reopens Stage 6a's founding decision (it does not) and how the CLI fits R&D. The owner's rulings (2026-09-05): the CLI is **workstation-only and is never deployed into the production landscape** — not the engine node, not the capture pair, not ops; the MCP server is **dropped** and the CLI is called through Bash with `-o json`; every CLI-relevant concept change is one branch and one PR, report 91's.

## Why this matters

The CLI reaches the account through an implementation separate from the engine's Nautilus client, which makes it a second, independent producer for account facts the cost model and the reconciler depend on. The MCP registration widened every session's live surface with no capability the CLI lacks. And a boundary ruled only in a report is invisible at execution time.

## Findings so far

- **The MCP server adds nothing and subtracts**: every tool is an argv rewrite into the CLI's own parse and dispatch (`src/mcp/server.rs`, the vendor's header comment); `src/mcp/registry.rs`'s `CLAP_ONLY` names the commands absent from the 174-tool catalog (`record`, `replay`, `session start`, `streamd start`, `playground`, `ws ping`); guarded mode's `acknowledged: true` is an argument the calling model supplies, so a Bash call under the harness's allowlist is the human gate the MCP flag was not. Dropping it gives up the mode-tagged MCP audit stream and the server's single-writer lock over paper and session writes the sessions do not perform. The registration is global: `~/.claude.json`'s top-level `mcpServers.kraken`, `args: ['mcp', '-s', 'all']`.
- **The fee tier is readable**: `kraken volume --pair <PAIR> -o json` returns the account's live taker and maker fee, 30-day volume and the next tier's threshold — read-only, matching `docs/reference/kraken-fee-schedule.md`'s account-confirmed tier 1 (measured 2026-09-05 by `zcrypto-zebra` and reproduced by `zcrypto-main`). The fee doc's header says nothing automated can refresh its numbers; that is now false for the half the attended `zcrypto-refdata-sweep` re-reads (the tier and the 30-day volume), and still true for the full 17-tier ladder.
- **What the credential proves**: the volume call shows account-read grants and says nothing about trade grants; report 91 states the `-s all` exposure as surface, not proven reach.
- **Where the CLI earns its place**, all workstation-side and read-only: the fee-tier read as the sweep's automated half and the second producer `agent-ops.md` asks for; a post-go-live reconciliation second reader over balances, positions and ledgers, from the workstation against the API (report 91 §8.2); ad-hoc microstructure cross-checks with `orderbook-l3`, `spreads` and `trades` against `docs/reference/captured-spread-calibration.md`.
- **Non-goals, so a later session does not rediscover them as ideas**: never a data source of record (canonical datasets carry hash-pinned provenance the CLI bypasses); never on the capture path, the engine node or the live trade path; never paper trading as evidence in any rung or gate (Kraken's own promote gate agrees); never a registry substitute; never an unattended path that can place an order.

## Suggested next steps

- **Owner's action, outside the repo**: delete the `kraken` entry from the top-level `mcpServers` in `~/.claude.json` on every machine that runs a session; restart the sessions; confirm no `mcp__kraken__*` tool loads. Then the harness allowlist carries the read-only prefixes (`kraken market`, `kraken account`, `kraken volume`, `kraken paper`, `kraken workspace`); `kraken trade` runs under the prompt, per call, attended.
- **The boundary lands on its operating surface in report 91's PR**: one bullet in `.claude/rules/fleet-deploys.md`'s invariants — the CLI is workstation-only; no role, compose file or host installs it — since that file is where every deploy invariant is read before a converge (the owner's per-edit sign-off applies, the file being protected).
- **The sweep gains the fee-tier read** (`zcrypto-refdata-sweep`, the same PR or the next sweep): `kraken volume` becomes the automated half of step 7, the attended half narrows to what the API cannot say, and the fee doc's "nothing automated can refresh them" sentence is corrected in the same change — owner's word, both being live surfaces.
- **Ripe later**: the reconciliation second reader when the live book exists (T0018's rungs); the microstructure cross-checks when the next alpha search opens.
- Any rule, skill or runbook naming an `mcp__kraken__*` tool renames to the Bash form once the registration is gone.
