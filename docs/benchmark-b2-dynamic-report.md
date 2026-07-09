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
still stands as the bar-to-beat; B2-dyn matches BTC but does not raise it. *(Superseded 2026-07-09:
**B3+vt-dynamic** — built in §"B3 and B4" below — was adopted as the frozen benchmark on the PR-74
review; master-plan §9, T0009.)*

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

## B3 and B4: gating and shorting the dynamic basket (iter-055)

The overlays mirror the fixed-window report: the gate is the same 200-day long/flat rule applied to a
**self-referential signal** — the basket's own equity index (cumulative product of the B2-dyn series,
seeded 1.0) vs its trailing 200-day average; B4 replaces "flat" with "short". Vol-targeted variants size
on the **raw basket** (10 %/yr, 30d) with the gate applied after — the committed generator's convention,
verified by reproducing the fixed-window numbers below. Gate warm-up (k < 199) is flat, never short.

**Instrument QA (all passed before any number was read):** the same code path reproduces (a) the
committed fixed-window B3/B4 line-for-line (B3 Sharpe 0.2369/maxDD 48.4 %; B3+vt 0.2696/14.8 %;
B4 −0.1362/83.0 %; gate long 41.8 %, B4 short 45.5 %), (b) this report's own B2-dyn numbers exactly,
and (c) gated-B1's 1.244 zero-fee / 1.047 net-of-cost; the per-asset weights reconstruct the basket
returns to 0.0; the dynamic gate makes 88 transitions (long 52.5 % of periods; B4 short-active 43.1 %).

### Full history 2013→2026, zero-fee

| Strategy | Total | Annualized | Sharpe | Max DD |
| --- | ---: | ---: | ---: | ---: |
| B2-dyn (reference) | 1169× | 75.6 % | 1.100 | 90.1 % |
| B2-dyn + vol-target | 4.79× | 13.3 % | 1.147 | 24.8 % |
| B3 — gated basket (long/flat) | 1239× | 76.4 % | 1.270 | 75.3 % |
| **B3 + vol-target** | 4.36× | 12.4 % | **1.419** | 21.9 % |
| B4 — long/short | 254× | 55.4 % | 0.959 | 91.5 % |
| B4 + vol-target | 4.23× | 12.2 % | 1.079 | 32.1 % |

Unlike the fixed window (where the gate rescued-but-didn't-lift and the short was disastrous), over the
full history the self-gate **helps**: B3+vt (1.419) beats both the vol-targeted basket (1.147) and
gated-B1 (1.247) zero-fee. B4 confirms — a **fourth** time — that the short kills: its raw margin carry
is 37.6 %/yr (short-active 43 % of periods at full weight).

### Net of cost (per-asset turnover × 1.5× Tier-1 maker + short margin carry)

| Strategy | net-of-cost Sharpe (full) | net-of-cost Sharpe (k ≥ 230) | spot drag | margin drag |
| --- | ---: | ---: | ---: | ---: |
| gated-B1 (the frozen bar) | 1.047 | 1.074 | 1.74 %/yr | — |
| B2-dyn | 1.043 | 0.958 | 4.65 %/yr | — |
| B2-dyn + vt | 1.028 | 0.994 | 1.37 %/yr | — |
| B3 | 1.150 | 1.180 | 6.89 %/yr | — |
| **B3 + vt** | **1.245** | **1.278** | 1.48 %/yr | — |
| B4 | 0.293 | 0.305 | 12.80 %/yr | 37.6 %/yr |
| B4 + vt | 0.297 | 0.301 | 2.74 %/yr | 6.0 %/yr |

(k ≥ 230 = past both gated-B1's 199-period gate warm-up and B3's ~229-period basket-lookback + equity-gate
warm-up — the apples-to-apples window per the iter-053 lesson.)

### Significance — read symmetrically

- **B3+vt vs gated-B1 head-to-head (net-of-cost): NOT significant** — p = 0.289 full / 0.271 post-warm-up
  (seed-stable 0.268–0.271), mean outperformance only +0.4 bps/day between two highly-correlated
  vol-targeted series. The **point** Sharpe edge (~+0.2) is real but statistically indistinguishable —
  the same estimation-uncertainty regime as every benchmark comparison since Phase 3.
- The K=4 overlay-family reality check vs gated-B1 gives p = 0.0085 with **raw B3** as the best arm —
  but that test rewards mean **return** (raw B3 does 76 %/yr at 75 % drawdown), not risk-adjusted
  quality; it is reported for completeness, not leaned on.

### What this changes — and what it doesn't

**The benchmark family now contains a member with a higher point net-of-cost Sharpe than gated-B1** —
no alpha family required; the benchmarks did it themselves. It does **not** settle the deployable bar:
B3+vt trades a ~+0.2 (non-significant) Sharpe edge for **~1.8× the drawdown** (21.9 % vs 12.3 %
zero-fee), and Phase 3's bar choice deliberately weighed drawdown control. Choosing between them — and
swapping the kill bar's **frozen benchmark**, a pre-registered-protocol change — is escalated as the
first item of **T0009**, not decided here. **(Update: decided by the human on the 2026-07-09 PR-74
review — B3+vt-dynamic is adopted as the frozen benchmark; the exact construction + reference
figures are bound in master-plan §9 and T0009's Done-so-far.)**

Re-reads against the candidate bar (k ≥ 230, net-of-cost): **A1-long/flat weekly** (offset-mean 1.416)
**significantly beats even B3+vt** (p = 0.0070, +1.7 bps/day) — the A1 alpha story survives the bar
move, still blocked only by the T0009 protocol questions and its 2014 tail. **A2's long/flat arms fall
below** B3+vt post-warm-up (1.24 / 1.20 vs 1.28) — the A2 verdict gets stronger on risk-adjusted terms
(the K=2 return-SPA vs B3+vt gives p = 0.026, i.e. A2 significantly out-*returns* the candidate bar at
higher risk — the usual return-vs-Sharpe pattern, not a Sharpe win). A1-long/flat *daily*
(1.142) is below the candidate bar.

## Caveats

- **Zero-fee (headline tables).** The basket rebalances inverse-vol weights daily and is the most
  fee-sensitive line in the family. The per-asset turnover + margin-carry **cost model is now applied**
  in §"B3 and B4" (net-of-cost for all six variants, 1.5× Tier-1 maker — the pre-registered stress rung);
  the remaining §9.6 rungs (2×, taker-only) are **explicitly dropped** for benchmarks — the kill bar's
  1.5× rung is the load-bearing one, and the A-family verdicts already carry it (A1's kill bar
  applies costs).
- **B3/B4 dynamic variants**: delivered above (iter-055, resolving T0010).
- **Point estimates marginally favor the basket, but not significantly** — the verdict is "≈tied,"
  read symmetrically. Do not carry "basket beats BTC" forward; carry "basket is a viable base,
  co-equal with btc_only under A1's kill bar."
- Union calendar is the sorted union of the 10 majors' daily `ts`; BTC's own 1-day gap makes the
  union (4582) one longer than BTC's series (4581) — immaterial to the metrics.
