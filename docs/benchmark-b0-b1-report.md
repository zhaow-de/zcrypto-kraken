# Benchmark Gated-BTC Panel: B0/B1 and Their 200-Day-Gated Variants on Real BTC/EUR Daily

This report records the **gated-BTC benchmark panel** — B0 buy-and-hold, B1 vol-targeted BTC, and
their 200-day-gated variants (gated-B0, gated-B1) — run through the full stack (dataset → returns
→ strategy → backtester → metrics) on real BTC/EUR daily OHLC data (2013-09-10 → 2026-03-31; 4581
daily closes → 4580 returns from 2013-09-11), at zero trading fees. Zero-fee is the headline
benchmark idealization; the `## Cost stress (§9.6)` section below re-runs the same four strategies
at the confirmed Tier-1 Kraken fee ladder, per `docs/research/00.master-plan.md` §9.6 (cost
stress). Any Phase-4 alpha strategy must clear this floor to be worth pursuing.

B1 uses the master plan's specified target — **vol-targeted BTC at 10–12%/yr** annualized
realized vol (§9; §10 risk model), 30-day lookback, no leverage above 1.0×. The primary row below
is the 10% end; the 10–12% range is discussed under Interpretation. The gate is the 200-day
long/flat regime rule (the §5 prior survivor): long BTC when the close sits above its trailing
200-day SMA, flat otherwise.

## Results

| Strategy                             | Total return | Annualized | Sharpe | Max DD |
| ------------------------------------- | ------------: | ----------: | ------: | ------: |
| B0 — buy-and-hold                     |        606.9× |      66.7% |  1.075 |  82.5% |
| gated-B0 — 200-day gate               |        188.9× |      51.9% |  1.102 |  62.8% |
| B1 — vol-target (10%/yr, 30d, ≤1.0×)  |          3.76× |      13.2% |  1.111 |  22.0% |
| gated-B1 — gate × vol-target          |          2.75× |      11.1% |  1.247 |  12.3% |

The 200-day gate is long BTC on ~56.0% of days, flat the rest.

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

### The 200-day regime gate

