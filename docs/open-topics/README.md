# Open topics

Topics worth follow-up are parked here, one file per topic. See `.claude/rules/open-topics.md` for the convention.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Research and development](#research-and-development)
  - [Open](#open)
  - [Resolved](#resolved)
- [Live trading preparation](#live-trading-preparation)
  - [Open](#open-1)

<!-- mdformat-toc end -->

## Research and development<a name="research-and-development"></a>

### Open<a name="open"></a>

- [T0001 — full-history OHLCVT backfill](T0001-ohlcvt-full-history-backfill.md) — Kraken's downloadable ZIP archive (Google-Drive-hosted) holds the 2019→2026 history the §9 walk-forward needs; the REST-seeded v0 dataset only spans ~2y. Mechanism needs investigation (possibly human-assisted).

### Resolved<a name="resolved"></a>

- [T0002 — universe liquidity-floor calibration & quote-currency volume](archive/T0002-universe-liquidity-floor-calibration.md) — resolved in iter-007: EUR floor lowered €1M→€150k (footprint-based) + `quote_volume_in_eur` FX-normalizes the BTC-quoted legs → the full 12-name basket, `escalate=False`; findings recorded in master-plan §3.

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](T0000-phase0-account-actions.md) — D3(i) Kraken account actions (verification-tier check, margin enablement, API keys) + live fee-tier/AoP confirmation; human-only, gates Phase 1 data, Phase 6 execution, and the cost model.
