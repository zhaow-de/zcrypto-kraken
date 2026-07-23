# Captured-spread calibration

The per-pair spread constants the cost model charges, calibrated from **our own L2 capture** rather than a vendor quote (T0014, spec [`00066`](../specs/00066-captured-spread-cost-calibration-design.md)). The live table is `cli/costs/spread.py`; this document is its provenance and its reading instructions.

## The table — mean effective spread, **bps per side**, mid-relative

| pair | @€100 | @€1k | @€10k |
|---|---|---|---|
| BTC | 0.260 | 0.386 | 0.625 |
| ETH | 0.420 | 0.486 | 0.686 |
| XRP | 0.758 | 1.116 | 2.071 |
| SOL | 0.922 | 1.029 | 1.822 |
| DOGE | 1.721 | 1.853 | 3.741 |
| LINK | 2.207 | 2.367 | 3.704 |
| LTC | 2.036 | 3.022 | 5.237 |
| ADA | 2.180 | 2.459 | 5.365 |
| AVAX | 2.408 | 2.858 | 5.863 |
| DOT | 3.579 | 5.405 | 12.223 |

Between pinned sizes the helper interpolates **linearly in log notional**; above €10k it **refuses** rather than extrapolating a convex curve; below €100 it clamps.

## Provenance

- **Source:** `l2-panel` (spec `00052`), the 1-second L2 primitive panel, read over the NAS NFS mount.
- **Window:** `2026-07-08T13:47:33Z … 2026-07-23T05:59:59Z` — **353 hourly files per pair**, 1,260,309–1,260,314 rows per pair (~12.6 M total). *(Restamped 2026-07-23 by [T0091](../open-topics/archive/T0091-spread-calibration-two-week-restamp.md); the predecessor stamp was 315 files / 13.1 days, reported by spec `00066`.)* Row counts agree to within 5 rows across all ten pairs, so the pairs are **jointly sampled** — the same gaps in all ten. That is not completeness: the window spans 1,267,946 s, so ~7,637 s (**0.602 %**) are absent in 6 shared gaps (three of 32–55 min on 2026-07-08, three shorter). A row-count check cannot see shared gaps; see the catalog's honest-gaps caveat.
- **Span is 14.68 days — Phase 2's exit-bar row ("≥2 weeks of captured spreads") is DISCHARGED** (2026-07-23, T0091; the predecessor 13.1-day window did not). The panel trails live capture by the ~7 h settle watermark (T0066), so the 336th hour landed about a day after the first calibration ran. **Uncertainty:** the 1.1 M rows are 1-second samples whose independent unit is roughly the day, so each constant carries a **day-level standard error of 1–6 %** (BTC 5.7 %); BTC and ETH trend downward through the window, and dropping the two earliest days alone moves BTC's constant ≈ −8 %. This is a 13.1-day **benign-regime** estimate — the window sits at the 0th–9.7th percentile of each pair's historical volatility — not a converged parameter.
- **The input was invariant-checked, not assumed.** `fill_bps` is produced by `cli/panel/materialize.py`'s book walk, which this calibration inherits wholesale. Three structural truths of a book walk hold on **100 %** of rows (BTC/DOT/XRP, ~1.26 M each): a fill at any size costs at least the half-spread; cost is non-decreasing in size (€100 ≤ €1k ≤ €10k); and every fill is positive. A materializer arithmetic bug would break at least one.
- **Era coverage:** the full window, per the [capture-era data-hygiene map](capture-era-data-hygiene-map.md) — the desync-era archive was never contaminated, so no era is excluded.
- **Nulls:** exactly 2 across 10 pairs × 3 sizes × 2 sides — XRP `fill_bps_ask_10k` at 2026-07-13 07:04:31–32Z, where `spread_bps` is 8.99 against a 1.19 window mean. The visible book covered €10k effectively always; those 2 rows drop out of XRP's @10k mean.

## Two things to know before you quote a spread number

