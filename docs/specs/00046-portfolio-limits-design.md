# §10 portfolio limits — gross, net band, margin floor (design)

**Iteration:** iter-088 (unattended research loop; decisions log `[iter-088]`). **Goal:** the remaining §10 portfolio limits as tested code in `cli/risk/limits.py` — T0016's standing prerequisite for any short-carrying or levered family (B4-legs/B3). §10 mandates them "hard, enforced in code pre-trade"; they were deliberately deferred in iter-059 because they never bind on the long-only P1 book (max gross 0.68×). **No consumer exists yet** — the deliverable is the tested functions with §10-ratified constants as defaults, in the exact idiom `apply_position_caps` established (pure pre-trade transforms, no redistribution/optimization, `RiskError` guards, inclusive at the limit). Wiring into a family harness happens when B4/B3 open.

## The three limits (constants ratified 2026-07-06, D1 — master plan §10 table)

1. **`apply_gross_leverage_cap(positions, *, soft_cap=1.5, hard_cap=2.0)`** — per bar: `gross_k = Σ_assets |w|`; if `gross_k > soft_cap`, **scale every asset's position at k by `soft_cap / gross_k`** (proportional — preserves the book's relative structure; the pre-trade governor always targets the soft cap, leaving headroom below hard). `hard_cap` is validated (`soft_cap ≤ hard_cap`) and exists as the named constant consumers alert on; a pre-trade transform that already scales to soft can never emit gross > soft, so hard is a guard-rail constant + input validation, not a second code path. Inclusive: `gross_k == soft_cap` passes unscaled.
2. **`apply_net_exposure_band(positions, *, short_bound=-0.5, long_bound=1.0)`** — per bar: `net_k = Σ_assets w`; if `net_k > long_bound`, scale the whole bar by `long_bound / net_k`; if `net_k < short_bound`, scale by `short_bound / net_k` (both factors ∈ (0,1)). **Whole-book proportional scaling on both sides** — the conservative, structure-preserving reading (it reduces gross too; a §10 limit breach is a de-risking event, never a re-optimization). Inclusive at both bounds. `net_k == 0` never scales.
3. **`margin_level(bar_positions) -> float` + `apply_margin_floor(positions, *, floor=2.5)`** — the self-imposed ≥250% margin-level floor, with the **documented simple margin model** (unit NAV, quote-currency collateral per §10):
   - `long_gross`, `short_gross` from the bar's weights; **margin used** `m = short_gross + max(0.0, long_gross − max(0.0, 1.0 − short_gross))` — shorts are fully margin-extended and consume collateral first; longs draw margin only beyond the remaining cash. (This is deliberately conservative vs Kraken's tiered leverage schedules; the live engine reconciles against the venue's real numbers at 6b — this function is for backtest/pre-trade research use.)
   - `margin_level = equity / m` with `equity = 1.0` (unit NAV); `m == 0` → `inf` (no margin in use — a pure long-only ≤1.0 book never binds).
   - `apply_margin_floor`: if `margin_level < floor`, scale the whole bar by the **largest factor `s ∈ (0,1)` such that the scaled bar's margin level ≥ floor**, computed in closed form from the model (both gross terms scale linearly in `s`, the cash offset does not — the implementation derives and documents the closed form; a bisection fallback is NOT acceptable, the model is piecewise-linear in `s`). Inclusive at the floor.
4. **Composition note (documented, not enforced)**: the limits are individually idempotent (`f(f(x)) = f(x)`); applying one may re-tighten another's input, and the future consumer decides the order (a fixed-point loop is YAGNI until a family binds them). The module docstring states the recommended order: caps → gross → net → margin floor.

## Testing (TDD)

Per function: pass-through below the limit (bit-identical lists returned — no float churn on the untouched path); exactly-at-limit inclusive; single-bar breach scaled to exactly the limit (assert the recomputed gross/net/margin-level equals the bound within 1e-12); proportionality (relative weights preserved); mixed long/short books; the margin model's closed-form factor verified against a brute-force scan at 1e-6 resolution on three fixtures (long-levered, short-heavy, mixed); guards (empty/NaN/negative caps/soft>hard/mismatched lengths) raising `RiskError`; idempotence per function; `margin_level` unit cases (flat book → inf; 0.5 long → inf; 1.5 long → m=0.5 → level 2.0; 0.3 short + 0.8 long → m = 0.3 + max(0, 0.8 − 0.7) = 0.4 → level 2.5 exactly at floor).

## Out of scope

Wiring into any backtest/driver (no consumer yet — B4/B3's opening iterations do it); the runtime/live governor (6b); Kraken's real tiered margin schedule; the drawdown ladder (already live in `cli/risk/governor.py`); changing `apply_position_caps`.

## Closeout

T0016's standing-prerequisite item flips to done-for-the-code-part (Done so far + the item reworded to the wiring remainder); iterations-history entry; PR; merge (loop mode).
