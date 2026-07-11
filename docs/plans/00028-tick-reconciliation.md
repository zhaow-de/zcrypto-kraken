# T0004 Tick Reconciliation — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Spec: `docs/specs/00028-tick-reconciliation-design.md`.

**Goal:** Build `cli/tick/` (read + aggregate + reconcile) TDD, then a sample real-data reconciliation report.

## Task 1 — `cli/tick/` (TDD)
- [ ] `read.py` — parse a Kraken trades CSV (header + headerless), → polars df (ts, price, volume, side); `TickError` on malformed; no NaN.
- [ ] `aggregate.py` — `ticks_to_bars(df, *, interval_minutes)` → OHLC + volume + count + **true VWAP** (Σ price·vol / Σ vol), left-closed epoch-aligned buckets.
- [ ] `reconcile.py` — `reconcile(tick_bars, ohlcvt_bars, *, tol)` → per-interval O/H/L/C match %, worst mismatches; pair-name map (XBT→BTC, XDG→DOGE).
- [ ] Tests (synthetic): read variants, aggregate exact VWAP/OHLC/bucket, reconcile 100%/planted-mismatch. `uv run pytest` green.

## Task 2 — sample real-data reconciliation
- [ ] Scratchpad run: extract a sample pair/window (e.g. BTC/EUR = XBTEUR.csv from the Q1-2026 ZIP) → tick bars 1h/4h/1d → reconcile vs `data/ohlc-full/BTC/EUR/{60,240,1440}.parquet` → `docs/research/02.phase1-tick-reconciliation-report.md` (% within tolerance + honest read of any VWAP-proxy offset).

## Task 3 — closeout
- [ ] T0004 → partial/resolved + index; iter-039 iterations-history entry.
