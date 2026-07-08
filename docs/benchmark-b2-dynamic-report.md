# Benchmark B2-dynamic: Full-History Dynamic-Composition Majors Basket (finding-1)

This report records the **full-history dynamic-composition B2 variant** — the honest answer to
Phase-4 **finding 1** (`docs/research/05.phase4-orientation.md`): *does a majors basket beat
single-asset BTC?* The fixed-window B2 (`docs/benchmark-b2-basket-report.md`) said the basket
*loses* to BTC (0.68×, Sharpe 0.194) — but over a single AVAX-limited 4.3-year window
(2021-12-21 → 2026-03-31) that opens at the cycle top and is uniquely alt-hostile, with bootstrap
CIs too wide to distinguish any strategy from zero. This variant grows the basket **2 → 10 assets
as they list** over BTC's full **2013-09-10 → 2026-03-31** history, so finding 1 can be answered
over the whole sample rather than the alt-hostile tail.

The basket is `dynamic_inverse_vol_basket` (`cli/benchmark/strategies.py`, iter-044): the 10 EUR
majors (ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP) are aligned to their **union `ts`
calendar** (4582 daily closes → 4581 returns), a day is `None` when the asset is absent
(pre-listing or a data gap), and at each period the basket inverse-vol-weights (30-day lookback)
**only the assets with a complete, gap-free trailing window** — renormalizing over that period's
qualifying set. It is strictly look-ahead-free (a period's weights use only returns *before* it)
and reduces bit-for-bit to the fixed `inverse_vol_basket` when no asset is absent. BTC B0/B1 are
re-run over BTC's own full history for an apples-to-apples span match. Zero trading fees
throughout — a benchmark idealization, consistent with the fixed-window B2 report. Vol-targeted
lines use a 10%/yr target (`vol_target(..., target_vol=0.10 / 365**0.5, lookback=30,
max_leverage=1.0)`).

## Results — full history (2013-09-10 → 2026-03-31, 4581 returns)

| Strategy                                | Total return | Annualized | Sharpe | Max DD |
| ---------------------------------------- | ------------: | ----------: | ------: | ------: |
| B0 — BTC buy-and-hold                    |         608×  |      66.67% |   1.075 |   82.5% |
| B1 — BTC vol-target (10%/yr)             |        4.76×  |      13.24% |   1.111 |   22.0% |
| **B2-dyn — dynamic basket (raw)**        |     **1169×** |  **75.56%** | **1.100** | **90.1%** |
| B2-dyn + vol-target (10%/yr)             |        4.79×  |      13.30% |   1.147 |   24.8% |

## Statistical significance (bootstrap CIs)

95% confidence intervals on the **annualized Sharpe** via the stationary block bootstrap
(`cli.validation.bootstrap_ci`, Politis–Romano), block length **ℓ=17** (≈ n^(1/3) for the 4581
returns), **2000 resamples**, seed=42 — the same method as the fixed-window report, scaled to the
full sample.

| Strategy                     |   Point |         95% CI |
| ------------------------------ | ------: | --------------: |
| B0 — BTC buy-and-hold          |   1.075 |  [0.44, 1.69] |
| B1 — BTC vol-target            |   1.111 |  [0.40, 1.79] |
| B2-dyn — dynamic basket        |   1.100 |  [0.43, 1.74] |
| B2-dyn + vol-target            |   1.147 |  [0.43, 1.83] |

**Two results, both decisive for finding 1:**

1. **All four CIs are strictly positive** (lower bounds 0.40–0.44). Over the full history every
   strategy has a *significantly* positive Sharpe — the exact power the 4.3-year window lacked,
   where all six CIs straddled zero (`docs/benchmark-b2-basket-report.md`). The full 2013–2026
   sample resolves the finding-4 power problem.
2. **The four CIs massively overlap.** The basket's point Sharpe edges BTC's (raw 1.100 vs 1.075;
   vol-targeted 1.147 vs 1.111), but the gaps (~0.03) are dwarfed by the ~1.3-wide intervals. The
   basket and single-asset BTC are **statistically indistinguishable** on risk-adjusted terms.

## Composition growth (dynamic 2 → 10)

Qualifying assets per period (a "qualifier" has a complete gap-free 30-day trailing window) and
the largest single-asset weight that period:

| Year | Qualifying | Top weight |
| ---- | ---------: | ---------: |
| 2014 |          2 |      58.4% |
| 2016 |          3 |      35.1% |
| 2018 |          4 |      36.2% |
| 2020 |          6 |      20.2% |
| 2022 |          9 |      15.7% |
| 2024 |         10 |      15.0% |

The basket grows exactly as the majors list, and the top weight *falls* (58% → 15%) as more
assets warm in — correct inverse-vol diversification. **82 periods have exactly one qualifying
asset** — 50 in 2013 (BTC-solo; LTC, the sole 2013 co-lister, is repeatedly disqualified by its 37
early data gaps + warm-up) and 32 in Jan–Feb 2018 (ETH-solo, from BTC's single 2018-01-12 data gap
disqualifying BTC for the following 30-day trailing window); in every one the basket return equals
that period's sole qualifier's own return exactly (see distrust-the-instrument note). So the
full-history basket is *BTC itself* through the 2013 open, then progressively diversifies.

## Interpretation — the finding-1 verdict

**The full-history dynamic basket is a wash against single-asset BTC — neither structurally worse
(the fixed-window story) nor a real winner.** Risk-adjusted, basket ≈ BTC (Sharpe ~1.1 both, CIs
heavily overlapping). This overturns *both* prior reads:

- **The fixed-window "basket loses to BTC" (0.68×, 0.194 vs 0.397) was a window artifact.** That
  2021-12 → 2026-03 window opened at the cycle top and caught the 2022 alt crash before most alts
  recovered; 8 of 10 majors ended below their window-start price. Over the full history — which
  also contains the 2013–2017 and 2020–2021 alt bull runs — the basket keeps pace with BTC.
- **Even the 4-major ~9-year proxy's "residual structural drag" (Sharpe 0.798 < BTC 0.929,
  `docs/benchmark-b2-basket-report.md`) does not persist** in the full 2 → 10 dynamic basket. The
  difference is the 2013–2017 head: there the dynamic basket is BTC-dominated (few assets warmed,
  50 BTC-solo periods through the 2013 open), so it inherits BTC's early run instead of the proxy's fixed-4 dilution,
  then adds the alt bull runs on top. Net: the raw basket out-*returns* BTC (1169× vs 608×) by
  riding alt bulls BTC-only missed, at a worse max drawdown (90.1% vs 82.5%) — higher return,
  higher risk, ~equal Sharpe.

