# Point-in-Time Universe

**Iteration:** iter-137 · **Phase:** 1 (Data Foundation) · **Scope:** the mechanical, rule-driven universe
selection defined in `docs/specs/00003-universe-finalization-design.md` (master-plan §3), composing iter-002's
margin/leverage snapshot (`cli.snapshot`) and daily OHLC via `cli/universe/` (`finalize_universe` +
`build_universe_file`). **Regenerated in iter-137** by the attended sitting that spec `00093` unblocked: the
volume signal now reads a source that reaches the present (`ohlc-reach-20260813`, stalest daily bar 2026-08-12)
rather than `data/ohlc-full`, whose every leg had been frozen at 2026-03-31 for 135 days.

**As of:** 2026-08-13 (UTC)
**Escalate:** **False** — 11 selected, within `MIN_NAMES`–`MAX_NAMES` (8–15). No escalation signal this run.

## Selected universe

BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, ADA/EUR, LINK/EUR, DOGE/EUR, LTC/EUR, AVAX/EUR, ETH/BTC, SOL/BTC

## Per-symbol criteria

| Symbol   | Selected | Margin | Max leverage | Median quote volume (30d, EUR) | Spread (bps) | Reasons |
| -------- | -------- | ------ | ------------ | ------------------------------- | ------------ | ------- |
| BTC/EUR  | yes      | yes    | 10           | 17,748,440.11                   | 0.333        | -       |
| ETH/EUR  | yes      | yes    | 10           | 8,599,762.22                    | 0.435        | -       |
| SOL/EUR  | yes      | yes    | 10           | 3,792,006.07                    | 1.152        | -       |
| XRP/EUR  | yes      | yes    | 10           | 2,204,186.24                    | 1.088        | -       |
| ADA/EUR  | yes      | yes    | 10           | 999,036.42                      | 3.081        | -       |
| LTC/EUR  | yes      | yes    | 10           | 807,318.83                      | 3.232        | -       |
| ETH/BTC  | yes      | yes    | 5            | 570,713.52                      | 1.178        | -       |
| SOL/BTC  | yes      | yes    | 4            | 322,637.71                      | 1.842        | -       |
| DOGE/EUR | yes      | yes    | 10           | 278,866.37                      | 2.043        | -       |
| LINK/EUR | yes      | yes    | 10           | 187,927.50                      | 2.769        | -       |
| AVAX/EUR | yes      | yes    | 10           | 183,593.90                      | 3.305        | -       |
| DOT/EUR  | **no**   | yes    | 5            | **146,957.37**                  | 4.930        | median quote volume 146957.37297554774 below floor 150000.0 |

All twelve candidates remain margin-enabled with `leverage_buy` clearing `min_leverage=2`, and every one clears the
10 bps spread cap. **DOT/EUR is dropped on volume** — the only criterion any candidate now fails. The two
BTC-quoted RV legs clear the floor comfortably once FX-normalized to EUR via `quote_volume_in_eur`. None of
BTC/ETH's own criteria failed, so the `mandatory` override (§3: BTC/ETH always selected) did not activate.

## Parameters

| Parameter                          | Value       |
| ----------------------------------- | ----------- |
| `min_leverage`                      | 2           |
| `min_median_quote_volume`           | 150,000.0 (EUR/day) |
| `median_quote_volume_window_days`   | 30          |
| `mandatory`                         | BTC, ETH (EUR-quoted leg only) |

## Spread cap

`spread_cap` is now a computed record rather than the `pending-capture` placeholder every prior generation carried:

| Field | Value |
| --- | --- |
| `max_spread_bps` | 10.0 |
| `reference_notional_eur` | 1400.0 |
| `source` | `cli/costs/spread.py` — mean effective spread at size |
| `unevaluated_count` | **0** |

All twelve symbols carry a numeric `spread_bps`, the two BTC-quoted legs included — they read `null` while L2
capture was EUR-only, and a null on either is now the failure signal rather than the expected state. The widest is
DOT/EUR at 4.930 bps, comfortably inside the 10 bps cap, so **the cap binds on nothing this run**: it excludes no
symbol that volume did not already exclude.

## Escalation note

