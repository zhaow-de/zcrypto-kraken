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
  2013 → the Q1-2026 boundary) — genuinely headerless, but only **3** fields in a *different order*:
  `Timestamp,Price,Volume` — **no side/type column.** `read_trades_csv` raises a clean `TickError`
  (not a silent misparse) if pointed at it, since it requests 4 columns from a 3-field file.

This pass reconciles the quarterly format (the recent window the exit bar cares about). The
full-history batch over the complete dataset needs a second recognized schema in `read_trades_csv`
(the 3-column `ts,price,volume` layout; `side` is unused by the O/H/L/C/VWAP math, so it is a
low-risk, mechanical extension) — tracked as the remainder of open topic `T0004`.

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
