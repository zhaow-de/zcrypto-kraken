# Combined-system builder (design)

**Iteration:** iter-063 (Phase-5 interlude, unattended). **Goal:** the adopted P1 system's full pipeline as one committed, tested function — `cli/portfolio/build_combined_system` — replacing scratchpad-driver archaeology for the holdout event (T0017's mechanical procedure) and the Phase-6 daily cycle, with the frozen figures as a standing regression guard.

## Why now

The deployable system (registry record 33) is defined by a pipeline that exists only in session-scratchpad drivers (`b3b4_dynamic_run.py` → `combination_trial_run.py`), re-verified against frozen figures each time by hand-written QA gates. The holdout event's pre-registered procedure ("compute exactly two systems, all parameters frozen as of record 33") and the Phase-6 engine both consume exactly this construction. Committing it makes the event mechanical and the QA gates permanent.

## Package: `cli/portfolio/`

New sibling package (the §12 Phase-5 assembly layer): `errors.py` (`PortfolioError`), `builder.py`, `__init__.py` re-exporting `CombinedSystemConfig`, `CombinedSystemResult`, `PortfolioError`, `build_combined_system`. Stdlib style of the neighbors.

## API

```python
@dataclass(frozen=True)
class CombinedSystemConfig:
    basket_lookback: int = 30
    gate_window: int = 200
    target_vol_annual: float = 0.10       # divided by sqrt(periods_per_year) internally
    vol_lookback: int = 30
    max_leverage: float = 1.0
    periods_per_year: int = 365
    spot_fee_per_side: float = 0.006      # tier-1 maker x1.5 = 40bps fee + 20bps headroom;
                                          # T0014 (2026-07-22) measured the spread at 2-4bps, so the
                                          # headroom is 5-10x it -- but maker-vs-taker is unsettled
                                          # and dominates; see T0090 before changing this.
    long_cap: float = 0.20
    short_cap: float = 0.10
    governor: GovernorConfig = GovernorConfig()

@dataclass(frozen=True)
class CombinedSystemResult:
    net_of_cost: list[float]              # THE system: capped + governed, net of costs
    benchmark_net_of_cost: list[float]    # the frozen benchmark (uncapped, ungoverned)
    capped_net_of_cost: list[float]       # capped, pre-governor (isolates the cap's effect)
    positions: dict[str, list[float]]     # final per-asset positions: multipliers[k] * capped[a][k]
    multipliers: list[float]              # the governor's stream
    governor: GovernorResult
    cap_breach_bars: int                  # bars where >=1 asset was clipped
    n_periods: int

def build_combined_system(
    prices_by_asset: dict[str, list[float | None]], *, config: CombinedSystemConfig = CombinedSystemConfig()
) -> CombinedSystemResult
```

## Pipeline (verbatim the QA-verified iter-059 construction — composition, not reimplementation)

1. `b2 = dynamic_inverse_vol_basket(prices_by_asset, lookback)` → equity index (cumprod, seeded 1.0) → `gate = sma_gate(equity, window)`; `vt = vol_target(b2, target_vol/sqrt(ppy), lookback=vol_lookback, max_leverage)`; `l3[k] = gate[k]·vt[k]`.
2. `w = _inverse_vol_weights(prices_by_asset, lookback)` and `ret = _asset_returns(...)` — **imported from `cli.alpha.a1` deliberately** (same code path = the reproduction guarantee every QA gate has relied on; a comment marks the cross-package private import; promoting them to public API is out of scope — logged `[iter-063]`).
3. Benchmark positions `w·l3` → benchmark net-of-cost (per-asset |Δposition| turnover × fee, summed).
4. `capped = apply_position_caps(bench_positions, long_cap, short_cap)` → capped gross `Σ capped·ret` (None → 0 contribution) → capped net-of-cost (same turnover rule on capped positions).
5. `gov = drawdown_governor(capped_net_of_cost, config.governor)`; final `positions[a][k] = gov.multipliers[k]·capped[a][k]`; `net_of_cost = gov.governed_returns` (the linear-cost overlay approximation, logged iter-058).
6. Validation: `PortfolioError` on empty/non-dict prices or non-finite/non-positive config numerics; everything deeper delegates to the building blocks' own typed errors.

## Tests

**Unit (synthetic prices, always run):**

- Identities: `net_of_cost == governor.governed_returns`; `positions[a][k] == multipliers[k]·capped[a][k]`; all series lengths equal `n_periods`.
- Composition order: with a 2-asset construction where one asset's vol → tiny (inverse-vol weight ≈ 0.9), the cap clips (`cap_breach_bars > 0`, `max positions ≤ long_cap`).
- Disable-degeneracy: with `long_cap` huge and a governor config whose thresholds can't fire, `net_of_cost == benchmark_net_of_cost` element-wise (the overlays compose to identity) — the strongest wiring test.
- Warm-up: all positions 0.0 until the gate window passes (gate warm-up flat).
- No look-ahead: perturbing the final price leaves all earlier positions unchanged.
- `PortfolioError` cases: empty dict, non-dict, zero/negative fee, bad ppy.

**Integration (skipif `data/ohlc-full` absent — the frozen-figure regression guard):** build from the real 10-asset dataset and assert record 33's figures: system net-of-cost Sharpe ≈ 1.3263 (tol 0.005), maxDD ≈ 0.1449 (tol 0.003), benchmark Sharpe ≈ 1.2455 (tol 0.005), `cap_breach_bars == 100`, governor occupancy {1.0: 2476, 0.5: 1711, 0.25: 394}.

## Out of scope

- CLI subcommand, weight-level cost exactness (Phase 6), multi-sleeve combination (waits on T0009), promoting a1's helpers to public API. No README change (library only, per `readme-usage.md` — subcommands/options only).
