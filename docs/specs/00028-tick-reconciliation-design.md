# T0004 — Tick ingestion + tick-derived bar reconciliation + true VWAP — Design

**Iteration:** iter-039 · **Phase:** 1 (Data Foundation — the tick-granularity exit-bar check) · **Status:** design approved (unattended loop)
**Refs:** master-plan §12 Phase-1 loop ("pull full tick history … build bars from ticks and reconcile vs OHLCVT (tolerance test)"; exit bar "candle reconciliation within tolerance on ≥99.5% of intervals"), §6 feature families. Open topic `docs/open-topics/T0004-tick-history-reconciliation.md`.

## Problem & context

Phase 1 validated the canonical bars at **1-minute** granularity (100 % OHLC match vs REST + Binance cross-check, iter-008/012) but never at **tick** granularity. The Kraken **time-and-sales** ZIPs are now on the NAS (`../zcrypto-kraken-data/kraken-trades/`: `Kraken_Trading_History.zip` (complete) + quarterlies). This iteration builds tick ingestion → tick-derived bars **with a true (tick-weighted) VWAP** → reconciliation vs the OHLCVT-derived canonical bars.

**Data facts:** per-pair CSVs inside the ZIPs, columns `Price,Volume,Timestamp,Type[,Misc,TradeID]` (Timestamp = unix seconds with fractional; Type = `b`/`s`). The complete dataset is headerless; the quarterly incrementals carry a header row — handle both. **Kraken legacy tickers:** our 10 EUR majors map to `XBTEUR`(BTC), `ETHEUR`, `ADAEUR`, `AVAXEUR`, `XDGEUR`(DOGE), `DOTEUR`, `LINKEUR`, `LTCEUR`, `SOLEUR`, `XRPEUR`. Reconcile targets: `data/ohlc-full/<PAIR>/EUR/{60,240,1440}.parquet` (1h/4h/1d).

## Goals

New `cli/tick/` package (stdlib + polars, mirroring `cli/backfill/`):

1. **`read.py`** — read a Kraken trades CSV (path or a member of a ZIP), auto-detecting header vs headerless; return a polars DataFrame with `ts` (datetime, UTC), `price` (float), `volume` (float), `side` (`b`/`s`). Raises `TickError` on malformed input; never emits NaN.
2. **`aggregate.py`** — `ticks_to_bars(df, *, interval_minutes)` → OHLCV bars per time bucket: `open`/`high`/`low`/`close` (first/max/min/last trade price), `volume` (Σ), `count` (n trades), and **`vwap` = Σ(price·volume)/Σ(volume)** (the true tick-weighted VWAP). Left-closed buckets aligned to the epoch, matching the canonical bar convention.
3. **`reconcile.py`** — `reconcile(tick_bars, ohlcvt_bars, *, tol)` → per-interval comparison of O/H/L/C (relative tolerance `tol`, default 1e-6 exact-ish; a looser band reported too) → a report: n intervals, % within tolerance, worst mismatches. The exit-bar bar is **≥99.5 % of intervals within tolerance**.
4. **Pair-name mapping** (`XBT→BTC`, `XDG→DOGE`, else identity) so a `XBTEUR.csv` reconciles against `data/ohlc-full/BTC/EUR/`.

TDD on **synthetic tick fixtures** (known ticks → known bars + VWAP; a planted mismatch is caught). Then a **real-data sample run** (a scratchpad script) reconciling ≥1 pair over a bounded recent window (e.g. BTC/EUR Q1-2026) against the canonical bars → a committed report of the reconciliation %.

## Non-goals

No full-universe full-history batch reconciliation this pass (12.5 GB / billions of ticks — a heavy follow-up job; this pass proves the machinery + a representative sample). No 15-minute bars (no OHLCVT 15m to reconcile against; the aggregator is interval-parametric so 15m is trivial later). No tick *storage*/catalog layer (parse-on-demand from the ZIPs suffices for reconciliation); no `zcrypto` CLI subcommand this pass (a scratchpad run drives the sample) unless trivially warranted.

## Testing / done

- `cli/tick/` unit tests (synthetic): read (header + headerless + malformed), aggregate (OHLC + volume + count + true VWAP exact on hand-computed fixtures; bucket alignment), reconcile (all-match → 100 %, planted mismatch → caught + reported). `uv run pytest` green.
- **Sample real-data reconciliation** committed as `docs/tick-reconciliation-report.md`: the tick-derived 1h/4h/1d bars for the sample pair/window vs the canonical OHLCVT bars — the % of intervals within tolerance (the exit-bar metric) + an honest read (any systematic offset, e.g. Kraken's OHLCVT VWAP proxy vs the true tick VWAP).

## Closeout (planned)

Flip `docs/open-topics/T0004-tick-history-reconciliation.md` → `partial` (machinery built + sample-validated; the full-universe/full-history reconciliation batch is the remainder) or `resolved` if the sample already clears ≥99.5 %. iter-039 iterations-history entry. Engineering/data iteration — not logged in `.tmp/decisions.md`.
