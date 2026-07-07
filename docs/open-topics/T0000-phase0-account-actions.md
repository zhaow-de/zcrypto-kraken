---
status: open
---

# Phase 0 human account actions & live-account confirmations (D3(i))

## Context — what

The master plan's Phase 0 (§Phase 0; Decision Register **D3(i)**) requires actions on the live Kraken account that only the human can perform: a verification-tier check, spot-margin enablement, API-key creation (a **read-only** key now; a **trade-scoped** key created but stored unused), and confirming current fee-tier mechanics on the live account — including the **July-9-2026 "Assets on Platform" (AoP)** qualification rule and the observed margin opening + 4-hourly rollover bands on majors.

## Why this matters

These gate downstream work and cannot be done autonomously (they require logging into the account and, for margin/keys, irreversible account changes): the read-only key unblocks the Phase 1 Blockpit read-only depot (T1 tax check) and account-scoped data; margin enablement + the trade key are prerequisites for Phase 6 execution; and the observed fee/rollover/AoP mechanics feed the cost model's fee ladder (§7, §8) and the snapshot register.

## Findings so far

_(none — parked at Phase 0 kickoff by the autonomous research loop, iter-001.)_

## Suggested next steps

- Verification-tier check; confirm margin-allowance limits vs our ~$10k size.
- Enable spot-margin for the EEA account (confirm eligibility).
- Create a **read-only** API key now (public + account data / Blockpit depot); create a **trade-scoped** key but store it unused until Phase 6.
- On the live account / order form, confirm: maker/taker tier at our volume, the July-9-2026 AoP qualification, and observed margin opening + 4-hourly rollover bands on majors.
- Record all confirmed ⏱ values into the snapshot register (feeds the cost model).
