# Captured-spread cost calibration — design (T0014)

**Status:** ratified by the 2026-07-22 `/zcrypto-auto-exec` run (approval gates pre-satisfied by the invocation; every decision below is a reversible research choice, recorded here and routed by subject matter — D1–D3 to `docs/research/03.phase2-decisions.md` (cost model = Phase 2), the trial-44 re-read to `13.phase5-decisions.md`, the execution-facing fee-tier finding to `14.phase6-decisions.md`).

## Goal

Close the cost model's known-missing **spread term**. Phase-4/5 verdicts charged Kraken fees plus margin carry and assumed **zero spread**, on a basket whose thin alts are exactly where spread bites. Calibrate the term from our own captured L2, add it to `cli/costs/`, and re-read the A-family net-of-cost conclusions with it included.

## The data actually used

`/mnt/zhao-crypto/l2-panel` (spec `00052` / iter-098), read over NFS, **full window** per the [capture-era data-hygiene map](../reference/capture-era-data-hygiene-map.md) (T0071): the desync-era archive was never contaminated, so no era is excluded.

- 10 pairs × **315 hourly files**, `2026-07-08 13:47:33Z … 2026-07-21 15:59:59Z` — **1,123,509–1,123,514 one-second rows per pair** (~11.2 M total, 696 MB).
- Span is **13.1 days, not the nominal 14**: the panel trails live capture by the ~7 h settle watermark (T0066), so the 336th hour lands well after this run. This does **not** discharge Phase 2's carried-forward exit-bar row ("≥2 weeks of captured spreads") — registered as [[T0091]] for the restamp. And the shortfall is not immaterial: the 1.1 M rows are 1-second samples whose independent unit is roughly the day, so the **day-level standard error of each constant is 1–6 %** (BTC 5.7 %), with BTC/ETH trending downward through the window — dropping the two earliest days alone moves BTC's constant ≈ −8 %. Treat the table as a 13.1-day benign-regime estimate (the window sits at the 0th–9.7th volatility percentile per pair), not a converged parameter.
- `fill_bps_{bid,ask}_{100,1k,10k}` — effective spread at a EUR notional, mid-relative, one side — had exactly **2 nulls across 10 pairs × 3 sizes × 2 sides** (XRP `fill_bps_ask_10k`, 2026-07-13 07:04:31–32Z, where `spread_bps` is 8.99 against a 1.19 window mean), so the visible book covered €10k effectively always; those 2 rows drop out of XRP's @10k mean.

## D1 — Use the effective spread at size, not the top-of-book spread

**Measured, and this is the load-bearing decision.** `spread_bps` is unusable as a per-pair constant for BTC:

| | BTC | every other pair |
|---|---|---|
| `spread_bps` mean ÷ median | **11.2×** | 0.9–1.3× |

BTC/EUR is **tick-quantised at €0.10** and sits at exactly one tick 42–58 % of the seconds on complete UTC days (41.4 % including the two partial edge days; 49.5 % pooled over the window). Because that fraction straddles 50 %, the *median* flips ~15× (0.29 bps → 0.018 bps around 2026-07-13) on a modest change in the 1-tick share, while the distribution barely moves. A median-based BTC spread is therefore an artifact of where the mode sits relative to the 50th percentile — not a property of the market.

The effective spread at size has no such problem (BTC: p50 0.346 vs mean 0.392 bps at €1k), because walking the book averages over the tick quantisation. It is also the quantity we actually pay. **The model uses the mean `fill_bps` at the traded notional.**

Corollary recorded so it is not re-derived: **never quote a median top-of-book spread for BTC/EUR** — cite the mean, or the effective spread at size.

## D2 — No session term

