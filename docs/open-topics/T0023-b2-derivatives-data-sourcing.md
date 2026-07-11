---
status: open
ripe_when: the B2 (derivatives-positioning) family is picked for an iteration — at which point the liquidations-history decision below must be made before the harness spec is written
---

# B2 derivatives-positioning data sourcing (funding / OI / liquidations)

## Context — what

Pre-work for opening the §5 **B2** family — "derivatives-positioning features at intraday horizons (funding, OI, liquidations) as short-horizon de-risking / re-entry triggers for the spot book" (master plan §5). The tradeable book is Kraken EUR spot; the derivatives signals come from USDT-M perp markets elsewhere. The free-data landscape was mapped autonomously (iter-088/089 research, six sources) so the family can open without a blocking data-discovery round — leaving exactly one genuine decision for the human. B2 does **not** open here (no trial, no budget spend); this topic parks the decision the harness spec depends on.

## Why this matters

B2 is the §5 ranked-queue head after B1's kill (T0022) and the A-family close. Its economics were pre-flagged as living on maker-fill realism + turnover control; before any of that, the family needs a data substrate, and the substrate has a hard asymmetry (below) that the master plan's one-line "free external data (Coinalyze/Binance)" note glossed over. Deciding it wrong — e.g. designing a liquidations factor with no free history to backtest it — would waste a trial.

## Findings so far

The full source map (access model, history depth, granularity, exact endpoints/paths, rate limits per source) was captured in the iter-089 research workflow. The decision-relevant conclusions:

- **Funding — solved, keyless, deep.** Primary backfill = **Binance Vision monthly `fundingRate` dumps** (`data.binance.vision/data/futures/um/monthly/fundingRate/<SYM>/…-YYYY-MM.zip`, `.CHECKSUM`-verifiable, 8h cadence, back to each perp's listing). Top up the current month with keyless REST `/fapi/v1/fundingRate`. Bybit v5 `/v5/market/funding/history` (keyless, paginates to listing) is a clean cross-check/backup.
- **Open interest — solved but shallower & uneven.** Only free history source = **Binance Vision daily `metrics` dumps** (`…/daily/metrics/<SYM>/…`, 5-minute `sum_open_interest` + `sum_open_interest_value`, resample to 1h/4h/8h; also ships free long/short + taker ratios). The REST `/futures/data/openInterestHist` is hard-capped at ~30 days → **useless for history, live/top-up only**. Per-symbol OI start dates are later and uneven vs funding (BTC OI 2020-09, but e.g. AVAX OI only ~2021-12).
- **Liquidations — NOT free-backfillable (the binding constraint).** Binance removed the public `allForceOrders` REST feed in 2021, there is **no Vision liquidation dump**, and the live WS `!forceOrder@arr` stream is **keyless but lossy** — since 2021 it emits ≤1 order/sec/symbol and (2026 doc change) only the *largest* liquidation per 1000 ms window, so any liquidation-volume feature from it is a lower-bound proxy, not the true tape.
- **Coverage / panel.** All 10 names have 5.8+ yr of perp history; a **balanced 10-name panel** is bounded by the last listing (~AVAX 2020-09), forfeiting the 2019-09→2020-09 window BTC/ETH alone would give. SOL & AVAX are the thinnest legs. Kraken EUR spot is far longer for the pre-2020 tokens (DOGE/LTC/XRP/LINK/ADA) — the derivatives layer is the short leg, so B2 features start years after the spot book does.
- **Aggregators.** **Coinalyze** — free, all 10 names, dedicated funding/OI/**liquidation** history endpoints, 40 calls/min — but intraday history is a purged rolling window (1h ≈ 2–3 months, deleted daily) → **live-only, no multi-year backfill**; needs a free account + API key. **Coinglass v4** — deepest single-vendor backfill (native 8h, ~1 yr hourly, daily all-time) and the natural place to *buy* liquidation history, but **no free API tier** and commercial use licensed only from **$299/mo Standard**. **Laevitas** — Enterprise-gated (~$500/mo) or x402 pay-per-call; funding is an OI-weighted aggregate (won't map 1:1 to single-venue raw funding).

## Suggested next steps

- **(human decision — the one gate, make it when B2 is picked): the liquidations approach.** Choose one, since it sets the family's scope and cannot be deferred past the harness spec:
  1. **Free, live-only liquidations** — accept liquidations as a self-collected, lossy (largest-only) live signal; **start recording the Binance WS `!forceOrder@arr` stream now** so a forward backtest window accrues; the initial B2 trials use only funding + OI (both free-backfillable) and add liquidations later once enough live tape exists. *(Zero cost, zero account — the recommended default; it lets B2 open immediately on funding+OI.)*
  2. **Free Coinalyze key for live liquidations** — a human signs up at **coinalyze.net**, generates a free API key (no payment/card), which is then vaulted; gives a cleaner aggregated live liquidation feed than the raw WS, still no historical backfill. *(Optional upgrade to option 1's live path.)*
  3. **Buy liquidation history** — budget **Coinglass Standard $299/mo** (commercial-use licensed) for a same-day multi-year liquidations backtest. *(A money decision — park under the standing "no spend without human sign-off" rule; only if a liquidations factor proves worth it on the free funding+OI base.)*
- **(autonomous, when B2 opens) build the funding + OI backfill** from Binance Vision dumps into a new derived dataset (mirroring `data/ohlc-15m`'s hash-versioned pattern; new path, never touching canonical), QA'd (per-name start dates, the balanced-panel ~2020-09 start, checksum verification), with Bybit as the funding cross-check — this **feeds** the decision (it de-risks funding/OI regardless of the liquidations choice) and is **independent** of it, so it runs first in the B2 opening iteration.
- **(autonomous) the B2 harness** consumes: funding (8h prints → cumulative/accrued carry, sign persistence for the 1h/4h horizon — derived, no finer native data), OI (5m → level, delta, momentum, z-score; + the free long/short ratios), and — per the chosen option — liquidations (per-bucket notional, long/short imbalance, spike flags, provenance-tagged as lower-bound if from the WS). All USDT-M perp features aligned to the Kraken spot decision grid with the venue gap carried explicitly.
