# Kraken Fee Schedule — Reference (⏱ 2026-07-07)

Reference for the cost model. This supersedes the master-plan §14 fee snapshot (0.25%/0.40% base), which was the schedule live **through July 8, 2026 only**. A **new schedule takes effect July 9, 2026** and is recorded below. ⏱ — reconfirm on the logged-in **Kraken Pro → Fee tab** (authoritative; the public fee-schedule page still showed the old schedule when this was captured). Verified 2026-07-07 against Kraken's official "Cross-platform fee tier changes" article + the margin-trading page.

## Spot maker/taker — new schedule (effective 2026-07-09)

Qualification is by **30-day USD trading volume** (rolling). EUR crypto pairs (BTC/EUR, ETH/EUR, …) use this **standard** schedule and **do** build 30-day volume.

| Tier | 30-day volume | Maker | Taker |
|---|---|---|---|
| 1 | $0+ | 0.40% | 0.80% |
| 2 | $2,500+ | 0.30% | 0.60% |
| 3 | $10,000+ | 0.22% | 0.38% |
| 4 | $25,000+ | 0.20% | 0.35% |
| 5 | $50,000+ | 0.15% | 0.30% |
| 6 | $100,000+ | 0.12% | 0.25% |
| 7 | $250,000+ | 0.10% | 0.22% |
| 8 | $500,000+ | 0.08% | 0.20% |
| 9 | $1,000,000+ | 0.06% | 0.18% |
| 10 | $2,500,000+ | 0.04% | 0.15% |
| 11 | $5,000,000+ | 0.02% | 0.12% |
| 12 | $10,000,000+ | 0.00% | 0.10% |
| Pro 1 | $50,000,000+ | 0.00% | 0.09% |
| Pro 2 | $100,000,000+ | 0.00% | 0.08% |
| Pro 3 | $250,000,000+ | 0.00% | 0.07% |
| Pro 4 | $400,000,000+ | 0.00% | 0.06% |
| Pro 5 | $500,000,000+ | 0.00% | 0.05% |

## Assets-on-Platform (AoP) qualification ladder (new, 2026-07-09)

An **alternative** qualification path: the real-time USD value of eligible holdings (wallet + staked + rewards). The account gets the **most favorable of** {30-day spot volume, futures volume, AoP} — **no stacking**. Note the AoP ladder starts at Tier 3 (there is **no AoP path to Tier 1/2**).

| AoP held | Grants tier | | AoP held | Grants tier |
|---|---|---|---|---|
| $20,000 | Tier 3 | | $2,500,000 | Tier 10 |
| $50,000 | Tier 4 | | $5,000,000 | Tier 11 |
| $100,000 | Tier 5 | | $10,000,000 | Tier 12 |
| $200,000 | Tier 6 | | $20,000,000 | Pro 1 |
| $400,000 | Tier 7 | | $25,000,000 | Pro 2 |
| $600,000 | Tier 8 | | $50,000,000 | Pro 3 |
| $1,000,000 | Tier 9 | | $80,000,000 | Pro 4 |
| | | | $100,000,000 | Pro 5 |

## What this means for the ~$10k account

- **Light trading → Tier 1: 0.40% maker / 0.80% taker.** A taker round trip = **1.60%**; a maker round trip = **0.80%**.
- **≥ $10k 30-day turnover → Tier 3: 0.22% / 0.38%.** Turnover ramps quickly with any real activity across a 10–12 name book at 4h cadence.
- **$25k+ 30-day turnover → Tier 4: 0.20% / 0.35%** — reachable via volume (this is the old "$10k tier" rate; the July-9 change moved it up to $25k).
- **AoP is not a lever at our size:** the ladder starts at **$20k held**; $10k of AoP grants **no** discount. Our tier is driven by 30-day volume.
- **Stablecoin/FX pairs** (EUR/USD, USDC/USD, USDC/USDT) use a **separate, cheaper, near-symmetric** schedule (~0.20%/0.20% at base, dropping with volume) and **do not count** toward the 30-day volume. Instant-Buy / Buy-Crypto purchases also don't count.
- **Maker rebate** (to −0.02% on selected low-liquidity pairs) is **tier-gated to the top volume bands** — not a lever for us.
- **Cancelled/untouched orders are free** — resting post-only maker orders cost nothing until filled.

## Live account confirmation (2026-07-07)

- **Fee tier: Tier 1**, 30-day spot volume **$0.00** ("generate 10,001 USD more to reach the next tier"). Plan on the base tier — **0.40% maker / 0.80% taker** (new schedule). AoP is moot at our size.
- **Per-pair max leverage** (the order-form Leverage dropdown) matches the iter-002 snapshot **exactly**: the EUR majors (BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, ADA/EUR, LINK/EUR, DOGE/EUR, LTC/EUR, AVAX/EUR) 2–10×; **DOT/EUR 2–5×, ETH/BTC 2–5×, SOL/BTC 2–4×**.
- **Read-only API key** created + **verified working** (Balance / Ledgers / TradesHistory all return OK → Query funds + Query ledger entries + Query closed orders & trades granted); placed in `.env`.

## Spot-margin fees — confirmed per-base-currency (⏱ 2026-07-07; unchanged July 9)

Charged on the **extended (borrowed) currency**, at that currency's rate — a range, dynamic, **locked at order execution**, and shown on the order form as an absolute EUR amount (the % is on this fee-schedule page). Rollover is the **same rate every 4 hours** the position is open.

| Extended (base) currency | Opening fee | Rollover /4h | ≈ annualized (×6×365) |
|---|---|---|---|
| **BTC** | 0.01–0.02% | 0.01–0.02% | **~22–44%/yr** |
| ETH · SOL · XRP · ADA · LINK · DOGE · LTC · DOT · AVAX | 0.02–0.04% | 0.02–0.04% | **~44–88%/yr** |

**Which rate applies:** a **SHORT** sells the borrowed asset → the **base crypto** is extended → the table's base-currency rate (short BTC = 0.01–0.02%; short alts = 0.02–0.04%). A **LONG on margin** buys with borrowed fiat → the **quote/fiat** is extended → the fiat leg's rate (the article's worked example: ~0.025% for a USD leg).

**Confirms + quantifies master-plan §4:** shorting/hedging is cheapest via **short BTC** (0.01–0.02%/4h); **alt shorts cost ~2×** (0.02–0.04%/4h ≈ 44–88%/yr) — *higher* than the §4 snapshot's ~22–44% low-end assumption. This tightens the short-side EV: alt shorts must clear ~44–88%/yr of carry, reinforcing **short-BTC-only** + tactical (days-to-weeks) shorts.

Plus: standard spot trade fees on **both** the open and close of a margin position (none on settling **in kind**) — the maker/taker fee is paid twice on top of the open + rollover; **3% liquidation fee** at index on forced liquidation.

## Provenance & cost-model note

Sources: Kraken "Cross-platform fee tier changes (July 2026)" support article; kraken.com/features/margin-trading; kraken.com/features/fee-schedule; "How trading fees work on Kraken". **Cost-model action:** the Phase-2 explicit-cost model must adopt this July-9 schedule (base taker **0.80%**, maker **0.40%**), not the master-plan §1/§4/§14 snapshot (0.25%/0.40%). The change *reinforces* the plan's thesis — maker-first execution, no fast taker mean-reversion at our size — with worse absolute numbers. All values ⏱: reconfirm on the live Fee tab and the margin order form at Phase 0 and go-live.
