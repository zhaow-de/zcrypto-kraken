# Benchmark B2: Inverse-Vol Majors-Basket Bar-to-Beat on Real Data

This report records the **B2 benchmark** — a naive inverse-vol-weighted basket of the 10 EUR
majors (ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP) — run through the full stack
(dataset → returns → `inverse_vol_basket` → backtester → metrics) on real daily OHLC data, and
compared to the single-asset BTC B0/B1 benchmarks from `docs/benchmark-b0-b1-report.md` over the
*same* window.

The 10 majors are aligned by intersecting their `ts` calendars: the common window is
**2021-12-21 → 2026-03-31** (1562 daily closes → 1561 returns), driven by AVAX being the newest
listing among the 10. All four strategies below are computed over this identical span so the
comparison to BTC is apples-to-apples (BTC's own B0/B1 in the prior report span its full
2013–2026 history; the numbers here are BTC re-run over the shorter common window). Zero trading
fees throughout — a benchmark idealization, not a live-trading estimate. B2's weighting uses a
30-day lookback (`inverse_vol_basket(prices_by_asset, lookback=30)`); B1 and the vol-targeted
basket use the same 30-day lookback and a 10%/yr target vol (`vol_target(..., target_vol=0.10 /
365**0.5, lookback=30, max_leverage=1.0)`), consistent with the rest of the family.

## Results

| Strategy                              | Total return | Annualized | Sharpe | Max DD |
| -------------------------------------- | ------------: | ----------: | ------: | ------: |
| B0 — BTC buy-and-hold                  |         1.36× |       7.49% |   0.397 |   65.8% |
| B1 — BTC vol-target (10%/yr)           |         1.21× |       4.61% |   0.456 |   17.5% |
| **B2 — inverse-vol basket (10 majors)** |     **0.68×** |  **−8.57%** | **0.194** | **69.4%** |
| B2 + vol-target (10%/yr)               |         1.21× |       4.49% |   0.453 |   14.6% |

## Per-asset context

Buy-hold multiple over the same common window (`prices[-1] / prices[0]`):

| Asset | Multiple | Asset | Multiple |
| ----- | -------: | ----- | -------: |
| BTC   |    1.36× | LINK  |    0.44× |
| XRP   |    1.38× | LTC   |    0.34× |
| DOGE  |    0.53× | ADA   |    0.18× |
| ETH   |    0.51× | AVAX  |    0.07× |
| SOL   |    0.45× | DOT   |    0.05× |

Only **BTC and XRP gained** over this window; the other 8 majors lost **47–95%** of their
window-start value (DOGE −47%, ETH −49%, SOL −55%, LINK −56%, LTC −66%, ADA −82%, AVAX −93%,
DOT −95%).

## Interpretation (honest)

**The raw inverse-vol basket underperformed single-asset BTC.** B2 *lost* money over the window
(0.68×, −8.6%/yr) with a *deeper* max drawdown (69.4%) than BTC buy-and-hold (65.8%). Naive
diversification across the 10 majors was no free lunch here — it was worse than just holding BTC.

**Mechanism.** The common window opens near the November-2021 cycle top. The 2022 bear market
(LUNA/UST collapse, FTX failure) devastated the altcoins, and most never recovered by 2026: **8 of
the 10 majors ended below their window-start price**, including AVAX (−93%), DOT (−95%), and ADA
(−82%). An inverse-vol basket still *holds* those losers — it just risk-normalizes their weights,
it doesn't drop them — so the two winners (BTC and XRP) can't carry the other eight.

**Vol-targeting is the edge, not asset selection.** Both B1 (vol-targeted BTC) and the
vol-targeted basket land at Sharpe ≈ 0.45 and max drawdown ≈ 15–18% — far better than either raw
strategy (B0's 0.397 / 65.8% or raw B2's 0.194 / 69.4%). The two vol-targeted lines are nearly
identical to each other despite one running on BTC alone and the other on a 10-asset basket. This
reinforces the master plan's §1/§5 thesis: it's disciplined risk control, not diversification
across assets, that delivers the risk-adjusted profile.

**Window caveat.** This is a single, BTC-unfavorable window. BTC B0's Sharpe here is **0.397**,
versus **1.075 over BTC's full 2013–2026 history** (`docs/benchmark-b0-b1-report.md`) — the common
window captures a post-top, bear-heavy stretch that flatters neither BTC nor the basket.
Conclusions above are specific to 2021-12 → 2026-03; a full-history dynamic-composition basket
(open topic **T0007**) would test whether the basket's underperformance is structural (alt-vs-BTC
beta) or an artifact of this particular window.

**B2's place in the family.** B2 does **not** raise the bar. The deployable target stays the
vol-targeted / gated family established on single-asset BTC — any Phase-4 alpha strategy still
has to clear B0/B1/gated-B1 from the prior report, not the raw basket.

## Distrust-the-instrument note

The whole stack — 10 real `data/ohlc-full/<BASE>/EUR/1440.parquet` daily closes, common-calendar
intersection, `inverse_vol_basket`, `run_backtest`, and the `sharpe`/`max_drawdown`/
`annualized_return` metrics — ran end-to-end and produced a *counter-intuitive* result (the basket
losing to single-asset BTC). That result is corroborated independently by the per-asset multiples:
8 of the 10 majors are down 47–95% over the same window, so the basket's loss reflects real 2022
alt-market carnage propagating through the weighting, not an internal artifact of the generator or
the backtester.

## Caveats

- **Single common window** (2021-12-21 → 2026-03-31, ~4.3 years) — the span where all 10 majors
  co-exist, driven by AVAX's late listing. It is not BTC's full history and skews bear-heavy (see
  window caveat above).
- **Zero-fee.** The basket rebalances its inverse-vol weights daily, so its net returns are the
  most fee-sensitive strategy in the panel — more so than the single-asset vol-target lines. A
  basket-turnover cost model and the §9.6-style stress ladder are deferred to a later iteration.
- **Fixed 10-asset intersection composition.** This basket drops each asset's pre-listing history
  to force a common calendar; the dynamic full-history variant that lets composition grow from 2
  assets (2013) to 10 (2021+) is parked as open topic **T0007**.
- **B3** (gate × basket), **B4** (short), and the DSR/PBO/SPA statistical-significance comparison
  across the full benchmark family are deferred to later iterations.
