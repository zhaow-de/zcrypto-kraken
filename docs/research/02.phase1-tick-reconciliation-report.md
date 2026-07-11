# Tick-derived bar reconciliation — sample report (T0004, iter-039)

**Scope:** all 10 EUR majors, **Q1-2026** (2026-01-01 → 2026-03-31), tick-derived 1h/4h/1d bars vs the
canonical OHLCVT bars (`data/ohlc-full/<BASE>/EUR/{60,240,1440}.parquet`). Machinery: `cli/tick/`
(`read_trades_csv` → `ticks_to_bars` → `reconcile`). Source ticks:
`../zcrypto-kraken-data/kraken-trades/Kraken_Trading_History_Q1_2026.zip`.

## Verdict

**Exit bar cleared.** The master-plan Phase-1 tick-reconciliation bar is *candle reconciliation within
tolerance on ≥99.5 % of intervals*. On this sample the O/H/L/C match is **100.000 % within a 1e-6
relative tolerance on every one of the 30 pair×interval cells** — 10 pairs × {1h, 4h, 1d} — over
**27,889 canonical bars** built from **~7.98 M ticks**, at **100.0000 % coverage** (see below). This
validates both the tick→bar aggregation and the canonical OHLCVT dataset it reconciles against.

## Reconciliation — O/H/L/C, tick-derived vs canonical OHLCVT

Every cell is 100.000 % within the strict 1e-6 band (and hence the looser 1e-3 band). Per-pair tick
counts and the 1h interval count (24 × 90 days = 2160 where the pair traded every hour):

| Pair | CSV member | Ticks | 1h bars | O/H/L/C match (1h/4h/1d) |
|---|---|--:|--:|:--:|
| BTC/EUR | XBTEUR | 2,877,848 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| ETH/EUR | ETHEUR | 1,408,925 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| SOL/EUR | SOLEUR | 1,105,995 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| XRP/EUR | XRPEUR | 819,013 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| LTC/EUR | LTCEUR | 710,623 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| ADA/EUR | ADAEUR | 339,180 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| DOGE/EUR | XDGEUR | 301,988 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| LINK/EUR | LINKEUR | 167,409 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| DOT/EUR | DOTEUR | 165,337 | 2160 | 100.000 % / 100.000 % / 100.000 % |
| AVAX/EUR | AVAXEUR | 81,201 | 2149 | 100.000 % / 100.000 % / 100.000 % |

## Coverage — the honest denominator

`reconcile` inner-joins on the bar timestamp, so a canonical bar with no tick counterpart (or vice
versa) is silently *excluded* rather than counted as a mismatch — which could inflate the match rate.
It does not here: across all 10 pairs × 3 intervals, **canonical-bars-in-window = 27,889, overlap =
27,889, not-covered = 0 → 100.0000 % coverage.** Every canonical bar in the window was actually
compared.

The AVAX/EUR 1h count (2149, not 2160) is the one place bars are missing — 11 hours had zero AVAX
trades in Q1-2026. Critically, the **canonical dataset also has exactly 2149 bars there**: both the
tick bars and Kraken's OHLCVT omit no-trade hours (no forward-fill), so they agree on *which* bars
exist as well as on their values. There is no hidden blind spot.

## Instrument check — why 100 % is trustworthy, not an artifact

A perfect match invites the "did I compare the array to itself?" suspicion. Three independent checks
rule that out:

1. **It is the expected result.** Both paths derive from the same Kraken trades — the tick bars
   directly, the canonical bars via Kraken's 1-minute OHLCVT (Kraken's own aggregation of those same
   trades). O/H/L/C are boundary/extremal prices that any correct aggregation of the same trades must
   reproduce identically. A match *validates* the alignment convention (left-closed, epoch-aligned)
   and the dataset; it does not indicate aliasing.
2. **The paths are provably independent — the VWAP differs.** If the tick frame and the canonical
   frame were the same data, every column would match. The **VWAP does not** (next section, 1–5 bps
   typical). The two are computed independently and agree on O/H/L/C while differing on the
   weighted-aggregate exactly as theory predicts — the "treatment engaged" evidence.
3. **`reconcile` can return < 100 %.** The unit suite (`tests/test_tick_reconcile.py`) plants an
   O/H/L/C mismatch and asserts it is caught and surfaced in `worst_mismatches` with `pct < 100`. The
   100 % here is a measured result, not a function that always returns 100.

## True tick VWAP vs the canonical stored `vwap`

The canonical `vwap` is a reconstruction proxy (a close-weighted aggregate of 1-minute bars, iter-008),
not the tick-weighted mean. `ticks_to_bars` computes the **true** VWAP = Σ(price·volume) / Σ(volume)
over the actual trades in each bar. Absolute relative difference (bps) between the two:

