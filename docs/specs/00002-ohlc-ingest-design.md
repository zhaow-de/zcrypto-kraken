# OHLC Ingestion → Canonical Parquet — Design (Phase 1 · v0)

**Iteration:** iter-004 · **Phase:** 1 (Data Foundation) · **Status:** design approved (unattended loop)
**Master plan refs:** §Phase 1 (ingest OHLCVT → canonical Parquet), §6 (frequency architecture: 1d/4h/1h decision cadence), §8 (immutable, hash-versioned datasets — "backtests reference dataset hashes, never latest").

## Problem & context

Phase 1 needs the primary research dataset: per-pair OHLC bars in a canonical, typed, hash-versioned columnar store. This iteration builds the **ingestion pipeline** and the canonical **Parquet** layout, seeded from Kraken's **public REST `OHLC`** endpoint (no key). REST caps at ~720 candles/interval (~2y daily; probed) — enough to build and validate the pipeline; full-history backfill from the ZIP archive is parked (open-topic **T0001**), and this pipeline is what that backfill later feeds.

## Goals

- `cli/ohlc/` — a fetch → normalize → write pipeline producing canonical Parquet + a content-hashed manifest, TDD on fixtures (no live-network tests).
- A generated v0 dataset for the candidate basket at the decision-cadence intervals, with a committed catalog (pairs/intervals/rows/span/hashes).

## Non-goals (this iteration)

- No full-history ZIP ingestion (→ T0001). No tick data, no bar-from-tick reconstruction, no Binance-Vision cross-check (later Phase 1 iterations). No 1m/5m intervals in v0 (bound the fetch to the decision cadence). No capture daemon (needs the VPS, human-gated).

## Design

**Module `cli/ohlc/` (adds `polars` — with it `pyarrow` — as the first research-core data dep), stdlib + polars:**

- `errors.py` — `OHLCError(Exception)`.
- `fetch.py` — `fetch_ohlc(pair_key: str, interval: int, *, opener=urllib.request.urlopen) -> list[list]`: GET `https://api.kraken.com/0/public/OHLC?pair={pair_key}&interval={interval}`, raise `OHLCError` on a non-empty Kraken `error` array / transport / JSON error, return the candle rows (the series under the non-`last` result key). `opener` is injectable for tests.
- `dataset.py` — pure transforms:
  - `to_frame(rows: list[list]) -> pl.DataFrame` with an explicit schema: `ts` (`Datetime("us","UTC")` from the epoch-seconds col 0), `open/high/low/close/vwap/volume` (`Float64`, parsed from Kraken's string decimals), `count` (`Int64`). Sorted by `ts`, de-duplicated, rejects non-monotonic/NaN via a validation that raises `OHLCError`.
  - `write_parquet(frame, path)` / `read_parquet(path)`.
  - `dataset_hash(frame) -> str`: sha256 over a canonical serialization (e.g. the frame's stable CSV/IPC bytes) — deterministic, so a dataset is referenced by hash (§8).
- `ingest.py` — `ingest_basket(pair_keys: dict[str,str], intervals: list[int], out_dir: Path, fetched_at: str, *, fetch_fn=fetch_ohlc) -> dict`: for each `(display_symbol -> kraken_pair_key)` × interval, fetch → `to_frame` → write `out_dir/{symbol}/{interval}.parquet`; return a **manifest** dict (per series: symbol, interval, rows, first_ts, last_ts, dataset_hash; plus `fetched_at`). `fetched_at`/`fetch_fn` injected for testability. Pair-key resolution reuses `cli.snapshot` (derive the Kraken pair key per candidate symbol from a live `AssetPairs`), so the two reference-data modules stay consistent.
- `__init__.py` — re-exports + `DEFAULT_INTERVALS = [1440, 240, 60]` (1d / 4h / 1h — the §6 decision cadence).

**Storage:** `data/ohlc/` (gitignored) holds the Parquet tree + `manifest.json`. The committed artifact is `docs/data-catalog.md` (NOT a research report → not on the mdformat allowlist; hand-formatted): the dataset's pairs/intervals/rows/span/hashes/fetched_at, so the dataset is reproducible-by-hash without committing the (large, changing) Parquet.

## Testing

`tests/test_ohlc_*.py` on saved fixtures (a trimmed real `OHLC` response) + monkeypatched opener:
- `fetch_ohlc` raises `OHLCError` on a non-empty `error` array; returns rows on success; picks the series key (ignores `last`).
- `to_frame` yields the exact schema/dtypes; parses string decimals to Float64; sorts + dedupes; raises on a NaN/non-monotonic row.
- `write_parquet`→`read_parquet` round-trips identically; `dataset_hash` is deterministic and changes when a value changes.
- `ingest_basket` (fixture `fetch_fn`) writes the expected tree and returns a manifest with correct rows/hashes; deterministic given fixed `fetched_at`.

## Deferred / parked

- Full-history ZIP backfill → **T0001**. Tick history, bar-from-tick reconstruction, Binance-Vision cross-check, 1m/5m, the capture daemon → later Phase-1 iterations / human-gated infra.

## Closeout (planned)

On merge: generate the live v0 dataset + `docs/data-catalog.md`; append the `iter-004` iterations-history entry.
