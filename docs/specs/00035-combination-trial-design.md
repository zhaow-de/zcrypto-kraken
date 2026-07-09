# Combination trial — the one-sleeve combined system (design)

**Iteration:** iter-059 (Phase 5, unattended). **Goal:** assemble and verdict the §12-named combination trial — **B3+vt-dynamic + §10 per-asset cap + §10 drawdown governor** — as the first non-A registry event, and ship the per-asset cap as tested code (the question spec `00034` scoped out).

## What §12 pre-registers

Phase 5: *"assemble + re-validate the combined system; the combination is a new registered trial, default method inverse-vol of sleeves."* One sleeve exists today (weight 1.0), so the inverse-vol default is trivially satisfied; a future second sleeve (e.g. A1-long/flat, pending T0009) re-runs the combination as a new trial.

## Empirical basis (probed before design, logged `[iter-059]`)

The §10 **20 %-NAV per-asset cap binds** on the candidate: max per-asset exposure 34.8 % (BTC, 2016-04-24), 100 of 4581 bars breach pre-governor. Gross leverage maxes at 0.68× — the 1.5×/2.0× gross, net-exposure, and margin-floor limits never bind on this long-only book, so the cap is the only §10 portfolio limit that needs code now (YAGNI on the rest; they return with a short-carrying or levered sleeve).

## The combined-book construction (decided, logged `[iter-059]`)

1. **Base positions**: `p_a[k] = w_a[k] · l3[k]` — the frozen candidate's per-asset exposures (dynamic inverse-vol weights × gate·vol-target scalar, the exact iter-055 construction).
2. **Cap**: `c_a[k] = min(p_a[k], 0.20)` — **clip, no redistribution** (a §10 limit is a pre-trade governor, not an optimizer; excess sits in cash). Short cap −10 % is implemented for generality but inert on this long-only book.
3. **Capped-book net-of-cost**: gross `g_c[k] = Σ_a c_a[k] · r_a[k]`; net-of-cost subtracts per-asset turnover of the capped positions × `SPOT_FEE = 0.006`. (No short leg → no margin carry.)
4. **Governor**: `drawdown_governor(noc_capped, config=GovernorConfig())` — the governor runs on the **capped** book's own series; cap-then-govern ordering keeps every final position under the cap since the multiplier ≤ 1. Same linear-cost overlay approximation as iter-058 (logged there).
5. **The trial's book** = the governed returns. **The comparator** = the frozen benchmark B3+vt-dynamic net-of-cost, uncapped and ungoverned (the §9 frozen construction, exactly as adopted).

## Committed code: `cli/risk/limits.py` (TDD)

```python
def apply_position_caps(
    positions: dict[str, list[float]], *, long_cap: float = 0.20, short_cap: float = 0.10
) -> dict[str, list[float]]
```

Per asset and bar: `min(p, long_cap)` for `p ≥ 0`, `max(p, -short_cap)` for `p < 0`. Validation (`RiskError`, no silent coercion): non-empty dict of non-empty equal-length lists; finite positions; caps finite and > 0. Pure, stdlib-only, mirroring `cli/risk/governor.py`. Tests: long clip at/above/below the cap (inclusive: exactly 0.20 passes uncapped), short clip symmetric, mixed series, ragged/empty/non-finite/invalid-cap `RiskError` cases, output-shape identity.

`cli/risk/__init__.py` re-exports `apply_position_caps`.

## The trial protocol (pre-registered verdict criteria, logged `[iter-059]` before any number is read)

Scratchpad driver (not committed), QA gates first:

- **QA-1 (frozen reference)**: the rebuilt benchmark reproduces zero-fee 1.419 / maxDD 21.9 % and net-of-cost 1.2455 full / 1.2781 k≥230.
- **QA-2 (iter-058 reproduction)**: the governor on the *uncapped* book reproduces Sharpe 1.3300 / maxDD 14.49 % through this driver's own code path.
- **QA-3 (engagement)**: the cap demonstrably clips (max pre-cap exposure 34.8 % → post-cap ≤ 20 %; breach-bar count reported and > 0, ≈100 bars per the probe), and the governor's occupancy/triggers are reported. An inert treatment invalidates the run.

Then, book = combined (capped + governed), benchmark = frozen B3+vt-dynamic net-of-cost:

- `net_of_cost_verdict(book, benchmark, mean_block=17, seed=42, n_resamples=2000)` — **and the reverse direction** (benchmark vs book), plus seed-stability (seeds 42/7/1234). A risk overlay trades return for vol: report the return give-up and both SPA directions symmetrically.
- `benchmark_relative_worst_slice` by calendar year (book vs benchmark), **and** the literal absolute worst-slice reading (recorded as it comes — the absolute leg is T0009-flagged uninformative; never weakened).
- **Cost stress**: fees ×1.5 and ×2 applied to *both* sides' turnover, governor re-run on each stressed capped series; combined must remain ≥ the equally-stressed benchmark (point Sharpe).
- **DSR**: at `n_trials=1` deflation is nil (expected-max of one trial); record PSR/DSR as computed with `var_trials` from the single trial noted as degenerate-by-construction.
- Full-window and k≥230 for every figure.

**ADOPT iff**: (a) QA-1/2/3 pass; (b) combined net-of-cost maxDD ≤ 15 % (the §10 budget); (c) combined net-of-cost Sharpe ≥ the benchmark's 1.2455 (point, Sharpe-primary per §9 precedent); (d) both-direction SPA + return give-up reported. Otherwise reject/park with the failing leg named. Expected but not assumed: iter-058's uncapped result (Sharpe 1.3300, maxDD 14.49 %) suggests adopt; the cap's drag on 2016-era BTC concentration is the open empirical question this trial answers.

## Registry event (first non-A family; first schema-v3 `variant` use)

- `family="P1"`, `variant="B3vtdyn+gov+cap"`, `n_trials_in_family=1`, `iteration="iter-059"`.
- `spec_hash` = sha256 of this spec file; `dataset_hash` = the sorted per-asset manifest sha256 and **must equal record 1's** (else STOP — dataset drift); `seeds=[42, 7, 1234]`; metrics = the protocol figures above; `verdict` per the pre-registered criteria; `notes` carries the two iter-058 governor properties (per-cycle budget under mechanical re-arm; daily rule as tail backstop) and the cap-binding stats.
- No Bucket-A/B/C budget is touched (the combination is the plan's own named trial). The A-family's 8 reserved trials stay held on T0009.

## Out of scope

- **Stress suite** (2× costs beyond the kill-bar rung, taker-only, borrow-unavailable, flash-wick replay, start-date sensitivity) — Phase-5 queue item 3, next iteration (registered in `10.phase4-closeout.md` §Phase-5 orientation).
- **Gross/net/margin-floor limits as code** — never bind on this book (probe above); they return with a short-carrying or levered sleeve.
- **Multi-sleeve combination** — waits on T0009 (A1-long/flat admission); re-runs as a new P1 trial.
- **Holdout** — untouched, as always (look budget 1, human present).
