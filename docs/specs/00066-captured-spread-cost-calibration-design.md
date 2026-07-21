# Captured-spread cost calibration — design (T0014)

**Status:** ratified by the 2026-07-22 `/zcrypto-auto-exec` run (approval gates pre-satisfied by the invocation; every decision below is a reversible research choice recorded here and in `docs/research/14.phase6-decisions.md`).

## Goal

Close the cost model's known-missing **spread term**. Phase-4/5 verdicts charged Kraken fees plus margin carry and assumed **zero spread**, on a basket whose thin alts are exactly where spread bites. Calibrate the term from our own captured L2, add it to `cli/costs/`, and re-read the A-family net-of-cost conclusions with it included.

## The data actually used

`/mnt/zhao-crypto/l2-panel` (spec `00052` / iter-098), read over NFS, **full window** per the [capture-era data-hygiene map](../reference/capture-era-data-hygiene-map.md) (T0071): the desync-era archive was never contaminated, so no era is excluded.

- 10 pairs × **315 hourly files**, `2026-07-08 13:47:33Z … 2026-07-21 15:59:59Z` — **1,123,509–1,123,514 one-second rows per pair** (~11.2 M total, 696 MB).
- Span is **13.1 days, not the nominal 14**: the panel trails live capture by the ~7 h settle watermark (T0066), so the 336th hour lands well after this run. Stated rather than rounded up — one marginal day cannot move a percentile over 1.1 M observations, and the honest span is what the reference doc records.
- `fill_bps_{bid,ask}_{100,1k,10k}` — effective spread at a EUR notional, mid-relative, one side — had a **0.00 % null rate at every size for every pair**, so the visible book covered €10k at all times; no shallow-book exclusions were needed.

## D1 — Use the effective spread at size, not the top-of-book spread

**Measured, and this is the load-bearing decision.** `spread_bps` is unusable as a per-pair constant for BTC:

| | BTC | every other pair |
|---|---|---|
| `spread_bps` mean ÷ median | **11.2×** | 0.9–1.3× |

BTC/EUR is **tick-quantised at €0.10** and sits at exactly one tick 42–58 % of the time. Because that fraction straddles 50 %, the *median* flips ~15× (0.29 bps → 0.018 bps around 2026-07-13) on a modest change in the 1-tick share, while the distribution barely moves. A median-based BTC spread is therefore an artifact of where the mode sits relative to the 50th percentile — not a property of the market.

The effective spread at size has no such problem (BTC: p50 0.346 vs mean 0.392 bps at €1k), because walking the book averages over the tick quantisation. It is also the quantity we actually pay. **The model uses the mean `fill_bps` at the traded notional.**

Corollary recorded so it is not re-derived: **never quote a median top-of-book spread for BTC/EUR** — cite the mean, or the effective spread at size.

## D2 — No session term

Mean effective spread at €1k across UTC sessions (Asia 00–07 / EU 07–15 / US 15–24) varies by **1.02×–1.08×** for every pair tested. That is inside the noise of the thing being modelled; a session term would be false precision. **One constant per pair per size.**

## D3 — Size grid, and what happens between the pinned notionals

The panel pins three notionals (€100 / €1k / €10k). Cost is monotone and strongly convex in size for thin pairs (DOT: 3.68 → 5.55 → 12.41 bps). The helper therefore **interpolates linearly in log-notional between pinned points and refuses to extrapolate** above €10k — an unbounded extrapolation on a convex curve understates cost exactly where it matters most, and refusing is the honest failure. Below €100 it clamps to the €100 value (the top-of-book cost floor).

## D4 — Round-trip composition

`round_trip_cost()` returns fee + spread + margin carry on one notional, each leg's spread charged **once per side** (open and close both cross). Margin carry stays opt-in (spot has none). The spread term is *additive to*, never a substitute for, the fee term — at tier 1 fees are 40–80 bps/side against 0.6–12.4 bps of spread, so a helper that silently replaced one with the other would be off by an order of magnitude.

## D5 — The table is committed as data, with its provenance

The calibrated per-pair constants live in `cli/costs/spread.py` as a literal table carrying the window, row count and generation date, mirrored into `docs/reference/kraken-fee-schedule.md`'s sibling reference. Recalibration is a deliberate edit with a new window stamp, not a silent drift — same discipline as `SPOT_FEE_TIERS`.

## Calibrated table (mean effective spread, bps per side, mid-relative)

| pair | @€100 | @€1k | @€10k |
|---|---|---|---|
| BTC | 0.266 | 0.392 | 0.635 |
| ETH | 0.425 | 0.494 | 0.698 |
| XRP | 0.768 | 1.121 | 2.076 |
| SOL | 0.925 | 1.034 | 1.834 |
| DOGE | 1.707 | 1.839 | 3.724 |
| LINK | 2.102 | 2.275 | 3.677 |
| LTC | 2.035 | 3.028 | 5.245 |
| ADA | 2.174 | 2.452 | 5.324 |
| AVAX | 2.438 | 2.886 | 5.916 |
| DOT | 3.684 | 5.545 | 12.412 |

## Instrument checks performed before any of the above counted

- **The 5× BTC discrepancy against the catalog's 2026-07-15 first-look (0.18 vs 0.036) was chased before use**, not explained away: it is the D1 bimodality, and the catalog's figure is a median over a shorter window that straddled the 1-tick crossing differently. Both numbers are correct; the statistic is the problem.
- **T0071's falsification probe was run** (it predicted no discontinuity in a depth-sensitive metric across the 2026-07-14 04:00 capture-fix boundary): `fill_bps@10k` moved −13 %…+1 % across seven pairs, **scattered in both directions**. A data artifact would move every pair the same way. The map's soundness conclusion survives a test that could have refuted it.
- Row counts agree to within 5 rows across all ten pairs (1,123,509–1,123,514), i.e. the panel grid is complete and the pairs are jointly sampled — no pair-specific gap silently narrowing one column.

## Out of scope

- Market impact beyond the visible book, queue position, and maker-fill probability: the panel measures the *visible* cost of crossing, which is the term that was missing. A maker-first strategy pays less than this and a size beyond €10k pays more (D3 refuses rather than guess).
- Depth beyond rank 10 is venue-unverified in every era (the map's standing caveat). `fill_bps@10k` walks past rank 10 on the thin pairs, so those figures rest on protocol congruence rather than on venue checksums — stated once, here.
