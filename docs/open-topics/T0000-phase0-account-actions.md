---
status: open
---

# Phase 0 human account actions & live-account confirmations (D3(i))

## Context — what

The master plan's Phase 0 (§Phase 0; Decision Register **D3(i)**) requires actions on the live Kraken account that only the human can perform: a verification-tier check, spot-margin enablement, API-key creation (a **read-only** key now; a **trade-scoped** key created but stored unused), and confirming current fee-tier mechanics on the live account — including the **July-9-2026 "Assets on Platform" (AoP)** qualification rule and the observed margin opening + 4-hourly rollover bands on majors.

## Why this matters

These gate downstream work and cannot be done autonomously (they require logging into the account and, for margin/keys, irreversible account changes): the read-only key unblocks the Phase 1 Blockpit read-only depot (T1 tax check) and account-scoped data; margin enablement + the trade key are prerequisites for Phase 6 execution; and the observed fee/rollover/AoP mechanics feed the cost model's fee ladder (§7, §8) and the snapshot register.

## Findings so far

Researched and verified against official Kraken sources on 2026-07-07 (the full schedule lives in `docs/kraken-fee-schedule.md`). Two material corrections to the master-plan snapshot:

- **Spot-margin eligibility: CONFIRMED by the account holder** (2026-07-07). Margin access is gated by verification tier + margin-enabled (not by account size); EEA retail at Intermediate+ qualifies.
- **Margin "allowance" is set by Kraken's per-currency pool liquidity, NOT by verification tier** (the memo's "per-tier" framing was imprecise). Public ceilings ≈ EUR 12M / BTC 330 / ETH 4,000 / USD 40M; a $10k book at 2× borrows ≈ €9k / 0.1 BTC / 2.5 ETH → **<0.1% of any allowance**. The real leverage cap is **per-pair max leverage** (BTC/ETH 2–10×, majors 2–5×) + per-pair position-size limits, not allowance. "Far above our size" holds decisively.
- **Fees roughly double on 2026-07-09, and the "$10k AoP" premise is false.** New base = 0.40% maker / 0.80% taker (was 0.25/0.40); the old 0.20/0.35 now requires $25k of 30-day volume (Tier 4). AoP qualification starts at **$20k held** (Tier 3) — $10k of AoP grants no discount, so our tier is driven by 30-day volume. Full volume-tier + AoP ladder in `docs/kraken-fee-schedule.md`.
- **Margin open/rollover: unchanged** — 0.01–0.05% opening + same rate per 4h, locked at execution and shown on the order form; the actual per-major rate is login-gated. Trade fees apply on open **and** close (none on settling in kind); 3% liquidation fee at index.

## Suggested next steps (account checklist — this topic stays open until all are done)

**Margin allowance vs ~$10k size** — resolved by the research above:

- [x] Confirm spot-margin eligibility — **DONE** (account holder confirmed 2026-07-07).
- [ ] (optional) On the order form note the Leverage-dropdown max per major (BTC/ETH up to 10×, majors 2–5×; we use 2×); watch the live margin level once a position exists (call ~80%, liquidation ~40%).

**Fee tier + AoP** (login-gated):

- [ ] On **Kraken Pro → Fee tab**, read the live maker/taker tier + rolling 30-day volume + AoP value (authoritative; overrides the public table, which still showed the old schedule pre-July-9). Expect Tier 1 (0.40/0.80) when light, Tier 3 (0.22/0.38) at ≥$10k/30d, Tier 4 (0.20/0.35) at $25k+/30d. Record the confirmed tier.

**Margin open + rollover on majors** (login-gated):

- [ ] On the **BTC/EUR** and **ETH/EUR** margin order forms, select 2× leverage and read the displayed **opening fee %** and **rollover %/4h** *before* submitting (the rate locks at execution). Record both per major; annualize (0.01%/4h ≈ 22%/yr, 0.02%/4h ≈ 44%/yr).

**API key** (you create it; the config lands in this branch):

- [ ] Create a **read-only** Kraken API key now (Settings → API; **Query** permissions only — NO trade, NO withdraw). Copy `.env.sample` → `.env` (gitignored) and set `KRAKEN_API_KEY` / `KRAKEN_API_SECRET`. A **trade-scoped** key comes later at Phase 6 — keep it out of `.env` until then.

**Cost-model follow-up:**

- [ ] Fold the July-9 schedule (`docs/kraken-fee-schedule.md`) into the Phase-2 cost model; the master-plan §1/§4/§14 fee numbers (0.25/0.40 base) are superseded.
