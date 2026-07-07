# Open topics

Topics worth follow-up are parked here, one file per topic. See `.claude/rules/open-topics.md` for the convention.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Research and development](#research-and-development)
  - [Open](#open)
- [Live trading preparation](#live-trading-preparation)
  - [Open](#open-1)

<!-- mdformat-toc end -->

## Research and development<a name="research-and-development"></a>

### Open<a name="open"></a>

- [T0001 — full-history OHLCVT backfill](T0001-ohlcvt-full-history-backfill.md) — Kraken's downloadable ZIP archive (Google-Drive-hosted) holds the 2019→2026 history the §9 walk-forward needs; the REST-seeded v0 dataset only spans ~2y. Mechanism needs investigation (possibly human-assisted).
- [T0002 — universe liquidity-floor calibration & quote-currency volume](T0002-universe-liquidity-floor-calibration.md) — iter-005's §3 rule selected only 6 names at the €1M/day floor (escalate fired); thin Kraken-EUR alt liquidity + a BTC-leg unit mismatch need a human basket/floor decision.

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](T0000-phase0-account-actions.md) — D3(i) Kraken account actions (verification-tier check, margin enablement, API keys) + live fee-tier/AoP confirmation; human-only, gates Phase 1 data, Phase 6 execution, and the cost model.