Mean effective spread at €1k across UTC sessions (Asia 00–07 / EU 07–15 / US 15–24) varies by **1.01×–1.10× across all ten pairs** (widest LTC 1.098×). The reason to omit the dimension is **materiality, not absence**: a ≤10 % modulation of a 2–4 bps term against a 40–80 bps fee does not earn one. A paired day-level test *does* detect a consistently-signed Asia-wider effect (t = −1.9…−2.3 on BTC/ETH/LTC; 7/10 pairs), so "inside the noise" is the wrong justification. **One constant per pair per size.**

## D3 — Size grid, and what happens between the pinned notionals

The panel pins three notionals (€100 / €1k / €10k). Cost is monotone and strongly convex in size for thin pairs (DOT: 3.68 → 5.55 → 12.41 bps). The helper therefore **interpolates linearly in log-notional between pinned points and refuses to extrapolate** above €10k — an unbounded extrapolation on a convex curve understates cost exactly where it matters most, and refusing is the honest failure. Below €100 it clamps to the €100 value (the top-of-book cost floor).

## D4 — Round-trip composition

`round_trip_cost()` returns fee + spread + margin carry on one notional, each leg's spread charged **once per side** (open and close both cross). Margin carry stays opt-in (spot has none). The spread term is *additive to*, never a substitute for, the fee term — at tier 1 fees are 40–80 bps/side against 0.6–12.4 bps of spread at €10k, so a helper that silently replaced one with the other would be off by an order of magnitude.

## D5 — The table is committed as data, with its provenance

The calibrated per-pair constants live in `cli/costs/spread.py` as a literal table beside three provenance constants (`CALIBRATION_WINDOW`, `CALIBRATION_HOURS`, `CALIBRATION_MIN_ROWS`), documented in the sibling reference `docs/reference/captured-spread-calibration.md`. Recalibration is a deliberate edit with a new window stamp, not a silent drift — same discipline as `SPOT_FEE_TIERS`, and the tests pin table and provenance together so the two cannot diverge.

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

- **The 5× BTC discrepancy against the catalog's 2026-07-15 first-look (0.18 vs 0.036) was chased before use**, not explained away: it is the D1 bimodality. **Verified rather than asserted**: recomputing medians on the catalog's own 174-hour window reproduces its published figures to ≤0.5 % on all ten pairs, so both numbers are correct on their own windows and the statistic is the problem.
- **T0071's falsification probe was run and is INCONCLUSIVE — it corroborates nothing.** Across **all ten** pairs `fill_bps@10k` moved −17.2 %…+4.5 % (7/10 down) over the 2026-07-14 04:00 boundary. But the identical statistic at **seven non-event dates** gives ranges of −26.6…+17.3, −12.2…+22.2, −22.5…+8.6, −22.2…+55.2, −19.1…+51.2, −8.1…+12.1 and −24.2…+19.1, with 4–8 of 10 pairs down at every one — the real boundary is the least remarkable of the eight. **The probe has no discriminating power at this window size**, so it could not have refuted the map and does not confirm it. T0071's conclusion continues to rest on its mechanism argument alone. (An earlier draft of this spec reported a seven-pair subset spanning −13 %…+1 %, which omitted AVAX's −17.2 % — the largest and most adverse move.)
- Row counts agree to within 5 rows across all ten pairs (1,123,509–1,123,514), i.e. the pairs are **jointly sampled** — the same gaps in all ten. That is not completeness: the window spans 1,131,147 s, so ~7,635 s (**0.675 %**) are absent, in 6 shared gaps (three of 32–55 min on 2026-07-08 plus three short ones). Because the gaps are shared, a row-count check cannot see them; see the catalog's honest-gaps caveat.

## Out of scope

- Market impact beyond the visible book, queue position, and maker-fill probability: the panel measures the *visible* cost of crossing, which is the term that was missing. A maker-first strategy pays less than this and a size beyond €10k pays more (D3 refuses rather than guess).
- Depth beyond rank 10 is venue-unverified in every era (the map's standing caveat). `fill_bps@10k` walks past rank 10 on the thin pairs, so those figures rest on protocol congruence rather than on venue checksums — stated once, here.
