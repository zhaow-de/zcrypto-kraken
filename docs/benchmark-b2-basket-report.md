# Benchmark B2: Inverse-Vol Majors-Basket Bar-to-Beat on Real Data

> **Update 2026-07-09:** gated-B1 was superseded as the frozen benchmark / deployable bar by
> **B3+vt-dynamic** (master-plan §9; T0009 item 1, human-adopted). The panel below stands as the
> Phase-3 record; present-tense "frozen bar" statements in this file describe the *then*-frozen bar.

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

## B3 and B4: gating and shorting the basket

The gate here is the same 200-day long/flat rule as the single-asset panel, but applied to a
**self-referential regime signal**: the basket's own equity index (the cumulative product of the
B2 return series, seeded at 1.0), not a market proxy. B3 goes long when the basket's equity is
above its trailing 200-day average and flat otherwise; B4 replaces "flat" with "short" below the
average. Both run over the same common window (2021-12-21 → 2026-03-31, 1561 returns), zero-fee.

| Strategy                          | Total return | Annualized | Sharpe | Max DD |
| ---------------------------------- | ------------: | ----------: | ------: | ------: |
| B2 — raw basket (reference)        |         0.68× |     −8.57% |   0.194 |   69.4% |
| B3 — gated-B2 (200d, long/flat)    |         1.06× |      1.36% |   0.237 |   48.4% |
| gated-B2 + vol-target              |         1.08× |      1.73% |   0.270 |   14.8% |
| **B4 — basket long/short**          |     **0.34×** | **−22.43%** | **−0.136** | **83.0%** |

Gate long fraction ≈ **41.8%**; B4 short fraction ≈ **45.5%**.

**B3 (gate) rescues the raw basket from a loss but doesn't lift it.** Long only ~41.8% of the
time, the gate turns the −8.6%/yr raw basket into a slight +1.4%/yr gain (0.68× → 1.06×) and
roughly halves the drawdown (69.4% → 48.4%) by sitting out much of the alt bear — but Sharpe
(0.237) stays far below the vol-targeted basket's 0.453.

**The gate HURTS the vol-targeted basket.** gated-B2 + vol-target (Sharpe 0.270) is *worse* than
plain B2 + vol-target (0.453): once vol-targeting controls the risk, the gate only subtracts
participation. On the basket the gate and vol-target are **substitutes, not complements** — the
*opposite* of single-asset BTC, where `gate × vol-target` (gated-B1) was the **best** result in
the whole family (Sharpe 1.247, `docs/benchmark-b0-b1-report.md`).

**B4 (short) is disastrous.** Adding the short takes Sharpe *negative* (**−0.136**) and the
drawdown to **83.0%** — worse than every other line. The 200-day gate is a *lagging* signal: it
flips to short only *after* price is already below the trailing SMA, so B4 shorts into the
violent 2022–2023 bear-market counter-rallies and gets whipsawed. Shorting a lagging-trend basket
over this window destroyed capital.

**Family conclusion.** No overlay lifts the basket to the single-asset BTC bar. Vol-targeting is
the only overlay that helps; gating rescues-but-doesn't-lift and is redundant with vol-targeting;
shorting backfires. The deployable target remains **gated-B1** (vol-targeted BTC with the regime
gate) from the single-asset panel.

B4 is an **idealized long/short** (zero-cost, always-shortable). Real short-borrow costs and
per-alt shortability constraints on Kraken spot-margin would make B4 *even worse* — and it is
already the worst line in the panel.

## Statistical significance (bootstrap CIs)

Same method as `docs/benchmark-b0-b1-report.md`, scaled to this shorter window: 95% confidence
intervals on the annualized Sharpe via the **stationary block bootstrap**
(`cli.validation.bootstrap_ci`, Politis–Romano resampling) on each strategy's zero-fee net-return
series, block length **ℓ=12** (≈ n^(1/3) for the 1561-return common window), **2000 resamples**,
seed=42.

| Strategy                     |   Point |          95% CI |
| ------------------------------ | ------: | ---------------: |
| B0 — BTC buy-and-hold          |   0.397 |  [−0.55, 1.38] |
| B1 — BTC vol-target            |   0.456 |  [−0.59, 1.53] |
| B2 — inverse-vol basket        |   0.194 |  [−0.74, 1.18] |
| B3 — gated-B2                  |   0.237 |  [−0.68, 1.26] |
| B2 + vol-target                |   0.453 |  [−0.57, 1.49] |
| B4 — long/short                |  −0.136 |  [−1.05, 0.80] |

