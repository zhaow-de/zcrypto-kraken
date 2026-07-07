---
status: open
---

# Blockpit T1 tax check (read-only depot connection + historical labeling + T1 memo)

## Context — what

Phase 1's autonomous loop (master-plan §12) ends with a *"**Blockpit T1 check (§11):** re-verify import scope, connect read-only depot, inspect historical labeling — T1 memo."* §11 ratified **Blockpit** (2026-07-06, Phase 0) as the tax pipeline for the German §23-EStG / crypto-Wirtschaftsgut treatment; the T1 (tier-1) check is the first hands-on validation: connect the live Kraken depot **read-only**, confirm Blockpit's import scope covers spot + spot-margin, and inspect how it labels historical trades — written up as a short **T1 memo**. Not started.

## Why this matters

Tax treatment is a **net-return** input, not a nicety: §11/§3 note that a EUR-funded account trading USD/USDT pairs owes a per-fill EUR/USD cost-basis join and that the BMF treats USDT as a crypto Wirtschaftsgut (each hop a taxable lot) — one of the reasons the universe stays EUR-quoted (§3). Margin-trade P&L is likely taxed under a different regime than spot (§4). The T1 memo is where those assumptions get checked against a real import before they harden into the Phase-2 cost/after-tax model and the Phase-6 go-live bookkeeping.

## Why it's human-gated in practice

**The master plan labels T1 autonomous** — §11 calls it *"T1 — Doc & depot check (Phase 1, autonomous)"* and the Decision Register lists "Blockpit T1/T3 (§11)" among items *"converted to autonomous-with-defaults."* In practice it is **not** autonomously executable by this agent: connecting Blockpit to the Kraken depot requires an **interactive login to a third-party SaaS plus an explicit authorize step**, which a coding agent without browser / computer-use tooling cannot perform. So T1 is human-gated *in practice* — an override of the plan's ratified classification, recorded here and in `docs/research/02.phase1-data-foundation-closeout.md`. It is coupled to T0000 (the verified read-only Kraken API key is the likely connection credential) but is a distinct action (a third-party Blockpit account + an explicit authorize step). It is a tax/live-preparation task, not a research-pipeline blocker.

## Findings so far

- **Blockpit ratified** as the tax tool (§11, Phase 0, 2026-07-06). No connection attempted yet.
- **Read-only Kraken key exists** (T0000, verified 2026-07-07: Query funds + Query ledger entries + Query closed orders & trades) — the natural read-only feed for Blockpit; no trade-scoped key is or should be involved.
- Not a dependency of the Phase-2 validation harness (synthetic data) or Phases 3–4 (historical OHLCVT research); it feeds the **after-tax** view and live bookkeeping, so it is deferred without blocking research.

## Suggested next steps

- **(human)** Create/log into Blockpit; connect the Kraken depot **read-only** (via the T0000 read-only API key or Blockpit's Kraken connector); authorize import.
- **(human + autonomous write-up)** Re-verify the import scope covers **spot + spot-margin**; inspect historical-trade labeling (esp. §23 holding-period handling and margin-vs-spot classification); capture screenshots/notes.
- **(autonomous)** Draft the **T1 memo** from the human's findings — import scope, labeling correctness, any gaps to feed the Phase-2 after-tax model — as a `docs/` note.
