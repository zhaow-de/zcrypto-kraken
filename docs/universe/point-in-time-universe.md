# Point-in-Time Universe

**Phase:** 1 (Data Foundation) · **Scope:** the mechanical, rule-driven universe selection defined in
`docs/specs/00003-universe-finalization-design.md` (master-plan §3), composing iter-002's margin/leverage snapshot
(`cli.snapshot`) and daily OHLC via `cli/universe/` (`finalize_universe` + `build_universe_file`). **Regenerated
2026-10-12** from the rolling canonical `ohlc-rolling` (spec `00125`) at its head day 2026-10-10.

**As of:** 2026-10-12 (UTC)
**Escalate:** **False** — 12 selected, within `MIN_NAMES`–`MAX_NAMES` (8–15). No escalation signal this run.

## Selected universe

BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, ADA/EUR, LINK/EUR, DOGE/EUR, LTC/EUR, DOT/EUR, AVAX/EUR, ETH/BTC, SOL/BTC

## Per-symbol criteria

| Symbol   | Selected | Margin | Max leverage | Median quote volume (30d, EUR) | Spread (bps) | Reasons |
| -------- | -------- | ------ | ------------ | ------------------------------- | ------------ | ------- |
| BTC/EUR  | yes      | yes    | 10           | 28,790,290.87                   | 0.333        | -       |
| ETH/EUR  | yes      | yes    | 10           | 16,315,456.01                   | 0.435        | -       |
| XRP/EUR  | yes      | yes    | 10           | 15,322,605.04                   | 1.088        | -       |
| SOL/EUR  | yes      | yes    | 10           | 9,759,123.01                    | 1.152        | -       |
| ADA/EUR  | yes      | yes    | 10           | 3,756,892.52                    | 3.081        | -       |
| LINK/EUR | yes      | yes    | 10           | 2,616,223.45                    | 2.769        | -       |
| AVAX/EUR | yes      | yes    | 10           | 1,564,775.34                    | 3.305        | -       |
| LTC/EUR  | yes      | yes    | 10           | 1,274,157.25                    | 3.232        | -       |
| DOGE/EUR | yes      | yes    | 10           | 1,244,780.56                    | 2.043        | -       |
| DOT/EUR  | yes      | yes    | 5            | 768,357.15                      | 4.930        | -       |
| ETH/BTC  | yes      | yes    | 5            | 712,128.94                      | 1.178        | -       |
| SOL/BTC  | yes      | yes    | 4            | 356,777.57                      | 1.842        | -       |

None of BTC/ETH's own criteria failed, so the `mandatory` override (§3: BTC/ETH always selected) did not activate.

## Parameters

| Parameter                          | Value       |
| ----------------------------------- | ----------- |
| `min_leverage`                      | 2           |
| `min_median_quote_volume`           | 150,000.0 (EUR/day) |
| `median_quote_volume_window_days`   | 30          |
| `mandatory`                         | BTC, ETH (EUR-quoted leg only) |

## Spread cap

`spread_cap` is a computed record:

| Field | Value |
| --- | --- |
| `max_spread_bps` | 10.0 |
| `reference_notional_eur` | 1400.0 |
| `source` | `cli/costs/spread.py` — mean effective spread at size |
| `unevaluated_count` | **0** |

All twelve symbols carry a numeric `spread_bps`, the two BTC-quoted legs included — they read `null` while L2
capture was EUR-only, and a null on either is now the failure signal rather than the expected state.

## Provenance

- **Reference data:** a **live** `AssetPairs` + `Assets` fetch performed by `_refresh_universe` at rebuild time
  (`cli.snapshot.register.build_snapshot` over `cli.snapshot.fetch.fetch_public`), raw sha256
  `e8f10892941617dd7bbe3b2b6f5d4e75de560c15361afab4a9a3b19de5bb2fc8`. This path does **not** persist a snapshot
  file.
- **OHLC dataset:** `data/ohlc-rolling/days/{base}/{quote}/` (gitignored), the rolling canonical (spec `00125`) at
  its head day **2026-10-10**, basket sha256 `fcb62a79fab7b58626f0cbd96ae40093a6dfc9e6ff51384cf25a5e9759dc44c4` —
  the sha256 of that day's index line, which `zcrypto data rolling verify` walks down to the base; the stalest daily
  bar across the basket is 2026-10-10, two days old against the 7-day staleness budget; no pair closed.
- **Derivation code:** `cli/universe/` (`volume.py`, `rules.py`, `build.py`) — see
  `docs/specs/00003-universe-finalization-design.md`. Volume is computed via `quote_volume_in_eur` (EUR-quoted
  legs: identical to `median_quote_volume`; BTC-quoted legs: FX-normalized through the BTC/EUR daily close), and
  the floor is `DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 150_000.0`.
- **Machine-readable file:** `data/universe-20261012/point-in-time-universe.json` (gitignored) — sha256
  `c6a168e5907cb03ba5c2479d41b1a3b864793deb194ad1c6d285a0e94636ae54`. Published to the hub as the immutable
  stamped set `universe-20261012/` (spec `00093` D5) on 2026-10-12 at 14:44Z.