Overlaying the 200-day long/flat gate shows the same trade-off surfacing from the other side. On
top of B0, the gate is long only ~56.0% of days, and this alone cuts the max drawdown from
**82.5% → 62.8%** while *raising* the Sharpe from **1.075 → 1.102** — sidestepping some of BTC's
worst drawdowns without giving up all participation in the trending regimes. Combined with
vol-targeting (gated-B1 = gate × B1), the two effects compound: max drawdown falls further to
**12.3%** (roughly a seventh of B0's), and Sharpe rises to **1.247** — the best risk-adjusted
result in the panel, at the cost of participation (total return ~2.75×, 11.1%/yr — a similar
order to B1 alone).

This is directionally consistent with — and supports — the master plan's §1/§5 thesis: a
disciplined, vol-targeted trend/regime rule — not raw buy-and-hold, and not vol-targeting alone —
is the realistic best case and the deployable target family. (These are single-run, zero-fee
benchmark numbers, not statistically-tested edges — the DSR/PBO/SPA significance comparison across
the family is a later iteration; "supports," not "proves.") It sets the benchmark any Phase-4 alpha
strategy must clear on risk-adjusted terms to justify added complexity.

Together these four form the deployment floor (§9's rule: the deployed system is the best of
{benchmarks ∪ validated survivors}). Any Phase-4 alpha must clear B0 on return/Sharpe, B1 on
drawdown-for-Sharpe, or gated-B1 on risk-adjusted return (Sharpe 1.247, maxDD 12.3%) to justify
added complexity over simply holding — or vol-targeting, or gating — BTC.

## Cost stress (§9.6)

The master plan's §9.6 deployment gate requires every headline result to be re-run at 1.5× and 2×
the fitted cost model, with the rule: **a strategy that dies at 1.5× costs is not deployable.** The
fitted base here is the confirmed **Tier-1 Kraken maker fee, 0.40%**
(`cli.costs.spot_fee_rates(0.0)["maker"]`), so the stress ladder is **0.40% (base) → 0.60% (1.5×)
→ 0.80% (2×, which coincides with the Tier-1 taker fee)**, applied through the backtester's
per-turnover `fee_rate`.

### Sharpe by fee level

| Strategy                             |    @0 | @0.40% (maker, base) | @0.60% (1.5×) | @0.80% (2×=taker) |
| ------------------------------------- | -----: | ---------------------: | --------------: | -------------------: |
| B0 — buy-and-hold                     | 1.075 |                  1.075 |            1.074 |                 1.074 |
| gated-B0 — 200-day gate                | 1.102 |                  1.040 |            1.009 |                 0.978 |
| B1 — vol-target (10%/yr, 30d, ≤1.0×)   | 1.111 |                  1.029 |            0.988 |                 0.948 |
| gated-B1 — gate × vol-target           | 1.247 |                  1.117 |            1.052 |                 0.986 |

**B0 is fee-immune.** Its turnover is ≈0.0002/day — it only ever buys once — so its Sharpe is
essentially unchanged across the ladder (1.075 at zero fees, 1.074 at 2×).

The **gated and vol-targeted strategies rebalance**: the vol-target position resizes daily and the
gate flips regime, so gated-B1's turnover runs ≈0.008/day, and its net Sharpe erodes steadily with
the fee — **1.247 → 1.117 → 1.052 → 0.986** across the ladder.

**§9.6 verdict: gated-B1 does not die at 1.5×** — its Sharpe at 0.60% fees is 1.052, still above
1.0, so it clears the deployment gate. The erosion is gentle precisely because its turnover is low.

**The honest crossover (distrust-the-instrument).** At the realistic base maker fee (0.40%),
gated-B1 (1.117) is still the panel's best Sharpe, above B0 (1.075). But because B0 is fee-immune
while gated-B1 pays to rebalance, **B0 overtakes gated-B1 on Sharpe at 1.5×+ stress** (1.074 vs
1.052 at 0.60%; 1.074 vs 0.986 at 0.80%). So gated-B1's *Sharpe edge over buy-and-hold* is
fee-sensitive and does not survive the stress ladder — its **drawdown** advantage does: gated-B1's
maxDD stays **15–18%** across the ladder versus B0's flat **82.5%**, roughly 4–5× smaller. The
deployment case for the gated/vol-targeted family rests on **risk (drawdown) control**, not a
fee-proof return edge.

A subtler, correct effect worth naming: **fees slightly raise the gated strategies' max drawdown**
— gated-B1's maxDD widens from **12.3% → 18.0%** across the ladder (annualized return also falls,
**11.1% → 8.6%**) — because the fee drag deepens and extends drawdown troughs rather than just
shaving off average return. This is expected behavior, not a bug.

## Statistical significance (bootstrap CIs)

The `## Results` and `## Cost stress` tables above are single-run point estimates. To gauge how
much of the ranking is signal versus noise from one ~12-year price path, this section adds 95%
confidence intervals on each strategy's annualized Sharpe, via a **stationary block bootstrap**
(`cli.validation.bootstrap_ci`, Politis–Romano resampling) on the zero-fee net-return series, with
block length **ℓ=16** (≈ n^(1/3) for the 4580-return history), **2000 resamples**, seed=42.

| Strategy                             |  Point |        95% CI |
| ------------------------------------- | -----: | -------------: |
| B0 — buy-and-hold                     |  1.075 |  [0.47, 1.70] |
| gated-B0                              |  1.102 |  [0.48, 1.70] |
| B1 — vol-target                       |  1.111 |  [0.43, 1.79] |
| gated-B1 (the bar)                    |  1.247 |  [0.61, 1.88] |

