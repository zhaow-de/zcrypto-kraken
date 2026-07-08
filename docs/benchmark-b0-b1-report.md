# Benchmark Bar-to-Beat: B0/B1 on Real BTC/EUR Daily

This report records the first **bar-to-beat**: B0 buy-and-hold BTC and B1 vol-targeted BTC,
run through the full stack (dataset → returns → strategy → backtester → metrics) on real
BTC/EUR daily OHLC data (2013-09-10 → 2026-03-31; 4581 daily closes → 4580 returns from
2013-09-11), at zero trading fees. Zero-fee is a benchmark idealization — cost stress is
applied later, at evaluation time, per `docs/research/00.master-plan.md` §9 (cost stress).
Any Phase-4 alpha strategy must clear this floor to be worth pursuing.

B1 uses the master plan's specified target — **vol-targeted BTC at 10–12%/yr** annualized
realized vol (§9; §10 risk model), 30-day lookback, no leverage above 1.0×. The primary row
below is the 10% end; the 10–12% range is discussed under Interpretation.

## Results

| Strategy                            | Total return | Annualized | Sharpe | Max DD |
| ----------------------------------- | ------------: | ----------: | ------: | ------: |
| B0 — buy-and-hold                   |         606.9× |      66.7% |  1.075 |  82.5% |
| B1 — vol-target (10%/yr, 30d, ≤1.0×) |           3.76× |      13.2% |  1.111 |  22.0% |

## Interpretation

BTC buy-and-hold (B0) is a **high-return, brutal-drawdown** floor: over 2013–2026 it turns 1×
into ~607× (66.7%/yr), but an investor holding through it must stomach an **82.5%** peak-to-trough
loss — and its Sharpe is ~1.08.

Vol-targeting (B1) is the **low-risk** floor. Scaling BTC exposure so realized vol tracks a
10%/yr target keeps the position around **0.17× on the median day** (BTC's own realized vol is
~5–8× the target, and the 1.0× leverage cap never binds), which cuts the max drawdown to **~22%**
— roughly a quarter of B0's — while *raising* the Sharpe slightly to **1.11**, because de-risking
the highest-vol regimes improves risk-adjusted return. The trade-off is participation: total
return drops to ~3.8× (13.2%/yr) since most days are only fractionally invested.

Because vol-targeting scales the position linearly, **Sharpe is invariant to the target vol**
(it scales mean and stdev of the strategy returns equally): at 10 / 11 / 12%/yr the Sharpe stays
**1.11**, while max drawdown rises **22.0% → 24.0% → 25.9%** and annualized return **13.2% →
14.6% → 15.9%** (total 3.8× → 4.5× → 5.4×). So the 10–12% band is a single risk/return ray, not
a Sharpe choice.

Together these are the deployment floor (§9's rule: the deployed system is the best of
{benchmarks ∪ validated survivors}). Any Phase-4 alpha must clear **B0 on return/Sharpe** or
**B1 on drawdown-for-Sharpe** to justify added complexity over simply holding — or vol-targeting
— BTC.

## Distrust-the-instrument note

The whole stack — real `data/ohlc-full/BTC/EUR/1440.parquet` daily closes, `returns_from_prices`,
the `buy_and_hold`/`vol_target` strategies, `run_backtest`, and the `sharpe`/`max_drawdown`/
`annualized_return` metrics — ran end-to-end on real data and produced sane numbers. BTC's
**~82% max drawdown** is a known historical fact (the 2018 and 2022 crashes), so the backtester
and its drawdown calculation check out against reality rather than an internal artifact; and the
vol-targeted position sitting near 0.17× matches the master plan's own expectation (§10:
"typical net exposure ≈ 0.2–0.5× in crypto-vol regimes").

## Caveats

- Single-asset (BTC/EUR) only — no cross-asset panel yet.
- Zero transaction cost — a benchmark idealization, not a live-trading estimate. (Vol-targeting
  rebalances daily, so B1's *net* return is more fee-sensitive than B0's; the fee model folds in
  with the full-panel run.)
- The full B0–B4 benchmark panel and the DSR/PBO/SPA statistical-significance comparison
  (the §9 deployment rule) are deferred to later iterations.
