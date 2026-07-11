# B1 — seasonality conditioning on the adopted A2-4h ensemble (family opening design)

**Iteration:** iter-086 (unattended research loop; decisions log `[iter-086]`; family topic T0022, split from the T0016 umbrella). **Goal:** the B1 family's harness — leak-free intraday-seasonality + vol-state **conditioning overlay** on the adopted A2-4h ensemble — plus the pre-registered trial 1 (run in this iteration only if the harness lands with comfortable time margin; otherwise next loop invocation). Master-plan §5's brief is binding: conditioning on adopted signals, never a standalone high-turnover system; every read net-of-cost. *(Revised by the adversarial leak review — decision matrix pre-registered, slot key moved to the decision boundary, composition-invariant vol state, protocol grid pinned, edge cases closed; findings F1–F9.)*

## Hypothesis (trial 1, pre-registered `[iter-086]`)

Hour-of-day/day-of-week structure and intraday-vol state carry conditioning information for the adopted A2-4h ensemble: **restricting position updates to favorable windows (holding through unfavorable ones) and de-risking in high-vol states improves net-of-cost performance — primarily via turnover reduction — versus the unconditioned ensemble.** Arms: **A** = trials 37–39's equal-weight ensemble exactly as adopted; **B** = the same ensemble passed through the conditioning overlay. One treatment (the overlay), judged by the pre-registered decision matrix below.

## The overlay (new module `cli/alpha/b1.py`, mirroring the a1/a2 pattern)

