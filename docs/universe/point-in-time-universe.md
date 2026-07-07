# Point-in-Time Universe

**Iteration:** iter-005 · **Phase:** 1 (Data Foundation) · **Scope:** the mechanical, rule-driven universe
selection defined in `docs/specs/00003-universe-finalization-design.md` (master-plan §3), composing iter-002's
margin/leverage snapshot (`cli.snapshot`) and iter-004's daily OHLC (`cli.ohlc`) via `cli/universe/`
(`finalize_universe` + `build_universe_file`). **Regenerated in iter-007** per **T0002**: the liquidity floor is
now €150,000/day and quote-volume is EUR-normalized via `quote_volume_in_eur` (FX-converts BTC-quoted legs
through the BTC/EUR daily close).

**As of:** 2026-07-07 (UTC)
**Escalate:** **False** — 12 selected, within `MIN_NAMES`–`MAX_NAMES` (8–15). No escalation signal this run.

## Selected universe

BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, ADA/EUR, LINK/EUR, DOGE/EUR, LTC/EUR, DOT/EUR, AVAX/EUR, ETH/BTC, SOL/BTC

## Per-symbol criteria

| Symbol   | Selected | Margin | Max leverage | Median quote volume (30d, EUR) | Reasons |
| -------- | -------- | ------ | ------------ | ------------------------------- | ------- |
| BTC/EUR  | yes      | yes    | 10           | 27,842,495.91                   | -       |
| ETH/EUR  | yes      | yes    | 10           | 11,453,549.13                   | -       |
| SOL/EUR  | yes      | yes    | 10           | 5,388,531.14                    | -       |
| XRP/EUR  | yes      | yes    | 10           | 3,968,065.63                    | -       |
| ADA/EUR  | yes      | yes    | 10           | 1,299,998.00                    | -       |
| LINK/EUR | yes      | yes    | 10           | 283,221.05                      | -       |
| DOGE/EUR | yes      | yes    | 10           | 501,434.02                      | -       |
| LTC/EUR  | yes      | yes    | 10           | 1,247,595.16                    | -       |
| DOT/EUR  | yes      | yes    | 5            | 182,168.24                      | -       |
| AVAX/EUR | yes      | yes    | 10           | 272,540.96                      | -       |
| ETH/BTC  | yes      | yes    | 5            | 579,963.79                      | -       |
| SOL/BTC  | yes      | yes    | 4            | 233,594.56                      | -       |

All twelve candidates are margin-enabled with `leverage_buy` clearing `min_leverage=2`, and at the new €150,000/day
floor every candidate also clears the median-quote-volume criterion: the four previously-thin EUR alts
(LINK/DOGE/DOT/AVAX) clear it directly, and the two BTC-quoted RV legs (ETH/BTC, SOL/BTC) clear it once
FX-normalized to EUR via `quote_volume_in_eur`. None of BTC/ETH's own criteria failed, so the `mandatory` override
(§3: BTC/ETH always selected) never had to activate for this run either.

## Parameters

| Parameter                          | Value       |
| ----------------------------------- | ----------- |
| `min_leverage`                      | 2           |
| `min_median_quote_volume`           | 150,000.0 (EUR/day) |
| `median_quote_volume_window_days`   | 30          |
| `mandatory`                         | BTC, ETH (EUR-quoted leg only) |

## Spread cap

`spread_cap`: `pending-capture` — no spread criterion yet; this needs the L2 capture daemon (VPS/infra-gated, not
built). Per the design's non-goals, every entry above carries this same placeholder rather than a computed value.

## Escalation note

12 of 12 candidates are selected; `escalate=False` (within `MIN_NAMES=8`–`MAX_NAMES=15`), so no escalation signal
fires on this run. This resolves iter-005's T0002 escalation on both of its drivers: (1) the liquidity floor
dropped from €1,000,000/day to €150,000/day — a footprint-sizing floor (a full max-size position at our sizing is
≈1% of median daily EUR volume) — under which the four previously-thin EUR alts (LINK €283,221.05, DOGE
€501,434.02, DOT €182,168.24, AVAX €272,540.96) now clear the bar; and (2) `quote_volume_in_eur` FX-normalizes the
two BTC-quoted relative-value legs (ETH/BTC, SOL/BTC) through the BTC/EUR daily close, so their turnover is judged
in EUR (€579,963.79 and €233,594.56 respectively) rather than compared unconverted against a EUR-scaled floor — no
longer a unit mismatch, a real, comparable measurement. All twelve candidates now clear every criterion on their
own merits.

## Provenance

- **Snapshot file:** `data/snapshots/kraken-refdata-20260707T032900Z.json` (gitignored; regenerate via
  `cli.snapshot.fetch_public` + `build_snapshot`) — fetched at `2026-07-07T03:29:00+00:00`, raw sha256
  `e1510e9887b5a2c4f03e7830c4f0f71b9fa458301d453c18b92e85d8ae3226e3`. Unchanged since iter-005 — this
  regeneration reuses the same snapshot and OHLC inputs; only the selection rule's parameters and volume
  derivation changed (T0002).
- **OHLC dataset:** `data/ohlc/{symbol}/1440.parquet` (gitignored; regenerate via `cli.ohlc.ingest_basket`) per
  `data/ohlc/manifest.json`, fetched at `2026-07-07T04:12:55.776871+00:00`; basket sha256 (over the sorted
  `{symbol: dataset_hash}` map for the twelve `1440.parquet` series used for the volume signal)
  `407d2ed8222946111dc8301cf420a456d9a7ebbfc2835610f89a236ed23fd093`.
- **Derivation code:** `cli/universe/` (`volume.py`, `rules.py`, `build.py`), unit-tested against synthetic
  `PairSnapshot`-shaped inputs — see `docs/specs/00003-universe-finalization-design.md`. Volume is now computed via
  `quote_volume_in_eur` (EUR-quoted legs: identical to `median_quote_volume`; BTC-quoted legs: FX-normalized
  through the BTC/EUR daily close), and the floor is `DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 150_000.0` (commit
  `9495e2d`, T0002).
- **Machine-readable file:** `data/universe/point-in-time-universe.json` (gitignored; the full `build_universe_file`
  dict, regenerable from the inputs above) — sha256 `2ddef2c7fc42da2af1af438ff3cd1861d7da49fa111c2075816f7c13aca210e9`.

## Deferred / follow-ups

- **Spread-cap criterion** — needs the L2 capture daemon (VPS-gated, not built). Parked per the design's non-goals.
- **Full-history volume** improves once T0001's OHLCVT backfill lands (currently ~2 years from the REST 720-candle
  cap; the median window is only 30 days, so this affects data depth, not the current selection).
- Full symbol & corporate-action ledger (redenominations, quote-book migrations) beyond iter-002's alias ledger
  (XBT=BTC, XDG=DOGE) is a follow-up, per the design's non-goals.