**Vol-targeting remains the edge, not asset selection.** As in every prior benchmark report, the
two vol-targeted lines (B1 1.111, B2-dyn+vt 1.147) collapse the drawdown to ~22–25% and land
within noise of each other despite one holding BTC alone and the other a 2 → 10 basket. Disciplined
risk control — not diversification across assets — delivers the risk-adjusted profile (master plan
§1/§5).

**Consequence for A1 (iter-045).** Finding 1 does **not** pre-select a base. The vol-targeted
majors basket is a *viable, honest* base for the A1 alpha book — it is not inferior to a
BTC-anchored book, as the fixed window suggested — but it does not decisively beat BTC either. So
A1 legitimately carries **both** the `equal_risk_basket` (this dynamic basket) and a `btc_only`
base through its kill bar, rather than dropping the basket on finding 1. The deployable *benchmark*
bar is unchanged: the vol-targeted / gated single-asset family (gated-B1, Sharpe 1.247 full-history)
still stands as the bar-to-beat; B2-dyn matches BTC but does not raise it.

## Distrust-the-instrument note

A "basket beats BTC" reversal of the fixed-window finding is exactly the kind of too-good surprise
that gets a bug-hunt *before* the verdict. Three independent checks cleared it:

- **Reduces-to-fixed cross-check.** Over the AVAX-limited window (all 10 present, no `None`),
  `dynamic_inverse_vol_basket` returns **bit-identical** output to the reviewed fixed
  `inverse_vol_basket` — reproducing the committed B2 report exactly (B0 1.36×/0.397, B2
  0.68×/0.194, B2+vt 0.453; see the fixed-window table below). The dynamic layer is a strict,
  behavior-preserving generalization.
- **No single-period artifact.** The 4581-day raw basket series has zero non-finite values; its
  most extreme daily returns are **+39.0% (2017-03-29 alt bull)** and **−37.7% (2020-03-11 COVID
  crash)** — plausible crypto daily moves, with only 5 periods above 30% and none above 50%. The
  1169× is genuine multi-year compounding, not one blown-up bar.
- **Single-qualifier consistency.** In all 82 periods with exactly one qualifying asset — 50
  BTC-solo (2013) + 32 ETH-solo (Jan–Feb 2018, from BTC's single 2018-01-12 gap) — the basket
  return equals that period's sole qualifier's own return to within 1e-12 (0 mismatches); the
  composition/renormalization layer collapses correctly to the single warmed asset, whether the
  early-history leader or a mid-history gap survivor.

The function itself passed an independent pre-merge review (look-ahead-freeness confirmed in both
perturbation directions; `_inverse_vol_weight` refactor verified byte-identical for
`inverse_vol_basket`; 17 non-vacuous tests). The verdict rests on a trustworthy instrument.

### Fixed-window cross-check (2021-12-21 → 2026-03-31, dynamic == fixed)

| Strategy                     | Total return | Annualized | Sharpe | Max DD |
| ------------------------------ | ------------: | ----------: | ------: | ------: |
| B0 — BTC buy-and-hold          |        1.36×  |       7.49% |   0.397 |   65.8% |
| B1 — BTC vol-target            |        1.21×  |       4.61% |   0.456 |   17.5% |
| B2 — dynamic basket (raw)      |        0.68×  |      −8.57% |   0.194 |   69.4% |
| B2 + vol-target                |        1.21×  |       4.49% |   0.453 |   14.6% |

These match `docs/benchmark-b2-basket-report.md` line-for-line — the cross-check that the dynamic
generalization did not perturb the established numbers.

## Caveats

- **Zero-fee.** The basket rebalances inverse-vol weights daily and is the most fee-sensitive line
  in the family; a basket-turnover cost model + the §9.6 stress ladder are deferred (A1's kill bar
  applies costs).
- **No B3/B4 dynamic variants this pass.** The gate × basket (B3) and basket + short (B4) overlays
  were characterized on the fixed window (`docs/benchmark-b2-basket-report.md`); a full-history
  dynamic B3/B4 is a noted follow-up once the basket base is in the A1 loop.
- **Point estimates marginally favor the basket, but not significantly** — the verdict is "≈tied,"
  read symmetrically. Do not carry "basket beats BTC" forward; carry "basket is a viable base,
  co-equal with btc_only under A1's kill bar."
- Union calendar is the sorted union of the 10 majors' daily `ts`; BTC's own 1-day gap makes the
  union (4582) one longer than BTC's series (4581) — immaterial to the metrics.
