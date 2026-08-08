# Captured-spread calibration

The per-pair spread constants the cost model charges, calibrated from **our own L2 capture** rather than a vendor quote (T0014, spec [`00066`](../specs/00066-captured-spread-cost-calibration-design.md)). The live table is `cli/costs/spread.py`; this document is its provenance and its reading instructions.

## The table — mean effective spread, **bps per side**, mid-relative

Keyed by **full symbol**, not base: a base-keyed table returns the EUR row for `ETH` while raising for `ETH/BTC`, so its failure mode was a silently wrong value.

The rung labels stay **EUR** on every row. On a BTC-quoted pair the rung is the BTC quantity worth that many EUR at the pinned FX reference `BTC_EUR_REFERENCE = 55876.28413495087` (`cli/panel/primitives.py`), so `@€1k` names the same grid point everywhere and the values stay comparable across quotes. That reference is pinned to **its own** fixed window and must not be moved to match a recalibration — it defines what every BTC `fill_bps_*` column already in the panel tree means.

| pair | @€100 | @€1k | @€10k |
|---|---|---|---|
| BTC/EUR | 0.198 | 0.299 | 0.533 |
| ETH/EUR | 0.344 | 0.404 | 0.619 |
| XRP/EUR | 0.603 | 0.945 | 1.924 |
| SOL/EUR | 0.927 | 1.041 | 1.798 |
| DOGE/EUR | 1.635 | 1.787 | 3.539 |
| LINK/EUR | 2.382 | 2.555 | 4.021 |
| LTC/EUR | 2.103 | 2.908 | 5.124 |
| ADA/EUR | 2.383 | 2.686 | 5.389 |
| AVAX/EUR | 2.417 | 2.838 | 6.031 |
| DOT/EUR | 2.812 | 4.053 | 10.054 |
| ETH/BTC | 0.748 | 1.112 | 1.564 |
| SOL/BTC | 1.343 | 1.685 | 2.757 |

Between pinned sizes the helper interpolates **linearly in log notional**; above €10k it **refuses** rather than extrapolating a convex curve; below €100 it clamps.

## Provenance

- **Source:** `l2-panel` (spec `00052`), the 1-second L2 primitive panel, read over the NAS NFS mount.
- **Window:** `2026-07-23T14:00:00Z … 2026-08-07T19:00:00Z` — **365 hourly files per pair**, **1,314,000 rows per pair exactly** (15.8 M total across twelve). *(Restamped 2026-08-08 by spec `00085`, onto ONE window shared by all twelve rows so the two BTC-quoted legs carry the same provenance as the ten EUR ones. The predecessors: 353 files / 14.68 days over `2026-07-08T13:47:33Z … 2026-07-23T05:59:59Z`, restamped 2026-07-23 by [T0091](../open-topics/archive/T0091-spread-calibration-two-week-restamp.md); before that 315 files / 13.1 days, spec `00066`.)* **Coverage is exact, not merely joint:** `min_rows == max_rows == 365 × 3600`, so every pair carries every second of the window and the spread between pairs is **0** — a strict improvement on the superseded window, where the pairs were jointly sampled but ~7,637 s (**0.602 %**) were absent in 6 shared gaps. Reproduce with `cli/costs/calibrate.py` against the **pulled** copy at `/mnt/zhao-crypto/l2-panel`, never the live ops-side tree.
- **Span is 15.21 days — Phase 2's exit-bar row ("≥2 weeks of captured spreads") stays DISCHARGED** (first discharged 2026-07-23 at 14.68 days by T0091; a 13.1-day predecessor did not). **The window end is chosen against this bar, not for convenience:** the 13.67-day window first drafted for the 2026-08-08 restamp would have un-discharged it, and nothing in the test suite checks span, so that regression would have shipped green. The panel trails live capture by the ~7 h settle watermark (T0066), so the 336th hour landed about a day after the first calibration ran. **Uncertainty:** the 1,314,000 rows per pair are 1-second samples whose independent unit is roughly the day, so each constant carries a **day-level standard error of 1–6 %** (BTC 5.7 %); BTC and ETH trend downward through the window, and dropping the two earliest days alone moves BTC's constant ≈ −8 %. That uncertainty was quantified on the 13.1-day window and has not been re-derived here; treat it as the standing order of magnitude. This remains a **benign-regime** estimate — the window sits at the 0th–9.7th percentile of each pair's historical volatility — not a converged parameter.
- **The input was invariant-checked, not assumed.** `fill_bps` is produced by `cli/panel/materialize.py`'s book walk, which this calibration inherits wholesale. Three structural truths of a book walk hold on **100 %** of rows (BTC/DOT/XRP, ~1.26 M each): a fill at any size costs at least the half-spread; cost is non-decreasing in size (€100 ≤ €1k ≤ €10k); and every fill is positive. A materializer arithmetic bug would break at least one.
- **Era coverage:** the full window, per the [capture-era data-hygiene map](capture-era-data-hygiene-map.md) — the desync-era archive was never contaminated, so no era is excluded.
- **Nulls (measured on the SUPERSEDED window, not re-measured for the 2026-08-08 restamp):** exactly 2 across 10 pairs × 3 sizes × 2 sides — XRP `fill_bps_ask_10k` at 2026-07-13 07:04:31–32Z, where `spread_bps` is 8.99 against a 1.19 window mean. The visible book covered €10k effectively always; those 2 rows drop out of XRP's @10k mean.

## Two things to know before you quote a spread number