11 of 12 candidates are selected; `escalate=False` (within `MIN_NAMES=8`–`MAX_NAMES=15`), so no escalation signal
fires. The single exclusion is a genuine liquidity change, not a measurement artifact, and it is the reverse of
the error this regeneration was commissioned to fix. Recomputing over the frozen `ohlc-full` window had selected
eleven by dropping **AVAX/EUR** at 132,274.82 — a stale-window artifact that spec `00093` refuted, and on this
fresh window AVAX clears at 183,593.90. What the fresh window instead shows is **DOT/EUR falling below the floor**
at 146,957.37, down from 194,771.98 on the window ending 2026-07-22 — roughly a 25% decline in three weeks. Two
different symbols, two different causes: the first was an artifact of measuring a dead window, the second is a
real market move measured correctly.

## Provenance

- **Reference data:** a **live** `AssetPairs` + `Assets` fetch performed by `_refresh_universe` at rebuild time
  (`cli.snapshot.register.build_snapshot` over `cli.snapshot.fetch.fetch_public`), raw sha256
  `32312484995c43777f20ca007be3d5d0da0a7505c830f4bf7f792f916aee8917`. This path does **not** persist a snapshot
  file — earlier generations of this document cited one under `data/snapshots/`, which no longer describes how the
  universe rebuild obtains its reference data.
- **OHLC dataset:** `data/ohlc-reach-20260813/{base}/{quote}/1440.parquet` (gitignored), basket sha256
  `d77fff97c819f5afbabbddf44ad0b8d94185a62a84002aaf36d153357100c98e`, minted 2026-08-13T03:14:02Z. Resolved by
  `resolve_ohlc_source` as the newest stamped `ohlc-reach-<stamp>` sibling; the stalest daily bar across the
  basket is **2026-08-12**, one day old against the 7-day staleness budget. All twelve daily series seamed to the
  canonical tail (`status: continuous`, 586 overlap bars, 134 bars appended, `gap_bars: 0`).
- **Derivation code:** `cli/universe/` (`volume.py`, `rules.py`, `build.py`) — see
  `docs/specs/00003-universe-finalization-design.md`. Volume is computed via `quote_volume_in_eur` (EUR-quoted
  legs: identical to `median_quote_volume`; BTC-quoted legs: FX-normalized through the BTC/EUR daily close), and
  the floor is `DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 150_000.0`.
- **Machine-readable file:** `data/universe-20260813/point-in-time-universe.json` (gitignored) — sha256
  `d4a6f2454ee3196dc5d15e35b9211df2329667b2b6eb054419efc03c60380d5a`. Published to the hub as the immutable
  stamped set `universe-20260813/` (spec `00093` D5); the legacy `universe/` directory is untouched and remains
  the resolver's fallback until it is retired.

## Deferred / follow-ups

- **Full-history volume** — **DISCHARGED 2026-08-13** by this regeneration (→
  `docs/open-topics/T0093-universe-rebuild-reads-a-stale-ohlc-set.md`). The volume signal no longer reads a dead
  window: `_refresh_universe` resolves the newest stamped reach sibling, and the reach round now mints all twelve
  legs rather than the ten EUR ones. What remains on that topic is repo-side only — retiring the legacy
  `universe/` fallback now that a stamped set is published and the resolver selects it.
- **Spread-cap criterion** — **DISCHARGED 2026-08-13** by this regeneration (→ **T0024**). The artifact carries a
  computed `spread_cap` record with `unevaluated_count: 0` and all twelve symbols carry a numeric `spread_bps`.
- **Intraday reach series are detached at this staleness** — the 240 and 60 minute series could not seam and are
  written as `240.detached.parquet` / `60.detached.parquet` for all twelve symbols, so a consumer globbing
  `240.parquet` finds nothing rather than a series with a hole. Kraken's REST returns ~720 bars at every
  interval, which reaches back 719 days at 1440 but only ~120 days at 240 and ~30 at 60 — shorter than the
  135-day canonical gap. Only the daily series, which this document depends on, bridged it.
- **Full symbol & corporate-action ledger** (redenominations, quote-book migrations, delistings) beyond iter-002's
  alias ledger (XBT=BTC, XDG=DOGE) — registered as **T0025** (`docs/open-topics/T0025-full-corporate-action-ledger.md`).
