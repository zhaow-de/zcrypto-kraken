# Kraken Cost Model — Fee Ladder + Margin Accrual — Design (Phase 2)

**Iteration:** iter-017 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §7/§8 (explicit cost model), §12 Phase 2 exit bar ("cost model validated…"), §4 (short carry). **Data source:** `docs/reference/kraken-fee-schedule.md` (confirmed 2026-07-07, T0000). Opens `cli/costs/`.

## Problem & context

Every §9 headline result is re-run at 1.5×/2× the fitted cost model and taker-only (§9.6). The cost model has three legs (§8): **spot fees** (the July-9 volume-tier ladder), **margin carry** (per-base opening + 4-hourly rollover), and **spread** (per-pair, from captured L2). This iteration builds the first two — both fully specified by the confirmed schedule already in-repo. **Spread is deferred** (T0003-gated: it needs ≥2 weeks of captured L2, which the Phase-2 exit bar also gates on the capture pipeline); it enters as a separate parameter when calibration lands.

Post-July-9 base tier is **0.40% maker / 0.80% taker** (a taker round trip = 1.60%) — this supersedes the master-plan §1/§4/§14 snapshot (0.25/0.40) and is why execution is maker-first, holds are days not minutes. Margin carry: short BTC 0.01–0.02%/4h (~22–44%/yr), alt shorts 0.02–0.04%/4h (~44–88%/yr).

## Goals

- **`cli/costs/`** — `fees.py` (spot fee ladder + round-trip fee) and `margin.py` (per-base rate lookup + open/rollover accrual), stdlib-only pure functions over the confirmed schedule. Property-tested; degenerate input raises `CostModelError` (harness never-crash discipline).

## Non-goals

- **No spread term** — T0003-gated (captured L2); enters later as a parameter. No combined "total trade cost" function yet (it needs spread).
- **No AoP path** — moot below $20k held (`docs/reference/kraken-fee-schedule.md`: our tier is volume-driven); YAGNI, deferred until the account nears $20k AoP.
- No stablecoin/FX cheaper schedule (our universe is EUR/BTC-quoted, on the standard schedule); no futures.
- No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

New package `cli/costs/` (module + `errors.py` + `__init__.py`), mirroring `cli/validation/` style.

**`cli/costs/errors.py`** — `class CostModelError(Exception)`.

**`cli/costs/fees.py`:**

- `SPOT_FEE_TIERS: tuple[tuple[float, float, float], ...]` — `(min_30d_volume_usd, maker, taker)` as **fractions**, post-July-9, ascending by volume: `(0, .0040, .0080), (2_500, .0030, .0060), (10_000, .0022, .0038), (25_000, .0020, .0035), (50_000, .0015, .0030), (100_000, .0012, .0025), (250_000, .0010, .0022), (500_000, .0008, .0020), (1_000_000, .0006, .0018), (2_500_000, .0004, .0015), (5_000_000, .0002, .0012), (10_000_000, .0000, .0010), (50_000_000, .0000, .0009), (100_000_000, .0000, .0008), (250_000_000, .0000, .0007), (400_000_000, .0000, .0006), (500_000_000, .0000, .0005)`.
- `spot_fee_rates(thirty_day_volume_usd: float) -> dict` → `{"tier": int, "maker": float, "taker": float}` for the highest tier whose `min_30d_volume_usd <= thirty_day_volume_usd` (`tier` is 1-based). Raises `CostModelError` if `thirty_day_volume_usd` is negative or non-finite.
- `round_trip_fee(notional: float, *, maker_rate: float, taker_rate: float, taker_open: bool = False, taker_close: bool = False) -> float` — `notional * (open_rate + close_rate)` where each leg's rate is `taker_rate` if that leg is taker else `maker_rate` (default maker-first, both legs maker). Raises `CostModelError` if `notional < 0`, any rate `< 0`, or any is non-finite.

**`cli/costs/margin.py`:**

- `MARGIN_RATES: dict[str, tuple[float, float]]` — base symbol → `(low, high)` fraction per open **and** per 4h rollover (same band, per `docs/reference/kraken-fee-schedule.md`): `BTC: (.0001, .0002)`; each of `ETH, SOL, XRP, ADA, LINK, DOGE, LTC, DOT, AVAX: (.0002, .0004)`.
- `margin_rate(base: str, *, band: str = "high") -> float` — the low/high rate for `base`. Raises `CostModelError` on an unknown base or `band not in {"low", "high"}`.
- `margin_carry(notional: float, hold_hours: float, rate: float) -> float` — `notional * rate * (1 + n_rollovers)` where `n_rollovers = floor(hold_hours / 4)` (opening fee at open + one rollover per completed 4-hour interval; matches §4's 24h → 6 rollovers, and Kraken's "first rollover at +4h"). Raises `CostModelError` if `notional < 0`, `hold_hours < 0`, `rate < 0`, or any is non-finite.

**`cli/costs/__init__.py`** — export `CostModelError`, `SPOT_FEE_TIERS`, `spot_fee_rates`, `round_trip_fee`, `MARGIN_RATES`, `margin_rate`, `margin_carry`.

## Testing

`tests/test_costs_fees.py` + `tests/test_costs_margin.py`:

- **`spot_fee_rates`** — `$0 → tier 1, maker .0040, taker .0080`; `$2_499 → tier 1` (just below the Tier-2 threshold); `$2_500 → tier 2 (.0030/.0060)`; `$9_999 → tier 2` (just below Tier 3 — note $9,999 ≥ $2,500 so it is Tier 2, not Tier 1); `$10_000 → tier 3 (.0022/.0038)`; `$25_000 → tier 4 (.0020/.0035)`; a huge volume (`1e12`) → tier 17 (`.0000/.0005`); monotonic non-increasing maker & taker as volume rises. Guards: negative / non-finite volume raise.
- **`round_trip_fee`** — maker-first `1000 * (.0040 + .0040) = 8.0`; taker-only (`taker_open=taker_close=True`) `1000 * (.0080 + .0080) = 16.0`; mixed (maker open, taker close) `1000 * (.0040 + .0080) = 12.0`. Guards: negative notional / rate / non-finite raise.
- **`margin_rate`** — `BTC high = .0002`, `BTC low = .0001`, `ETH high = .0004`; unknown base and bad `band` raise.
- **`margin_carry`** — opening-only for `hold_hours < 4` (`floor` = 0): `margin_carry(1000, 3, .0002) == 0.2`; 24h → `floor(6)` rollovers + open = `1000 * .0002 * 7 == 1.4`; 4h → `1 + 1 = 2` units → `1000 * .0002 * 2 == 0.4`; `0` hours → opening only. Guards: negative notional / hold / rate / non-finite raise.
- **Sanity vs the schedule** — a Tier-1 taker round trip on `€1000` notional is `€16` (1.60%); BTC short of `€1000` held 5 days (120h) at high band ≈ open + 30 rollovers = `1000 * .0002 * 31 = €6.2` (≈0.62%), consistent with §4's ~5-day BTC carry.

## Deferred / parked

Spread term (T0003), a combined total-trade-cost function, AoP qualification, stablecoin/FX schedule, the fiat-leg margin-long rate, the 3% liquidation fee; the rest of §9/§12 Phase-2 (registry hash-chain, multi-seed, SPA, acceptance suite).

## Closeout (planned)

On merge: append the `iter-017` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-017]` entry stays in the running log (drained at Phase-2 close-out).
