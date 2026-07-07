# Point-in-Time Universe

**Iteration:** iter-005 · **Phase:** 1 (Data Foundation) · **Scope:** the mechanical, rule-driven universe
selection defined in `docs/specs/00003-universe-finalization-design.md` (master-plan §3), composing iter-002's
margin/leverage snapshot (`cli.snapshot`) and iter-004's daily OHLC (`cli.ohlc`) via `cli/universe/`
(`finalize_universe` + `build_universe_file`).

**As of:** 2026-07-07 (UTC)
**Escalate:** **True** — 6 selected, below `MIN_NAMES` (8). See "Escalation note" below; this is a recorded
signal for review, not an error.

## Selected universe

BTC/EUR, ETH/EUR, SOL/EUR, XRP/EUR, ADA/EUR, LTC/EUR

## Per-symbol criteria

| Symbol   | Selected | Margin | Max leverage | Median quote volume (30d) | Reasons                                             |
| -------- | -------- | ------ | ------------ | -------------------------- | ---------------------------------------------------- |
| BTC/EUR  | yes      | yes    | 10           | 27,842,495.91               | -                                                      |
| ETH/EUR  | yes      | yes    | 10           | 11,453,549.13               | -                                                      |
| SOL/EUR  | yes      | yes    | 10           | 5,388,531.14                | -                                                      |
| XRP/EUR  | yes      | yes    | 10           | 3,968,065.63                | -                                                      |
| ADA/EUR  | yes      | yes    | 10           | 1,299,998.00                | -                                                      |
| LINK/EUR | no       | yes    | 10           | 283,221.05                  | median quote volume below the €1,000,000.0 floor     |
| DOGE/EUR | no       | yes    | 10           | 501,434.02                  | median quote volume below the €1,000,000.0 floor     |
| LTC/EUR  | yes      | yes    | 10           | 1,247,595.16                | -                                                      |
| DOT/EUR  | no       | yes    | 5            | 182,168.24                  | median quote volume below the €1,000,000.0 floor     |
| AVAX/EUR | no       | yes    | 10           | 272,540.96                  | median quote volume below the €1,000,000.0 floor     |
| ETH/BTC  | no       | yes    | 5            | 10.55                       | median quote volume below the 1,000,000.0 floor (BTC-denominated, see note) |
| SOL/BTC  | no       | yes    | 4            | 4.36                        | median quote volume below the 1,000,000.0 floor (BTC-denominated, see note) |

All twelve candidates are margin-enabled with `leverage_buy` clearing `min_leverage=2`, so the selection line here is
drawn entirely by the median-quote-volume floor. None of BTC/ETH's own criteria failed, so the `mandatory` override
(§3: BTC/ETH always selected) never had to activate for this run.

## Parameters

| Parameter                          | Value       |
| ----------------------------------- | ----------- |
| `min_leverage`                      | 2           |
| `min_median_quote_volume`           | 1,000,000.0 (EUR/day) |
| `median_quote_volume_window_days`   | 30          |
| `mandatory`                         | BTC, ETH (EUR-quoted leg only) |

## Spread cap

`spread_cap`: `pending-capture` — no spread criterion yet; this needs the L2 capture daemon (VPS/infra-gated, not
built). Per the design's non-goals, every entry above carries this same placeholder rather than a computed value.

## Escalation note

6 of 12 candidates are selected, below `MIN_NAMES=8`, so `escalate=True` per §3. The six EUR-quoted majors (BTC, ETH,
SOL, XRP, ADA, LTC) clear all three criteria on their own merits. LINK/DOGE/DOT/AVAX are dropped solely on the
€1,000,000/day median-quote-volume floor — all four pass margin+leverage. The two BTC-quoted relative-value legs
(ETH/BTC, SOL/BTC) are also dropped: their `volume * vwap` is denominated in BTC, not EUR, so it is compared against
the same nominal `1,000,000.0` floor as the EUR-quoted legs — a known unit mismatch (their raw BTC turnover numbers,
~10.5 and ~4.4, are not literally "below liquidity", they're in the wrong unit), not evidence the legs are illiquid.
Per the design, this escalation is a recorded signal for the next review, not auto-resolved by this module.

## Provenance

- **Snapshot file:** `data/snapshots/kraken-refdata-20260707T032900Z.json` (gitignored; regenerate via
  `cli.snapshot.fetch_public` + `build_snapshot`) — fetched at `2026-07-07T03:29:00+00:00`, raw sha256
  `e1510e9887b5a2c4f03e7830c4f0f71b9fa458301d453c18b92e85d8ae3226e3`.
- **OHLC dataset:** `data/ohlc/{symbol}/1440.parquet` (gitignored; regenerate via `cli.ohlc.ingest_basket`) per
  `data/ohlc/manifest.json`, fetched at `2026-07-07T04:12:55.776871+00:00`; basket sha256 (over the sorted
  `{symbol: dataset_hash}` map for the twelve `1440.parquet` series used for the volume signal)
  `407d2ed8222946111dc8301cf420a456d9a7ebbfc2835610f89a236ed23fd093`.
- **Derivation code:** `cli/universe/` (`volume.py`, `rules.py`, `build.py`), unit-tested against synthetic
  `PairSnapshot`-shaped inputs — see `docs/specs/00003-universe-finalization-design.md`.
- **Machine-readable file:** `data/universe/point-in-time-universe.json` (gitignored; the full `build_universe_file`
  dict, regenerable from the inputs above) — sha256 `43a727a71f3ff16aaa5b4bcf4b177103799c322a73147f7e816393759c0d7499`.

## Deferred / follow-ups

- **Spread-cap criterion** — needs the L2 capture daemon (VPS-gated, not built). Parked per the design's non-goals.
- **BTC-quoted relative-value legs' volume unit mismatch** (see "Escalation note" above) — `median_quote_volume` for
  ETH/BTC and SOL/BTC is in raw BTC, compared against a EUR-scaled floor, so it always fails by construction. An
  FX-normalization step (e.g. via the BTC/EUR reference price) would be needed to judge these legs on the same
  €-denominated bar as the EUR-quoted majors, if that is the intent.
- **Full-history volume** improves once T0001's OHLCVT backfill lands (currently ~2 years from the REST 720-candle
  cap; the median window is only 30 days, so this affects data depth, not the current selection).
- Full symbol & corporate-action ledger (redenominations, quote-book migrations) beyond iter-002's alias ledger
  (XBT=BTC, XDG=DOGE) is a follow-up, per the design's non-goals.
