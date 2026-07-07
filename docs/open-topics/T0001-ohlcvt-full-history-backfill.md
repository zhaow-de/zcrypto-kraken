---
status: open
---

# Full-history OHLCVT backfill from Kraken's downloadable ZIP archive

## Context — what

iter-004 built the OHLCVT ingestion pipeline seeded from Kraken's **public REST `OHLC`** endpoint, which caps at ~720 candles per interval (~2 years of daily bars; ~12 hours of 1m). The master plan's full research history (2019/2020→2026, incl. the LUNA/FTX-era stress, the 2024 top, and the 2025–26 bear) lives only in Kraken's **downloadable full-history OHLCVT ZIP archive** (support article 360047124832) — Google-Drive-hosted quarterly ZIPs, not the REST API.

## Why this matters

§9's walk-forward validation slices explicit regimes (2022 crash / 2023–24 bull / 2025–26 bear); a ~2-year REST window cannot span them. The v0 REST-seeded dataset is enough to build and test the pipeline, but every real backtest needs the full history. This is the binding data dependency for Phases 3–5.

## Findings so far

- REST `OHLC` returns exactly ~720 rows/interval (probed: XBT/EUR daily = 721 rows ≈ 720 days). Older data is not retrievable via REST (master plan §2).
- **Download mechanism: resolved.** The ZIPs are downloaded manually to the NAS mount `/home/zhaow/Projects/zcrypto-kraken-data/kraken-ohlcvt-updates/` (NFS cold storage, ~27 TB free). Two kinds of file are present (verified 2026-07-07):
  - **Base full-history dump `Kraken_OHLCVT.zip`** — 7.9 GB; ~12,028 CSVs nested under a `master_q4/` prefix (plus a parallel `__MACOSX/` AppleDouble tree to skip). Carries **all 8 intervals** (1/5/15/30/60/240/720/1440 min). BTC/EUR daily spans **2013-09-10 → 2025-12-31** (4491 rows) — fully covers §9's 2019+ walk-forward.
  - **Quarterly *update* ZIPs `Kraken_OHLCVT_Q<n>_<yyyy>.zip`** — 13 files, Q1-2023 → Q1-2026, each holding just that quarter. The interval set **varies by quarter** (verified per file): the **four 2023 quarters** carry a reduced set `1/5/15/60/720/1440` (no 30, no 240); **2024-Q1 → 2025-Q3** carry the **full 8** (incl. 30 + 240); **2025-Q4 & 2026-Q1** carry 7 — `1/5/15/60/240/720/1440` (240 present, only 30 missing). So native 4h (240) is absent **only from the four 2023 quarters**.
- **CSV format is 7 columns `time,open,high,low,close,volume,trades` — no vwap** (OHLCVT). The canonical schema's `vwap` must therefore be **reconstructed** by aggregating the 1-minute bars (Σ price·vol / Σ vol); it is not present in any dump interval. (Support article 360047124832 lists all 8 intervals for the base dump — accurate; the *update* ZIPs are the ones with the reduced set.)
- **Intraday history is much shorter than daily** in the base dump — e.g. `master_q4/XBTEUR_240.csv` (4h) starts **2024-01-01**, not 2013. So deep-history *daily* is native, but a deep-history *4h/1h* series can only reach back as far as the 1-minute data does (verify per interval). Reconstructing 4h/1h from the 1-minute bars is still the cleanest uniform path because **vwap is missing from every interval** and must be rebuilt regardless; it also fills the native-240 gap for the four 2023 update quarters (240 is native everywhere else, so it can double as a cross-check there).

## Suggested next steps (backfill implementation — deferred; do not start until scheduled)

- Wire a **`ZIP → canonical Parquet` backfill**: read the base dump + quarterly updates from the NAS path (configured in `zcrypto.toml`, **not** hardcoded), reconstruct 1h/4h/1d **and vwap** by aggregating the 1-minute bars, merge base + update quarters (sort + dedup on `ts`), skip `__MACOSX/` entries and strip the `master_q4/` prefix, write the canonical `data/ohlc/{base}/{quote}/{interval}.parquet` tree, and reconcile vs the REST v0 window. TDD on small synthetic ZIP fixtures.
- Decide scope at build time: the 12-name universe (matches v0) vs all EUR/BTC pairs vs the full archive; and which intervals (1h/4h/1d vs also 1m/5m/15m). Verify per-interval how far back the 1-minute data actually reaches (this bounds deep-history intraday).
- Empty-interval handling; re-hash the dataset + update `docs/data-catalog.md`; Binance Vision cross-check per §8 remains a follow-up.
