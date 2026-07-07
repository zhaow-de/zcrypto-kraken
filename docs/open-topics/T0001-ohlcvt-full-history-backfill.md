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
- The full-history ZIPs are Google-Drive-hosted and were **not** confirmed cleanly scriptable in an unattended run — the download mechanism needs investigation (rclone/gdown against the shared folder? a stable direct-download URL? or a human-assisted one-time pull to the NAS, then a scripted ingest).

## Suggested next steps

- Investigate the ZIP download mechanism (support article 360047124832): is there a scriptable path, or is a one-time human-assisted download required? (A human-assisted download is a D3(i)-style account/infra action, not autonomously doable.)
- Once the ZIPs are local, wire a ZIP→canonical-Parquet backfill into the iter-004 `cli/ohlc` pipeline (empty-interval reconstruction, reconcile vs the REST window, Binance Vision cross-check per §8), extending the dataset to full history and re-hashing.