**Every CI straddles zero.** Over this short ~4.3-year window, not one strategy — not BTC
buy-and-hold, not the basket, not either vol-targeted line — has a significantly-positive Sharpe,
and B4's −0.136 is not significantly negative either ([−1.05, 0.80] spans both signs). The
basket's underperformance against BTC (`## Interpretation` above) and B4's disastrous −0.136
(`## B3 and B4` above) are **directional point estimates, not significant results** at this
sample size.

This is a **power problem, not a null finding**: 1561 daily returns spanning a single
bull→bear→recovery cycle cannot statistically distinguish these Sharpes from each other or from
zero. It reinforces the case for the full-history, dynamic-composition basket parked as open
topic **T0007** — a basket spanning BTC's full 2013–2026 history, rather than one truncated to
AVAX's 2021-12 listing, would have the sample horizon this common window lacks.

## Longer-history robustness check (4 majors, ~9 years)

The window caveat above asks whether B2's underperformance is *structural* (alt-vs-BTC beta) or a
*window artifact* of the alt-hostile 2021-12 → 2026-03 stretch. A partial answer, at low cost,
comes from restricting the basket to the **four majors with long history** — BTC, ETH, LTC, XRP —
whose common window is **2017-05-18 → 2026-03-31 (3239 days, ~8.9 years)**, spanning the 2018 bear,
the 2020–21 bull, the 2022 crash, and the 2023–25 recovery (multiple full cycles). All strategies
below are re-run over this identical window, zero-fee; gated-B1's Sharpe here (**0.759**) is
window-specific and far below its full-history **1.247** (this window omits BTC's 2013–2016 run).

| Strategy (same 2017–2026 window)       | Total return | Annualized | Sharpe | Max DD |
| --------------------------------------- | ------------: | ----------: | ------: | ------: |
| B0 — BTC buy-and-hold                   |        34.63× |      49.12% |  0.929 |  82.5% |
| gated-B1 — BTC (the frozen bar)         |         1.68× |       6.05% |  0.759 |  12.3% |
| 4-major inverse-vol basket              |        16.31× |      36.99% |  0.798 |  86.4% |
| 4-major basket + vol-target (10%/yr)    |         2.22× |       9.43% |  0.841 |  20.9% |

Two things change and one does not:

- **The catastrophic loss was largely a window artifact.** Over ~9 years the raw 4-major basket
  returns **16.31×** (Sharpe 0.798) — nothing like the 10-asset basket's 0.68× *loss* over the
  4.3-year window. The 2021–2026 window was uniquely alt-hostile (it opened at the cycle top and
  caught the 2022 crash before most alts recovered); a longer window that also contains the alt
  bull runs is far kinder to the basket.
- **A residual structural drag remains.** Even over ~9 years the raw basket does **not** beat
  single-asset BTC on risk-adjusted terms — Sharpe 0.798 < BTC's 0.929, and its max drawdown
  (86.4%) is *worse* than BTC's (82.5%). BTC was the best single major (34.6× vs ETH 21.1×, XRP
  3.6×, LTC 1.8×), so inverse-vol weighting still dilutes the winner with laggards.
- **The vol-targeted basket is competitive with the bar over this window.** The 4-major basket
  *with* vol-targeting (Sharpe **0.841**, maxDD 20.9%) edges the same-window gated-B1 (0.759) on
  Sharpe — though with a worse drawdown and on a single window. So the basket base, once
  vol-targeted, is not disqualified; it is a *viable* candidate to A/B in Phase 4, more so than the
  4.3-year window alone suggested (cf. `docs/research/05.phase4-orientation.md` finding 1).

**Caveat:** this is a *fixed 4-asset* proxy (not the full 10, and not the dynamic 2→10 composition),
and its window still starts in 2017, not BTC's 2013. It narrows the structural-vs-window question
but does not close it — the honest test remains the full-history dynamic-composition basket
(**T0007**).

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
- The DSR/PBO/SPA statistical-significance comparison across the full benchmark family, and the
  basket-turnover cost model, are deferred to later iterations.
