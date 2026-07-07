# Open topics

Topics worth follow-up are parked here, one file per topic. See `.claude/rules/open-topics.md` for the convention.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Research and development](#research-and-development)
  - [Open](#open)
  - [Partially done](#partially-done)
  - [Resolved](#resolved)
- [Live trading preparation](#live-trading-preparation)
  - [Open](#open-1)
  - [Partially done](#partially-done-1)

<!-- mdformat-toc end -->

## Research and development<a name="research-and-development"></a>

### Open<a name="open"></a>

_(none)_

### Partially done<a name="partially-done"></a>

- [T0001 — full-history OHLCVT backfill](T0001-ohlcvt-full-history-backfill.md) — download mechanism resolved (manual pull to the NAS mount; the base 2013+ full-history dump + the quarterly updates are present and their structure verified); the ZIP→canonical-Parquet backfill build is deferred until scheduled.

### Resolved<a name="resolved"></a>

- [T0002 — universe liquidity-floor calibration & quote-currency volume](archive/T0002-universe-liquidity-floor-calibration.md) — resolved in iter-007: EUR floor lowered €1M→€150k (footprint-based) + `quote_volume_in_eur` FX-normalizes the BTC-quoted legs → the full 12-name basket, `escalate=False`; findings recorded in master-plan §3.

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

_(none)_

### Partially done<a name="partially-done-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](T0000-phase0-account-actions.md) — all account actions done (eligibility, read-only key verified + in `.env`, fee tier Tier 1/$0, leverage, margin rates); only the Phase-2 cost-model fold-in remains (deferred to Phase 2).