**All four Sharpes are significantly positive** — every lower bound (0.43–0.61) sits well above
zero, so each strategy's edge over a zero-Sharpe null is real. But **their CIs overlap heavily**:
gated-B1's [0.61, 1.88] comfortably brackets the other three strategies' point estimates, and vice
versa — from a single ~12-year path, the four Sharpes are **not statistically distinguishable**
from one another. gated-B1 does carry both the highest point estimate (1.247) and the highest,
most robustly-positive lower bound (~0.61, stable across block lengths ℓ∈{8,16,24} and seeds∈{1,
42,99}), so it remains the best-supported pick in the family — but that pick rests on **point
estimate + best lower bound + drawdown control** (12.3% vs B0's 82.5%), **not** on a statistically
significant Sharpe edge over B0 or B1. No such edge exists at this sample size.

## Regime slices (calendar-year)

The tables above are single point estimates over the whole 2013–2026 history. This section slices
the same zero-fee net-return series by **calendar year** — each return `rets[k]` is bucketed by the
year it is realized in (`ts[k+1].year`), and each cell is the compounded net return for that
strategy over that year's returns. **2013 and 2026 are partial years**: 2013 covers only the last
108 days of the dataset (2013-09-11 to year end) and additionally sits inside the 200-day gate's
warm-up, so gated-B1 shows 0.0% (flat, not yet gated); 2026 covers only the first 90 days of the
year (through 2026-03-31, the dataset's end).

| Year               |    B0 |   B1 | gated-B1 |
| ------------------ | ----: | ---: | -------: |
| 2013 (partial, 108 d) | 455.7% | 20.8% |     0.0% |
| 2014               | −50.5% | −10.7% |   −5.5% |
| 2015               |  48.5% | 20.2% |    19.1% |
| 2016               | 131.1% | 39.9% |    39.9% |
| 2017               | 1211.3% | 46.9% |    46.9% |
| 2018               | −73.0% | −17.9% |   −5.2% |
| 2019               |  97.7% | 25.2% |     8.9% |
| 2020               | 269.6% | 33.6% |    27.5% |
| 2021               |  71.9% |  9.6% |   −0.6% |
| 2022               | −62.1% | −17.1% |   −0.5% |
| 2023               | 149.0% | 27.0% |    11.4% |
| 2024               | 134.6% | 23.8% |    17.2% |
| 2025               | −17.3% | −4.1% |   −4.6% |
| 2026 (partial, 90 d) | −20.8% | −5.2% |     0.0% |

**gated-B1 turns catastrophic bear years into near-flat ones.** In the three big BTC bear years —
2014 (**−50.5%**), 2018 (**−73.0%**), 2022 (**−62.1%**) — gated-B1 lost only **−5.5%, −5.2%,
−0.5%** by going flat below the 200-day line. Its **worst year in the whole 2013–2026 sample is
−5.5%**; B0 has four double-digit-loss years.

**The gate's marginal value over vol-targeting is concentrated in the bear years.** Vol-targeting
alone (B1) already softens them (2018 −17.9%, 2022 −17.1%), but the gate cuts them much further
(2018 −5.2%, 2022 −0.5%). In calm uptrends (2016, 2017) the gate is long all year and gated-B1 ≡
B1.

**The cost is the bull-year cap.** gated-B1 gives up the explosive years — 2017 (**+46.9%** vs
B0's **+1211%**), 2020 (+27.5% vs +269.6%) — so over the full history it dramatically
underperforms buy-and-hold in *raw cumulative* return (the report's headline: 2.75× vs 607×). It
trades return for the elimination of catastrophic years.

**This decomposes the whole dossier.** The bootstrap CIs above showed gated-B1's Sharpe edge over
B0/B1 is *not* statistically significant; the year-by-year view shows what *is* robust and
economically real — not a higher average return, but **never losing more than ~6% in a year**.
That bear-year elimination is the source of the low max drawdown (12.3% vs 82.5%) and is why
gated-B1 is the frozen deployment bar.

This is a single historical path, not a guarantee — "worst year −5.5%" describes 2013–2026, it is
not a guaranteed floor for future years.

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
- Zero transaction cost in the headline `## Results` table above — a benchmark idealization, not a
  live-trading estimate. (The gated and vol-targeted strategies rebalance whenever the gate flips
  or the vol-target position resizes, so the *net* returns of gated-B0, B1, and gated-B1 are more
  fee-sensitive than B0's; the `## Cost stress (§9.6)` section above now applies the confirmed
  Tier-1 fee ladder to all four.)
- The `## Cost stress (§9.6)` ladder stresses **exchange fees only**. The bid-ask spread — a
  further per-trade cost that would deepen the same erosion — is not yet modeled (it is gated on
  the D2 forward-capture pipeline whose captured L2 books feed the per-pair spread term, open topic
  T0003). Margin rollover/carry is genuinely N/A for this
  panel: all four strategies are long/flat spot (position ≤ 1.0×, never short), so nothing is
  borrowed.
- The full B0–B4 benchmark panel (adding the basket + short strategies) and the DSR/PBO/SPA
  statistical-significance comparison (the §9 deployment rule) are deferred to later iterations.
