# B2 funding substrate — Binance Vision funding-rate backfill (design)

**Iteration:** iter-090 (unattended research loop; decisions log `[iter-090]`). **Goal:** the B2 family's **funding-rate** data substrate — full-history realized funding for the 10-name USDT-M perp universe, backfilled from **Binance Vision monthly `fundingRate` dumps** (the ratified §8 data plan's Binance path; keyless, checksum-verified), into a hash-versioned derived dataset. This is the autonomous, human-gate-independent half of T0023's B2 pre-work (funding + OI are keyless-backfillable; the liquidations decision is the human's — parked in T0023). **OI is explicitly out of scope here** (the daily 5m `metrics` dumps are a much larger, separate build for the B2 opening iteration); funding is the tightly-scoped substrate that de-risks the family's funding factor now.

## Source (probed + confirmed iter-090)

`https://data.binance.vision/data/futures/um/monthly/fundingRate/<PERP>/<PERP>-fundingRate-YYYY-MM.zip` (+ `.zip.CHECKSUM`). Verified: keyless HTTP 200; the `.CHECKSUM` is `sha256  filename`; the zip holds one CSV, header `calc_time,funding_interval_hours,last_funding_rate` — `calc_time` epoch **ms**, 8h cadence (e.g. `1577836800000,8,-0.00012359`). Deep to each perp's listing (BTC 2020-01). A month before listing / not yet published → HTTP 404.

## Universe mapping (Kraken spot → USDT-M perp)

`{BTC:BTCUSDT, ETH:ETHUSDT, SOL:SOLUSDT, ADA:ADAUSDT, XRP:XRPUSDT, DOGE:DOGEUSDT, DOT:DOTUSDT, LINK:LINKUSDT, LTC:LTCUSDT, AVAX:AVAXUSDT}` — the 10 basket assets; funding is a USDT-M perp feature (the tradeable book is Kraken EUR spot — the venue/instrument gap is carried by the consumer, not resolved here).

## The derived dataset

- **Path:** `data/derivatives-funding/<PERP>/funding.parquet` — a **new derived root** (gitignored via `data/.gitignore`, like every dataset), never touching canonical.
- **Schema:** `ts` (aware-UTC `datetime`, from `calc_time` ms), `funding_rate` (float, from `last_funding_rate`), `interval_hours` (int, from `funding_interval_hours`). Sorted ascending, deduplicated on `ts` (last-wins is irrelevant — dumps don't overlap, but dedup guards a re-fetch).
- **Provenance + hashes:** a `manifest.json` mirroring the backfill convention — per perp `{rows, first_ts, last_ts, sha256}` + a `basket_sha256` over the sorted per-series hashes; plus `source` (the base URL) and `fetched_at`. The registry-referenceable hash for every future B2 funding trial.

## The fetch (new package `cli/derivatives/`, TDD)

Mirror the `cli/ohlc/fetch.py` injectable-opener convention (`opener=urllib.request.urlopen`) so tests inject a fake:

```python
# cli/derivatives/funding.py — loggers get_logger("derivatives.funding")
PERP_SYMBOLS: dict[str, str]                     # the 10 mappings above
def fetch_funding_month(perp: str, year: int, month: int, *, opener=...) -> list[list] | None
#   GET the monthly zip + its .CHECKSUM; verify sha256 (mismatch -> DerivativesError, never silently
#   accept); unzip the single CSV; parse rows [calc_time_ms, interval_hours, rate]; HTTP 404 -> None
#   (month before listing / unpublished). Transport/parse failure -> DerivativesError.
def backfill_funding(perp: str, *, start=(2019,9), clock=_utc_now, opener=...) -> pl.DataFrame
#   Walk months from `start` to the last COMPLETE month (clock's month is incomplete -> excluded);
#   the leading run of 404s (before this perp's listing) is skipped, then once data begins a 404
#   inside the range is an error (a hole in a listed series must not pass silently). Concat -> the
#   3-col frame, ts aware-UTC, sorted, deduped.
def build_funding_substrate(out_root: Path, *, perps=PERP_SYMBOLS, clock=_utc_now, opener=...) -> dict
#   backfill each perp -> write_parquet -> the manifest (returns it).
def read_funding_series(out_root: Path, perp: str) -> pl.DataFrame
```

**Drop rule (the only look-ahead surface):** the current (incomplete) calendar month is excluded — funding for an unfinished month is partial. A funding print `calc_time` is the settlement stamp; it is point-in-time by construction (no forward transform), so beyond the current-month exclusion there is no leakage vector.

## QA (before the substrate is registered)

- Per-perp coverage: `rows`, first/last `ts`, and **funding-cadence gap check** — consecutive `ts` deltas should be `interval_hours` (≈8h); flag and count any gap > 1.5× the interval (funding outages / listing-day partials), reported per perp (the iter-009/085 QA pattern).
- The **balanced-panel start**: the max first_ts across the 10 perps (expected ≈ 2020-09, AVAX/SOL — the T0023 finding); reported so B2 balanced-panel runs key off it.
- Sanity: funding rates in a plausible band (|rate| < 0.075, Binance's ±0.75%/8h cap era — flag outliers, don't clip); `interval_hours` ∈ {8} for this era (flag if any perp shows the later 4h/1h cadence, a real venue change to disclose).

## Out of scope

Open interest (the daily `metrics` dumps — the B2 opening iteration); liquidations (T0023's human decision); the B2 harness/features/trial (its own iteration, against this dataset's hash); Bybit/OKX cross-check (a nice-to-have, deferred — the Binance dumps are checksum-verified at source); any change to canonical data, the engine, or capture.

## Closeout

T0023's "build the funding + OI backfill" next-step flips to **funding-done / OI-remaining** (Done so far + the step reworded); decisions-log delivery note with the dataset `basket_sha256`; iterations-history entry (per-perp coverage + the panel start); PR; merge (loop mode). The dataset is substrate — no trial spend, B budget untouched.