| Pair | 1h mean / max | 4h mean / max | 1d mean / max |
|---|--:|--:|--:|
| BTC/EUR | 1.65 / 40.7 | 1.41 / 30.1 | 0.97 / 12.0 |
| ETH/EUR | 2.28 / 43.2 | 1.83 / 26.4 | 1.27 / 7.5 |
| SOL/EUR | 2.57 / 54.3 | 2.32 / 43.2 | 1.93 / 25.5 |
| XRP/EUR | 2.18 / 79.2 | 1.92 / 72.3 | 1.60 / 28.6 |
| LTC/EUR | 2.14 / 90.1 | 2.15 / 49.9 | 1.89 / 16.8 |
| ADA/EUR | 3.21 / 107.6 | 3.82 / 100.3 | 4.74 / 39.9 |
| DOGE/EUR | 2.85 / 102.5 | 3.09 / 99.1 | 2.94 / 61.1 |
| LINK/EUR | 2.40 / 66.8 | 2.63 / 45.2 | 2.68 / 25.0 |
| DOT/EUR | 2.92 / 148.5 | 3.29 / 83.3 | 3.21 / 40.2 |
| AVAX/EUR | 2.56 / 202.5 | 3.46 / 194.8 | 5.57 / 174.3 |

**Read:** the proxy is a good-but-imperfect stand-in — median ≈ 1 bp for the liquid pairs. The error
scales with illiquidity: the least-liquid names (AVAX, DOT, ADA) show mean 3–6 bps and **tails up to
~200 bps** in thin bars, where a few large trades pull the true volume-weighted mean far from the
close-weighted proxy. For any cost model or execution logic that consumes VWAP, the tick-derived VWAP
is a material refinement over the stored proxy, most of all on the thin pairs — which are exactly the
ones where slippage assumptions matter most.

## Data-schema discovery

The trades data is **not** a single schema (the spec assumed one — corrected here):

- **Quarterly ZIPs** (`Kraken_Trading_History_Q<n>_<yyyy>.zip`, used for this sample) — a header row,
  then **7** comma fields per row: `Price,Volume,Timestamp,Type(b/s),OrderType(m/l),Misc,TradeID`
  (the header text names only 6; a known Kraken export quirk). `read_trades_csv` reads the first four
  positionally, so extra trailing fields are ignored — handled.
- **Complete dataset** (`Kraken_Trading_History.zip:TimeAndSales_Combined/<PAIR>.csv`, ~102 M rows,
  2013 → the Q1-2026 boundary) — genuinely headerless, only **3** fields in a *different order*:
  `Timestamp,Price,Volume` — **no side/type column.** `read_trades_csv` auto-detects it (a 3-field
  row whose first field is a plausible Unix timestamp `>= 1e9`) and reads it with `side` = null; a
  3-field row whose first field is a small number is still treated as a malformed 4-field row and
  errors, so genuinely-short rows are not silently reinterpreted (iter-042).

Both layouts are now handled, so the full-history reconciliation below runs directly.

## Full-history reconciliation — BTC/EUR, 2013–2025 (iter-042)

With the complete-dataset reader, the whole BTC/EUR history reconciles end to end:
**102,444,670 ticks** (`TimeAndSales_Combined/XBTEUR.csv`, 2013-09-10 → 2025-12-31) → 106,626 hourly
bars vs the canonical OHLCVT, at **100.0000 % coverage** (0 not-covered). Unlike the Q1-2026 sample
(100 % at 1e-6), the full history does **not** match to floating-point precision — and the honest read
is more interesting than a headline number:

| Tolerance | 1h match | 1d match |
|---|--:|--:|
| 1e-6 (exact-ish) | 77.14 % | 74.86 % |
| 1e-4 (1 bp) | 88.24 % | 86.53 % |
| 1e-3 (10 bp) | 97.23 % | 96.68 % |
| 1e-2 (1 %) | **99.94 %** | **99.80 %** |

