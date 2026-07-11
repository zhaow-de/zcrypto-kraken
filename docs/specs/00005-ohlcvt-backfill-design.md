# Full-History OHLCVT Backfill — Design (Phase 1)

**Iteration:** iter-008 · **Phase:** 1 (Data Foundation) · **Status:** design approved (unattended loop)
**Master-plan refs:** §8 (data plan), §9 (2019+ walk-forward regimes), §Phase 1. **Resolves:** open-topic **T0001** (partial → resolved).

## Problem & context

iter-004 built the OHLC ingestion pipeline seeded from Kraken's **public REST `OHLC`** endpoint, which caps at ~720 candles/interval (the v0 dataset, ~2y). §9's walk-forward validation needs the full history (2019+; BTC back to 2013). That history lives in Kraken's **downloadable OHLCVT ZIP archive**, now on the NAS (T0001 groundwork done):

- **Base dump** `Kraken_OHLCVT.zip` — CSVs under a `master_q4/` prefix (skip the parallel `__MACOSX/` tree). **1-minute bars span the pair's full listing history** (XBTEUR: 2013-09-10 → 2025-12-31, 5.5M rows), as do native 1h/1d; only native 4h (240) is short (2024+).
- **Quarterly update ZIPs** `Kraken_OHLCVT_Q<n>_<yyyy>.zip` — one quarter each, Q1-2023 → Q1-2026 (extend the base dump's right edge into 2026).
- **CSV format:** 7 columns `time,open,high,low,close,volume,trades` — **no vwap**.

Because 1-minute is full-history, we **reconstruct every canonical cadence (1h/4h/1d) from the 1-minute bars**, which yields a real (volume-weighted) vwap uniformly and full history for every cadence including 4h.

## Goals

- **`cli/backfill/`** — read the 1-minute OHLCVT rows for a pair (base dump + quarterly updates, merged + de-duped), aggregate them into canonical 1h/4h/1d bars (with a reconstructed vwap), write a **full-history dataset to a new path** (not overwriting the v0), and **reconcile** it against the v0 REST overlap. TDD on small synthetic ZIP fixtures (no reads of the 27 GB archive in tests).
- **The full-history dataset** for the 12-name universe basket × 1h/4h/1d, cataloged (`docs/reference/data-catalog-full.md`) and reconciled (`docs/research/02.phase1-ohlcvt-backfill-reconciliation.md`).

## Non-goals

- No finer cadences (1m/5m/15m) and no full-exchange breadth — universe basket + 1h/4h/1d only (deferred).
- **No overwrite of the v0 dataset** (`data/ohlc/`) — the backfill writes a **new** dataset root (`data/ohlc-full/`), per the canonical-immutability rule.
- No empty-interval reconstruction (report gaps via existing `cli.ohlc.qa`, don't fill); no Binance-Vision cross-check (follow-ups).
- No new third-party deps (stdlib `zipfile` + polars).

## Design

Reuses `cli.ohlc.dataset.to_frame` / `write_parquet` / `dataset_hash` (the canonical schema: `ts` UTC, `open/high/low/close/vwap/volume` Float64, `count` Int64) and `cli.ohlc.qa.INTERVAL_SECONDS` ({1440: 86400, 240: 14400, 60: 3600}). The reconstruction emits the same **8-field row list** (`[time, o, h, l, c, vwap, volume, count]`) `to_frame` already consumes.

**`cli/backfill/errors.py`** — `BackfillError`.

**`cli/backfill/read.py`:**
- `dump_pair_name(symbol: str) -> str` — map a canonical `"BASE/QUOTE"` symbol to the dump altname: apply the Kraken aliases BTC→`XBT`, DOGE→`XDG` to **both** legs, concatenate, drop the `/` (e.g. `BTC/EUR`→`XBTEUR`, `DOGE/EUR`→`XDGEUR`, `ETH/BTC`→`ETHXBT`, `SOL/BTC`→`SOLXBT`). (Confirmed against the base dump for all 12 universe pairs.)
- `read_minute_rows(source_dir: Path, symbol: str) -> list[list]` — locate the pair's `{altname}_1.csv` in the base dump (`Kraken_OHLCVT.zip`, entry `master_q4/{altname}_1.csv`) and in every `Kraken_OHLCVT_Q*_*.zip` (entry `{altname}_1.csv`); parse each 7-field row to `[int ts, str o, str h, str l, str c, str volume, str trades]`; concatenate, **sort by ts, drop exact-`ts` duplicates** (base/quarterly overlap → keep one; raise `BackfillError` on a same-`ts` conflict with differing OHLC). Skip `__MACOSX/` entries. Raise `BackfillError` if the pair appears in no zip or the source dir/base zip is missing.

**`cli/backfill/aggregate.py`:**
- `aggregate_minutes(minute_rows: list[list], interval_secs: int) -> list[list]` — bucket by `floor(ts / interval_secs) * interval_secs`; per bucket (in ts order): `open`=first, `high`=max, `low`=min, `close`=last, `volume`=Σ, `count`=Σ trades, `vwap`=Σ(close_i·vol_i)/Σvol_i (**reconstruction proxy**; if Σvol_i == 0, `vwap`=close). Emit 8-field rows `[bucket_ts, open, high, low, close, vwap, volume, count]` sorted ascending. No-trade buckets (no 1-minute rows) produce no bar (gaps are reported by `cli.ohlc.qa`, not filled).

**`cli/backfill/backfill.py`:**
- `backfill_pair(source_dir, symbol, intervals) -> dict[str, pl.DataFrame]` — `read_minute_rows` once, then per interval `to_frame(aggregate_minutes(rows, INTERVAL_SECONDS[iv]))`.
- `backfill_basket(source_dir, symbols, intervals, out_root, fetched_at) -> dict` — per symbol × interval, `write_parquet(frame, out_root/{base}/{quote}/{interval}.parquet)` and record `dataset_hash`; write `out_root/manifest.json` (mirroring `cli.ohlc.ingest.ingest_basket`: `{as_of/fetched_at, source, series: {symbol: {interval: {rows, first_ts, last_ts, sha256}}}, basket_sha256}`) and return it.

**`cli/backfill/reconcile.py`:**
- `reconcile_series(backfill: pl.DataFrame, rest: pl.DataFrame) -> dict` — inner-join on `ts` (the overlap window); report `{overlap_rows, ohlc_exact_match_rows, ohlc_match_rate, volume_rel_diff_max, vwap_mean_abs_rel_diff}`. OHLC/volume are expected to match closely (same Kraken source); **vwap is expected to differ** (reconstructed proxy vs REST's true vwap) — reported, not asserted.
- `reconcile_dataset(backfill_root, rest_root, intervals) -> dict` + `render_markdown(report) -> str`.

**Config:** add `ohlcvt_source_dir: Path | None` to `cli.config.AppConfig` (+ `_read_path` in `load_config`, + a `resolve_ohlcvt_source_dir` resolver mirroring `resolve_data_dir`); set `ohlcvt_source_dir = "../zcrypto-kraken-data/kraken-ohlcvt-updates"` in `zcrypto.toml`; document it in the README `[zcrypto]` block. The backfill **functions take `source_dir` as a `Path` param** (config-agnostic, testable); the one-shot generation run reads it from config.

## Testing

`tests/test_backfill_read.py`, `tests/test_backfill_aggregate.py`, `tests/test_backfill_reconcile.py` — build **tiny synthetic ZIPs** in `tmp_path` with `zipfile` (a base `Kraken_OHLCVT.zip` with `master_q4/FOO_1.csv` + a quarterly zip with `FOO_1.csv`, a handful of 1-minute rows) and synthetic frames:
- `dump_pair_name` maps all 12 universe symbols correctly (BTC→XBT, DOGE→XDG, cross legs).
- `read_minute_rows` merges base+quarterly, de-dupes overlapping ts, sorts, skips `__MACOSX/`, raises on a missing pair and on a same-ts OHLC conflict.
- `aggregate_minutes` — a known set of 1-minute bars aggregates to the right OHLC (first/max/min/last), summed volume+trades, and vwap = Σ(close·vol)/Σvol; bucket boundaries are correct (floor to interval); Σvol==0 → vwap=close; empty input → empty output.
- Round-trip: `to_frame(aggregate_minutes(...))` yields the canonical schema.
- `reconcile_series` — identical OHLCV → 100% match; a planted OHLC diff is counted; vwap diff is reported not raised; disjoint ts → 0 overlap.

## Deferred / parked

Finer cadences (1m/5m/15m) and full-exchange breadth; empty-interval reconstruction; Binance-Vision cross-check; the symbol & corporate-action ledger (e.g. DOT's 2020 1:100 redenomination lives in the DOTEUR price history — flag any such discontinuity in the reconciliation, and handle it in the ledger iteration). Pointing the universe/backtests at the new dataset hash is a follow-up (a human/Phase-2 decision), not this iteration.

## Closeout (planned)

On merge: run `backfill_basket` over the live archive → write `data/ohlc-full/` (gitignored) + `docs/reference/data-catalog-full.md`; run `reconcile_dataset` vs `data/ohlc/` → commit `docs/research/02.phase1-ohlcvt-backfill-reconciliation.md`; flip **T0001 → resolved** (archive); append the `iter-008` iterations-history entry.
