---
status: resolved
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

## Done so far

- **Download mechanism resolved** (commit `a52a700` on this branch): the ZIPs are downloaded manually to the NAS mount `/home/zhaow/Projects/zcrypto-kraken-data/kraken-ohlcvt-updates/` — the **base 2013+ full-history dump** (`Kraken_OHLCVT.zip`) and the **quarterly update ZIPs** (2023-Q1 → 2026-Q1) are both present, resolving T0001's core "how do we get the data" question.
- **Archive structure verified** (the Findings above): per-file interval sets, the 7-column no-vwap format, the `master_q4/` prefix + `__MACOSX/` cruft, and the coverage bounds are all confirmed — so the backfill can be designed against known ground truth rather than guessed.

## Resolution (iter-008, 2026-07-07)

Built **`cli/backfill/`** (spec/plan `docs/{specs,plans}/00005-ohlcvt-backfill*`) and generated the full-history dataset:

- **Pipeline** — `read_minute_rows` (base + quarterly zips), `aggregate_minutes` (1-minute → 1h/4h/1d bars), `backfill_basket` (canonical Parquet + manifest, reusing `cli.ohlc.dataset`), `reconcile_series`/`reconcile_dataset`; `ohlcvt_source_dir` added to `zcrypto.toml`. 27 tests.
- **Key correction to the Findings above:** the 1-minute bars are **full-history** (XBTEUR: 2013-09-10 → 2025-12-31, 5.5M rows) — only *native* 4h (240) is short (2024+). So **all cadences are reconstructed from the 1-minute bars**, giving full-history 1h/4h/1d *and* a volume-weighted vwap proxy (Σ close·vol / Σ vol — the dumps carry no vwap).
- **Merge policy** — the base dump is authoritative for its range (2013 → 2025-12-31); quarterly updates contribute only rows past the base's last ts (Q1-2026, exactly contiguous). Found by an instrument-check smoke test: the base + 2023-2025 quarterlies overlap and the base has more-complete volume/trades.
- **Dataset** — `data/ohlc-full/` (gitignored): the 12-name universe × 1h/4h/1d, BTC/EUR daily 2013-09-10 → 2026-03-31 (4581 rows). Cataloged in `docs/reference/data-catalog-full.md`.
- **Validation** (`docs/research/02.phase1-ohlcvt-backfill-reconciliation.md`) — reconstructed OHLC is **bit-identical to the v0 REST** (100% exact match over 623 daily + 137 4h overlap rows/pair); vwap proxy within **~0.05%** of REST's true vwap. Caveats: daily volume within ~7% max on the worst bar (aggregation/revision artifact; 4h volume exact); 1h not independently reconciled (v0's REST 1h window post-dates the 2026-03-31 dump end). QA: 7807 no-trade gaps, 90.5% min coverage (expected for thin markets/early history).

**Deferred follow-ups:** finer cadences (1m/5m/15m) and full-exchange breadth; empty-interval reconstruction; Binance-Vision cross-check; the symbol & corporate-action ledger; pointing the universe/backtests at the new dataset hash (a Phase-2 decision).