**1. Never quote a *median top-of-book* spread for BTC/EUR.** BTC/EUR is tick-quantised at €0.10 and sits at exactly one tick 42–58 % of the seconds on complete UTC days. Because that fraction straddles 50 %, the median flips ~15× (0.29 bps → 0.018 bps around 2026-07-13) on a modest change in the one-tick share, while the distribution barely moves.

| | BTC | every other pair |
|---|---|---|
| `spread_bps` mean ÷ median | **14.14×** | 0.92–1.37× |

*(Re-measured 2026-08-08 on the committed window: **14.14×**, from 11.2× on the 13.1-day window and 20.7× on the 14.68-day one. The mean barely moves across all three; the swing is the **median** moving, which is precisely this section's point rather than a contradiction of it. The widest "every other pair" values are now LTC/EUR 1.37× and SOL/BTC 1.27×. **The `fill_bps` table below did NOT move by under 2 % this time** — 9 of the 10 EUR rows moved by more than 2 %, worst −25.01 % (DOT @1k); see the window bullet above and spec `00085` D4.)*

(One-tick share: 42–58 % of the seconds on complete UTC days; 41.4 % including the two partial edge days, 49.5 % pooled.)

This is why the table is built from the **effective spread at size** (`fill_bps`), which shows no such instability (on the superseded window BTC read p50 0.340 vs mean 0.386 at €1k; the committed window's BTC/EUR @1k mean is 0.299) — walking the book averages over the quantisation, and it is also the quantity actually paid. A 5× disagreement between this table and `data-catalog-full.md`'s 2026-07-15 first-look BTC figure (0.18) is this effect, not an error in either: both are correct medians over windows that straddled the crossing differently — verified by recomputing on the catalog's own 174-hour window, which reproduces its published figures to ≤0.5 % on all ten pairs.

**2. There is no session term — on materiality, not absence.** *(Measured on the superseded window and its predecessor; not re-measured for the 2026-08-08 restamp, so read the ratios as the standing finding rather than as figures for the current window.)* Mean effective spread at €1k across UTC sessions (Asia 00–07 / EU 07–15 / US 15–24) varies by **1.01×–1.10× across all ten pairs** (widest LTC 1.098×; re-measured on the 14.68-day window 2026-07-23: **1.01×–1.10×, widest LTC 1.099×** — the same pair and effectively the same figure). A ≤10 % modulation of a 2–4 bps term against a 40–80 bps fee does not earn a per-session dimension. Note a paired day-level test *does* detect a consistently-signed Asia-wider effect (t = −1.9…−2.3 on BTC/ETH/LTC; 7/10 pairs), so "inside the noise" would be the wrong reason to give — and **top-of-hour seconds are measurably ~1.2× wider**, decaying to the mean by ~second 50, which matters to a 6b executor firing taker inside the first minute of a bar boundary (over the ratified 15–30 min execution window it washes out to ×1.010).

## Caveats

- **A 17-minute frozen-book interval is inside this window and is NOT excluded from the means.** Kraken's first observed venue maintenance, 2026-08-06 07:01–07:18Z: the venue emitted nothing, neither capture daemon restarted, and no archive gap was booked — so the panel's 1 s grid carries those seconds computed off a **frozen** book rather than showing a hole. Same shared-gap class as the superseded window's 0.602 %, but far smaller: ~1,020 s is **0.078 %** of this window's 1,314,000 s. It is disclosed rather than trimmed because the alternative — ending the window before it — costs the ≥2-week exit bar (spec `00085` D4). Do not "clean this up" by shortening the window.
- **Ranks beyond 10 are venue-unverified in every era** (the hygiene map's standing caveat). At €10k the fill walk passes rank 10 on the thin pairs, so those figures rest on protocol congruence rather than on Kraken's own checksums. The €100 and €1k columns sit inside the CRC-verified window for most pairs.
- **This is the *visible* cost of crossing.** Market impact beyond the visible book, queue position, and maker-fill probability are out of scope: a maker-first strategy pays less than this, and a size beyond €10k pays more (which is why the helper refuses rather than guessing).
- **Fees still dominate at low tiers.** At tier 1 (maker 0.40 % / taker 0.80 % per side) the fee term is 40–80 bps against 0.6–12.4 bps of spread **at €10k** (0.27–3.68 bps at €100). The spread term is additive to the fee term and never a substitute for it.

## Recalibrating

Change `SPREAD_CALIBRATION` **and** `CALIBRATION_WINDOW` / `CALIBRATION_HOURS` / `CALIBRATION_MIN_ROWS` in `cli/costs/spread.py` together, then restamp this document. `tests/test_costs_spread.py` pins both the values and the provenance, so a table edited without a new window stamp fails rather than silently repricing every historical verdict.

**Do not hand-roll the query — run `cli/costs/calibrate.py`**, which is the provenance of record (spec `00085` D5) and is pinned by a test that reproduces the superseded table over the superseded window. It scans **every quote**, `l2-panel/*/*/panel-1s/**/*.parquet`, taking the **mean** of `(fill_bps_bid_<size> + fill_bps_ask_<size>) / 2` per pair. The `<BASE>/EUR/**` glob this line used to carry was the pre-`00085` EUR-only scope and would now silently drop both `/BTC` legs. Run the two instrument checks with it: the mean÷median ratio per pair (to catch a new pair sitting on a tick-quantisation crossing), and the session spread (to confirm a session term is still unwarranted).
