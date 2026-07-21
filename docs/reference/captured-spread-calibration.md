# Captured-spread calibration

The per-pair spread constants the cost model charges, calibrated from **our own L2 capture** rather than a vendor quote (T0014, spec [`00066`](../specs/00066-captured-spread-cost-calibration-design.md)). The live table is `cli/costs/spread.py`; this document is its provenance and its reading instructions.

## The table — mean effective spread, **bps per side**, mid-relative

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

Between pinned sizes the helper interpolates **linearly in log notional**; above €10k it **refuses** rather than extrapolating a convex curve; below €100 it clamps.

## Provenance

- **Source:** `l2-panel` (spec `00052`), the 1-second L2 primitive panel, read over the NAS NFS mount.
- **Window:** `2026-07-08T13:47:33Z … 2026-07-21T15:59:59Z` — **315 hourly files per pair**, 1,123,509–1,123,514 rows per pair (~11.2 M total). Row counts agree to within 5 rows across all ten pairs, so the grid is complete and the pairs are jointly sampled.
- **Span is 13.1 days, not 14.** The panel trails live capture by the ~7 h settle watermark (T0066). Recorded as measured; one marginal day cannot move a statistic over 1.1 M observations.
- **Era coverage:** the full window, per the [capture-era data-hygiene map](capture-era-data-hygiene-map.md) — the desync-era archive was never contaminated, so no era is excluded.
- **Null rate:** 0.00 % at every size for every pair, i.e. the visible book covered €10k at all times; no shallow-book exclusions.

## Two things to know before you quote a spread number

**1. Never quote a *median top-of-book* spread for BTC/EUR.** BTC/EUR is tick-quantised at €0.10 and sits at exactly one tick 42–58 % of the time. Because that fraction straddles 50 %, the median flips ~15× (0.29 bps → 0.018 bps around 2026-07-13) on a modest change in the one-tick share, while the distribution barely moves.

| | BTC | every other pair |
|---|---|---|
| `spread_bps` mean ÷ median | **11.2×** | 0.9–1.3× |

This is why the table is built from the **effective spread at size** (`fill_bps`), which shows no such instability (BTC p50 0.346 vs mean 0.392 at €1k) — walking the book averages over the quantisation, and it is also the quantity actually paid. A 5× disagreement between this table and `data-catalog-full.md`'s 2026-07-15 first-look BTC figure (0.18) is this effect, not an error in either: both are correct medians over windows that straddled the crossing differently.

**2. There is no session term.** Mean effective spread at €1k across UTC sessions (Asia 00–07 / EU 07–15 / US 15–24) varies by **1.02×–1.08×** for every pair tested — inside the noise of the thing being modelled. One constant per pair per size is the honest resolution.

## Caveats

- **Ranks beyond 10 are venue-unverified in every era** (the hygiene map's standing caveat). At €10k the fill walk passes rank 10 on the thin pairs, so those figures rest on protocol congruence rather than on Kraken's own checksums. The €100 and €1k columns sit inside the CRC-verified window for most pairs.
- **This is the *visible* cost of crossing.** Market impact beyond the visible book, queue position, and maker-fill probability are out of scope: a maker-first strategy pays less than this, and a size beyond €10k pays more (which is why the helper refuses rather than guessing).
- **Fees still dominate at low tiers.** At tier 1 (maker 0.40 % / taker 0.80 % per side) the fee term is 40–80 bps against 0.6–12.4 bps of spread. The spread term is additive to the fee term and never a substitute for it.

## Recalibrating

Change `SPREAD_CALIBRATION` **and** `CALIBRATION_WINDOW` / `CALIBRATION_HOURS` / `CALIBRATION_MIN_ROWS` in `cli/costs/spread.py` together, then restamp this document. `tests/test_costs_spread.py` pins both the values and the provenance, so a table edited without a new window stamp fails rather than silently repricing every historical verdict.

The query is a `pl.scan_parquet` over `l2-panel/<BASE>/EUR/panel-1s/**/*.parquet` taking the **mean** of `(fill_bps_bid_<size> + fill_bps_ask_<size>) / 2` per pair. Run the two instrument checks with it: the mean÷median ratio per pair (to catch a new pair sitting on a tick-quantisation crossing), and the session spread (to confirm a session term is still unwarranted).