1. **Slot key — on the decision boundary, not the bar-start stamp (F3)**: position `k` applies to the move `close[k] → close[k+1]`, executed at wall-clock `ts[k] + 4h`. Its cell is therefore `(hour, day_of_week)` **of `ts[k] + 4h`** (= `ts[k+1]` on a dense grid) — the same close-time-shifted identity as `expand_daily_positions`' pinned contract. Cells: `hour ∈ {0,4,8,12,16,20}` × `dow ∈ 0..6` = 42, purely calendar. (Keying on `ts[k]` would label every move with the previous slot — dow wrong exactly at the weekend transitions the family targets, and any future §6 execution-scheduler consumer would apply the windows 4 h off.)
2. **Favorable-window gate — the fitted component, estimated walk-forward only**:
   - Expanding annual walk-forward (this repo's first fold-internal estimator — no full-sample estimation anywhere): for each calendar year `Y`, cell gates are estimated from arm-A stamps **whose return interval closes ≤ Y-01-01T00:00Z** (the completion-time rule — F7) and applied throughout `Y`. Estimation rule (fixed): a cell is *favorable* iff arm A's net-of-cost return summed over its train stamps is `> 0` AND the cell has `≥ 100` train observations; thin cells default **open** (closed would silently zero early alt-era books).
   - **Effective burn-in disclosed (F8)**: the series starts 2013-09-10; at ~52 obs/cell/year the ≥100-obs rule leaves 2013–2015 effectively all-open — gates first bind in **2016**, giving ~10.3 of 12.5 years of live gating. The per-fold-year gated-cell counts in the engagement report surface this; it is a property of the data, not a knob.
3. **Hold-through-unfavorable semantics (the turnover-control mechanism)**: at a favorable stamp, arm B tracks the ensemble target times the vol scaler; at an unfavorable stamp, arm B **holds its previous position** (no trade, no turnover). It never forces flat — forced flattening would *add* churn, the exact fee suicide the plan warns against.
4. **Vol-state scaler (fixed constants, pre-registered — not tuned; composition-invariant per F4)**: at each decision boundary, **per asset**: trailing realized vol of its 15m log-close returns over the prior 96 bars (24 h) ÷ the rolling median of its **own** measure over the prior 180 boundaries → a per-asset state; the boundary's state = the **mean of the per-asset states** over assets with data (own-normalization makes listings step-free). **Scale = 0.5 if state > 1.5 else 1.0**, applied at update stamps only. **The scaler is active from the start of the series** (it is unfitted; only the gates have burn-in — F2), so arm B ≠ arm A from ~30 days in. Edge cases pinned (F7): fewer than 180 prior boundaries → per-asset state neutral (1.0); fewer than 48 of 96 15m bars for an asset → that asset contributes nothing that boundary; no asset with ≥ 48 bars → boundary state neutral. **Runtime assertion (F8)**: the 15m substrate's last close must reach the last 4h decision boundary — a future substrate refresh with a different cut must fail loudly, not silently un-condition the tail.
5. **Alignment**: 15m bar-START stamps; a boundary `T` uses 15m bars with `ts + 900s ≤ T` (fully closed at decision time). The `scales[k]`/`gates[k]` lists are indexed on the return index and keyed by boundary `ts[k] + 4h` (F7).

**Interfaces (produces)**:

```python
@dataclass(frozen=True, kw_only=True)
class B1Config:
    vol_lookback_bars: int = 96      # 15m bars = 24h
    vol_median_lookback: int = 180   # 4h boundaries = 30d
    vol_state_threshold: float = 1.5
    vol_scale_high: float = 0.5
    min_cell_obs: int = 100
    min_vol_bars: int = 48

def seasonality_gates(arm_noc_returns: list[float], union_ts: list[datetime], *, config: B1Config) -> list[int]
#   walk-forward gate per return index k (1 favorable / 0 hold), cell keyed on ts[k]+4h,
#   trained on returns whose interval closes <= Y-01-01T00:00Z
def vol_state_scale(m15_closes_by_asset: dict[str, tuple[list[datetime], list[float]]],
                    union_ts: list[datetime], *, config: B1Config) -> list[float]
def condition_positions(asset_positions: dict[str, list[float]], gates: list[int], scales: list[float]) -> dict[str, list[float]]
#   hold-through: gated stamps carry the previous conditioned position verbatim
```

## The trial protocol (when run) — decision matrix pre-registered (F1)

Arm A/B books → per-asset turnover costing at 0.006/side (the inline convention) → for arm B: `a1_kill_bar(book, benchmark_4h, n_trials=1, var_trials=0.0, mean_block=30, seed=42, n_resamples=2000, cost_stressed(×1.5), calendar-year slices stub-excluded, decisive_start=1380)`; SPA robustness grid **blocks {30, 102} × seeds {42, 7, 1234}** (F5); the **DSR leg is declared non-binding at n_trials=1** (expected-max-Sharpe is 0 at n=1, so DSR ≈ PSR vs 0 — the burden sits on SPA + worst-slice; stated in the record notes — F6). Head-to-head: `net_of_cost_verdict(B, A)` on the full window AND from 2016-01-01 (the first binding-gate year — the pre-2016 inert span dilutes the full-window read toward a false kill; F7).

**Engagement proof before any verdict (F2 — per mechanism, per year)**: gated-stamp count per fold year (gates mechanism), 0.5-scaled-stamp count per year (vol mechanism), arm-B turnover reduction vs arm A, and the count of stamps where positions differ. Either mechanism showing zero engagement across all years = dead knob = instrument finding, no verdict.

**The decision matrix (adopt/reject/park — fixed before the run):**

| Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from-2016 read primary) | Verdict |
|---|---|---|
| pass | B beats A (mean outperformance > 0 AND SPA p < 0.05) | **adopt** the overlay |
| pass | B > A point estimate but SPA n.s. AND turnover reduced ≥ 20% | **park** (variant candidates: window-only / vol-only attribution arms) |
| pass | B ≤ A | **reject** the overlay (arm B passing the bar merely inherits A's edge — not evidence for the knob) |
| fail | any | **reject** (a conditioning that breaks the adopted arm's bar is harmful) |

Registry: **new family key `B1`** (bucket budget B = 25 shared), `n_trials_in_family=1`, `variant="B1-conditioning-a2eq-v1"`, `dataset_hash = sha256(hex_4h + ":" + hex_15m)` where `hex_4h` is **the literal trials-37–39 dataset hash `81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f`** and `hex_15m` is `0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1`, both components + the recipe verbatim in `notes` (byte-reproducible — F7). Metrics mirror the trials-37–39 key set + the engagement metrics; **bools coerced to 0/1 ints, all keys str** (the registry's type-strict finiteness check rejects bool and non-str keys — F9).

## Out of scope

Standalone intraday systems; 1h-cadence variants; maker-fill modeling (T0014's spread term upgrades this family later); conditioning the full record-44 combination (attribution — ensemble-only isolates the treatment); any change to `cli/portfolio`, the engine, or adopted artifacts. The overlay consumes `a2_book_returns`/ensemble outputs as-is.

## Closeout

Harness merged with this spec/plan regardless of whether trial 1 runs tonight; T0022 tracks the family; the trial's verdict (when run) appends to the registry + decisions log per the standing discipline.
