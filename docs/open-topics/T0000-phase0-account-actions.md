---
status: partial
---

# Phase 0 human account actions & live-account confirmations (D3(i))

## Context — what

The master plan's Phase 0 (§Phase 0; Decision Register **D3(i)**) requires actions on the live Kraken account that only the human can perform: a verification-tier check, spot-margin enablement, API-key creation (a **read-only** key now, with the **trade-scoped** key deferred to Phase 6), and confirming current fee-tier mechanics on the live account — including the **July-9-2026 "Assets on Platform" (AoP)** qualification rule and the observed margin opening + 4-hourly rollover bands on majors.

## Why this matters

These gate downstream work and cannot be done autonomously (they require logging into the account and, for margin/keys, irreversible account changes): the read-only key unblocks the Phase 1 Blockpit read-only depot (T1 tax check) and account-scoped data; margin enablement + the trade key are prerequisites for Phase 6 execution; and the observed fee/rollover/AoP mechanics feed the cost model's fee ladder (§7, §8) and the snapshot register.

## Findings so far

Researched and verified against official Kraken sources on 2026-07-07 (the full schedule lives in `docs/kraken-fee-schedule.md`). Two material corrections to the master-plan snapshot:

- **Spot-margin eligibility: CONFIRMED by the account holder** (2026-07-07). Margin access is gated by verification tier + margin-enabled (not by account size); EEA retail at Intermediate+ qualifies.
- **Margin "allowance" is set by Kraken's per-currency pool liquidity, NOT by verification tier** (the memo's "per-tier" framing was imprecise). Public ceilings ≈ EUR 12M / BTC 330 / ETH 4,000 / USD 40M; a $10k book at 2× borrows ≈ €9k / 0.1 BTC / 2.5 ETH → **<0.1% of any allowance**. The real leverage cap is **per-pair max leverage** (EUR majors 2–10×, DOT/EUR & ETH/BTC 2–5×, SOL/BTC 2–4×) + per-pair position-size limits, not allowance. "Far above our size" holds decisively.
- **Fees roughly double on 2026-07-09, and the "$10k AoP" premise is false.** New base = 0.40% maker / 0.80% taker (was 0.25/0.40); the old 0.20/0.35 now requires $25k of 30-day volume (Tier 4). AoP qualification starts at **$20k held** (Tier 3) — $10k of AoP grants no discount, so our tier is driven by 30-day volume. Full volume-tier + AoP ladder in `docs/kraken-fee-schedule.md`.
- **Margin open/rollover — confirmed per-base-currency** (2026-07-07, fee-schedule page): the fee is charged on the **extended (borrowed) currency** at that currency's rate, locked at execution. **BTC 0.01–0.02%** opening + same per 4h (~22–44%/yr); **ETH/SOL/XRP/ADA/LINK/DOGE/LTC/DOT/AVAX 0.02–0.04%** (~44–88%/yr). A short extends the base crypto → the table's rate; a margin long extends the fiat (~0.025% per the article's worked example). This **quantifies §4**: short BTC is ~2× cheaper than short alts — the alt-short carry is *worse* than the §4 ~22–44% assumption. Trade fees apply on open **and** close (none on settling in kind); 3% liquidation fee at index. Full table in `docs/kraken-fee-schedule.md`.
- **Live-account confirmations (2026-07-07):** fee tier **Tier 1**, 30-day spot volume **$0.00**; the order-form **Leverage dropdown matches the iter-002 snapshot exactly** (EUR majors 2–10×, DOT/EUR & ETH/BTC 2–5×, SOL/BTC 2–4×); the **read-only API key is created, in `.env`, and verified working** (Balance / Ledgers / TradesHistory all OK).

## Done so far

All Phase-0 human account actions and live confirmations are **complete** (2026-07-07; commits `5123e6b`, `71af90d`, `5ee4cac` on this branch, plus the `.env` loader in `eabf7ed` / `ed4b3e4`):

- **Spot-margin eligibility** — confirmed by the account holder.
- **Read-only API key** — created (Settings → API; scopes enabled: Query funds + Query ledger entries + Query closed orders & trades; open-orders / WebSocket / all order + deposit + withdraw perms left off), placed in `.env`, and **verified working** (Balance / Ledgers / TradesHistory all return OK). A **trade-scoped** key is deferred to Phase 6.
- **Fee tier** — Kraken Pro → Fee tab: **Tier 1**, 30-day spot volume **$0.00**; AoP moot at our size; plan on base 0.40 / 0.80 (new schedule).
- **Per-major leverage** — the order-form Leverage dropdown matches the iter-002 snapshot exactly (EUR majors 2–10×, DOT/EUR & ETH/BTC 2–5×, SOL/BTC 2–4×). (Watch the live margin level once a real position exists: call ~80%, liquidation ~40%.)
- **Margin open + rollover** — per-base-currency, recorded: **BTC 0.01–0.02%/4h; alts 0.02–0.04%/4h** (locked at execution). Full table + annualization in `docs/kraken-fee-schedule.md`.

## Suggested next steps

- **(→ deferred to Phase 2)** Fold the July-9 schedule (`docs/kraken-fee-schedule.md`) into the Phase-2 cost model; the master-plan §1/§4/§14 fee numbers (0.25 / 0.40 base) are superseded. Autonomously doable, but **deliberately deferred to Phase 2** (the cost-model code does not exist yet) — the inputs are fully recorded, so it is not a login-gated blocker.