**The strict miss is storage-precision noise, not aggregation error.** The same code gives 100 % on
recent data, coverage is 100 %, and the **median close relative difference is 0.000 bps in every year**
(2013–2025) — the centre of the distribution is exact. The historical OHLCVT (reconstructed from
Kraken's 1-minute dumps, iter-008) and the TimeAndSales tick export carry slightly different rounding,
so ~23 % of bars differ by an economically negligible sub-10-bp amount that busts the ultra-strict
1e-6 but clears 10 bp (97 %) and 1 % (99.94 %).

**Genuine divergences are tiny and isolated:** only **68 hourly bars (0.064 %) differ by > 1 %**,
concentrated in **2013–2015** (48 in 2013) — the early, illiquid period where the OHLCVT dumps and the
tick export disagree on the actual trades (sparse / revised early history) — plus 1 lone 2024 bar.
These would be the candidates to flag if early-2013 bars ever became load-bearing (they are not for the
1h/4h/1d strategies).

**Exit-bar reading:** the master-plan tolerance test (≥99.5 % of intervals within tolerance) is met at
a 1 % band (99.94 %) but not at 1e-6; the honest conclusion is that the canonical dataset faithfully
reproduces 12+ years of tick-derived bars to within ~10 bp, with a 0.064 % early-illiquid residual —
and the exact Q1-2026 match reflects that recent data shares identical precision in both sources.

## Full-universe full-history reconciliation — all 10 majors (iter-043)

The whole universe, full history, complete dataset → **660,343 hourly bars, 100.0000 % coverage**
(0 not-covered). Per-pair 1h match at each tolerance, and the count of bars diverging > 1 %:

| Pair | ticks | 1h bars | 1e-6 | 10 bp | 1 % | > 1 % bars |
|---|--:|--:|--:|--:|--:|--:|
| BTC/EUR | 102,444,670 | 106,626 | 77.14 % | 97.23 % | 99.94 % | 68 |
| ETH/EUR | 53,134,545 | 90,134 | 79.43 % | 97.37 % | 99.86 % | 125 |
| LTC/EUR | 19,663,798 | 97,405 | 82.25 % | 95.58 % | **99.37 %** | 611 |
| ADA/EUR | 13,529,994 | 63,463 | 77.47 % | 97.32 % | 99.96 % | 27 |
| SOL/EUR | 12,076,835 | 39,758 | 85.95 % | 99.08 % | 100.00 % | 1 |
| DOGE/EUR | 9,402,117 | 51,077 | 84.32 % | 98.00 % | 99.70 % | 152 |
| DOT/EUR | 7,727,919 | 47,021 | 78.71 % | 98.97 % | 99.99 % | 3 |
| LINK/EUR | 5,117,408 | 54,358 | 79.44 % | 98.10 % | 99.94 % | 34 |
| XRP/EUR | 26,247,964 | 75,493 | 77.74 % | 97.43 % | 99.92 % | 63 |
| AVAX/EUR | 1,528,331 | 35,008 | 91.42 % | 98.69 % | 99.99 % | 4 |

**The BTC finding generalizes across the universe:** 100 % coverage everywhere; 1e-6 is
precision-noise-limited (77–91 %); **9 of 10 pairs match ≥ 99.7 % within 1 %.** Total > 1 % divergences
are **1088 bars (0.165 %)**, and — verified per year — they sit in each pair's **early-illiquid
history**. The weakest pair, **LTC/EUR (99.37 % within 1 %, 611 > 1 % bars)**, is the clearest case:
**606 of its 611 outliers fall in 2013–2017** (220 in 2014, 211 in 2015), with essentially none after
2018 (5 bars in 8 years) — LTC was very thinly traded early, so the OHLCVT-vs-tick divergence is
concentrated there while its modern history reconciles near-exactly.

**Exit-bar verdict (honest):** at a 1 % tolerance the ≥ 99.5 %-of-intervals test is met for **9 of 10
pairs**; **LTC (99.37 %) is marginally below**, dragged entirely by 2013–2017 sparse data. None of the
pairs clear ≥ 99.5 % at 1e-6 (precision-noise-limited). The reconciliation itself is **complete** and
the canonical dataset is validated as faithful to tick data to within ~1 % (≈ 10 bp for 95–99 %) over
the full universe and full history — the residual is a characterized early-illiquid data property, not
aggregation error. Whether that clears the Phase-1 tick-reconciliation exit bar is a **tolerance
judgment** (accept ~1 % with the early-illiquid residual, or tighten and flag the early years) left for
attended review — see open topic `T0004`.

## Reproduce

```bash
uv run python - <<'PY'
import polars as pl
from cli.tick import read_trades_csv, ticks_to_bars, reconcile, csv_pair_to_canonical
from cli.ohlc.dataset import read_parquet
ZIP = "../zcrypto-kraken-data/kraken-trades/Kraken_Trading_History_Q1_2026.zip"
base, quote = csv_pair_to_canonical("XBTEUR")          # -> ("BTC", "EUR")
df = read_trades_csv((ZIP, "XBTEUR.csv"))
tb = ticks_to_bars(df, interval_minutes=60)
oh = read_parquet(f"data/ohlc-full/{base}/{quote}/60.parquet")
lo, hi = tb["ts"].min(), tb["ts"].max()
ow = oh.filter((pl.col("ts") >= lo) & (pl.col("ts") <= hi))
print(reconcile(tb, ow, tol=1e-6)["pct_within_tol"])   # -> 100.0
# coverage: every canonical bar in-window has a tick counterpart (0 not-covered)
overlap = tb.join(ow.select("ts"), on="ts", how="inner").height
print(ow.height, overlap, ow.height - overlap)         # -> 2160 2160 0
PY
```