**1. Never quote a *median top-of-book* spread for BTC/EUR.** BTC/EUR is tick-quantised at €0.10 and sits at exactly one tick 42–58 % of the seconds on complete UTC days. Because that fraction straddles 50 %, the median flips ~15× (0.29 bps → 0.018 bps around 2026-07-13) on a modest change in the one-tick share, while the distribution barely moves.

| | BTC | every other pair |
|---|---|---|
| `spread_bps` mean ÷ median | **20.7×** | 0.9–1.3× |

*(That ratio was **11.2×** on the 13.1-day window and is 20.7× on the 14.68-day one — the mean barely moved, so the swing is the **median** moving again, which is precisely this section's point rather than a contradiction of it. The `fill_bps` figures below moved by under 2 % over the same restamp.)*

(One-tick share: 42–58 % of the seconds on complete UTC days; 41.4 % including the two partial edge days, 49.5 % pooled.)

This is why the table is built from the **effective spread at size** (`fill_bps`), which shows no such instability (BTC p50 0.340 vs mean 0.386 at €1k) — walking the book averages over the quantisation, and it is also the quantity actually paid. A 5× disagreement between this table and `data-catalog-full.md`'s 2026-07-15 first-look BTC figure (0.18) is this effect, not an error in either: both are correct medians over windows that straddled the crossing differently — verified by recomputing on the catalog's own 174-hour window, which reproduces its published figures to ≤0.5 % on all ten pairs.

**2. There is no session term — on materiality, not absence.** Mean effective spread at €1k across UTC sessions (Asia 00–07 / EU 07–15 / US 15–24) varies by **1.01×–1.10× across all ten pairs** (widest LTC 1.098×; re-measured on the 14.68-day window 2026-07-23: **1.01×–1.10×, widest LTC 1.099×** — the same pair and effectively the same figure). A ≤10 % modulation of a 2–4 bps term against a 40–80 bps fee does not earn a per-session dimension. Note a paired day-level test *does* detect a consistently-signed Asia-wider effect (t = −1.9…−2.3 on BTC/ETH/LTC; 7/10 pairs), so "inside the noise" would be the wrong reason to give — and **top-of-hour seconds are measurably ~1.2× wider**, decaying to the mean by ~second 50, which matters to a 6b executor firing taker inside the first minute of a bar boundary (over the ratified 15–30 min execution window it washes out to ×1.010).

## Caveats

- **Ranks beyond 10 are venue-unverified in every era** (the hygiene map's standing caveat). At €10k the fill walk passes rank 10 on the thin pairs, so those figures rest on protocol congruence rather than on Kraken's own checksums. The €100 and €1k columns sit inside the CRC-verified window for most pairs.
- **This is the *visible* cost of crossing.** Market impact beyond the visible book, queue position, and maker-fill probability are out of scope: a maker-first strategy pays less than this, and a size beyond €10k pays more (which is why the helper refuses rather than guessing).
- **Fees still dominate at low tiers.** At tier 1 (maker 0.40 % / taker 0.80 % per side) the fee term is 40–80 bps against 0.6–12.4 bps of spread **at €10k** (0.27–3.68 bps at €100). The spread term is additive to the fee term and never a substitute for it.

## Recalibrating

Change `SPREAD_CALIBRATION` **and** `CALIBRATION_WINDOW` / `CALIBRATION_HOURS` / `CALIBRATION_MIN_ROWS` in `cli/costs/spread.py` together, then restamp this document. `tests/test_costs_spread.py` pins both the values and the provenance, so a table edited without a new window stamp fails rather than silently repricing every historical verdict.

The query is a `pl.scan_parquet` over `l2-panel/<BASE>/EUR/panel-1s/**/*.parquet` taking the **mean** of `(fill_bps_bid_<size> + fill_bps_ask_<size>) / 2` per pair. Run the two instrument checks with it: the mean÷median ratio per pair (to catch a new pair sitting on a tick-quantisation crossing), and the session spread (to confirm a session term is still unwarranted).
